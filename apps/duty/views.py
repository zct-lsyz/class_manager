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
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.duty.forms import DutyTaskForm, DutyGroupForm, DutyRecordForm
from apps.duty.models import (
    DutyTask,
    DutyGroup,
    DutyRecord,
    DutyMemberTask,
    DutyRoster,
    DutyRosterTask,
    DutyRosterEntry,
    DutyAbsenceRecord,
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
    """值日管理首页：手动小组 + 当前生效方案的当周值日小组"""
    current_class = get_current_class(request.user)
    groups = DutyGroup.objects.filter(
        school_class=current_class, is_active=True
    ).prefetch_related("members", "tasks") if current_class else []

    tasks = DutyTask.objects.filter(
        school_class=current_class, is_active=True
    ) if current_class else []

    # 当前生效的智能值日方案 → 按天展示当周各个值日小组
    roster = None
    roster_groups = []
    if current_class:
        roster = DutyRoster.objects.filter(
            school_class=current_class, is_current=True, status="active",
        ).first()
        if roster:
            roster_groups = _roster_day_groups(roster)

    all_students = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("name_pinyin", "name", "student_id") if current_class else []

    context = {
        "groups": groups, "tasks": tasks,
        "roster": roster, "roster_groups": roster_groups,
        "all_students": all_students,
    }
    return render(request, "duty/index.html", context)


def _roster_day_groups(roster):
    """把生效方案按天构造成小组：日期、组长（is_leader）、按任务的成员。"""
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
    leaders = {}
    for entry in entries:
        cell_map[(entry.day_index, entry.task_id)].append(entry)
        if entry.is_leader:
            leaders.setdefault(entry.day_index, entry)
    dates = get_day_dates(roster.date_start, roster.day_count)
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    groups = []
    for day in range(roster.day_count):
        date_obj = dates[day] if day < len(dates) else None
        date_label = ""
        if date_obj:
            date_label = f"{date_obj.month}月{date_obj.day}日 周{weekdays[date_obj.weekday()]}"
        tasks = []
        for rt in roster_tasks:
            cell_entries = cell_map.get((day, rt.task_id), [])
            tasks.append({
                "task": rt.task,
                "rt_pk": rt.pk,
                "max_count": rt.people_count,
                "students": [e.student for e in cell_entries],
            })
        leader_entry = leaders.get(day)
        groups.append({
            "day_index": day,
            "date": date_obj,
            "date_label": date_label,
            "group_name": f"{date_label or f'第{day + 1}天'}值日组",
            "leader": leader_entry.student if leader_entry else None,
            "tasks": tasks,
            "member_count": sum(len(t["students"]) for t in tasks),
        })
    return groups


@login_required
def export(request):
    """导出当前值日小组表为 Excel。"""
    current_class = get_current_class(request.user)
    groups = DutyGroup.objects.filter(
        school_class=current_class, is_active=True,
    ).prefetch_related("members", "leader") if current_class else []

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "值日生表"
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", start_color="1A73E8")
    header_font = Font(bold=True, color="FFFFFF")

    headers = ["小组", "周次", "组长", "成员"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for g in groups:
        members = "、".join(m.name for m in g.members.all())
        ws.append([
            g.name, g.week or "",
            g.leader.name if g.leader else "",
            members,
        ])
        for cell in ws[ws.max_row]:
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for idx, width in enumerate([22, 8, 12, 50], start=1):
        ws.column_dimensions[chr(64 + idx)].width = width

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="duty_groups.xlsx"'
    wb.save(response)
    return response


@login_required
@require_current_class
def task_list(request):
    """值日任务配置"""
    current_class = get_current_class(request.user)
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
    current_class = get_current_class(request.user)
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
    current_class = get_current_class(request.user)
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
    current_class = get_current_class(request.user)
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
        "members_for_tasks": group.members.all().order_by("name_pinyin", "name", "student_id"),
        "tasks_for_assignment": group.tasks.all(), "assignments": assignments,
    })


