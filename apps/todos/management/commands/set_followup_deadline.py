"""把已有「跟进」自动生成的待办截止时间统一设为当天 22:00。

用法：python manage.py set_followup_deadline [--dry-run]
"""
from datetime import datetime, time as dt_time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.todos.models import TodoItem


class Command(BaseCommand):
    help = "把跟进自动生成的待办截止时间统一设为当天 22:00"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="只统计不写入，预览将更新的数量",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        # source_type 非空的待办 = 由各模块勾选「跟进」自动生成
        todos = TodoItem.objects.filter(
            is_deleted=False, source_type__gt="", deadline__isnull=False,
        )
        updated = 0
        for todo in todos:
            local_date = timezone.localtime(todo.deadline).date()
            new_deadline = timezone.make_aware(datetime.combine(local_date, dt_time(22, 0)))
            if todo.deadline == new_deadline:
                continue
            if not dry:
                todo.deadline = new_deadline
                todo.save(update_fields=["deadline", "updated_at"])
            updated += 1
        verb = "将更新" if dry else "已更新"
        self.stdout.write(self.style.SUCCESS(f"跟进待办 {updated} 条，{verb}为当天 22:00。"))
