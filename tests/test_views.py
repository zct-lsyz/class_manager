"""关键页面渲染冒烟测试。"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.classes.subjects import Subject
from apps.scores.models import Exam, ExamSubject
from apps.students.models import Student


class CorePageSmokeTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("teacher", password="strong-test-password")
        self.client.force_login(self.user)
        self.school_class = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.semester = Semester.objects.create(
            school_class=self.school_class,
            academic_year="2026-2027",
            semester_type="first",
            is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.school_class, student_id="2026001", name="张三", gender="male",
        )
        subject = Subject.objects.create(name="数学")
        exam = Exam.objects.create(
            school_class=self.school_class, semester=self.semester,
            name="月考", date="2026-09-01",
        )
        self.exam_subject = ExamSubject.objects.create(
            exam=exam, subject=subject, full_score=100,
        )

    def test_key_pages_render(self):
        urls = [
            reverse("students:detail", args=[self.student.pk]),
            reverse("scores:exam_list"),
            reverse("scores:score_entry") + f"?exam_id={self.exam_subject.exam_id}&subject_id={self.exam_subject.pk}",
            reverse("scores:analysis"),
            reverse("scores:ai_settings"),
            reverse("scores:exam_analysis"),
            reverse("activities:activities"),
            reverse("exports:export_center"),
            reverse("exports:full_export"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)


class ExamCreateGuardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("exam-guard", password="strong-test-password")
        self.client.force_login(self.user)

    def test_exam_create_requires_current_class(self):
        response = self.client.get(reverse("scores:exam_create"))
        self.assertRedirects(response, reverse("classes:settings"))

    def test_exam_create_requires_current_semester_for_current_class(self):
        SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        response = self.client.post(reverse("scores:exam_create"), {
            "name": "月考", "exam_type": "regular", "date": "2026-09-01",
        })
        self.assertRedirects(response, reverse("classes:settings"))
        self.assertFalse(Exam.objects.exists())


class CurrentClassGuardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("class-guard", password="strong-test-password")
        self.client.force_login(self.user)

    def test_class_bound_create_pages_require_current_class(self):
        urls = [
            reverse("attendance:create"),
            reverse("activities:activity_create"),
            reverse("comments:create"),
            reverse("communications:conversation_create"),
            reverse("classes:committee_role_create"),
            reverse("discipline:classroom_create"),
            reverse("dormitory:building_create"),
            reverse("duty:group_create"),
            reverse("homework:task_create"),
            reverse("rewards:reward_create"),
            reverse("dashboard:warnings"),
            reverse("exports:import_data"),
            reverse("exports:option_import", args=["attendance_reason"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, reverse("classes:settings"))
