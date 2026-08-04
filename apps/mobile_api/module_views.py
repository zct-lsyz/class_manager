from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.mobile_api.auth import api_error, api_ok, mobile_api, parse_data
from apps.mobile_api.resources import _after_save, _apply_data, _force_scope, get_spec
from apps.mobile_api.serializers import serialize_instance


@mobile_api(["GET"])
def dashboard(request):
    from apps.attendance.models import AttendanceRecord
    from apps.backups.models import BackupRecord
    from apps.classes.models import Semester
    from apps.homework.models import HomeworkRecord, HomeworkStatus
    from apps.students.models import Student
    from apps.todos.models import TodoItem

    user = request.mobile_user
    current = get_current_class(user)
    if not current:
        return api_ok({"has_current_class": False})
    today = timezone.localdate()
    semester = Semester.objects.filter(school_class=current, is_current=True).first()
    students = Student.objects.filter(school_class=current, is_deleted=False)
    week_start = today - timezone.timedelta(days=today.weekday())
    negative_custom = HomeworkStatus.objects.filter(
        school_class=current, is_active=True, is_positive=False,
    ).values_list("pk", flat=True)
    status_filter = Q(status__in=["unsubmitted", "late"])
    for status_id in negative_custom:
        status_filter |= Q(status=f"custom:{status_id}")
    todos = TodoItem.objects.filter(
        created_by=user, is_deleted=False, is_completed=False,
    ).select_related("student").order_by("priority", "deadline", "-created_at")[:8]
    last_backup = BackupRecord.objects.filter(user=user).order_by("-created_at").first()
    return api_ok({
        "has_current_class": True,
        "today": today.isoformat(),
        "class": {"id": current.pk, "name": current.name},
        "semester": {"id": semester.pk, "name": semester.get_display_name()} if semester else None,
        "teaching_week": _teaching_week(semester, today),
        "stats": {
            "students": students.count(),
            "male": students.filter(gender="male").count(),
            "female": students.filter(gender="female").count(),
            "today_absent": AttendanceRecord.objects.filter(
                school_class=current, date=today,
            ).exclude(status="normal").values("student_id").distinct().count(),
            "week_unsubmitted": HomeworkRecord.objects.filter(
                task__school_class=current, task__assigned_date__gte=week_start,
                task__assigned_date__lte=today,
            ).filter(status_filter).count(),
            "active_todos": TodoItem.objects.filter(
                created_by=user, is_deleted=False, is_completed=False,
            ).count(),
        },
        "todos": [serialize_instance(item, get_spec("todos").fields) for item in todos],
        "backup": {
            "status": last_backup.status,
            "created_at": last_backup.created_at.isoformat(),
            "error": last_backup.error_message,
        } if last_backup else None,
    })


def _teaching_week(semester, today):
    if not semester or not semester.start_date or today < semester.start_date:
        return 0 if semester and semester.start_date and today < semester.start_date else None
    if semester.end_date and today > semester.end_date:
        return None
    return (today - semester.start_date).days // 7 + 1


@mobile_api(["GET"])
def course_schedule(request):
    from apps.classes.models import CoursePeriod, CourseScheduleEntry, Semester
    current = get_current_class(request.mobile_user)
    semester = Semester.objects.filter(school_class=current, is_current=True).first()
    entries = CourseScheduleEntry.objects.filter(
        school_class=current, semester=semester,
    ).select_related("course").order_by("weekday", "period") if current and semester else []
    periods = CoursePeriod.objects.filter(
        school_class=current, semester=semester,
    ).order_by("period") if current and semester else []
    return api_ok({
        "semester": semester.get_display_name() if semester else None,
        "weekdays": [{"value": value, "label": label} for value, label in CourseScheduleEntry.WEEKDAY_CHOICES],
        "periods": [{
            "period": row.period, "name": row.name,
            "start_time": row.start_time.isoformat(timespec="minutes") if row.start_time else None,
            "end_time": row.end_time.isoformat(timespec="minutes") if row.end_time else None,
        } for row in periods],
        "entries": [{
            "id": row.pk, "weekday": row.weekday, "period": row.period,
            "course": row.course.name if row.course else row.subject,
            "teacher": row.teacher or (row.course.teacher if row.course else ""),
            "remarks": row.remarks,
        } for row in entries],
    })


