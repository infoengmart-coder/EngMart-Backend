from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from apps.products.models import Product
from .models import SavedAddress, WishlistItem
from .serializers import SavedAddressSerializer, WishlistItemSerializer


class SavedAddressListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/account/addresses/ — the signed-in customer's addresses."""
    permission_classes = [IsAuthenticated]
    serializer_class = SavedAddressSerializer
    pagination_class = None

    def get_queryset(self):
        return SavedAddress.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        # The first address a customer saves becomes their default.
        is_first = not SavedAddress.objects.filter(user=self.request.user).exists()
        serializer.save(
            user=self.request.user,
            is_default=is_first or serializer.validated_data.get('is_default', False),
        )


class SavedAddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Manage one saved address.

    Scoped to the owner, so another customer's address id returns 404 rather
    than exposing or letting anyone edit their delivery details.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SavedAddressSerializer

    def get_queryset(self):
        return SavedAddress.objects.filter(user=self.request.user)


class WishlistView(generics.ListAPIView):
    """GET /api/account/wishlist/ — saved products with full card data."""
    permission_classes = [IsAuthenticated]
    serializer_class = WishlistItemSerializer
    pagination_class = None

    def get_queryset(self):
        return WishlistItem.objects.filter(user=self.request.user).select_related(
            'product__brand', 'product__category',
        ).prefetch_related('product__variants')


class WishlistToggleView(APIView):
    """
    POST   /api/account/wishlist/<product_id>/ — add to wishlist (idempotent).
    DELETE /api/account/wishlist/<product_id>/ — remove from wishlist.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, product_id):
        product = get_object_or_404(Product, id=product_id, is_active=True)
        item, created = WishlistItem.objects.get_or_create(
            user=request.user, product=product,
        )
        return Response(
            WishlistItemSerializer(item).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, product_id):
        WishlistItem.objects.filter(user=request.user, product_id=product_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
