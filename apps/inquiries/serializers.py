from rest_framework import serializers
from .models import Inquiry


class InquiryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new inquiries from the contact form."""

    class Meta:
        model = Inquiry
        fields = ['name', 'company', 'phone', 'email', 'message', 'product_interest']
