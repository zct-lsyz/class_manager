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
