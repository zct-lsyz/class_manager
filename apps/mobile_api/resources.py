from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.paginator import Paginator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.mobile_api.auth import api_error, api_ok, mobile_api, parse_data
from apps.mobile_api.serializers import field_schema, serialize_instance


@dataclass
class ResourceSpec:
    key: str
    title: str
    model: type
    fields: tuple
    editable: tuple
    search: tuple = ()
    order: tuple = ("-pk",)
    scope: str = "current"
    module: str = ""
    soft_name: str = ""
    allow_delete: bool = True
    relation_filters: dict = dc_field(default_factory=dict)


def _specs():
    from apps.attendance.models import AttendanceReason, AttendanceRecord, WarningRule
    from apps.backups.models import StorageAlertRule
    from apps.classes.models import SchoolClass, Semester
    from apps.communications.models import ConcernRecord, HomeSchoolContact, StudentConversation
    from apps.dashboard.models import Countdown, TeachingWebsite
    from apps.discipline.models import ClassroomDisciplineRecord, ConfigurableItem, DormDisciplineRecord
    from apps.dormitory.models import DormAssignment, DormBuilding, DormHygieneCheck, DormHygieneItem, DormRoom
    from apps.homework.models import HomeworkRecord, HomeworkStatus, HomeworkTask, Subject
    from apps.rewards.models import PointRecord, RankingSetting, RewardItem, RewardRecord
    from apps.scores.models import Exam, ExamSubject, ExamTotal, ExternalClass, ExternalScore, ExternalTotal, GradeLine, Score, SupportFollowUp, SupportPlan
    from apps.students.models import Guardian, Student
    from apps.todos.models import TodoItem

    values = [
        ResourceSpec("countdowns", "工作台倒计时", Countdown,
            ("name", "target_date", "is_active"), ("name", "target_date", "is_active"),
            ("name",), ("target_date", "pk"), "user", "dashboard"),
        ResourceSpec("teaching_websites", "常用教学网站", TeachingWebsite,
            ("name", "url", "sort_order"), ("name", "url", "sort_order"),
            ("name", "url"), ("sort_order", "name"), "user", "dashboard"),
        ResourceSpec("classes", "班级", SchoolClass,
            ("name", "grade", "school_name", "head_teacher", "classroom_name", "is_current", "sort_order"),
            ("name", "grade", "school_name", "head_teacher", "classroom_name", "is_current", "sort_order"),
            ("name", "grade", "school_name"), ("sort_order", "pk"), "account", "classes"),
        ResourceSpec("semesters", "学期", Semester,
            ("school_class", "academic_year", "semester_type", "is_current", "is_archived", "start_date", "end_date"),
            ("school_class", "academic_year", "semester_type", "is_current", "is_archived", "start_date", "end_date"),
            ("academic_year",), ("-academic_year", "semester_type"), "account", "semesters", allow_delete=False),
        ResourceSpec("students", "学生花名册", Student,
            ("school_class", "student_id", "name", "gender", "birth_date", "height", "vision", "seat_requirement", "class_position", "home_address", "is_league_member", "is_boarder", "dormitory", "bed_number", "primary_contact", "primary_phone", "secondary_contact", "secondary_phone", "remarks", "sort_order"),
            ("school_class", "student_id", "name", "gender", "birth_date", "height", "vision", "seat_requirement", "class_position", "home_address", "is_league_member", "is_boarder", "dormitory", "bed_number", "primary_contact", "primary_phone", "secondary_contact", "secondary_phone", "remarks", "sort_order"),
            ("student_id", "name", "primary_contact", "primary_phone"), ("sort_order", "student_id"), "current", "students", "student"),
        ResourceSpec("guardians", "家长联系方式", Guardian,
            ("student", "father_name", "father_phone", "mother_name", "mother_phone", "other_guardian", "primary_contact", "home_address", "remarks"),
            ("student", "father_name", "father_phone", "mother_name", "mother_phone", "other_guardian", "primary_contact", "home_address", "remarks"),
            ("student__name", "student__student_id", "father_name", "mother_name"), ("student__student_id",), "current", "students", allow_delete=False),
        ResourceSpec("todos", "待办事项", TodoItem,
            ("title", "priority", "deadline", "student", "is_completed", "completed_at", "source_type", "source_id"),
            ("title", "priority", "deadline", "student", "is_completed"),
            ("title", "student__name"), ("is_completed", "priority", "deadline", "-created_at"), "account", "todos", "todo"),
        ResourceSpec("attendance", "考勤记录", AttendanceRecord,
            ("student", "date", "period", "status", "reason", "points_deducted", "leave_proof", "needs_follow_up", "follow_up_date"),
            ("student", "date", "period", "status", "reason", "points_deducted", "leave_proof", "needs_follow_up", "follow_up_date"),
            ("student__name", "reason"), ("-date", "student__student_id"), "current", "attendance", allow_delete=False),
        ResourceSpec("attendance_reasons", "考勤原因", AttendanceReason,
            ("name", "is_active", "sort_order"), ("name", "is_active", "sort_order"),
            ("name",), ("sort_order", "name"), "current", "attendance"),
        ResourceSpec("warning_rules", "预警规则", WarningRule,
            ("name", "content", "unit", "threshold", "is_active"),
            ("name", "content", "unit", "threshold", "is_active"),
            ("name",), ("-is_active", "name"), "current", "attendance"),
        ResourceSpec("subjects", "科目", Subject,
            ("name", "short_name", "is_active", "sort_order"),
            ("name", "short_name", "is_active", "sort_order"),
            ("name", "short_name"), ("sort_order", "name"), "subjects", "homework"),
        ResourceSpec("homework_statuses", "作业状态", HomeworkStatus,
            ("name", "is_positive", "is_active", "sort_order"),
            ("name", "is_positive", "is_active", "sort_order"),
            ("name",), ("sort_order", "name"), "current", "homework"),
        ResourceSpec("homework_tasks", "作业任务", HomeworkTask,
            ("subject", "title", "content", "assigned_date", "due_date", "person_in_charge", "remarks", "needs_follow_up", "follow_up_date"),
            ("subject", "title", "content", "assigned_date", "due_date", "person_in_charge", "remarks", "needs_follow_up", "follow_up_date"),
            ("title", "content", "subject__name"), ("-assigned_date", "-pk"), "current", "homework"),
        ResourceSpec("homework_records", "作业检查记录", HomeworkRecord,
            ("task", "student", "status", "submission_date", "correction_deadline", "correction_result", "remark"),
            ("task", "student", "status", "submission_date", "correction_deadline", "correction_result", "remark"),
            ("student__name", "task__title", "remark"), ("-task__assigned_date", "student__student_id"), "current", "homework"),
        ResourceSpec("discipline_items", "纪律条目", ConfigurableItem,
            ("name", "module", "category", "default_severity", "default_points", "needs_follow_up", "is_active", "sort_order", "description"),
            ("name", "module", "category", "default_severity", "default_points", "needs_follow_up", "is_active", "sort_order", "description"),
            ("name", "category"), ("module", "sort_order", "name"), "current", "discipline"),
        ResourceSpec("classroom_discipline", "课堂纪律", ClassroomDisciplineRecord,
            ("student", "date", "time", "period", "subject", "item", "custom_content", "severity", "description", "action_taken", "points_deducted", "needs_follow_up", "follow_up_date", "follow_up_result", "remarks"),
            ("student", "date", "time", "period", "subject", "item", "custom_content", "severity", "description", "action_taken", "points_deducted", "needs_follow_up", "follow_up_date", "follow_up_result", "remarks"),
            ("student__name", "custom_content", "description"), ("-date", "-pk"), "current", "discipline", "classroomdiscipline"),
        ResourceSpec("dorm_discipline", "宿舍纪律", DormDisciplineRecord,
            ("student", "dorm_room", "date", "time", "item", "custom_content", "severity", "description", "action_taken", "points_deducted", "needs_follow_up", "follow_up_date", "follow_up_result", "remarks"),
            ("student", "dorm_room", "date", "time", "item", "custom_content", "severity", "description", "action_taken", "points_deducted", "needs_follow_up", "follow_up_date", "follow_up_result", "remarks"),
            ("student__name", "custom_content", "description"), ("-date", "-pk"), "current", "dormitory", "dormdiscipline"),
        ResourceSpec("dorm_buildings", "宿舍楼", DormBuilding,
            ("name", "floors", "sort_order"), ("name", "floors", "sort_order"),
            ("name",), ("sort_order", "name"), "current", "dormitory"),
        ResourceSpec("dorm_rooms", "宿舍", DormRoom,
            ("building", "room_number", "floor", "room_type", "bed_count", "monitor", "is_active", "remarks"),
            ("building", "room_number", "floor", "room_type", "bed_count", "monitor", "is_active", "remarks"),
            ("room_number", "building__name"), ("building__sort_order", "room_number"), "current", "dormitory"),
        ResourceSpec("dorm_assignments", "住宿分配", DormAssignment,
            ("student", "room", "bed", "is_current", "assigned_date", "end_date"),
            ("student", "room", "bed", "is_current", "end_date"),
            ("student__name", "room__room_number", "bed__bed_number"), ("room__room_number", "bed__bed_number"), "current", "dormitory", allow_delete=False),
        ResourceSpec("hygiene_items", "卫生检查项", DormHygieneItem,
            ("name", "full_score", "default_deduction", "is_active", "sort_order"),
            ("name", "full_score", "default_deduction", "is_active", "sort_order"),
            ("name",), ("sort_order", "name"), "current", "dormitory"),
        ResourceSpec("hygiene_checks", "宿舍卫生", DormHygieneCheck,
            ("room", "date", "check_time", "inspector", "total_score", "grade", "rectification", "rectification_deadline", "rectification_result", "needs_follow_up", "follow_up_date", "photo", "remarks"),
            ("room", "date", "check_time", "inspector", "total_score", "grade", "rectification", "rectification_deadline", "rectification_result", "needs_follow_up", "follow_up_date", "photo", "remarks"),
            ("room__room_number", "inspector", "rectification"), ("-date", "-pk"), "current", "dormitory", "hygienecheck"),
        ResourceSpec("reward_items", "奖惩条目", RewardItem,
            ("item_type", "name", "default_points", "category", "is_active", "sort_order"),
            ("item_type", "name", "default_points", "category", "is_active", "sort_order"),
            ("name", "category"), ("sort_order", "name"), "current", "rewards"),
        ResourceSpec("rewards", "奖惩记录", RewardRecord,
            ("student", "date", "record_type", "item", "custom_name", "level", "points", "description", "certificate_photo", "needs_follow_up", "follow_up_date"),
            ("student", "date", "record_type", "item", "custom_name", "level", "points", "description", "certificate_photo", "needs_follow_up", "follow_up_date"),
            ("student__name", "custom_name", "description"), ("-date", "-pk"), "current", "rewards", "reward"),
        ResourceSpec("point_records", "积分明细", PointRecord,
            ("student", "date", "points", "reason", "source_type", "manual_reason"),
            ("student", "date", "points", "reason", "manual_reason"),
            ("student__name", "reason"), ("-date", "-pk"), "current", "rewards"),
        ResourceSpec("ranking_settings", "积分排名设置", RankingSetting,
            ("enable_reward", "enable_classroom_discipline", "enable_dorm_discipline", "enable_hygiene", "enable_attendance", "enable_homework"),
            ("enable_reward", "enable_classroom_discipline", "enable_dorm_discipline", "enable_hygiene", "enable_attendance", "enable_homework"),
            (), ("pk",), "current", "rewards", allow_delete=False),
        ResourceSpec("exams", "考试", Exam,
            ("name", "exam_type", "date", "total_score", "is_published", "remarks"),
            ("name", "exam_type", "date", "total_score", "is_published", "remarks"),
            ("name", "remarks"), ("-date", "-pk"), "current", "scores", "exam"),
        ResourceSpec("exam_subjects", "考试科目", ExamSubject,
            ("exam", "subject", "full_score", "sort_order"),
            ("exam", "subject", "full_score", "sort_order"),
            ("exam__name", "subject__name"), ("exam__date", "sort_order"), "current", "scores"),
        ResourceSpec("scores", "成绩", Score,
            ("exam", "exam_subject", "student", "score", "status", "rank", "grade_rank", "city_rank", "remarks"),
            ("exam_subject", "student", "score", "status", "grade_rank", "city_rank", "remarks"),
            ("student__name", "exam__name", "exam_subject__subject__name"), ("-exam__date", "exam_subject__sort_order", "student__student_id"), "current", "scores", "score"),
        ResourceSpec("grade_lines", "成绩分数线", GradeLine,
            ("exam_subject", "undergraduate_line", "pass_line"),
            ("exam_subject", "undergraduate_line", "pass_line"),
            ("exam_subject__exam__name", "exam_subject__subject__name"), ("-exam_subject__exam__date",), "current", "scores", allow_delete=False),
        ResourceSpec("external_classes", "外部对比班级", ExternalClass,
            ("name", "school_name"), ("name", "school_name"),
            ("name", "school_name"), ("school_name", "name"), "current", "scores"),
        ResourceSpec("external_scores", "外部班级单科成绩", ExternalScore,
            ("external_class", "exam", "exam_subject", "student_label", "score", "class_rank", "grade_rank", "city_rank"),
            ("external_class", "exam_subject", "student_label", "score", "class_rank", "grade_rank", "city_rank"),
            ("external_class__name", "exam__name", "student_label"), ("-exam__date", "external_class__name", "student_label"), "current", "scores"),
        ResourceSpec("exam_totals", "本班考试总分", ExamTotal,
            ("exam", "student", "total_score", "class_rank", "grade_rank", "city_rank"),
            ("exam", "student", "total_score", "class_rank", "grade_rank", "city_rank"),
            ("exam__name", "student__name"), ("-exam__date", "student__student_id"), "current", "scores"),
        ResourceSpec("external_totals", "外部班级总分", ExternalTotal,
            ("external_class", "exam", "student_label", "total_score", "class_rank", "grade_rank", "city_rank"),
            ("external_class", "exam", "student_label", "total_score", "class_rank", "grade_rank", "city_rank"),
            ("external_class__name", "exam__name", "student_label"), ("-exam__date", "external_class__name", "student_label"), "current", "scores"),
        ResourceSpec("support_plans", "培优补差计划", SupportPlan,
            ("student", "plan_type", "subject", "target_score", "stage_goal", "is_active", "start_date", "end_date"),
            ("student", "plan_type", "subject", "target_score", "stage_goal", "is_active", "end_date"),
            ("student__name", "subject__name", "stage_goal"), ("-is_active", "student__student_id"), "current", "scores"),
        ResourceSpec("support_followups", "培优补差跟进", SupportFollowUp,
            ("plan", "date", "content", "effect", "next_step"),
            ("plan", "date", "content", "effect", "next_step"),
            ("plan__student__name", "content", "effect"), ("-date",), "current", "scores"),
        ResourceSpec("conversations", "学生谈话", StudentConversation,
            ("student", "exam", "date", "location", "reason", "main_content", "student_feedback", "follow_up_actions", "follow_up_date", "is_private"),
            ("student", "exam", "date", "location", "reason", "main_content", "student_feedback", "follow_up_actions", "follow_up_date", "is_private"),
            ("student__name", "reason", "main_content"), ("-date", "-pk"), "current", "communications", "conversation"),
        ResourceSpec("home_school_contacts", "家校沟通", HomeSchoolContact,
            ("student", "contact_date", "contact_person", "contact_method", "reason", "summary", "parent_feedback", "follow_up_items", "follow_up_date", "is_private"),
            ("student", "contact_date", "contact_person", "contact_method", "reason", "summary", "parent_feedback", "follow_up_items", "follow_up_date", "is_private"),
            ("student__name", "contact_person", "reason", "summary"), ("-contact_date", "-pk"), "current", "communications", allow_delete=False),
        ResourceSpec("concerns", "重点关注", ConcernRecord,
            ("student", "concern_type", "level", "observation", "conversation_notes", "action_plan", "next_follow_up", "status", "is_private", "end_date"),
            ("student", "concern_type", "level", "observation", "conversation_notes", "action_plan", "next_follow_up", "status", "is_private", "end_date"),
            ("student__name", "observation", "action_plan"), ("-created_at",), "current", "communications", allow_delete=False),
        ResourceSpec("storage_alerts", "存储提醒", StorageAlertRule,
            ("name", "category", "threshold_mb", "recipient_emails", "is_active", "last_notified_at"),
            ("name", "category", "threshold_mb", "recipient_emails", "is_active"),
            ("name", "recipient_emails"), ("-is_active", "name"), "user", "backups"),
    ]
    return {item.key: item for item in values}


