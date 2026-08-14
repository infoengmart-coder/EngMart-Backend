from django.contrib import admin
from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton admin — one row, no add/delete."""

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    fieldsets = (
        ('Identity', {'fields': ('name', 'tagline', 'description', 'url', 'logo')}),
        ('Contact', {'fields': ('phone', 'mobile', 'email', 'address', 'hours', 'hours_note', 'whatsapp', 'map_embed_url', 'map_link_url')}),
        ('Social', {'fields': ('facebook_url', 'instagram_url', 'linkedin_url', 'twitter_url', 'youtube_url')}),
        ('Payment Methods', {'fields': ('cod_enabled', 'bank_transfer_enabled', 'mobile_wallet_enabled', 'whatsapp_order_enabled')}),
        ('Bank Account', {'fields': ('bank_name', 'bank_account_title', 'bank_account_number', 'bank_iban', 'bank_branch', 'bank_swift', 'bank_transfer_note')}),
        ('Second Bank Account', {'classes': ('collapse',), 'fields': ('bank_name_2', 'bank_account_title_2', 'bank_account_number_2', 'bank_iban_2', 'bank_branch_2')}),
        ('Mobile Wallets', {'classes': ('collapse',), 'fields': ('jazzcash_number', 'jazzcash_title', 'easypaisa_number', 'easypaisa_title')}),
        ('Storefront Copy', {'fields': ('free_shipping_threshold', 'footer_payment_note', 'copyright_text')}),
    )
