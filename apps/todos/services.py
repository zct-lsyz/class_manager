"""待办自动同步服务：勾选「跟进」的记录自动加入待办。"""
from datetime import datetime, time as dt_time

from django.utils import timezone

from apps.todos.models import TodoItem


def _deadline_from_date(date):
    """日期 → 待办截止时间（当天 0 点，带时区）。"""
    if not date:
        return None
    return timezone.make_aware(datetime.combine(date, dt_time()))


def _severity_priority(severity):
    """严重程度 → 待办优先级（1 高 / 2 中 / 3 低）。"""
    return 1 if severity in ("serious", "critical") else (3 if severity == "mild" else 2)


def _record_source_type(record):
    """识别记录来源类型 → (source_type, 模块显示名)。"""
    from apps.discipline.models import ClassroomDisciplineRecord, DormDisciplineRecord
    from apps.attendance.models import AttendanceRecord
    from apps.homework.models import HomeworkTask
    from apps.dormitory.models import DormHygieneCheck
    from apps.rewards.models import RewardRecord
    for cls, (source_type, label) in (
        (ClassroomDisciplineRecord, ("classroom_discipline", "课堂纪律")),
        (DormDisciplineRecord, ("dorm_discipline", "宿舍纪律")),
        (AttendanceRecord, ("attendance", "考勤")),
        (HomeworkTask, ("homework", "作业")),
        (DormHygieneCheck, ("hygiene", "卫生检查")),
        (RewardRecord, ("reward", "奖惩")),
    ):
        if isinstance(record, cls):
            return source_type, label
    return "", record.__class__.__name__


def _record_student(record):
    return getattr(record, "student", None)


def _record_date(record):
    return (
        getattr(record, "date", None)
        or getattr(record, "submission_date", None)
        or getattr(record, "due_date", None)
        or getattr(record, "assigned_date", None)
    )


def _record_school_class(record):
    sc = getattr(record, "school_class", None)
    if sc:
        return sc
    task = getattr(record, "task", None)
    return getattr(task, "school_class", None)


def _record_title_fragment(record):
    """待办标题中的项目/事件描述。"""
    item = getattr(record, "item", None)
    if item is not None:
        return getattr(item, "name", "") or getattr(record, "custom_name", "") or "事件"
    for attr in ("custom_content", "custom_name", "reason"):
        val = getattr(record, attr, None)
        if val:
            return val
    task = getattr(record, "task", None)
    if task is not None:
        return task.title
    room = getattr(record, "room", None)
    if room is not None:
        return str(room)
    for attr in ("title", "name"):
        val = getattr(record, attr, None)
        if val:
            return val
    if hasattr(record, "get_status_display"):
        try:
            return record.get_status_display()
        except Exception:
            pass
    return "事项"


def sync_follow_up_todo(record, user):
    """按记录的「需要跟进」状态自动同步待办。

    - 勾选跟进：创建或更新对应待办（截止时间 = 跟进日期，标题含项目与姓名）；
    - 取消跟进 / 跟进已处理：将对应待办标记为已完成。
    返回创建的待办，未创建则返回 None。
    """
    if not record.pk:
        return None
    source_type, module_label = _record_source_type(record)
    if not source_type:
        return None
    source_id = str(record.pk)
    todo = TodoItem.objects.filter(
        source_type=source_type, source_id=source_id, is_deleted=False,
    ).first()

    if record.needs_follow_up:
        student = _record_student(record)
        title = f"{module_label}跟进：{_record_title_fragment(record)}"
        if student is not None:
            title += f"（{student.name}）"
        defaults = {
            "school_class": _record_school_class(record),
            "created_by": user,
            "title": title,
            "priority": _severity_priority(getattr(record, "severity", "")),
            "deadline": _deadline_from_date(record.follow_up_date or _record_date(record)),
            "student": student,
            "is_completed": False,
            "completed_at": None,
        }
        if todo:
            for key, value in defaults.items():
                setattr(todo, key, value)
            todo.save()
            return todo
        return TodoItem.objects.create(
            source_type=source_type, source_id=source_id, **defaults,
        )

    # 跟进已处理：标记对应待办完成
    if todo and not todo.is_completed:
        todo.is_completed = True
        todo.completed_at = timezone.now()
        todo.save(update_fields=["is_completed", "completed_at", "updated_at"])
    return None


def remove_follow_up_todo(record):
    """记录被删除时，软删除关联待办。"""
    if not record.pk:
        return
    source_type, _label = _record_source_type(record)
    if not source_type:
        return
    TodoItem.objects.filter(
        source_type=source_type, source_id=str(record.pk), is_deleted=False,
    ).update(is_deleted=True)
