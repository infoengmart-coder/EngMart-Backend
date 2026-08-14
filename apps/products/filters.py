import django_filters
from django.db.models import Q

from .models import Product


class ProductFilter(django_filters.FilterSet):
    """
    Filtering for the product listing.

    Usage:
      /api/products/?brand=abb&category=mcb
      /api/products/?min_price=1000&max_price=50000
      /api/products/?spec=32A
      /api/products/?priced_only=true      (hide "Price on Request" items)

    Price and spec live on ProductVariant, so those filters span a reverse
    relation and must de-duplicate — a product with three matching variants
    would otherwise appear three times.
    """
    brand = django_filters.CharFilter(field_name='brand__slug')
    category = django_filters.CharFilter(method='filter_category')
    is_featured = django_filters.BooleanFilter(field_name='is_featured')
    series = django_filters.CharFilter(field_name='series', lookup_expr='icontains')

    # ── Price range (contracted) ──
    min_price = django_filters.NumberFilter(method='filter_min_price')
    max_price = django_filters.NumberFilter(method='filter_max_price')

    # ── Specification (contracted) ──
    spec = django_filters.CharFilter(method='filter_spec')

    # Hide "Price on Request" items when the buyer wants priced stock only.
    priced_only = django_filters.BooleanFilter(method='filter_priced_only')

    class Meta:
        model = Product
        fields = [
            'brand', 'category', 'is_featured', 'series',
            'min_price', 'max_price', 'spec', 'priced_only',
        ]

    def filter_category(self, queryset, name, value):
        """Match the category itself or any of its subcategories."""
        return queryset.filter(
            Q(category__slug=value) | Q(category__parent__slug=value)
        ).distinct()

    def filter_min_price(self, queryset, name, value):
        return queryset.filter(
            variants__is_active=True,
            variants__price_on_request=False,
            variants__price__gte=value,
        ).distinct()

    def filter_max_price(self, queryset, name, value):
        return queryset.filter(
            variants__is_active=True,
            variants__price_on_request=False,
            variants__price__lte=value,
        ).distinct()

    def filter_spec(self, queryset, name, value):
        """
        Match a specification such as "32A", "3 Pole" or "IP67".

        ProductVariant.specs is a JSONField, so this matches its serialised
        text. The variant description and catalogue number are included too,
        because much of the imported catalogue carries the rating there rather
        than in a structured spec field.
        """
        return queryset.filter(
            Q(variants__specs__icontains=value)
            | Q(variants__description__icontains=value)
            | Q(variants__cat_no__icontains=value)
        ).distinct()

    def filter_priced_only(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            variants__is_active=True,
            variants__price_on_request=False,
            variants__price__isnull=False,
        ).distinct()