@mobile_api(["GET"])
def seating(request):
    from apps.seating.models import SeatAssignment, SeatPlan
    current = get_current_class(request.mobile_user)
    plan = SeatPlan.objects.filter(school_class=current, is_active=True).select_related("layout").order_by("-created_at").first() if current else None
    if not plan:
        return api_ok({"plan": None, "assignments": []})
    assignments = SeatAssignment.objects.filter(seat_plan=plan).select_related("student").order_by("row", "col")
    return api_ok({
        "plan": {
            "id": plan.pk, "version": plan.version, "reason": plan.reason,
            "layout": {
                "name": plan.layout.name, "rows": plan.layout.rows, "cols": plan.layout.cols,
                "seats_per_desk": plan.layout.seats_per_desk,
                "aisle_positions": plan.layout.aisle_positions,
                "podium_position": plan.layout.podium_position,
            },
        },
        "assignments": [{
            "id": row.pk, "row": row.row, "col": row.col,
            "student_id": row.student_id, "student_name": row.student.name,
            "locked": row.is_locked,
        } for row in assignments],
    })


@mobile_api(["GET"])
def duty_roster(request):
    from apps.duty.models import DutyRoster, DutyRosterEntry, DutyRosterTask
    current = get_current_class(request.mobile_user)
    roster_id = request.GET.get("roster_id")
    qs = DutyRoster.objects.filter(school_class=current).order_by("-is_current", "-date_start") if current else DutyRoster.objects.none()
    roster = qs.filter(pk=roster_id).first() if roster_id else qs.first()
    if not roster:
        return api_ok({"roster": None, "tasks": [], "entries": []})
    tasks = DutyRosterTask.objects.filter(roster=roster).select_related("task").order_by("sort_order", "pk")
    entries = DutyRosterEntry.objects.filter(roster=roster).select_related("task", "student").order_by("day_index", "task__sort_order", "sort_order")
    return api_ok({
        "available": [{"id": row.pk, "name": row.name, "current": row.is_current} for row in qs[:30]],
        "roster": {
            "id": roster.pk, "name": roster.name, "date_start": roster.date_start.isoformat(),
            "date_end": roster.date_end.isoformat(), "day_count": roster.day_count,
            "status": roster.status, "current": roster.is_current,
        },
        "tasks": [{"id": row.task_id, "name": row.task.name, "area": row.task.area, "people_count": row.people_count} for row in tasks],
        "entries": [{
            "id": row.pk, "day_index": row.day_index,
            "date": (roster.date_start + timezone.timedelta(days=row.day_index)).isoformat(),
            "task_id": row.task_id, "task_name": row.task.name,
            "student_id": row.student_id, "student_name": row.student.name,
        } for row in entries],
    })


def _warning_rows(user):
    from apps.attendance.models import WarningRule
    from apps.dashboard.views import _warning_events
    from apps.students.models import Student
    current = get_current_class(user)
    rules = WarningRule.objects.filter(school_class=current, is_active=True) if current else []
    students = Student.objects.filter(school_class=current, is_deleted=False) if current else []
    rows = []
    for student in students:
        matched = []
        for rule in rules:
            events = _warning_events(student, rule)
            value = len(events) if rule.unit == "count" else sum(abs(item["points"]) for item in events if item["points"] < 0)
            if value >= rule.threshold:
                matched.append({
                    "rule_id": rule.pk, "rule": rule.name, "content": rule.content,
                    "value": value, "threshold": rule.threshold, "unit": rule.unit,
                    "events": [{**event, "date": event["date"].isoformat()} for event in events],
                })
        if matched:
            rows.append({"student_id": student.pk, "student_name": student.name, "warnings": matched})
    return rows


@mobile_api(["GET"])
def warnings(request):
    rows = _warning_rows(request.mobile_user)
    return api_ok({"student_count": len(rows), "students": rows})


@mobile_api(["GET"])
def growth(request):
    from apps.students.history_services import get_student_all_events
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    student = Student.objects.filter(
        pk=request.GET.get("student_id"), school_class=current, is_deleted=False,
    ).first()
    if not student:
        return api_error("请选择当前班级的学生。", 400, "student_required")
    events = get_student_all_events(
        student, request.GET.get("date_from") or None, request.GET.get("date_to") or None,
    )
    module = request.GET.get("module", "")
    if module:
        events = [item for item in events if item["module_key"] == module]
    return api_ok({
        "student": {"id": student.pk, "name": student.name},
        "events": [{**item, "date": item["date"].isoformat()} for item in events[:500]],
    })


