import io

from django.http import HttpResponse
from django.db import transaction
from openpyxl import Workbook, load_workbook


HEADERS = {
    "classroom_discipline": ["名称", "默认分值", "分类", "严重程度", "需要跟进", "启用", "排序"],
    "dorm_discipline": ["名称", "默认分值", "分类", "严重程度", "需要跟进", "启用", "排序"],
    "reward": ["类型", "名称", "默认分值", "分类", "启用", "排序"],
    "dorm_hygiene": ["名称", "满分", "默认扣分", "启用", "排序"],
    "attendance_reason": ["名称", "启用", "排序"],
    "duty_task": ["名称", "区域", "默认人数", "启用", "排序"],
    "homework_status": ["名称", "积极状态", "启用", "排序"],
}


def _bool(value, default=True):
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "是", "启用"}


def option_template_response(category):
    if category not in HEADERS:
        raise ValueError("不支持的选项类型。")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "选项导入"
    sheet.append(HEADERS[category])
    examples = {
        "classroom_discipline": ["上课讲话", -1, "课堂秩序", "mild", "否", "是", 0],
        "dorm_discipline": ["晚归", -2, "作息", "moderate", "是", "是", 0],
        "reward": ["奖励", "主动帮助同学", 1, "品德", "是", 0],
        "dorm_hygiene": ["地面", 10, 1, "是", 0],
        "attendance_reason": ["交通拥堵", "是", 0],
        "duty_task": ["擦黑板", "讲台", 1, "是", 0],
        "homework_status": ["待订正", "否", "是", 0],
    }
    sheet.append(examples[category])
    output = io.BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="option_{category}_template.xlsx"'
    return response


@transaction.atomic
def import_options(category, uploaded, school_class):
    if category not in HEADERS:
        raise ValueError("不支持的选项类型。")
    workbook = load_workbook(uploaded, data_only=True)
    sheet = workbook.active
    imported = 0
    for values in sheet.iter_rows(min_row=2, values_only=True):
        name = str(values[0] or "").strip()
        if not name:
            continue
        if category in {"classroom_discipline", "dorm_discipline"}:
            from apps.discipline.models import ConfigurableItem
            severity = str(values[3] or "moderate")
            if severity not in dict(ConfigurableItem.SEVERITY_CHOICES):
                severity = "moderate"
            ConfigurableItem.objects.update_or_create(
                school_class=school_class, module=category, name=name,
                defaults={"default_points": int(values[1] or 0), "category": str(values[2] or ""), "default_severity": severity, "needs_follow_up": _bool(values[4], False), "is_active": _bool(values[5]), "sort_order": int(values[6] or 0)},
            )
        elif category == "reward":
            from apps.rewards.models import RewardItem
            item_type_raw = str(values[0] or "").strip()
            item_type = "penalty" if any(k in item_type_raw for k in ("惩罚", "扣分", "penalty")) else "reward"
            RewardItem.objects.update_or_create(
                school_class=school_class, name=name,
                defaults={
                    "item_type": item_type,
                    "default_points": int(values[2] or 0),
                    "category": str(values[3] or ""),
                    "is_active": _bool(values[4]),
                    "sort_order": int(values[5] or 0),
                },
            )
        elif category == "dorm_hygiene":
            from apps.dormitory.models import DormHygieneItem
            DormHygieneItem.objects.update_or_create(school_class=school_class, name=name, defaults={"full_score": int(values[1] or 10), "default_deduction": int(values[2] or 0), "is_active": _bool(values[3]), "sort_order": int(values[4] or 0)})
        elif category == "attendance_reason":
            from apps.attendance.models import AttendanceReason
            AttendanceReason.objects.update_or_create(school_class=school_class, name=name, defaults={"is_active": _bool(values[1]), "sort_order": int(values[2] or 0)})
        elif category == "duty_task":
            from apps.duty.models import DutyTask
            try:
                default_count = max(1, int(values[2] or 1))
            except (TypeError, ValueError):
                default_count = 1
            DutyTask.objects.update_or_create(school_class=school_class, name=name, defaults={"area": str(values[1] or ""), "default_people_count": default_count, "is_active": _bool(values[3]), "sort_order": int(values[4] or 0)})
        elif category == "homework_status":
            from apps.homework.models import HomeworkStatus
            HomeworkStatus.objects.update_or_create(school_class=school_class, name=name, defaults={"is_positive": _bool(values[1], False), "is_active": _bool(values[2]), "sort_order": int(values[3] or 0)})
        imported += 1
    return imported
