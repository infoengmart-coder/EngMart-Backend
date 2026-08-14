import re

from rest_framework import generics, filters, status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from apps.common.cache import CachedListMixin, CachedRetrieveMixin, InvalidatesCatalogMixin
from apps.common.permissions import IsAdminOrReadOnly, IsAdminUser
from apps.notifications.service import notify_all_customers
from .models import Product, ProductImage
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, ProductAdminSerializer,
    ProductSlugSerializer, ProductImageSerializer,
)
from .filters import ProductFilter


class ProductListView(CachedListMixin, InvalidatesCatalogMixin, generics.ListCreateAPIView):
    """
    GET /api/products/ — List products (public)
    POST /api/products/ — Create new product (admin only)
    """
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = ProductFilter
    # Covers what the search box promises: product name, model/catalogue number,
    # brand and category. Catalogue numbers live on the variant, so searching
    # "NXB-63" previously returned nothing. DRF adds .distinct() automatically
    # for these multi-valued relations.
    search_fields = [
        'name', 'series', 'short_description',
        'brand__name', 'category__name',
        'variants__cat_no', 'variants__description',
    ]
    ordering_fields = ['name', 'brand__name', 'created_at']
    ordering = ['brand__name', 'name']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProductAdminSerializer
        return ProductListSerializer

    def perform_create(self, serializer):
        """Announce genuinely new stock to customers — drafts stay quiet."""
        product = serializer.save()
        if getattr(product, 'is_active', True):
            notify_all_customers(
                'new_product',
                f'New arrival: {product.name}'[:200],
                f'{product.brand.name if product.brand_id else ""} — now available to order'.strip(' —'),
                f'/products/{product.slug}',
            )

    def get_queryset(self):
        qs = Product.objects.all()
        # ?all=true reveals inactive/draft products, so it is staff-only.
        show_all = self.request.query_params.get('all') or self.request.query_params.get('show_all')
        user = self.request.user
        is_staff = bool(user and user.is_authenticated and user.is_staff)
        if not (is_staff and show_all and show_all.lower() in ['1', 'true', 'yes']):
            qs = qs.filter(is_active=True)
        return qs.select_related('brand', 'category').prefetch_related('variants')

    def filter_queryset(self, queryset):
        """
        Fall back to a separator-tolerant search when the literal one finds
        nothing.

        Customers type catalogue numbers the way they remember them, not the
        way the price list punctuated them: "T-Max" and "Tmax" both mean
        "T MAX", and "NXB63" means "NXB-63". DRF's SearchFilter is a literal
        substring match, so all of those returned zero while the products
        plainly existed — the single most embarrassing thing that can happen
        when a customer searches for a product they know you stock.

        Normal searches are untouched: this only runs when the standard filter
        returned no rows, so the fast path keeps its existing behaviour and
        ranking.
        """
        result = super().filter_queryset(queryset)

        term = (self.request.query_params.get('search') or '').strip()
        if len(term) < 3 or result.exists():
            return result

        core = re.sub(r'[^0-9a-zA-Z]+', '', term)
        if len(core) < 3:
            return result

        # Optional separators between every character, so one regex matches
        # "TMAX", "T MAX" and "T-MAX" alike.
        pattern = r'[^0-9a-zA-Z]*'.join(re.escape(ch) for ch in core)
        return queryset.filter(
            Q(name__iregex=pattern)
            | Q(series__iregex=pattern)
            | Q(variants__cat_no__iregex=pattern)
            | Q(variants__description__iregex=pattern)
            | Q(brand__name__iregex=pattern)
        ).distinct()


