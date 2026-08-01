"""
备份与恢复服务
- SQLite 在线备份（sqlite3 backup API，保证一致性）
- 备份文件打包（数据库 + 版本信息 + 校验值）
- 备份恢复（恢复前自动创建安全备份）
- 保留策略
"""
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.backups.models import BackupRecord


BACKUP_DIR = Path(settings.BASE_DIR) / "backups"
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")


def _sha256_file(path):
    sha256 = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _iter_files(root):
    root = Path(root)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _migration_versions():
    return [
        {"app": app, "name": name}
        for app, name in MigrationRecorder.Migration.objects.order_by(
            "app", "applied"
        ).values_list("app", "name")
    ]


def _validate_zip_members(zip_file):
    for member in zip_file.infolist():
        member_path = Path(member.filename)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"备份包包含不安全路径: {member.filename}")


def _validate_sqlite(path):
    connection = sqlite3.connect(str(path))
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        table_count = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    finally:
        connection.close()
    if not result or result[0] != "ok":
        raise ValueError("备份数据库完整性检查失败")
    if table_count == 0:
        raise ValueError("备份数据库中没有数据表")


def _safe_remove(path):
    """安全删除文件（兼容 Windows 沙箱环境）"""
    try:
        if path.exists():
            os.remove(str(path))
    except OSError:
        pass


def _get_db_path():
    """获取当前数据库路径"""
    return settings.DATABASES["default"]["NAME"]


