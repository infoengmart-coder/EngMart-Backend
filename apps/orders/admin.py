from django.contrib import admin
from .models import Order, OrderItem, PromoCode


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['line_total']
    fields = [
        'product_name', 'variant_description', 'cat_no', 'brand_name',
        'quantity', 'unit_price', 'line_total', 'is_price_on_request',
    ]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        'order_number', 'customer_name', 'company_name', 'customer_phone',
        'total', 'payment_method', 'payment_status', 'status', 'created_at',
    ]
    list_filter = ['status', 'payment_status', 'payment_method', 'city', 'created_at']
    search_fields = ['order_number', 'customer_name', 'customer_email', 'customer_phone', 'company_name']
    readonly_fields = ['order_number', 'subtotal', 'discount_amount', 'total', 'created_at', 'updated_at']
    inlines = [OrderItemInline]
    fieldsets = [
        ('Order Info', {
            'fields': ['order_number', 'status', 'created_at', 'updated_at'],
        }),
        ('Customer', {
            'fields': ['customer_name', 'company_name', 'customer_email', 'customer_phone'],
        }),
        ('Shipping', {
            'fields': ['shipping_address', 'city', 'notes'],
        }),
        ('Payment', {
            'fields': ['payment_method', 'payment_status'],
        }),
        ('Pricing', {
            'fields': ['subtotal', 'promo_code_text', 'discount_amount', 'total'],
        }),
    ]


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = [
        'code', 'discount_type', 'discount_value', 'is_active',
        'times_used', 'max_uses', 'valid_until',
    ]
    list_filter = ['is_active', 'discount_type']
    search_fields = ['code', 'description']
    readonly_fields = ['times_used', 'created_at']
