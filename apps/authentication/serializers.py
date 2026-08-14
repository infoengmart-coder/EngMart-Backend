from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate


class LoginSerializer(serializers.Serializer):
    """Accepts username or email + password."""
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get('username', '').strip()
        password = attrs.get('password', '')

        if not username or not password:
            raise serializers.ValidationError('Both username and password are required.')

        # Try authenticating by username first
        user = authenticate(username=username, password=password)

        # If that fails, treat the input as an email address.
        #
        # Django does NOT enforce unique emails, so several accounts can share
        # one. `User.objects.get(email=...)` then raises MultipleObjectsReturned,
        # which used to escape as an HTTP 500 and made login impossible for that
        # address. Try every matching account instead, and let the password
        # decide which one it is.
        if user is None:
            for candidate in User.objects.filter(email__iexact=username).order_by('id'):
                user = authenticate(username=candidate.username, password=password)
                if user is not None:
                    break

        if user is None:
            raise serializers.ValidationError('Invalid credentials.')

        if not user.is_active:
            raise serializers.ValidationError('This account is disabled.')

        attrs['user'] = user
        return attrs


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password', 'password_confirm']

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        return attrs

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user


class UserSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'name', 'is_admin', 'date_joined']

    def get_is_admin(self, obj):
        return obj.is_staff or obj.is_superuser

    def get_name(self, obj):
        full = f'{obj.first_name} {obj.last_name}'.strip()
        return full or obj.username
