from django.urls import path
from . import account_views

urlpatterns = [
    path('orders/', account_views.MyOrderListView.as_view(), name='my-orders'),
    path('orders/<str:order_number>/cancel/', account_views.MyOrderCancelView.as_view(), name='my-order-cancel'),
    path('orders/<str:order_number>/return/', account_views.MyOrderReturnView.as_view(), name='my-order-return'),
    path('orders/<str:order_number>/', account_views.MyOrderDetailView.as_view(), name='my-order-detail'),
    path('quotes/', account_views.MyQuotationListView.as_view(), name='my-quotes'),
    path('inquiries/', account_views.MyInquiryListView.as_view(), name='my-inquiries'),
]
