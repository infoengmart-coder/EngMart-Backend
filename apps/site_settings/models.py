import re

from django.db import models


class SiteSettings(models.Model):
    """
    Singleton store configuration, editable from the admin dashboard.

    Always stored as the row with pk=1 — use ``SiteSettings.load()`` to fetch it
    (it creates the row on first access so the API never 404s).
    """

    # ── Identity ──
    name = models.CharField(max_length=200, default='Eng-Mart')
    tagline = models.CharField(max_length=300, blank=True, default='')
    description = models.TextField(blank=True, default='')
    url = models.URLField(max_length=500, blank=True, default='')
    logo = models.ImageField(upload_to='site/', blank=True)

    # ── Contact ──
    phone = models.CharField(max_length=50, blank=True, default='')
    mobile = models.CharField(max_length=50, blank=True, default='')
    email = models.EmailField(blank=True, default='')
    address = models.TextField(blank=True, default='')
    hours = models.CharField(max_length=200, blank=True, default='')
    hours_note = models.CharField(max_length=200, blank=True, default='')
    whatsapp = models.CharField(max_length=50, blank=True, default='')
    map_embed_url = models.URLField(max_length=1000, blank=True, default='')
    map_link_url = models.URLField(max_length=1000, blank=True, default='')

    # ── Social ──
    facebook_url = models.URLField(max_length=500, blank=True, default='')
    instagram_url = models.URLField(max_length=500, blank=True, default='')
    linkedin_url = models.URLField(max_length=500, blank=True, default='')
    twitter_url = models.URLField(max_length=500, blank=True, default='')
    youtube_url = models.URLField(max_length=500, blank=True, default='')

    # ── Payment method toggles ──
    cod_enabled = models.BooleanField(default=True)
    bank_transfer_enabled = models.BooleanField(default=True)
    mobile_wallet_enabled = models.BooleanField(default=False)
    whatsapp_order_enabled = models.BooleanField(default=True)

    # ── Bank details shown at checkout ──
    bank_name = models.CharField(max_length=150, blank=True, default='')
    bank_account_title = models.CharField(max_length=200, blank=True, default='')
    bank_account_number = models.CharField(max_length=64, blank=True, default='')
    bank_iban = models.CharField(max_length=34, blank=True, default='')
    bank_branch = models.CharField(max_length=200, blank=True, default='')
    bank_swift = models.CharField(max_length=16, blank=True, default='')

    bank_name_2 = models.CharField(max_length=150, blank=True, default='')
    bank_account_title_2 = models.CharField(max_length=200, blank=True, default='')
    bank_account_number_2 = models.CharField(max_length=64, blank=True, default='')
    bank_iban_2 = models.CharField(max_length=34, blank=True, default='')
    bank_branch_2 = models.CharField(max_length=200, blank=True, default='')
    bank_transfer_note = models.TextField(blank=True, default='')

    jazzcash_number = models.CharField(max_length=50, blank=True, default='')
    jazzcash_title = models.CharField(max_length=200, blank=True, default='')
    easypaisa_number = models.CharField(max_length=50, blank=True, default='')
    easypaisa_title = models.CharField(max_length=200, blank=True, default='')

    # ── Storefront copy ──
    free_shipping_threshold = models.DecimalField(
        max_digits=12, decimal_places=2, default=50000,
    )
    footer_payment_note = models.CharField(max_length=300, blank=True, default='')
    copyright_text = models.CharField(max_length=300, blank=True, default='')

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.name or 'Site Settings'

    def save(self, *args, **kwargs):
        # Pin to a single row so there is only ever one settings record.
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # The storefront reads these values — never allow the row to disappear.
        pass

    @classmethod
    def load(cls):
        """Fetch the singleton, creating it with defaults on first access."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def whatsapp_digits(self):
        """Digits-only WhatsApp number for building wa.me links."""
        return re.sub(r'[^0-9]', '', self.whatsapp or '')
