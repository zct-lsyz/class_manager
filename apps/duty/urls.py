from django.urls import path
from apps.duty import views

app_name = "duty"

urlpatterns = [
    path("", views.index, name="index"),
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
]
