"""完整备份服务测试。"""
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.backups.services import create_backup, restore_backup, verify_backup


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
