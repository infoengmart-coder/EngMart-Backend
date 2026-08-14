from rest_framework import generics, status
from rest_framework.response import Response
from django.db.models import Count, Q

from apps.common.cache import CachedListMixin, CachedRetrieveMixin, InvalidatesCatalogMixin
from apps.common.permissions import IsAdminOrReadOnly
from .models import Category
from .serializers import (
    CategoryListSerializer,
    CategoryDetailSerializer,
    CategoryWriteSerializer,
)


def _wants_all(request):
    """Admin flag: ?all=true returns every category (incl. inactive & children)."""
    v = request.query_params.get('all')
    if not v or v.lower() not in ['1', 'true', 'yes']:
        return False
    # Staff-only: this branch exposes inactive rows that the storefront hides.
    user = request.user
    return bool(user and user.is_authenticated and user.is_staff)


class CategoryListView(CachedListMixin, InvalidatesCatalogMixin, generics.ListCreateAPIView):
    """
    GET /api/categories/ — Top-level categories with children (public).
    GET /api/categories/?all=true — Flat list of ALL categories (admin).
    POST /api/categories/ — Create a category (admin only).
    """
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None  # Return all categories (small list)

    def get_serializer_class(self):
        if self.request.method == 'POST' or _wants_all(self.request):
            return CategoryWriteSerializer
        return CategoryListSerializer

    def get_queryset(self):
        if _wants_all(self.request):
            # Annotate the count in one query — the recursive product_count
            # property would otherwise fire a COUNT per category (N+1).
            return (
                Category.objects.all()
                .select_related('parent')
                .annotate(num_products=Count('products', filter=Q(products__is_active=True)))
                .order_by('order', 'name')
            )
        return Category.objects.filter(
            is_active=True,
            parent__isnull=True,
        ).annotate(
            num_products=Count('products', filter=Q(products__is_active=True))
        ).prefetch_related('children')


class CategoryDetailView(CachedRetrieveMixin, InvalidatesCatalogMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/categories/{slug}/ — Category detail (public).
    PATCH/PUT /api/categories/{slug}/ — Update category (admin only).
    DELETE /api/categories/{slug}/ — Delete category (admin only, blocked if it has products).
    """
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return CategoryWriteSerializer
        return CategoryDetailSerializer

    def get_queryset(self):
        qs = Category.objects.all().prefetch_related('children')
        # Public reads only see active categories; admin writes can target any.
        if self.request.method == 'GET':
            qs = qs.filter(is_active=True)
        return qs

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        # Product.category is on_delete=CASCADE, so refuse to delete a category
        # that still has products — deleting it would wipe those products.
        product_count = category.products.count()
        if product_count:
            return Response(
                {'detail': (
                    f'Cannot delete "{category.name}" — it still has {product_count} '
                    f'product(s). Reassign or remove those products first.'
                )},
                status=status.HTTP_409_CONFLICT,
            )
        child_count = category.children.count()
        if child_count:
            return Response(
                {'detail': (
                    f'Cannot delete "{category.name}" — it has {child_count} '
                    f'subcategory(ies). Remove or reassign them first.'
                )},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


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