@login_required
def group_detail(request, pk):
    """值日小组详情：成员值日记录录入"""
    current_class = get_current_class(request.user)
    group = get_object_or_404(
        DutyGroup.objects.prefetch_related("members", "tasks"),
        pk=pk, school_class=current_class,
    )
    members = group.members.all().order_by("name_pinyin", "name", "student_id")
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
    return get_current_class(request.user)


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
        # 是否使用已分配小组（同组尽量同一天值日）
        request.session["smart_duty_use_groups"] = request.POST.get("use_groups") == "1"

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

    use_groups = bool(request.session.get("smart_duty_use_groups", False))
    if request.method == "POST":
        # 重新生成
        if roster is None:
            return redirect("duty:smart_duty")
        with transaction.atomic():
            DutyRosterEntry.objects.filter(roster=roster).delete()
            _run_generation(roster, current_class, use_groups=use_groups)
        _log_operation(request, "edit", roster.name, "重新生成值日排班")
        return redirect("duty:smart_duty_generate")

    if roster is None:
        messages.info(request, "请先配置任务再自动生成。")
        return redirect("duty:smart_duty")

    # GET 时若尚无排班记录，则自动执行生成
    if not DutyRosterEntry.objects.filter(roster=roster).exists():
        with transaction.atomic():
            _run_generation(roster, current_class, use_groups=use_groups)
        _log_operation(request, "create", roster.name, "自动生成值日排班")

    stats = _get_roster_stats(roster)
    return render(request, "duty/smart_duty_generate.html", {
        "roster": roster, "stats": stats,
    })


def _run_generation(roster, current_class, use_groups=False):
    """执行公平轮值算法并写入 DutyRosterEntry。"""
    from apps.students.models import Student
    students = list(Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("sort_order", "student_id"))
    roster_tasks = list(DutyRosterTask.objects.filter(roster=roster).order_by("sort_order", "pk"))
    tasks_with_counts = [(rt.task_id, rt.people_count) for rt in roster_tasks]
    # 上一个方案中出现过的学生（未出现者优先安排值日）
    previous_roster = DutyRoster.objects.filter(
        school_class=current_class,
    ).exclude(pk=roster.pk).order_by("-created_at").first()
    previous_student_ids = set()
    if previous_roster:
        previous_student_ids = set(DutyRosterEntry.objects.filter(
            roster=previous_roster,
        ).values_list("student_id", flat=True))
    result = generate_duty_roster(
        students, tasks_with_counts, roster.day_count, current_class,
        use_groups=use_groups, previous_student_ids=previous_student_ids,
    )
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
            _log_operation(request, "edit", roster.name, "手动调整值日排班（存在冲突）")
            return redirect("duty:smart_duty_adjust", pk=roster.pk)
        messages.success(request, "值日安排已保存。")
        _log_operation(request, "edit", roster.name, "手动调整值日排班")
        # "保存调整并继续" → 进入第 4 步确认存档
        return redirect("duty:smart_duty_finalize", pk=roster.pk)

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
        # 每天小组自动指定第一位学生为组长（可在值日生表页调整）
        for day in range(roster.day_count):
            DutyRosterEntry.objects.filter(
                roster=roster, day_index=day,
            ).update(is_leader=False)
            first = DutyRosterEntry.objects.filter(
                roster=roster, day_index=day,
            ).order_by("task__sort_order", "sort_order").first()
            if first:
                first.is_leader = True
                first.save(update_fields=["is_leader"])
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


# ============ 值日缺勤记录 ============


def _sync_absence_points(record):
    """缺勤记录 → 统一积分明细（source_type=duty），修改扣分时自动更新。"""
    from apps.rewards.services import sync_source_point
    sync_source_point(
        student=record.student,
        school_class=record.school_class,
        semester=record.semester,
        date=record.date,
        points=-record.points,
        reason=f"值日缺勤：{record.group_name or record.task_name or '值日'}",
        source_type="duty",
        source_id=record.pk,
    )