def get_spec(key):
    return _specs().get(key)


def _queryset(spec, user):
    model = spec.model
    current = get_current_class(user)
    qs = model.objects.all()
    if spec.scope == "account":
        if spec.key == "classes":
            return qs.filter(created_by=user)
        if spec.key == "semesters":
            return qs.filter(school_class__created_by=user)
        if spec.key == "todos":
            return qs.filter(created_by=user, is_deleted=False)
    if spec.scope == "subjects":
        return qs.filter(Q(created_by=user) | Q(created_by__isnull=True))
    if spec.scope == "user":
        return qs.filter(created_by=user)
    if not current:
        return qs.none()
    filters = {}
    names = {field.name for field in model._meta.fields}
    if "school_class" in names:
        filters["school_class"] = current
    elif spec.key == "guardians":
        filters["student__school_class"] = current
    elif spec.key == "homework_records":
        filters["task__school_class"] = current
    elif spec.key == "dorm_rooms":
        filters["building__school_class"] = current
    elif spec.key == "dorm_assignments":
        filters["room__building__school_class"] = current
    elif spec.key == "exam_subjects":
        filters["exam__school_class"] = current
    elif spec.key == "scores":
        filters["exam__school_class"] = current
    elif spec.key == "grade_lines":
        filters["exam_subject__exam__school_class"] = current
    elif spec.key == "external_scores":
        filters["external_class__school_class"] = current
    elif spec.key == "exam_totals":
        filters["exam__school_class"] = current
    elif spec.key == "external_totals":
        filters["external_class__school_class"] = current
    elif spec.key == "support_followups":
        filters["plan__school_class"] = current
    if "is_deleted" in names:
        filters["is_deleted"] = False
    return qs.filter(**filters)


def _relation_queryset(spec, field, user, data=None):
    from django.contrib.auth.models import User
    from apps.classes.models import SchoolClass, Semester
    from apps.discipline.models import ConfigurableItem
    from apps.dormitory.models import DormBed, DormBuilding, DormRoom
    from apps.homework.models import HomeworkTask, Subject
    from apps.rewards.models import RewardItem
    from apps.scores.models import Exam, ExamSubject, ExternalClass, SupportPlan
    from apps.students.models import Student

    model = field.remote_field.model
    current = get_current_class(user)
    if model is User:
        return model.objects.none()
    if model is SchoolClass:
        return model.objects.filter(created_by=user)
    if model is Semester:
        return model.objects.filter(school_class__created_by=user)
    if model is Student:
        if spec.key == "todos":
            return model.objects.filter(school_class__created_by=user, is_deleted=False)
        return model.objects.filter(school_class=current, is_deleted=False)
    if model is Subject:
        return model.objects.filter(Q(created_by=user) | Q(created_by__isnull=True), is_active=True)
    if model is ConfigurableItem:
        qs = model.objects.filter(school_class=current)
        if spec.key == "classroom_discipline":
            qs = qs.filter(module="classroom_discipline")
        elif spec.key == "dorm_discipline":
            qs = qs.filter(module="dorm_discipline")
        return qs
    if model is DormBuilding:
        return model.objects.filter(school_class=current)
    if model is DormRoom:
        return model.objects.filter(building__school_class=current)
    if model is DormBed:
        qs = model.objects.filter(room__building__school_class=current)
        room_id = (data or {}).get("room")
        return qs.filter(room_id=room_id) if room_id else qs
    if model is HomeworkTask:
        return model.objects.filter(school_class=current)
    if model is RewardItem:
        return model.objects.filter(school_class=current)
    if model is Exam:
        return model.objects.filter(school_class=current, is_deleted=False)
    if model is ExamSubject:
        return model.objects.filter(exam__school_class=current, exam__is_deleted=False)
    if model is ExternalClass:
        return model.objects.filter(school_class=current)
    if model is SupportPlan:
        return model.objects.filter(school_class=current)
    return model.objects.none()


def _convert(field, value, spec, user, data):
    if value == "" and getattr(field, "null", False):
        return None
    if isinstance(field, (models.ForeignKey, models.OneToOneField)):
        if value in (None, ""):
            if field.null:
                return None
            raise ValidationError({field.name: ["该项不能为空。"]})
        obj = _relation_queryset(spec, field, user, data).filter(pk=value).first()
        if not obj:
            raise ValidationError({field.name: ["所选对象不存在或不属于当前账户。"]})
        return obj
    if isinstance(field, models.BooleanField):
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    if isinstance(field, models.DateTimeField):
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
    if isinstance(field, models.DateField):
        return date.fromisoformat(str(value)) if value else None
    if isinstance(field, models.TimeField):
        return time.fromisoformat(str(value)) if value else None
    if isinstance(field, models.IntegerField):
        return int(value) if value not in (None, "") else None
    if isinstance(field, models.FloatField):
        return float(value) if value not in (None, "") else None
    if isinstance(field, models.DecimalField):
        try:
            return Decimal(str(value)) if value not in (None, "") else None
        except InvalidOperation:
            raise ValidationError({field.name: ["请输入有效数字。"]})
    return value


def _apply_data(instance, spec, data, request):
    for name in spec.editable:
        if name not in data and name not in request.FILES:
            continue
        field = instance._meta.get_field(name)
        if isinstance(field, models.FileField):
            if name in request.FILES:
                setattr(instance, name, request.FILES[name])
            continue
        setattr(instance, name, _convert(field, data.get(name), spec, request.mobile_user, data))


