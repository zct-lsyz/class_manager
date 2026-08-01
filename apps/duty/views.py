import io
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from apps.audit.models import OperationLog
from apps.classes.decorators import require_current_class
from apps.classes.models import SchoolClass, Semester
from apps.duty.forms import DutyTaskForm, DutyGroupForm, DutyRecordForm
from apps.duty.models import (
    DutyTask,
    DutyGroup,
    DutyRecord,
    DutyMemberTask,
    DutyRoster,
    DutyRosterTask,
    DutyRosterEntry,
)
from apps.duty.services import (
    generate_duty_roster,
    get_day_dates,
    build_roster_text,
)


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


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
@require_current_class
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
@require_current_class
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


# ============ 智能值日 ============

def _current_class(request):
    return SchoolClass.objects.filter(is_current=True).first()


def _get_roster_or_404(request, pk):
    current_class = _current_class(request)
    return get_object_or_404(DutyRoster, pk=pk, school_class=current_class)


def _log_operation(request, action, obj_repr, detail):
    OperationLog.objects.create(
        user=request.user, action=action, module="duty",
        object_repr=obj_repr, detail=detail,
        ip_address=get_client_ip(request), success=True,
    )


def _roster_grid(roster):
    """构建值日表二维网格数据：每天 × 每任务的已分配学生。"""
    roster_tasks = list(
        DutyRosterTask.objects.filter(roster=roster)
        .select_related("task").order_by("sort_order", "pk")
    )
    entries = list(
        DutyRosterEntry.objects.filter(roster=roster)
        .select_related("student", "task")
        .order_by("day_index", "task__sort_order", "sort_order")
    )
    cell_map = defaultdict(list)
    for entry in entries:
        cell_map[(entry.day_index, entry.task_id)].append(entry)
    dates = get_day_dates(roster.date_start, roster.day_count)
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    days = []
    for day in range(roster.day_count):
        date_obj = dates[day] if day < len(dates) else None
        date_label = ""
        if date_obj:
            date_label = f"{date_obj.month}月{date_obj.day}日 周{weekdays[date_obj.weekday()]}"
        tasks = []
        for rt in roster_tasks:
            cell_entries = cell_map.get((day, rt.task_id), [])
            tasks.append({
                "rt": rt,
                "task": rt.task,
                "max_count": rt.people_count,
                "students": [e.student for e in cell_entries],
                "entry_ids": {e.student_id: e.pk for e in cell_entries},
            })
        days.append({
            "day_index": day,
            "date_label": date_label,
            "tasks": tasks,
        })
    return days, roster_tasks


@login_required
@require_current_class
def smart_duty(request):
    """智能值日 Step 1：配置任务与人数。"""
    current_class = _current_class(request)
    tasks = DutyTask.objects.filter(school_class=current_class, is_active=True)
    students = list(current_class.students.filter(is_deleted=False))
    today = timezone.localdate()

    if request.method == "POST":
        name = request.POST.get("name", "").strip() or f"第{today.isocalendar().week}周值日表"
        date_start = request.POST.get("date_start", "") or str(today)
        day_count = int(request.POST.get("day_count") or 5)
        names = request.POST.getlist("names[]")
        counts = request.POST.getlist("counts[]")
        task_pks = request.POST.getlist("task_pks[]")

        tasks_with_count = []
        for i in range(len(names)):
            task_name = (names[i] if i < len(names) else "").strip()
            try:
                count = max(1, int(counts[i] if i < len(counts) else 1))
            except (TypeError, ValueError):
                count = 1
            if not task_name:
                continue
            tasks_with_count.append((task_name, count, task_pks[i] if i < len(task_pks) else ""))

        if not tasks_with_count:
            messages.error(request, "请至少配置一项值日任务。")
            return redirect("duty:smart_duty")

        total_needed = sum(count for _, count, _ in tasks_with_count)
        if total_needed > len(students):
            messages.error(request, f"每天所需总人数（{total_needed}）超过班级人数（{len(students)}），请减少任务或人数。")
            return redirect("duty:smart_duty")

        semester = Semester.objects.filter(school_class=current_class, is_current=True).first()
        dates = get_day_dates(date_start, day_count)

        with transaction.atomic():
            roster = DutyRoster.objects.create(
                school_class=current_class, semester=semester,
                name=name, date_start=dates[0] if dates else today,
                date_end=dates[-1] if dates else today,
                day_count=day_count, status="draft",
                created_by=request.user, is_current=False,
            )
            for sort_order, (task_name, count, task_pk) in enumerate(tasks_with_count):
                task = None
                if task_pk:
                    task = DutyTask.objects.filter(
                        pk=task_pk, school_class=current_class, is_active=True,
                    ).first()
                if task is None:
                    task = DutyTask.objects.create(
                        school_class=current_class, name=task_name,
                        default_people_count=count, sort_order=sort_order,
                    )
                DutyRosterTask.objects.create(
                    roster=roster, task=task, people_count=count, sort_order=sort_order,
                )
            request.session["smart_duty_roster_id"] = roster.pk
        _log_operation(request, "create", roster.name, f"创建智能值日方案，共 {len(tasks_with_count)} 项任务，{day_count} 天")
        return redirect("duty:smart_duty_generate")

    context = {
        "tasks": tasks,
        "student_count": len(students),
        "today": today,
    }
    return render(request, "duty/smart_duty.html", context)


