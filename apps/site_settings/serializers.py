from rest_framework import serializers
from .models import SiteSettings


class SiteSettingsSerializer(serializers.ModelSerializer):
    """Store configuration consumed by the storefront and edited by the admin."""
    whatsapp_digits = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        fields = '__all__'
        read_only_fields = ['id', 'updated_at']

    def get_whatsapp_digits(self, obj):
        """Pre-stripped number so the frontend never re-implements the regex."""
        return obj.whatsapp_digits
