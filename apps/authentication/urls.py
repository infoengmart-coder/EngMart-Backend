from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .clerk_views import ClerkLoginView
from .password_reset_views import PasswordResetConfirmView, PasswordResetRequestView
from .views import LoginView, RegisterView, UserInfoView, LogoutView

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    # "Continue with Google" — Clerk brokers the OAuth flow, this trades the
    # resulting Clerk session for our own JWT pair.
    path('clerk/', ClerkLoginView.as_view(), name='auth-clerk'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('me/', UserInfoView.as_view(), name='auth-me'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
]
