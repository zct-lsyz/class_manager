from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.classes.models import CommitteeRole, SchoolClass, Semester
from apps.seating.forms import ClassroomLayoutForm
from apps.seating.models import ClassroomLayout, SeatAssignment, SeatPlan
from apps.seating.services import (
    arrange_students, attach_student_seat_metadata, rotate_plan,
)
from apps.students.models import Student


class SeatingFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("seat-manager", password="test-password")
        self.client.force_login(self.user)
        self.school_class = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.semester = Semester.objects.create(
            school_class=self.school_class, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.layout = ClassroomLayout.objects.create(
            school_class=self.school_class, rows=2, cols=4,
            aisle_count=1, aisle_positions=[2], podium_position="back", is_current=True,
        )
        self.plan = SeatPlan.objects.create(
            school_class=self.school_class, semester=self.semester,
            layout=self.layout, is_active=True,
        )
        self.students = [
            Student.objects.create(school_class=self.school_class, student_id="2026010100000000001", name="男生甲", gender="male", height=180, dormitory="101"),
            Student.objects.create(school_class=self.school_class, student_id="2026010100000000002", name="男生乙", gender="male", height=170, dormitory="102"),
            Student.objects.create(school_class=self.school_class, student_id="2026010100000000003", name="女生甲", gender="female", height=160, dormitory="201", seat_requirement="需安排前排"),
            Student.objects.create(school_class=self.school_class, student_id="2026010100000000004", name="女生乙", gender="female", height=165, dormitory="202"),
        ]

    def test_layout_uses_dynamic_aisle_positions(self):
        response = self.client.post(reverse("seating:layout"), {
            "name": "默认布局", "rows": 3, "cols": 5, "seats_per_desk": 1,
            "aisle_count": 2, "aisle_positions": ["1", "4"], "is_current": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.aisle_positions, [1, 4])
        self.assertEqual(self.layout.podium_position, "back")

    def test_layout_rejects_too_many_aisles(self):
        form = ClassroomLayoutForm(data={
            "name": "错误布局", "rows": 2, "cols": 2, "seats_per_desk": 1,
            "aisle_count": 2, "aisle_positions": ["1"], "is_current": "on",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("aisle_count", form.errors)

    def test_seat_page_teacher_view_and_student_blocks(self):
        SeatAssignment.objects.create(
            seat_plan=self.plan, student=self.students[0], row=0, col=0,
        )
        response = self.client.get(reverse("seating:index"))
        content = response.content.decode()
        self.assertLess(content.index('data-row="1"'), content.index('data-row="0"'))
        self.assertContains(response, "seat-aisle")
        self.assertContains(response, "student-male")
        self.assertContains(response, "student-female")
        self.assertContains(response, "special-star")
        self.assertContains(response, "101 · 180cm")

    def test_code_arrangement_keeps_same_gender_deskmates_and_special_front(self):
        attach_student_seat_metadata(self.students, self.school_class)
        arranged = arrange_students(
            self.layout, self.students,
            ["height", "gender", "score", "dormitory", "special"],
        )
        positions = {student.pk: position for position, student in arranged.items()}
        self.assertEqual(positions[self.students[2].pk][0], 0)
        for row in range(self.layout.rows):
            for first_col in (0, 2):
                first = arranged.get((row, first_col))
                second = arranged.get((row, first_col + 1))
                if first and second:
                    self.assertEqual(first.gender, second.gender)

    def test_auto_arrange_saves_priorities_and_rotation(self):
        response = self.client.post(reverse("seating:auto_arrange"), {
            "priority_1": "special", "priority_2": "height",
            "priority_3": "gender", "priority_4": "score",
            "priority_5": "dormitory", "rotation_interval_months": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.arrangement_priorities[0], "special")
        self.assertEqual(self.plan.rotation_interval_months, 1)
        self.assertEqual(SeatAssignment.objects.filter(seat_plan=self.plan).count(), 4)

    def test_rotation_moves_each_student_two_columns(self):
        for col, student in enumerate(self.students):
            SeatAssignment.objects.create(
                seat_plan=self.plan, student=student, row=0, col=col,
            )
        before = dict(SeatAssignment.objects.filter(seat_plan=self.plan).values_list("student_id", "col"))
        rotate_plan(self.plan)
        after = dict(SeatAssignment.objects.filter(seat_plan=self.plan).values_list("student_id", "col"))
        for student_id, col in before.items():
            self.assertEqual(after[student_id], (col + 2) % 4)

    def test_print_view_only_uses_student_names_in_seats(self):
        SeatAssignment.objects.create(
            seat_plan=self.plan, student=self.students[0], row=0, col=0,
        )
        response = self.client.get(reverse("seating:print"))
        self.assertContains(response, "男生甲")
        self.assertNotContains(response, "180cm")
        self.assertNotContains(response, "2026010100000000001")

    def test_committee_can_assign_unclassified_roster_student(self):
        student = Student.objects.create(
            student_id="2026010100000000005", name="未分班学生", gender="male",
        )
        role = CommitteeRole.objects.create(
            school_class=self.school_class, name="班长", is_active=True,
        )
        self.assertContains(self.client.get(reverse("classes:committee_list")), "未分班学生")
        response = self.client.post(reverse("classes:committee_member_create"), {
            "role": role.pk, "student": student.pk,
        })
        self.assertEqual(response.status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.school_class, self.school_class)
