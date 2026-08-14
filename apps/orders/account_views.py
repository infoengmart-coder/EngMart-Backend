"""
Customer-facing account endpoints.

Everything here is scoped to the authenticated user. Orders placed as a guest
are matched back by email, so a customer who checks out before signing up still
sees that history once they register with the same address.
"""
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from apps.common.email import send_order_status_email
from apps.notifications.service import notify_admin
from .models import Order
from .serializers import OrderReadSerializer


def orders_for(user):
    """
    Orders belonging to this user.

    Ownership is the ``user`` foreign key only. Matching on customer_email was
    deliberately removed: email is self-asserted and unverified, so anyone could
    register (or re-point their profile) with someone else's address and read
    that person's order history. Guest orders therefore do not appear here until
    a verified claim flow exists.
    """
    return Order.objects.filter(user=user).prefetch_related('items__product').distinct()


class MyOrderListView(generics.ListAPIView):
    """GET /api/account/orders/ — the signed-in customer's order history."""
    permission_classes = [IsAuthenticated]
    serializer_class = OrderReadSerializer

    def get_queryset(self):
        return orders_for(self.request.user).order_by('-created_at')


class MyOrderDetailView(generics.RetrieveAPIView):
    """
    GET /api/account/orders/<order_number>/ — one of the customer's own orders.

    Scoped to their own orders, so a guessed order number cannot expose someone
    else's details.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OrderReadSerializer
    lookup_field = 'order_number'

    def get_queryset(self):
        return orders_for(self.request.user)


class MyOrderCancelView(APIView):
    """
    POST /api/account/orders/<order_number>/cancel/ — customer cancels their own
    order.

    Scoped to their own orders, and only allowed while the order has not been
    dispatched: once it is packed or shipped, cancelling is a conversation with
    the shop, not a button.
    """
    permission_classes = [IsAuthenticated]

    # Anything past this point involves stock that has already moved.
    CANCELLABLE = {'pending', 'confirmed'}

    def post(self, request, order_number):
        order = orders_for(request.user).filter(order_number=order_number).first()
        if not order:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if order.status == 'cancelled':
            return Response(OrderReadSerializer(order).data)

        if order.status not in self.CANCELLABLE:
            return Response(
                {'detail': (
                    f'This order is already {order.get_status_display().lower()} and can no '
                    f'longer be cancelled online. Please contact us and we will help.'
                )},
                status=status.HTTP_409_CONFLICT,
            )

        order.status = 'cancelled'
        order.save(update_fields=['status', 'updated_at'])
        # Tell the shop — otherwise a cancellation only exists in the customer's
        # browser and the team keeps preparing the order.
        send_order_status_email(order, cancelled_by_customer=True)
        notify_admin('order_cancelled', f'Order {order.order_number} cancelled',
                     f'{order.customer_name} cancelled their order', '/admin/orders')
        return Response(OrderReadSerializer(order).data)


class MyOrderReturnView(APIView):
    """
    POST /api/account/orders/<order_number>/return/ — request a return.

    Only meaningful once the goods have arrived.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, order_number):
        order = orders_for(request.user).filter(order_number=order_number).first()
        if not order:
            return Response({'detail': 'Order not found.'}, status=status.HTTP_404_NOT_FOUND)

        if order.status != 'delivered':
            return Response(
                {'detail': 'A return can only be requested after the order has been delivered.'},
                status=status.HTTP_409_CONFLICT,
            )

        order.status = 'return_requested'
        order.save(update_fields=['status', 'updated_at'])
        send_order_status_email(order, return_requested=True)
        notify_admin('return_requested', f'Return requested — {order.order_number}',
                     f'{order.customer_name} asked to return this order', '/admin/orders')
        return Response(OrderReadSerializer(order).data)


class MyQuotationListView(APIView):
    """GET /api/account/quotes/ — quote requests raised by this customer."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.quotations.models import Quotation
        from apps.quotations.serializers import QuotationSerializer

        # Email on the account is validated unique at registration and is no
        # longer self-editable, so it is a safe lookup key here.
        email = (request.user.email or '').strip()
        if not email:
            return Response({'count': 0, 'results': []})

        quotes = (
            Quotation.objects.filter(email__iexact=email)
            .prefetch_related('items__product')
            .order_by('-created_at')
        )
        data = QuotationSerializer(quotes, many=True).data
        # admin_notes are internal — never expose them to the customer.
        for row in data:
            row.pop('admin_notes', None)
        return Response({'count': len(data), 'results': data})


class MyInquiryListView(APIView):
    """GET /api/account/inquiries/ — contact/support messages from this customer."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.inquiries.models import Inquiry
        from apps.inquiries.serializers import InquiryReadSerializer

        email = (request.user.email or '').strip()
        if not email:
            return Response({'count': 0, 'results': []})

        inquiries = Inquiry.objects.filter(email__iexact=email).order_by('-created_at')
        data = InquiryReadSerializer(inquiries, many=True).data
        # `notes` is the internal admin note on Inquiry — strip it.
        for row in data:
            row.pop('notes', None)
        return Response({'count': len(data), 'results': data})
