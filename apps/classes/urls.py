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
    # 班委名单
    path("committee/", views.committee_list, name="committee_list"),
    path("committee/role/create/", views.committee_role_create, name="committee_role_create"),
    path("committee/member/create/", views.committee_member_create, name="committee_member_create"),
    path("committee/member/<int:pk>/remove/", views.committee_member_remove, name="committee_member_remove"),
    # 学习小组
    path("study-groups/", views.study_groups, name="study_groups"),
    path("study-groups/create/", views.study_group_create, name="study_group_create"),
    path("study-groups/<int:pk>/delete/", views.study_group_delete, name="study_group_delete"),
    # 课程表
    path("course-schedule/", views.course_schedule, name="course_schedule"),
]
