from django.contrib import admin
from .models import Brand


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'origin_country', 'supplier_name', 'order', 'is_active', 'product_count']
    list_filter = ['is_active', 'origin_country']
    list_editable = ['order', 'is_active']
    search_fields = ['name', 'supplier_name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['order', 'name']
    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'logo', 'color', 'is_active', 'order'),
        }),
        ('Origin & Supplier', {
            'fields': ('origin_country', 'supplier_name', 'supplier_contact', 'website'),
        }),
        ('Description', {
            'fields': ('description',),
        }),
    )
