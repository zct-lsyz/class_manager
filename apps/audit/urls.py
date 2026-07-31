from django.urls import path
from apps.audit import views

app_name = "audit"

urlpatterns = [
    path("logs/", views.log_list, name="log_list"),
    path("trash/", views.trash_list, name="trash_list"),
    path("trash/<int:pk>/restore/", views.trash_restore, name="trash_restore"),
    path("trash/<int:pk>/delete/", views.trash_delete, name="trash_delete"),
]
