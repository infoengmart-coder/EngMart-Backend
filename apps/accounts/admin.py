from django.contrib import admin
from .models import SavedAddress, WishlistItem


@admin.register(SavedAddress)
class SavedAddressAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'city', 'phone', 'is_default']
    list_filter = ['is_default', 'city']
    search_fields = ['name', 'phone', 'address_line1', 'user__username']


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'created_at']
    search_fields = ['user__username', 'product__name']
