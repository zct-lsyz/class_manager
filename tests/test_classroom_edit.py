"""课堂纪律编辑表单：显示原学生且「选择学生」可用。"""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.discipline.models import ClassroomDisciplineRecord


class ClassroomEditFormTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="cls-edit", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="编辑班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="E0001", name="张三", gender="male",
        )
        self.record = ClassroomDisciplineRecord.objects.create(
            school_class=self.cls, semester=self.sem, student=self.student,
            date=date(2026, 8, 2), description="上课说话",
        )

    def test_edit_shows_existing_student_with_normal_select(self):
        """编辑页应显示原学生，且用可点击的普通下拉而非复选框面板。"""
        resp = self.client.get(reverse("discipline:classroom_edit", args=[self.record.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "张三")
        self.assertNotContains(resp, "scsButton")

    def test_edit_post_updates_student(self):
        """编辑提交后学生可更换。"""
        s2 = Student.objects.create(
            school_class=self.cls, student_id="E0002", name="李四", gender="male",
        )
        resp = self.client.post(reverse("discipline:classroom_edit", args=[self.record.pk]), {
            "student": s2.pk,
            "date": "2026-08-02",
            "severity": "moderate",
            "points_sign": "deduct",
            "points_deducted": "1",
            "description": "上课说话",
        })
        self.assertEqual(resp.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.student_id, s2.pk)
