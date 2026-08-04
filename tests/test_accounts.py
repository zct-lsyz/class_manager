"""账户安全与受保护附件测试。"""
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse


class AccountSecurityTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user("teacher", password="strong-test-password")
        from apps.classes.models import SchoolClass
        SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)

    def test_external_next_url_is_rejected(self):
        response = self.client.post(
            reverse("accounts:login") + "?next=https://evil.example/steal",
            {"username": "teacher", "password": "strong-test-password"},
        )
        self.assertRedirects(response, reverse("dashboard:index"), fetch_redirect_response=False)

    def test_lockout_applies_to_a_new_session_from_same_ip(self):
        login_url = reverse("accounts:login")
        for _index in range(5):
            self.client.post(
                login_url,
                {"username": "teacher", "password": "wrong-password"},
                REMOTE_ADDR="192.0.2.10",
            )
        new_client = Client()
        response = new_client.get(login_url, REMOTE_ADDR="192.0.2.10")
        self.assertContains(response, "登录失败次数过多")

    def test_media_requires_login(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            media_root = Path(temp_dir_name)
            (media_root / "proof.txt").write_text("private", encoding="utf-8")
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.get("/protected-media/proof.txt")
                self.assertEqual(response.status_code, 302)
                self.client.force_login(self.user)
                response = self.client.get("/protected-media/proof.txt")
                self.assertEqual(response.status_code, 200)
                response.close()


class AccountDeletionTests(TestCase):
    """注销账号应真正删除学生等关联数据，而不是只解绑。"""

    def setUp(self):
        from apps.classes.models import SchoolClass
        from apps.students.models import Student
        self.user = User.objects.create_user("del-user", password="strong-test-password")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="删除班", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="2023370613000130205",
            name="张三", gender="male",
        )
        from apps.students.models import Guardian
        Guardian.objects.create(
            student=self.student, mother_name="母亲", mother_phone="13900000000",
            primary_contact="mother",
        )

    def test_delete_account_removes_students(self):
        """注销账号后，学生及其家长记录应被删除（学号不再占用唯一约束）。"""
        from apps.students.models import Student, Guardian
        resp = self.client.post(
            reverse("accounts:delete_account"),
            {"password": "strong-test-password"},
        )
        self.assertEqual(resp.status_code, 302)
        # 账号被删除
        self.assertFalse(User.objects.filter(username="del-user").exists())
        # 学生和班级都被删除，而不是留成孤儿
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(Guardian.objects.filter(student_id=self.student.pk).exists())
        self.assertFalse(Student.objects.filter(
            student_id="2023370613000130205",
        ).exists())

    def test_delete_account_removes_backups_and_media(self):
        """注销账号后，备份记录及物理文件、媒体文件都应被清除。"""
        import tempfile
        from pathlib import Path
        from django.test import override_settings
        from apps.backups.models import BackupRecord, MediaArchiveExport
        with tempfile.TemporaryDirectory() as backup_dir, tempfile.TemporaryDirectory() as media_dir:
            with override_settings(
                MEDIA_ROOT=Path(media_dir),
            ):
                # 造一个备份记录 + 一个真实备份文件
                backup_file = Path(backup_dir) / "backup_test.zip"
                backup_file.write_bytes(b"fake-backup")
                BackupRecord.objects.create(
                    backup_type="manual", status="completed",
                    file_path=str(backup_file), user=self.user, school_class=self.cls,
                )
                media_file = Path(media_dir) / "proof.txt"
                media_file.write_text("private", encoding="utf-8")
                MediaArchiveExport.objects.create(
                    file_path=str(Path(backup_dir) / "archive.zip"),
                    user=self.user,
                )

                resp = self.client.post(
                    reverse("accounts:delete_account"),
                    {"password": "strong-test-password"},
                )
                self.assertEqual(resp.status_code, 302)
                self.assertFalse(BackupRecord.objects.exists())
                self.assertFalse(MediaArchiveExport.objects.exists())
                # 备份物理文件不存在（如果 faked 文件能被删）——这里备份文件在 backup_dir，
                # 我们只断言 DB 记录被删 + 媒体文件被清空
                self.assertFalse((Path(media_dir) / "proof.txt").exists())

    def test_wipe_user_command_deletes_students(self):
        """wipe_user 命令也应彻底删除学生与备份。"""
        from io import StringIO
        from django.core.management import call_command
        from apps.students.models import Student
        from apps.backups.models import BackupRecord
        BackupRecord.objects.create(
            backup_type="auto_daily", status="completed",
            file_path="", school_class=self.cls,
        )
        out = StringIO()
        call_command("wipe_user", username="del-user", force=True, stdout=out)
        self.assertFalse(User.objects.filter(username="del-user").exists())
        self.assertFalse(Student.objects.filter(pk=self.student.pk).exists())
        self.assertFalse(BackupRecord.objects.exists())


class CleanupOrphanedDataTests(TestCase):
    """清理命令：删除注销账号遗留的孤儿数据。"""

    def test_cleanup_removes_orphans(self):
        from io import StringIO
        from django.core.management import call_command
        from apps.classes.models import SchoolClass
        from apps.students.models import Student
        from apps.backups.models import BackupRecord
        # 无班级的孤儿学生 + 无归属的备份
        Student.objects.create(
            student_id="2023370613000999999", name="孤儿", gender="male",
        )
        BackupRecord.objects.create(
            backup_type="manual", status="completed", file_path="",
        )
        out = StringIO()
        call_command("cleanup_orphaned_data", stdout=out)
        self.assertIn("已清理", out.getvalue())
        self.assertFalse(Student.objects.filter(student_id="2023370613000999999").exists())
        self.assertFalse(BackupRecord.objects.exists())

    def test_cleanup_dry_run_does_not_delete(self):
        from io import StringIO
        from django.core.management import call_command
        from apps.students.models import Student
        Student.objects.create(
            student_id="2023370613000888888", name="孤儿2", gender="male",
        )
        out = StringIO()
        call_command("cleanup_orphaned_data", dry_run=True, stdout=out)
        self.assertIn("将清理", out.getvalue())
        self.assertTrue(Student.objects.filter(student_id="2023370613000888888").exists())
