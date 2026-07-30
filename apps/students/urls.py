from django.urls import path
from apps.students import views

app_name = "students"

urlpatterns = [
    # 学生
    path("", views.student_list, name="list"),
    path("create/", views.student_create, name="create"),
    path("<int:pk>/", views.student_detail, name="detail"),
    path("<int:pk>/edit/", views.student_edit, name="edit"),
    path("<int:pk>/delete/", views.student_delete, name="delete"),
    # 家长联系方式
    path("guardians/", views.guardian_list, name="guardian_list"),
    path("guardians/<int:pk>/edit/", views.guardian_edit, name="guardian_edit"),
    path("<int:student_pk>/guardian/create/", views.guardian_create, name="guardian_create"),
]
