from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend

from apps.common.permissions import IsAdminUser
from apps.notifications.service import notify_admin, notify_user
from apps.common.email import send_quotation_request_emails, send_quotation_ready_email
from .models import Quotation
from .serializers import (
    QuotationSerializer,
    QuotationCreateSerializer,
)


class QuotationCreateView(generics.CreateAPIView):
    """POST /api/quotations/submit/ — Request a quote from the storefront (public)."""
    permission_classes = [AllowAny]
    serializer_class = QuotationCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = serializer.save()

        # Acknowledge the customer + alert sales. Never blocks or fails the request.
        send_quotation_request_emails(quotation)
        notify_admin('quote_request', f'New quote request {quotation.quote_number}',
                     f'{quotation.name} — {quotation.items.count()} item(s)', '/admin/quotations')

        return Response(
            {
                'message': 'Quote request submitted. Our team will respond shortly.',
                'quote_number': quotation.quote_number,
            },
            status=status.HTTP_201_CREATED,
        )


class QuotationListView(generics.ListAPIView):
    """GET /api/quotations/ — All quotations (admin)."""
    permission_classes = [IsAdminUser]
    serializer_class = QuotationSerializer
    queryset = Quotation.objects.prefetch_related('items').all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'source']
    search_fields = ['quote_number', 'name', 'company', 'email', 'phone']
    ordering_fields = ['created_at', 'quoted_total']
    ordering = ['-created_at']


class QuotationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET/PATCH/DELETE /api/quotations/<id>/ — Manage a quotation (admin).

    Setting status to 'quoted' stamps quoted_at automatically.
    """
    permission_classes = [IsAdminUser]
    serializer_class = QuotationSerializer
    queryset = Quotation.objects.prefetch_related('items').all()

    def perform_update(self, serializer):
        was_quoted = serializer.instance.status == 'quoted'
        instance = serializer.save()

        # First transition into 'quoted' = the sales team has finished pricing,
        # so deliver the priced quote to the customer. Only fires once.
        if instance.status == 'quoted' and not was_quoted:
            if not instance.quoted_at:
                instance.quoted_at = timezone.now()
                instance.save(update_fields=['quoted_at', 'updated_at'])
            send_quotation_ready_email(instance)
            _notify_quote_ready(instance)


def _notify_quote_ready(quotation):
    """Tell the customer their quote is priced — matched by account email."""
    from django.contrib.auth.models import User
    user = User.objects.filter(email__iexact=(quotation.email or '').strip()).first()
    notify_user(
        user, 'quote_ready',
        f'Your quotation {quotation.quote_number} is ready',
        f'Total PKR {quotation.quoted_total:,.0f} — view and accept it',
        '/account/quotes',
    )