@login_required
@require_current_class
def smart_duty_generate(request):
    """智能值日 Step 2：自动生成排班。"""
    current_class = _current_class(request)
    roster_id = request.session.get("smart_duty_roster_id")
    roster = None
    if roster_id:
        roster = DutyRoster.objects.filter(pk=roster_id, school_class=current_class).first()

    if request.method == "POST":
        # 重新生成
        if roster is None:
            return redirect("duty:smart_duty")
        with transaction.atomic():
            DutyRosterEntry.objects.filter(roster=roster).delete()
            _run_generation(roster, current_class)
        _log_operation(request, "edit", roster.name, "重新生成值日排班")
        return redirect("duty:smart_duty_generate")

    if roster is None:
        messages.info(request, "请先配置任务再自动生成。")
        return redirect("duty:smart_duty")

    # GET 时若尚无排班记录，则自动执行生成
    if not DutyRosterEntry.objects.filter(roster=roster).exists():
        with transaction.atomic():
            _run_generation(roster, current_class)
        _log_operation(request, "create", roster.name, "自动生成值日排班")

    stats = _get_roster_stats(roster)
    return render(request, "duty/smart_duty_generate.html", {
        "roster": roster, "stats": stats,
    })


def _run_generation(roster, current_class):
    """执行公平轮值算法并写入 DutyRosterEntry。"""
    from apps.students.models import Student
    students = list(Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("sort_order", "student_id"))
    roster_tasks = list(DutyRosterTask.objects.filter(roster=roster).order_by("sort_order", "pk"))
    tasks_with_counts = [(rt.task_id, rt.people_count) for rt in roster_tasks]
    result = generate_duty_roster(students, tasks_with_counts, roster.day_count, current_class)
    entries = []
    for day, day_plan in result.items():
        for rt in roster_tasks:
            for sort_order, student in enumerate(day_plan.get(rt.task_id, [])):
                entries.append(DutyRosterEntry(
                    roster=roster, task_id=rt.task_id, student=student,
                    day_index=day, sort_order=sort_order,
                ))
    if entries:
        DutyRosterEntry.objects.bulk_create(entries)
    return len(entries)


def _get_roster_stats(roster):
    roster_tasks = list(DutyRosterTask.objects.filter(roster=roster))
    entries = list(DutyRosterEntry.objects.filter(roster=roster).select_related("student"))
    total_slots = sum(rt.people_count for rt in roster_tasks) * roster.day_count
    covered_students = len({e.student_id for e in entries})
    return {
        "total_slots": total_slots,
        "entry_count": len(entries),
        "covered_students": covered_students,
        "task_count": len(roster_tasks),
        "day_count": roster.day_count,
    }


@login_required
@require_current_class
def smart_duty_adjust(request, pk):
    """智能值日 Step 3：拖拽调整。"""
    roster = _get_roster_or_404(request, pk)
    current_class = _current_class(request)
    request.session["smart_duty_roster_id"] = roster.pk
    days, roster_tasks = _roster_grid(roster)

    if request.method == "POST":
        conflicts = []
        with transaction.atomic():
            for day in range(roster.day_count):
                for rt in roster_tasks:
                    key = f"cell_{day}_{rt.pk}"
                    student_ids = [
                        int(x) for x in request.POST.get(key, "").split(",")
                        if x.strip().isdigit()
                    ]
                    student_ids = student_ids[:rt.people_count]
                    DutyRosterEntry.objects.filter(
                        roster=roster, task=rt.task, day_index=day,
                    ).delete()
                    for i, sid in enumerate(student_ids):
                        DutyRosterEntry.objects.create(
                            roster=roster, task=rt.task, student_id=sid,
                            day_index=day, sort_order=i,
                        )
            # 校验同一天每个学生只分配一项
            seen = defaultdict(set)
            for entry in DutyRosterEntry.objects.filter(roster=roster):
                if entry.student_id in seen[entry.day_index]:
                    conflicts.append(f"第{entry.day_index + 1}天 学生重复分配")
                seen[entry.day_index].add(entry.student_id)
        if conflicts:
            messages.warning(request, "发现同一天重复分配：" + "；".join(dict.fromkeys(conflicts)))
        else:
            messages.success(request, "值日安排已保存。")
        _log_operation(request, "edit", roster.name, "手动调整值日排班")
        return redirect("duty:smart_duty_adjust", pk=roster.pk)

    unassigned = list(current_class.students.filter(is_deleted=False))
    assigned_ids = {e.student_id for e in DutyRosterEntry.objects.filter(roster=roster)}
    unassigned = [s for s in unassigned if s.pk not in assigned_ids]

    return render(request, "duty/smart_duty_adjust.html", {
        "roster": roster, "days": days, "roster_tasks": roster_tasks,
        "unassigned": unassigned, "step": 3,
    })


