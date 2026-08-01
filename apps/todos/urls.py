from django.urls import path
from apps.todos import views

app_name = "todos"

urlpatterns = [
    path("", views.todo_list, name="list"),
    path("add/", views.todo_add, name="add"),
    path("<int:pk>/toggle/", views.todo_toggle, name="toggle"),
    path("<int:pk>/edit/", views.todo_edit, name="edit"),
    path("<int:pk>/delete/", views.todo_delete, name="delete"),
]
