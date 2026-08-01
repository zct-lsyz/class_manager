"""统一积分同步服务。

课堂纪律、宿舍纪律、考勤等各模块的加减分，最终都汇总到 PointRecord，
保证"一份积分数据"，各模块不各论各的。
"""
from apps.rewards.models import PointRecord


def sync_source_point(student, school_class, semester, date, points, reason,
                      source_type, source_id):
    """按来源同步一条积分记录。

    同一来源（source_type + source_id）只保留一条最新积分；积分为 0 时删除对应记录。
    points 语义：正数加分、负数扣分。
    """
    if not points:
        unsync_source_point(source_type, source_id)
        return
    pr = PointRecord.objects.filter(
        source_type=source_type, source_id=source_id,
    ).order_by("pk").first()
    if not pr:
        pr = PointRecord(source_type=source_type, source_id=source_id)
    pr.student = student
    pr.school_class = school_class
    pr.semester = semester
    pr.date = date
    pr.points = points
    pr.reason = reason
    pr.is_deleted = False
    pr.save()


def unsync_source_point(source_type, source_id):
    """按来源软删除积分记录（用于删除/撤销事件时）。"""
    PointRecord.objects.filter(
        source_type=source_type, source_id=source_id,
    ).update(is_deleted=True)