@mobile_api(["GET"])
def ranking(request):
    from apps.rewards.models import PointRecord, RankingSetting
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    setting, _ = RankingSetting.objects.get_or_create(school_class=current)
    qs = PointRecord.objects.filter(
        school_class=current, source_type__in=setting.enabled_source_types(), is_deleted=False,
    ).select_related("student")
    if request.GET.get("date_from"):
        qs = qs.filter(date__gte=request.GET["date_from"])
    if request.GET.get("date_to"):
        qs = qs.filter(date__lte=request.GET["date_to"])
    totals = defaultdict(int)
    reasons = defaultdict(lambda: defaultdict(lambda: {"total": 0, "count": 0}))
    for row in qs:
        totals[row.student_id] += row.points
        reasons[row.student_id][row.reason]["total"] += row.points
        reasons[row.student_id][row.reason]["count"] += 1
    rows = []
    for student in Student.objects.filter(school_class=current, is_deleted=False):
        detail = sorted(reasons[student.pk].items(), key=lambda item: abs(item[1]["total"]), reverse=True)[:6]
        rows.append({
            "student_id": student.pk, "student_name": student.name, "total": totals[student.pk],
            "reasons": [{"reason": name, **data} for name, data in detail],
        })
    rows.sort(key=lambda item: (-item["total"], item["student_name"]))
    rank = 0
    last = None
    for index, row in enumerate(rows, 1):
        if row["total"] != last:
            rank = index
            last = row["total"]
        row["rank"] = rank
    return api_ok({"enabled_labels": setting.enabled_labels(), "ranking": rows})


@mobile_api(["GET"])
def score_analysis(request):
    from apps.scores.analysis_exports import compute_analysis_data
    from apps.scores.models import Exam
    current = get_current_class(request.mobile_user)
    exams = Exam.objects.filter(school_class=current, is_deleted=False).order_by("-date") if current else []
    exam = exams.filter(pk=request.GET.get("exam_id")).first() if request.GET.get("exam_id") else exams.first()
    if not exam:
        return api_ok({"exam": None, "exams": []})
    data = compute_analysis_data(current, exam)
    return api_ok({
        "exams": [{"id": row.pk, "name": row.name, "date": row.date.isoformat()} for row in exams[:50]],
        "exam": {"id": exam.pk, "name": exam.name, "date": exam.date.isoformat(), "published": exam.is_published},
        "subjects": [{"name": name, **values} for name, values in data["analysis_data"].items()],
        "total": {"count": data["total_count"], "avg": data["total_avg"], "max": data["total_max"]},
        "students": [{
            "student_id": row["student"].pk, "student_name": row["student"].name,
            "total_score": row["total_score"], "rank": row["rank"],
            "grade_rank": row["total_grade_rank"], "city_rank": row["total_city_rank"],
            "subjects": row["subjects"],
        } for row in data["class_total_table"]],
    })


@mobile_api(["POST"])
def batch_create(request, resource):
    spec = get_spec(resource)
    if not spec or resource not in {
        "attendance", "homework_records", "classroom_discipline", "dorm_discipline",
        "rewards", "conversations", "home_school_contacts", "concerns", "scores",
    }:
        return api_error("该资源不支持批量登记。", 404, "batch_not_supported")
    data = parse_data(request)
    records = data.get("records")
    if not isinstance(records, list):
        student_ids = data.get("student_ids", [])
        if not isinstance(student_ids, list) or not student_ids:
            return api_error("请提供 records 或 student_ids。")
        records = [{**data, "student": student_id} for student_id in student_ids]
    created = []
    with transaction.atomic():
        for values in records:
            instance = spec.model()
            fake_request = request
            _apply_data(instance, spec, values, fake_request)
            _force_scope(instance, spec, request.mobile_user, True)
            instance.full_clean()
            if resource == "homework_records":
                instance, _ = spec.model.objects.update_or_create(
                    task=instance.task, student=instance.student,
                    defaults={name: getattr(instance, name) for name in spec.editable if name not in {"task", "student"}},
                )
            elif resource == "scores":
                instance, _ = spec.model.objects.update_or_create(
                    exam_subject=instance.exam_subject, student=instance.student,
                    defaults={
                        "exam": instance.exam, "score": instance.score, "status": instance.status,
                        "grade_rank": instance.grade_rank, "city_rank": instance.city_rank,
                        "remarks": instance.remarks, "is_deleted": False,
                    },
                )
            else:
                instance.save()
            _after_save(instance, spec, request.mobile_user)
            created.append(serialize_instance(instance, spec.fields))
    return api_ok({"count": len(created), "records": created}, 201)


