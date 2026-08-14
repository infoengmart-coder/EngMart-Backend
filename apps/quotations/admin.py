from django.contrib import admin
from .models import Quotation, QuotationItem


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = ['line_total']


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['quote_number', 'name', 'company', 'status', 'quoted_total', 'created_at']
    list_filter = ['status', 'source', 'created_at']
    search_fields = ['quote_number', 'name', 'company', 'email', 'phone']
    readonly_fields = ['quote_number', 'quoted_total', 'created_at', 'updated_at']
    inlines = [QuotationItemInline]
    ordering = ['-created_at']
