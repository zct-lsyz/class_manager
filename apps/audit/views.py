from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import timedelta

from apps.audit.models import OperationLog, SoftDeleteRecord


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


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


@login_required
def trash_list(request):
    """回收站列表"""
    records = SoftDeleteRecord.objects.filter(is_permanently_deleted=False)

    module = request.GET.get("module", "")
    if module:
        records = records.filter(module=module)

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    module_choices = SoftDeleteRecord.objects.values_list("module", flat=True).distinct().order_by("module")

    return render(request, "audit/trash_list.html", {
        "page_obj": page_obj,
        "module_choices": module_choices,
        "current_module": module,
    })


@login_required
def trash_restore(request, pk):
    """从回收站恢复"""
    record = get_object_or_404(SoftDeleteRecord, pk=pk)
    if request.method == "POST":
        try:
            restored = _restore_object(record)
            if restored:
                messages.success(request, f"「{record.object_repr}」已恢复。")
                OperationLog.objects.create(
                    user=request.user, action="edit", module=record.module,
                    object_repr=record.object_repr, detail="从回收站恢复数据",
                    ip_address=get_client_ip(request), success=True,
                )
                record.delete()
            else:
                messages.error(request, f"恢复失败：原对象类型不受支持（{record.model_name}）。")
        except Exception as exc:
            messages.error(request, f"恢复失败：{exc}")
    return redirect("audit:trash_list")


def _restore_object(record):
    """根据模型名恢复对象"""
    from apps.students.models import Student
    from apps.scores.models import Exam
    from apps.discipline.models import ClassroomDisciplineRecord
    from apps.rewards.models import RewardRecord
    from apps.comments.models import StudentComment
    from apps.communications.models import StudentConversation
    from apps.activities.models import Activity
    from apps.dormitory.models import DormHygieneCheck

    model_map = {
        "student": Student,
        "exam": Exam,
        "classroomdiscipline": ClassroomDisciplineRecord,
        "reward": RewardRecord,
        "comment": StudentComment,
        "conversation": StudentConversation,
        "activity": Activity,
        "hygienecheck": DormHygieneCheck,
    }
    model_cls = model_map.get(record.model_name)
    if not model_cls:
        return False

    obj = model_cls.objects.filter(pk=record.object_id, is_deleted=True).first()
    if not obj:
        return False
    obj.restore()
    return True


@login_required
def trash_delete(request, pk):
    """永久删除（二次确认 + 需输入对象名称）"""
    record = get_object_or_404(SoftDeleteRecord, pk=pk)
    if request.method == "POST":
        confirm_name = request.POST.get("confirm_name", "")
        if confirm_name.strip() != record.object_repr:
            messages.error(request, "确认输入的对象名称不匹配，删除已取消。")
            return redirect("audit:trash_list")

        # 物理删除原对象
        try:
            from apps.students.models import Student
            from apps.scores.models import Exam
            from apps.discipline.models import ClassroomDisciplineRecord
            from apps.rewards.models import RewardRecord
            from apps.comments.models import StudentComment
            from apps.communications.models import StudentConversation
            from apps.activities.models import Activity
            from apps.dormitory.models import DormHygieneCheck

            model_map = {
                "student": Student, "exam": Exam,
                "classroomdiscipline": ClassroomDisciplineRecord,
                "reward": RewardRecord, "comment": StudentComment,
                "conversation": StudentConversation, "activity": Activity,
                "hygienecheck": DormHygieneCheck,
            }
            model_cls = model_map.get(record.model_name)
            if model_cls:
                model_cls.objects.filter(pk=record.object_id).delete()
        except Exception:
            pass

        OperationLog.objects.create(
            user=request.user, action="delete", module=record.module,
            object_repr=record.object_repr, detail="回收站永久删除",
            ip_address=get_client_ip(request), success=True,
        )
        record.is_permanently_deleted = True
        record.save()
        messages.warning(request, f"「{record.object_repr}」已永久删除。")
    return redirect("audit:trash_list")