@mobile_api(["POST"])
def assign_bed(request, pk):
    from apps.classes.models import Semester
    from apps.dormitory.models import DormAssignment, DormBed
    from apps.dormitory.services import release_bed
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    bed = DormBed.objects.filter(pk=pk, room__building__school_class=current).select_related("room").first()
    if not bed:
        return api_error("床位不存在。", 404, "not_found")
    data = parse_data(request)
    student_id = data.get("student_id")
    with transaction.atomic():
        previous = list(Student.objects.filter(dorm_assignments__is_current=True).filter(
            Q(dorm_assignments__bed=bed) | Q(pk=student_id or None),
        ).distinct())
        if student_id:
            student = Student.objects.filter(pk=student_id, school_class=current, is_deleted=False).first()
            if not student:
                raise ValidationError("学生不存在或不属于当前班级。")
            DormAssignment.objects.filter(student=student, is_current=True).update(is_current=False, bed=None)
            release_bed(bed)
            DormAssignment.objects.create(
                student=student, room=bed.room, bed=bed, is_current=True,
                semester=Semester.objects.filter(school_class=current, is_current=True).first(),
            )
            student.dormitory = str(bed.room)
            student.bed_number = bed.bed_number
            student.save(update_fields=["dormitory", "bed_number", "updated_at"])
        else:
            release_bed(bed)
        for student in previous:
            if not student.dorm_assignments.filter(is_current=True).exists():
                student.dormitory = ""
                student.bed_number = ""
                student.save(update_fields=["dormitory", "bed_number", "updated_at"])
    return api_ok()


@mobile_api(["GET"])
def dorm_overview(request):
    from apps.dormitory.models import DormAssignment, DormBed, DormBuilding, DormRoom
    current = get_current_class(request.mobile_user)
    buildings = DormBuilding.objects.filter(school_class=current).order_by("sort_order", "name") if current else []
    rooms = DormRoom.objects.filter(building__school_class=current).select_related("building", "monitor").order_by("building__sort_order", "room_number") if current else []
    room_rows = []
    for room in rooms:
        assignments = {
            row.bed_id: row for row in DormAssignment.objects.filter(
                room=room, is_current=True,
            ).select_related("student", "bed")
        }
        room_rows.append({
            "id": room.pk, "building_id": room.building_id, "building": room.building.name,
            "room_number": room.room_number, "floor": room.floor,
            "room_type": room.room_type, "bed_count": room.bed_count,
            "monitor_id": room.monitor_id, "monitor_name": room.monitor.name if room.monitor else "",
            "active": room.is_active, "remarks": room.remarks,
            "beds": [{
                "id": bed.pk, "bed_number": bed.bed_number, "active": bed.is_active,
                "student_id": assignments[bed.pk].student_id if bed.pk in assignments else None,
                "student_name": assignments[bed.pk].student.name if bed.pk in assignments else "",
            } for bed in DormBed.objects.filter(room=room).order_by("bed_number")],
        })
    return api_ok({
        "buildings": [{"id": row.pk, "name": row.name, "floors": row.floors} for row in buildings],
        "rooms": room_rows,
    })


@mobile_api(["POST"])
def set_room_monitor(request, pk):
    from apps.dormitory.models import DormAssignment, DormRoom
    current = get_current_class(request.mobile_user)
    room = DormRoom.objects.filter(pk=pk, building__school_class=current).first()
    if not room:
        return api_error("宿舍不存在。", 404, "not_found")
    student_id = parse_data(request).get("student_id")
    if student_id:
        assignment = DormAssignment.objects.filter(
            room=room, student_id=student_id, is_current=True,
        ).select_related("student").first()
        if not assignment:
            return api_error("舍长必须是当前宿舍已分配的学生。")
        room.monitor = assignment.student
    else:
        room.monitor = None
    room.save(update_fields=["monitor", "updated_at"])
    return api_ok()


