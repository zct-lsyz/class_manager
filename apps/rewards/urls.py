from django.urls import path
from apps.rewards import views

app_name = "rewards"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.reward_create, name="reward_create"),
    path("<int:pk>/edit/", views.reward_edit, name="reward_edit"),
    path("<int:pk>/delete/", views.reward_delete, name="reward_delete"),
    path("points/", views.points, name="points"),
    path("points/settings/", views.ranking_settings, name="ranking_settings"),
    path("rules/", views.rules, name="rules"),
    path("rules/<int:pk>/delete/", views.rule_delete, name="rule_delete"),
]
