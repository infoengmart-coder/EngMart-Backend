from rest_framework import serializers
from .models import Brand


class BrandWriteSerializer(serializers.ModelSerializer):
    """Create/update brands from the admin dashboard (supports logo upload)."""
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'logo', 'origin_country', 'supplier_name',
            'supplier_contact', 'description', 'color', 'website',
            'order', 'is_active', 'product_count', 'created_at',
        ]
        read_only_fields = ['created_at']
        extra_kwargs = {
            'slug': {'required': False},
        }

    def get_product_count(self, obj):
        # Prefer the annotated count from the queryset (single query).
        annotated = getattr(obj, 'num_products', None)
        return annotated if annotated is not None else obj.product_count


class BrandMinimalSerializer(serializers.ModelSerializer):
    """Minimal brand info for embedding in category/product responses."""
    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'logo', 'color']


class BrandListSerializer(serializers.ModelSerializer):
    """Brand card data for brand listing page."""
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'logo', 'origin_country',
            'supplier_name', 'color', 'product_count',
        ]

    def get_product_count(self, obj):
        # NOTE: do not write getattr(obj, 'num_products', obj.product_count) —
        # Python evaluates the default eagerly, so the fallback COUNT would run
        # for every row even when the annotation is present.
        annotated = getattr(obj, 'num_products', None)
        return annotated if annotated is not None else obj.product_count


class BrandDetailSerializer(serializers.ModelSerializer):
    """Full brand detail with all fields."""
    product_count = serializers.SerializerMethodField()
    categories = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'logo', 'origin_country',
            'supplier_name', 'supplier_contact', 'description',
            'color', 'website', 'product_count', 'categories',
        ]

    def get_product_count(self, obj):
        # NOTE: do not write getattr(obj, 'num_products', obj.product_count) —
        # Python evaluates the default eagerly, so the fallback COUNT would run
        # for every row even when the annotation is present.
        annotated = getattr(obj, 'num_products', None)
        return annotated if annotated is not None else obj.product_count

    def get_categories(self, obj):
        """Return distinct categories that have products from this brand."""
        from apps.categories.serializers import CategoryChildSerializer
        from apps.categories.models import Category
        category_ids = obj.products.filter(
            is_active=True
        ).values_list('category_id', flat=True).distinct()
        categories = Category.objects.filter(id__in=category_ids, is_active=True)
        return CategoryChildSerializer(categories, many=True).data