@mobile_api(["GET", "PUT"])
def hygiene_scores(request, pk):
    from apps.dormitory.models import DormHygieneCheck, DormHygieneItem, DormHygieneItemScore
    current = get_current_class(request.mobile_user)
    check = DormHygieneCheck.objects.filter(pk=pk, school_class=current, is_deleted=False).select_related("room").first()
    if not check:
        return api_error("卫生检查记录不存在。", 404, "not_found")
    items = list(DormHygieneItem.objects.filter(school_class=current).order_by("sort_order", "name"))
    if request.method == "PUT":
        values = parse_data(request).get("scores", [])
        if not isinstance(values, list):
            return api_error("scores 必须是数组。")
        allowed = {item.pk: item for item in items}
        total = 0
        full = 0
        with transaction.atomic():
            for value in values:
                item = allowed.get(int(value.get("item_id", 0)))
                if not item:
                    raise ValidationError("卫生检查项不存在或不属于当前班级。")
                score = max(0, min(int(value.get("score", 0)), item.full_score))
                DormHygieneItemScore.objects.update_or_create(
                    check_record=check, item=item,
                    defaults={"score": score, "deduction_reason": str(value.get("deduction_reason", ""))},
                )
            existing = DormHygieneItemScore.objects.filter(check_record=check).select_related("item")
            for row in existing:
                total += row.score
                full += row.item.full_score
            ratio = total / full if full else 0
            check.total_score = total
            check.grade = "excellent" if ratio >= .9 else "good" if ratio >= .8 else "fair" if ratio >= .6 else "poor"
            check.save(update_fields=["total_score", "grade", "updated_at"])
    scores = {row.item_id: row for row in DormHygieneItemScore.objects.filter(check_record=check)}
    return api_ok({
        "check_id": check.pk, "room": str(check.room), "date": check.date.isoformat(),
        "total_score": check.total_score, "grade": check.grade,
        "items": [{
            "item_id": item.pk, "name": item.name, "full_score": item.full_score,
            "score": scores[item.pk].score if item.pk in scores else None,
            "deduction_reason": scores[item.pk].deduction_reason if item.pk in scores else "",
        } for item in items],
    })


@mobile_api(["GET"])
def student_score_analysis(request, pk):
    from apps.scores.models import Exam, ExamSubject, ExamTotal, Score
    from apps.students.models import Student
    current = get_current_class(request.mobile_user)
    student = Student.objects.filter(pk=pk, school_class=current, is_deleted=False).first()
    if not student:
        return api_error("学生不存在。", 404, "not_found")
    exams = list(Exam.objects.filter(school_class=current, is_deleted=False).order_by("date"))
    total_map = {row.exam_id: row for row in ExamTotal.objects.filter(exam__in=exams, student=student)}
    rows = []
    for exam in exams:
        subjects = []
        calculated_total = 0.0
        has_score = False
        for exam_subject in ExamSubject.objects.filter(exam=exam).select_related("subject"):
            score = Score.objects.filter(
                exam_subject=exam_subject, student=student, is_deleted=False,
            ).first()
            subjects.append({
                "subject": exam_subject.subject.name, "full_score": exam_subject.full_score,
                "score": float(score.score) if score and score.score is not None else None,
                "status": score.status if score else None, "rank": score.rank if score else None,
                "grade_rank": score.grade_rank if score else None, "city_rank": score.city_rank if score else None,
            })
            if score and score.status == "normal" and score.score is not None:
                calculated_total += float(score.score)
                has_score = True
        official = total_map.get(exam.pk)
        if has_score or official:
            rows.append({
                "exam_id": exam.pk, "exam": exam.name, "date": exam.date.isoformat(),
                "total": float(official.total_score) if official and official.total_score is not None else round(calculated_total, 1),
                "class_rank": official.class_rank if official else None,
                "grade_rank": official.grade_rank if official else None,
                "city_rank": official.city_rank if official else None,
                "subjects": subjects,
            })
    return api_ok({"student": {"id": student.pk, "name": student.name}, "history": rows})


@mobile_api(["GET"])
def notifications(request):
    from apps.todos.models import TodoItem
    now = timezone.now()
    upcoming = TodoItem.objects.filter(
        created_by=request.mobile_user, is_deleted=False, is_completed=False,
        deadline__isnull=False, deadline__lte=now + timezone.timedelta(days=30),
    ).select_related("student").order_by("deadline")[:200]
    warnings_data = _warning_rows(request.mobile_user)
    return api_ok({
        "server_time": now.isoformat(),
        "todos": [serialize_instance(row, get_spec("todos").fields) for row in upcoming],
        "warnings": warnings_data,
    })
