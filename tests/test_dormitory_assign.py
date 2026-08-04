"""宿舍：录入表单显示床位号 + 导入自动匹配宿舍/床位一致性。"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.dormitory.models import DormBuilding, DormRoom, DormBed, DormAssignment
from apps.dormitory.views import _build_room_students
from apps.exports.import_services import import_students


STUDENT_ID = "2026010100000000001"


class DormitoryFormOptionsTests(TestCase):
    """录入表单的学生选项应显示床位号。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="dorm-opt", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="一班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.building = DormBuilding.objects.create(school_class=self.cls, name="一栋")
        self.room = DormRoom.objects.create(
            building=self.building, room_number="101", bed_count=8,
        )
        for i in range(1, 9):
            DormBed.objects.create(room=self.room, bed_number=f"{i:02d}")

    def test_build_room_students_includes_bed(self):
        """已占床学生选项含床位号。"""
        student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="张三", gender="male",
        )
        DormAssignment.objects.create(
            student=student, room=self.room, bed=DormBed.objects.get(room=self.room, bed_number="01"),
            is_current=True, semester=self.sem,
        )
        data = _build_room_students(self.cls)
        entry = data[self.room.pk][0]
        self.assertEqual(entry["name"], "张三")
        self.assertEqual(entry["bed"], "01")

    def test_build_room_students_bedless_empty(self):
        """已分配但未占床的学生选项床位号为空。"""
        s2 = Student.objects.create(
            school_class=self.cls, student_id="2026010100000000002", name="李四", gender="male",
        )
        DormAssignment.objects.create(
            student=s2, room=self.room, bed=None, is_current=True, semester=self.sem,
        )
        data = _build_room_students(self.cls)
        entry = next(x for x in data[self.room.pk] if x["id"] == s2.pk)
        self.assertEqual(entry["bed"], "")

    def test_hygiene_form_context_has_bed(self):
        """卫生检查录入页的学生选项数据含床位号。"""
        student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="张三", gender="male",
        )
        DormAssignment.objects.create(
            student=student, room=self.room, bed=DormBed.objects.get(room=self.room, bed_number="02"),
            is_current=True, semester=self.sem,
        )
        client = Client()
        client.force_login(self.user)
        resp = client.get(reverse("dormitory:hygiene_create"))
        self.assertEqual(resp.status_code, 200)
        data = resp.context["dorm_room_students"]
        entry = data[self.room.pk][0]
        self.assertEqual(entry["name"], "张三")
        self.assertEqual(entry["bed"], "02")


class DormitoryImportSyncTests(TestCase):
    """导入时自动匹配宿舍与学生床位。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="dorm-imp", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="二班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )

    def _row(self, student_id, name, dormitory="", bed_number=""):
        return {
            "row": 2, "student_id": student_id, "name": name, "gender": "male",
            "birth_date": None, "height": None, "vision": "", "seat_requirement": "",
            "class_position": "", "dormitory": dormitory, "bed_number": bed_number,
            "primary_contact": "", "primary_phone": "", "remarks": "",
        }

    def test_roster_import_creates_assignment_and_normalizes_bed(self):
        """花名册导入：有宿舍/床位时自动生成分配，床位号 3 匹配到生成的 03 号床。"""
        import_students([self._row(STUDENT_ID, "王五", "一栋 101", "3")], self.cls)
        student = Student.objects.get(name="王五")
        assignment = student.dorm_assignments.filter(is_current=True).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.room.room_number, "101")
        self.assertIsNotNone(assignment.bed)
        self.assertEqual(assignment.bed.bed_number, "03")
        self.assertEqual(student.bed_number, "03")

    def test_roster_import_without_dorm_skips(self):
        """无宿舍信息时不应生成分配。"""
        import_students([self._row("2026010100000000002", "赵六")], self.cls)
        student = Student.objects.get(name="赵六")
        self.assertFalse(student.dorm_assignments.exists())

    def test_roster_import_bed_number_beyond_capacity_gets_free_bed(self):
        """床位号超出床位数（如 9，而房间只有 8 床）时自动分配到空闲床。"""
        import_students([self._row(STUDENT_ID, "钱九", "一栋 101", "9")], self.cls)
        student = Student.objects.get(name="钱九")
        assignment = student.dorm_assignments.filter(is_current=True).first()
        self.assertIsNotNone(assignment)
        self.assertIsNotNone(assignment.bed)
        # 9 号床不存在，自动落到第一张空闲床 01
        self.assertEqual(assignment.bed.bed_number, "01")
        self.assertEqual(student.bed_number, "01")

    def test_multiple_imports_fill_distinct_free_beds(self):
        """同宿舍多个学生（床位号都匹配不上时）应各自落到不同的空闲床。"""
        rows = [
            self._row(STUDENT_ID, "钱九", "一栋 101", "9"),
            self._row("2026010100000000002", "孙十", "一栋 101", "9"),
        ]
        import_students(rows, self.cls)
        s1 = Student.objects.get(name="钱九").dorm_assignments.get(is_current=True)
        s2 = Student.objects.get(name="孙十").dorm_assignments.get(is_current=True)
        self.assertIsNotNone(s1.bed)
        self.assertIsNotNone(s2.bed)
        self.assertNotEqual(s1.bed_id, s2.bed_id)

    def test_two_students_same_room_same_bed_no_500(self):
        """同宿舍两个学生填了同一床位号：第二个应落到空闲床，而不是报 500。"""
        rows = [
            self._row(STUDENT_ID, "张三", "一栋 101", "1"),
            self._row("2026010100000000002", "李四", "一栋 101", "1"),
        ]
        import_students(rows, self.cls)
        a = Student.objects.get(name="张三").dorm_assignments.get(is_current=True)
        b = Student.objects.get(name="李四").dorm_assignments.get(is_current=True)
        self.assertIsNotNone(a.bed)
        self.assertIsNotNone(b.bed)
        self.assertNotEqual(a.bed_id, b.bed_id)


class BedReleaseTests(TestCase):
    """历史分配仍引用床位时，重新分配/导入不应撞 bed_id 唯一约束。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="dorm-rel", password="pass")
        self.client = Client()
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="释放班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.building = DormBuilding.objects.create(school_class=self.cls, name="一栋")
        self.room = DormRoom.objects.create(
            building=self.building, room_number="104", bed_count=8,
        )
        for i in range(1, 9):
            DormBed.objects.create(room=self.room, bed_number=f"{i:02d}")
        self.bed01 = DormBed.objects.get(room=self.room, bed_number="01")

    def test_bed_assign_releases_historical_reference(self):
        """某床存在历史(非当前)分配仍引用时，重新分配不报 500。"""
        old_student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="旧生", gender="male",
        )
        DormAssignment.objects.create(
            student=old_student, room=self.room, bed=self.bed01,
            is_current=False, semester=self.sem,
        )
        new_student = Student.objects.create(
            school_class=self.cls, student_id="2026010100000000002", name="新生", gender="male",
        )
        resp = self.client.post(
            reverse("dormitory:bed_assign", args=[self.bed01.pk]),
            {"student_id": new_student.pk},
        )
        self.assertEqual(resp.status_code, 302)
        new = DormAssignment.objects.get(student=new_student, is_current=True)
        self.assertEqual(new.bed_id, self.bed01.pk)

    def test_import_releases_historical_bed_reference(self):
        """导入学生到一张有历史引用的床时不应报 500。"""
        old_student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="旧生", gender="male",
        )
        DormAssignment.objects.create(
            student=old_student, room=self.room, bed=self.bed01,
            is_current=False, semester=self.sem,
        )
        import_students([{
            "row": 2, "student_id": "2026010100000000003", "name": "导入生", "gender": "male",
            "birth_date": None, "height": None, "vision": "", "seat_requirement": "",
            "class_position": "", "dormitory": "一栋 104", "bed_number": "1",
            "primary_contact": "", "primary_phone": "", "remarks": "",
        }], self.cls)
        student = Student.objects.get(name="导入生")
        assignment = student.dorm_assignments.get(is_current=True)
        self.assertEqual(assignment.bed_id, self.bed01.pk)


