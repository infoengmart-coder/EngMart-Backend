from django.db import models


class Inquiry(models.Model):
    """
    Contact/inquiry form submission from the website.
    Stored in DB and viewable in Django Admin.
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('closed', 'Closed'),
    ]

    name = models.CharField(max_length=200)
    company = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField()
    message = models.TextField()
    product_interest = models.CharField(
        max_length=300,
        blank=True,
        help_text='Product or category the customer is asking about',
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new',
    )
    notes = models.TextField(
        blank=True,
        help_text='Internal notes (not visible to customer)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Inquiries'

    def __str__(self):
        return f'{self.name} — {self.product_interest or "General"} ({self.created_at:%Y-%m-%d})'
