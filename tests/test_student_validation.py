from django.test import TestCase

from apps.exports.import_services import validate_guardians, validate_students
from apps.students.forms import GuardianForm, StudentForm
from apps.students.models import Student


class StudentValidationTests(TestCase):
    def test_student_form_rejects_invalid_formats(self):
        form = StudentForm(data={
            "student_id": "123",
            "name": "张三",
            "gender": "male",
            "height": "175.5",
            "primary_phone": "1380013800a",
            "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("student_id", form.errors)
        self.assertIn("height", form.errors)
        self.assertIn("primary_phone", form.errors)

    def test_guardian_form_rejects_invalid_phone(self):
        form = GuardianForm(data={"father_phone": "1234567890"})
        self.assertFalse(form.is_valid())
        self.assertIn("father_phone", form.errors)

    def test_student_import_rejects_invalid_formats(self):
        valid_rows, errors = validate_students([{
            "学号": "123",
            "姓名": "张三",
            "性别": "男",
        }])
        self.assertFalse(valid_rows)
        self.assertEqual(errors[0]["error"], "学号必须为19位纯数字")

    def test_guardian_import_rejects_invalid_phone(self):
        student = Student.objects.create(
            student_id="2026010100000000001", name="张三", gender="male",
        )
        valid_rows, errors = validate_guardians([{
            "学号": student.student_id,
            "父亲电话": "1380013800a",
        }])
        self.assertFalse(valid_rows)
        self.assertEqual(errors[0]["field"], "父亲电话")
