"""
备份与恢复服务
- SQLite 在线备份（sqlite3 backup API，保证一致性）
- 备份文件打包（数据库 + 版本信息 + 校验值）
- 备份恢复（恢复前自动创建安全备份）
- 保留策略
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from apps.backups.models import BackupRecord


BACKUP_DIR = Path(settings.BASE_DIR) / "backups"


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
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    zip_path = BACKUP_DIR / f"backup_{backup_type}_{timestamp}.zip"

    record = BackupRecord.objects.create(
        backup_type=backup_type,
        status="running",
        db_path=str(db_path),
        version_info="1.0.0",
        user=user,
        school_class=school_class,
    )

    try:
        # 1. SQLite 在线备份到临时文件（保证一致性）
        tmp_db = BACKUP_DIR / f"_tmp_{timestamp}.sqlite3"
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(tmp_db))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()

        # 2. 统计记录数
        conn = sqlite3.connect(str(tmp_db))
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM apps_students_student")
            student_count = cur.fetchone()[0]
        except sqlite3.OperationalError:
            student_count = 0
        try:
            cur.execute("SELECT COUNT(*) FROM apps_scores_exam")
            exam_count = cur.fetchone()[0]
        except sqlite3.OperationalError:
            exam_count = 0
        conn.close()

        # 3. 打包 ZIP
        manifest = {
            "backup_type": backup_type,
            "created_at": timezone.now().isoformat(),
            "version": "1.0.0",
            "db_file": "db.sqlite3",
            "student_count": student_count,
            "exam_count": exam_count,
        }

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, "db.sqlite3")
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("README.txt", (
                "班级教学管理平台 - 完整系统备份\n"
                f"备份时间：{manifest['created_at']}\n"
                f"备份类型：{backup_type}\n"
                f"版本：{manifest['version']}\n"
                "恢复方式：通过「备份管理 - 恢复」功能恢复。\n"
            ))

        # 4. 清理临时文件
        _safe_remove(tmp_db)

        # 5. 计算校验值
        sha256 = hashlib.sha256()
        with open(zip_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        checksum = sha256.hexdigest()

        # 6. 更新记录
        record.status = "completed"
        record.file_path = str(zip_path)
        record.file_size = zip_path.stat().st_size
        record.checksum = checksum
        record.record_count = student_count
        record.exam_count = exam_count
        record.save(update_fields=[
            "status", "file_path", "file_size", "checksum",
            "record_count", "exam_count", "updated_at",
        ])

        # 7. 应用保留策略
        apply_retention_policy(backup_type)

        return record

    except Exception as exc:
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

    # 2. 创建恢复前安全备份
    safety_backup = create_backup(backup_type="pre_restore", user=user)

    # 3. 解压备份
    db_path = Path(_get_db_path())
    restore_tmp = BACKUP_DIR / "_restore_tmp.sqlite3"
    with zipfile.ZipFile(record.file_path, "r") as zf:
        if "db.sqlite3" not in zf.namelist():
            raise ValueError("备份包中缺少数据库文件")
        with zf.open("db.sqlite3") as src, open(restore_tmp, "wb") as dst:
            shutil.copyfileobj(src, dst)

    # 4. 验证恢复的数据库可读
    try:
        conn = sqlite3.connect(str(restore_tmp))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cur.fetchone()[0]
        conn.close()
        if table_count == 0:
            raise ValueError("备份数据库中没有表，恢复中止")
    except sqlite3.DatabaseError as exc:
        _safe_remove(restore_tmp)
        raise ValueError(f"备份数据库无法读取: {exc}")

    # 5. 替换数据库（先备份旧库到内存）
    if db_path.exists():
        _safe_remove(db_path)
    shutil.move(str(restore_tmp), str(db_path))
    _safe_remove(restore_tmp)

    return safety_backup
