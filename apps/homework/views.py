from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from apps.homework.models import HomeworkTask, HomeworkRecord, Subject, HomeworkStatus
from apps.homework.forms import HomeworkTaskForm, HomeworkRecordForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.students.models import Student


@login_required
def index(request):
    """作业检查首页"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    tasks = HomeworkTask.objects.filter(
        school_class=current_class
    ).select_related("subject").order_by("-assigned_date") if current_class else []

    paginator = Paginator(tasks, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    context = {"page_obj": page_obj, "title": "作业检查"}
    return render(request, "homework/index.html", context)


@login_required
@require_current_class
def task_create(request):
    """新建作业任务"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    if request.method == "POST":
        form = HomeworkTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.school_class = current_class
            task.semester = current_semester
            task.save()
            messages.success(request, f"作业「{task.title}」已创建。")
            return redirect("homework:index")
    else:
        form = HomeworkTaskForm()

    return render(request, "homework/task_form.html", {"form": form})


@login_required
@require_current_class
def task_edit(request, pk):
    """修改作业任务内容"""
    current_class = get_current_class(request.user)
    task = get_object_or_404(
        HomeworkTask.objects.select_related("subject"),
        pk=pk, school_class=current_class,
    )
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    if request.method == "POST":
        form = HomeworkTaskForm(request.POST, instance=task)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.school_class = current_class
            updated.semester = current_semester
            updated.save()
            from apps.audit.models import OperationLog
            OperationLog.objects.create(
                user=request.user, action="edit", module="homework",
                object_repr=updated.title, detail="修改作业内容",
                ip_address=request.META.get("REMOTE_ADDR", ""), success=True,
            )
            messages.success(request, f"作业「{updated.title}」已更新。")
            return redirect("homework:task_detail", pk=task.pk)
    else:
        form = HomeworkTaskForm(instance=task)

    return render(request, "homework/task_form.html", {"form": form, "task": task})


@login_required
@require_current_class
def task_delete(request, pk):
    """删除作业任务（连带其完成记录）"""
    current_class = get_current_class(request.user)
    task = get_object_or_404(
        HomeworkTask, pk=pk, school_class=current_class,
    )
    if request.method == "POST":
        title = task.title
        record_count = task.records.count()
        task.delete()
        from apps.audit.models import OperationLog
        OperationLog.objects.create(
            user=request.user, action="delete", module="homework",
            object_repr=title, detail=f"删除作业，连带 {record_count} 条完成记录",
            ip_address=request.META.get("REMOTE_ADDR", ""), success=True,
        )
        messages.info(request, f"作业「{title}」已删除（含 {record_count} 条完成记录）。")
        return redirect("homework:index")
    messages.error(request, "请通过删除按钮确认删除。")
    return redirect("homework:task_detail", pk=task.pk)


@login_required
def task_detail(request, pk):
    """作业任务详情及完成情况"""
    current_class = get_current_class(request.user)
    task = get_object_or_404(
        HomeworkTask.objects.select_related("subject"),
        pk=pk, school_class=current_class,
    )
    records = HomeworkRecord.objects.filter(task=task).select_related("student").order_by("student__student_id")

    # 未登记学生
    recorded_ids = records.values_list("student_id", flat=True)
    unrecorded = Student.objects.filter(
        school_class=task.school_class, is_deleted=False
    ).exclude(id__in=recorded_ids)

    # 批量登记作业状态（POST record_{student_id}）
    if request.method == "POST":
        from django.db import transaction as db_tx
        with db_tx.atomic():
            saved = 0
            batch_status = request.POST.get("batch_status", "")
            batch_student_ids = request.POST.getlist("batch_students")
            valid_statuses = {value for value, _label in HomeworkRecord.STATUS_CHOICES}
            valid_statuses.update(
                f"custom:{status.pk}" for status in HomeworkStatus.objects.filter(
                    school_class=task.school_class, is_active=True,
                )
            )
            if batch_status in valid_statuses:
                batch_students = Student.objects.filter(
                    pk__in=batch_student_ids, school_class=task.school_class, is_deleted=False,
                )
                for student in batch_students:
                    HomeworkRecord.objects.update_or_create(
                        task=task, student=student,
                        defaults={
                            "status": batch_status,
                            "submission_date": timezone.localdate()
                            if batch_status in ("submitted", "excellent") else None,
                        },
                    )
                    saved += 1
            for key, value in request.POST.items():
                if not key.startswith("record_"):
                    continue
                student_id = key.replace("record_", "")
                if not student_id.isdigit() or not value:
                    continue
                status = request.POST.get(f"status_{student_id}", value or "submitted")
                if status not in valid_statuses:
                    continue
                HomeworkRecord.objects.update_or_create(
                    task=task, student_id=int(student_id),
                    defaults={
                        "status": status,
                        "submission_date": timezone.localdate() if status == "submitted" else None,
                    },
                )
                saved += 1
        from apps.audit.models import OperationLog
        OperationLog.objects.create(
            user=request.user, action="edit", module="homework",
            object_repr=task.title, detail=f"登记作业完成状态 {saved} 人",
            ip_address=request.META.get("REMOTE_ADDR", ""), success=True,
        )
        messages.success(request, f"已登记 {saved} 名学生的作业状态。")
        return redirect("homework:task_detail", pk=task.pk)

    custom_statuses = HomeworkStatus.objects.filter(
        school_class=task.school_class, is_active=True
    ).order_by("sort_order", "name")
    status_options = list(HomeworkRecord.STATUS_CHOICES) + [
        (f"custom:{status.pk}", status.name) for status in custom_statuses
    ]
    context = {
        "task": task,
        "records": records,
        "unrecorded": unrecorded,
        "all_students": Student.objects.filter(
            school_class=task.school_class, is_deleted=False,
        ).order_by("student_id"),
        "status_options": status_options,
    }
    return render(request, "homework/task_detail.html", context)


@login_required
@require_current_class
def status_settings(request):
    """作业状态设置"""
    current_class = get_current_class(request.user)
    statuses = HomeworkStatus.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        from apps.homework.forms import HomeworkStatusForm
        form = HomeworkStatusForm(request.POST)
        if form.is_valid():
            s = form.save(commit=False)
            s.school_class = current_class
            s.save()
            messages.success(request, f"状态「{s.name}」已添加。")
            return redirect("homework:status_settings")

    context = {"statuses": statuses}
    return render(request, "homework/status_settings.html", context)


@login_required
def status_delete(request, pk):
    current_class = get_current_class(request.user)
    status = get_object_or_404(HomeworkStatus, pk=pk, school_class=current_class)
    if request.method == "POST":
        if HomeworkRecord.objects.filter(status=f"custom:{status.pk}").exists():
            status.is_active = False
            status.save(update_fields=["is_active", "updated_at"])
            messages.info(request, "状态已有历史记录，已停用并保留原状态。")
        else:
            status.delete()
            messages.info(request, "作业状态已删除。")
    return redirect("homework:status_settings")
