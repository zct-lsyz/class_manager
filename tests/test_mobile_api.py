import json
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.classes.models import Course, CourseScheduleEntry, SchoolClass, Semester
from apps.discipline.models import ConfigurableItem, DormDisciplineRecord
from apps.dormitory.models import DormAssignment, DormBed, DormBuilding, DormHygieneCheck, DormHygieneItem, DormHygieneItemScore, DormHygienePhoto, DormRoom
from apps.homework.models import HomeworkPointRule, Subject
from apps.mobile_api.models import MobileNotificationDelivery, MobilePushDevice
from apps.mobile_api.push import dispatch_due_todos
from apps.rewards.models import PointRecord
from apps.scores.ai_models import AIAnalysisConfig, AIExamAnalysisSource, AIQuestionWeakness
from apps.scores.models import Exam, ExamSubject, ExternalClass, Score
from apps.students.models import Student
from apps.seating.models import ClassroomLayout, SeatAssignment, SeatPlan
from apps.todos.models import TodoItem


class MobileApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("teacher", password="safe-password")
        self.school_class = SchoolClass.objects.create(
            created_by=self.user, name="测试一班", is_current=True,
            head_teacher="王老师", school_name="测试中学",
        )
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
        response = self.client.get(reverse("mobile_api:dashboard"), **self.auth)
        self.assertEqual(response.json()["data"]["class"]["head_teacher"], "王老师")
        self.assertEqual(response.json()["data"]["class"]["school_name"], "测试中学")

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
            "points_deducted": 1, "needs_follow_up": False,
        })
        self.assertEqual(response.status_code, 201, response.content)
        record = AttendanceRecord.objects.get(student=self.student)
        point = PointRecord.objects.get(source_type="attendance", source_id=record.pk)
        self.assertEqual(record.points_deducted, -1)
        self.assertEqual(point.points, -1)

    def test_mobile_forms_match_website_sign_and_guardian_choices(self):
        response = self.client.get(reverse("mobile_api:schemas"), **self.auth)
        schemas = {item["key"]: item for item in response.json()["data"]}
        attendance = {item["name"]: item for item in schemas["attendance"]["fields"]}
        self.assertNotIn("points_sign", attendance)
        self.assertEqual(attendance["points_deducted"]["label"], "扣分")
        self.assertEqual(attendance["points_deducted"]["min"], 0)
        self.assertNotIn("normal", [item["value"] for item in attendance["status"]["choices"]])
        guardian = {item["name"]: item for item in schemas["guardians"]["fields"]}
        self.assertEqual([item["label"] for item in guardian["primary_contact"]["choices"]], ["父亲", "母亲", "其他监护人"])

    def test_discipline_schema_exposes_item_defaults_and_room_students(self):
        item = ConfigurableItem.objects.create(
            school_class=self.school_class, name="夜间喧哗", module="dorm_discipline",
            default_severity="serious", default_points=3,
        )
        classroom_item = ConfigurableItem.objects.create(
            school_class=self.school_class, name="课堂讲话", module="classroom_discipline",
            default_severity="mild", default_points=1,
        )
        building = DormBuilding.objects.create(school_class=self.school_class, name="一号楼")
        room = DormRoom.objects.create(building=building, room_number="101")
        bed = DormBed.objects.create(room=room, bed_number="01")
        DormAssignment.objects.create(student=self.student, room=room, bed=bed, semester=self.semester)
        response = self.client.get(reverse("mobile_api:schemas"), **self.auth)
        schemas = {row["key"]: row for row in response.json()["data"]}
        fields = {row["name"]: row for row in schemas["dorm_discipline"]["fields"]}
        option = next(row for row in fields["item"]["options"] if row["value"] == item.pk)
        self.assertEqual((option["severity"], option["points_deducted"], option["points_sign"]), ("serious", 3, "deduct"))
        self.assertTrue(fields["item"]["required"])
        classroom_fields = {row["name"]: row for row in schemas["classroom_discipline"]["fields"]}
        classroom_option = next(row for row in classroom_fields["item"]["options"] if row["value"] == classroom_item.pk)
        self.assertEqual((classroom_option["severity"], classroom_option["points_deducted"]), ("mild", 1))
        student = fields["student"]["options"][0]
        self.assertEqual((student["label"], student["room_id"], student["bed_number"]), (f"{self.student.name}（01号床）", room.pk, "01"))

    def test_hygiene_batch_scores_and_rejects_cross_room_students(self):
        building = DormBuilding.objects.create(school_class=self.school_class, name="一号楼")
        room = DormRoom.objects.create(building=building, room_number="101")
        other_room = DormRoom.objects.create(building=building, room_number="102")
        bed = DormBed.objects.create(room=room, bed_number="01")
        other_bed = DormBed.objects.create(room=other_room, bed_number="02")
        other_student = Student.objects.create(
            school_class=self.school_class, student_id="T002", name="另一学生", gender="female",
        )
        DormAssignment.objects.create(student=self.student, room=room, bed=bed, semester=self.semester)
        DormAssignment.objects.create(student=other_student, room=other_room, bed=other_bed, semester=self.semester)
        item = DormHygieneItem.objects.create(
            school_class=self.school_class, name="地面", full_score=10, default_deduction=1, default_severity="serious",
        )
        response = self.client.get(reverse("mobile_api:schemas"), **self.auth)
        hygiene = next(row for row in response.json()["data"] if row["key"] == "hygiene_checks")
        student_field = next(row for row in hygiene["fields"] if row["name"] == "student")
        room_options = [row for row in student_field["options"] if row["room_id"] == room.pk]
        self.assertEqual([row["label"] for row in room_options], ["所有学生", f"{self.student.name}（01号床）"])
        self.assertEqual(hygiene["hygiene_items"][0]["default_score"], 9)
        self.assertEqual((hygiene["hygiene_items"][0]["severity"], hygiene["hygiene_items"][0]["points_deducted"]), ("serious", 1))
        url = reverse("mobile_api:batch_create", args=["hygiene_checks"])
        invalid = self.request_json("post", url, {
            "room": room.pk, "date": "2026-08-04", "student_mode": "selected",
            "student_ids": [other_student.pk], "scores": [{"item_id": item.pk, "score": 8}],
        })
        self.assertEqual(invalid.status_code, 400)
        response = self.request_json("post", url, {
            "room": room.pk, "date": "2026-08-04", "student_mode": "all",
            "student_ids": [], "severity": "非常严重", "scores": [{"item_id": item.pk, "score": 8}],
        })
        self.assertEqual(response.status_code, 201, response.content)
        check = DormHygieneCheck.objects.get(room=room)
        self.assertEqual((check.total_score, check.grade), (8, "good"))
        self.assertEqual(DormHygieneItemScore.objects.get(check_record=check).score, 8)
        discipline = DormDisciplineRecord.objects.get(student=self.student, dorm_room=room)
        self.assertEqual(discipline.points_deducted, 2)
        self.assertEqual((discipline.custom_content, discipline.severity), ("地面", "critical"))
        self.assertEqual(PointRecord.objects.get(source_type="dorm_discipline", source_id=discipline.pk).points, -2)

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

    def test_seating_view_includes_only_needed_student_display_metadata(self):
        layout = ClassroomLayout.objects.create(school_class=self.school_class, name="标准教室", rows=1, cols=1)
        plan = SeatPlan.objects.create(school_class=self.school_class, layout=layout, version=1, is_active=True)
        SeatAssignment.objects.create(seat_plan=plan, student=self.student, row=0, col=0)
        response = self.client.get(reverse("mobile_api:seating"), **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        seat = response.json()["data"]["assignments"][0]
        self.assertEqual(seat["student_name"], self.student.name)
        self.assertEqual(seat["student_gender"], "male")

    def test_relation_options_hide_student_number_and_ranking_accepts_sources(self):
        Student.objects.create(school_class=self.school_class, student_id="Z999", name="A同学", gender="male")
        Student.objects.create(school_class=self.school_class, student_id="A000", name="B同学", gender="female")
        roster = self.client.get(reverse("mobile_api:resource_list", args=["students"]), **self.auth)
        self.assertEqual([row["name"] for row in roster.json()["data"]["results"][:2]], ["A同学", "B同学"])
        response = self.client.get(reverse("mobile_api:resource_list", args=["todos"]), **self.auth)
        student_field = next(item for item in response.json()["data"]["schema"]["fields"] if item["name"] == "student")
        self.assertEqual([row["label"] for row in student_field["options"][:2]], ["A同学", "B同学"])
        todo = TodoItem.objects.create(created_by=self.user, student=self.student, title="不显示学号")
        response = self.client.get(reverse("mobile_api:resource_list", args=["todos"]), **self.auth)
        self.assertEqual(next(row for row in response.json()["data"]["results"] if row["id"] == todo.pk)["student_label"], self.student.name)
        response = self.client.get(reverse("mobile_api:ranking") + "?sources=attendance,homework", **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["selected_sources"], ["attendance", "homework"])
        response = self.request_json("post", reverse("mobile_api:ranking"), {"sources": ["attendance"]})
        self.assertEqual(response.json()["data"]["selected_sources"], ["attendance"])
        response = self.request_json("post", reverse("mobile_api:ranking"), {"sources": []})
        self.assertEqual(response.json()["data"]["selected_sources"], [])
        PointRecord.objects.create(school_class=self.school_class, student=self.student, date="2026-08-01", points=2, reason="范围外", source_type="reward")
        PointRecord.objects.create(school_class=self.school_class, student=self.student, date="2026-08-05", points=5, reason="范围内", source_type="reward")
        response = self.client.get(reverse("mobile_api:ranking") + "?sources=reward&date_from=2026-08-04&date_to=2026-08-06", **self.auth)
        self.assertEqual(next(row for row in response.json()["data"]["ranking"] if row["student_id"] == self.student.pk)["total"], 5)
        self.assertEqual((response.json()["data"]["date_from"], response.json()["data"]["date_to"]), ("2026-08-04", "2026-08-06"))
        response = self.client.get(reverse("mobile_api:resource_list", args=["point_records"]) + f"?student={self.student.pk}&sources=reward&date_from=2026-08-04&date_to=2026-08-06", **self.auth)
        self.assertEqual([row["reason"] for row in response.json()["data"]["results"]], ["范围内"])

    def test_unauthenticated_resource_request_is_rejected(self):
        response = self.client.get(reverse("mobile_api:resource_list", args=["students"]))
        self.assertEqual(response.status_code, 401)

    def test_system_subject_is_read_only_but_user_subject_is_editable(self):
        system_subject = Subject.objects.create(name="系统科目")
        response = self.request_json("patch", reverse("mobile_api:resource_detail", args=["subjects", system_subject.pk]), {"name": "非法修改"})
        self.assertEqual(response.status_code, 403)
        response = self.request_json("post", reverse("mobile_api:resource_list", args=["subjects"]), {"name": "自定义科目", "is_active": True, "sort_order": 1})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Subject.objects.get(pk=response.json()["data"]["id"]).created_by, self.user)

    def test_external_score_resources_and_ai_config_are_scoped(self):
        response = self.request_json("post", reverse("mobile_api:resource_list", args=["external_classes"]), {"name": "对比班", "school_name": "测试学校"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(ExternalClass.objects.filter(pk=response.json()["data"]["id"], school_class=self.school_class).exists())
        response = self.client.get(reverse("mobile_api:ai_analysis"), **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["data"]["config"]["has_api_key"])

    def test_attendance_statistics(self):
        AttendanceRecord.objects.create(school_class=self.school_class, semester=self.semester, student=self.student, date="2026-08-04", status="late", points_deducted=-1)
        response = self.client.get(reverse("mobile_api:attendance_stats"), **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)

    def test_due_todo_push_is_delivered_once(self):
        todo = TodoItem.objects.create(created_by=self.user, title="到期提醒", deadline=timezone.now() - timezone.timedelta(minutes=1))
        MobilePushDevice.objects.create(user=self.user, device_id="phone", provider="xiaomi", registration_id="reg-id")
        with patch.dict(os.environ, {"XIAOMI_PUSH_APP_SECRET": "secret"}), patch("apps.mobile_api.push.send_xiaomi", return_value={"result": "ok", "code": 0}) as sender:
            self.assertEqual(dispatch_due_todos()["sent"], 1)
            self.assertEqual(dispatch_due_todos()["sent"], 0)
        self.assertEqual(sender.call_count, 1)
        self.assertEqual(MobileNotificationDelivery.objects.filter(todo=todo, status="sent").count(), 1)

    def test_logout_disables_push_for_current_device(self):
        device = MobilePushDevice.objects.create(user=self.user, device_id="test-device", provider="xiaomi", registration_id="reg-id")
        response = self.request_json("post", reverse("mobile_api:logout"), {})
        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertFalse(device.is_active)

    def test_student_comprehensive_profile_is_scoped(self):
        response = self.client.get(
            reverse("mobile_api:student_profile") + f"?student_id={self.student.pk}", **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["student"]["name"], "测试学生")
        self.assertIn("growth_events", response.json()["data"])

    def test_mobile_score_reports_group_exam_and_expose_subject_ranks(self):
        chinese = Subject.objects.create(name="语文")
        math = Subject.objects.create(name="数学")
        exam = Exam.objects.create(
            school_class=self.school_class, semester=self.semester,
            name="期中考试", date="2026-08-01",
        )
        chinese_exam = ExamSubject.objects.create(exam=exam, subject=chinese, full_score=100, sort_order=1)
        math_exam = ExamSubject.objects.create(exam=exam, subject=math, full_score=100, sort_order=2)
        Score.objects.create(
            exam=exam, exam_subject=chinese_exam, student=self.student,
            score=80, rank=1, grade_rank=3, city_rank=20,
        )
        Score.objects.create(
            exam=exam, exam_subject=math_exam, student=self.student,
            score=90, rank=1, grade_rank=2, city_rank=15,
        )
        response = self.client.get(
            reverse("mobile_api:student_profile") + f"?student_id={self.student.pk}", **self.auth,
        )
        latest = response.json()["data"]["latest_exams"]
        self.assertEqual(len(latest), 1)
        self.assertEqual((latest[0]["total_score"], latest[0]["class_rank"]), (170.0, 1))
        self.assertEqual([row["subject"] for row in latest[0]["subjects"]], ["语文", "数学"])
        response = self.client.get(
            reverse("mobile_api:score_analysis") + f"?exam_id={exam.pk}", **self.auth,
        )
        details = response.json()["data"]["students"][0]["subject_details"]
        self.assertEqual(details[0]["class_rank"], 1)
        self.assertEqual(details[0]["grade_rank"], 3)
        response = self.client.get(
            reverse("mobile_api:selected_student_score_analysis") + f"?student_id={self.student.pk}", **self.auth,
        )
        self.assertEqual(len(response.json()["data"]["history"][0]["subjects"]), 2)

    def test_homework_point_rule_choices_and_create(self):
        response = self.client.get(reverse("mobile_api:schemas"), **self.auth)
        schema = next(item for item in response.json()["data"] if item["key"] == "homework_point_rules")
        status = next(item for item in schema["fields"] if item["name"] == "status")
        self.assertIn("submitted", [item["value"] for item in status["choices"]])
        response = self.request_json("post", reverse("mobile_api:resource_list", args=["homework_point_rules"]), {
            "status": "submitted", "points": 2, "is_add": True,
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(HomeworkPointRule.objects.filter(school_class=self.school_class, points=2).exists())

    def test_hygiene_photo_upload(self):
        building = DormBuilding.objects.create(school_class=self.school_class, name="一号楼")
        room = DormRoom.objects.create(building=building, room_number="101")
        check = DormHygieneCheck.objects.create(school_class=self.school_class, room=room, date="2026-08-04")
        image = SimpleUploadedFile(
            "room.gif", b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;",
            content_type="image/gif",
        )
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            response = self.client.post(
                reverse("mobile_api:resource_list", args=["hygiene_photos"]),
                data={"check_record": check.pk, "image": image}, **self.auth,
            )
            self.assertEqual(response.status_code, 201, response.content)
            photo = DormHygienePhoto.objects.get(check_record=check)
            self.assertEqual(photo.original_name, "room.gif")
            self.assertGreater(photo.stored_size, 0)

    def test_exam_paper_analysis_configuration(self):
        response = self.client.get(reverse("mobile_api:exam_paper_analysis"), **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["data"]["ai_ready"])
        self.assertIn("数学", response.json()["data"]["subjects"])

    def test_exam_paper_analysis_upload_and_result(self):
        AIAnalysisConfig.objects.create(school_class=self.school_class, is_enabled=True)
        paper = SimpleUploadedFile("paper.txt", b"test paper content", content_type="text/plain")
        scores = SimpleUploadedFile(
            "scores.xlsx", b"test score sheet", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        summary = [{
            "question_label": "1", "question_type": "选择题", "knowledge_points": ["函数"],
            "full_score": 5, "average_score": 2.5, "score_rate": .5,
            "zero_rate": .1, "full_rate": .2, "sort_order": 1,
        }]
        result = {"overall_summary": "函数题较薄弱", "questions": [{
            "question_label": "1", "knowledge_points": ["函数"],
            "analysis": "基础不牢", "recommendation": "加强练习",
        }]}
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root), \
                patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}), \
                patch("apps.scores.exam_analysis_services.extract_paper_text", return_value="试卷解析文本"), \
                patch("apps.scores.exam_analysis_services.parse_score_sheet", return_value=(summary, [])), \
                patch("apps.scores.exam_analysis_services.generate_exam_analysis", return_value=(result, 120)):
            response = self.client.post(
                reverse("mobile_api:exam_paper_analysis"),
                data={
                    "subject_name": "数学", "privacy_confirm": "true",
                    "paper_file": paper, "score_file": scores,
                }, **self.auth,
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.json()["data"]["overall_summary"], "函数题较薄弱")
            self.assertTrue(AIExamAnalysisSource.objects.filter(status="completed").exists())
            self.assertTrue(AIQuestionWeakness.objects.filter(weakness_level="high").exists())
