from rest_framework import generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from apps.common.cache import CachedListMixin, InvalidatesCatalogMixin
from apps.common.permissions import IsAdminOrReadOnly
from .models import Banner
from .serializers import BannerSerializer


def _wants_all(request):
    """Admin flag: ?all=true also returns inactive banners."""
    v = request.query_params.get('all')
    if not v or v.lower() not in ['1', 'true', 'yes']:
        return False
    # Staff-only: this branch exposes inactive rows that the storefront hides.
    user = request.user
    return bool(user and user.is_authenticated and user.is_staff)


class BannerListView(CachedListMixin, InvalidatesCatalogMixin, generics.ListCreateAPIView):
    """
    GET  /api/banners/            — Active banners for the storefront (public).
    GET  /api/banners/?all=true   — All banners incl. inactive (admin).
    GET  /api/banners/?type=sidebar — Filter by placement.
    POST /api/banners/            — Create a banner (admin only).
    """
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = BannerSerializer
    pagination_class = None  # Small list — return everything

    def get_queryset(self):
        qs = Banner.objects.all()
        if not _wants_all(self.request):
            qs = qs.filter(is_active=True)
        banner_type = self.request.query_params.get('type')
        if banner_type:
            qs = qs.filter(type=banner_type)
        return qs


class BannerDetailView(InvalidatesCatalogMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/PUT/DELETE /api/banners/<id>/ — Manage a banner (admin only for writes).
    """
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = BannerSerializer
    queryset = Banner.objects.all()
