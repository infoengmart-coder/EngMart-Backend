from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """
    Product category with self-referencing parent for subcategories.
    Examples: MCB, MCCB, Contactors, Current Transformers, Panel Meters
    """
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
    )
    short_name = models.CharField(
        max_length=50,
        blank=True,
        help_text='Abbreviated name, e.g. "MCBs" for "Miniature Circuit Breakers"',
    )
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=100,
        blank=True,
        help_text='Emoji or icon class name',
    )
    image = models.ImageField(upload_to='categories/', blank=True)
    color = models.CharField(
        max_length=7,
        blank=True,
        help_text='Hex color code for UI, e.g. #F97316',
    )
    order = models.IntegerField(default=0, help_text='Display order (lower = first)')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def product_count(self):
        """Total products in this category and all subcategories."""
        count = self.products.filter(is_active=True).count()
        for child in self.children.filter(is_active=True):
            count += child.product_count
        return count
