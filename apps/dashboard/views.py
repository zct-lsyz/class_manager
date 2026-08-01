import logging

from django.contrib.auth.decorators import login_required
import logging

from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class


logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


def _warning_events(student, rule):
    from apps.students.history_services import get_student_events
    events = [event for event in get_student_events(student, rule.content) if event["adverse"]]
    if rule.content == "attendance":
        events = [event for event in events if event["code"] in {"late", "early_leave", "absent"}]
    return events


@login_required
def index(request):
    """工作台首页"""
    today = timezone.localdate()

    # 当前班级和学期
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    # ----- 统计数据 -----
    # 学生统计（依赖 students 模块，后续完善）
    total_students = 0
    male_count = 0
    female_count = 0
    try:
        from apps.students.models import Student
        qs = Student.objects.all()
        if current_class:
            qs = qs.filter(school_class=current_class)
        total_students = qs.count()
        male_count = qs.filter(gender="male").count()
        female_count = qs.filter(gender="female").count()
    except Exception:
        logger.exception("工作台学生统计加载失败")
        pass

    # 今日缺勤（依赖 attendance 模块）
    today_absent = 0
    try:
        from apps.attendance.models import AttendanceRecord
        today_absent = AttendanceRecord.objects.filter(
            date=today, status__in=["absent", "late"]
        ).count()
    except Exception:
        logger.exception("工作台考勤统计加载失败")
        pass

    # 本周未交作业（依赖 homework 模块）
    week_start = today - timezone.timedelta(days=today.weekday())
    week_unsubmitted = 0
    try:
        from apps.homework.models import HomeworkRecord
        week_unsubmitted = HomeworkRecord.objects.filter(
            submission_date__gte=week_start,
            status__in=["unsubmitted", "late"],
        ).count()
    except Exception:
        logger.exception("工作台作业统计加载失败")
        pass

    # 本周课堂纪律（依赖 discipline 模块）
    week_discipline = 0
    try:
        from apps.discipline.models import ClassroomDisciplineRecord
        week_discipline = ClassroomDisciplineRecord.objects.filter(
            date__gte=week_start
        ).count()
    except Exception:
        logger.exception("工作台课堂纪律统计加载失败")
        pass

    # 本周宿舍纪律（依赖 discipline 模块）
    week_dorm_discipline = 0
    try:
        from apps.discipline.models import DormDisciplineRecord
        week_dorm_discipline = DormDisciplineRecord.objects.filter(
            date__gte=week_start
        ).count()
    except Exception:
        logger.exception("工作台宿舍纪律统计加载失败")
        pass

    # 本月奖励（依赖 rewards 模块）
    this_month_rewards = 0
    try:
        from apps.rewards.models import RewardRecord
        this_month_rewards = RewardRecord.objects.filter(
            date__month=today.month, date__year=today.year
        ).count()
    except Exception:
        logger.exception("工作台奖励统计加载失败")
        pass

    # 最近考试均分（依赖 scores 模块）
    latest_exam = None
    exam_avg_score = None
    try:
        from apps.scores.models import Exam, Score
        if current_semester:
            latest_exam = Exam.objects.filter(
                semester=current_semester, is_deleted=False
            ).order_by("-date").first()
            if latest_exam:
                from django.db.models import Avg
                result = Score.objects.filter(
                    exam=latest_exam, status="normal", is_deleted=False
                ).aggregate(avg=Avg("score"))
                exam_avg_score = result["avg"]
    except Exception:
        logger.exception("工作台成绩统计加载失败")
        pass

    # 待完成评语（依赖 comments 模块）
    pending_comments = 0
    try:
        from apps.comments.models import StudentComment
        if current_semester:
            pending_comments = StudentComment.objects.filter(
                semester=current_semester,
                status__in=["draft", "pending"],
            ).count()
    except Exception:
        logger.exception("工作台评语统计加载失败")
        pass

    # 出勤率
    attendance_rate = None
    try:
        from apps.attendance.models import AttendanceRecord
        this_month_attendance_count = AttendanceRecord.objects.filter(
            date__month=today.month, date__year=today.year
        ).count()
        total_days_this_month = AttendanceRecord.objects.filter(
            date__month=today.month, date__year=today.year
        ).values("date").distinct().count()
        if total_days_this_month > 0 and total_students > 0:
            total_possible = total_students * total_days_this_month
            if total_possible > 0:
                attendance_rate = round(
                    (total_possible - this_month_attendance_count)
                    / total_possible * 100, 1
                )
    except Exception:
        logger.exception("工作台提醒加载失败")
        pass

    # ----- 提醒事项 -----
    reminders = []
    # 自动备份状态检查
    try:
        from apps.backups.models import BackupRecord
        last_backup = BackupRecord.objects.filter(
            backup_type="auto"
        ).order_by("-created_at").first()
        if last_backup and not last_backup.success:
            reminders.append({
                "type": "danger",
                "icon": "bi-exclamation-triangle",
                "text": "最近一次自动备份失败，请检查备份配置。",
            })
    except Exception:
        logger.exception("工作台近期事件加载失败")
        pass

    # 长时间未下载备份提醒
    try:
        from apps.backups.models import BackupRecord
        recent_download = BackupRecord.objects.filter(
            downloaded=True
        ).order_by("-created_at").first()
        if recent_download:
            days_since = (today - recent_download.created_at.date()).days
            if days_since > 14:
                reminders.append({
                    "type": "warning",
                    "icon": "bi-download",
                    "text": f"已 {days_since} 天未下载异地备份，建议定期下载到本地。",
                })
    except Exception:
        logger.exception("工作台趋势统计加载失败")
        pass

    # ----- 待办事项 -----
    active_todos = []
    completed_todos = []
    try:
        from apps.todos.models import TodoItem
        active_todos = TodoItem.objects.filter(
            school_class=current_class, is_deleted=False, is_completed=False,
        ).order_by("deadline", "-created_at") if current_class else []
        completed_todos = TodoItem.objects.filter(
            school_class=current_class, is_deleted=False, is_completed=True,
        ).order_by("-updated_at")[:5] if current_class else []
    except Exception:
        logger.exception("工作台待办事项加载失败")
        pass

    context = {
        "today": today,
        "now": timezone.now(),
        "current_class": current_class,
        "current_semester": current_semester,
        # 统计卡片
        "total_students": total_students,
        "male_count": male_count,
        "female_count": female_count,
        "today_absent": today_absent,
        "attendance_rate": attendance_rate,
        "week_unsubmitted": week_unsubmitted,
        "week_discipline": week_discipline,
        "week_dorm_discipline": week_dorm_discipline,
        "this_month_rewards": this_month_rewards,
        "exam_avg_score": exam_avg_score,
        "latest_exam": latest_exam,
        "pending_comments": pending_comments,
        # 提醒
        "reminders": reminders,
        # 待办事项
        "active_todos": active_todos,
        "completed_todos": completed_todos,
    }
    return render(request, "dashboard/index.html", context)


