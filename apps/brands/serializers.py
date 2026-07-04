from rest_framework import serializers
from .models import Brand


class BrandMinimalSerializer(serializers.ModelSerializer):
    """Minimal brand info for embedding in category/product responses."""
    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'logo', 'color']


class BrandListSerializer(serializers.ModelSerializer):
    """Brand card data for brand listing page."""
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'logo', 'origin_country',
            'supplier_name', 'color', 'product_count',
        ]


class BrandDetailSerializer(serializers.ModelSerializer):
    """Full brand detail with all fields."""
    product_count = serializers.IntegerField(read_only=True)
    categories = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            'id', 'name', 'slug', 'logo', 'origin_country',
            'supplier_name', 'supplier_contact', 'description',
            'color', 'website', 'product_count', 'categories',
        ]

    def get_categories(self, obj):
        """Return distinct categories that have products from this brand."""
        from apps.categories.serializers import CategoryChildSerializer
        from apps.categories.models import Category
        category_ids = obj.products.filter(
            is_active=True
        ).values_list('category_id', flat=True).distinct()
        categories = Category.objects.filter(id__in=category_ids, is_active=True)
        return CategoryChildSerializer(categories, many=True).data
