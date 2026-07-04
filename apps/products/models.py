from django.db import models
from django.utils.text import slugify
from apps.brands.models import Brand
from apps.categories.models import Category


class Product(models.Model):
    """
    A product represents a model series, e.g. "CHINT NXB-63 MCB".
    Individual ratings/sizes are stored as ProductVariant instances.
    """
    name = models.CharField(max_length=300)
    slug = models.SlugField(max_length=300, unique=True)
    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name='products',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='products',
    )
    series = models.CharField(
        max_length=200,
        blank=True,
        help_text='Model series, e.g. "NXB-63", "T MAX", "HDM3"',
    )
    short_description = models.TextField(
        blank=True,
        help_text='One-line description for cards and search results',
    )
    full_description = models.TextField(
        blank=True,
        help_text='Detailed product description for the detail page',
    )
    image = models.ImageField(upload_to='products/', blank=True)
    datasheet_url = models.URLField(blank=True, help_text='Link to PDF datasheet')
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(
        default=False,
        help_text='Show on homepage featured products section',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # SEO fields
    meta_title = models.CharField(
        max_length=60,
        blank=True,
        help_text='SEO title (auto-generated if blank)',
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text='SEO description (auto-generated if blank)',
    )

    class Meta:
        ordering = ['brand__name', 'name']

    def __str__(self):
        return f'{self.brand.name} {self.name}'

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f'{self.brand.name}-{self.name}')
            self.slug = base_slug
        # Auto-generate SEO fields if blank
        if not self.meta_title:
            self.meta_title = f'{self.name} | {self.brand.name} | Eng-Mart'[:60]
        if not self.meta_description:
            self.meta_description = (
                f'Buy {self.name} by {self.brand.name} in Pakistan. '
                f'{self.short_description}'
            )[:160]
        super().save(*args, **kwargs)

    @property
    def price_range(self):
        """Return min/max price from variants for display."""
        prices = self.variants.filter(
            is_active=True,
            price__isnull=False,
            price_on_request=False,
        ).values_list('price', flat=True)
        if not prices:
            return None
        price_list = list(prices)
        return {
            'min': min(price_list),
            'max': max(price_list),
        }

    @property
    def has_price_on_request(self):
        """Check if any variant is price-on-request."""
        return self.variants.filter(
            is_active=True,
            price_on_request=True,
        ).exists()


class ProductVariant(models.Model):
    """
    Individual product variant with specific ratings/specs.
    E.g., "NXB-63 3P C32 6kA" is a variant of the NXB-63 product.
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='variants',
    )
    cat_no = models.CharField(
        max_length=100,
        blank=True,
        help_text='Catalog/model number',
    )
    description = models.CharField(
        max_length=300,
        help_text='Variant description, e.g. "16A 3-Pole IP44"',
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Price in PKR (leave blank if price on request)',
    )
    price_on_request = models.BooleanField(
        default=False,
        help_text='Check if price is "POR" or "On Request"',
    )
    specs = models.JSONField(
        default=dict,
        blank=True,
        help_text='Flexible specs: {"ampere": "32A", "poles": "3", "breaking_capacity": "6kA"}',
    )
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def __str__(self):
        return f'{self.product.name} — {self.description}'


class ProductImage(models.Model):
    """Additional product images beyond the main image."""
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='images',
    )
    image = models.ImageField(upload_to='products/')
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['-is_primary', 'order']

    def __str__(self):
        return f'{self.product.name} — Image {self.order}'
