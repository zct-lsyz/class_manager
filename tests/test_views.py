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
        self.school_class = SchoolClass.objects.create(name="高一(1)班", is_current=True)
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
            reverse("scores:score_entry") + f"?exam_id={self.exam_subject.exam_id}&subject_id={self.exam_subject.pk}",
            reverse("scores:exam_analysis"),
            reverse("exports:export_center"),
            reverse("exports:full_export"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
