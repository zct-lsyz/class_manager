"""
导入导出服务测试
"""
import io
from django.test import TestCase

from apps.classes.models import SchoolClass
from apps.students.models import Student
from apps.exports.import_services import (
    parse_uploaded_file, validate_students, import_students,
)
from apps.exports.services import build_excel_bytes, fmt
from apps.exports.module_data import MODULE_EXPORTS, collect_module_data


class ImportServiceTests(TestCase):
    """导入服务测试"""

    def setUp(self):
        self.cls = SchoolClass.objects.create(name="高一(1)班", is_current=True)

    def _make_excel(self, headers, rows):
        """生成测试 Excel 文件的类文件对象"""
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.append(headers)
        for r in rows:
            ws.append(r)
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return buf

    def test_validate_duplicate_student_id(self):
        """重复学号校验"""
        Student.objects.create(
            school_class=self.cls, student_id="2026010100000000001", name="已存在", gender="male",
        )
        file = self._make_excel(
            ["学号", "姓名", "性别"],
            [["2026010100000000001", "张三", "男"]],
        )
        _, data_rows = parse_uploaded_file(file)
        valid_rows, errors = validate_students(data_rows)
        self.assertEqual(len(valid_rows), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("已存在", errors[0]["error"])

    def test_validate_invalid_gender(self):
        """非法性别校验"""
        file = self._make_excel(
            ["学号", "姓名", "性别"],
            [["2026010100000000002", "李四", "未知"]],
        )
        _, data_rows = parse_uploaded_file(file)
        valid_rows, errors = validate_students(data_rows)
        self.assertEqual(len(valid_rows), 0)
        self.assertEqual(len(errors), 1)
        self.assertIn("性别", errors[0]["error"])

    def test_import_valid_students(self):
        """正常导入学生"""
        file = self._make_excel(
            ["学号", "姓名", "性别", "身高(cm)"],
            [["2026010100000000003", "王五", "男", 175], ["2026010100000000004", "赵六", "女", 162]],
        )
        _, data_rows = parse_uploaded_file(file)
        valid_rows, errors = validate_students(data_rows)
        self.assertEqual(len(errors), 0)
        count = import_students(valid_rows, self.cls)
        self.assertEqual(count, 2)
        self.assertEqual(Student.objects.count(), 2)


class ExportServiceTests(TestCase):
    """导出服务测试"""

    def test_fmt_helper(self):
        """格式化辅助函数"""
        self.assertEqual(fmt(None), "-")
        self.assertEqual(fmt(""), "-")
        self.assertEqual(fmt("abc"), "abc")

    def test_build_excel_bytes(self):
        """生成 Excel bytes"""
        content = build_excel_bytes(
            [["1", "张三", "男"], ["2", "李四", "女"]],
            ["学号", "姓名", "性别"],
            "测试",
        )
        self.assertTrue(len(content) > 100)
        # 验证可以重新读取
        from openpyxl import load_workbook
        from io import BytesIO
        wb = load_workbook(BytesIO(content))
        ws = wb.active
        self.assertEqual(ws.cell(1, 1).value, "学号")
        self.assertEqual(ws.cell(2, 2).value, "张三")

    def test_every_registered_module_can_be_collected(self):
        school_class = SchoolClass.objects.create(name="导出测试班", is_current=True)
        for key, _name, _path in MODULE_EXPORTS:
            rows, headers, sheet_name, filename = collect_module_data(key, school_class)
            self.assertIsInstance(rows, list)
            self.assertTrue(headers)
            self.assertTrue(sheet_name)
            self.assertTrue(filename.endswith(".xlsx"))
