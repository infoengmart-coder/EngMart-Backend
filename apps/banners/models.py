from django.db import models


class Banner(models.Model):
    """
    Homepage promotional banner managed from the admin dashboard.

    Two placements:
      - carousel: full-width rotating hero slides
      - sidebar:  smaller promo cards beside/below the hero

    The image can either be uploaded (``image``) or referenced by an external
    URL (``image_url``) — the serializer exposes a single resolved ``image_src``.
    """
    TYPE_CHOICES = [
        ('hero', 'Homepage Hero'),
        ('carousel', 'Hero Carousel'),
        ('sidebar', 'Sidebar Promo'),
    ]

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='carousel',
        help_text='Where this banner is displayed on the homepage',
    )
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    badge = models.CharField(
        max_length=100,
        blank=True,
        help_text='Small label above the title, e.g. "PREMIUM SELECTION"',
    )

    # Primary call to action
    cta_text = models.CharField(max_length=100, blank=True)
    cta_link = models.CharField(max_length=500, blank=True)
    # Secondary call to action (carousel slides usually have two)
    cta_text_2 = models.CharField(max_length=100, blank=True)
    cta_link_2 = models.CharField(max_length=500, blank=True)

    image = models.ImageField(upload_to='banners/', blank=True)
    image_url = models.URLField(
        max_length=1000,
        blank=True,
        help_text='External image URL, used when no image file is uploaded',
    )

    # Hero banners can play a background video instead of a still image.
    video_url = models.CharField(
        max_length=1000,
        blank=True,
        help_text='Background video for the homepage hero, e.g. /herovideo.mp4 or a full URL',
    )
    # Small pills shown under the hero copy, e.g. ["2,500+ Products", "Karachi Based"].
    highlights = models.JSONField(
        default=list,
        blank=True,
        help_text='List of short strings shown as pills under the hero text',
    )

    accent_color = models.CharField(max_length=7, blank=True, default='#3B82F6')
    text_color = models.CharField(max_length=7, blank=True, default='#FFFFFF')
    bg_color = models.CharField(max_length=7, blank=True, default='#0F172A')

    is_active = models.BooleanField(default=True)
    order = models.IntegerField(default=0, help_text='Display order (lower = first)')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['type', 'order', 'id']

    def __str__(self):
        return f'[{self.get_type_display()}] {self.title}'

    @property
    def image_src(self):
        """Resolved image source — uploaded file takes precedence over the URL."""
        if self.image:
            return self.image.url
        return self.image_url or ''
