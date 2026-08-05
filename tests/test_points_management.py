"""积分管理：加分/扣分选择、作业积分规则、奖惩条目类型与罚分。"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class PointsSignTests(TestCase):
    """考勤/纪律：分值恒为正，加分/扣分由选择决定。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="points", password="pass")
        self.client = Client()
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="积分班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="P0001", name="小明", gender="male",
        )

    def test_attendance_deduct_is_negative(self):
        """考勤选「扣分」→ points_deducted 存负数（正=加分、负=扣分）。"""
        from apps.attendance.models import AttendanceRecord
        self.client.post(reverse("attendance:create"), {
            "students": [self.student.pk], "date": "2026-08-04",
            "status": "late", "period": "morning",
            "points_sign": "deduct", "points_deducted": "5",
        })
        record = AttendanceRecord.objects.get(student=self.student)
        self.assertEqual(record.points_deducted, -5)

    def test_attendance_add_is_positive(self):
        from apps.attendance.models import AttendanceRecord
        self.client.post(reverse("attendance:create"), {
            "students": [self.student.pk], "date": "2026-08-04",
            "status": "late", "period": "morning",
            "points_sign": "add", "points_deducted": "5",
        })
        record = AttendanceRecord.objects.get(student=self.student)
        self.assertEqual(record.points_deducted, 5)

    def test_discipline_deduct_is_positive(self):
        """纪律选「扣分」→ points_deducted 存正数（正=扣分、负=加分）。"""
        from apps.discipline.models import ClassroomDisciplineRecord
        self.client.post(reverse("discipline:classroom_create"), {
            "student": self.student.pk, "date": "2026-08-04",
            "severity": "moderate",
            "points_sign": "deduct", "points_deducted": "3",
        })
        record = ClassroomDisciplineRecord.objects.get(student=self.student)
        self.assertEqual(record.points_deducted, 3)

    def test_discipline_add_is_negative(self):
        from apps.discipline.models import ClassroomDisciplineRecord
        self.client.post(reverse("discipline:classroom_create"), {
            "student": self.student.pk, "date": "2026-08-04",
            "severity": "moderate",
            "points_sign": "add", "points_deducted": "3",
        })
        record = ClassroomDisciplineRecord.objects.get(student=self.student)
        self.assertEqual(record.points_deducted, -3)

    def test_web_ranking_filters_totals_and_details_by_date_range(self):
        from apps.rewards.models import PointRecord
        PointRecord.objects.create(school_class=self.cls, student=self.student, date=date(2026, 8, 1), points=2, reason="范围外", source_type="reward")
        PointRecord.objects.create(school_class=self.cls, student=self.student, date=date(2026, 8, 5), points=5, reason="范围内", source_type="reward")
        response = self.client.get(reverse("rewards:points"), {"date_from": "2026-08-04", "date_to": "2026-08-06"})
        self.assertEqual(response.context["student_points"][0]["total"], 5)
        self.assertEqual([row.reason for row in response.context["page_obj"]], ["范围内"])


class HomeworkPointRuleTests(TestCase):
    """作业优秀/未交等状态的自定义加减分规则。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="hwpts", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="作业班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="H0001", name="小红", gender="female",
        )

    def test_excellent_custom_points(self):
        from apps.homework.models import HomeworkTask, HomeworkRecord, HomeworkPointRule
        from apps.homework.views import _sync_homework_points
        from apps.rewards.models import PointRecord
        task = HomeworkTask.objects.create(
            school_class=self.cls, semester=self.sem, title="作业1",
            assigned_date=date(2026, 8, 4),
        )
        record = HomeworkRecord.objects.create(task=task, student=self.student, status="excellent")
        # 未配置：默认 +2
        _sync_homework_points(record)
        self.assertEqual(
            PointRecord.objects.get(source_type="homework", source_id=record.pk).points, 2,
        )
        # 配置：优秀 +5
        HomeworkPointRule.objects.create(school_class=self.cls, status="excellent", points=5, is_add=True)
        _sync_homework_points(record)
        self.assertEqual(
            PointRecord.objects.get(source_type="homework", source_id=record.pk).points, 5,
        )

    def test_unsubmitted_deduct_points(self):
        from apps.homework.models import HomeworkTask, HomeworkRecord, HomeworkPointRule
        from apps.homework.views import _sync_homework_points
        from apps.rewards.models import PointRecord
        task = HomeworkTask.objects.create(
            school_class=self.cls, semester=self.sem, title="作业2",
            assigned_date=date(2026, 8, 4),
        )
        HomeworkPointRule.objects.create(school_class=self.cls, status="unsubmitted", points=3, is_add=False)
        record = HomeworkRecord.objects.create(task=task, student=self.student, status="unsubmitted")
        _sync_homework_points(record)
        self.assertEqual(
            PointRecord.objects.get(source_type="homework", source_id=record.pk).points, -3,
        )


class RewardTypeTests(TestCase):
    """奖惩条目类型 + 惩罚记录分值为负。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="rwtype", password="pass")
        self.client = Client()
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="奖惩班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="R0001", name="小刚", gender="male",
        )

    def test_reward_item_type_saved(self):
        """新增条目可选择类型（奖励/惩罚）。"""
        from apps.rewards.models import RewardItem
        self.client.post(reverse("rewards:rules"), {
            "item_type": "penalty", "name": "打架", "default_points": "5",
            "sort_order": "0", "is_active": "on",
        })
        item = RewardItem.objects.get(name="打架")
        self.assertEqual(item.item_type, "penalty")

    def test_penalty_record_points_negative(self):
        """选「惩罚」时，填正分值保存后为负。"""
        from apps.rewards.models import RewardRecord
        resp = self.client.post(reverse("rewards:reward_create"), {
            "students": [self.student.pk], "date": "2026-08-04",
            "record_type": "penalty", "level": "serious", "points": "2",
        })
        self.assertEqual(resp.status_code, 302)
        record = RewardRecord.objects.get(student=self.student)
        self.assertEqual(record.points, -2)
