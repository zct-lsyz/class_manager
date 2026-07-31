from django.urls import path
from apps.attendance import views

app_name = "attendance"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create, name="create"),
]
