from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from apps.duty.models import DutyTask, DutyGroup, DutyRecord
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
            return redirect("duty:task_list")
    else:
        form = DutyTaskForm()

    context = {"tasks": tasks, "form": form}
    return render(request, "duty/task_list.html", context)


@login_required
def group_create(request):
    """创建值日小组"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = DutyGroupForm(request.POST)
        if form.is_valid():
            group = form.save(commit=False)
            group.school_class = current_class
            group.save()
            form.save_m2m()
            messages.success(request, f"小组「{group.name}」已创建。")
            return redirect("duty:index")
    else:
        form = DutyGroupForm()

    return render(request, "duty/group_form.html", {"form": form, "title": "创建值日小组"})


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
        return redirect("duty:group_detail", pk=group.pk)

    return render(request, "duty/group_detail.html", {
        "group": group, "members": members,
        "today": today, "today_map": today_map, "history": history,
    })