@login_required
def duty_absence_list(request):
    """缺勤记录列表：日期 / 工作 / 小组 / 组长 / 扣分（可修改）"""
    current_class = get_current_class(request.user)
    records = DutyAbsenceRecord.objects.filter(
        school_class=current_class,
    ).select_related("student", "leader", "task").order_by("-date", "-created_at") if current_class else DutyAbsenceRecord.objects.none()

    paginator = Paginator(records, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    students = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("name_pinyin", "name") if current_class else []
    tasks = DutyTask.objects.filter(
        school_class=current_class, is_active=True,
    ) if current_class else []

    return render(request, "duty/absence_list.html", {
        "page_obj": page_obj, "students": students, "tasks": tasks,
        "today": timezone.localdate(),
    })


@login_required
@require_current_class
def duty_absence_add(request):
    """添加缺勤记录（小组快捷按钮或列表页表单），扣分默认 1 分。"""
    current_class = get_current_class(request.user)
    if request.method != "POST":
        return redirect("duty:absence_list")

    student = get_object_or_404(
        Student, pk=request.POST.get("student_id", ""),
        school_class=current_class, is_deleted=False,
    )
    date_raw = request.POST.get("date", "") or str(timezone.localdate())
    from datetime import date as _date
    try:
        date = _date.fromisoformat(str(date_raw).strip())
    except ValueError:
        messages.error(request, "日期格式不正确。")
        return redirect(request.META.get("HTTP_REFERER") or "duty:index")

    try:
        points = max(1, int(request.POST.get("points", "1") or "1"))
    except (ValueError, TypeError):
        points = 1

    task = None
    task_id = request.POST.get("task_id", "")
    if task_id.isdigit():
        task = DutyTask.objects.filter(pk=task_id, school_class=current_class).first()

    leader = None
    leader_id = request.POST.get("leader_id", "")
    if leader_id.isdigit():
        leader = Student.objects.filter(pk=leader_id, school_class=current_class).first()

    roster = None
    roster_id = request.POST.get("roster_id", "")
    if roster_id.isdigit():
        roster = DutyRoster.objects.filter(pk=roster_id, school_class=current_class).first()

    group_name = request.POST.get("group_name", "").strip()
    task_name = request.POST.get("task_name", "").strip()

    # 自动匹配：根据值日方案 + 缺勤日期 + 缺勤学生，
    # 自动带出当天负责的工作、小组和组长
    if roster is None:
        roster = DutyRoster.objects.filter(
            school_class=current_class, is_current=True, status="active",
        ).first()
    if roster:
        from apps.duty.services import get_day_dates
        dates = get_day_dates(roster.date_start, roster.day_count)
        try:
            day_index = dates.index(date)
        except ValueError:
            day_index = -1
        if day_index >= 0:
            entry = DutyRosterEntry.objects.filter(
                roster=roster, day_index=day_index, student=student,
            ).select_related("task").first()
            if entry:
                task = entry.task
                task_name = entry.task.name
            if not group_name:
                date_obj = dates[day_index]
                weekdays = ["一", "二", "三", "四", "五", "六", "日"]
                group_name = f"{date_obj.month}月{date_obj.day}日 周{weekdays[date_obj.weekday()]}值日组"
            leader_entry = DutyRosterEntry.objects.filter(
                roster=roster, day_index=day_index, is_leader=True,
            ).select_related("student").first()
            if leader_entry and leader is None:
                leader = leader_entry.student

    record = DutyAbsenceRecord.objects.create(
        school_class=current_class,
        semester=Semester.objects.filter(
            school_class=current_class, is_current=True,
        ).first(),
        roster=roster,
        date=date,
        task=task,
        task_name=task_name or (task.name if task else ""),
        group_name=group_name,
        student=student,
        leader=leader,
        leader_name=(leader.name if leader else request.POST.get("leader_name", "")).strip(),
        points=points,
        remark=request.POST.get("remark", "").strip(),
    )
    _sync_absence_points(record)
    OperationLog.objects.create(
        user=request.user, action="create", module="duty",
        object_repr=f"{student.name} {date} 缺勤",
        detail=f"值日缺勤：{record.group_name or record.task_name or '值日'}，扣 {points} 分",
        ip_address=get_client_ip(request), success=True,
    )
    messages.success(request, f"已记录 {student.name} {date} 值日缺勤，扣 {points} 分。")
    next_url = request.POST.get("next", "")
    if next_url:
        return redirect(next_url)
    return redirect("duty:absence_list")


@login_required
def duty_absence_update_points(request, pk):
    """修改缺勤扣分（同步更新积分）。"""
    current_class = get_current_class(request.user)
    record = get_object_or_404(DutyAbsenceRecord, pk=pk, school_class=current_class)
    if request.method == "POST":
        try:
            points = max(1, int(request.POST.get("points", record.points) or record.points))
        except (ValueError, TypeError):
            points = record.points
        record.points = points
        record.save(update_fields=["points", "updated_at"])
        _sync_absence_points(record)
        messages.success(request, f"{record.student.name} 缺勤扣分已改为 {points} 分。")
    return redirect("duty:absence_list")


@login_required
def duty_absence_delete(request, pk):
    """删除缺勤记录（同步撤销积分）。"""
    current_class = get_current_class(request.user)
    record = get_object_or_404(DutyAbsenceRecord, pk=pk, school_class=current_class)
    if request.method == "POST":
        from apps.rewards.services import unsync_source_point
        unsync_source_point("duty", record.pk)
        student_name = record.student.name
        record.delete()
        messages.info(request, f"{student_name} 的缺勤记录已删除，积分已撤销。")
    return redirect("duty:absence_list")


@login_required
@require_current_class
def duty_update_day(request, pk):
    """修改某天值日小组的组员与组长（值日生表「修改」按钮）。"""
    current_class = get_current_class(request.user)
    roster = get_object_or_404(DutyRoster, pk=pk, school_class=current_class)
    if request.method != "POST":
        return redirect("duty:index")
    day_index_raw = request.POST.get("day_index", "")
    if not day_index_raw.isdigit():
        messages.error(request, "参数错误。")
        return redirect("duty:index")
    day_index = int(day_index_raw)

    roster_tasks = list(DutyRosterTask.objects.filter(roster=roster))
    with transaction.atomic():
        for rt in roster_tasks:
            student_ids = [
                int(x) for x in request.POST.getlist(f"task_{rt.pk}") if x.isdigit()
            ][:rt.people_count]
            DutyRosterEntry.objects.filter(
                roster=roster, task=rt.task, day_index=day_index,
            ).delete()
            for i, sid in enumerate(student_ids):
                DutyRosterEntry.objects.create(
                    roster=roster, task=rt.task, student_id=sid,
                    day_index=day_index, sort_order=i,
                )

        # 组长：默认取当天第一个学生，或表单指定的学生
        leader_id = request.POST.get("leader_id", "")
        duty_entries = list(DutyRosterEntry.objects.filter(
            roster=roster, day_index=day_index,
        ).order_by("task__sort_order", "sort_order"))
        DutyRosterEntry.objects.filter(
            roster=roster, day_index=day_index,
        ).update(is_leader=False)
        leader_entry = None
        if leader_id.isdigit():
            leader_entry = next(
                (e for e in duty_entries if e.student_id == int(leader_id)), None,
            )
        if leader_entry is None and duty_entries:
            leader_entry = duty_entries[0]
        if leader_entry:
            leader_entry.is_leader = True
            leader_entry.save(update_fields=["is_leader"])

    messages.success(request, "当天小组已更新。")
    return redirect("duty:index")


@login_required
@require_current_class
def duty_set_leader(request, pk):
    """把某天值日小组的某位学生设为组长。"""
    current_class = get_current_class(request.user)
    roster = get_object_or_404(DutyRoster, pk=pk, school_class=current_class)
    if request.method == "POST":
        day_index = request.POST.get("day_index", "")
        student_id = request.POST.get("student_id", "")
        if day_index.isdigit() and student_id.isdigit():
            DutyRosterEntry.objects.filter(
                roster=roster, day_index=int(day_index),
            ).update(is_leader=False)
            updated = DutyRosterEntry.objects.filter(
                roster=roster, day_index=int(day_index), student_id=int(student_id),
            ).update(is_leader=True)
            if updated:
                messages.success(request, "组长已更新。")
            else:
                messages.error(request, "该学生不在当天小组中。")
    return redirect("duty:index")
