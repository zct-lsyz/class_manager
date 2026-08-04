"""Repro: student_info import (统一导入) must not 500 on realistic data."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.exports.import_services import (
    import_student_info, import_students, validate_student_info,
    validate_students, parse_uploaded_file,
)
from openpyxl import Workbook
import io


STUDENT_ID = "2026010100000000001"


def make_excel(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class StudentInfoImportReproTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="repro-import2", password="pass")
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="导入班", is_current=True,
        )
        Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )

    def test_full_flow_with_dorm_and_contacts(self):
        """模拟用户实际导入：宿舍+床位+联系人关系。"""
        excel = make_excel(
            ["学号", "姓名", "性别", "出生日期", "身高(cm)", "视力", "座位需求", "职务",
             "家庭住址", "是否团员", "是否住校", "宿舍", "床位",
             "联系人关系", "联系人电话", "备用联系人关系", "备用联系人电话", "备注"],
            [
                ["2026010100000000001", "张三", "男", "2010-03-15", 175, "左5.0 右4.8",
                 "", "", "山东省济南市", "是", "是", "一栋 101", "3",
                 "母亲", "13800138000", "父亲", "13900139000", ""],
                ["2026010100000000002", "李四", "女", "", 162, "", "", "",
                 "", "否", "否", "", "", "父亲", "13700137000", "", "", ""],
            ],
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded = SimpleUploadedFile("stu.xlsx", excel.getvalue())
        headers, data_rows = parse_uploaded_file(uploaded)
        self.assertTrue(data_rows)
        valid_rows, errors = validate_student_info(data_rows, self.cls)
        self.assertEqual(errors, [])
        count = import_student_info(valid_rows, self.cls)
        self.assertEqual(count, 2)
        # 宿舍分配应已生成且占床
        zhang = Student.objects.get(name="张三")
        assignment = zhang.dorm_assignments.filter(is_current=True).first()
        self.assertIsNotNone(assignment)
        self.assertIsNotNone(assignment.bed, "张三应被分配到空闲床")
        # 家长记录应已生成
        self.assertTrue(hasattr(zhang, "guardian"))
        self.assertEqual(zhang.guardian.mother_phone, "13800138000")

    def test_duplicate_id_cross_class_caught_at_validate(self):
        """学号在其他班级已存在时，校验应报错，而不是导入时 500。"""
        other = SchoolClass.objects.create(
            created_by=self.user, name="另一班", is_current=False,
        )
        Student.objects.create(
            school_class=other, student_id=STUDENT_ID, name="跨班生", gender="male",
        )
        excel = make_excel(
            ["学号", "姓名", "性别"], [[STUDENT_ID, "张三", "男"]],
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded = SimpleUploadedFile("stu.xlsx", excel.getvalue())
        _headers, data_rows = parse_uploaded_file(uploaded)
        valid_rows, errors = validate_student_info(data_rows, self.cls)
        self.assertFalse(valid_rows)
        self.assertTrue(any("已存在" in e["error"] for e in errors))

    def test_import_skips_duplicate_student_id(self):
        """重复导入同一批数据时应跳过已存在的学号，而不是 500。"""
        excel = make_excel(
            ["学号", "姓名", "性别"], [[STUDENT_ID, "张三", "男"]],
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        uploaded = SimpleUploadedFile("stu.xlsx", excel.getvalue())
        _headers, data_rows = parse_uploaded_file(uploaded)
        valid_rows, _ = validate_student_info(data_rows, self.cls)
        self.assertEqual(import_student_info(valid_rows, self.cls), 1)
        # 再次导入（模拟重复/预览过期）：不应 500，应跳过
        self.assertEqual(import_student_info(valid_rows, self.cls), 0)
        self.assertEqual(Student.objects.filter(student_id=STUDENT_ID).count(), 1)

    def test_roster_import_skips_duplicate_student_id(self):
        """花名册导入同样跳过已存在的学号，不报 500。"""
        Student.objects.create(
            school_class=self.cls, student_id=STUDENT_ID, name="已存在", gender="male",
        )
        rows = [{
            "row": 2, "student_id": STUDENT_ID, "name": "张三", "gender": "male",
            "birth_date": None, "height": None, "vision": "", "seat_requirement": "",
            "class_position": "", "dormitory": "", "bed_number": "",
            "primary_contact": "", "primary_phone": "", "remarks": "",
        }]
        self.assertEqual(import_students(rows, self.cls), 0)
        self.assertEqual(Student.objects.filter(student_id=STUDENT_ID).count(), 1)

    def test_roster_validate_duplicate_cross_class_caught(self):
        """花名册校验也需全库查重。"""
        other = SchoolClass.objects.create(
            created_by=self.user, name="三班", is_current=False,
        )
        Student.objects.create(
            school_class=other, student_id=STUDENT_ID, name="跨班生", gender="male",
        )
        valid_rows, errors = validate_students(
            [{"学号": STUDENT_ID, "姓名": "张三", "性别": "男"}], self.cls,
        )
        self.assertFalse(valid_rows)
        self.assertTrue(any("已存在" in e["error"] for e in errors))
