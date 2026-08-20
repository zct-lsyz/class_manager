def _apply_dates(queryset, date_field, date_from=None, date_to=None):
    if date_from:
        queryset = queryset.filter(**{f"{date_field}__gte": date_from})
    if date_to:
        queryset = queryset.filter(**{f"{date_field}__lte": date_to})
    return queryset


ALL_MODULES = [
    ("evaluation", "荣誉评选"),
    ("rewards", "奖惩记录"),
    ("points", "积分变动"),
    ("discipline", "课堂纪律"),
    ("dormitory", "宿舍管理"),
    ("attendance", "考勤管理"),
    ("homework", "作业情况"),
    ("duty", "值日情况"),
]

# 这些来源模块已独立展示其事件（含分值），其同步出的 PointRecord 不再重复计入「积分变动」。
# 保留：manual（手工调整）、homework（作业正分无独立展示）等。
SYNCED_POINT_SOURCES = ("reward", "attendance", "classroom_discipline", "dorm_discipline")


def _sort_events(events):
    """按（业务日期，录入时间）倒序，同一天内按实际录入先后排列。"""
    return sorted(
        events,
        key=lambda e: (e["date"], e.get("created_at") or e["date"]),
        reverse=True,
    )


def get_student_all_events(student, date_from=None, date_to=None):
    """汇总学生全部成长事件（按时间倒序），并附模块标签。

    去重：奖惩/考勤/课堂纪律/宿舍纪律等来源模块已展示的事件（含分值），
    其同步出的 PointRecord 不再重复计入「积分变动」，避免同一事件计两次。
    """
    events = []
    for module, label in ALL_MODULES:
        try:
            module_events = get_student_events(student, module, date_from, date_to)
        except Exception:
            module_events = []
        for event in module_events:
            if module == "points" and event.get("code") in SYNCED_POINT_SOURCES:
                continue
            event["module"] = label
            event["module_key"] = module
            events.append(event)
    return _sort_events(events)


def get_student_events(student, module, date_from=None, date_to=None):
    events = []
    if module == "rewards":
        from apps.rewards.models import RewardRecord
        records = _apply_dates(RewardRecord.objects.filter(student=student, is_deleted=False).select_related("item"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "created_at": record.created_at, "item": record.item.name if record.item else record.custom_name or record.get_record_type_display(), "code": record.record_type, "points": record.points, "note": record.description, "adverse": record.points < 0})
    elif module == "points":
        from apps.rewards.models import PointRecord
        records = _apply_dates(PointRecord.objects.filter(student=student, is_deleted=False), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "created_at": record.created_at, "item": record.reason, "code": record.source_type, "points": record.points, "note": record.manual_reason, "adverse": record.points < 0})
    elif module == "discipline":
        from apps.discipline.models import ClassroomDisciplineRecord
        records = _apply_dates(ClassroomDisciplineRecord.objects.filter(student=student, is_deleted=False).select_related("item"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "created_at": record.created_at, "item": record.item.name if record.item else record.custom_content, "code": record.item.name if record.item else "custom", "points": -abs(record.points_deducted), "note": record.remarks or record.description, "adverse": True})
    elif module == "dormitory":
        from apps.discipline.models import DormDisciplineRecord
        from apps.dormitory.models import DormAssignment, DormHygieneCheck
        records = _apply_dates(DormDisciplineRecord.objects.filter(student=student, is_deleted=False).select_related("item"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "created_at": record.created_at, "item": record.item.name if record.item else record.custom_content, "code": record.item.name if record.item else "discipline", "points": -abs(record.points_deducted), "note": record.remarks or record.description, "adverse": True})
        room_ids = DormAssignment.objects.filter(student=student, is_current=True).values_list("room_id", flat=True)
        checks = _apply_dates(DormHygieneCheck.objects.filter(room_id__in=room_ids, is_deleted=False), "date", date_from, date_to)
        for check in checks:
            events.append({"date": check.date, "created_at": check.created_at, "item": f"宿舍卫生 {check.get_grade_display() or '检查'}", "code": "hygiene", "points": 0, "note": check.rectification or check.remarks, "adverse": check.grade in {"poor", "needs_improvement"}})
    elif module == "attendance":
        from apps.attendance.models import AttendanceRecord
        records = _apply_dates(AttendanceRecord.objects.filter(student=student).exclude(status="normal"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "created_at": record.created_at, "item": record.get_status_display(), "code": record.status, "points": record.points_deducted, "note": record.reason, "adverse": True})
    elif module == "homework":
        from apps.homework.models import HomeworkRecord
        negative = {"unsubmitted", "late", "needs_correction", "poor"}
        records = HomeworkRecord.objects.filter(student=student).select_related("task")
        if date_from:
            records = records.filter(task__assigned_date__gte=date_from)
        if date_to:
            records = records.filter(task__assigned_date__lte=date_to)
        for record in records:
            if record.status in negative or record.status.startswith("custom:"):
                events.append({"date": record.submission_date or record.task.assigned_date, "created_at": record.created_at, "item": f"{record.task.title}：{record.status_display}", "code": record.status, "points": 0, "note": record.remark, "adverse": True})
    elif module == "duty":
        from apps.duty.models import DutyRecord, DutyAbsenceRecord
        records = _apply_dates(DutyRecord.objects.filter(student=student).select_related("group"), "date", date_from, date_to)
        for record in records:
            adverse = record.is_absent or not record.is_completed or record.evaluation == "poor"
            if adverse:
                label = "缺岗" if record.is_absent else ("未完成" if not record.is_completed else "评价差")
                events.append({"date": record.date, "created_at": record.created_at, "item": f"{record.group.name}：{label}", "code": label, "points": 0, "note": record.remark, "adverse": True})
        # 值日缺勤记录（扣分已同步积分，供预警与成长足迹）
        absences = _apply_dates(DutyAbsenceRecord.objects.filter(student=student), "date", date_from, date_to)
        for record in absences:
            events.append({
                "date": record.date, "created_at": record.created_at,
                "item": f"{record.group_name or record.task_name or '值日'}：缺勤",
                "code": "absent", "points": -record.points,
                "note": record.remark, "adverse": True,
            })
    elif module == "evaluation":
        from apps.evaluation.models import EvaluationResult
        records = EvaluationResult.objects.filter(student=student).select_related("project").order_by("-created_at")
        if date_from:
            records = records.filter(created_at__date__gte=date_from)
        if date_to:
            records = records.filter(created_at__date__lte=date_to)
        for record in records:
            events.append({
                "date": record.created_at.date(),
                "created_at": record.created_at,
                "item": f"{record.project.name} · 第{record.rank}名",
                "code": "evaluation",
                "points": 0,
                "note": f"{record.period_label} · 评分 {record.total_score} 分",
                "adverse": False,
            })
    return _sort_events(events)
