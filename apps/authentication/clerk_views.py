"""
"Continue with Google" via Clerk.

Clerk is used purely as an **OAuth broker**, not as the identity system.
Django + SimpleJWT remains the source of truth for accounts, and this endpoint
trades a verified Clerk session for our own JWT pair.

Why that shape rather than handing Clerk the whole auth system:

* Orders, addresses, quotations and inquiries are all foreign-keyed to
  ``auth.User``. Moving identity to Clerk would mean re-keying live customer
  data - a migration with real downside and no customer-visible benefit.
* Email/password sign-in keeps working if Clerk is ever down, over quota, or
  dropped later. An outage costs the Google button, not the ability to log in.
* The account a Google sign-in lands on is the same Django account the customer
  already had, so their order history simply appears.

Security notes worth keeping:

* The session token's signature is verified against Clerk's JWKS. Decoding
  without verification would let anyone forge a login by crafting JSON - the
  single most common way this is implemented insecurely.
* ``iss`` is pinned to our own Clerk instance, so a valid token from a
  *different* Clerk application cannot log anyone in here.
* ``azp`` (authorised party) is checked against our own origins when
  CLERK_ALLOWED_ORIGINS is set, which is what stops a token minted for another
  site's frontend being replayed at ours.
* The email is read from Clerk's **Backend API**, not from the token, and is
  accepted only when Clerk reports it verified. Linking accounts on a
  provider-verified email is safe; linking on a self-asserted one is the
  account-takeover shape deliberately kept out of ``PATCH /api/auth/me/``.
* Users created this way get an unusable password, so the account cannot be
  entered through the password form without going through a reset.
"""
import base64
import logging

import jwt
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from jwt import PyJWKClient
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import UserSerializer

logger = logging.getLogger('apps.authentication')

CLERK_API_BASE = 'https://api.clerk.com/v1'

# PyJWKClient caches fetched signing keys, so keep one instance per process
# instead of re-downloading the key set on every sign-in.
_jwk_client = None
_jwk_client_url = None


def clerk_domain():
    """
    Our Clerk instance's frontend domain, e.g. ``foo-bar-12.clerk.accounts.dev``.

    Derived from the publishable key so the only things that ever need setting
    are the two keys Clerk shows on its dashboard. A publishable key is
    ``pk_test_<base64url of "domain$">`` (or ``pk_live_``), so the domain can be
    decoded rather than configured by hand and gotten wrong.
    """
    explicit = getattr(settings, 'CLERK_FRONTEND_API', '').strip()
    if explicit:
        return explicit.replace('https://', '').strip('/')

    pk = getattr(settings, 'CLERK_PUBLISHABLE_KEY', '').strip()
    if not pk:
        return ''
    encoded = pk.split('_', 2)[-1]
    try:
        # base64url without padding - restore it before decoding.
        padded = encoded + '=' * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode('utf-8')
    except Exception:
        logger.error('CLERK_PUBLISHABLE_KEY is malformed; cannot derive Clerk domain')
        return ''
    return decoded.rstrip('$').strip('/')


def _jwks_client():
    """JWKS client for the current Clerk domain, rebuilt only if the URL changes."""
    global _jwk_client, _jwk_client_url

    url = getattr(settings, 'CLERK_JWKS_URL', '').strip()
    if not url:
        domain = clerk_domain()
        if not domain:
            return None
        url = f'https://{domain}/.well-known/jwks.json'

    if _jwk_client is None or _jwk_client_url != url:
        # lifespan: re-fetch keys periodically so Clerk key rotation is picked
        # up without a redeploy.
        _jwk_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        _jwk_client_url = url
    return _jwk_client


def _unique_username(email):
    """
    Derive a stable, unique username from the email local-part.

    Usernames must be unique, and two people can hold name@gmail.com and
    name@yahoo.com - so a bare local-part collides. Suffix until free.
    """
    base = (email.split('@')[0] or 'user')[:140] or 'user'
    candidate = base
    n = 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f'{base}{n}'[:150]
    return candidate


