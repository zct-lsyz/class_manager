import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.classes.models import Course, CourseScheduleEntry, SchoolClass, Semester
from apps.rewards.models import PointRecord
from apps.students.models import Student
from apps.todos.models import TodoItem


class MobileApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("teacher", password="safe-password")
        self.school_class = SchoolClass.objects.create(created_by=self.user, name="测试一班", is_current=True)
        self.semester = Semester.objects.create(
            school_class=self.school_class, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.school_class, student_id="T001", name="测试学生",
            gender="male",
        )
        response = self.client.post(
            reverse("mobile_api:login"),
            data=json.dumps({
                "username": "teacher", "password": "safe-password",
                "device_id": "test-device", "device_name": "测试设备",
            }), content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.token = response.json()["data"]["token"]
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    def request_json(self, method, url, data=None):
        return getattr(self.client, method)(
            url, data=json.dumps(data or {}), content_type="application/json", **self.auth,
        )

    def test_login_and_profile(self):
        response = self.client.get(reverse("mobile_api:profile"), **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["username"], "teacher")

    def test_todo_crud_and_completion_timestamp(self):
        response = self.request_json("post", reverse("mobile_api:resource_list", args=["todos"]), {
            "title": "检查测试待办", "priority": 1,
            "deadline": (timezone.now() + timezone.timedelta(hours=1)).isoformat(),
            "student": self.student.pk, "is_completed": False,
        })
        self.assertEqual(response.status_code, 201, response.content)
        todo_id = response.json()["data"]["id"]
        response = self.request_json("patch", reverse("mobile_api:resource_detail", args=["todos", todo_id]), {
            "is_completed": True,
        })
        self.assertEqual(response.status_code, 200, response.content)
        todo = TodoItem.objects.get(pk=todo_id)
        self.assertTrue(todo.is_completed)
        self.assertIsNotNone(todo.completed_at)

    def test_resources_are_isolated_by_user(self):
        other = User.objects.create_user("other", password="other-password")
        SchoolClass.objects.create(created_by=other, name="其他账户班级", is_current=True)
        response = self.client.get(reverse("mobile_api:resource_list", args=["classes"]), **self.auth)
        self.assertEqual(response.status_code, 200)
        names = [row["name"] for row in response.json()["data"]["results"]]
        self.assertEqual(names, ["测试一班"])

    def test_batch_attendance_preserves_point_side_effect(self):
        response = self.request_json("post", reverse("mobile_api:batch_create", args=["attendance"]), {
            "student_ids": [self.student.pk], "date": "2026-08-04",
            "period": "full_day", "status": "late", "reason": "测试迟到",
            "points_deducted": -1, "needs_follow_up": False,
        })
        self.assertEqual(response.status_code, 201, response.content)
        record = AttendanceRecord.objects.get(student=self.student)
        point = PointRecord.objects.get(source_type="attendance", source_id=record.pk)
        self.assertEqual(point.points, -1)

    def test_course_schedule_is_read_only_and_scoped(self):
        course = Course.objects.create(school_class=self.school_class, name="数学")
        CourseScheduleEntry.objects.create(
            school_class=self.school_class, semester=self.semester,
            course=course, weekday=1, period=1,
        )
        response = self.client.get(reverse("mobile_api:course_schedule"), **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["entries"][0]["course"], "数学")
        response = self.request_json("post", reverse("mobile_api:course_schedule"), {})
        self.assertEqual(response.status_code, 405)

    def test_unauthenticated_resource_request_is_rejected(self):
        response = self.client.get(reverse("mobile_api:resource_list", args=["students"]))
        self.assertEqual(response.status_code, 401)
