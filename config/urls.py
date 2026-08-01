"""
项目主 URL 配置
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from apps.accounts.media_views import protected_media


def root_redirect(request):
    """根路径根据登录状态重定向"""
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    return redirect("accounts:login")


urlpatterns = [
    # 根路径重定向
    path("", root_redirect, name="root"),
    # Admin 站点（开发调试用）
    path("admin/", admin.site.urls),
    # 账户管理
    path("accounts/", include("apps.accounts.urls")),
    # 工作台首页
    path("dashboard/", include("apps.dashboard.urls")),
    # 班级与学期
    path("classes/", include("apps.classes.urls")),
    # 学生管理
    path("students/", include("apps.students.urls")),
    # 座位管理
    path("seating/", include("apps.seating.urls")),
    # 值日管理
    path("duty/", include("apps.duty.urls")),
    # 考勤管理
    path("attendance/", include("apps.attendance.urls")),
    # 作业管理
    path("homework/", include("apps.homework.urls")),
    # 纪律管理
    path("discipline/", include("apps.discipline.urls")),
    # 宿舍管理
    path("dormitory/", include("apps.dormitory.urls")),
    # 奖励管理
    path("rewards/", include("apps.rewards.urls")),
    # 成绩管理
    path("scores/", include("apps.scores.urls")),
    # 评语管理
    path("comments/", include("apps.comments.urls")),
    # 沟通记录
    path("communications/", include("apps.communications.urls")),
    # 活动管理
    path("activities/", include("apps.activities.urls")),
    # 数据导出
    path("exports/", include("apps.exports.urls")),
    # 备份管理
    path("backups/", include("apps.backups.urls")),
    # 操作日志
    path("audit/", include("apps.audit.urls")),
    # 待办事项
    path("todos/", include("apps.todos.urls")),
    # 登录保护的上传附件
    path("protected-media/<path:path>", protected_media, name="protected_media"),
]

# 开发环境提供静态文件和媒体文件服务
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
