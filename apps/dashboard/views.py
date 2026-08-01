import json
import logging
import os
import ssl
import urllib.request

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.dashboard.models import Countdown, DailyQuote, TeachingWebsite


logger = logging.getLogger(__name__)


def _warning_events(student, rule):
    from apps.students.history_services import get_student_events
    events = [event for event in get_student_events(student, rule.content) if event["adverse"]]
    if rule.content == "attendance":
        events = [event for event in events if event["code"] in {"late", "early_leave", "absent"}]
    return events


def _get_daily_quote():
    """获取今日名言：缓存优先，无缓存时调用 LLM API 生成。"""
    today = timezone.localdate()
    cached = DailyQuote.objects.filter(date=today).first()
    if cached:
        return cached.quote, cached.author

    # 调用 LLM API 生成
    api_key = os.environ.get("LLM_API_KEY", os.environ.get("DEEPSEEK_API_KEY", ""))
    api_url = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
    model = os.environ.get("LLM_MODEL", "deepseek-chat")

    if not api_key:
        fallback = "教育不是注满一桶水，而是点燃一把火。"
        author = "叶芝"
        DailyQuote.objects.create(date=today, quote=fallback, author=author)
        return fallback, author

    try:
        req_body = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": (
                    "你是一位教育励志名言生成器。请生成一条激励教师或学生的教育类名言，"
                    "要求原创或经典名言，50字以内，积极向上。"
                    "请以 JSON 格式返回：{\"quote\": \"名言内容\", \"author\": \"作者或出处\"}。"
                    "只返回 JSON，不要其他文字。"
                )},
                {"role": "user", "content": "请生成一条教育励志名言。"},
            ],
            "temperature": 0.9,
            "max_tokens": 200,
        }).encode("utf-8")

        req = urllib.request.Request(
            api_url,
            data=req_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            content = raw["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
            result = json.loads(content)
            quote = result.get("quote", content)
            author = result.get("author", "")
    except Exception:
        logger.exception("LLM 名言生成失败，使用默认名言")
        quote = "教育不是注满一桶水，而是点燃一把火。"
        author = "叶芝"

    DailyQuote.objects.create(date=today, quote=quote, author=author)
    return quote, author


def _calc_teaching_week(current_semester):
    """根据学期起止日期计算当前教学周（1-based）。"""
    if not current_semester:
        return None
    start = current_semester.start_date
    end = current_semester.end_date
    if not start:
        return None
    today = timezone.localdate()
    if today < start:
        return 0  # 学期尚未开始
    if end and today > end:
        return None  # 学期已结束
    days_elapsed = (today - start).days
    week = days_elapsed // 7 + 1
    return max(1, week)


SHANDONG_DEFAULT_WEBSITES = [
    ("山东省教育云平台", "https://www.sdei.edu.cn/"),
    ("山东省教育招生考试院", "https://www.sdzk.cn/"),
    ("山东教师教育网", "https://www.sdjsjy.com/"),
    ("国家中小学智慧教育平台", "https://basic.smartedu.cn/"),
    ("山东省教育厅", "http://edu.shandong.gov.cn/"),
]


def _seed_default_websites(user):
    """为新用户创建山东省默认教育网站收藏"""
    for i, (name, url) in enumerate(SHANDONG_DEFAULT_WEBSITES):
        TeachingWebsite.objects.get_or_create(
            created_by=user, url=url,
            defaults={"name": name, "sort_order": i},
        )


@login_required
def index(request):
    """工作台首页"""
    today = timezone.localdate()

    # 当前班级和学期
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    # 教学周
    teaching_week = _calc_teaching_week(current_semester)

    # ----- 统计数据 -----
    total_students = 0
    male_count = 0
    female_count = 0
    try:
        from apps.students.models import Student
        qs = Student.objects.filter(is_deleted=False)
        if current_class:
            qs = qs.filter(school_class=current_class)
        total_students = qs.count()
        male_count = qs.filter(gender="male").count()
        female_count = qs.filter(gender="female").count()
    except Exception:
        pass

    # 今日缺勤
    today_absent = 0
    try:
        from apps.attendance.models import AttendanceRecord
        qs_att = AttendanceRecord.objects.filter(date=today)
        if current_class:
            qs_att = qs_att.filter(school_class=current_class)
        today_absent = qs_att.filter(status__in=["absent", "late"]).count()
    except Exception:
        pass

    # 本周未交作业
    week_start = today - timezone.timedelta(days=today.weekday())
    week_unsubmitted = 0
    try:
        from apps.homework.models import HomeworkRecord
        qs_hw = HomeworkRecord.objects.filter(
            submission_date__gte=week_start,
            status__in=["unsubmitted", "late"],
        )
        if current_class:
            qs_hw = qs_hw.filter(school_class=current_class)
        week_unsubmitted = qs_hw.count()
    except Exception:
        pass

    # ----- 提醒事项 -----
    reminders = []
    try:
        from apps.backups.models import BackupRecord
        last_backup = BackupRecord.objects.filter(backup_type="auto").order_by("-created_at").first()
        if last_backup and not last_backup.success:
            reminders.append({
                "type": "danger",
                "icon": "bi-exclamation-triangle",
                "text": "最近一次自动备份失败，请检查备份配置。",
            })
    except Exception:
        pass

    try:
        from apps.backups.models import BackupRecord
        recent_download = BackupRecord.objects.filter(downloaded=True).order_by("-created_at").first()
        if recent_download:
            days_since = (today - recent_download.created_at.date()).days
            if days_since > 14:
                reminders.append({
                    "type": "warning",
                    "icon": "bi-download",
                    "text": f"已 {days_since} 天未下载异地备份，建议定期下载到本地。",
                })
    except Exception:
        pass

    # ----- 待办事项概览 -----
    active_todos = []
    todo_count = 0
    try:
        from apps.todos.models import TodoItem
        qs_todos = TodoItem.objects.filter(is_deleted=False, is_completed=False)
        if current_class:
            qs_todos = qs_todos.filter(school_class=current_class)
        todo_count = qs_todos.count()
        active_todos = qs_todos.order_by("deadline", "-created_at")[:5]
    except Exception:
        pass

    # ----- 倒计时 -----
    countdowns = Countdown.objects.filter(
        created_by=request.user, is_active=True,
    ).order_by("target_date")

    # ----- 每日名言 -----
    daily_quote, daily_quote_author = _get_daily_quote()

    # ----- 常用教学网站 -----
    teaching_websites = list(TeachingWebsite.objects.filter(
        created_by=request.user,
    ).order_by("sort_order", "name"))

    # 首次访问时自动创建山东省默认教育网站
    if not teaching_websites and current_class:
        _seed_default_websites(request.user)
        teaching_websites = list(TeachingWebsite.objects.filter(
            created_by=request.user,
        ).order_by("sort_order", "name"))

    context = {
        "today": today,
        "now": timezone.now(),
        "current_class": current_class,
        "current_semester": current_semester,
        "teaching_week": teaching_week,
        # 统计卡片（3个核心数据）
        "total_students": total_students,
        "male_count": male_count,
        "female_count": female_count,
        "today_absent": today_absent,
        "week_unsubmitted": week_unsubmitted,
        # 提醒
        "reminders": reminders,
        # 待办事项概览
        "active_todos": active_todos,
        "todo_count": todo_count,
        # 倒计时
        "countdowns": countdowns,
        # 每日名言
        "daily_quote": daily_quote,
        "daily_quote_author": daily_quote_author,
        # 常用教学网站
        "teaching_websites": teaching_websites,
    }
    return render(request, "dashboard/index.html", context)


# ====== 倒计时管理 ======

@login_required
def countdown_list(request):
    """倒计时管理页面"""
    countdowns = Countdown.objects.filter(
        created_by=request.user,
    ).order_by("target_date")

    # 编辑表单 GET 参数
    edit_id = request.GET.get("edit")
    edit_obj = None
    if edit_id:
        try:
            edit_obj = Countdown.objects.get(pk=int(edit_id), created_by=request.user)
        except (ValueError, Countdown.DoesNotExist):
            pass

    context = {
        "countdowns": countdowns,
        "edit_obj": edit_obj,
        "today": timezone.localdate(),
    }
    return render(request, "dashboard/countdown_list.html", context)


@login_required
def countdown_add(request):
    """添加倒计时"""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        target_date = request.POST.get("target_date", "").strip()
        if name and target_date:
            Countdown.objects.create(
                created_by=request.user,
                name=name,
                target_date=target_date,
            )
            messages.success(request, f"倒计时「{name}」已添加。")
        else:
            messages.error(request, "请填写名称和目标日期。")
    return redirect("dashboard:countdown_list")


@login_required
def countdown_edit(request, pk):
    """编辑倒计时"""
    cd = get_object_or_404(Countdown, pk=pk, created_by=request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        target_date = request.POST.get("target_date", "").strip()
        if name and target_date:
            cd.name = name
            cd.target_date = target_date
            cd.save(update_fields=["name", "target_date", "updated_at"])
            messages.success(request, f"倒计时「{cd.name}」已更新。")
        else:
            messages.error(request, "请填写名称和目标日期。")
    return redirect("dashboard:countdown_list")


@login_required
def countdown_delete(request, pk):
    """删除倒计时"""
    cd = get_object_or_404(Countdown, pk=pk, created_by=request.user)
    if request.method == "POST":
        messages.info(request, f"倒计时「{cd.name}」已删除。")
        cd.delete()
    return redirect("dashboard:countdown_list")


# ====== 常用教学网站管理 ======

@login_required
def website_add(request):
    """添加教学网站"""
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        url = request.POST.get("url", "").strip()
        if name and url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            # 去重
            if not TeachingWebsite.objects.filter(created_by=request.user, url=url).exists():
                TeachingWebsite.objects.create(
                    created_by=request.user, name=name, url=url,
                )
                messages.success(request, f"网站「{name}」已添加。")
            else:
                messages.warning(request, "该网址已存在。")
        else:
            messages.error(request, "请填写网站名称和URL链接。")
    return redirect("dashboard:index")


@login_required
def website_delete(request, pk):
    """删除教学网站"""
    site = get_object_or_404(TeachingWebsite, pk=pk, created_by=request.user)
    if request.method == "POST":
        messages.info(request, f"网站「{site.name}」已删除。")
        site.delete()
    return redirect("dashboard:index")


# ====== 原警告/预警模块 ======

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

    if current_class:
        try:
            from apps.attendance.models import WarningRule
            from apps.students.models import Student
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

    try:
        from apps.backups.models import BackupRecord
        failed = BackupRecord.objects.filter(
            status="failed", created_at__date=today,
        ).count()
        result["today_backup_alert"] = failed > 0
    except Exception:
        pass

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
