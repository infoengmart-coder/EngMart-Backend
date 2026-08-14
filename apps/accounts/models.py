from django.conf import settings
from django.db import models


class SavedAddress(models.Model):
    """A delivery address the customer has saved for reuse at checkout."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='saved_addresses',
    )
    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200, blank=True, default='')
    phone = models.CharField(max_length=50)
    address_line1 = models.CharField(max_length=300)
    address_line2 = models.CharField(max_length=300, blank=True, default='')
    city = models.CharField(max_length=100, default='Karachi')
    province = models.CharField(max_length=100, blank=True, default='Sindh')
    postal_code = models.CharField(max_length=20, blank=True, default='')
    country = models.CharField(max_length=100, default='Pakistan')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-updated_at']
        verbose_name_plural = 'Saved addresses'

    def __str__(self):
        return f'{self.name} — {self.city}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Exactly one default per customer.
        if self.is_default:
            SavedAddress.objects.filter(user=self.user).exclude(pk=self.pk).update(is_default=False)


class WishlistItem(models.Model):
    """A product the customer saved for later."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='wishlist_items',
    )
    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='wishlisted_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        # Saving the same product twice is a no-op, not a duplicate row.
        constraints = [
            models.UniqueConstraint(fields=['user', 'product'], name='unique_wishlist_entry'),
        ]

    def __str__(self):
        return f'{self.user} ♥ {self.product}'
