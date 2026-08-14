from django.urls import path
from . import views

urlpatterns = [
    path('addresses/', views.SavedAddressListCreateView.as_view(), name='saved-address-list'),
    path('addresses/<int:pk>/', views.SavedAddressDetailView.as_view(), name='saved-address-detail'),
    path('wishlist/', views.WishlistView.as_view(), name='wishlist'),
    path('wishlist/<int:product_id>/', views.WishlistToggleView.as_view(), name='wishlist-toggle'),
]
