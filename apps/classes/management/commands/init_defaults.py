"""
初始化系统默认数据
用法：python manage.py init_defaults [--class-name "高一(1)班"]
创建：默认班级、科目、课堂纪律条目、宿舍纪律条目、奖励条目、卫生项目
"""
from django.core.management.base import BaseCommand

from apps.classes.models import SchoolClass, Semester
from apps.classes.subjects import Subject
from apps.discipline.models import ConfigurableItem
from apps.rewards.models import RewardItem
from apps.dormitory.models import DormHygieneItem


class Command(BaseCommand):
    help = "初始化系统默认数据（班级、科目、纪律条目、奖励条目、卫生项目）"

    def add_arguments(self, parser):
        parser.add_argument("--class-name", type=str, default="高一(1)班", help="班级名称")
        parser.add_argument("--academic-year", type=str, default="2026-2027", help="学年")
        parser.add_argument("--force", action="store_true", help="已存在数据时仍执行")

    def handle(self, *args, **options):
        # ---------- 1. 班级 ----------
        cls, created = SchoolClass.objects.get_or_create(
            name=options["class_name"],
            defaults={"grade": "高一", "is_current": True},
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"创建班级: {cls.name}"))
        else:
            cls.is_current = True
            cls.save()
            self.stdout.write(f"班级已存在: {cls.name}")

        # ---------- 2. 学期 ----------
        sem, sem_created = Semester.objects.get_or_create(
            school_class=cls,
            academic_year=options["academic_year"],
            semester_type="first",
            defaults={"is_current": True},
        )
        if sem_created:
            self.stdout.write(self.style.SUCCESS(f"创建学期: {sem.get_display_name()}"))
        else:
            sem.is_current = True
            sem.save()

        # ---------- 3. 科目 ----------
        subjects = [
            ("语文", "语"), ("数学", "数"), ("英语", "英"),
            ("物理", "物"), ("化学", "化"), ("生物", "生"),
            ("政治", "政"), ("历史", "史"), ("地理", "地"),
        ]
        for i, (name, short) in enumerate(subjects):
            _, created = Subject.objects.get_or_create(
                name=name, defaults={"short_name": short, "sort_order": i}
            )
            if created:
                self.stdout.write(f"  科目: {name}")

        # ---------- 4. 课堂纪律条目 ----------
        classroom_items = [
            ("上课迟到", 2, "moderate", False),
            ("随意讲话", 1, "mild", False),
            ("睡觉", 2, "moderate", True),
            ("打闹", 3, "serious", True),
            ("玩手机", 3, "serious", True),
            ("未带学习用品", 1, "mild", False),
            ("扰乱课堂", 3, "serious", True),
            ("不服从课堂安排", 3, "serious", True),
            ("抄袭作业", 2, "moderate", True),
            ("其他", 1, "mild", False),
        ]
        for i, (name, points, severity, follow) in enumerate(classroom_items):
            _, created = ConfigurableItem.objects.get_or_create(
                school_class=cls, module="classroom_discipline", name=name,
                defaults={
                    "default_points": points,
                    "default_severity": severity,
                    "needs_follow_up": follow,
                    "sort_order": i,
                },
            )
            if created:
                self.stdout.write(f"  课堂纪律条目: {name}")

        # ---------- 5. 宿舍纪律条目 ----------
        dorm_items = [
            ("未按时就寝", 2, "moderate", True),
            ("熄灯后讲话", 1, "mild", False),
            ("使用手机", 3, "serious", True),
            ("串寝", 2, "moderate", True),
            ("影响他人休息", 2, "moderate", True),
            ("未按规定起床", 1, "mild", False),
            ("私拉电线", 5, "critical", True),
            ("使用违规电器", 5, "critical", True),
            ("物品摆放不规范", 1, "mild", False),
            ("宿舍内打闹", 3, "serious", True),
            ("未履行值日职责", 2, "moderate", True),
            ("其他", 1, "mild", False),
        ]
        for i, (name, points, severity, follow) in enumerate(dorm_items):
            _, created = ConfigurableItem.objects.get_or_create(
                school_class=cls, module="dorm_discipline", name=name,
                defaults={
                    "default_points": points,
                    "default_severity": severity,
                    "needs_follow_up": follow,
                    "sort_order": i,
                },
            )
            if created:
                self.stdout.write(f"  宿舍纪律条目: {name}")

        # ---------- 6. 奖励条目 ----------
        reward_items = [
            ("课堂积极", 1), ("作业优秀", 1), ("成绩进步", 2),
            ("乐于助人", 1), ("卫生优秀", 1), ("宿舍优秀", 1),
            ("活动贡献", 1), ("班级荣誉", 2), ("校级荣誉", 3),
            ("其他", 1),
        ]
        for i, (name, points) in enumerate(reward_items):
            _, created = RewardItem.objects.get_or_create(
                school_class=cls, name=name,
                defaults={"default_points": points, "sort_order": i},
            )
            if created:
                self.stdout.write(f"  奖励条目: {name}")

        # ---------- 7. 卫生项目 ----------
        hygiene_items = [
            ("地面", 10), ("床铺", 10), ("桌面", 10),
            ("物品摆放", 10), ("垃圾", 10), ("门窗", 10),
            ("卫生间", 10), ("阳台", 10), ("整体评价", 10),
        ]
        for i, (name, full) in enumerate(hygiene_items):
            _, created = DormHygieneItem.objects.get_or_create(
                school_class=cls, name=name,
                defaults={"full_score": full, "sort_order": i},
            )
            if created:
                self.stdout.write(f"  卫生项目: {name}")

        self.stdout.write(self.style.SUCCESS(
            f"\n初始化完成！当前班级: {cls.name}，当前学期: {sem.get_display_name()}"
        ))
