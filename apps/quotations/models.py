import random
from decimal import Decimal

from django.db import models
from django.utils import timezone


class Quotation(models.Model):
    """
    A request for quotation (RFQ) raised from the storefront.

    Kept separate from ``Inquiry`` on purpose: an RFQ carries line items,
    quantities and quoted prices, and uses its own status vocabulary. Folding
    it into Inquiry would break the contact-form inbox and lose the line items.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('quoted', 'Quoted'),
        ('converted', 'Converted'),
        ('expired', 'Expired'),
    ]
    SOURCE_CHOICES = [
        ('product', 'Product Page'),
        ('cart', 'Cart RFQ'),
        ('whatsapp', 'WhatsApp'),
        ('contact', 'Contact Form'),
    ]

    quote_number = models.CharField(max_length=20, unique=True, db_index=True, blank=True)

    # Requester
    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200, blank=True, default='')
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True, default='')

    notes = models.TextField(
        blank=True, default='',
        help_text="The customer's own message with the request",
    )
    admin_notes = models.TextField(
        blank=True, default='',
        help_text='Internal notes — never exposed to the customer',
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True,
    )
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default='product', blank=True,
    )

    quoted_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    valid_until = models.DateTimeField(null=True, blank=True)
    quoted_at = models.DateTimeField(null=True, blank=True)

    converted_order = models.ForeignKey(
        'orders.Order',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='quotations',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Quotations'

    def __str__(self):
        return f'{self.quote_number} — {self.name}'

    def save(self, *args, **kwargs):
        if not self.quote_number:
            self.quote_number = self._generate_quote_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_quote_number():
        """RFQ-YYYYMMDD-XXXX, retrying until unique."""
        stamp = timezone.now().strftime('%Y%m%d')
        for _ in range(20):
            candidate = f'RFQ-{stamp}-{random.randint(1000, 9999)}'
            if not Quotation.objects.filter(quote_number=candidate).exists():
                return candidate
        # Extremely unlikely fallback
        return f'RFQ-{stamp}-{timezone.now().strftime("%H%M%S")}'

    def recalculate_total(self, save=True):
        """
        Sum the line totals into ``quoted_total``.

        Aggregates in the database rather than iterating ``self.items``: when the
        instance was loaded with prefetch_related, that cache still holds the
        pre-update rows and the total would come out as 0.
        """
        total = QuotationItem.objects.filter(quotation=self).aggregate(
            total=models.Sum('line_total'),
        )['total'] or Decimal('0')
        self.quoted_total = total
        if save:
            self.save(update_fields=['quoted_total', 'updated_at'])
        return total


class QuotationItem(models.Model):
    """
    One line on a quotation.

    Product details are denormalised (same pattern as OrderItem) so the quote
    still reads correctly if the catalog entry is later renamed or removed.
    """
    quotation = models.ForeignKey(
        Quotation, on_delete=models.CASCADE, related_name='items',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='quotation_items',
    )

    product_name = models.CharField(max_length=300)
    variant_description = models.CharField(max_length=300, blank=True, default='')
    cat_no = models.CharField(max_length=100, blank=True, default='')
    brand_name = models.CharField(max_length=200, blank=True, default='')

    quantity = models.PositiveIntegerField(default=1)
    quoted_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Price the sales team quotes for this line (blank = not yet quoted)',
    )
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.CharField(max_length=300, blank=True, default='')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product_name} x{self.quantity}'

    def save(self, *args, **kwargs):
        # Keep the line total consistent with price x quantity.
        if self.quoted_price is not None:
            self.line_total = self.quoted_price * self.quantity
        else:
            self.line_total = Decimal('0')
        super().save(*args, **kwargs)