@login_required
@require_current_class
def warnings(request):
    from apps.attendance.models import WarningRule
    from apps.students.models import Student
    current_class = get_current_class(request.user)
    if request.method == "POST":
        try:
            threshold = int(request.POST.get("threshold", "2"))
        except ValueError:
            threshold = 0
        content = request.POST.get("content", "")
        unit = request.POST.get("unit", "count")
        name = request.POST.get("name", "").strip()
        if current_class and name and content in dict(WarningRule.CONTENT_CHOICES) and unit in dict(WarningRule.UNIT_CHOICES) and 1 <= threshold <= 20:
            WarningRule.objects.create(school_class=current_class, name=name, content=content, unit=unit, threshold=threshold)
            messages.success(request, "预警条目已添加。")
            return redirect("dashboard:warnings")
        messages.error(request, "请完整填写预警内容，数量必须为 1–20。")
    rules = WarningRule.objects.filter(school_class=current_class, is_active=True) if current_class else []
    warning_students = []
    students = Student.objects.filter(school_class=current_class, is_deleted=False) if current_class else []
    for student in students:
        matched = []
        for rule in rules:
            events = _warning_events(student, rule)
            value = len(events) if rule.unit == "count" else sum(abs(event["points"]) for event in events if event["points"] < 0)
            if value >= rule.threshold:
                matched.append({"rule": rule, "events": events, "value": value, "items": "、".join(sorted({event["item"] for event in events}))})
        if matched:
            warning_students.append({"student": student, "warnings": matched})
    return render(request, "dashboard/warnings.html", {"rules": rules, "warning_students": warning_students, "content_choices": WarningRule.CONTENT_CHOICES})


