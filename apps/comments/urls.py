from django.urls import path
from apps.comments import views

app_name = "comments"

urlpatterns = [
    path("", views.list, name="list"),
    path("create/", views.create, name="create"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("templates/", views.templates, name="templates"),
]
