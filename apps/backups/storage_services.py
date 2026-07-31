import json
import re
import shutil
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.backups.models import MediaArchiveExport, StorageAlertRule


ARCHIVE_DIR = Path(settings.BASE_DIR) / "backups" / "media_archives"
VALID_MODULES = {"dormitory", "rewards", "activities"}
ARCHIVE_MODELS = {
    "dormitory": {"dormitory.dormhygienecheck", "dormitory.dormhygieneitemscore", "dormitory.dormhygienephoto", "discipline.dormdisciplinerecord"},
    "rewards": {"rewards.rewardrecord", "rewards.pointrecord"},
    "activities": {"activities.activity"},
}
MEDIA_FIELD_NAMES = {
    "dormitory.dormhygienecheck": ("photo",),
    "dormitory.dormhygienephoto": ("image",),
    "rewards.rewardrecord": ("certificate_photo",),
    "activities.activity": ("photo",),
}


def _media_files_for_modules(modules):
    from apps.activities.models import Activity
    from apps.dormitory.models import DormHygieneCheck, DormHygienePhoto
    from apps.rewards.models import RewardRecord

    fields = []
    if "dormitory" in modules:
        fields.extend(check.photo for check in DormHygieneCheck.objects.exclude(photo=""))
        fields.extend(photo.image for photo in DormHygienePhoto.objects.exclude(image=""))
    if "rewards" in modules:
        fields.extend(record.certificate_photo for record in RewardRecord.objects.exclude(certificate_photo=""))
    if "activities" in modules:
        fields.extend(activity.photo for activity in Activity.objects.exclude(photo=""))
    return [field for field in fields if field and field.name]


def _objects_for_modules(modules):
    from apps.activities.models import Activity
    from apps.discipline.models import DormDisciplineRecord
    from apps.dormitory.models import DormHygieneCheck, DormHygieneItemScore, DormHygienePhoto
    from apps.rewards.models import PointRecord, RewardRecord

    objects = []
    if "dormitory" in modules:
        objects.extend(DormHygieneCheck.objects.all())
        objects.extend(DormHygieneItemScore.objects.all())
        objects.extend(DormHygienePhoto.objects.all())
        objects.extend(DormDisciplineRecord.objects.all())
    if "rewards" in modules:
        objects.extend(RewardRecord.objects.all())
        objects.extend(PointRecord.objects.filter(source_type="reward"))
    if "activities" in modules:
        objects.extend(Activity.objects.all())
    return objects


def create_media_archive(modules, user=None):
    modules = sorted(set(modules) & VALID_MODULES)
    if not modules:
        raise ValueError("请至少选择一个导出模块。")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S_%f")
    archive_path = ARCHIVE_DIR / f"media_data_{timestamp}.zip"
    objects = _objects_for_modules(modules)
    records = []
    for obj in objects:
        model_name = obj._meta.label_lower
        fields = {
            field_name: getattr(obj, field_name).name
            for field_name in MEDIA_FIELD_NAMES.get(model_name, ())
            if getattr(obj, field_name) and getattr(obj, field_name).name
        }
        if fields:
            records.append({"model": model_name, "pk": obj.pk, "fields": fields})
    data = json.dumps(records, ensure_ascii=False, indent=2)
    media_root = Path(settings.MEDIA_ROOT)
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data.json", data)
        archive.writestr("manifest.json", json.dumps({
            "format": "classroom-media-archive-v1",
            "created_at": timezone.now().isoformat(),
            "modules": modules,
            "record_count": len(records),
        }, ensure_ascii=False, indent=2))
        written = set()
        for field in _media_files_for_modules(modules):
            path = Path(field.path)
            if path.is_file():
                name = (Path("media") / Path(field.name)).as_posix()
                if name not in written:
                    archive.write(path, name)
                    written.add(name)
    return MediaArchiveExport.objects.create(
        modules=modules, file_path=str(archive_path), file_size=archive_path.stat().st_size,
        record_count=len(records), user=user,
    )


def _validate_archive(archive):
    for member in archive.infolist():
        path = Path(member.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"压缩包包含不安全路径：{member.filename}")
    names = set(archive.namelist())
    if not {"manifest.json", "data.json"}.issubset(names):
        raise ValueError("压缩包缺少 manifest.json 或 data.json。")
    manifest = json.loads(archive.read("manifest.json"))
    if manifest.get("format") != "classroom-media-archive-v1":
        raise ValueError("不是受支持的媒体数据包。")
    modules = set(manifest.get("modules", []))
    if not modules or not modules.issubset(VALID_MODULES):
        raise ValueError("数据包声明了不支持的模块。")
    allowed_models = set().union(*(ARCHIVE_MODELS[module] for module in modules))
    records = json.loads(archive.read("data.json"))
    if any(record.get("model") not in allowed_models for record in records):
        raise ValueError("数据包包含所选模块之外的数据模型。")
    for record in records:
        for field_name in ("photo", "image", "certificate_photo"):
            value = record.get("fields", {}).get(field_name, "")
            if value and (Path(value).is_absolute() or ".." in Path(value).parts):
                raise ValueError("数据包包含不安全的照片路径。")
    return manifest


