"""
Clerk JWT Authentication for Django REST Framework.

Validates Clerk-issued JWTs using the JWKS endpoint.
Attach to protected views via:
    authentication_classes = [ClerkJWTAuthentication]
    permission_classes = [IsClerkAdmin]
"""
import logging
import jwt
import requests
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)

# Cache the JWKS keys in memory to avoid fetching on every request
_jwks_cache = None


def get_jwks():
    """Fetch and cache Clerk's JWKS (JSON Web Key Set)."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    jwks_url = settings.CLERK_JWKS_URL
    if not jwks_url or 'placeholder' in jwks_url:
        logger.warning('CLERK_JWKS_URL not configured — Clerk auth disabled')
        return None

    try:
        response = requests.get(jwks_url, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
        return _jwks_cache
    except requests.RequestException as e:
        logger.error(f'Failed to fetch Clerk JWKS: {e}')
        return None


def clear_jwks_cache():
    """Clear the JWKS cache (useful when keys rotate)."""
    global _jwks_cache
    _jwks_cache = None


class ClerkJWTAuthentication(BaseAuthentication):
    """
    DRF Authentication class that validates Clerk JWTs.

    Flow:
    1. Extract Bearer token from Authorization header
    2. Decode and verify JWT using Clerk's public keys (JWKS)
    3. Get or create a Django User from the Clerk user_id (sub claim)
    4. Return (user, decoded_payload) tuple
    """

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return None  # No token — let other auth backends handle it

        token = auth_header[7:]  # Strip "Bearer "
        payload = self._verify_token(token)
        user = self._get_or_create_user(payload)
        return (user, payload)

    def _verify_token(self, token):
        """Verify the JWT signature and claims using Clerk's JWKS."""
        jwks = get_jwks()
        if jwks is None:
            raise AuthenticationFailed('Clerk authentication is not configured.')

        try:
            # Get the signing key from JWKS
            jwks_client = jwt.PyJWKClient(settings.CLERK_JWKS_URL)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            # Decode and verify
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=['RS256'],
                options={
                    'verify_exp': True,
                    'verify_aud': False,  # Clerk doesn't always set aud
                },
            )
            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token has expired.')
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f'Invalid token: {str(e)}')

    def _get_or_create_user(self, payload):
        """
        Map Clerk user to a Django User.
        Uses Clerk's 'sub' claim as the username.
        """
        clerk_user_id = payload.get('sub')
        if not clerk_user_id:
            raise AuthenticationFailed('Token missing user ID (sub claim).')

        # Get or create a Django user for this Clerk user
        user, created = User.objects.get_or_create(
            username=clerk_user_id,
            defaults={
                'first_name': payload.get('first_name', ''),
                'last_name': payload.get('last_name', ''),
                'email': payload.get('email', ''),
                'is_active': True,
            },
        )

        if created:
            logger.info(f'Created Django user for Clerk user: {clerk_user_id}')

        return user

    def authenticate_header(self, request):
        return 'Bearer'
