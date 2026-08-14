from rest_framework import serializers

from apps.products.serializers import ProductListSerializer
from .models import SavedAddress, WishlistItem


class SavedAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedAddress
        fields = [
            'id', 'name', 'company', 'phone',
            'address_line1', 'address_line2', 'city', 'province',
            'postal_code', 'country', 'is_default',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']


class WishlistItemSerializer(serializers.ModelSerializer):
    """Wishlist row with the full product card payload embedded."""
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ['id', 'product', 'created_at']
        read_only_fields = ['created_at']
