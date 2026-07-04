"""
Custom permissions for Clerk-authenticated requests.
"""
from rest_framework.permissions import BasePermission


class IsClerkAuthenticated(BasePermission):
    """
    Allow access only to Clerk-authenticated users.
    Use on any endpoint that requires login.
    """
    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.auth is not None  # auth contains Clerk JWT payload
        )


class IsClerkAdmin(BasePermission):
    """
    Allow access only to users with admin role in Clerk metadata.

    To set up: In Clerk Dashboard → Users → select user →
    Public Metadata → add: {"role": "admin"}

    Alternatively, checks if the Django user is a superuser
    (for backward compatibility with Django admin).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if Django superuser
        if request.user.is_superuser:
            return True

        # Check Clerk JWT metadata for admin role
        if request.auth and isinstance(request.auth, dict):
            metadata = request.auth.get('public_metadata', {})
            if not metadata:
                metadata = request.auth.get('metadata', {})
            return metadata.get('role') == 'admin'

        return False
