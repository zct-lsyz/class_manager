from django.urls import path
from apps.seating import views

app_name = "seating"

urlpatterns = [
    path("", views.index, name="index"),
    path("layout/", views.layout_settings, name="layout"),
    path("plan/create/", views.plan_create, name="plan_create"),
    path("plan/<int:pk>/activate/", views.plan_activate, name="plan_activate"),
    path("save/", views.save_plan, name="save_plan"),
    path("auto-arrange/", views.auto_arrange, name="auto_arrange"),
]