def import_media_archives(uploaded_files):
    from django.apps import apps

    imported_records = 0
    imported_packages = 0
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    for uploaded in uploaded_files:
        with tempfile.TemporaryDirectory() as temp_name:
            temp_path = Path(temp_name)
            package_path = temp_path / "archive.zip"
            with open(package_path, "wb") as target:
                for chunk in uploaded.chunks():
                    target.write(chunk)
            with zipfile.ZipFile(package_path) as archive:
                _validate_archive(archive)
                for member in archive.infolist():
                    if member.filename.startswith("media/") and not member.is_dir():
                        destination = media_root / Path(member.filename).relative_to("media")
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, open(destination, "wb") as target:
                            shutil.copyfileobj(source, target)
                records = json.loads(archive.read("data.json"))
                package_names = set(archive.namelist())
                with transaction.atomic():
                    for record in records:
                        model_name = record.get("model", "")
                        media_fields = MEDIA_FIELD_NAMES.get(model_name, ())
                        obj = apps.get_model(model_name).objects.filter(pk=record.get("pk")).first()
                        if not obj:
                            continue
                        update_fields = []
                        for field_name in media_fields:
                            value = record.get("fields", {}).get(field_name, "")
                            if value and (Path("media") / value).as_posix() in package_names:
                                setattr(obj, field_name, value)
                                update_fields.append(field_name)
                        if update_fields:
                            obj.save(update_fields=update_fields)
                            imported_records += 1
                imported_packages += 1
    return imported_packages, imported_records


def _delete_file(field):
    if field and field.name:
        field.delete(save=False)


def _archived_ids(export_record):
    path = Path(export_record.file_path)
    if not path.is_file():
        raise FileNotFoundError("归档压缩包不存在，不能安全确定清理范围。")
    with zipfile.ZipFile(path) as archive:
        _validate_archive(archive)
        records = json.loads(archive.read("data.json"))
    result = {}
    for record in records:
        result.setdefault(record["model"], []).append(record["pk"])
    return result


def clear_archived_modules(export_record):
    from apps.activities.models import Activity
    from apps.dormitory.models import DormHygieneCheck, DormHygienePhoto
    from apps.rewards.models import RewardRecord

    modules = set(export_record.modules)
    ids = _archived_ids(export_record)
    if "dormitory" in modules:
        checks = DormHygieneCheck.objects.filter(pk__in=ids.get("dormitory.dormhygienecheck", []))
        photos = DormHygienePhoto.objects.filter(pk__in=ids.get("dormitory.dormhygienephoto", []))
        for check in checks.exclude(photo=""):
            _delete_file(check.photo)
            check.photo = ""
            check.save(update_fields=["photo", "updated_at"])
        for photo in photos:
            _delete_file(photo.image)
            photo.image = ""
            photo.save(update_fields=["image", "updated_at"])
    if "rewards" in modules:
        records = RewardRecord.objects.filter(pk__in=ids.get("rewards.rewardrecord", []))
        for record in records.exclude(certificate_photo=""):
            _delete_file(record.certificate_photo)
            record.certificate_photo = ""
            record.save(update_fields=["certificate_photo", "updated_at"])
    if "activities" in modules:
        activities = Activity.objects.filter(pk__in=ids.get("activities.activity", []))
        for activity in activities.exclude(photo=""):
            _delete_file(activity.photo)
            activity.photo = ""
            activity.save(update_fields=["photo", "updated_at"])
    export_record.cleared_at = timezone.now()
    export_record.save(update_fields=["cleared_at", "updated_at"])


def _directory_size(relative_path):
    root = Path(settings.MEDIA_ROOT) / relative_path
    if not root.exists():
        return 0
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def storage_usage_mb(category):
    if category == "disk_free":
        return shutil.disk_usage(Path(settings.MEDIA_ROOT).parent).free / 1024 / 1024
    paths = {"dormitory": "hygiene", "rewards": "rewards", "activities": "activities"}
    return _directory_size(paths[category]) / 1024 / 1024


def check_storage_alerts(force=False):
    sent = 0
    now = timezone.now()
    for rule in StorageAlertRule.objects.filter(is_active=True):
        usage = storage_usage_mb(rule.category)
        triggered = usage <= rule.threshold_mb if rule.category == "disk_free" else usage >= rule.threshold_mb
        recently_sent = rule.last_notified_at and rule.last_notified_at >= now - timedelta(hours=24)
        if not triggered or (recently_sent and not force):
            continue
        recipients = [email.strip() for email in re.split(r"[,;\s]+", rule.recipient_emails) if email.strip()]
        if not recipients:
            continue
        direction = "仅剩" if rule.category == "disk_free" else "已占用"
        send_mail(
            f"[班级管理平台] 存储空间提醒：{rule.name}",
            f"提醒项：{rule.get_category_display()}\n当前{direction}：{usage:.1f} MB\n设置阈值：{rule.threshold_mb} MB\n请及时登录系统归档或清理。",
            settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False,
        )
        rule.last_notified_at = now
        rule.save(update_fields=["last_notified_at", "updated_at"])
        sent += 1
    return sent
