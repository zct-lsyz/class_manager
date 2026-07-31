from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from apps.duty.models import DutyTask, DutyGroup, DutyRecord, DutyMemberTask
from apps.duty.forms import DutyTaskForm, DutyGroupForm, DutyRecordForm
from apps.classes.models import SchoolClass
from django.utils import timezone


@login_required
def index(request):
    """值日管理首页"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    groups = DutyGroup.objects.filter(
        school_class=current_class, is_active=True
    ).prefetch_related("members", "tasks") if current_class else []

    tasks = DutyTask.objects.filter(
        school_class=current_class, is_active=True
    ) if current_class else []

    context = {"groups": groups, "tasks": tasks}
    return render(request, "duty/index.html", context)


@login_required
def task_list(request):
    """值日任务配置"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    tasks = DutyTask.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        form = DutyTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.school_class = current_class
            task.save()
            messages.success(request, f"任务「{task.name}」已添加。")
            return redirect("duty:index")
    else:
        form = DutyTaskForm()

    context = {"tasks": tasks, "form": form}
    return render(request, "duty/task_list.html", context)


@login_required
def task_delete(request, pk):
    current_class = SchoolClass.objects.filter(is_current=True).first()
    task = get_object_or_404(DutyTask, pk=pk, school_class=current_class)
    if request.method == "POST":
        if task.duty_groups.exists() or task.member_assignments.exists():
            task.is_active = False
            task.save(update_fields=["is_active", "updated_at"])
            messages.info(request, "任务已有历史分配，已改为停用。")
        else:
            task.delete()
            messages.info(request, "值日任务已删除。")
    return redirect("duty:task_list")


@login_required
def group_create(request):
    """创建值日小组"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = DutyGroupForm(request.POST, current_class=current_class)
        if form.is_valid():
            group = form.save(commit=False)
            group.school_class = current_class
            group.save()
            form.save_m2m()
            messages.success(request, f"小组「{group.name}」已创建。")
            return redirect("duty:index")
    else:
        form = DutyGroupForm(current_class=current_class)

    return render(request, "duty/group_form.html", {"form": form, "title": "创建值日小组"})


@login_required
def group_edit(request, pk):
    """修改值日小组及每位成员的任务"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    group = get_object_or_404(DutyGroup, pk=pk, school_class=current_class)
    if request.method == "POST":
        form = DutyGroupForm(request.POST, instance=group, current_class=current_class)
        if form.is_valid():
            group = form.save()
            valid_tasks = {task.pk: task for task in group.tasks.all()}
            member_ids = set(group.members.values_list("pk", flat=True))
            DutyMemberTask.objects.filter(group=group).exclude(student_id__in=member_ids).delete()
            for student_id in member_ids:
                task_id = request.POST.get(f"task_{student_id}", "")
                if task_id.isdigit() and int(task_id) in valid_tasks:
                    DutyMemberTask.objects.update_or_create(
                        group=group, student_id=student_id,
                        defaults={"task": valid_tasks[int(task_id)]},
                    )
                else:
                    DutyMemberTask.objects.filter(group=group, student_id=student_id).delete()
            messages.success(request, f"小组「{group.name}」及成员任务已更新。")
            return redirect("duty:index")
    else:
        form = DutyGroupForm(instance=group, current_class=current_class)
    assignments = {item.student_id: item for item in DutyMemberTask.objects.filter(group=group)}
    return render(request, "duty/group_form.html", {
        "form": form, "title": "修改值日小组", "group": group,
        "members_for_tasks": group.members.all().order_by("student_id"),
        "tasks_for_assignment": group.tasks.all(), "assignments": assignments,
    })


@login_required
def group_detail(request, pk):
    """值日小组详情：成员值日记录录入"""
    group = get_object_or_404(
        DutyGroup.objects.prefetch_related("members", "tasks"), pk=pk,
    )
    members = group.members.all().order_by("student_id")
    today = timezone.localdate()

    # 当日记录
    today_records = DutyRecord.objects.filter(group=group, date=today).select_related("student")
    today_map = {r.student_id: r for r in today_records}

    # 历史记录
    history = DutyRecord.objects.filter(group=group).select_related("student").order_by("-date")[:50]

    # 批量登记当日值日
    if request.method == "POST":
        date = request.POST.get("date", str(today))
        from django.db import transaction as db_tx
        with db_tx.atomic():
            saved = 0
            for member in members:
                key = f"member_{member.pk}"
                val = request.POST.get(key, "")
                if not val:
                    continue
                is_completed = val in ("completed", "excellent", "good")
                is_absent = val == "absent"
                evaluation = ""
                if val == "excellent":
                    evaluation = "excellent"
                elif val == "good":
                    evaluation = "good"
                elif val == "poor":
                    evaluation = "poor"
                DutyRecord.objects.update_or_create(
                    group=group, date=date, student=member,
                    defaults={
                        "is_completed": is_completed,
                        "is_absent": is_absent,
                        "evaluation": evaluation,
                        "remark": request.POST.get(f"remark_{member.pk}", "").strip(),
                    },
                )
                saved += 1
        messages.success(request, f"已保存 {saved} 条值日记录。")
        return redirect("duty:index")

    return render(request, "duty/group_detail.html", {
        "group": group, "members": members,
        "today": today, "today_map": today_map, "history": history,
        "assignments": {
            item.student_id: item for item in DutyMemberTask.objects.filter(group=group).select_related("task")
        },
    })
