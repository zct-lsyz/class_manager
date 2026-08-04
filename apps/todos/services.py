"""待办自动同步服务：纪律等记录勾选「跟进」时自动加入待办。"""
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
    """识别纪律记录来源类型。"""
    from apps.discipline.models import ClassroomDisciplineRecord, DormDisciplineRecord
    if isinstance(record, ClassroomDisciplineRecord):
        return "classroom_discipline", "课堂纪律"
    if isinstance(record, DormDisciplineRecord):
        return "dorm_discipline", "宿舍纪律"
    return "", record.__class__.__name__


def sync_discipline_follow_up_todo(record, user):
    """按纪律记录的「需要跟进」状态自动同步待办。

    - 勾选跟进：创建或更新对应待办（截止时间 = 跟进日期，标题含项目与姓名）；
    - 取消跟进 / 跟进已处理：将对应待办标记为已完成。
    返回创建的待办，未创建则返回 None。
    """
    if not record.pk:
        return None
    source_type, module_label = _record_source_type(record)
    if not source_type or not record.student_id:
        return None

    source_id = str(record.pk)
    todo = TodoItem.objects.filter(
        source_type=source_type, source_id=source_id, is_deleted=False,
    ).first()

    if record.needs_follow_up:
        item_name = record.item.name if record.item else (record.custom_content or "纪律事件")
        defaults = {
            "school_class": record.school_class,
            "created_by": user,
            "title": f"{module_label}跟进：{item_name}（{record.student.name}）",
            "priority": _severity_priority(record.severity),
            "deadline": _deadline_from_date(record.follow_up_date or record.date),
            "student": record.student,
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


def remove_discipline_todo(record):
    """纪律记录被删除时，软删除关联待办。"""
    if not record.pk:
        return
    source_type, _module_label = _record_source_type(record)
    if not source_type:
        return
    TodoItem.objects.filter(
        source_type=source_type, source_id=str(record.pk), is_deleted=False,
    ).update(is_deleted=True)
