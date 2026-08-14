from django.urls import path
from . import views

urlpatterns = [
    path('', views.BannerListView.as_view(), name='banner-list'),
    path('<int:pk>/', views.BannerDetailView.as_view(), name='banner-detail'),
]
