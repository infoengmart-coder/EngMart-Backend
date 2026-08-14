from rest_framework import serializers
from .models import Banner


class BannerSerializer(serializers.ModelSerializer):
    """Banner payload shared by the public storefront and the admin dashboard."""
    image_src = serializers.SerializerMethodField()

    class Meta:
        model = Banner
        fields = [
            'id', 'type', 'title', 'subtitle', 'badge',
            'cta_text', 'cta_link', 'cta_text_2', 'cta_link_2',
            'image', 'image_url', 'image_src', 'video_url', 'highlights',
            'accent_color', 'text_color', 'bg_color',
            'is_active', 'order', 'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_image_src(self, obj):
        """Absolute URL for uploaded files, raw URL for external images."""
        if obj.image:
            request = self.context.get('request')
            url = obj.image.url
            return request.build_absolute_uri(url) if request else url
        return obj.image_url or ''
