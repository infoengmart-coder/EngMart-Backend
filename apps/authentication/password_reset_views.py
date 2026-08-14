"""
Forgot / reset password.

Flow (the standard one, and the one customers expect):

  1. POST /api/auth/password-reset/          { email }
     -> always answers 200, emails a link ONLY if that account exists
  2. Customer clicks the link: /reset-password?uid=...&token=...
  3. POST /api/auth/password-reset/confirm/  { uid, token, password }
     -> sets the new password and invalidates the link

Security decisions worth keeping:

* **The request endpoint never reveals whether an email is registered.** Saying
  "no account with that email" turns this form into a tool for checking which of
  your customers shop here.
* Tokens come from Django's ``PasswordResetTokenGenerator``: signed, expiring
  (``PASSWORD_RESET_TIMEOUT``), and **single-use** — the token embeds the current
  password hash and last-login, so it stops working the moment the password
  changes.
* The new password goes through Django's validators (length, common passwords,
  all-numeric), the same rules registration uses.
* Accounts created via Google have an unusable password. A reset gives them a
  real one, which is correct — it is a legitimate way to add password sign-in.
"""
import logging

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.email import send_password_reset_email

logger = logging.getLogger('apps.authentication')

# Deliberately identical for "sent" and "no such account" — see module docstring.
GENERIC_OK = {
    'detail': 'If an account exists for that email address, we have sent a '
              'password reset link. Please check your inbox.'
}


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ — email a reset link."""
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get('email') or '').strip()
        if not email:
            return Response({'email': ['Please enter your email address.']},
                            status=status.HTTP_400_BAD_REQUEST)

        # An email can, in principle, be on more than one account; send to each
        # active one rather than guessing which the customer meant.
        users = User.objects.filter(email__iexact=email, is_active=True)
        for user in users:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            send_password_reset_email(user, uid, token)
            logger.info('Password reset link sent for user id %s', user.pk)

        if not users:
            # Log it (so the shop can spot typos in support requests) but tell
            # the caller the same thing either way.
            logger.info('Password reset requested for unknown email')

        return Response(GENERIC_OK)


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — set the new password."""
    permission_classes = [AllowAny]

    def post(self, request):
        uid = (request.data.get('uid') or '').strip()
        token = (request.data.get('token') or '').strip()
        password = request.data.get('password') or ''

        if not uid or not token or not password:
            return Response(
                {'detail': 'This reset link is incomplete. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            # Same message as a bad token: do not confirm which part was wrong.
            return Response(
                {'detail': 'This reset link is invalid or has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response(
                {'detail': 'This reset link is invalid or has expired. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password, user)
        except DjangoValidationError as exc:
            return Response({'password': list(exc.messages)},
                            status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save(update_fields=['password'])
        logger.info('Password reset completed for user id %s', user.pk)

        return Response({'detail': 'Your password has been changed. You can now sign in.'})
