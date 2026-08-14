from django.urls import path
from . import views

urlpatterns = [
    path('validate/', views.PromoCodeValidateView.as_view(), name='promo-validate'),
    path('', views.PromoCodeListCreateView.as_view(), name='promo-list'),
    path('<int:pk>/', views.PromoCodeDetailView.as_view(), name='promo-detail'),
]
