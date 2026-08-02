from django.urls import path
from apps.scores import views
from apps.scores import support_views
from apps.scores import ai_views
from apps.scores import exam_analysis_views

app_name = "scores"

urlpatterns = [
    path("exams/", views.exam_list, name="exam_list"),
    path("exams/create/", views.exam_create, name="exam_create"),
    path("exams/<int:pk>/", views.exam_detail, name="exam_detail"),
    path("exams/<int:pk>/delete/", views.exam_delete, name="exam_delete"),
    path("exams/<int:pk>/subject/create/", views.exam_subject_create, name="exam_subject_create"),
    path("exams/subject/<int:pk>/delete/", views.exam_subject_delete, name="exam_subject_delete"),
    path("entry/", views.score_entry, name="score_entry"),
    path("entry/score/<int:pk>/delete/", views.score_delete, name="score_delete"),
    path("entry/import/", views.score_import, name="score_import"),
    path("entry/template/", views.score_import_template, name="score_import_template"),
    path("entry/import-wide/", views.score_import_wide, name="score_import_wide"),
    path("entry/template-wide/", views.score_import_wide_template, name="score_import_wide_template"),
    path("analysis/", views.analysis, name="analysis"),
    path("analysis/export/<str:fmt>/", views.analysis_export, name="analysis_export"),
    path("analysis/comparison/", views.comparison, name="comparison"),
    path("analysis/comparison/export/", views.comparison_export, name="comparison_export"),
    path("analysis/external/import/", views.external_import, name="external_import"),
    path("analysis/external/template/", views.external_import_template, name="external_import_template"),
    path("analysis/external/<int:pk>/delete/", views.external_delete, name="external_delete"),
    path("analysis/student/<int:pk>/", views.student_analysis_detail, name="student_analysis_detail"),
    path("analysis/student/<int:pk>/export/", views.student_analysis_export, name="student_analysis_export"),
    path("analysis/student/<int:pk>/export/<str:fmt>/", views.student_analysis_export, name="student_analysis_export"),
    path("analysis/students/", views.class_student_overview, name="class_student_overview"),
    path("analysis/grade-lines/<int:exam_id>/", views.grade_line_settings, name="grade_line_settings"),
    path("subjects/", views.subject_settings, name="subject_settings"),
    path("subjects/<int:pk>/edit/", views.subject_edit, name="subject_edit"),
    path("subjects/<int:pk>/delete/", views.subject_delete, name="subject_delete"),
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
    path("ai/exam-analysis/", exam_analysis_views.exam_analysis, name="exam_analysis"),
    path("ai/exam-analysis/template/", exam_analysis_views.score_template, name="exam_analysis_template"),
    path("ai/exam-analysis/<int:pk>/", exam_analysis_views.exam_analysis_detail, name="exam_analysis_detail"),
]
