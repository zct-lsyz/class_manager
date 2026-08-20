from django.urls import path
from apps.duty import views

app_name = "duty"

urlpatterns = [
    path("", views.index, name="index"),
    path("export/", views.export, name="export"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("group/create/", views.group_create, name="group_create"),
    path("group/<int:pk>/edit/", views.group_edit, name="group_edit"),
    path("group/<int:pk>/", views.group_detail, name="group_detail"),
    # 智能值日
    path("smart/", views.smart_duty, name="smart_duty"),
    path("smart/generate/", views.smart_duty_generate, name="smart_duty_generate"),
    path("smart/<int:pk>/adjust/", views.smart_duty_adjust, name="smart_duty_adjust"),
    path("smart/<int:pk>/finalize/", views.smart_duty_finalize, name="smart_duty_finalize"),
    path("smart/<int:pk>/activate/", views.smart_duty_activate, name="smart_duty_activate"),
    path("smart/<int:pk>/archive/", views.smart_duty_archive, name="smart_duty_archive"),
    path("smart/<int:pk>/print/", views.smart_duty_print, name="smart_duty_print"),
    path("smart/<int:pk>/export/", views.smart_duty_export, name="smart_duty_export"),
    path("smart/history/", views.smart_duty_history, name="smart_duty_history"),
    # 缺勤记录
    path("absence/", views.duty_absence_list, name="absence_list"),
    path("absence/add/", views.duty_absence_add, name="absence_add"),
    path("absence/<int:pk>/points/", views.duty_absence_update_points, name="absence_update_points"),
    path("absence/<int:pk>/delete/", views.duty_absence_delete, name="absence_delete"),
    # 方案小组组长 / 修改当天小组
    path("roster/<int:pk>/set-leader/", views.duty_set_leader, name="set_leader"),
    path("roster/<int:pk>/update-day/", views.duty_update_day, name="update_day"),
]
