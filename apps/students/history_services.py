def _apply_dates(queryset, date_field, date_from=None, date_to=None):
    if date_from:
        queryset = queryset.filter(**{f"{date_field}__gte": date_from})
    if date_to:
        queryset = queryset.filter(**{f"{date_field}__lte": date_to})
    return queryset


def get_student_events(student, module, date_from=None, date_to=None):
    events = []
    if module == "rewards":
        from apps.rewards.models import RewardRecord
        records = _apply_dates(RewardRecord.objects.filter(student=student, is_deleted=False).select_related("item"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "item": record.item.name if record.item else record.custom_name or record.get_record_type_display(), "code": record.record_type, "points": record.points, "note": record.description, "adverse": record.points < 0})
    elif module == "points":
        from apps.rewards.models import PointRecord
        records = _apply_dates(PointRecord.objects.filter(student=student, is_deleted=False), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "item": record.reason, "code": record.source_type, "points": record.points, "note": record.manual_reason, "adverse": record.points < 0})
    elif module == "discipline":
        from apps.discipline.models import ClassroomDisciplineRecord
        records = _apply_dates(ClassroomDisciplineRecord.objects.filter(student=student, is_deleted=False).select_related("item"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "item": record.item.name if record.item else record.custom_content, "code": record.item.name if record.item else "custom", "points": -abs(record.points_deducted), "note": record.remarks or record.description, "adverse": True})
    elif module == "dormitory":
        from apps.discipline.models import DormDisciplineRecord
        from apps.dormitory.models import DormAssignment, DormHygieneCheck
        records = _apply_dates(DormDisciplineRecord.objects.filter(student=student, is_deleted=False).select_related("item"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "item": record.item.name if record.item else record.custom_content, "code": record.item.name if record.item else "discipline", "points": -abs(record.points_deducted), "note": record.remarks or record.description, "adverse": True})
        room_ids = DormAssignment.objects.filter(student=student, is_current=True).values_list("room_id", flat=True)
        checks = _apply_dates(DormHygieneCheck.objects.filter(room_id__in=room_ids, is_deleted=False), "date", date_from, date_to)
        for check in checks:
            events.append({"date": check.date, "item": f"宿舍卫生 {check.get_grade_display() or '检查'}", "code": "hygiene", "points": 0, "note": check.rectification or check.remarks, "adverse": check.grade in {"poor", "needs_improvement"}})
    elif module == "attendance":
        from apps.attendance.models import AttendanceRecord
        records = _apply_dates(AttendanceRecord.objects.filter(student=student).exclude(status="normal"), "date", date_from, date_to)
        for record in records:
            events.append({"date": record.date, "item": record.get_status_display(), "code": record.status, "points": 0, "note": record.reason, "adverse": True})
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
                events.append({"date": record.submission_date or record.task.assigned_date, "item": f"{record.task.title}：{record.status_display}", "code": record.status, "points": 0, "note": record.remark, "adverse": True})
    elif module == "duty":
        from apps.duty.models import DutyRecord
        records = _apply_dates(DutyRecord.objects.filter(student=student).select_related("group"), "date", date_from, date_to)
        for record in records:
            adverse = record.is_absent or not record.is_completed or record.evaluation == "poor"
            if adverse:
                label = "缺岗" if record.is_absent else ("未完成" if not record.is_completed else "评价差")
                events.append({"date": record.date, "item": f"{record.group.name}：{label}", "code": label, "points": 0, "note": record.remark, "adverse": True})
    return sorted(events, key=lambda event: event["date"], reverse=True)
