from django.urls import path
from . import views

urlpatterns = [
    path('', views.BrandListView.as_view(), name='brand-list'),
    path('<slug:slug>/', views.BrandDetailView.as_view(), name='brand-detail'),
    path('<slug:slug>/products/', views.BrandProductsView.as_view(), name='brand-products'),
]
