from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from apps.classes.models import SchoolClass, Semester


def require_current_class(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not SchoolClass.objects.filter(is_current=True).exists():
            messages.error(request, "请先在班级与学期设置中指定当前班级。")
            return redirect("classes:settings")
        return view_func(request, *args, **kwargs)
    return wrapped


def require_current_semester(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        current_class = SchoolClass.objects.filter(is_current=True).first()
        if not current_class:
            messages.error(request, "请先在班级与学期设置中指定当前班级。")
            return redirect("classes:settings")
        if not Semester.objects.filter(school_class=current_class, is_current=True).exists():
            messages.error(request, "请先为当前班级指定当前学期。")
            return redirect("classes:settings")
        return view_func(request, *args, **kwargs)
    return wrapped
