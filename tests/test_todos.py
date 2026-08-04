"""
待办事项 + 到期通知 API 测试
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.todos.models import TodoItem


class TodoItemTests(TestCase):
    """待办事项 CRUD"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="todo", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True,
        )

    def test_add_todo(self):
        """添加待办项"""
        response = self.client.post(reverse("todos:add"), {
            "title": "买文具", "deadline": "2026-08-02T17:00",
        })
        self.assertEqual(response.status_code, 302)
        todo = TodoItem.objects.get(title="买文具")
        self.assertEqual(todo.school_class, self.cls)
        self.assertEqual(todo.created_by, self.user)
        self.assertFalse(todo.is_completed)
        self.assertEqual(
            timezone.localtime(todo.deadline).strftime("%Y-%m-%d %H:%M"),
            "2026-08-02 17:00",
        )

    def test_add_todo_without_deadline(self):
        """无截止时间的待办"""
        self.client.post(reverse("todos:add"), {"title": "整理教案", "deadline": ""})
        todo = TodoItem.objects.get(title="整理教案")
        self.assertIsNone(todo.deadline)

    def test_add_todo_empty_title_rejected(self):
        """空标题被拒绝，不创建记录"""
        response = self.client.post(reverse("todos:add"), {"title": "  ", "deadline": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TodoItem.objects.count(), 0)

    def test_toggle_todo(self):
        """切换完成状态"""
        todo = TodoItem.objects.create(
            school_class=self.cls, created_by=self.user, title="批改作业",
        )
        self.client.post(reverse("todos:toggle", args=[todo.pk]))
        todo.refresh_from_db()
        self.assertTrue(todo.is_completed)
        self.client.post(reverse("todos:toggle", args=[todo.pk]))
        todo.refresh_from_db()
        self.assertFalse(todo.is_completed)

    def test_delete_todo_soft(self):
        """软删除待办"""
        todo = TodoItem.objects.create(
            school_class=self.cls, created_by=self.user, title="写总结",
        )
        self.client.post(reverse("todos:delete", args=[todo.pk]))
        todo.refresh_from_db()
        self.assertTrue(todo.is_deleted)

    def test_dashboard_shows_active_todos(self):
        """工作台首页显示待办"""
        TodoItem.objects.create(school_class=self.cls, created_by=self.user, title="交计划")
        response = self.client.get(reverse("dashboard:index"))
        self.assertContains(response, "交计划")
        self.assertEqual(response.context["active_todos"].count(), 1)


class TodoAccountSharedTests(TestCase):
    """待办在同一账号下跨班级共享，不随切换班级而变化。"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="todo-shared", password="pass")
        self.client.force_login(self.user)
        self.cls_a = SchoolClass.objects.create(
            created_by=self.user, name="A班", is_current=True,
        )
        self.cls_b = SchoolClass.objects.create(
            created_by=self.user, name="B班", is_current=False,
        )

    def _switch_class(self, target):
        SchoolClass.objects.filter(created_by=self.user).update(is_current=False)
        target.is_current = True
        target.save(update_fields=["is_current"])

    def test_todos_shared_across_classes(self):
        """A 班创建的待办，切到 B 班后仍能看到。"""
        TodoItem.objects.create(
            school_class=self.cls_a, created_by=self.user, title="A班的待办",
        )
        self._switch_class(self.cls_b)
        response = self.client.get(reverse("todos:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A班的待办")
        self.assertEqual(response.context["active_todos"].count(), 1)

    def test_todo_toggle_works_after_switching_class(self):
        """跨班切换后仍可操作 A 班的待办。"""
        todo = TodoItem.objects.create(
            school_class=self.cls_a, created_by=self.user, title="跨班待办",
        )
        self._switch_class(self.cls_b)
        self.client.post(reverse("todos:toggle", args=[todo.pk]))
        todo.refresh_from_db()
        self.assertTrue(todo.is_completed)

    def test_add_todo_without_current_class(self):
        """没有当前班级时也能添加待办（账号级共享）。"""
        SchoolClass.objects.filter(created_by=self.user).update(is_current=False)
        response = self.client.post(reverse("todos:add"), {"title": "无班级待办"})
        self.assertEqual(response.status_code, 302)
        todo = TodoItem.objects.get(title="无班级待办")
        self.assertIsNone(todo.school_class)

    def test_dashboard_todo_count_across_classes(self):
        """工作台待办数量跨班共享。"""
        TodoItem.objects.create(
            school_class=self.cls_a, created_by=self.user, title="A班待办",
        )
        self._switch_class(self.cls_b)
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.context["active_todos"].count(), 1)


class TodoNotificationApiTests(TestCase):
    """到期待办通知 API"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="notif", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(2)班", is_current=True)
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True,
        )

    def _get_api(self):
        return self.client.get(reverse("dashboard:api_notifications"))

    def test_no_due_todos_returns_empty(self):
        """无到期待办时 due_count=0"""
        TodoItem.objects.create(
            school_class=self.cls, created_by=self.user, title="未来事项",
            deadline=timezone.now() + timedelta(days=1),
        )
        response = self._get_api()
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["due_count"], 0)
        self.assertEqual(data["due_todos"], [])

    def test_due_todo_appears_in_api(self):
        """到期待办出现在 API 响应中"""
        TodoItem.objects.create(
            school_class=self.cls, created_by=self.user, title="买文具",
            deadline=timezone.now() - timedelta(minutes=5),
        )
        response = self._get_api()
        data = response.json()
        self.assertEqual(data["due_count"], 1)
        self.assertEqual(data["due_todos"][0]["title"], "买文具")

    def test_completed_due_todo_excluded(self):
        """已完成或已删除的待办不触发通知"""
        TodoItem.objects.create(
            school_class=self.cls, created_by=self.user, title="已完成事项",
            deadline=timezone.now() - timedelta(minutes=5), is_completed=True,
        )
        TodoItem.objects.create(
            school_class=self.cls, created_by=self.user, title="已删除事项",
            deadline=timezone.now() - timedelta(minutes=5), is_deleted=True,
        )
        response = self._get_api()
        data = response.json()
        self.assertEqual(data["due_count"], 0)
