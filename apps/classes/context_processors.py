from apps.classes.models import Semester
from apps.classes.utils import get_current_class


def current_class_info(request):
    """将当前班级和学期信息注入所有模板上下文（多租户隔离）"""
    if not request.user.is_authenticated:
        return {}

    current_class = get_current_class(request.user)
    current_semester = None
    if current_class:
        current_semester = Semester.objects.filter(
            school_class=current_class, is_current=True
        ).first()

    return {
        "current_class": current_class,
        "current_semester": current_semester,
    }
