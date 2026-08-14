"""
Shared DRF permission classes for Eng-Mart.

The project uses SimpleJWT. Admin access is granted to Django staff accounts
(is_staff=True) — the same accounts the frontend treats as `is_admin`.
"""
from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminUser(BasePermission):
    """
    Allow access only to authenticated staff accounts.

    Use on endpoints that expose or mutate admin-only data
    (orders list, customers, reports, stats, promo CRUD, inquiry management).
    """
    message = 'Admin privileges are required for this action.'

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)


class IsAdminOrReadOnly(BasePermission):
    """
    Public, unauthenticated read (GET/HEAD/OPTIONS) for everyone.
    Writes (POST/PUT/PATCH/DELETE) require an authenticated staff account.

    Use on public catalog endpoints that also serve admin CRUD
    (products, brands, categories, banners).
    """
    message = 'Admin privileges are required to modify this resource.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        return bool(user and user.is_authenticated and user.is_staff)
