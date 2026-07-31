from django.urls import path
from apps.activities import views

app_name = "activities"

urlpatterns = [
    path("class-meetings/", views.class_meetings, name="class_meetings"),
    path("class-meetings/create/", views.class_meeting_create, name="class_meeting_create"),
    path("activities/", views.activities, name="activities"),
    path("activities/create/", views.activity_create, name="activity_create"),
    path("activities/<int:pk>/delete/", views.activity_delete, name="activity_delete"),
    path("culture/", views.culture, name="culture"),
    path("culture/create/", views.culture_create, name="culture_create"),
]
