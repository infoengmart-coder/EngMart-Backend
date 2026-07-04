from rest_framework import serializers
from .models import Product, ProductVariant, ProductImage
from apps.brands.serializers import BrandMinimalSerializer
from apps.categories.serializers import CategoryChildSerializer


class ProductVariantSerializer(serializers.ModelSerializer):
    """Variant data for product detail page variants table."""
    class Meta:
        model = ProductVariant
        fields = [
            'id', 'cat_no', 'description', 'price',
            'price_on_request', 'specs', 'order',
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    """Product image for gallery."""
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text', 'is_primary', 'order']


class ProductListSerializer(serializers.ModelSerializer):
    """
    Product card data for listing pages.
    Includes brand info, category, price range, and variant count.
    """
    brand = BrandMinimalSerializer(read_only=True)
    category = CategoryChildSerializer(read_only=True)
    price_range = serializers.DictField(read_only=True)
    has_price_on_request = serializers.BooleanField(read_only=True)
    variant_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'brand', 'category', 'series',
            'short_description', 'image', 'is_featured',
            'price_range', 'has_price_on_request', 'variant_count',
        ]

    def get_variant_count(self, obj):
        return obj.variants.filter(is_active=True).count()


class ProductDetailSerializer(serializers.ModelSerializer):
    """
    Full product detail with all variants, images, and SEO data.
    Used on /products/{slug}/ page.
    """
    brand = BrandMinimalSerializer(read_only=True)
    category = CategoryChildSerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    price_range = serializers.DictField(read_only=True)
    has_price_on_request = serializers.BooleanField(read_only=True)
    related_products = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'brand', 'category', 'series',
            'short_description', 'full_description', 'image',
            'datasheet_url', 'is_featured',
            'meta_title', 'meta_description',
            'price_range', 'has_price_on_request',
            'variants', 'images', 'related_products',
            'created_at', 'updated_at',
        ]

    def get_related_products(self, obj):
        """Up to 4 related products from same category or brand."""
        related = Product.objects.filter(
            is_active=True,
            category=obj.category,
        ).exclude(id=obj.id).select_related('brand', 'category')[:4]

        if related.count() < 4:
            more = Product.objects.filter(
                is_active=True,
                brand=obj.brand,
            ).exclude(
                id=obj.id,
            ).exclude(
                id__in=related.values_list('id', flat=True),
            ).select_related('brand', 'category')[:4 - related.count()]
            related = list(related) + list(more)

        return ProductListSerializer(related, many=True).data
