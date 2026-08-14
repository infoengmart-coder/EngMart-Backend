from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.CatalogStatsView.as_view(), name='catalog-stats'),
    path('', views.ProductListView.as_view(), name='product-list'),
    path('search/', views.ProductSearchView.as_view(), name='product-search'),
    path('featured/', views.FeaturedProductsView.as_view(), name='product-featured'),
    path('slugs/', views.ProductSlugListView.as_view(), name='product-slugs'),
    path('filter-meta/', views.ProductFilterMetaView.as_view(), name='product-filter-meta'),
    path('images/<int:pk>/', views.ProductImageDetailView.as_view(), name='product-image-detail'),
    path('<slug:slug>/', views.ProductDetailView.as_view(), name='product-detail'),
    path('<slug:slug>/image/', views.ProductMainImageView.as_view(), name='product-main-image'),
    path('<slug:slug>/images/', views.ProductGalleryView.as_view(), name='product-gallery'),
]
