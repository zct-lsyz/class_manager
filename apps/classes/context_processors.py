from django.utils import timezone

from apps.classes.models import Semester
from apps.classes.utils import get_current_class


def _calc_teaching_week(semester):
    """根据学期起止日期计算当前教学周（1-based）。"""
    if not semester or not semester.start_date:
        return None
    today = timezone.localdate()
    start = semester.start_date
    end = semester.end_date
    if today < start:
        return 0  # 学期尚未开始
    if end and today > end:
        return None  # 学期已结束
    days_elapsed = (today - start).days
    week = days_elapsed // 7 + 1
    return max(1, week)


def current_class_info(request):
    """将当前班级和学期信息注入所有模板上下文（多租户隔离）"""
    if not request.user.is_authenticated:
        return {}

    current_class = get_current_class(request.user)
    current_semester = None
    teaching_week = None
    if current_class:
        current_semester = Semester.objects.filter(
            school_class=current_class, is_current=True
        ).first()
        teaching_week = _calc_teaching_week(current_semester)

    return {
        "current_class": current_class,
        "current_semester": current_semester,
        "teaching_week": teaching_week,
    }
