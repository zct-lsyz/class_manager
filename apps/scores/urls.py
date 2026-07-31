from django.urls import path
from apps.scores import views
from apps.scores import support_views
from apps.scores import ai_views

app_name = "scores"

urlpatterns = [
    path("exams/", views.exam_list, name="exam_list"),
    path("exams/create/", views.exam_create, name="exam_create"),
    path("exams/<int:pk>/", views.exam_detail, name="exam_detail"),
    path("exams/<int:pk>/subject/create/", views.exam_subject_create, name="exam_subject_create"),
    path("exams/subject/<int:pk>/delete/", views.exam_subject_delete, name="exam_subject_delete"),
    path("entry/", views.score_entry, name="score_entry"),
    path("entry/import/", views.score_import, name="score_import"),
    path("entry/template/", views.score_import_template, name="score_import_template"),
    path("analysis/", views.analysis, name="analysis"),
    path("subjects/", views.subject_settings, name="subject_settings"),
    # 培优补差
    path("support/", support_views.support_list, name="support_list"),
    path("support/create/", support_views.support_create, name="support_create"),
    path("support/candidates/", support_views.support_candidates, name="support_candidates"),
    path("support/<int:pk>/", support_views.support_detail, name="support_detail"),
    path("support/<int:pk>/close/", support_views.support_close, name="support_close"),
    # AI 成绩分析
    path("ai/settings/", ai_views.ai_settings, name="ai_settings"),
    path("ai/generate/", ai_views.ai_generate, name="ai_generate"),
    path("ai/records/", ai_views.ai_records, name="ai_records"),
    path("ai/records/<int:pk>/", ai_views.ai_record_detail, name="ai_record_detail"),
]
