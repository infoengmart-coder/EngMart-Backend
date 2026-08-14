from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import Count, Q

from apps.common.cache import CachedListMixin, CachedRetrieveMixin, InvalidatesCatalogMixin
from apps.common.permissions import IsAdminOrReadOnly
from .models import Brand
from .serializers import (
    BrandListSerializer,
    BrandDetailSerializer,
    BrandWriteSerializer,
)


def _wants_all(request):
    """Admin flag: ?all=true returns every brand, including inactive / empty ones."""
    v = request.query_params.get('all')
    if not v or v.lower() not in ['1', 'true', 'yes']:
        return False
    # Staff-only: this branch exposes inactive rows that the storefront hides.
    user = request.user
    return bool(user and user.is_authenticated and user.is_staff)


class BrandListView(CachedListMixin, InvalidatesCatalogMixin, generics.ListCreateAPIView):
    """
    GET /api/brands/ — Active brands that have products, most products first (public).
    GET /api/brands/?all=true — Flat list of ALL brands (admin).
    POST /api/brands/ — Create a brand (admin only).
    """
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None  # Return all brands (small list)

    def get_serializer_class(self):
        if self.request.method == 'POST' or _wants_all(self.request):
            return BrandWriteSerializer
        return BrandListSerializer

    def get_queryset(self):
        if _wants_all(self.request):
            return (
                Brand.objects.all()
                .annotate(num_products=Count('products', filter=Q(products__is_active=True)))
                .order_by('order', 'name')
            )
        return Brand.objects.filter(is_active=True).annotate(
            num_products=Count('products', filter=Q(products__is_active=True))
        ).filter(num_products__gt=0).order_by('-num_products', 'name')


class BrandDetailView(CachedRetrieveMixin, InvalidatesCatalogMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/brands/{slug}/ — Brand detail with categories (public).
    PATCH/PUT /api/brands/{slug}/ — Update brand (admin only).
    DELETE /api/brands/{slug}/ — Delete brand (admin only, blocked if it has products).
    """
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return BrandWriteSerializer
        return BrandDetailSerializer

    def get_queryset(self):
        qs = Brand.objects.all()
        # Public reads only see active brands; admin writes can target any.
        if self.request.method == 'GET':
            qs = qs.filter(is_active=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        brand = self.get_object()
        # Product.brand is on_delete=CASCADE, so refuse to delete a brand that
        # still has products — deleting it would wipe those products.
        product_count = brand.products.count()
        if product_count:
            return Response(
                {'detail': (
                    f'Cannot delete "{brand.name}" — it still has {product_count} '
                    f'product(s). Reassign or remove those products first.'
                )},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class BrandProductsView(generics.ListAPIView):
    """
    GET /api/brands/{slug}/products/
    Returns all products for a brand, with optional category filter.
    """
    def get_serializer_class(self):
        from apps.products.serializers import ProductListSerializer
        return ProductListSerializer

    def get_queryset(self):
        from apps.products.models import Product
        slug = self.kwargs['slug']
        queryset = Product.objects.filter(
            brand__slug=slug,
            is_active=True,
        ).select_related('brand', 'category').prefetch_related('variants')

        # Optional category filter
        category = self.request.query_params.get('category')
        if category:
            queryset = queryset.filter(category__slug=category)

        # Optional search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset
