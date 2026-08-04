"""跟进自动生成待办：各模块勾选「跟进」→ 自动加入待办。"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.discipline.models import ConfigurableItem, ClassroomDisciplineRecord
from apps.todos.models import TodoItem
from apps.todos.services import sync_follow_up_todo, remove_follow_up_todo


class FollowUpTodoTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="todo-sync", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="一班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="T0001", name="小明", gender="male",
        )
        self.item = ConfigurableItem.objects.create(
            school_class=self.cls, module="classroom_discipline", name="上课说话",
        )

    def test_follow_up_creates_todo(self):
        """勾选跟进时按跟进日期和项目自动创建待办。"""
        record = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), item=self.item, severity="serious",
            needs_follow_up=True, follow_up_date=date(2026, 8, 5),
        )
        sync_follow_up_todo(record, self.user)
        todo = TodoItem.objects.get(
            source_type="classroom_discipline", source_id=str(record.pk),
        )
        self.assertEqual(todo.title, "课堂纪律跟进：上课说话（小明）")
        self.assertEqual(timezone.localtime(todo.deadline).date(), date(2026, 8, 5))
        self.assertEqual(todo.student, self.student)
        self.assertEqual(todo.school_class, self.cls)
        self.assertEqual(todo.created_by, self.user)
        self.assertEqual(todo.priority, 1)  # serious → 高
        self.assertFalse(todo.is_completed)

    def test_no_follow_up_no_todo(self):
        """未勾选跟进的记录不生成待办。"""
        record = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), item=self.item, needs_follow_up=False,
        )
        sync_follow_up_todo(record, self.user)
        self.assertEqual(
            TodoItem.objects.filter(source_type="classroom_discipline").count(), 0,
        )

    def test_follow_up_processed_completes_todo(self):
        """跟进处理完成后，对应待办标记为已完成。"""
        record = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), item=self.item,
            needs_follow_up=True, follow_up_date=date(2026, 8, 5),
        )
        sync_follow_up_todo(record, self.user)
        record.needs_follow_up = False
        record.follow_up_result = "已整改"
        record.save()
        sync_follow_up_todo(record, self.user)
        todo = TodoItem.objects.get(
            source_type="classroom_discipline", source_id=str(record.pk),
        )
        self.assertTrue(todo.is_completed)
        self.assertIsNotNone(todo.completed_at)

    def test_sync_dedupes_on_resync(self):
        """重复同步同一记录不产生重复待办。"""
        record = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), item=self.item,
            needs_follow_up=True, follow_up_date=date(2026, 8, 5),
        )
        sync_follow_up_todo(record, self.user)
        sync_follow_up_todo(record, self.user)
        self.assertEqual(
            TodoItem.objects.filter(
                source_type="classroom_discipline", source_id=str(record.pk),
            ).count(), 1,
        )

    def test_remove_todo_on_record_delete(self):
        """记录删除时关联待办一并软删除。"""
        record = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), item=self.item,
            needs_follow_up=True, follow_up_date=date(2026, 8, 5),
        )
        sync_follow_up_todo(record, self.user)
        remove_follow_up_todo(record)
        todo = TodoItem.objects.get(
            source_type="classroom_discipline", source_id=str(record.pk),
        )
        self.assertTrue(todo.is_deleted)


class FollowUpTodoExtendedTests(TestCase):
    """考勤/作业/卫生/奖惩勾选跟进自动生成待办。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="todo-ext", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="拓展班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="T0002", name="小明", gender="male",
        )

    def test_attendance_follow_up_creates_todo(self):
        from apps.attendance.models import AttendanceRecord
        record = AttendanceRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), status="late", reason="迟到未到",
            needs_follow_up=True, follow_up_date=date(2026, 8, 5),
        )
        sync_follow_up_todo(record, self.user)
        todo = TodoItem.objects.get(source_type="attendance", source_id=str(record.pk))
        self.assertEqual(todo.title, "考勤跟进：迟到未到（小明）")
        self.assertEqual(timezone.localtime(todo.deadline).date(), date(2026, 8, 5))

    def test_homework_task_follow_up_creates_todo(self):
        from apps.homework.models import HomeworkTask
        task = HomeworkTask.objects.create(
            school_class=self.cls, semester=self.sem, title="数学作业",
            assigned_date=date(2026, 8, 2),
            needs_follow_up=True, follow_up_date=date(2026, 8, 6),
        )
        sync_follow_up_todo(task, self.user)
        todo = TodoItem.objects.get(source_type="homework", source_id=str(task.pk))
        self.assertEqual(todo.title, "作业跟进：数学作业")
        self.assertIsNone(todo.student)

    def test_hygiene_follow_up_creates_todo(self):
        from apps.dormitory.models import DormBuilding, DormRoom, DormHygieneCheck
        building = DormBuilding.objects.create(school_class=self.cls, name="一栋")
        room = DormRoom.objects.create(building=building, room_number="101")
        check = DormHygieneCheck.objects.create(
            room=room, school_class=self.cls, semester=self.sem,
            date=date(2026, 8, 2),
            needs_follow_up=True, follow_up_date=date(2026, 8, 7),
        )
        sync_follow_up_todo(check, self.user)
        todo = TodoItem.objects.get(source_type="hygiene", source_id=str(check.pk))
        self.assertEqual(todo.title, "卫生检查跟进：一栋 101")
        self.assertIsNone(todo.student)

    def test_reward_follow_up_creates_todo(self):
        from apps.rewards.models import RewardRecord
        record = RewardRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), custom_name="月考优秀",
            needs_follow_up=True, follow_up_date=date(2026, 8, 8),
        )
        sync_follow_up_todo(record, self.user)
        todo = TodoItem.objects.get(source_type="reward", source_id=str(record.pk))
        self.assertEqual(todo.title, "奖惩跟进：月考优秀（小明）")
