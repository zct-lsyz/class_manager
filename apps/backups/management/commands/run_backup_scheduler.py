"""在独立容器中运行每日、每周和每月备份计划。"""
import json
import os
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.backups.services import create_backup
from apps.seating.services import rotate_due_plans
from apps.backups.storage_services import check_storage_alerts


class Command(BaseCommand):
    help = "运行自动备份调度器"

    def add_arguments(self, parser):
        parser.add_argument(
            "--once", action="store_true", help="只检查一次计划后退出"
        )

    def handle(self, *args, **options):
        state_path = Path(settings.BASE_DIR) / "backups" / ".scheduler_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        daily_time = os.environ.get("BACKUP_DAILY_TIME", "02:30")
        weekly_time = os.environ.get("BACKUP_WEEKLY_TIME", "03:00")
        monthly_time = os.environ.get("BACKUP_MONTHLY_TIME", "03:30")

        self.stdout.write("自动备份调度器已启动")
        while True:
            now = timezone.localtime()
            today = now.date().isoformat()
            current_time = now.strftime("%H:%M")
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                state = {}

            if state.get("seating_rotation") != today:
                try:
                    rotated = rotate_due_plans(now.date())
                    state["seating_rotation"] = today
                    state_path.write_text(
                        json.dumps(state, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if rotated:
                        self.stdout.write(self.style.SUCCESS(f"座位方案自动轮换完成: {rotated} 个"))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"座位方案自动轮换失败: {exc}"))

            if state.get("storage_alerts") != today:
                try:
                    sent = check_storage_alerts()
                    state["storage_alerts"] = today
                    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                    if sent:
                        self.stdout.write(self.style.SUCCESS(f"存储空间提醒已发送: {sent} 封"))
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"存储空间检查失败: {exc}"))

            due_types = []
            if current_time >= daily_time and state.get("auto_daily") != today:
                due_types.append("auto_daily")
            if (
                now.weekday() == 6
                and current_time >= weekly_time
                and state.get("auto_weekly") != today
            ):
                due_types.append("auto_weekly")
            if (
                now.day == 1
                and current_time >= monthly_time
                and state.get("auto_monthly") != today
            ):
                due_types.append("auto_monthly")

            for backup_type in due_types:
                try:
                    record = create_backup(backup_type=backup_type)
                    state[backup_type] = today
                    state_path.write_text(
                        json.dumps(state, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    self.stdout.write(
                        self.style.SUCCESS(f"自动备份完成: {record.file_path}")
                    )
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(f"自动备份失败: {exc}"))

            if options["once"]:
                return
            time.sleep(30)
