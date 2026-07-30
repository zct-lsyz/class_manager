from django.urls import path
from apps.classes import views

app_name = "classes"

urlpatterns = [
    path("settings/", views.settings, name="settings"),
    path("class/create/", views.class_create, name="class_create"),
    path("class/<int:pk>/edit/", views.class_edit, name="class_edit"),
    path("semester/create/", views.semester_create, name="semester_create"),
    path("semester/<int:pk>/edit/", views.semester_edit, name="semester_edit"),
    path("semester/<int:pk>/archive/", views.semester_archive, name="semester_archive"),
    path("committee/", views.committee_list, name="committee_list"),
    path("study-groups/", views.study_groups, name="study_groups"),
    path("course-schedule/", views.course_schedule, name="course_schedule"),
]