def _verified_email_from_clerk(user_id):
    """
    Fetch the Clerk user and return (email, first_name, last_name).

    The email comes from the Backend API rather than the session token because
    the default token carries no email claim, and because this response also
    states whether Clerk actually verified it. Returns (None, ...) when there is
    no verified primary address.
    """
    secret = getattr(settings, 'CLERK_SECRET_KEY', '').strip()
    resp = requests.get(
        f'{CLERK_API_BASE}/users/{user_id}',
        headers={'Authorization': f'Bearer {secret}'},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.warning('Clerk Backend API returned HTTP %s for %s', resp.status_code, user_id)
        return None, '', ''

    data = resp.json()
    primary_id = data.get('primary_email_address_id')
    addresses = data.get('email_addresses') or []

    # Prefer the primary address; fall back to the first verified one so a user
    # whose primary is unverified can still sign in with a verified alias.
    chosen = next((a for a in addresses if a.get('id') == primary_id), None)
    if not chosen or (chosen.get('verification') or {}).get('status') != 'verified':
        chosen = next(
            (a for a in addresses
             if (a.get('verification') or {}).get('status') == 'verified'),
            None,
        )
    if not chosen:
        return None, '', ''

    email = (chosen.get('email_address') or '').strip().lower()
    return email or None, (data.get('first_name') or ''), (data.get('last_name') or '')


class ClerkLoginView(APIView):
    """
    POST /api/auth/clerk/   { "token": "<Clerk session JWT>" }

    Returns the same payload as /api/auth/login/, so the frontend stores the
    result identically no matter which button the customer pressed.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        token = (request.data.get('token') or '').strip()
        if not token:
            return Response({'detail': 'Missing Clerk session token.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not getattr(settings, 'CLERK_SECRET_KEY', '').strip():
            logger.error('Clerk sign-in attempted but CLERK_SECRET_KEY is not set')
            return Response({'detail': 'Google sign-in is not configured on this server.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        jwks = _jwks_client()
        if jwks is None:
            logger.error('Clerk sign-in attempted but no publishable key / JWKS URL is set')
            return Response({'detail': 'Google sign-in is not configured on this server.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # ── verify the token ────────────────────────────────────────────
        try:
            signing_key = jwks.get_signing_key_from_jwt(token)
        except Exception as exc:
            logger.warning('Could not fetch Clerk signing key: %s', exc)
            return Response({'detail': 'Could not verify Google sign-in. Please try again.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        issuer = f'https://{clerk_domain()}'
        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=['RS256'],
                issuer=issuer,
                # Clerk session tokens carry no `aud` by default.
                options={'verify_aud': False, 'require': ['exp', 'iat', 'sub']},
                leeway=5,  # tolerate small clock skew between us and Clerk
            )
        except jwt.ExpiredSignatureError:
            return Response({'detail': 'Your sign-in expired. Please try again.'},
                            status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidIssuerError:
            logger.warning('Clerk token issuer mismatch (expected %s)', issuer)
            return Response({'detail': 'This sign-in was not issued for Eng-Mart.'},
                            status=status.HTTP_401_UNAUTHORIZED)
        except jwt.InvalidTokenError as exc:
            logger.warning('Invalid Clerk session token: %s', exc)
            return Response({'detail': 'Google sign-in failed. Please try again.'},
                            status=status.HTTP_401_UNAUTHORIZED)

        # `azp` is the origin the token was minted for. Enforced only when
        # configured, so local development does not need the list maintained.
        allowed = [o.strip() for o in getattr(settings, 'CLERK_ALLOWED_ORIGINS', '').split(',') if o.strip()]
        azp = claims.get('azp')
        if allowed and azp and azp not in allowed:
            logger.warning('Clerk token azp %r not in allowed origins', azp)
            return Response({'detail': 'This sign-in was not issued for Eng-Mart.'},
                            status=status.HTTP_401_UNAUTHORIZED)

        # ── resolve the verified email ──────────────────────────────────
        try:
            email, given, family = _verified_email_from_clerk(claims['sub'])
        except requests.RequestException as exc:
            logger.warning('Could not reach Clerk Backend API: %s', exc)
            return Response({'detail': 'Could not reach Google to verify sign-in. Please try again.'},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if not email:
            return Response({'detail': 'Your Google account has no verified email address.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # ── find or create the Django account ───────────────────────────
        with transaction.atomic():
            user = User.objects.filter(email__iexact=email).first()
            created = False
            if user is None:
                user = User.objects.create(
                    username=_unique_username(email),
                    email=email,
                    first_name=given[:150],
                    last_name=family[:150],
                )
                user.set_unusable_password()
                user.save()
                created = True
            elif not user.first_name and given:
                user.first_name = given[:150]
                user.last_name = family[:150]
                user.save(update_fields=['first_name', 'last_name'])

        if not user.is_active:
            return Response({'detail': 'This account has been disabled.'},
                            status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        logger.info('Clerk Google sign-in %s for %s', 'created' if created else 'matched', email)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
            'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
