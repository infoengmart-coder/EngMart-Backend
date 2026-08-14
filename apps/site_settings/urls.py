from django.urls import path
from . import views

urlpatterns = [
    path('', views.SiteSettingsView.as_view(), name='site-settings'),
]
