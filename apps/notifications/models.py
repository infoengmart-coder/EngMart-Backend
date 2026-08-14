"""
In-app notifications for the admin panel and customer accounts.

Design note — why there is a separate `NotificationRead` table:

A "new product added" notification goes to *every* customer. Writing one row
per customer would mean thousands of rows for a single announcement, growing
with the customer base. Instead a broadcast is ONE row, and we record only the
customers who have actually read it. Unread is the default, which is also the
common case, so the read table stays small.
"""
from django.contrib.auth.models import User
from django.db import models


class Notification(models.Model):
    """Something worth telling the shop or a customer about."""

    # Who it is for:
    #   admin     — everyone with staff access (new order, cancellation…)
    #   user      — one specific customer (their quote is ready)
    #   broadcast — all customers (new products in stock)
    AUDIENCE_CHOICES = [
        ('admin', 'Admin team'),
        ('user', 'Specific customer'),
        ('broadcast', 'All customers'),
    ]

    KIND_CHOICES = [
        ('order_placed', 'Order placed'),
        ('order_cancelled', 'Order cancelled'),
        ('order_status', 'Order status changed'),
        ('return_requested', 'Return requested'),
        ('quote_request', 'Quote requested'),
        ('quote_ready', 'Quote ready'),
        ('inquiry', 'New inquiry'),
        ('inquiry_reply', 'Inquiry answered'),
        ('new_product', 'New products added'),
    ]

    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, db_index=True)
    # Set only when audience='user'.
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications',
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=400, blank=True, default='')
    # Where clicking it should take you, e.g. /admin/orders or /account/quotes
    link = models.CharField(max_length=300, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['audience', '-created_at'])]

    def __str__(self):
        return f'[{self.audience}] {self.title}'


class NotificationRead(models.Model):
    """Marks one notification as read by one user."""
    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name='reads',
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_reads')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # One row per (notification, user) — marking read twice must not
        # create duplicates.
        constraints = [
            models.UniqueConstraint(
                fields=['notification', 'user'], name='uniq_notification_read',
            )
        ]
