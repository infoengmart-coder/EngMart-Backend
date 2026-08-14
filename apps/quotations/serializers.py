from rest_framework import serializers

from .models import Quotation, QuotationItem


class QuotationItemSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = QuotationItem
        fields = [
            'id', 'product', 'product_name', 'variant_description', 'cat_no',
            'brand_name', 'quantity', 'quoted_price', 'line_total', 'notes',
        ]
        read_only_fields = ['line_total']


class QuotationSerializer(serializers.ModelSerializer):
    """Full quotation payload for the admin dashboard."""
    items = QuotationItemSerializer(many=True, required=False)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = Quotation
        fields = [
            'id', 'quote_number', 'name', 'company', 'email', 'phone',
            'notes', 'admin_notes', 'status', 'source',
            'quoted_total', 'valid_until', 'quoted_at',
            'converted_order', 'items', 'item_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['quote_number', 'created_at', 'updated_at', 'quoted_total']

    def get_item_count(self, obj):
        return obj.items.count()

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        quotation = Quotation.objects.create(**validated_data)
        for item in items_data:
            item.pop('id', None)
            QuotationItem.objects.create(quotation=quotation, **item)
        quotation.recalculate_total()
        return quotation

    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            existing_ids = set(instance.items.values_list('id', flat=True))
            sent_ids = {i['id'] for i in items_data if i.get('id')}
            # Only drop lines the client explicitly removed.
            if sent_ids:
                instance.items.filter(id__in=existing_ids - sent_ids).delete()

            for item in items_data:
                item_id = item.pop('id', None)
                if item_id and item_id in existing_ids:
                    obj = QuotationItem.objects.get(id=item_id)
                    for attr, value in item.items():
                        setattr(obj, attr, value)
                    obj.save()
                else:
                    QuotationItem.objects.create(quotation=instance, **item)

        instance.recalculate_total()
        return instance


class QuotationCreateSerializer(serializers.ModelSerializer):
    """
    Public submission from the storefront.

    Deliberately narrow: a customer can never set status, quoted prices or
    internal notes — those belong to the sales team.
    """
    items = QuotationItemSerializer(many=True, required=False)

    class Meta:
        model = Quotation
        fields = [
            'name', 'company', 'email', 'phone', 'notes', 'source', 'items',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        quotation = Quotation.objects.create(**validated_data)
        for item in items_data:
            item.pop('id', None)
            # Customers request quantities, not prices.
            item.pop('quoted_price', None)
            QuotationItem.objects.create(quotation=quotation, **item)
        return quotation
