from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import LoginSerializer, RegisterSerializer, UserSerializer


class LoginView(APIView):
    """POST /api/auth/login/ — Authenticate and return JWT tokens."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user).data

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': user_data,
        })


class RegisterView(APIView):
    """POST /api/auth/register/ — Create a new user account."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        user_data = UserSerializer(user).data

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': user_data,
        }, status=status.HTTP_201_CREATED)


class UserInfoView(APIView):
    """
    GET   /api/auth/me/ — Return current authenticated user info.
    PATCH /api/auth/me/ — Update the signed-in user's own profile.
    """
    permission_classes = [IsAuthenticated]

    # Only these may be self-edited.
    # - is_staff/is_superuser are excluded so a customer cannot escalate privileges.
    # - email is excluded because account-scoped data is looked up by it; letting a
    #   user re-point their address would expose another customer's quotes/inquiries.
    #   Changing an email needs a verification flow, which does not exist yet.
    EDITABLE_FIELDS = ['first_name', 'last_name']

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        user = request.user
        for field in self.EDITABLE_FIELDS:
            if field in request.data:
                setattr(user, field, request.data[field])
        user.save(update_fields=self.EDITABLE_FIELDS)
        return Response(UserSerializer(user).data)


class LogoutView(APIView):
    """POST /api/auth/logout/ — Blacklist the refresh token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass  # Token may already be blacklisted or invalid
        return Response({'detail': 'Logged out.'}, status=status.HTTP_200_OK)
