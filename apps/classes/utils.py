"""班级工具函数"""
from apps.classes.models import SchoolClass


def get_current_class(user):
    """获取当前用户的当前班级（多租户隔离）"""
    if not user or not user.is_authenticated:
        return None
    return SchoolClass.objects.filter(is_current=True, created_by=user).first()
