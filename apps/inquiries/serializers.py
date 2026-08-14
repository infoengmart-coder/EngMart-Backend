from rest_framework import serializers
from .models import Inquiry


class InquiryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new inquiries from the contact form."""

    class Meta:
        model = Inquiry
        fields = ['name', 'company', 'phone', 'email', 'message', 'product_interest']


class InquiryReadSerializer(serializers.ModelSerializer):
    """Serializer for viewing and updating inquiries in admin."""

    class Meta:
        model = Inquiry
        fields = [
            'id', 'name', 'company', 'phone', 'email', 'message',
            'product_interest', 'status', 'notes', 'admin_reply', 'replied_at',
            'created_at', 'updated_at',
        ]
