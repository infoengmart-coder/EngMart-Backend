from django.urls import path
from . import views

urlpatterns = [
    path('', views.CategoryListView.as_view(), name='category-list'),
    path('<slug:slug>/', views.CategoryDetailView.as_view(), name='category-detail'),
    path('<slug:slug>/products/', views.CategoryProductsView.as_view(), name='category-products'),
]
