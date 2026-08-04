from django.urls import path

from apps.mobile_api import account_views, ai_views, backup_views, module_views, resources


app_name = "mobile_api"

urlpatterns = [
    path("auth/login/", account_views.login, name="login"),
    path("auth/verify/", account_views.verify, name="verify"),
    path("auth/logout/", account_views.logout, name="logout"),
    path("account/profile/", account_views.profile, name="profile"),
    path("account/password/", account_views.change_password, name="change_password"),
    path("account/devices/", account_views.devices, name="devices"),
    path("account/devices/<int:pk>/", account_views.device_detail, name="device_detail"),
    path("account/delete/", account_views.delete_account, name="delete_account"),
    path("push/device/", account_views.push_device, name="push_device"),

    path("dashboard/", module_views.dashboard, name="dashboard"),
    path("course-schedule/", module_views.course_schedule, name="course_schedule"),
    path("seating/", module_views.seating, name="seating"),
    path("duty-roster/", module_views.duty_roster, name="duty_roster"),
    path("warnings/", module_views.warnings, name="warnings"),
    path("growth/", module_views.growth, name="growth"),
    path("student-profile/", module_views.student_profile, name="student_profile"),
    path("ranking/", module_views.ranking, name="ranking"),
    path("score-analysis/", module_views.score_analysis, name="score_analysis"),
    path("score-comparison/", module_views.score_comparison, name="score_comparison"),
    path("student-score-analysis/", module_views.selected_student_score_analysis, name="selected_student_score_analysis"),
    path("attendance-stats/", module_views.attendance_stats, name="attendance_stats"),
    path("homework-stats/", module_views.homework_stats, name="homework_stats"),
    path("discipline-stats/", module_views.discipline_stats, name="discipline_stats"),
    path("dormitory-stats/", module_views.dormitory_stats, name="dormitory_stats"),
    path("reward-stats/", module_views.reward_stats, name="reward_stats"),
    path("notifications/", module_views.notifications, name="notifications"),
    path("batch/<slug:resource>/", module_views.batch_create, name="batch_create"),
    path("dorm-beds/<int:pk>/assign/", module_views.assign_bed, name="assign_bed"),
    path("dormitory/", module_views.dorm_overview, name="dorm_overview"),
    path("dormitory/rooms/<int:pk>/monitor/", module_views.set_room_monitor, name="set_room_monitor"),
    path("dormitory/hygiene/<int:pk>/scores/", module_views.hygiene_scores, name="hygiene_scores"),
    path("students/<int:pk>/score-analysis/", module_views.student_score_analysis, name="student_score_analysis"),
    path("ai-analysis/", ai_views.analysis, name="ai_analysis"),
    path("exam-paper-analysis/", ai_views.exam_paper_analysis, name="exam_paper_analysis"),

    path("backups/", backup_views.backups, name="backups"),
    path("backups/<int:pk>/", backup_views.backup_detail, name="backup_detail"),
    path("backups/<int:pk>/download/", backup_views.backup_download, name="backup_download"),
    path("backups/<int:pk>/restore/", backup_views.backup_restore, name="backup_restore"),
    path("media-archives/", backup_views.media_archives, name="media_archives"),
    path("media-archives/import/", backup_views.media_archive_import, name="media_archive_import"),
    path("media-archives/<int:pk>/download/", backup_views.media_archive_download, name="media_archive_download"),
    path("media-archives/<int:pk>/clear/", backup_views.media_archive_clear, name="media_archive_clear"),
    path("storage/check/", backup_views.storage_check, name="storage_check"),

    path("schemas/", resources.schemas, name="schemas"),
    path("resources/<slug:resource>/", resources.resource_list, name="resource_list"),
    path("resources/<slug:resource>/<int:pk>/", resources.resource_detail, name="resource_detail"),
]