@login_required
@require_current_class
def smart_duty_finalize(request, pk):
    """智能值日 Step 4：确认、打印、分享、存档。"""
    roster = _get_roster_or_404(request, pk)
    current_class = _current_class(request)
    days, roster_tasks = _roster_grid(roster)
    stats = _get_roster_stats(roster)
    class_name = current_class.name if current_class else ""
    text_version = build_roster_text(roster, class_name)
    return render(request, "duty/smart_duty_finalize.html", {
        "roster": roster, "days": days, "roster_tasks": roster_tasks,
        "stats": stats, "class_name": class_name, "text_version": text_version,
        "step": 4,
    })


@login_required
@require_current_class
def smart_duty_activate(request, pk):
    """设为当前生效方案。"""
    roster = _get_roster_or_404(request, pk)
    if request.method == "POST":
        current_class = _current_class(request)
        DutyRoster.objects.filter(
            school_class=current_class, is_current=True,
        ).exclude(pk=roster.pk).update(is_current=False)
        roster.status = "active"
        roster.is_current = True
        roster.save(update_fields=["status", "is_current", "updated_at"])
        messages.success(request, f"「{roster.name}」已设为当前生效方案。")
        _log_operation(request, "edit", roster.name, "设为当前生效值日方案")
    return redirect("duty:smart_duty_finalize", pk=roster.pk)


@login_required
@require_current_class
def smart_duty_archive(request, pk):
    """归档方案。"""
    roster = _get_roster_or_404(request, pk)
    if request.method == "POST":
        roster.status = "archived"
        if roster.is_current:
            roster.is_current = False
        roster.save(update_fields=["status", "is_current", "updated_at"])
        messages.success(request, f"「{roster.name}」已归档。")
        _log_operation(request, "archive", roster.name, "归档值日方案")
    return redirect("duty:smart_duty_history")


@login_required
@require_current_class
def smart_duty_history(request):
    """方案历史列表。"""
    current_class = _current_class(request)
    rosters = DutyRoster.objects.filter(school_class=current_class).select_related("created_by")
    return render(request, "duty/roster_history.html", {"rosters": rosters})


@login_required
@require_current_class
def smart_duty_print(request, pk):
    """值日表打印页（独立模板）。"""
    roster = _get_roster_or_404(request, pk)
    current_class = _current_class(request)
    days, roster_tasks = _roster_grid(roster)
    class_name = current_class.name if current_class else ""
    return render(request, "duty/roster_print.html", {
        "roster": roster, "days": days, "roster_tasks": roster_tasks,
        "class_name": class_name,
    })


@login_required
@require_current_class
def smart_duty_export(request, pk):
    """导出值日方案为 Excel。"""
    roster = _get_roster_or_404(request, pk)
    current_class = _current_class(request)
    days, roster_tasks = _roster_grid(roster)
    class_name = current_class.name if current_class else ""

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "值日生表"
    thin = Side(style="thin", color="cccccc")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill(start_color="1a73e8", end_color="1a73e8", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    headers = ["日期"] + [rt.task.name for rt in roster_tasks]
    sheet.append(headers)
    for col, cell in enumerate(sheet[1], start=1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = border

    for day in days:
        row = [day["date_label"]]
        for task in day["tasks"]:
            row.append("、".join(s.name for s in task["students"]))
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")

    for idx, width in enumerate([18] + [24] * len(roster_tasks), start=1):
        sheet.column_dimensions[chr(64 + idx)].width = width

    output = io.BytesIO()
    workbook.save(output)
    filename = f"{class_name}_{roster.name}_值日生表.xlsx"
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    from urllib.parse import quote
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    _log_operation(request, "export", roster.name, "导出值日方案 Excel")
    return response
