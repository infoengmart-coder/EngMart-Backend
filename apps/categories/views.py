from rest_framework import generics
from rest_framework.response import Response
from .models import Category
from .serializers import CategoryListSerializer, CategoryDetailSerializer


class CategoryListView(generics.ListAPIView):
    """
    GET /api/categories/
    Returns all top-level categories with their children.
    """
    serializer_class = CategoryListSerializer

    def get_queryset(self):
        return Category.objects.filter(
            is_active=True,
            parent__isnull=True,
        ).prefetch_related('children')


class CategoryDetailView(generics.RetrieveAPIView):
    """
    GET /api/categories/{slug}/
    Returns a single category with full detail.
    """
    serializer_class = CategoryDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Category.objects.filter(
            is_active=True,
        ).prefetch_related('children')


class CategoryProductsView(generics.ListAPIView):
    """
    GET /api/categories/{slug}/products/
    Returns all products in a category, with filtering support.
    """
    def get_serializer_class(self):
        from apps.products.serializers import ProductListSerializer
        return ProductListSerializer

    def get_queryset(self):
        from apps.products.models import Product
        slug = self.kwargs['slug']
        # Include products from subcategories too
        category = Category.objects.get(slug=slug, is_active=True)
        category_ids = [category.id]
        for child in category.children.filter(is_active=True):
            category_ids.append(child.id)

        queryset = Product.objects.filter(
            category_id__in=category_ids,
            is_active=True,
        ).select_related('brand', 'category').prefetch_related('variants')

        # Optional brand filter
        brand = self.request.query_params.get('brand')
        if brand:
            queryset = queryset.filter(brand__slug=brand)

        # Optional search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset
