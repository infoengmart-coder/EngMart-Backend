from django.db import models
from django.utils.text import slugify


class Brand(models.Model):
    """
    Product brand / manufacturer.
    Examples: ABB, CHINT, Himel, FICO Hi-Tech, PCE, Tense, Kondas, Opas, Siemens
    """
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    logo = models.ImageField(upload_to='brands/', blank=True)
    origin_country = models.CharField(
        max_length=100,
        blank=True,
        help_text='Country of origin, e.g. "Switzerland", "Turkey"',
    )
    supplier_name = models.CharField(
        max_length=200,
        blank=True,
        help_text='Local supplier/distributor, e.g. "AT Electricals"',
    )
    supplier_contact = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    color = models.CharField(
        max_length=7,
        blank=True,
        help_text='Brand accent color hex, e.g. #FF0000 for ABB',
    )
    website = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0, help_text='Display order')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def product_count(self):
        """Total active products for this brand."""
        return self.products.filter(is_active=True).count()
