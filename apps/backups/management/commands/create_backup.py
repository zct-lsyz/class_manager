"""
创建完整备份的管理命令
用法：python manage.py create_backup [--type auto_daily|auto_weekly|auto_monthly|manual]
供 Linux cron 定时调用
"""
import logging

from django.core.management.base import BaseCommand, CommandError

from apps.backups.services import create_backup

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "创建完整系统备份（数据库+配置+校验值）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--type",
            type=str,
            default="auto_daily",
            choices=["auto_daily", "auto_weekly", "auto_monthly", "manual"],
            help="备份类型",
        )

    def handle(self, *args, **options):
        backup_type = options["type"]
        try:
            record = create_backup(backup_type=backup_type)
            self.stdout.write(
                self.style.SUCCESS(
                    f"备份成功: {record.file_path} "
                    f"({record.file_size} bytes, 学生 {record.record_count} 人)"
                )
            )
        except Exception as exc:
            logger.error(f"自动备份失败: {exc}")
            raise CommandError(f"备份失败: {exc}")
