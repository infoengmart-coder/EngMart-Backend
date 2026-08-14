from decimal import Decimal

from django.db import transaction
from django.db.models import F
from rest_framework import serializers

from .models import Order, OrderItem, PromoCode


class OrderItemCreateSerializer(serializers.Serializer):
    """
    One cart line submitted at checkout.

    Only ``product_id``, ``variant_id`` and ``quantity`` are trusted. Prices and
    product names are looked up server-side from the catalog — see
    ``OrderCreateSerializer.create``. The remaining fields are still accepted so
    existing clients keep working, but their values are ignored.
    """
    product_id = serializers.IntegerField()
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=100000)

    # Accepted for backwards compatibility, never used.
    product_name = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')
    variant_description = serializers.CharField(max_length=300, required=False, allow_blank=True, default='')
    cat_no = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    brand_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    is_price_on_request = serializers.BooleanField(required=False, default=False)


class OrderCreateSerializer(serializers.Serializer):
    """Serializer for the full order creation payload from checkout."""
    # Customer info
    customer_name = serializers.CharField(max_length=200)
    customer_email = serializers.EmailField()
    customer_phone = serializers.CharField(max_length=50)
    company_name = serializers.CharField(max_length=200, required=False, allow_blank=True, default='')
    shipping_address = serializers.CharField()
    city = serializers.CharField(max_length=100, default='Karachi')
    notes = serializers.CharField(required=False, allow_blank=True, default='')

    # Payment
    payment_method = serializers.ChoiceField(
        choices=['cod', 'bank', 'whatsapp'],
        default='cod',
    )

    # Promo
    promo_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')

    # Cart items
    items = OrderItemCreateSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('At least one item is required.')
        return value

    def _resolve_lines(self, items_data):
        """
        Turn the submitted cart into priced lines using catalog data only.

        The client sends product/variant ids and quantities; everything that
        affects money — price, and the names that appear on the order and in
        emails — is read from the database here. Trusting the posted
        ``unit_price`` would let anyone order a PKR 240,000 breaker for 1 rupee.
        """
        from apps.products.models import Product, ProductVariant

        lines = []
        for item in items_data:
            try:
                product = Product.objects.select_related('brand').get(
                    id=item['product_id'], is_active=True,
                )
            except Product.DoesNotExist:
                raise serializers.ValidationError({
                    'items': f'Product {item["product_id"]} is unavailable.'
                })

            variant = None
            variant_id = item.get('variant_id')
            if variant_id:
                try:
                    variant = ProductVariant.objects.get(id=variant_id, product=product)
                except ProductVariant.DoesNotExist:
                    raise serializers.ValidationError({
                        'items': f'Variant {variant_id} does not belong to {product.name}.'
                    })
            else:
                variant = product.variants.filter(is_active=True).first()

            # Authoritative price straight from the catalog.
            if variant is not None:
                on_request = bool(variant.price_on_request or variant.price is None)
                unit_price = Decimal('0') if on_request else Decimal(str(variant.price))
            else:
                on_request = True
                unit_price = Decimal('0')

            lines.append({
                'product': product,
                'variant': variant,
                'product_name': product.name,
                'variant_description': (variant.description if variant else ''),
                'cat_no': (variant.cat_no if variant else ''),
                'brand_name': (product.brand.name if product.brand else ''),
                'quantity': item['quantity'],
                'unit_price': unit_price,
                'is_price_on_request': on_request,
            })
        return lines

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        promo_code_text = validated_data.pop('promo_code', '')

        # Price every line from the catalog, ignoring anything the client sent.
        lines = self._resolve_lines(items_data)

        subtotal = sum(
            (line['unit_price'] * line['quantity'] for line in lines),
            Decimal('0'),
        )

        # Apply promo code
        discount_amount = Decimal('0')
        promo_obj = None
        if promo_code_text:
            try:
                promo_obj = PromoCode.objects.get(code__iexact=promo_code_text)
            except PromoCode.DoesNotExist:
                promo_obj = None
            if promo_obj and promo_obj.is_valid:
                discount_amount = Decimal(str(promo_obj.calculate_discount(subtotal)))
                if discount_amount > 0:
                    # Only consume a use when the code actually discounted
                    # something — otherwise sub-minimum orders could burn
                    # through a code's usage limit. F() keeps it atomic under
                    # concurrent checkouts.
                    PromoCode.objects.filter(pk=promo_obj.pk).update(
                        times_used=F('times_used') + 1,
                    )
                else:
                    promo_obj = None  # not applied, do not attach to the order
            else:
                promo_obj = None

        total = subtotal - discount_amount

        # Create order
        order = Order.objects.create(
            customer_name=validated_data['customer_name'],
            customer_email=validated_data['customer_email'],
            customer_phone=validated_data['customer_phone'],
            company_name=validated_data.get('company_name', ''),
            shipping_address=validated_data['shipping_address'],
            city=validated_data.get('city', 'Karachi'),
            notes=validated_data.get('notes', ''),
            payment_method=validated_data.get('payment_method', 'cod'),
            subtotal=subtotal,
            discount_amount=discount_amount,
            total=total,
            promo_code=promo_obj,
            promo_code_text=promo_code_text,
        )

        # Create order items from the server-priced lines
        for line in lines:
            OrderItem.objects.create(
                order=order,
                product=line['product'],
                variant=line['variant'],
                product_name=line['product_name'],
                variant_description=line['variant_description'],
                cat_no=line['cat_no'],
                brand_name=line['brand_name'],
                quantity=line['quantity'],
                unit_price=line['unit_price'],
                is_price_on_request=line['is_price_on_request'],
            )

        return order


