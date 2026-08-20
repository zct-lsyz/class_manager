from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from apps.homework.models import HomeworkTask, HomeworkRecord, Subject, HomeworkStatus
from apps.homework.forms import HomeworkTaskForm, HomeworkRecordForm
from apps.todos.services import sync_follow_up_todo, remove_follow_up_todo
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
            sync_follow_up_todo(task, request.user)
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
            sync_follow_up_todo(updated, request.user)
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
        remove_follow_up_todo(task)
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


def _sync_homework_points(record):
    """作业完成状态同步到统一积分（source_type=homework）。

    优先使用该班级配置的作业积分规则（HomeworkPointRule），未配置则用内置默认。
    """
    from apps.rewards.services import sync_source_point
    from apps.homework.services import get_status_points
    points = get_status_points(record.task.school_class, record.status)
    sync_source_point(
        student=record.student, school_class=record.task.school_class,
        semester=record.task.semester,
        date=record.submission_date or record.task.assigned_date,
        points=points,
        reason=f"作业：{record.task.title}（{record.status_display}）",
        source_type="homework", source_id=record.pk,
    )


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

    # 修改「未交 / 完成差」扣分（并重新同步积分）
    if request.method == "POST" and request.POST.get("action") == "save_points":
        from apps.homework.models import HomeworkPointRule
        configs = {"unsubmitted": "未交", "poor": "完成差"}
        for status, label in configs.items():
            raw = request.POST.get(f"points_{status}", "").strip()
            if raw == "":
                HomeworkPointRule.objects.filter(
                    school_class=task.school_class, status=status,
                ).delete()
                continue
            try:
                value = abs(int(raw))
            except (ValueError, TypeError):
                continue
            HomeworkPointRule.objects.update_or_create(
                school_class=task.school_class, status=status,
                defaults={"points": value, "is_add": False},
            )
        # 重新同步本班所有相关状态记录到积分管理
        affected = HomeworkRecord.objects.filter(
            task__school_class=task.school_class, status__in=list(configs),
        )
        resynced = 0
        for record in affected:
            _sync_homework_points(record)
            resynced += 1
        messages.success(
            request,
            f"扣分设置已更新，并重新同步 {resynced} 条作业记录到积分管理。",
        )
        return redirect("homework:task_detail", pk=task.pk)

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
                    record, _ = HomeworkRecord.objects.update_or_create(
                        task=task, student=student,
                        defaults={
                            "status": batch_status,
                            "submission_date": timezone.localdate()
                            if batch_status in ("submitted", "excellent") else None,
                        },
                    )
                    _sync_homework_points(record)
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
                record, _ = HomeworkRecord.objects.update_or_create(
                    task=task, student_id=int(student_id),
                    defaults={
                        "status": status,
                        "submission_date": timezone.localdate() if status == "submitted" else None,
                    },
                )
                _sync_homework_points(record)
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
    from apps.homework.services import get_status_points
    context = {
        "task": task,
        "records": records,
        "unrecorded": unrecorded,
        "all_students": Student.objects.filter(
            school_class=task.school_class, is_deleted=False,
        ).order_by("name_pinyin", "name", "student_id"),
        "status_options": status_options,
        "unsubmitted_points": get_status_points(task.school_class, "unsubmitted"),
        "poor_points": get_status_points(task.school_class, "poor"),
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


@login_required
@require_current_class
def point_rules(request):
    """作业状态积分规则：为各完成状态自定义加分/扣分（分数恒为正）。"""
    from apps.homework.models import HomeworkPointRule
    current_class = get_current_class(request.user)
    rules = {r.status: r for r in HomeworkPointRule.objects.filter(school_class=current_class)}

    if request.method == "POST":
        for status, _label in HomeworkRecord.STATUS_CHOICES:
            raw = request.POST.get(f"points_{status}", "").strip()
            if raw == "":
                HomeworkPointRule.objects.filter(
                    school_class=current_class, status=status,
                ).delete()
                continue
            try:
                value = int(raw)
            except (ValueError, TypeError):
                continue
            is_add = request.POST.get(f"is_add_{status}") == "on"
            if value < 0:
                value = abs(value)
                is_add = False
            HomeworkPointRule.objects.update_or_create(
                school_class=current_class, status=status,
                defaults={"points": value, "is_add": is_add},
            )
        messages.success(request, "作业积分规则已保存（未填写的状态不参与加减分）。")
        return redirect("homework:point_rules")

    return render(request, "homework/point_rules.html", {
        "status_choices": HomeworkRecord.STATUS_CHOICES,
        "rules": rules,
    })
