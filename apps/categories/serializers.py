from rest_framework import serializers
from .models import Category


class CategoryChildSerializer(serializers.ModelSerializer):
    """Minimal serializer for subcategories (no recursion)."""
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'short_name', 'icon', 'color', 'product_count']


class CategoryListSerializer(serializers.ModelSerializer):
    """Category with children and product count for listing pages."""
    product_count = serializers.IntegerField(read_only=True)
    children = CategoryChildSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'short_name', 'description',
            'icon', 'image', 'color', 'order', 'product_count',
            'children',
        ]


class CategoryDetailSerializer(serializers.ModelSerializer):
    """Full category detail with parent info and children."""
    product_count = serializers.IntegerField(read_only=True)
    children = CategoryChildSerializer(many=True, read_only=True)
    parent = CategoryChildSerializer(read_only=True)
    brands = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'short_name', 'description',
            'icon', 'image', 'color', 'order', 'product_count',
            'parent', 'children', 'brands',
        ]

    def get_brands(self, obj):
        """Return distinct brands that have products in this category."""
        from apps.brands.serializers import BrandMinimalSerializer
        from apps.brands.models import Brand
        brand_ids = obj.products.filter(
            is_active=True
        ).values_list('brand_id', flat=True).distinct()
        brands = Brand.objects.filter(id__in=brand_ids, is_active=True)
        return BrandMinimalSerializer(brands, many=True).data
