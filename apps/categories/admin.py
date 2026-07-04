from django.contrib import admin
from .models import Category


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'parent', 'order', 'is_active', 'product_count']
    list_filter = ['is_active', 'parent']
    list_editable = ['order', 'is_active']
    search_fields = ['name', 'short_name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['order', 'name']