@login_required
def warning_delete(request, pk):
    from apps.attendance.models import WarningRule
    rule = get_object_or_404(WarningRule, pk=pk)
    if request.method == "POST":
        rule.delete()
        messages.info(request, "预警条目已删除。")
    return redirect("dashboard:warnings")


@login_required
def warning_detail(request, pk):
    from apps.attendance.models import WarningRule
    from apps.students.models import Student
    student = get_object_or_404(Student, pk=pk, is_deleted=False)
    rules = WarningRule.objects.filter(school_class=student.school_class, is_active=True)
    details = []
    for rule in rules:
        events = _warning_events(student, rule)
        value = len(events) if rule.unit == "count" else sum(abs(event["points"]) for event in events if event["points"] < 0)
        if value >= rule.threshold:
            details.append({"rule": rule, "events": events, "value": value})
    return render(request, "dashboard/warning_detail.html", {"student": student, "details": details})


@login_required
def api_notifications(request):
    """供 Android App 后台轮询的轻量通知接口。"""
    today = timezone.localdate()
    current_class = get_current_class(request.user)

    result = {
        "ok": True,
        "timestamp": today.isoformat(),
        "has_current_class": bool(current_class),
        "today_duty": None,
        "warning_count": 0,
        "warnings": [],
        "today_backup_alert": False,
        "due_count": 0,
        "due_todos": [],
    }

    # 今日值日
    if current_class:
        try:
            from apps.duty.models import DutyRoster, DutyRosterEntry, DutyRosterTask
            roster = DutyRoster.objects.filter(
                school_class=current_class, status="active", is_current=True,
                date_start__lte=today, date_end__gte=today,
            ).first()
            if roster:
                day_index = (today - roster.date_start).days
                if 0 <= day_index < roster.day_count:
                    roster_tasks = list(
                        DutyRosterTask.objects.filter(roster=roster)
                        .select_related("task").order_by("sort_order", "pk")
                    )
                    entries = list(
                        DutyRosterEntry.objects.filter(
                            roster=roster, day_index=day_index,
                        ).select_related("student", "task").order_by("task__sort_order", "sort_order")
                    )
                    by_task = {}
                    for entry in entries:
                        by_task.setdefault(entry.task_id, []).append(entry.student.name)
                    summary = []
                    for rt in roster_tasks:
                        names = by_task.get(rt.task_id, [])
                        if names:
                            summary.append(f"{rt.task.name}：{'、'.join(names)}")
                    result["today_duty"] = {
                        "roster_name": roster.name,
                        "summary": "；".join(summary) if summary else "今日无排班",
                    }
        except Exception:
            pass

    # 预警
    if current_class:
        try:
            from apps.attendance.models import WarningRule
            from apps.students.models import Student
            from apps.students.history_services import get_student_events
            rules = WarningRule.objects.filter(school_class=current_class, is_active=True)
            students = Student.objects.filter(school_class=current_class, is_deleted=False)
            warning_count = 0
            warning_items = []
            for student in students:
                for rule in rules:
                    events = _warning_events(student, rule)
                    value = len(events) if rule.unit == "count" else sum(
                        abs(event["points"]) for event in events if event["points"] < 0
                    )
                    if value >= rule.threshold:
                        warning_count += 1
                        warning_items.append(f"{student.name}({rule.name})")
                        break
            result["warning_count"] = warning_count
            result["warnings"] = warning_items[:20]
        except Exception:
            pass

    # 备份失败提醒
    try:
        from apps.backups.models import BackupRecord
        failed = BackupRecord.objects.filter(
            status="failed", created_at__date=today,
        ).count()
        result["today_backup_alert"] = failed > 0
    except Exception:
        pass

    # 到期/逾期待办
    if current_class:
        try:
            from apps.todos.models import TodoItem
            due_todos = TodoItem.objects.filter(
                school_class=current_class, is_deleted=False, is_completed=False,
                deadline__lte=timezone.now(),
            ).order_by("deadline")[:10]
            result["due_count"] = due_todos.count()
            result["due_todos"] = [
                {
                    "title": t.title,
                    "deadline": timezone.localtime(t.deadline).strftime("%m-%d %H:%M") if t.deadline else None,
                }
                for t in due_todos
            ]
        except Exception:
            pass

    return JsonResponse(result)
