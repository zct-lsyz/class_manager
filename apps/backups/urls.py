from django.urls import path
from apps.backups import views

app_name = "backups"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create_backup_view, name="create_backup"),
    path("<int:pk>/download/", views.download_backup, name="download"),
    path("<int:pk>/delete/", views.delete_backup, name="delete"),
    path("<int:pk>/restore/", views.restore_view, name="restore"),
    path("storage/", views.storage_center, name="storage_center"),
    path("storage/check/", views.storage_check_now, name="storage_check_now"),
    path("storage/rules/<int:pk>/delete/", views.storage_rule_delete, name="storage_rule_delete"),
    path("storage/archive/create/", views.media_archive_create, name="media_archive_create"),
    path("storage/archive/import/", views.media_archive_import, name="media_archive_import"),
    path("storage/archive/<int:pk>/download/", views.media_archive_download, name="media_archive_download"),
    path("storage/archive/<int:pk>/clear/", views.media_archive_clear, name="media_archive_clear"),
]
