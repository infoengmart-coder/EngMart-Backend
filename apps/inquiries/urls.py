from django.urls import path
from . import views

urlpatterns = [
    path('<int:pk>/reply/', views.InquiryReplyView.as_view(), name='inquiry-reply'),
    path('', views.InquiryListView.as_view(), name='inquiry-list'),
    path('submit/', views.InquiryCreateView.as_view(), name='inquiry-create'),
    path('<int:pk>/', views.InquiryDetailView.as_view(), name='inquiry-detail'),
]
