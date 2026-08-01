from django.urls import path
from apps.todos import views

app_name = "todos"

urlpatterns = [
    path("add/", views.todo_add, name="add"),
    path("<int:pk>/toggle/", views.todo_toggle, name="toggle"),
    path("<int:pk>/delete/", views.todo_delete, name="delete"),
]
