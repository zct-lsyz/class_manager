from apps.classes.models import SchoolClass, Semester


def current_class_info(request):
    """将当前班级和学期信息注入所有模板上下文"""
    if not request.user.is_authenticated:
        return {}

    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = None
    if current_class:
        current_semester = Semester.objects.filter(
            school_class=current_class, is_current=True
        ).first()

    return {
        "current_class": current_class,
        "current_semester": current_semester,
    }
