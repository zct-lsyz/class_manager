"""
一次性补建家长联系方式（用于历史存量数据）

旧版本导入（学生花名册/旧版学生信息）只把联系人写入学生表，
没有创建 Guardian 家长记录，导致「家长联系方式」列表和综合档案
的「家长」选项卡为空。本命令遍历已有学生，只要学生表里存在
联系人关系/电话/备用关系/备用电话，就自动创建或更新 Guardian 记录。

用法：
    python manage.py backfill_guardians
"""
from django.core.management.base import BaseCommand

from apps.students.models import Student, Guardian
from apps.exports.import_services import _create_guardian_from_import


class Command(BaseCommand):
    help = "为已有学生补建/更新家长联系方式（从学生联系人字段回填）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="仅统计，不写入数据库",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        created = 0
        updated = 0
        skipped = 0

        students = Student.objects.filter(is_deleted=False).order_by("name_pinyin", "name")
        for student in students:
            item = {
                "primary_contact": student.primary_contact or "",
                "primary_phone": student.primary_phone or "",
                "secondary_contact": student.secondary_contact or "",
                "secondary_phone": student.secondary_phone or "",
                "home_address": student.home_address or "",
            }
            has_contact = any([
                item["primary_contact"], item["primary_phone"],
                item["secondary_contact"], item["secondary_phone"],
            ])
            if not has_contact:
                continue
            existed = Guardian.objects.filter(student=student).exists()
            if dry_run:
                self.stdout.write(
                    f"  {'更新' if existed else '创建'} {student.name} "
                    f"(联系人: {item['primary_contact'] or '-'}/{item['primary_phone'] or '-'}, "
                    f"备用: {item['secondary_contact'] or '-'}/{item['secondary_phone'] or '-'})"
                )
                skipped += 1
                continue
            _create_guardian_from_import(student, item)
            if existed:
                updated += 1
            else:
                created += 1

        if dry_run:
            self.stdout.write(self.style.WARNING(f"预览完成：共 {skipped} 条将创建/更新（未写入）"))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"完成：新建 {created} 条，更新 {updated} 条。"
            ))
