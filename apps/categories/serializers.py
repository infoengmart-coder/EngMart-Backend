from rest_framework import serializers
from .models import Category


class CategoryWriteSerializer(serializers.ModelSerializer):
    """Create/update categories from the admin dashboard (supports image upload)."""
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), required=False, allow_null=True,
    )
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'parent', 'parent_name', 'short_name',
            'description', 'icon', 'image', 'color', 'order', 'is_active',
            'product_count', 'created_at',
        ]
        read_only_fields = ['created_at']
        extra_kwargs = {
            'slug': {'required': False},
        }

    def get_product_count(self, obj):
        # Prefer the annotated count from the queryset (single query) and only
        # fall back to the recursive property when the annotation is absent.
        annotated = getattr(obj, 'num_products', None)
        return annotated if annotated is not None else obj.product_count

    def validate_parent(self, value):
        # Prevent a category from being its own parent (self-reference loop).
        if value and self.instance and value.pk == self.instance.pk:
            raise serializers.ValidationError('A category cannot be its own parent.')
        return value


class CategoryChildSerializer(serializers.ModelSerializer):
    """Minimal serializer for subcategories (no recursion)."""
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'short_name', 'icon', 'color', 'product_count']

    def get_product_count(self, obj):
        return getattr(obj, 'num_products', 0)


class CategoryListSerializer(serializers.ModelSerializer):
    """Category with children and product count for listing pages."""
    product_count = serializers.SerializerMethodField()
    children = CategoryChildSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'short_name', 'description',
            'icon', 'image', 'color', 'order', 'product_count',
            'children',
        ]

    def get_product_count(self, obj):
        return getattr(obj, 'num_products', 0)


class CategoryDetailSerializer(serializers.ModelSerializer):
    """Full category detail with parent info and children."""
    product_count = serializers.SerializerMethodField()
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

    def get_product_count(self, obj):
        return getattr(obj, 'num_products', 0)

    def get_brands(self, obj):
        """Return distinct brands that have products in this category."""
        from apps.brands.serializers import BrandMinimalSerializer
        from apps.brands.models import Brand
        brand_ids = obj.products.filter(
            is_active=True
        ).values_list('brand_id', flat=True).distinct()
        brands = Brand.objects.filter(id__in=brand_ids, is_active=True)
        return BrandMinimalSerializer(brands, many=True).data
