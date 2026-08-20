"""复现：预警管理作业检查规则筛选。"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.homework.models import HomeworkTask, HomeworkRecord, Subject
from apps.attendance.models import WarningRule


class HomeworkWarningReproTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="hw-warn", password="pass12345")
        self.client.login(username="hw-warn", password="pass12345")
        self.cls = SchoolClass.objects.create(created_by=self.user, name="作业班", is_current=True)
        self.sem = Semester.objects.create(school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True)
        self.s = Student.objects.create(school_class=self.cls, name="张三", gender="male")
        self.task = HomeworkTask.objects.create(school_class=self.cls, semester=self.sem, title="数学作业", assigned_date="2026-08-03")

    def test_homework_rule_filters_student(self):
        # 张三未交
        HomeworkRecord.objects.create(task=self.task, student=self.s, status="unsubmitted")
        WarningRule.objects.create(
            school_class=self.cls, name="作业检查预警", content="homework",
            unit="count", threshold=1, is_active=True,
        )
        resp = self.client.get(reverse("dashboard:warnings"))
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode("utf-8")
        self.assertIn("张三", html)
        self.assertIn("作业检查预警", html)

    def test_homework_events_have_adverse(self):
        from apps.students.history_services import get_student_events
        HomeworkRecord.objects.create(task=self.task, student=self.s, status="unsubmitted")
        events = get_student_events(self.s, "homework")
        self.assertTrue(events, "应有作业事件")
        self.assertTrue(all(e["adverse"] for e in events))
