from datetime import timedelta

from django.apps import apps
from django.utils import timezone

from apps.audit.models import OperationLog, SoftDeleteRecord


MODEL_LABELS = {
    "student": "students.Student",
    "exam": "scores.Exam",
    "score": "scores.Score",
    "classroomdiscipline": "discipline.ClassroomDisciplineRecord",
    "dormdiscipline": "discipline.DormDisciplineRecord",
    "reward": "rewards.RewardRecord",
    "comment": "comments.StudentComment",
    "conversation": "communications.StudentConversation",
    "activity": "activities.Activity",
    "hygienecheck": "dormitory.DormHygieneCheck",
}


def soft_delete(instance, *, user, module, model_name, object_repr=None):
    """软删除对象并创建可恢复的回收站索引。"""
    if not hasattr(instance, "is_deleted"):
        raise ValueError(f"{instance.__class__.__name__} 不支持软删除")
    instance.is_deleted = True
    update_fields = ["is_deleted"]
    if hasattr(instance, "deleted_at"):
        instance.deleted_at = timezone.now()
        update_fields.append("deleted_at")
    if hasattr(instance, "updated_at"):
        update_fields.append("updated_at")
    instance.save(update_fields=update_fields)

    SoftDeleteRecord.objects.update_or_create(
        model_name=model_name,
        object_id=instance.pk,
        is_permanently_deleted=False,
        defaults={
            "object_repr": object_repr or str(instance),
            "module": module,
            "serialized_data": {
                "model": instance._meta.label,
                "pk": instance.pk,
            },
            "deleted_by": user,
            "expires_at": timezone.now() + timedelta(days=30),
        },
    )
    OperationLog.objects.create(
        user=user,
        action="delete",
        module=module,
        object_repr=object_repr or str(instance),
        detail="软删除并移入回收站",
        success=True,
    )


def get_model_for_record(record):
    label = MODEL_LABELS.get(record.model_name)
    return apps.get_model(label) if label else None


def restore(record):
    model_class = get_model_for_record(record)
    if not model_class:
        return False
    instance = model_class.objects.filter(pk=record.object_id).first()
    if not instance or not hasattr(instance, "is_deleted"):
        return False
    instance.is_deleted = False
    update_fields = ["is_deleted"]
    if hasattr(instance, "deleted_at"):
        instance.deleted_at = None
        update_fields.append("deleted_at")
    if hasattr(instance, "updated_at"):
        update_fields.append("updated_at")
    instance.save(update_fields=update_fields)
    # 恢复后重新同步积分变动（纪律/奖惩/卫生检查）
    try:
        resync_points_for(record.model_name, instance)
    except Exception:
        pass
    return True


def permanently_delete(record):
    model_class = get_model_for_record(record)
    if not model_class:
        return False
    # 永久删除前先撤销其关联的积分变动
    unsync_points_for(record.model_name, record.object_id)
    deleted_count, _details = model_class.objects.filter(
        pk=record.object_id, is_deleted=True,
    ).delete()
    return deleted_count > 0


def _linked_discipline_records(check):
    """卫生检查关联的宿舍纪律扣分记录（含旧数据兼容）。"""
    from apps.discipline.models import DormDisciplineRecord
    queryset = DormDisciplineRecord.objects.filter(source_check=check)
    if not queryset.exists():
        # 旧数据无 source_check 关联：按 宿舍+日期+来源描述 匹配
        queryset = DormDisciplineRecord.objects.filter(
            dorm_room=check.room, date=check.date,
            description__startswith="卫生检查扣分：",
        )
    return queryset


def unsync_points_for(model_name, object_id):
    """按回收站记录类型撤销对应的积分变动。"""
    from apps.rewards.models import PointRecord
    if model_name == "reward":
        PointRecord.objects.filter(
            source_type="reward", source_id=object_id,
        ).update(is_deleted=True)
    elif model_name in ("classroomdiscipline", "dormdiscipline"):
        PointRecord.objects.filter(
            source_type=(
                "classroom_discipline" if model_name == "classroomdiscipline"
                else "dorm_discipline"
            ),
            source_id=object_id,
        ).update(is_deleted=True)
    elif model_name == "hygienecheck":
        # 撤销该卫生检查同步产生的纪律扣分记录及其积分
        from apps.dormitory.models import DormHygieneCheck
        check = DormHygieneCheck.objects.filter(pk=object_id).first()
        if not check:
            return
        for record in _linked_discipline_records(check):
            PointRecord.objects.filter(
                source_type="dorm_discipline", source_id=record.pk,
            ).update(is_deleted=True)


def resync_points_for(model_name, instance):
    """从回收站恢复后，重新同步对应的积分变动。"""
    if model_name in ("classroomdiscipline", "dormdiscipline"):
        from apps.discipline.views import _sync_discipline_points
        _sync_discipline_points(instance)
    elif model_name == "reward":
        from apps.rewards.views import _sync_point_record
        _sync_point_record(instance)
    elif model_name == "hygienecheck":
        # 恢复卫生检查时，一并恢复其同步产生的纪律扣分记录与积分
        from apps.discipline.views import _sync_discipline_points
        from apps.discipline.models import DormDisciplineRecord
        for record in _linked_discipline_records(instance):
            if record.is_deleted:
                record.is_deleted = False
                update_fields = ["is_deleted", "updated_at"]
                if hasattr(record, "deleted_at"):
                    record.deleted_at = None
                    update_fields.append("deleted_at")
                record.save(update_fields=update_fields)
            _sync_discipline_points(record)
