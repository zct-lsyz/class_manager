from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.core.paginator import Paginator

from apps.audit.models import OperationLog


@login_required
def log_list(request):
    """操作日志列表"""
    logs = OperationLog.objects.select_related("user").all()

    # 筛选
    module = request.GET.get("module", "")
    action = request.GET.get("action", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    if module:
        logs = logs.filter(module=module)
    if action:
        logs = logs.filter(action=action)
    if date_from:
        logs = logs.filter(created_at__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__lte=date_to)

    # 分页
    paginator = Paginator(logs, 50)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    # 模块列表和操作类型列表（用于筛选下拉框）
    module_choices = OperationLog.objects.values_list("module", flat=True).distinct().order_by("module")
    action_choices = OperationLog.ACTION_CHOICES

    context = {
        "page_obj": page_obj,
        "module_choices": module_choices,
        "action_choices": action_choices,
        "current_filters": {
            "module": module,
            "action": action,
            "date_from": date_from,
            "date_to": date_to,
        },
    }
    return render(request, "audit/log_list.html", context)
