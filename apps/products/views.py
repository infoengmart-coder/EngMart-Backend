from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from .models import Product
from .serializers import ProductListSerializer, ProductDetailSerializer
from .filters import ProductFilter


class ProductListView(generics.ListAPIView):
    """
    GET /api/products/
    Returns all active products with filtering and search.

    Query params:
        - brand: filter by brand slug
        - category: filter by category slug
        - search: search product name, series, descriptions
        - is_featured: filter featured products (true/false)
        - ordering: order by name, brand__name, created_at
    """
    serializer_class = ProductListSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    search_fields = ['name', 'series', 'short_description', 'brand__name']
    ordering_fields = ['name', 'brand__name', 'created_at']
    ordering = ['brand__name', 'name']

    def get_queryset(self):
        return Product.objects.filter(
            is_active=True,
        ).select_related('brand', 'category').prefetch_related('variants')


class ProductDetailView(generics.RetrieveAPIView):
    """
    GET /api/products/{slug}/
    Returns full product detail with variants, images, and related products.
    """
    serializer_class = ProductDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Product.objects.filter(
            is_active=True,
        ).select_related('brand', 'category').prefetch_related(
            'variants', 'images',
        )


class ProductSearchView(generics.ListAPIView):
    """
    GET /api/products/search/?q=query
    Full-text search across product names, series, descriptions, and brand names.
    """
    serializer_class = ProductListSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        if not query:
            return Product.objects.none()

        return Product.objects.filter(
            is_active=True,
        ).filter(
            Q(name__icontains=query) |
            Q(series__icontains=query) |
            Q(short_description__icontains=query) |
            Q(full_description__icontains=query) |
            Q(brand__name__icontains=query) |
            Q(category__name__icontains=query) |
            Q(variants__cat_no__icontains=query) |
            Q(variants__description__icontains=query)
        ).select_related('brand', 'category').prefetch_related('variants').distinct()


class FeaturedProductsView(generics.ListAPIView):
    """
    GET /api/products/featured/
    Returns featured products for the homepage.
    """
    serializer_class = ProductListSerializer
    pagination_class = None  # No pagination for featured products

    def get_queryset(self):
        return Product.objects.filter(
            is_active=True,
            is_featured=True,
        ).select_related('brand', 'category').prefetch_related('variants')[:12]