class OrderItemReadSerializer(serializers.ModelSerializer):
    # Live FK ids + slug so the storefront "Reorder" can rebuild a cart line
    # that passes server-side pricing. All null-safe: the FK is SET_NULL, so a
    # deleted product must not break serialization — the snapshot fields still
    # render, the line just can't be reordered.
    product_id = serializers.SerializerMethodField()
    variant_id = serializers.SerializerMethodField()
    product_slug = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()

    def get_product_id(self, obj):
        return obj.product_id

    def get_variant_id(self, obj):
        return obj.variant_id

    def get_product_slug(self, obj):
        return obj.product.slug if obj.product else None

    def get_product_image(self, obj):
        """Relative media path of the product's main image, if it still exists."""
        if obj.product and obj.product.image:
            return obj.product.image.url if hasattr(obj.product.image, 'url') else str(obj.product.image)
        return None

    class Meta:
        model = OrderItem
        fields = [
            'id', 'product_id', 'variant_id', 'product_slug', 'product_image',
            'product_name', 'variant_description', 'cat_no',
            'brand_name', 'quantity', 'unit_price', 'line_total',
            'is_price_on_request',
        ]


class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemReadSerializer(many=True, read_only=True)
    payment_slip_url = serializers.SerializerMethodField()

    def get_payment_slip_url(self, obj):
        """Absolute URL of the uploaded receipt, so admin can open it."""
        if not obj.payment_slip:
            return None
        request = self.context.get('request')
        url = obj.payment_slip.url
        return request.build_absolute_uri(url) if request else url

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 'customer_name', 'customer_email',
            'customer_phone', 'company_name', 'shipping_address', 'city',
            'notes', 'payment_method', 'payment_status', 'subtotal',
            'discount_amount', 'total', 'promo_code_text', 'status',
            'items', 'payment_slip_url', 'payment_slip_uploaded_at',
            'payment_reference', 'created_at', 'updated_at',
        ]


class PromoCodeValidateSerializer(serializers.Serializer):
    """Validate a promo code and return discount info."""
    code = serializers.CharField(max_length=50)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)


class PromoCodeSerializer(serializers.ModelSerializer):
    """Full CRUD serializer for promo codes."""
    class Meta:
        model = PromoCode
        fields = [
            'id', 'code', 'description', 'discount_type', 'discount_value',
            'min_order_amount', 'max_discount_amount', 'max_uses', 'times_used',
            'is_active', 'valid_from', 'valid_until', 'created_at',
        ]
        read_only_fields = ['id', 'times_used', 'created_at']
