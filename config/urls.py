"""
URL configuration for Eng-Mart backend.
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.authentication.urls')),
    path('api/categories/', include('apps.categories.urls')),
    path('api/brands/', include('apps.brands.urls')),
    path('api/products/', include('apps.products.urls')),
    path('api/inquiries/', include('apps.inquiries.urls')),
    path('api/orders/', include('apps.orders.urls')),
    path('api/promo/', include('apps.orders.promo_urls')),
    path('api/banners/', include('apps.banners.urls')),
    path('api/settings/', include('apps.site_settings.urls')),
    path('api/quotations/', include('apps.quotations.urls')),
    path('api/account/', include('apps.orders.account_urls')),
    path('api/account/', include('apps.accounts.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Admin site customization
admin.site.site_header = 'Eng-Mart Administration'
admin.site.site_title = 'Eng-Mart Admin'
admin.site.index_title = 'Product Management'
