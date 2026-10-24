from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from api import admin_dashboard

urlpatterns = [
    # Custom admin analytics dashboards. Must precede the admin include so the
    # specific paths win over ``admin.site.urls``.
    path(
        "admin/dashboard/payments/",
        admin_dashboard.payments_dashboard,
        name="admin_payments_dashboard",
    ),
    path(
        "admin/dashboard/balance-edits/",
        admin_dashboard.balance_edits_dashboard,
        name="admin_balance_edits_dashboard",
    ),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)