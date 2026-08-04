"""把「已分配宿舍但未占床」的学生补分到空闲床位。

历史导入中床位号未匹配（如 3 vs 生成的 03）会产生 bed=None 的当前分配，
导致宿舍床位分布图里看不到学生、而宿舍列表统计却计入。运行本命令一次性补齐。

用法：python manage.py assign_dormitory_beds [--dry-run]
"""
from django.core.management.base import BaseCommand

from apps.dormitory.models import DormAssignment
from apps.exports.import_services import _first_free_bed


class Command(BaseCommand):
    help = "为已分配宿舍但未占床的学生自动补分空闲床位"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="只统计不写入，预览将要补分的数量",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        bedless = list(DormAssignment.objects.filter(
            is_current=True, bed__isnull=True,
        ).select_related("room", "student").order_by("room_id", "student__sort_order"))

        placed = 0
        skipped = 0
        for assignment in bedless:
            bed = _first_free_bed(assignment.room)
            if not bed:
                skipped += 1
                continue
            if dry_run:
                placed += 1
                continue
            assignment.bed = bed
            assignment.save(update_fields=["bed", "updated_at"])
            student = assignment.student
            if student.bed_number != bed.bed_number:
                student.bed_number = bed.bed_number
                student.save(update_fields=["bed_number", "updated_at"])
            placed += 1

        verb = "将补分" if dry_run else "已补分"
        self.stdout.write(
            self.style.SUCCESS(f"共 {len(bedless)} 名未占床学生，{verb} {placed} 名，{skipped} 名因无空闲床位跳过。")
        )
