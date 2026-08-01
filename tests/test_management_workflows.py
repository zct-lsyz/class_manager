from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.classes.models import CoursePeriod, CourseScheduleEntry, SchoolClass, Semester
from apps.classes.subjects import Subject
from apps.duty.models import DutyGroup, DutyMemberTask, DutyTask
from apps.homework.models import HomeworkRecord, HomeworkTask
from apps.rewards.models import PointRecord, RewardRecord
from apps.seating.models import ClassroomLayout, SeatPlan
from apps.students.models import Student


class ManagementWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("manager", password="test-password")
        self.client.force_login(self.user)
        self.school_class = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.semester = Semester.objects.create(
            school_class=self.school_class, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.school_class, student_id="S001", name="张三", gender="male",
        )
        self.student2 = Student.objects.create(
            school_class=self.school_class, student_id="S002", name="李四", gender="female",
        )
        self.student2.seat_requirement = "需安排前排座位"
        self.student2.save(update_fields=["seat_requirement"])
        self.subject = Subject.objects.create(name="数学")
        self.layout = ClassroomLayout.objects.create(
            school_class=self.school_class, rows=2, cols=2,
        )
        self.plan = SeatPlan.objects.create(
            school_class=self.school_class, semester=self.semester,
            layout=self.layout, is_active=True,
        )
        self.duty_task = DutyTask.objects.create(
            school_class=self.school_class, name="擦黑板",
        )
        self.group = DutyGroup.objects.create(
            school_class=self.school_class, semester=self.semester, name="第一组",
        )
        self.group.members.add(self.student)
        self.group.tasks.add(self.duty_task)
        self.homework = HomeworkTask.objects.create(
            school_class=self.school_class, semester=self.semester,
            subject=self.subject, title="练习一", assigned_date="2026-07-31",
        )
        self.reward = RewardRecord.objects.create(
            school_class=self.school_class, semester=self.semester,
            student=self.student, date="2026-07-31", custom_name="表现良好", points=1,
        )

    def test_changed_pages_render(self):
        urls = [
            reverse("classes:settings"), reverse("classes:course_schedule"),
            reverse("seating:index"), reverse("duty:group_detail", args=[self.group.pk]),
            reverse("duty:group_edit", args=[self.group.pk]), reverse("attendance:index"),
            reverse("attendance:create"), reverse("homework:task_detail", args=[self.homework.pk]),
            reverse("rewards:reward_edit", args=[self.reward.pk]), reverse("rewards:points"),
            reverse("dashboard:warnings"), reverse("backups:storage_center"),
            reverse("students:history_browser", args=["rewards"]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
        self.assertContains(self.client.get(reverse("seating:index")), 'draggable="true"')
        self.assertContains(self.client.get(reverse("seating:index")), "特殊座位要求：需安排前排座位")
        self.assertContains(self.client.get(reverse("seating:index")), "special-star")
        self.assertContains(self.client.get(reverse("seating:index")), "student-female")

    def test_student_roster_accepts_contacts_and_bed(self):
        response = self.client.post(reverse("students:create"), {
            "school_class": self.school_class.pk, "student_id": "2026010100000000003",
            "name": "王五", "gender": "male", "dormitory": "2号楼301",
            "bed_number": "3", "primary_contact": "王先生",
            "primary_phone": "13800138000", "secondary_contact": "王女士",
            "secondary_phone": "13900139000", "sort_order": 0,
        })
        self.assertEqual(response.status_code, 302)
        student = Student.objects.get(student_id="2026010100000000003")
        self.assertEqual(student.bed_number, "3")
        self.assertEqual(student.secondary_contact, "王女士")

    def test_course_period_and_schedule_save(self):
        response = self.client.post(reverse("classes:course_schedule"), {
            "action": "save_schedule", "period_count": "2",
            "start_time_1": "08:00", "end_time_1": "08:45",
            "start_time_2": "08:55", "end_time_2": "09:40",
            "cell_1_1": "数学", "teacher_1_1": "陈老师",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(CoursePeriod.objects.filter(school_class=self.school_class).count(), 2)
        entry = CourseScheduleEntry.objects.get(school_class=self.school_class)
        self.assertEqual((entry.subject, entry.teacher), ("数学", "陈老师"))

    def test_duty_member_task_assignment(self):
        response = self.client.post(reverse("duty:group_edit", args=[self.group.pk]), {
            "name": self.group.name, "leader": self.student.pk,
            "members": [self.student.pk], "tasks": [self.duty_task.pk],
            "week": 1, "is_active": "on", f"task_{self.student.pk}": self.duty_task.pk,
        })
        self.assertEqual(response.status_code, 302)
        assignment = DutyMemberTask.objects.get(group=self.group, student=self.student)
        self.assertEqual(assignment.task, self.duty_task)

    def test_duty_record_redirects_to_list(self):
        response = self.client.post(reverse("duty:group_detail", args=[self.group.pk]), {
            "date": "2026-07-31", f"member_{self.student.pk}": "completed",
        })
        self.assertRedirects(response, reverse("duty:index"))

    def test_homework_batch_marks_poor(self):
        response = self.client.post(reverse("homework:task_detail", args=[self.homework.pk]), {
            "batch_students": [self.student.pk, self.student2.pk], "batch_status": "poor",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            HomeworkRecord.objects.filter(task=self.homework, status="poor").count(), 2,
        )

    def test_penalty_creates_negative_point_record(self):
        response = self.client.post(reverse("rewards:reward_create"), {
            "student": self.student.pk, "date": "2026-07-31",
            "record_type": "penalty", "custom_name": "迟到违纪",
            "level": "class", "points": 3, "description": "一次迟到",
        })
        self.assertEqual(response.status_code, 302)
        record = RewardRecord.objects.get(custom_name="迟到违纪")
        self.assertEqual(record.points, -3)
        self.assertEqual(
            PointRecord.objects.get(source_type="reward", source_id=record.pk).points, -3,
        )

    def test_batch_penalty_creates_records_for_selected_students(self):
        response = self.client.post(reverse("rewards:reward_create"), {
            "students": [self.student.pk, self.student2.pk], "date": "2026-07-31",
            "record_type": "penalty", "custom_name": "集体迟到",
            "level": "class", "points": 2, "description": "批量登记",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RewardRecord.objects.filter(custom_name="集体迟到", points=-2).count(), 2)
