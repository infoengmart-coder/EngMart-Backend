from rest_framework import serializers
from .models import Product, ProductVariant, ProductImage
from apps.brands.models import Brand
from apps.categories.models import Category
from apps.brands.serializers import BrandMinimalSerializer
from apps.categories.serializers import CategoryChildSerializer


class ProductVariantSerializer(serializers.ModelSerializer):
    """Variant data for product detail page variants table."""
    # Writable so admin updates can be matched to existing rows. With the
    # default read-only pk the update path saw no ids, treated every existing
    # variant as removed, and deleted them all on each save.
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProductVariant
        fields = [
            'id', 'cat_no', 'description', 'price',
            'price_on_request', 'specs', 'order', 'is_active',
        ]


class ProductAdminSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating products by admin."""
    brand_id = serializers.PrimaryKeyRelatedField(
        queryset=Brand.objects.all(), source='brand', write_only=True, required=False
    )
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False
    )
    brand = BrandMinimalSerializer(read_only=True)
    category = CategoryChildSerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'brand', 'brand_id', 'category', 'category_id',
            'series', 'short_description', 'full_description', 'image',
            'datasheet_url', 'is_active', 'is_featured',
            'meta_title', 'meta_description', 'variants',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            # Product.save() derives the slug from brand + name; requiring it
            # here made every create fail with "This field is required".
            'slug': {'required': False},
        }

    def create(self, validated_data):
        variants_data = validated_data.pop('variants', [])
        product = Product.objects.create(**validated_data)
        for var_data in variants_data:
            var_data.pop('id', None)  # ids are assigned by the DB
            ProductVariant.objects.create(product=product, **var_data)
        return product

    def update(self, instance, validated_data):
        variants_data = validated_data.pop('variants', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if variants_data is not None:
            existing_ids = set(instance.variants.values_list('id', flat=True))

            # Upsert only — never infer deletions from an incomplete payload.
            #
            # The admin edit form submits a SINGLE variant (the product's first
            # one) even when the product has many. Treating the payload as the
            # complete set would silently destroy every other variant on an
            # unrelated edit such as toggling "featured". Deletions must be an
            # explicit action, so they are not handled here.
            for var_data in variants_data:
                var_id = var_data.pop('id', None)
                if var_id and var_id in existing_ids:
                    ProductVariant.objects.filter(id=var_id).update(**var_data)
                else:
                    ProductVariant.objects.create(product=instance, **var_data)

        return instance


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
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    price_range = serializers.DictField(read_only=True)
    has_price_on_request = serializers.BooleanField(read_only=True)
    variant_count = serializers.SerializerMethodField()
    first_variant = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'brand', 'brand_name', 'category',
            'category_name', 'series', 'short_description', 'image',
            'is_featured', 'price_range', 'has_price_on_request',
            'variant_count', 'first_variant',
        ]

    def get_variant_count(self, obj):
        return len([v for v in obj.variants.all() if v.is_active])

    def get_first_variant(self, obj):
        active_variants = [v for v in obj.variants.all() if v.is_active]
        if active_variants:
            v = active_variants[0]
            return {
                # id lets the admin edit form update this variant in place
                # instead of appending a duplicate on every save.
                'id': v.id,
                'cat_no': v.cat_no,
                'description': v.description,
                'price': str(v.price) if v.price else None,
                'price_on_request': v.price_on_request,
                'specs': v.specs or {},
            }
        return None


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
        """
        Up to 4 related products from the same category, topped up from the
        same brand.

        ``prefetch_related('variants')`` matters here: ProductListSerializer
        reads price_range / variant_count / first_variant off each product, and
        without the prefetch every related product costs extra round-trips.
        """
        base = Product.objects.filter(is_active=True).select_related(
            'brand', 'category',
        ).prefetch_related('variants')

        related = list(base.filter(category=obj.category).exclude(id=obj.id)[:4])

        if len(related) < 4:
            more = base.filter(brand=obj.brand).exclude(
                id=obj.id,
            ).exclude(
                id__in=[p.id for p in related],
            )[:4 - len(related)]
            related = related + list(more)

        return ProductListSerializer(related, many=True).data


class ProductSlugSerializer(serializers.ModelSerializer):
    """Minimal payload for sitemap generation — slug + last modified only."""

    class Meta:
        model = Product
        fields = ['slug', 'updated_at']
