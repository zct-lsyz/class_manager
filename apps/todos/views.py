from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone

from apps.classes.decorators import require_current_class
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass
from apps.todos.models import TodoItem


@login_required
@require_current_class
def todo_add(request):
    """添加待办项"""
    title = request.POST.get("title", "").strip()
    deadline_str = request.POST.get("deadline", "").strip()
    if not title:
        messages.error(request, "待办标题不能为空")
        return redirect("dashboard:index")
    deadline = None
    if deadline_str:
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
            deadline = timezone.make_aware(deadline)
        except (ValueError, TypeError):
            deadline = None
    cls = get_current_class(request.user)
    TodoItem.objects.create(
        school_class=cls, created_by=request.user, title=title, deadline=deadline,
    )
    return redirect("dashboard:index")


@login_required
@require_current_class
def todo_toggle(request, pk):
    """切换完成状态"""
    item = get_object_or_404(TodoItem, pk=pk, is_deleted=False)
    item.is_completed = not item.is_completed
    item.save()
    return redirect("dashboard:index")


@login_required
@require_current_class
def todo_delete(request, pk):
    """软删除待办"""
    item = get_object_or_404(TodoItem, pk=pk, is_deleted=False)
    item.is_deleted = True
    item.save()
    return redirect("dashboard:index")
