from django.contrib import admin
from .models import Product, ProductVariant, ProductImage


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ['cat_no', 'description', 'price', 'price_on_request', 'specs', 'is_active', 'order']
    ordering = ['order', 'id']


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ['image', 'alt_text', 'is_primary', 'order']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'brand', 'category', 'series',
        'is_active', 'is_featured', 'variant_count', 'updated_at',
    ]
    list_filter = ['brand', 'category', 'is_active', 'is_featured']
    list_editable = ['is_active', 'is_featured']
    search_fields = ['name', 'series', 'short_description', 'variants__cat_no']
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ['brand', 'category']
    inlines = [ProductVariantInline, ProductImageInline]
    ordering = ['brand__name', 'name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'brand', 'category', 'series', 'is_active', 'is_featured'),
        }),
        ('Descriptions', {
            'fields': ('short_description', 'full_description'),
        }),
        ('Media', {
            'fields': ('image', 'datasheet_url'),
        }),
        ('SEO', {
            'classes': ('collapse',),
            'fields': ('meta_title', 'meta_description'),
        }),
        ('Timestamps', {
            'classes': ('collapse',),
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def variant_count(self, obj):
        return obj.variants.count()
    variant_count.short_description = 'Variants'


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    """Standalone variant admin for bulk editing."""
    list_display = ['product', 'cat_no', 'description', 'price', 'price_on_request', 'is_active']
    list_filter = ['product__brand', 'product__category', 'price_on_request', 'is_active']
    list_editable = ['price', 'price_on_request', 'is_active']
    search_fields = ['cat_no', 'description', 'product__name']
    autocomplete_fields = ['product']
    list_per_page = 50
