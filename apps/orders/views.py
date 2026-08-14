from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from apps.common.permissions import IsAdminUser
from apps.common.email import send_order_emails, send_payment_slip_notification
from apps.notifications.service import notify_admin, notify_user
from django.db.models import Sum, Count, F, Q, Value, CharField, DecimalField
from django.db.models.functions import TruncMonth, TruncWeek, Coalesce
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from datetime import timedelta

from .models import Order, OrderItem, PromoCode
from .serializers import (
    OrderCreateSerializer,
    OrderReadSerializer,
    PromoCodeValidateSerializer,
    PromoCodeSerializer,
)
from apps.products.models import Product
from apps.inquiries.models import Inquiry
from apps.inquiries.serializers import InquiryReadSerializer


class OrderCreateView(generics.CreateAPIView):
    """POST /api/orders/ — Create a new order from checkout (public)."""
    serializer_class = OrderCreateSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        # Attach the order to the account when the buyer is signed in, so it
        # shows up under "My Orders" even if they used a different email.
        if request.user and request.user.is_authenticated:
            order.user = request.user
            order.save(update_fields=['user', 'updated_at'])

        # Confirm to the customer + alert sales. Never blocks or fails the order.
        send_order_emails(order)
        notify_admin(
            'order_placed',
            f'New order {order.order_number}',
            f'{order.customer_name} — PKR {order.total:,.0f}',
            '/admin/orders',
        )

        # Return the created order details
        read_serializer = OrderReadSerializer(order)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED)


