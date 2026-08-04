"""家长联系方式：主要联系人显示为「关系-手机号」，导入默认母亲。"""
from django.test import TestCase

from apps.students.models import Student, Guardian
from apps.exports.import_services import validate_guardians, import_guardians


STUDENT_ID = "2026010100000000001"


class GuardianDisplayTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            student_id=STUDENT_ID, name="小红", gender="female",
        )

    def _guardian(self, **kwargs):
        defaults = dict(
            student=self.student,
            father_phone="13800000000",
            mother_phone="13900000000",
        )
        defaults.update(kwargs)
        return Guardian.objects.create(**defaults)

    def test_primary_display_mother_phone(self):
        g = self._guardian(primary_contact="mother")
        self.assertEqual(g.get_primary_contact_display(), "母亲-13900000000")

    def test_primary_display_father_phone(self):
        g = self._guardian(primary_contact="father")
        self.assertEqual(g.get_primary_contact_display(), "父亲-13800000000")

    def test_primary_display_without_phone_shows_relation_only(self):
        g = self._guardian(mother_phone="", primary_contact="mother")
        self.assertEqual(g.get_primary_contact_display(), "母亲")

    def test_primary_display_other_shows_actual_guardian(self):
        g = self._guardian(other_guardian="爷爷", primary_contact="other")
        self.assertEqual(g.get_primary_contact_display(), "爷爷")

    def test_primary_display_legacy_raw_text(self):
        """兼容旧数据：主要联系人直接存了「母亲-手机号」。"""
        g = self._guardian(primary_contact="母亲-13900000000")
        self.assertEqual(g.get_primary_contact_display(), "母亲-13900000000")


class GuardianImportTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            student_id=STUDENT_ID, name="小刚", gender="male",
        )

    def _validate_and_import(self, row):
        valid_rows, errors = validate_guardians([row])
        self.assertFalse(errors, errors)
        import_guardians(valid_rows)

    def test_empty_primary_defaults_to_mother(self):
        """未写明父/母时默认为母亲（父母都有电话也默认母亲）。"""
        self._validate_and_import({
            "学号": self.student.student_id,
            "父亲电话": "13800000000",
            "母亲电话": "13900000000",
        })
        g = Guardian.objects.get(student=self.student)
        self.assertEqual(g.primary_contact, "mother")

    def test_mother_primary_explicit(self):
        self._validate_and_import({
            "学号": self.student.student_id,
            "母亲电话": "13900000000",
            "主要联系人": "母亲",
        })
        self.assertEqual(
            Guardian.objects.get(student=self.student).primary_contact, "mother",
        )

    def test_mother_phone_format_primary(self):
        """主要联系人按「母亲-手机号」格式填写也能识别。"""
        self._validate_and_import({
            "学号": self.student.student_id,
            "母亲电话": "13900000000",
            "主要联系人": "母亲-13900000000",
        })
        self.assertEqual(
            Guardian.objects.get(student=self.student).primary_contact, "mother",
        )

    def test_father_primary_explicit(self):
        self._validate_and_import({
            "学号": self.student.student_id,
            "父亲电话": "13800000000",
            "母亲电话": "13900000000",
            "主要联系人": "父亲",
        })
        self.assertEqual(
            Guardian.objects.get(student=self.student).primary_contact, "father",
        )

    def test_grandparent_relation_is_other(self):
        """祖父/祖母等非父母关系不应被误判为父母。"""
        self._validate_and_import({
            "学号": self.student.student_id,
            "父亲电话": "13800000000",
            "母亲电话": "13900000000",
            "主要联系人": "祖父",
        })
        self.assertEqual(
            Guardian.objects.get(student=self.student).primary_contact, "other",
        )

    def test_other_relation_explicit(self):
        self._validate_and_import({
            "学号": self.student.student_id,
            "母亲电话": "13900000000",
            "主要联系人": "其他监护人",
        })
        self.assertEqual(
            Guardian.objects.get(student=self.student).primary_contact, "other",
        )
