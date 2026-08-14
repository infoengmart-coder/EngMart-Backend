from django.urls import path
from . import views

urlpatterns = [
    path('', views.QuotationListView.as_view(), name='quotation-list'),
    path('submit/', views.QuotationCreateView.as_view(), name='quotation-create'),
    path('<int:pk>/', views.QuotationDetailView.as_view(), name='quotation-detail'),
]
