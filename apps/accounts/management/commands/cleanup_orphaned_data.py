"""清理注销账号遗留的孤儿数据。

旧版注销逻辑不完整，会留下无班级的学生、无归属的备份/归档等孤儿数据，
导致重新注册同名账号后仍能看到旧数据、导入时报「学号已存在」。

用法：python manage.py cleanup_orphaned_data [--dry-run]
"""
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.students.models import Student
from apps.backups.models import BackupRecord, MediaArchiveExport, MediaArchiveImport
from apps.backups.services import _safe_remove


class Command(BaseCommand):
    help = "删除注销账号遗留的孤儿数据（无班级学生、无归属备份），恢复干净状态"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="只统计不删除，预览将要清理的数量",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        verb = "将清理" if dry else "已清理"

        # 1. 无班级的孤儿学生（含其家长记录，随学生 CASCADE）
        orphan_students = Student.objects.filter(school_class__isnull=True)
        student_count = orphan_students.count()

        # 2. 无归属的备份记录 + 物理文件
        orphan_backups = list(BackupRecord.objects.filter(school_class__isnull=True))
        backup_count = len(orphan_backups)

        # 3. 无归属的媒体归档 + 物理文件
        export_archives = list(MediaArchiveExport.objects.filter(user__isnull=True))
        import_archives = list(MediaArchiveImport.objects.filter(user__isnull=True))
        archive_count = len(export_archives) + len(import_archives)

        if not dry:
            orphan_students.delete()
            for record in orphan_backups:
                if record.file_path:
                    _safe_remove(Path(record.file_path))
            BackupRecord.objects.filter(school_class__isnull=True).delete()
            for row in export_archives + import_archives:
                if row.file_path:
                    _safe_remove(Path(row.file_path))
            MediaArchiveExport.objects.filter(user__isnull=True).delete()
            MediaArchiveImport.objects.filter(user__isnull=True).delete()

        self.stdout.write(self.style.SUCCESS(
            f"孤儿学生 {student_count} 名、备份 {backup_count} 条、"
            f"媒体归档 {archive_count} 条，{verb}。"
        ))
