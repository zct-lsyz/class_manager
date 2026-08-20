"""作业积分统一取分服务。

内置默认分值 + 班级级规则（HomeworkPointRule）覆盖，
供积分同步（views）与成长事件/预警（history_services）共用。
"""
from apps.homework.models import HomeworkPointRule

# 内置默认分值：正数加分、负数扣分
HOMEWORK_POINTS = {
    "submitted": 1,
    "excellent": 2,
    "corrected": 1,
    "unsubmitted": -1,
    "late": -1,
    "needs_correction": -1,
    "poor": -2,
    "exempted": 0,
    "other": 0,
}


def get_status_points(school_class, status):
    """返回某完成状态的分值（正加负扣）。

    优先班级配置的 HomeworkPointRule，未配置时用内置默认。
    """
    rule = HomeworkPointRule.objects.filter(
        school_class=school_class, status=status,
    ).first()
    if rule:
        return rule.signed_points
    return HOMEWORK_POINTS.get(status, 0)
