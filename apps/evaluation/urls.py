from django.urls import path
from apps.evaluation import views

app_name = "evaluation"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.project_create, name="project_create"),
    path("<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("<int:pk>/delete/", views.project_delete, name="project_delete"),
    path("<int:pk>/calculate/", views.calculate, name="calculate"),
    path("<int:pk>/history/", views.history, name="history"),
]
