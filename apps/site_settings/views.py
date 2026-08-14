from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.common.permissions import IsAdminOrReadOnly
from .models import SiteSettings
from .serializers import SiteSettingsSerializer


class SiteSettingsView(generics.RetrieveUpdateAPIView):
    """
    GET   /api/settings/ — Store configuration (public; the storefront renders it).
    PATCH /api/settings/ — Update store configuration (admin only).

    Always operates on the singleton row, so no pk is needed in the URL.
    """
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = SiteSettingsSerializer

    def get_object(self):
        return SiteSettings.load()
