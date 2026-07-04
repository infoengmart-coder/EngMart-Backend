import django_filters
from .models import Product


class ProductFilter(django_filters.FilterSet):
    """
    Filtering support for product listing.
    Usage: /api/products/?brand=abb&category=mcb&is_featured=true
    """
    brand = django_filters.CharFilter(field_name='brand__slug')
    category = django_filters.CharFilter(field_name='category__slug')
    is_featured = django_filters.BooleanFilter(field_name='is_featured')
    series = django_filters.CharFilter(field_name='series', lookup_expr='icontains')

    class Meta:
        model = Product
        fields = ['brand', 'category', 'is_featured', 'series']
