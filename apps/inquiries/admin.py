from django.contrib import admin
from .models import Inquiry


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'product_interest', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    list_editable = ['status']
    search_fields = ['name', 'email', 'company', 'message', 'product_interest']
    readonly_fields = ['name', 'company', 'phone', 'email', 'message', 'product_interest', 'created_at']
    ordering = ['-created_at']
    list_per_page = 25
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Customer Info', {
            'fields': ('name', 'company', 'phone', 'email'),
        }),
        ('Inquiry', {
            'fields': ('message', 'product_interest', 'created_at'),
        }),
        ('Admin', {
            'fields': ('status', 'notes'),
        }),
    )

    def has_add_permission(self, request):
        """Inquiries are only created via the API, not admin."""
        return False
