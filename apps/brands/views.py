from rest_framework import generics
from .models import Brand
from .serializers import BrandListSerializer, BrandDetailSerializer


class BrandListView(generics.ListAPIView):
    """
    GET /api/brands/
    Returns all active brands with product counts.
    """
    serializer_class = BrandListSerializer

    def get_queryset(self):
        return Brand.objects.filter(is_active=True)


class BrandDetailView(generics.RetrieveAPIView):
    """
    GET /api/brands/{slug}/
    Returns full brand detail with categories.
    """
    serializer_class = BrandDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Brand.objects.filter(is_active=True)


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
