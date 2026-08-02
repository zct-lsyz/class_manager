"""
账户隔离回归测试：用户 B 不能访问/修改用户 A 的数据
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.homework.models import Subject, HomeworkTask
from apps.students.models import Student
from apps.todos.models import TodoItem
from apps.scores.models import Exam
from apps.backups.models import BackupRecord


class AccountIsolationTests(TestCase):
    """跨账户越权访问防护"""

    def setUp(self):
        User = get_user_model()
        # 用户 A 及其数据
        self.user_a = User.objects.create_user(username="iso-a", password="pass")
        self.client_a = Client()
        self.client_a.force_login(self.user_a)
        self.cls_a = SchoolClass.objects.create(
            created_by=self.user_a, name="A班", is_current=True,
        )
        self.sem_a = Semester.objects.create(
            school_class=self.cls_a, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student_a = Student.objects.create(
            school_class=self.cls_a, student_id="A0001", name="A学生", gender="male",
        )
        self.subject_a = Subject.objects.create(name="语文", created_by=self.user_a)
        self.task_a = HomeworkTask.objects.create(
            school_class=self.cls_a, semester=self.sem_a, subject=self.subject_a,
            title="A的作业", assigned_date=date(2026, 8, 2),
        )
        self.todo_a = TodoItem.objects.create(
            school_class=self.cls_a, created_by=self.user_a, title="A的待办", priority=2,
        )
        self.exam_a = Exam.objects.create(
            school_class=self.cls_a, semester=self.sem_a, name="A的考试", date=date(2026, 8, 2),
        )
        self.backup_a = BackupRecord.objects.create(
            user=self.user_a, school_class=self.cls_a,
            backup_type="manual", status="completed", file_path="/tmp/a.zip",
        )

        # 用户 B（有自己的班级，但数据与 A 无关）
        self.user_b = get_user_model().objects.create_user(username="iso-b", password="pass")
        self.client_b = Client()
        self.client_b.force_login(self.user_b)
        self.cls_b = SchoolClass.objects.create(
            created_by=self.user_b, name="B班", is_current=True,
        )

    def test_dashboard_requires_class(self):
        """无班级的新用户访问仪表盘应跳转班级设置，而非看到全库统计"""
        user_c = get_user_model().objects.create_user(username="iso-c", password="pass")
        client_c = Client()
        client_c.force_login(user_c)
        response = client_c.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("classes:settings"), response.url)

    def test_student_detail_is_isolated(self):
        response = self.client_b.get(
            reverse("students:detail", args=[self.student_a.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_student_delete_is_isolated(self):
        response = self.client_b.post(
            reverse("students:delete", args=[self.student_a.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Student.objects.filter(pk=self.student_a.pk).exists())

    def test_guardian_list_is_isolated(self):
        from apps.students.models import Guardian
        Guardian.objects.create(
            student=self.student_a,
            father_name="A家长", father_phone="13800000000",
            mother_name="", mother_phone="", primary_contact="father",
        )
        response = self.client_b.get(reverse("students:guardian_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "A家长")
        self.assertNotContains(response, "13800000000")

    def test_homework_delete_is_isolated(self):
        response = self.client_b.post(
            reverse("homework:task_delete", args=[self.task_a.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(HomeworkTask.objects.filter(pk=self.task_a.pk).exists())

    def test_todo_toggle_is_isolated(self):
        response = self.client_b.post(
            reverse("todos:toggle", args=[self.todo_a.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.todo_a.refresh_from_db()
        self.assertFalse(self.todo_a.is_completed)

    def test_exam_detail_is_isolated(self):
        response = self.client_b.get(
            reverse("scores:exam_detail", args=[self.exam_a.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_backup_list_and_download_is_isolated(self):
        response = self.client_b.get(reverse("backups:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "a.zip")
        # 下载 A 的备份 → 404
        response = self.client_b.get(
            reverse("backups:download", args=[self.backup_a.pk]),
        )
        self.assertEqual(response.status_code, 404)

    def test_subject_delete_is_isolated(self):
        response = self.client_b.post(
            reverse("scores:subject_delete", args=[self.subject_a.pk]),
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Subject.objects.filter(pk=self.subject_a.pk).exists())

    def test_subject_settings_only_shows_own_and_system(self):
        """B 的科目设置页不应列出 A 创建的科目"""
        Subject.objects.create(name="数学", created_by=self.user_b)
        response = self.client_b.get(reverse("scores:subject_settings"))
        self.assertEqual(response.status_code, 200)
        # A 的语文科目（created_by=A）不应出现在 B 的列表
        body = response.content.decode("utf-8")
        self.assertIn("数学", body)
