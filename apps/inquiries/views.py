from rest_framework import generics, status
from rest_framework.response import Response
from .serializers import InquiryCreateSerializer


class InquiryCreateView(generics.CreateAPIView):
    """
    POST /api/inquiries/
    Submit a contact/inquiry form. Public endpoint, no auth required.
    """
    serializer_class = InquiryCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {'message': 'Inquiry submitted successfully. We will contact you soon.'},
            status=status.HTTP_201_CREATED,
        )
