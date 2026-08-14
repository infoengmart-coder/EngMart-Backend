from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.products.models import Product, ProductVariant


class PromoCode(models.Model):
    """Promotional / wholesale discount codes."""
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount (PKR)'),
    ]

    code = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default='percentage',
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Percentage (e.g. 20 = 20%) or fixed PKR amount',
    )
    min_order_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Minimum cart total required to use this code',
    )
    max_discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Cap on discount (for percentage codes). Leave blank for no cap.',
    )
    max_uses = models.PositiveIntegerField(
        default=0,
        help_text='0 = unlimited uses',
    )
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.code} ({self.get_discount_type_display()}: {self.discount_value})'

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.max_uses > 0 and self.times_used >= self.max_uses:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if now < self.valid_from:
            return False
        return True

    def calculate_discount(self, subtotal):
        """Return the discount amount for a given subtotal."""
        if not self.is_valid:
            return 0
        if subtotal < self.min_order_amount:
            return 0
        if self.discount_type == 'percentage':
            discount = subtotal * (self.discount_value / 100)
            if self.max_discount_amount:
                discount = min(discount, self.max_discount_amount)
        else:
            discount = min(self.discount_value, subtotal)
        return round(discount, 2)


class Order(models.Model):
    """Customer order / quote request."""
    # The admin UI walks an order through this exact sequence. 'processing' is
    # kept as a legacy alias for older rows; new orders use 'packaging'.
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('packaging', 'Packaging'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('return_requested', 'Return Requested'),
    ]
    PAYMENT_STATUS_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('refunded', 'Refunded'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('cod', 'Cash on Delivery'),
        ('bank', 'Bank Transfer'),
        ('whatsapp', 'WhatsApp Order'),
    ]

    # Auto-generated order number
    order_number = models.CharField(max_length=20, unique=True, db_index=True)

    # Links an order to the account that placed it. Nullable because guest
    # checkout is supported — those orders are matched back to a customer by
    # email when they later sign in.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='orders',
        db_index=True,
    )

    # Customer info
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=50)
    company_name = models.CharField(max_length=200, blank=True)
    shipping_address = models.TextField()
    city = models.CharField(max_length=100, default='Karachi')
    notes = models.TextField(blank=True, help_text='Customer notes or special instructions')

    # Payment
    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cod',
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='unpaid',
    )

    # Pricing
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Promo
    promo_code = models.ForeignKey(
        PromoCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
    )
    promo_code_text = models.CharField(max_length=50, blank=True)

    # Proof of bank transfer uploaded by the customer
    payment_slip = models.FileField(
        upload_to='payment_slips/%Y/%m/',
        blank=True,
        help_text='Screenshot or photo of the bank transfer receipt',
    )
    payment_slip_uploaded_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(
        max_length=100,
        blank=True,
        help_text='Transaction / reference number quoted by the customer',
    )

    # Status & timestamps
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order {self.order_number} — {self.customer_name}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            # Generate: EM-YYYYMMDD-XXXX
            from django.utils.crypto import get_random_string
            date_part = timezone.now().strftime('%Y%m%d')
            random_part = get_random_string(4, allowed_chars='0123456789').upper()
            self.order_number = f'EM-{date_part}-{random_part}'
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    """Individual line item within an order."""
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='items',
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        related_name='order_items',
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_items',
    )
    # Snapshot fields (preserved even if product is deleted)
    product_name = models.CharField(max_length=300)
    variant_description = models.CharField(max_length=300, blank=True)
    cat_no = models.CharField(max_length=100, blank=True)
    brand_name = models.CharField(max_length=200, blank=True)

    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text='Price per unit at time of order',
    )
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_price_on_request = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product_name} x{self.quantity}'

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        super().save(*args, **kwargs)
