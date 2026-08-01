from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from apps.classes.models import SchoolClass, Semester
from apps.classes.utils import get_current_class


def require_current_class(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not SchoolClass.objects.filter(is_current=True, created_by=request.user).exists():
            messages.error(request, "请先创建班级。")
            return redirect("classes:settings")
        return view_func(request, *args, **kwargs)
    return wrapped


def require_current_semester(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        current_class = get_current_class(request.user)
        if not current_class:
            messages.error(request, "请先创建班级。")
            return redirect("classes:settings")
        if not Semester.objects.filter(school_class=current_class, is_current=True).exists():
            messages.error(request, "请先为当前班级指定当前学期。")
            return redirect("classes:settings")
        return view_func(request, *args, **kwargs)
    return wrapped
