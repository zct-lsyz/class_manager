from django.urls import path
from apps.homework import views

app_name = "homework"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.task_create, name="task_create"),
    path("<int:pk>/", views.task_detail, name="task_detail"),
    path("status-settings/", views.status_settings, name="status_settings"),
    path("status-settings/<int:pk>/delete/", views.status_delete, name="status_delete"),
]
