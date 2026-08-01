"""
成绩计算相关测试
"""
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from apps.classes.models import SchoolClass, Semester
from apps.homework.models import Subject
from apps.students.models import Student
from apps.scores.models import Exam, ExamSubject, Score


class ScoreCalculationTests(TestCase):
    """成绩计算测试"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username="test-score", password="pass")
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True
        )
        self.subject = Subject.objects.create(name="数学")
        self.exam = Exam.objects.create(
            school_class=self.cls, semester=self.sem,
            name="月考一", date="2026-09-10",
        )
        self.exam_subject = ExamSubject.objects.create(
            exam=self.exam, subject=self.subject, full_score=100,
        )
        self.students = []
        for i in range(3):
            s = Student.objects.create(
                school_class=self.cls, student_id=f"2026{i+1:03d}",
                name=f"学生{i+1}", gender="male",
            )
            self.students.append(s)

    def test_absent_not_counted_as_zero(self):
        """缺考学生不应按 0 分参与平均分计算"""
        Score.objects.create(
            exam=self.exam, exam_subject=self.exam_subject,
            student=self.students[0], score=80, status="normal",
        )
        Score.objects.create(
            exam=self.exam, exam_subject=self.exam_subject,
            student=self.students[1], score=90, status="normal",
        )
        Score.objects.create(
            exam=self.exam, exam_subject=self.exam_subject,
            student=self.students[2], score=None, status="absent",
        )

        from django.db.models import Avg
        avg = Score.objects.filter(
            exam_subject=self.exam_subject, status="normal"
        ).aggregate(avg=Avg("score"))["avg"]

        self.assertEqual(avg, 85.0)

    def test_score_cannot_exceed_full(self):
        """成绩不得超过科目满分"""
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            Score.objects.create(
                exam=self.exam, exam_subject=self.exam_subject,
                student=self.students[0], score=150, status="normal",
            )


class PointCalculationTests(TestCase):
    """积分计算测试"""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username="test-point", password="pass")
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.student = Student.objects.create(
            school_class=self.cls, student_id="2026001",
            name="测试学生", gender="female",
        )

    def test_points_summary(self):
        """积分汇总正确"""
        from apps.rewards.models import PointRecord
        from django.utils import timezone
        today = timezone.localdate()
        PointRecord.objects.create(
            student=self.student, school_class=self.cls, date=today,
            points=3, reason="成绩进步", source_type="reward",
        )
        PointRecord.objects.create(
            student=self.student, school_class=self.cls, date=today,
            points=-2, reason="玩手机", source_type="classroom_discipline",
        )
        PointRecord.objects.create(
            student=self.student, school_class=self.cls, date=today,
            points=1, reason="卫生优秀", source_type="reward",
        )

        from django.db.models import Sum
        total = PointRecord.objects.filter(student=self.student).aggregate(Sum("points"))["points__sum"]
        self.assertEqual(total, 2)


class WideScoreImportTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="score-importer", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(3)班", is_current=True)
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True,
        )
        self.exam = Exam.objects.create(
            school_class=self.cls, semester=self.sem, name="期末考试", date="2026-07-12",
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="2026000000000000001", name="李四", gender="male",
        )

    def test_reference_wide_sheet_prefers_assigned_score_and_matches_name(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["姓名", "总分赋分", "语文", "政治原始", "政治赋分"])
        sheet.append(["李四", 180, 91.5, 33, 53])
        output = io.BytesIO()
        workbook.save(output)
        uploaded = SimpleUploadedFile(
            "scores.xlsx", output.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(reverse("scores:score_import_wide"), {
            "exam_id": self.exam.pk, "file": uploaded,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Score.objects.filter(exam=self.exam, student=self.student).count(), 2)
        self.assertEqual(float(Score.objects.get(exam=self.exam, student=self.student, exam_subject__subject__name="政治").score), 53)

    def test_student_analysis_detail_shows_history(self):
        subject = Subject.objects.create(name="数学")
        exam_subject = ExamSubject.objects.create(exam=self.exam, subject=subject, full_score=150)
        Score.objects.create(
            exam=self.exam, exam_subject=exam_subject, student=self.student, score=120, status="normal",
        )

        response = self.client.get(reverse("scores:student_analysis_detail", args=[self.student.pk]))

        self.assertContains(response, "李四成绩详情")
        self.assertContains(response, "数学")
