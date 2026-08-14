"""Customer + admin notification feed."""
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification, NotificationRead

# Cap the feed: a bell menu shows recent activity, not an archive.
FEED_LIMIT = 30


def visible_to(user):
    """
    Notifications this user is allowed to see.

    Staff see the admin feed; customers see their own plus broadcasts. A
    customer must never see the admin feed — it names other customers.
    """
    if user.is_staff:
        return Notification.objects.filter(Q(audience='admin') | Q(audience='user', user=user))
    return Notification.objects.filter(Q(audience='broadcast') | Q(audience='user', user=user))


class NotificationListView(APIView):
    """GET /api/notifications/ — recent notifications + unread count."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = visible_to(request.user)[:FEED_LIMIT]
        read_ids = set(
            NotificationRead.objects
            .filter(user=request.user, notification__in=[n.id for n in qs])
            .values_list('notification_id', flat=True)
        )
        results = [{
            'id': n.id,
            'kind': n.kind,
            'title': n.title,
            'body': n.body,
            'link': n.link,
            'created_at': n.created_at,
            'is_read': n.id in read_ids,
        } for n in qs]
        return Response({
            'results': results,
            'unread': sum(1 for r in results if not r['is_read']),
        })


class NotificationReadView(APIView):
    """POST /api/notifications/read/ — mark some (or all) as read."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ids = request.data.get('ids')
        qs = visible_to(request.user)
        if ids:
            qs = qs.filter(id__in=ids)
        else:
            qs = qs[:FEED_LIMIT]      # "mark all read" = everything on screen

        # ignore_conflicts: re-reading an already-read notification is normal
        # and must not raise on the unique constraint.
        NotificationRead.objects.bulk_create(
            [NotificationRead(notification=n, user=request.user) for n in qs],
            ignore_conflicts=True,
        )
        return Response({'detail': 'ok'}, status=status.HTTP_200_OK)
