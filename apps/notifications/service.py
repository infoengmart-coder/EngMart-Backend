"""
One place to raise a notification.

Every call is wrapped so a notification failure can NEVER break the business
action that triggered it — the same rule the email layer follows. Nobody should
lose an order because the bell icon had a bad day.
"""
import logging

from .models import Notification

logger = logging.getLogger('apps.notifications')


def _create(**kwargs):
    try:
        return Notification.objects.create(**kwargs)
    except Exception:
        logger.exception('Failed to create notification (ignored)')
        return None


def notify_admin(kind, title, body='', link=''):
    """Tell the shop team something happened."""
    return _create(audience='admin', kind=kind, title=title, body=body, link=link)


def notify_user(user, kind, title, body='', link=''):
    """Tell one customer something. No-op for guest (userless) actions."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return _create(audience='user', user=user, kind=kind, title=title, body=body, link=link)


def notify_all_customers(kind, title, body='', link=''):
    """One row that every customer sees — used for new-stock announcements."""
    return _create(audience='broadcast', kind=kind, title=title, body=body, link=link)