def _force_scope(instance, spec, user, creating=True):
    current = get_current_class(user)
    field_names = {field.name for field in instance._meta.fields}
    if spec.key == "classes":
        instance.created_by = user
    elif spec.key == "subjects":
        if creating:
            instance.created_by = user
    elif spec.key == "todos":
        instance.created_by = user
        if creating:
            instance.school_class = current
    elif spec.key == "storage_alerts":
        instance.created_by = user
    elif spec.scope == "user" and hasattr(instance, "created_by_id"):
        instance.created_by = user
    elif "school_class" in field_names and spec.key not in {"students", "semesters"}:
        instance.school_class = current
    if "semester" in field_names and spec.key not in {"semesters"}:
        from apps.classes.models import Semester
        instance.semester = Semester.objects.filter(school_class=current, is_current=True).first()
    if spec.key == "point_records":
        instance.source_type = "manual"
        instance.source_id = None
    if spec.key == "scores" and instance.exam_subject_id:
        instance.exam = instance.exam_subject.exam
    if spec.key == "external_scores" and instance.exam_subject_id:
        instance.exam = instance.exam_subject.exam


def _after_save(instance, spec, user):
    if spec.key == "classes" and instance.is_current:
        spec.model.objects.filter(created_by=user).exclude(pk=instance.pk).update(is_current=False)
    elif spec.key == "semesters" and instance.is_current:
        spec.model.objects.filter(school_class=instance.school_class).exclude(pk=instance.pk).update(is_current=False)
    elif spec.key == "guardians":
        from apps.students.views import _sync_student_contact
        _sync_student_contact(instance)
    elif spec.key == "todos":
        instance.completed_at = timezone.now() if instance.is_completed else None
        instance.save(update_fields=["completed_at", "updated_at"])
    elif spec.key == "attendance":
        from apps.attendance.views import _sync_attendance_points
        from apps.todos.services import sync_follow_up_todo
        _sync_attendance_points(instance)
        sync_follow_up_todo(instance, user)
    elif spec.key == "homework_tasks":
        from apps.todos.services import sync_follow_up_todo
        sync_follow_up_todo(instance, user)
    elif spec.key == "homework_records":
        from apps.homework.views import _sync_homework_points
        _sync_homework_points(instance)
    elif spec.key in {"classroom_discipline", "dorm_discipline"}:
        from apps.discipline.views import _sync_discipline_points
        from apps.todos.services import sync_follow_up_todo
        _sync_discipline_points(instance)
        sync_follow_up_todo(instance, user)
    elif spec.key == "hygiene_checks":
        from apps.todos.services import sync_follow_up_todo
        sync_follow_up_todo(instance, user)
    elif spec.key == "rewards":
        from apps.rewards.views import _sync_point_record
        from apps.todos.services import sync_follow_up_todo
        instance.points = -abs(instance.points) if instance.record_type == "penalty" else abs(instance.points)
        instance.save(update_fields=["points", "updated_at"])
        _sync_point_record(instance)
        sync_follow_up_todo(instance, user)
    elif spec.key == "scores":
        from apps.scores.views import _update_ranks
        _update_ranks(instance.exam_subject)
    elif spec.key == "dorm_rooms":
        from apps.dormitory.views import _generate_beds
        _generate_beds(instance)


