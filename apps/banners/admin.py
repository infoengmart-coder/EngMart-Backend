from django.contrib import admin
from .models import Banner


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ['title', 'type', 'badge', 'order', 'is_active']
    list_filter = ['type', 'is_active']
    list_editable = ['order', 'is_active']
    search_fields = ['title', 'subtitle', 'badge']
    ordering = ['type', 'order']
    fieldsets = (
        (None, {
            'fields': ('type', 'title', 'subtitle', 'badge', 'is_active', 'order'),
        }),
        ('Call to Action', {
            'fields': ('cta_text', 'cta_link', 'cta_text_2', 'cta_link_2'),
        }),
        ('Image / Video', {
            'fields': ('image', 'image_url', 'video_url'),
            'description': 'Upload a file, paste an external image URL, or set a background video for the hero.',
        }),
        ('Hero Highlights', {
            'classes': ('collapse',),
            'fields': ('highlights',),
            'description': 'Short pills under the hero text, as a JSON list.',
        }),
        ('Colors', {
            'fields': ('accent_color', 'text_color', 'bg_color'),
        }),
    )
