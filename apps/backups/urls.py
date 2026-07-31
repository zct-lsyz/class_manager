from django.urls import path
from apps.backups import views

app_name = "backups"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create_backup_view, name="create_backup"),
    path("<int:pk>/download/", views.download_backup, name="download"),
    path("<int:pk>/delete/", views.delete_backup, name="delete"),
    path("<int:pk>/restore/", views.restore_view, name="restore"),
]
