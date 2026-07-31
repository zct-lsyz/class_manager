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
    return True


def permanently_delete(record):
    model_class = get_model_for_record(record)
    if not model_class:
        return False
    deleted_count, _details = model_class.objects.filter(
        pk=record.object_id, is_deleted=True,
    ).delete()
    return deleted_count > 0
