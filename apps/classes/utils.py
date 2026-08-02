"""班级工具函数"""
from django.contrib import messages
from django.shortcuts import redirect

from apps.classes.models import SchoolClass


def get_current_class(user):
    """获取当前用户的当前班级（多租户隔离）"""
    if not user or not user.is_authenticated:
        return None
    return SchoolClass.objects.filter(is_current=True, created_by=user).first()


def require_current_class_or_redirect(request):
    """获取当前用户的班级；若无班级则返回重定向到班级设置页。

    返回 (current_class, redirect_response)。redirect_response 为 None 表示一切正常。
    用法：
        current_class, redir = require_current_class_or_redirect(request)
        if redir:
            return redir
    """
    cls = get_current_class(request.user)
    if not cls:
        messages.warning(request, "请先创建班级，再使用各功能模块。")
        return None, redirect("classes:settings")
    return cls, None
