from rest_framework import generics, status, filters
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from apps.common.permissions import IsAdminUser
from django.utils import timezone

from apps.common.email import send_inquiry_emails, send_inquiry_reply_email
from apps.notifications.service import notify_admin, notify_user
from .models import Inquiry
from .serializers import InquiryCreateSerializer, InquiryReadSerializer


class InquiryCreateView(generics.CreateAPIView):
    """
    POST /api/inquiries/
    Submit a contact/inquiry form. Public endpoint, no auth required.
    """
    serializer_class = InquiryCreateSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Acknowledge the customer + alert sales. Never blocks or fails the request.
        send_inquiry_emails(serializer.instance)
        _i = serializer.instance
        notify_admin('inquiry', f'New enquiry from {_i.name}',
                     (_i.message or '')[:120], '/admin/queries')

        return Response(
            {'message': 'Inquiry submitted successfully. We will contact you soon.'},
            status=status.HTTP_201_CREATED,
        )


class InquiryListView(generics.ListAPIView):
    """
    GET /api/inquiries/
    List inquiries for admin.
    """
    permission_classes = [IsAdminUser]
    queryset = Inquiry.objects.all()
    serializer_class = InquiryReadSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filter_fields = ['status']
    search_fields = ['name', 'company', 'email', 'phone', 'product_interest', 'message']
    ordering_fields = ['created_at']
    ordering = ['-created_at']


class InquiryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/inquiries/<int:pk>/ — Get single inquiry
    PATCH/PUT /api/inquiries/<int:pk>/ — Update status, notes
    DELETE /api/inquiries/<int:pk>/ — Delete inquiry
    """
    permission_classes = [IsAdminUser]
    queryset = Inquiry.objects.all()
    serializer_class = InquiryReadSerializer


class InquiryReplyView(APIView):
    """
    POST /api/inquiries/<pk>/reply/  { reply }

    Sends the shop's reply to the customer by email, records it against the
    inquiry so it also shows in their account, and marks the thread replied.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        reply = (request.data.get('reply') or '').strip()
        if not reply:
            return Response({'reply': ['Please write a reply before sending.']},
                            status=status.HTTP_400_BAD_REQUEST)

        inquiry = Inquiry.objects.filter(pk=pk).first()
        if not inquiry:
            return Response({'detail': 'Inquiry not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        if not inquiry.email:
            return Response({'detail': 'This inquiry has no email address to reply to.'},
                            status=status.HTTP_409_CONFLICT)

        inquiry.admin_reply = reply
        inquiry.replied_at = timezone.now()
        inquiry.status = 'replied'
        inquiry.save(update_fields=['admin_reply', 'replied_at', 'status', 'updated_at'])

        send_inquiry_reply_email(inquiry, reply)
        from django.contrib.auth.models import User
        _u = User.objects.filter(email__iexact=(inquiry.email or '').strip()).first()
        notify_user(_u, 'inquiry_reply', 'We replied to your enquiry',
                    reply[:120], '/account/support')
        return Response(InquiryReadSerializer(inquiry).data)