def create_backup(backup_type="manual", user=None, school_class=None):
    """
    创建完整备份
    返回 BackupRecord
    """
    db_path = Path(_get_db_path())
    if not db_path.exists():
        raise FileNotFoundError(f"数据库文件不存在: {db_path}")

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S_%f")
    zip_path = BACKUP_DIR / f"backup_{backup_type}_{timestamp}.zip"

    record = BackupRecord.objects.create(
        backup_type=backup_type,
        status="running",
        db_path=str(db_path),
        version_info=APP_VERSION,
        user=user,
        school_class=school_class,
    )

    try:
        with tempfile.TemporaryDirectory(dir=BACKUP_DIR) as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            tmp_db = temp_dir / "db.sqlite3"

            # 1. SQLite 在线备份到临时文件（保证一致性）
            src = sqlite3.connect(str(db_path))
            dst = sqlite3.connect(str(tmp_db))
            try:
                with dst:
                    src.backup(dst)
            finally:
                src.close()
                dst.close()
            _validate_sqlite(tmp_db)

            # 2. 使用 ORM 统计，避免依赖数据库表名
            from apps.students.models import Student
            from apps.scores.models import Exam

            student_count = Student.objects.filter(is_deleted=False).count()
            exam_count = Exam.objects.filter(is_deleted=False).count()
            media_files = _iter_files(settings.MEDIA_ROOT)
            migrations = _migration_versions()

            manifest = {
                "backup_type": backup_type,
                "created_at": timezone.now().isoformat(),
                "version": APP_VERSION,
                "database": "database/db.sqlite3",
                "student_count": student_count,
                "exam_count": exam_count,
                "attachment_count": len(media_files),
                "settings_module": os.environ.get(
                    "DJANGO_SETTINGS_MODULE", "config.settings.production"
                ),
                "migrations": migrations,
                "files": {},
            }

            system_config = {
                "version": APP_VERSION,
                "time_zone": settings.TIME_ZONE,
                "language_code": settings.LANGUAGE_CODE,
                "database_engine": settings.DATABASES["default"]["ENGINE"],
                "settings_module": manifest["settings_module"],
            }

            # 3. 打包数据库、附件和无密钥配置元数据
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(tmp_db, manifest["database"])
                manifest["files"][manifest["database"]] = {
                    "size": tmp_db.stat().st_size,
                    "sha256": _sha256_file(tmp_db),
                }
                media_root = Path(settings.MEDIA_ROOT)
                for media_file in media_files:
                    archive_name = (
                        Path("media") / media_file.relative_to(media_root)
                    ).as_posix()
                    zf.write(media_file, archive_name)
                    manifest["files"][archive_name] = {
                        "size": media_file.stat().st_size,
                        "sha256": _sha256_file(media_file),
                    }
                zf.writestr(
                    "config/system.json",
                    json.dumps(system_config, ensure_ascii=False, indent=2),
                )
                zf.writestr(
                    "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
                zf.writestr(
                    "README.txt",
                    "班级教学管理平台 - 完整系统备份\n"
                    f"备份时间：{manifest['created_at']}\n"
                    f"备份类型：{backup_type}\n"
                    f"版本：{manifest['version']}\n"
                    "内容：SQLite 数据库、上传附件、迁移清单和配置元数据。\n"
                    "注意：环境变量、密码和 API Key 不写入备份。\n",
                )

        # 4. 计算整包校验值
        checksum = _sha256_file(zip_path)

        # 5. 更新记录
        record.status = "completed"
        record.file_path = str(zip_path)
        record.file_size = zip_path.stat().st_size
        record.checksum = checksum
        record.record_count = student_count
        record.exam_count = exam_count
        record.attachment_count = len(media_files)
        record.migration_version = ", ".join(
            f"{item['app']}.{item['name']}" for item in migrations[-10:]
        )[:100]
        record.save(update_fields=[
            "status", "file_path", "file_size", "checksum",
            "record_count", "exam_count", "attachment_count",
            "migration_version", "updated_at",
        ])

        # 6. 应用保留策略
        apply_retention_policy(backup_type)

        return record

    except Exception as exc:
        _safe_remove(zip_path)
        record.status = "failed"
        record.error_message = str(exc)
        record.save(update_fields=["status", "error_message", "updated_at"])
        raise


def apply_retention_policy(backup_type):
    """
    保留策略：
    每日备份保留 14 份，每周 8 份，每月 12 份，手动备份不删除
    """
    retention_map = {
        "auto_daily": 14,
        "auto_weekly": 8,
        "auto_monthly": 12,
    }
    keep = retention_map.get(backup_type)
    if not keep:
        return

    records = BackupRecord.objects.filter(
        backup_type=backup_type, status="completed"
    ).order_by("-created_at")
    for old in records[keep:]:
        if old.file_path and Path(old.file_path).exists():
            _safe_remove(Path(old.file_path))
        old.status = "completed"
        old.file_path = ""
        old.save(update_fields=["file_path"])


def verify_backup(record):
    """校验备份文件完整性"""
    if not record.file_path or not Path(record.file_path).exists():
        return False, "备份文件不存在"
    sha256 = hashlib.sha256()
    with open(record.file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    current = sha256.hexdigest()
    if record.checksum and current != record.checksum:
        return False, "文件校验值不匹配，文件可能已损坏"
    return True, "校验通过"


def restore_backup(record, user=None):
    """
    恢复备份
    流程：校验 → 恢复前安全备份 → 替换数据库 → 校验
    """
    # 1. 校验备份完整性
    ok, msg = verify_backup(record)
    if not ok:
        raise ValueError(f"备份校验失败: {msg}")

    db_path = Path(_get_db_path())
    media_root = Path(settings.MEDIA_ROOT)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    media_root.parent.mkdir(parents=True, exist_ok=True)

    # 2. 先完整解包到隔离目录并校验，不接触当前数据
    with tempfile.TemporaryDirectory(dir=BACKUP_DIR) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        with zipfile.ZipFile(record.file_path, "r") as zip_file:
            _validate_zip_members(zip_file)
            names = set(zip_file.namelist())
            database_member = (
                "database/db.sqlite3"
                if "database/db.sqlite3" in names
                else "db.sqlite3"
            )
            if database_member not in names:
                raise ValueError("备份包中缺少数据库文件")
            zip_file.extractall(temp_dir)

        restore_db = temp_dir / database_member
        try:
            _validate_sqlite(restore_db)
        except sqlite3.DatabaseError as exc:
            raise ValueError(f"备份数据库无法读取: {exc}")

        manifest_path = temp_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for file_name, file_info in manifest.get("files", {}).items():
                extracted_file = temp_dir / file_name
                if not extracted_file.is_file():
                    raise ValueError(f"备份包缺少清单文件: {file_name}")
                expected = file_info.get("sha256", "")
                if expected and _sha256_file(extracted_file) != expected:
                    raise ValueError(f"备份成员校验失败: {file_name}")

        # 3. 校验通过后创建恢复前安全备份
        safety_backup = create_backup(backup_type="pre_restore", user=user)

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        staged_db = db_path.parent / f".{db_path.name}.restore-{timestamp}.tmp"
        rollback_db = db_path.parent / f".{db_path.name}.before-{timestamp}.tmp"
        staged_media = media_root.parent / f".{media_root.name}.restore-{timestamp}"
        rollback_media = media_root.parent / f".{media_root.name}.before-{timestamp}"
        extracted_media = temp_dir / "media"

        shutil.copy2(restore_db, staged_db)
        if extracted_media.exists():
            shutil.copytree(extracted_media, staged_media)
        else:
            staged_media.mkdir()

        db_replaced = False
        media_replaced = False
        try:
            # 4. 关闭连接后替换数据库（文件可原子重命名）
            connections.close_all()
            if db_path.exists():
                os.replace(db_path, rollback_db)
            os.replace(staged_db, db_path)
            db_replaced = True

            # 5. 替换 media 目录内容。
            #    Docker 中 /app/media 常为 volume 挂载点，目录本身不能重命名（Device or resource busy），
            #    因此采用「备份副本 + 清空 + 复制新内容」的方式，而不是重命名挂载点。
            if rollback_media.exists():
                shutil.rmtree(rollback_media, ignore_errors=True)
            if media_root.exists():
                shutil.copytree(media_root, rollback_media, dirs_exist_ok=True)
                # 清空 media_root 内所有内容（保留挂载点目录本身）
                for child in media_root.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            else:
                media_root.mkdir(parents=True, exist_ok=True)
            if staged_media.exists():
                shutil.copytree(staged_media, media_root, dirs_exist_ok=True)
            media_replaced = True

            _validate_sqlite(db_path)
        except Exception:
            connections.close_all()
            if db_replaced and db_path.exists():
                _safe_remove(db_path)
            if rollback_db.exists():
                os.replace(rollback_db, db_path)
            if media_replaced and media_root.exists():
                for child in media_root.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            if rollback_media.exists():
                shutil.copytree(rollback_media, media_root, dirs_exist_ok=True)
            raise
        finally:
            _safe_remove(staged_db)
            if staged_media.exists():
                shutil.rmtree(staged_media, ignore_errors=True)

        _safe_remove(rollback_db)
        if rollback_media.exists():
            shutil.rmtree(rollback_media, ignore_errors=True)
        connections.close_all()

        return safety_backup