def _deactivate_if_used(instance, spec):
    if spec.key == "homework_statuses":
        from apps.homework.models import HomeworkRecord
        return HomeworkRecord.objects.filter(status=f"custom:{instance.pk}").exists()
    if spec.key == "discipline_items":
        return instance.classroom_discipline_records.exists() or instance.dorm_discipline_records.exists()
    if spec.key == "hygiene_items":
        return instance.dormhygieneitemscore_set.exists()
    if spec.key == "reward_items":
        return instance.records.exists()
    if spec.key == "subjects":
        return instance.homeworktask_set.exists() or instance.examsubject_set.exists()
    return False


def _delete(instance, spec, user, confirmation=""):
    if spec.key == "classes":
        if confirmation != instance.name:
            raise ValidationError({"confirmation": ["请输入完整班级名称确认删除。"]})
        from apps.students.models import Student
        Student.objects.filter(school_class=instance).delete()
        instance.delete()
        return
    if _deactivate_if_used(instance, spec):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        return
    if spec.key == "students":
        instance.soft_delete()
        from datetime import timedelta
        from apps.audit.models import SoftDeleteRecord
        SoftDeleteRecord.objects.update_or_create(
            model_name="student", object_id=instance.pk,
            defaults={
                "object_repr": f"{instance.name}（学号：{instance.student_id}）",
                "module": "students", "serialized_data": {"student_id": instance.student_id, "name": instance.name, "gender": instance.gender},
                "deleted_by": user, "expires_at": timezone.now() + timedelta(days=30),
            },
        )
        return
    if spec.key == "todos":
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted", "updated_at"])
        return
    if spec.key == "homework_tasks":
        from apps.todos.services import remove_follow_up_todo
        remove_follow_up_todo(instance)
        instance.delete()
        return
    if spec.key == "homework_records":
        from apps.rewards.services import unsync_source_point
        unsync_source_point("homework", instance.pk)
        instance.delete()
        return
    if spec.soft_name:
        if spec.key in {"classroom_discipline", "dorm_discipline"}:
            from apps.rewards.services import unsync_source_point
            from apps.todos.services import remove_follow_up_todo
            unsync_source_point("classroom_discipline" if spec.key == "classroom_discipline" else "dorm_discipline", instance.pk)
            remove_follow_up_todo(instance)
        elif spec.key == "rewards":
            from apps.rewards.models import PointRecord
            from apps.todos.services import remove_follow_up_todo
            PointRecord.objects.filter(source_type="reward", source_id=instance.pk).update(is_deleted=True)
            remove_follow_up_todo(instance)
        from apps.audit.services import soft_delete
        soft_delete(instance, user=user, module=spec.module, model_name=spec.soft_name)
        return
    instance.delete()


