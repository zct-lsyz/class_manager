from django.urls import path
from apps.duty import views

app_name = "duty"

urlpatterns = [
    path("", views.index, name="index"),
    path("tasks/", views.task_list, name="task_list"),
    path("group/create/", views.group_create, name="group_create"),
    path("group/<int:pk>/edit/", views.group_edit, name="group_edit"),
    path("group/<int:pk>/", views.group_detail, name="group_detail"),
]