class AssignDormitoryBedsCommandTests(TestCase):
    """管理命令：把历史「已分配未占床」数据补分到空闲床。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="dorm-cmd", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="四班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.building = DormBuilding.objects.create(school_class=self.cls, name="一栋")
        self.room = DormRoom.objects.create(
            building=self.building, room_number="103", bed_count=8,
        )
        for i in range(1, 9):
            DormBed.objects.create(room=self.room, bed_number=f"{i:02d}")

    def test_command_backfills_bedless(self):
        from io import StringIO
        from django.core.management import call_command

        student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="孙七", gender="male",
        )
        DormAssignment.objects.create(
            student=student, room=self.room, bed=None, is_current=True, semester=self.sem,
        )
        out = StringIO()
        call_command("assign_dormitory_beds", stdout=out)
        self.assertIn("已补分 1", out.getvalue())
        assignment = student.dorm_assignments.get(is_current=True)
        self.assertIsNotNone(assignment.bed)
        self.assertEqual(assignment.bed.bed_number, "01")
        student.refresh_from_db()
        self.assertEqual(student.bed_number, "01")

    def test_command_dry_run_does_not_write(self):
        from io import StringIO
        from django.core.management import call_command

        student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="孙七", gender="male",
        )
        DormAssignment.objects.create(
            student=student, room=self.room, bed=None, is_current=True, semester=self.sem,
        )
        out = StringIO()
        call_command("assign_dormitory_beds", dry_run=True, stdout=out)
        self.assertIn("将补分 1", out.getvalue())
        student.dorm_assignments.get(is_current=True).refresh_from_db()
        self.assertIsNone(student.dorm_assignments.get(is_current=True).bed)


class RoomDetailBedlessTests(TestCase):
    """宿舍详情：已分配未占床的学生要可见、可再分配。"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="dorm-bedless", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="三班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.building = DormBuilding.objects.create(school_class=self.cls, name="一栋")
        self.room = DormRoom.objects.create(
            building=self.building, room_number="102", bed_count=8,
        )
        for i in range(1, 9):
            DormBed.objects.create(room=self.room, bed_number=f"{i:02d}")
        self.student = Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="孙七", gender="male",
        )
        # 已分配宿舍但未占床
        DormAssignment.objects.create(
            student=self.student, room=self.room, bed=None, is_current=True, semester=self.sem,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_room_detail_warns_and_offers_bedless_student(self):
        resp = self.client.get(reverse("dormitory:room_detail", args=[self.room.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "尚未占床")
        # 该学生出现在可分配下拉中，便于补分床位
        self.assertContains(resp, "孙七")

    def test_index_counts_only_bed_placed(self):
        """首页「已分配」只统计已占床学生，避免与床位分布图不一致。"""
        placed = Student.objects.create(
            school_class=self.cls, student_id="2026010100000000002", name="周八", gender="male",
        )
        DormAssignment.objects.create(
            student=placed, room=self.room,
            bed=DormBed.objects.get(room=self.room, bed_number="01"),
            is_current=True, semester=self.sem,
        )
        resp = self.client.get(reverse("dormitory:index"))
        self.assertEqual(resp.status_code, 200)
        room_row = next(r for r in resp.context["rooms"] if r.pk == self.room.pk)
        # 只统计占床的周八，未占床的孙七不计入
        self.assertEqual(room_row.assigned_count, 1)
