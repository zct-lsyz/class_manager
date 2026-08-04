"""成长足迹：去重（来源事件与同步积分不重复计入）与排序。"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.students.history_services import get_student_all_events, get_student_events


class GrowthFootprintTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="growth", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="成长班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="G0001", name="初奥捷", gender="male",
        )

    def test_reward_and_its_synced_point_not_duplicated(self):
        """奖惩记录 + 其同步积分 → 足迹里只出现一次（奖惩记录），不再重复计入积分变动。"""
        from apps.rewards.models import RewardRecord
        from apps.rewards.services import sync_source_point
        reward = RewardRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 4), record_type="penalty",
            custom_name="违纪", points=-2,
        )
        sync_source_point(
            student=self.student, school_class=self.cls, semester=self.sem,
            date=reward.date, points=-2, reason="违纪",
            source_type="reward", source_id=reward.pk,
        )
        events = get_student_all_events(self.student)
        rewards_events = [e for e in events if e["module_key"] == "rewards"]
        points_events = [e for e in events if e["module_key"] == "points"]
        self.assertEqual(len(rewards_events), 1)
        self.assertEqual(len(points_events), 0)

    def test_attendance_and_its_synced_point_not_duplicated(self):
        """考勤记录 + 同步积分 → 考勤事件带分值，积分变动不再重复。"""
        from apps.attendance.models import AttendanceRecord
        from apps.rewards.services import sync_source_point
        record = AttendanceRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 4), status="late", period="evening_study",
            points_deducted=-3,
        )
        sync_source_point(
            student=self.student, school_class=self.cls, semester=self.sem,
            date=record.date, points=-3, reason="晚自习：迟到",
            source_type="attendance", source_id=record.pk,
        )
        events = get_student_all_events(self.student)
        attendance_events = [e for e in events if e["module_key"] == "attendance"]
        points_events = [e for e in events if e["module_key"] == "points"]
        self.assertEqual(len(attendance_events), 1)
        self.assertEqual(attendance_events[0]["points"], -3)
        self.assertEqual(len(points_events), 0)

    def test_manual_point_adjustment_still_shown(self):
        """手工调整的积分变动仍保留在足迹里。"""
        from apps.rewards.models import PointRecord
        PointRecord.objects.create(
            student=self.student, school_class=self.cls, semester=self.sem,
            date=date(2026, 8, 3), points=5, reason="手工奖励",
            source_type="manual",
        )
        events = get_student_all_events(self.student)
        points_events = [e for e in events if e["module_key"] == "points"]
        self.assertEqual(len(points_events), 1)
        self.assertEqual(points_events[0]["points"], 5)

    def test_points_browser_still_lists_all_points(self):
        """「积分变动」浏览（get_student_events）仍返回全部积分，不受足迹去重影响。"""
        from apps.rewards.models import RewardRecord
        from apps.rewards.services import sync_source_point
        reward = RewardRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 4), record_type="reward", custom_name="奖学金", points=5,
        )
        sync_source_point(
            student=self.student, school_class=self.cls, semester=self.sem,
            date=reward.date, points=5, reason="奖学金",
            source_type="reward", source_id=reward.pk,
        )
        points_events = get_student_events(self.student, "points")
        self.assertEqual(len(points_events), 1)

    def test_same_day_ordering_by_created_at(self):
        """同一天内按录入时间（created_at）倒序排列。"""
        from apps.discipline.models import ClassroomDisciplineRecord
        from apps.rewards.models import RewardRecord
        base = timezone.now()
        discipline = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 4), custom_content="传纸条", points_deducted=2,
        )
        reward = RewardRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 4), custom_name="奖学金", points=5,
        )
        # 手动调整 created_at（auto_now_add 不覆盖 update）
        ClassroomDisciplineRecord.objects.filter(pk=discipline.pk).update(created_at=base)
        RewardRecord.objects.filter(pk=reward.pk).update(created_at=base + timedelta(minutes=5))
        events = get_student_all_events(self.student)
        same_day = [e for e in events if e["date"] == date(2026, 8, 4)]
        # 奖学金（created_at 更晚）应排在传纸条前面
        self.assertEqual(same_day[0]["item"], "奖学金")
        self.assertEqual(same_day[1]["item"], "传纸条")
