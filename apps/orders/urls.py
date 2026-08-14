from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderCreateView.as_view(), name='order-create'),
    path('list/', views.OrderListView.as_view(), name='order-list'),
    path('stats/', views.AdminStatsView.as_view(), name='admin-stats'),
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('reports/', views.AdminReportsView.as_view(), name='admin-reports'),
    path('<str:order_number>/payment-slip/', views.PaymentSlipUploadView.as_view(), name='order-payment-slip'),
    path('<str:order_number>/', views.OrderDetailView.as_view(), name='order-detail'),
]
