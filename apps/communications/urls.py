from django.urls import path
from apps.communications import views

app_name = "communications"

urlpatterns = [
    path("conversations/", views.conversations, name="conversations"),
    path("conversations/create/", views.conversation_create, name="conversation_create"),
    path("conversations/<int:pk>/delete/", views.conversation_delete, name="conversation_delete"),
    path("home-school/", views.home_school, name="home_school"),
    path("home-school/create/", views.home_school_create, name="home_school_create"),
    path("concerns/", views.concerns, name="concerns"),
    path("concerns/create/", views.concern_create, name="concern_create"),
    path("concerns/<int:pk>/", views.concern_detail, name="concern_detail"),
    path("concerns/<int:pk>/update/", views.concern_update, name="concern_update"),
]
