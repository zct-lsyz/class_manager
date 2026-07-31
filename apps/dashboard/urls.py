from django.urls import path
from apps.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.index, name="index"),
    path("warnings/", views.warnings, name="warnings"),
    path("warnings/<int:pk>/", views.warning_detail, name="warning_detail"),
    path("warnings/rule/<int:pk>/delete/", views.warning_delete, name="warning_delete"),
]
