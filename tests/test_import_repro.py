"""Repro: student_info import (统一导入) must not 500 on realistic data."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.exports.import_services import (
    import_student_info, validate_student_info, parse_uploaded_file,
)
from openpyxl import Workbook
import io


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