def _schema(spec, user):
    editable = set(spec.editable)
    fields = []
    for name in spec.fields:
        field = spec.model._meta.get_field(name)
        item = field_schema(field, required=name in editable and not field.blank and not field.null)
        item["read_only"] = name not in editable
        if isinstance(field, (models.ForeignKey, models.OneToOneField)) and name in editable:
            item["options"] = [
                {"value": obj.pk, "label": str(obj)}
                for obj in _relation_queryset(spec, field, user)[:500]
            ]
        fields.append(item)
    return {
        "key": spec.key, "title": spec.title, "fields": fields,
        "allow_create": True, "allow_edit": bool(spec.editable),
        "allow_delete": spec.allow_delete,
    }


@mobile_api(["GET"])
def schemas(request):
    return api_ok([_schema(spec, request.mobile_user) for spec in _specs().values()])


@mobile_api(["GET", "POST"])
def resource_list(request, resource):
    spec = get_spec(resource)
    if not spec:
        return api_error("资源不存在。", 404, "not_found")
    if request.method == "POST":
        data = parse_data(request)
        with transaction.atomic():
            if spec.key == "ranking_settings":
                current = get_current_class(request.mobile_user)
                instance, _ = spec.model.objects.get_or_create(school_class=current)
            else:
                instance = spec.model()
            _apply_data(instance, spec, data, request)
            _force_scope(instance, spec, request.mobile_user, instance.pk is None)
            instance.full_clean()
            instance.save()
            _after_save(instance, spec, request.mobile_user)
        return api_ok(serialize_instance(instance, spec.fields), 201)

    qs = _queryset(spec, request.mobile_user)
    search = request.GET.get("search", "").strip()
    if search and spec.search:
        query = Q()
        for name in spec.search:
            query |= Q(**{f"{name}__icontains": search})
        qs = qs.filter(query)
    for name in spec.fields:
        value = request.GET.get(name)
        if value not in (None, ""):
            try:
                spec.model._meta.get_field(name)
                qs = qs.filter(**{name: value})
            except (FieldDoesNotExist, ValueError):
                pass
    qs = qs.order_by(*spec.order)
    try:
        size = min(100, max(1, int(request.GET.get("page_size", 30))))
        page = max(1, int(request.GET.get("page", 1)))
    except ValueError:
        return api_error("分页参数无效。")
    paginator = Paginator(qs, size)
    page_obj = paginator.get_page(page)
    return api_ok({
        "results": [serialize_instance(obj, spec.fields) for obj in page_obj.object_list],
        "page": page_obj.number, "page_size": size,
        "total": paginator.count, "pages": paginator.num_pages,
        "schema": _schema(spec, request.mobile_user),
    })


@mobile_api(["GET", "PUT", "PATCH", "DELETE"])
def resource_detail(request, resource, pk):
    spec = get_spec(resource)
    if not spec:
        return api_error("资源不存在。", 404, "not_found")
    instance = _queryset(spec, request.mobile_user).filter(pk=pk).first()
    if not instance:
        return api_error("记录不存在。", 404, "not_found")
    if request.method == "GET":
        return api_ok({"record": serialize_instance(instance, spec.fields), "schema": _schema(spec, request.mobile_user)})
    if spec.key == "subjects" and instance.created_by_id != request.mobile_user.pk:
        return api_error("系统预置科目不允许修改或删除。", 403, "read_only")
    data = parse_data(request)
    if request.method == "DELETE":
        if not spec.allow_delete:
            return api_error("该记录不允许删除。", 405, "delete_not_allowed")
        with transaction.atomic():
            _delete(instance, spec, request.mobile_user, str(data.get("confirmation", "")))
        return api_ok()
    with transaction.atomic():
        _apply_data(instance, spec, data, request)
        _force_scope(instance, spec, request.mobile_user, False)
        instance.full_clean()
        instance.save()
        _after_save(instance, spec, request.mobile_user)
    return api_ok(serialize_instance(instance, spec.fields))