class PaymentSlipUploadView(APIView):
    """
    POST /api/orders/<order_number>/payment-slip/ — Upload proof of bank transfer.

    Public because guests check out without an account. The order number is the
    capability: it is random per order and only shown to the buyer. To limit
    what a guessed number could do, an upload is only accepted while the order
    is still unpaid, and it can never change any other field.
    """
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser]

    MAX_BYTES = 5 * 1024 * 1024
    ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/heic', 'application/pdf'}

    def post(self, request, order_number):
        order = get_object_or_404(Order, order_number=order_number)

        if order.payment_status == 'paid':
            return Response(
                {'detail': 'This order is already marked paid. Contact us if you need to send another receipt.'},
                status=status.HTTP_409_CONFLICT,
            )

        upload = request.FILES.get('payment_slip') or request.FILES.get('file')
        if not upload:
            return Response(
                {'detail': 'No file was provided (expected form field "payment_slip").'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size > self.MAX_BYTES:
            return Response(
                {'detail': 'File is too large. Maximum size is 5 MB.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.content_type not in self.ALLOWED_TYPES:
            return Response(
                {'detail': 'Unsupported file type. Upload a JPG, PNG, WEBP or PDF.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        order.payment_slip = upload
        order.payment_slip_uploaded_at = timezone.now()
        reference = (request.data.get('payment_reference') or '').strip()
        if reference:
            order.payment_reference = reference[:100]
        order.save(update_fields=[
            'payment_slip', 'payment_slip_uploaded_at', 'payment_reference', 'updated_at',
        ])

        # Let the sales team know a receipt is waiting to be verified.
        send_payment_slip_notification(order)

        return Response({
            'message': 'Payment slip uploaded. We will verify it and confirm your order.',
            'order_number': order.order_number,
            'payment_slip': request.build_absolute_uri(order.payment_slip.url),
            'payment_reference': order.payment_reference,
        }, status=status.HTTP_200_OK)


class OrderListView(generics.ListAPIView):
    """GET /api/orders/list/ — List all orders (admin) with search and status filters."""
    permission_classes = [IsAdminUser]
    queryset = Order.objects.prefetch_related('items__product').all()
    serializer_class = OrderReadSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'payment_status', 'payment_method']
    search_fields = ['order_number', 'customer_name', 'customer_email', 'customer_phone', 'company_name']
    ordering_fields = ['created_at', 'total']
    ordering = ['-created_at']


class OrderDetailView(generics.RetrieveUpdateAPIView):
    """
    GET /api/orders/<order_number>/ — Get single order
    PATCH/PUT /api/orders/<order_number>/ — Update order status, payment_status, notes
    """
    permission_classes = [IsAdminUser]
    serializer_class = OrderReadSerializer
    lookup_field = 'order_number'
    queryset = Order.objects.prefetch_related('items__product').all()

    def perform_update(self, serializer):
        """Notify the customer when the shop moves their order along."""
        previous = serializer.instance.status
        order = serializer.save()
        if order.status != previous and order.user_id:
            notify_user(
                order.user, 'order_status',
                f'Order {order.order_number} is now {order.get_status_display()}',
                'Tap to see the latest on your order',
                f'/account/orders/{order.order_number}',
            )


class PromoCodeValidateView(APIView):
    """POST /api/promo/validate/ — Validate a promo code (public, used at checkout)."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PromoCodeValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code = serializer.validated_data['code']
        subtotal = serializer.validated_data.get('subtotal', 0)

        try:
            promo = PromoCode.objects.get(code__iexact=code)
        except PromoCode.DoesNotExist:
            return Response(
                {'valid': False, 'error': 'Invalid promo code.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not promo.is_valid:
            return Response(
                {'valid': False, 'error': 'This promo code has expired or reached its usage limit.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if subtotal < promo.min_order_amount:
            return Response(
                {
                    'valid': False,
                    'error': f'Minimum order of PKR {promo.min_order_amount:,.0f} required for this code.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        discount = promo.calculate_discount(subtotal)

        return Response({
            'valid': True,
            'code': promo.code,
            'discount_type': promo.discount_type,
            'discount_value': str(promo.discount_value),
            'discount_amount': str(discount),
            'description': promo.description,
        })


# ─── Promo Code CRUD ─────────────────────────────────────────

class PromoCodeListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/promo/ — List and create promo codes (admin)."""
    permission_classes = [IsAdminUser]
    queryset = PromoCode.objects.all()
    serializer_class = PromoCodeSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['code', 'description']
    pagination_class = None


class PromoCodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/promo/<id>/ — Manage individual promo code (admin)."""
    permission_classes = [IsAdminUser]
    queryset = PromoCode.objects.all()
    serializer_class = PromoCodeSerializer


# ─── Admin Stats ──────────────────────────────────────────────

class AdminStatsView(APIView):
    """GET /api/orders/stats/ — Return overview metrics for admin dashboard."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Revenue
        valid_orders = Order.objects.exclude(status='cancelled')
        total_revenue = valid_orders.aggregate(res=Sum('total'))['res'] or 0
        monthly_revenue = valid_orders.filter(created_at__gte=start_of_month).aggregate(res=Sum('total'))['res'] or 0

        # Order stats
        total_orders = Order.objects.count()
        pending_orders = Order.objects.filter(status='pending').count()
        distinct_customers = Order.objects.values('customer_email').distinct().count()

        # Product stats
        total_products = Product.objects.filter(is_active=True).count()

        # Inquiries stats
        new_inquiries = Inquiry.objects.filter(status='new').count()
        total_inquiries = Inquiry.objects.count()

        # Recent items
        recent_orders = OrderReadSerializer(Order.objects.prefetch_related('items__product')[:5], many=True).data
        recent_inquiries = InquiryReadSerializer(Inquiry.objects.all()[:5], many=True).data

        # Revenue chart — last 6 months
        six_months_ago = now - timedelta(days=180)
        revenue_chart = list(
            valid_orders
            .filter(created_at__gte=six_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(value=Coalesce(Sum('total'), Value(0, output_field=DecimalField())))
            .order_by('month')
        )
        revenue_chart_data = [
            {'label': m['month'].strftime('%b %Y'), 'value': float(m['value'])}
            for m in revenue_chart
        ]

        # Top selling products
        top_selling = list(
            OrderItem.objects
            .values('product_name')
            .annotate(units=Sum('quantity'))
            .order_by('-units')[:5]
        )

        # Low stock — products with few active variants
        # Since we don't have a stock field, return products with 0 or few variants
        low_stock_items = []  # Will be populated if stock tracking is added

        return Response({
            'total_revenue': float(total_revenue),
            'monthly_revenue': float(monthly_revenue),
            'total_orders': total_orders,
            'pending_orders': pending_orders,
            'total_customers': distinct_customers,
            'total_products': total_products,
            'new_inquiries': new_inquiries,
            'total_inquiries': total_inquiries,
            'recent_orders': recent_orders,
            'recent_inquiries': recent_inquiries,
            'revenue_chart': revenue_chart_data,
            'top_selling': top_selling,
            'low_stock_items': low_stock_items,
        })


# ─── Customers (derived from orders) ─────────────────────────

class CustomerListView(APIView):
    """GET /api/orders/customers/ — Aggregate customers from orders."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        search = request.query_params.get('search', '').strip()
        type_filter = request.query_params.get('type', '').strip()

        customers_qs = (
            Order.objects
            .values('customer_email')
            .annotate(
                name=F('customer_name'),
                company=F('company_name'),
                phone=F('customer_phone'),
                total_orders=Count('id'),
                lifetime_value=Coalesce(Sum('total'), Value(0, output_field=DecimalField())),
                joined=F('created_at'),
            )
            .order_by('-lifetime_value')
        )

        if search:
            customers_qs = customers_qs.filter(
                Q(customer_name__icontains=search) |
                Q(customer_email__icontains=search) |
                Q(company_name__icontains=search)
            )

        # Build customer list with deduplication
        seen = set()
        customers = []
        for c in customers_qs:
            email = c['customer_email']
            if email in seen:
                continue
            seen.add(email)
            # Determine type based on order count
            acct_type = 'Wholesale' if c['total_orders'] >= 5 else 'Retail'
            if type_filter and type_filter != 'All' and acct_type != type_filter:
                continue
            customers.append({
                'name': c['name'],
                'company': c['company'] or '',
                'email': email,
                'phone': c['phone'],
                'type': acct_type,
                'total_orders': c['total_orders'],
                'lifetime_value': float(c['lifetime_value']),
                'joined': c['joined'].isoformat() if c['joined'] else '',
            })

        return Response({'results': customers, 'count': len(customers)})


# ─── Reports ─────────────────────────────────────────────────

class AdminReportsView(APIView):
    """GET /api/orders/reports/ — Aggregated report data."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        now = timezone.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        start_of_prev_month = (start_of_month - timedelta(days=1)).replace(day=1)

        valid_orders = Order.objects.exclude(status='cancelled')

        # Revenue metrics
        total_revenue = float(valid_orders.aggregate(r=Sum('total'))['r'] or 0)
        monthly_revenue = float(
            valid_orders.filter(created_at__gte=start_of_month).aggregate(r=Sum('total'))['r'] or 0
        )
        prev_month_revenue = float(
            valid_orders.filter(
                created_at__gte=start_of_prev_month, created_at__lt=start_of_month
            ).aggregate(r=Sum('total'))['r'] or 0
        )

        # Average order value
        order_count = valid_orders.count() or 1
        avg_order_value = total_revenue / order_count

        # Revenue change
        if prev_month_revenue > 0:
            revenue_change = round(((monthly_revenue - prev_month_revenue) / prev_month_revenue) * 100, 1)
        else:
            revenue_change = 0

        # Monthly revenue chart (last 7 months)
        seven_months_ago = now - timedelta(days=210)
        monthly_chart = list(
            valid_orders
            .filter(created_at__gte=seven_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(value=Coalesce(Sum('total'), Value(0, output_field=DecimalField())))
            .order_by('month')
        )

        # Top selling products
        top_selling = list(
            OrderItem.objects
            .values('product_name', 'brand_name', 'cat_no')
            .annotate(
                units=Sum('quantity'),
                revenue=Coalesce(Sum('line_total'), Value(0, output_field=DecimalField())),
            )
            .order_by('-units')[:5]
        )
        # Add rank and guess category
        for i, item in enumerate(top_selling):
            item['rank'] = i + 1
            item['category'] = ''
            item['revenue'] = float(item['revenue'])

        # Brand performance
        brand_perf = list(
            OrderItem.objects
            .exclude(brand_name='')
            .values('brand_name')
            .annotate(revenue=Coalesce(Sum('line_total'), Value(0, output_field=DecimalField())))
            .order_by('-revenue')[:5]
        )
        total_brand_rev = sum(float(b['revenue']) for b in brand_perf) or 1
        for b in brand_perf:
            b['revenue'] = float(b['revenue'])
            b['percentage'] = round((b['revenue'] / total_brand_rev) * 100)

        return Response({
            'total_revenue': total_revenue,
            'monthly_revenue': monthly_revenue,
            'avg_order_value': round(avg_order_value, 2),
            'revenue_change': revenue_change,
            'total_orders': valid_orders.count(),
            'monthly_chart': [
                {'month': m['month'].strftime('%b'), 'value': float(m['value'])}
                for m in monthly_chart
            ],
            'top_selling': top_selling,
            'brand_performance': brand_perf,
        })
