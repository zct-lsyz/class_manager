"""跟进自动生成待办：纪律记录勾选「跟进」→ 自动加入待办。"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.discipline.models import ConfigurableItem, ClassroomDisciplineRecord
from apps.todos.models import TodoItem
from apps.todos.services import sync_discipline_follow_up_todo, remove_discipline_todo


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
        sync_discipline_follow_up_todo(record, self.user)
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
        sync_discipline_follow_up_todo(record, self.user)
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
        sync_discipline_follow_up_todo(record, self.user)
        record.needs_follow_up = False
        record.follow_up_result = "已整改"
        record.save()
        sync_discipline_follow_up_todo(record, self.user)
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
        sync_discipline_follow_up_todo(record, self.user)
        sync_discipline_follow_up_todo(record, self.user)
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
        sync_discipline_follow_up_todo(record, self.user)
        remove_discipline_todo(record)
        todo = TodoItem.objects.get(
            source_type="classroom_discipline", source_id=str(record.pk),
        )
        self.assertTrue(todo.is_deleted)