class ProductDetailView(CachedRetrieveMixin, InvalidatesCatalogMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/products/{slug}/ — Retrieve product detail (public)
    PUT/PATCH /api/products/{slug}/ — Update product (admin only)
    DELETE /api/products/{slug}/ — Delete product (admin only)
    """
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return ProductAdminSerializer
        return ProductDetailSerializer

    def get_queryset(self):
        qs = Product.objects.all()
        if self.request.method == 'GET':
            show_all = self.request.query_params.get('all')
            user = self.request.user
            is_staff = bool(user and user.is_authenticated and user.is_staff)
            if not (is_staff and show_all and show_all.lower() in ['1', 'true', 'yes']):
                qs = qs.filter(is_active=True)
        return qs.select_related('brand', 'category').prefetch_related('variants', 'images')


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


class ProductMainImageView(APIView):
    """
    POST   /api/products/{slug}/image/ — Upload/replace the main product image.
    DELETE /api/products/{slug}/image/ — Clear the main product image.

    Files are handled here rather than on the product body endpoint: DRF's
    multipart parsing cannot round-trip the nested `variants` list, so mixing
    them would silently drop variant edits.
    """
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        upload = request.FILES.get('image')
        if not upload:
            return Response(
                {'detail': 'No image file was provided (expected form field "image").'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        product.image = upload
        product.save(update_fields=['image', 'updated_at'])
        return Response(ProductDetailSerializer(product, context={'request': request}).data)

    def delete(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        product.image.delete(save=False)
        product.image = ''
        product.save(update_fields=['image', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductGalleryView(APIView):
    """
    GET  /api/products/{slug}/images/ — List gallery images.
    POST /api/products/{slug}/images/ — Add a gallery image (multipart).
    """
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        return Response(
            ProductImageSerializer(product.images.all(), many=True, context={'request': request}).data
        )

    def post(self, request, slug):
        product = get_object_or_404(Product, slug=slug)
        upload = request.FILES.get('image')
        if not upload:
            return Response(
                {'detail': 'No image file was provided (expected form field "image").'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image = ProductImage.objects.create(
            product=product,
            image=upload,
            alt_text=request.data.get('alt_text', '') or product.name,
            is_primary=str(request.data.get('is_primary', '')).lower() in ['1', 'true', 'yes'],
            order=int(request.data.get('order') or 0),
        )
        return Response(
            ProductImageSerializer(image, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProductImageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/products/images/{id}/ — Manage one gallery image."""
    permission_classes = [IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = ProductImageSerializer
    queryset = ProductImage.objects.all()


class ProductFilterMetaView(APIView):
    """
    GET /api/products/filter-meta/

    Bounds and options the storefront needs to render filter controls: the real
    min/max variant price, and the most common specification values so the UI
    can offer them as suggestions instead of a blind free-text box.
    """
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request):
        from django.core.cache import cache
        from django.db.models import Min, Max
        from apps.products.models import ProductVariant

        cache_key = 'catalog:filter-meta'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        # price__gt=0 — a handful of rows carry 0.00 as a placeholder, which
        # would pin the slider's lower bound to zero and make it useless.
        bounds = ProductVariant.objects.filter(
            is_active=True, price_on_request=False, price__isnull=False,
            price__gt=0, product__is_active=True,
        ).aggregate(min_price=Min('price'), max_price=Max('price'))

        data = {
            'min_price': float(bounds['min_price'] or 0),
            'max_price': float(bounds['max_price'] or 0),
            # Common rating suffixes buyers actually search for in this catalog.
            'spec_suggestions': [
                '6A', '10A', '16A', '20A', '25A', '32A', '40A', '63A',
                '100A', '125A', '160A', '250A', '400A', '630A',
                '1 Pole', '2 Pole', '3 Pole', '4 Pole',
                'IP44', 'IP67',
            ],
        }
        cache.set(cache_key, data, 3600)
        return Response(data)


class ProductSlugListView(CachedListMixin, generics.ListAPIView):
    """
    GET /api/products/slugs/
    Lightweight, unpaginated list of every active product slug + last-modified
    timestamp. Exists so the Next.js sitemap can be built in a single request
    instead of paging through the full catalog.
    """
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = None
    serializer_class = ProductSlugSerializer

    def get_queryset(self):
        return Product.objects.filter(is_active=True).only(
            'slug', 'updated_at',
        ).order_by('slug')


class FeaturedProductsView(CachedListMixin, generics.ListAPIView):
    """
    GET /api/products/featured/
    Returns featured products for the homepage.

    If the admin has curated featured products they are returned. Otherwise the
    view self-heals by returning the newest active products that have an image,
    so the homepage is never empty before curation happens.
    """
    serializer_class = ProductListSerializer
    pagination_class = None  # No pagination for featured products

    def get_queryset(self):
        base = (
            Product.objects.filter(is_active=True)
            .select_related('brand', 'category')
            .prefetch_related('variants')
        )
        featured = base.filter(is_featured=True)
        if featured.exists():
            return featured[:12]
        # Fallback: newest products that have a real image
        return (
            base.exclude(image='')
            .exclude(image__isnull=True)
            .order_by('-created_at')[:12]
        )


class CatalogStatsView(APIView):
    """
    GET /api/products/stats/ — public headline numbers for the storefront.

    The homepage used to hardcode "2,500+ Products / 8 Global Brands", which
    drifted badly out of date as the catalog grew (it is 4,788 and 69 today).
    Serving them from here keeps the marketing copy honest by construction.

    Cached for an hour: these change when the client adds stock, not per request.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.core.cache import cache

        cached = cache.get('catalog:public_stats')
        if cached:
            return Response(cached)

        from apps.brands.models import Brand
        from apps.categories.models import Category

        data = {
            'products': Product.objects.filter(is_active=True).count(),
            'brands': Brand.objects.annotate(
                n=Count('products', filter=Q(products__is_active=True))
            ).filter(n__gt=0).count(),
            'categories': Category.objects.annotate(
                n=Count('products', filter=Q(products__is_active=True))
            ).filter(n__gt=0).count(),
        }
        cache.set('catalog:public_stats', data, 3600)
        return Response(data)
