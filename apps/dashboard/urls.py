from django.urls import path
from apps.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    # 倒计时
    path("countdown/", views.countdown_list, name="countdown_list"),
    path("countdown/add/", views.countdown_add, name="countdown_add"),
    path("countdown/<int:pk>/edit/", views.countdown_edit, name="countdown_edit"),
    path("countdown/<int:pk>/delete/", views.countdown_delete, name="countdown_delete"),
    # 教学网站
    path("website/add/", views.website_add, name="website_add"),
    path("website/<int:pk>/delete/", views.website_delete, name="website_delete"),
    # 预警管理
    path("warnings/", views.warnings, name="warnings"),
    path("warnings/<int:pk>/", views.warning_detail, name="warning_detail"),
    path("warnings/rule/<int:pk>/delete/", views.warning_delete, name="warning_delete"),
    # API
    path("api/notifications/", views.api_notifications, name="api_notifications"),
]
