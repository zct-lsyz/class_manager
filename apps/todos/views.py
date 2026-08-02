from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q

from apps.classes.decorators import require_current_class
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass
from apps.students.models import Student
from apps.todos.models import TodoItem


@login_required
def todo_list(request):
    """待办事项管理页面"""
    current_class = get_current_class(request.user)
    if not current_class:
        messages.info(request, "请先创建班级。")
        return redirect("classes:settings")

    # 未完成待办（按优先级、截止时间排序）
    active_todos = TodoItem.objects.filter(
        school_class=current_class, is_deleted=False, is_completed=False,
    ).select_related("student").order_by("priority", "deadline", "-created_at")

    # 已完成待办（最近完成在前）
    completed_todos = TodoItem.objects.filter(
        school_class=current_class, is_deleted=False, is_completed=True,
    ).select_related("student").order_by("-completed_at", "-created_at")[:50]

    # 学生列表（用于关联选择）
    students = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("student_id")

    # 筛选
    priority_filter = request.GET.get("priority", "")
    student_filter = request.GET.get("student", "")
    search = request.GET.get("search", "")

    if priority_filter:
        try:
            active_todos = active_todos.filter(priority=int(priority_filter))
        except (ValueError, TypeError):
            pass
    if student_filter:
        try:
            active_todos = active_todos.filter(student_id=int(student_filter))
        except (ValueError, TypeError):
            pass
    if search:
        active_todos = active_todos.filter(title__icontains=search)

    context = {
        "active_todos": active_todos,
        "completed_todos": completed_todos,
        "students": students,
        "priority_choices": TodoItem.PRIORITY_CHOICES,
        "filters": {
            "priority": priority_filter,
            "student": student_filter,
            "search": search,
        },
    }
    return render(request, "todos/todo_list.html", context)


@login_required
def todo_add(request):
    """添加待办项（支持弹窗提交和快速添加）"""
    current_class = get_current_class(request.user)
    if not current_class:
        messages.error(request, "请先创建班级，再添加待办。")
        return redirect("classes:settings")

    title = request.POST.get("title", "").strip()
    if not title:
        messages.error(request, "待办标题不能为空。")
        return redirect("todos:list")

    priority = request.POST.get("priority", "2")
    deadline_str = request.POST.get("deadline", "").strip()
    student_id = request.POST.get("student", "").strip()

    deadline = None
    if deadline_str:
        try:
            deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
            deadline = timezone.make_aware(deadline)
        except (ValueError, TypeError):
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%d")
                deadline = timezone.make_aware(deadline)
            except (ValueError, TypeError):
                pass

    todo = TodoItem.objects.create(
        school_class=current_class,
        created_by=request.user,
        title=title,
        priority=int(priority) if priority in ("1", "2", "3") else 2,
        deadline=deadline,
        student_id=int(student_id) if student_id else None,
    )
    messages.success(request, f"待办「{todo.title}」已添加。")
    return redirect(request.META.get("HTTP_REFERER", "todos:list"))


@login_required
def todo_toggle(request, pk):
    """切换完成状态"""
    current_class = get_current_class(request.user)
    todo = get_object_or_404(TodoItem, pk=pk, school_class=current_class, is_deleted=False)
    todo.is_completed = not todo.is_completed
    if todo.is_completed:
        todo.completed_at = timezone.now()
        status = "已完成"
    else:
        todo.completed_at = None
        status = "已恢复"
    todo.save(update_fields=["is_completed", "completed_at", "updated_at"])
    messages.info(request, f"待办「{todo.title}」标记为{status}。")
    return redirect(request.META.get("HTTP_REFERER", "todos:list"))


@login_required
def todo_delete(request, pk):
    """软删除待办"""
    current_class = get_current_class(request.user)
    todo = get_object_or_404(TodoItem, pk=pk, school_class=current_class, is_deleted=False)
    todo.is_deleted = True
    todo.save(update_fields=["is_deleted", "updated_at"])
    messages.info(request, f"待办「{todo.title}」已删除。")
    return redirect(request.META.get("HTTP_REFERER", "todos:list"))


@login_required
def todo_edit(request, pk):
    """编辑待办"""
    current_class = get_current_class(request.user)
    todo = get_object_or_404(TodoItem, pk=pk, school_class=current_class, is_deleted=False)
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if not title:
            messages.error(request, "标题不能为空。")
            return redirect("todos:list")

        todo.title = title
        priority = request.POST.get("priority", "2")
        todo.priority = int(priority) if priority in ("1", "2", "3") else 2

        deadline_str = request.POST.get("deadline", "").strip()
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, "%Y-%m-%dT%H:%M")
                todo.deadline = timezone.make_aware(deadline)
            except (ValueError, TypeError):
                todo.deadline = None
        else:
            todo.deadline = None

        student_id = request.POST.get("student", "").strip()
        todo.student_id = int(student_id) if student_id else None

        todo.save()
        messages.success(request, f"待办「{todo.title}」已更新。")
        return redirect("todos:list")

    return redirect("todos:list")
