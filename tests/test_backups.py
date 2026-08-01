"""完整备份服务测试。"""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.activities.models import Activity
from apps.backups.models import MediaArchiveExport
from apps.backups.services import create_backup, restore_backup, verify_backup
from apps.backups.storage_services import clear_archived_modules, create_media_archive, import_media_archives
from apps.classes.models import SchoolClass


class BackupServiceTests(TestCase):

    def test_backup_contains_consistent_database_media_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            database_path = temp_dir / "source.sqlite3"
            media_root = temp_dir / "media"
            backup_dir = temp_dir / "backups"
            media_root.mkdir()
            (media_root / "proof.txt").write_text("attachment", encoding="utf-8")
            connection = sqlite3.connect(database_path)
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO sample(value) VALUES ('before')")
            connection.commit()
            connection.close()

            with override_settings(MEDIA_ROOT=media_root), patch(
                "apps.backups.services.BACKUP_DIR", backup_dir,
            ), patch(
                "apps.backups.services._get_db_path", return_value=database_path,
            ):
                record = create_backup("manual")
                verified, message = verify_backup(record)

            self.assertTrue(verified, message)
            with zipfile.ZipFile(record.file_path) as archive:
                names = set(archive.namelist())
                self.assertIn("database/db.sqlite3", names)
                self.assertIn("media/proof.txt", names)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["attachment_count"], 1)
                self.assertIn("sha256", manifest["files"]["database/db.sqlite3"])

    def test_restore_replaces_database_and_media_as_one_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            database_path = temp_dir / "source.sqlite3"
            media_root = temp_dir / "media"
            backup_dir = temp_dir / "backups"
            media_root.mkdir()
            (media_root / "proof.txt").write_text("before", encoding="utf-8")
            connection = sqlite3.connect(database_path)
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO sample(value) VALUES ('before')")
            connection.commit()
            connection.close()

            with override_settings(MEDIA_ROOT=media_root), patch(
                "apps.backups.services.BACKUP_DIR", backup_dir,
            ), patch(
                "apps.backups.services._get_db_path", return_value=database_path,
            ), patch("apps.backups.services.connections.close_all"):
                record = create_backup("manual")
                connection = sqlite3.connect(database_path)
                connection.execute("UPDATE sample SET value='after'")
                connection.commit()
                connection.close()
                (media_root / "proof.txt").write_text("after", encoding="utf-8")
                (media_root / "extra.txt").write_text("extra", encoding="utf-8")
                restore_backup(record)

            connection = sqlite3.connect(database_path)
            value = connection.execute("SELECT value FROM sample").fetchone()[0]
            connection.close()
            self.assertEqual(value, "before")
            self.assertEqual((media_root / "proof.txt").read_text(encoding="utf-8"), "before")
            self.assertFalse((media_root / "extra.txt").exists())


class MediaArchiveTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("archive-manager", password="test-password")
        self.client.force_login(self.user)

    def test_archive_clears_only_media_and_import_restores_existing_record(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            media_root = temp_dir / "media"
            archive_dir = temp_dir / "archives"
            school_class = SchoolClass.objects.create(created_by=self.user, name="高一(1)班")
            with override_settings(MEDIA_ROOT=media_root), patch(
                "apps.backups.storage_services.ARCHIVE_DIR", archive_dir,
            ):
                activity = Activity.objects.create(
                    school_class=school_class, name="保留的文字记录",
                    photo=SimpleUploadedFile("proof.jpg", b"image-data", content_type="image/jpeg"),
                )
                original_photo = activity.photo.name
                archive = create_media_archive(["activities"], self.user)
                with zipfile.ZipFile(archive.file_path) as package:
                    records = json.loads(package.read("data.json"))
                self.assertEqual(records[0]["fields"], {"photo": original_photo})
                self.assertNotIn("name", records[0]["fields"])

                clear_archived_modules(archive)
                activity.refresh_from_db()
                self.assertEqual(activity.name, "保留的文字记录")
                self.assertEqual(activity.photo.name, "")
                self.assertEqual(Activity.objects.count(), 1)

                uploaded = SimpleUploadedFile(
                    Path(archive.file_path).name, Path(archive.file_path).read_bytes(),
                    content_type="application/zip",
                )
                packages, records = import_media_archives([uploaded])
                activity.refresh_from_db()
                self.assertEqual((packages, records), (1, 1))
                self.assertEqual(activity.name, "保留的文字记录")
                self.assertEqual(activity.photo.name, original_photo)
                self.assertTrue((media_root / original_photo).is_file())

    @patch("apps.backups.views.clear_archived_modules")
    def test_clear_requires_exact_confirmation_words(self, clear_mock):
        archive = MediaArchiveExport.objects.create(
            modules=["activities"], file_path="unused.zip", user=self.user,
        )
        url = reverse("backups:media_archive_clear", args=[archive.pk])
        self.client.post(url, {"confirmation": "确认清理", "password": "test-password"})
        clear_mock.assert_not_called()

        self.client.post(url, {"confirmation": "确认清除", "password": "test-password"})
        clear_mock.assert_called_once_with(archive)

    def test_storage_center_separates_generated_packages_and_import_history(self):
        MediaArchiveExport.objects.create(
            modules=["activities"], file_path="unused.zip", user=self.user,
        )
        response = self.client.get(reverse("backups:storage_center"))
        self.assertContains(response, "已生成的数据包")
        self.assertContains(response, "批量导入恢复")
        self.assertContains(response, "导入历史")
        self.assertContains(response, 'pattern="确认清除"', html=False)
