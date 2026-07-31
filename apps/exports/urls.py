from django.urls import path
from apps.exports import views

app_name = "exports"

urlpatterns = [
    path("", views.export_center, name="export_center"),
    path("module/<str:module>/", views.export_module, name="export_module"),
    path("full-export/", views.full_export, name="full_export"),
    path("import/", views.import_data, name="import_data"),
    path("import/template/<str:template_type>/", views.template_download, name="template_download"),
]
