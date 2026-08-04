from pathlib import Path

from django.db.models import Q
from django.http import FileResponse

from apps.audit.models import OperationLog
from apps.backups.models import BackupRecord, MediaArchiveExport, MediaArchiveImport
from apps.backups.services import create_backup, restore_backup, verify_backup
from apps.backups.storage_services import (
    check_storage_alerts, clear_archived_modules, create_media_archive,
    import_media_archives,
)
from apps.classes.utils import get_current_class
from apps.mobile_api.auth import api_error, api_ok, get_client_ip, mobile_api, parse_data


def _records(user):
    return BackupRecord.objects.filter(Q(user=user) | Q(user__isnull=True))


def _serialize(row):
    return {
        "id": row.pk, "backup_type": row.backup_type,
        "backup_type_display": row.get_backup_type_display(),
        "status": row.status, "status_display": row.get_status_display(),
        "file_size": row.file_size, "checksum": row.checksum,
        "version_info": row.version_info, "migration_version": row.migration_version,
        "student_count": row.record_count, "exam_count": row.exam_count,
        "attachment_count": row.attachment_count, "downloaded": row.downloaded,
        "error_message": row.error_message, "created_at": row.created_at.isoformat(),
        "downloadable": row.status == "completed" and bool(row.file_path) and Path(row.file_path).is_file(),
    }


@mobile_api(["GET", "POST"])
def backups(request):
    if request.method == "POST":
        try:
            row = create_backup("manual", request.mobile_user, get_current_class(request.mobile_user))
        except Exception as exc:
            return api_error(f"备份失败：{exc}", 500, "backup_failed")
        OperationLog.objects.create(
            user=request.mobile_user, action="backup", module="backups",
            object_repr=f"手动备份 {row.created_at:%Y-%m-%d %H:%M}",
            detail=f"Android 客户端创建完整备份，大小 {row.file_size} bytes",
            ip_address=get_client_ip(request), success=True,
        )
        return api_ok(_serialize(row), 201)
    rows = _records(request.mobile_user).order_by("-created_at")[:100]
    return api_ok([_serialize(row) for row in rows])


@mobile_api(["GET", "DELETE"])
def backup_detail(request, pk):
    row = _records(request.mobile_user).filter(pk=pk).first()
    if not row:
        return api_error("备份不存在。", 404, "not_found")
    if request.method == "GET":
        ok, message = verify_backup(row)
        return api_ok({**_serialize(row), "verified": ok, "verification_message": message})
    if row.file_path:
        path = Path(row.file_path)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                return api_error("备份文件删除失败。", 500, "delete_failed")
    row.delete()
    return api_ok()


@mobile_api(["GET"])
def backup_download(request, pk):
    row = _records(request.mobile_user).filter(pk=pk, status="completed").first()
    path = Path(row.file_path) if row and row.file_path else None
    if not path or not path.is_file():
        return api_error("备份文件不存在或不可下载。", 404, "not_found")
    row.downloaded = True
    row.save(update_fields=["downloaded", "updated_at"])
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name, content_type="application/zip")


@mobile_api(["POST"])
def backup_restore(request, pk):
    row = _records(request.mobile_user).filter(pk=pk).first()
    if not row:
        return api_error("备份不存在。", 404, "not_found")
    data = parse_data(request)
    if not request.mobile_user.check_password(str(data.get("password", ""))):
        return api_error("密码错误，恢复操作已取消。", 403, "invalid_password")
    try:
        safety = restore_backup(row, user=request.mobile_user)
    except Exception as exc:
        return api_error(f"恢复失败：{exc}", 500, "restore_failed")
    return api_ok({"safety_backup_id": safety.pk, "message": "恢复成功，已自动创建恢复前安全备份。"})


@mobile_api(["GET", "POST"])
def media_archives(request):
    if request.method == "POST":
        data = parse_data(request)
        modules = data.get("modules", [])
        if not isinstance(modules, list) or not modules:
            return api_error("请选择需要归档的媒体模块。")
        try:
            row = create_media_archive(modules, request.mobile_user)
        except Exception as exc:
            return api_error(f"媒体归档失败：{exc}", 500, "archive_failed")
        return api_ok({"id": row.pk, "modules": row.modules, "file_size": row.file_size, "record_count": row.record_count}, 201)
    exports = MediaArchiveExport.objects.filter(user=request.mobile_user)[:30]
    imports = MediaArchiveImport.objects.filter(user=request.mobile_user)[:30]
    return api_ok({
        "exports": [{
            "id": row.pk, "modules": row.modules, "file_size": row.file_size,
            "record_count": row.record_count, "cleared_at": row.cleared_at.isoformat() if row.cleared_at else None,
            "created_at": row.created_at.isoformat(),
        } for row in exports],
        "imports": [{
            "id": row.pk, "file_names": row.file_names, "package_count": row.package_count,
            "record_count": row.record_count, "status": row.status,
            "error_message": row.error_message, "created_at": row.created_at.isoformat(),
        } for row in imports],
    })


@mobile_api(["GET"])
def media_archive_download(request, pk):
    row = MediaArchiveExport.objects.filter(pk=pk, user=request.mobile_user).first()
    path = Path(row.file_path) if row else None
    if not path or not path.is_file():
        return api_error("归档文件不存在。", 404, "not_found")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@mobile_api(["POST"])
def media_archive_clear(request, pk):
    row = MediaArchiveExport.objects.filter(pk=pk, user=request.mobile_user).first()
    if not row:
        return api_error("媒体归档不存在。", 404, "not_found")
    data = parse_data(request)
    if str(data.get("confirmation", "")) != "确认清除":
        return api_error("必须完整输入“确认清除”四个字。")
    if not request.mobile_user.check_password(str(data.get("password", ""))):
        return api_error("管理员密码不正确。", 403, "invalid_password")
    clear_archived_modules(row)
    return api_ok()


@mobile_api(["POST"])
def media_archive_import(request):
    files = request.FILES.getlist("archives")
    if not files:
        return api_error("请至少选择一个媒体归档压缩包。")
    names = [item.name for item in files]
    try:
        packages, records = import_media_archives(files)
        row = MediaArchiveImport.objects.create(
            file_names=names, package_count=packages, record_count=records,
            status="completed", user=request.mobile_user,
        )
    except Exception as exc:
        MediaArchiveImport.objects.create(
            file_names=names, package_count=len(files), status="failed",
            error_message=str(exc), user=request.mobile_user,
        )
        return api_error(f"导入失败：{exc}", 400, "import_failed")
    return api_ok({"id": row.pk, "package_count": packages, "record_count": records}, 201)


@mobile_api(["POST"])
def storage_check(request):
    try:
        sent = check_storage_alerts(force=True)
    except Exception as exc:
        return api_error(f"存储检查或发信失败：{exc}", 500, "storage_check_failed")
    return api_ok({"sent": sent})
