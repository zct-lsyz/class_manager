"""数据导入页 GET 渲染回归测试。"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass


class ImportPageGetTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="imp-page", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="导入页班", is_current=True,
        )

    def test_import_page_renders(self):
        for query in ("", "?type=students", "?type=guardians"):
            resp = self.client.get(reverse("exports:import_data") + query)
            self.assertEqual(resp.status_code, 200, query)

    def test_template_download_urls_reverse(self):
        for t in ("student_info", "students", "guardians"):
            url = reverse("exports:template_download", args=[t])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
