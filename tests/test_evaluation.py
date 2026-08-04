"""评选：评分规则保存与计算回归测试。"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.evaluation.models import EvaluationProject, EvaluationResult
from apps.evaluation.services import calculate_evaluation


class EvaluationFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="eval", password="pass")
        self.client = Client()
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(
            created_by=self.user, name="评选班", is_current=True,
        )
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027",
            semester_type="first", is_current=True,
        )
        self.students = [
            Student.objects.create(
                school_class=self.cls, student_id=f"E2026010100000000{i}",
                name=f"学生{i}", gender="male",
            )
            for i in range(1, 6)
        ]

    def _post_project(self, url, name="sanhxs"):
        return self.client.post(url, {
            "name": name,
            "description": "",
            "cycle": "monthly",
            "is_active": "on",
            # 评分规则：积分 0.5 + 成绩排名 0.5
            "rule_keys": ["points", "score_rank"],
            "rule_labels": ["积分", "成绩排名"],
            "rule_weights": ["0.5", "0.5"],
        })

    def test_create_persists_rules(self):
        """新建评选项目后，评分规则应被保存。"""
        resp = self._post_project(reverse("evaluation:project_create"))
        self.assertEqual(resp.status_code, 302)
        project = EvaluationProject.objects.get(name="sanhxs")
        rules = project.rules()
        self.assertEqual(len(rules), 2)
        self.assertEqual({r["key"] for r in rules}, {"points", "score_rank"})

    def test_edit_persists_rules(self):
        """编辑评选项目时，规则应被正确保存并可重新计算。"""
        project = EvaluationProject.objects.create(
            school_class=self.cls, semester=self.sem, name="旧项目",
            cycle="monthly", rules_json={"indicators": []},
        )
        resp = self._post_project(
            reverse("evaluation:project_edit", args=[project.pk]),
        )
        self.assertEqual(resp.status_code, 302)
        project.refresh_from_db()
        self.assertEqual(len(project.rules()), 2)

    def test_calculate_with_rules_returns_results(self):
        """有规则且有学生时，计算应生成结果，而不是提示未配置规则。"""
        project = EvaluationProject.objects.create(
            school_class=self.cls, semester=self.sem, name="测试项目",
            cycle="monthly",
            rules_json={"indicators": [
                {"key": "points", "label": "积分", "weight": 0.5},
                {"key": "score_rank", "label": "成绩排名", "weight": 0.5},
            ]},
        )
        results, period_label, count = calculate_evaluation(project)
        self.assertNotEqual(results, [])
        self.assertEqual(count, len(self.students))
        self.assertEqual(EvaluationResult.objects.filter(project=project).count(), len(self.students))

    def test_calculate_without_rules_returns_empty(self):
        """没有规则时计算返回空（用于提示）。"""
        project = EvaluationProject.objects.create(
            school_class=self.cls, semester=self.sem, name="无规则",
            cycle="monthly", rules_json={"indicators": []},
        )
        results, _label, count = calculate_evaluation(project)
        self.assertEqual(results, [])
        self.assertEqual(count, 0)

    def test_calculate_edit_page_warning_flow(self):
        """编辑页展示的规则与计算应一致：保存后计算不再报未配置。"""
        project = EvaluationProject.objects.create(
            school_class=self.cls, semester=self.sem, name="sanhxs",
            cycle="monthly", rules_json={"indicators": []},
        )
        # 编辑页 GET 应显示规则编辑器（当前为空 → 一个默认行）
        resp = self.client.get(reverse("evaluation:project_edit", args=[project.pk]))
        self.assertEqual(resp.status_code, 200)
        # 保存规则
        self._post_project(reverse("evaluation:project_edit", args=[project.pk]))
        project.refresh_from_db()
        self.assertEqual(len(project.rules()), 2)
        # 计算不再为空
        results, _label, _count = calculate_evaluation(project)
        self.assertNotEqual(results, [])

    def test_calculate_view_success_with_rules_and_students(self):
        """有规则+有学生时，点「重新计算」应成功而不是提示未配置。"""
        project = EvaluationProject.objects.create(
            school_class=self.cls, semester=self.sem, name="能计算",
            cycle="monthly",
            rules_json={"indicators": [
                {"key": "points", "label": "积分", "weight": 0.5},
                {"key": "score_rank", "label": "成绩排名", "weight": 0.5},
            ]},
        )
        resp = self.client.post(reverse("evaluation:calculate", args=[project.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertRedirects(resp, f"/evaluation/?project={project.pk}")
        self.assertEqual(EvaluationResult.objects.filter(project=project).count(), len(self.students))

    def test_calculate_view_warns_no_rules(self):
        """没有规则时，提示是「未配置评分规则」。"""
        project = EvaluationProject.objects.create(
            school_class=self.cls, semester=self.sem, name="无规则",
            cycle="monthly", rules_json={"indicators": []},
        )
        resp = self.client.post(reverse("evaluation:calculate", args=[project.pk]))
        self.assertEqual(resp.status_code, 302)
        resp2 = self.client.get(resp.url)
        self.assertContains(resp2, "未配置评分规则")

    def test_calculate_view_warns_no_students(self):
        """已配规则但班里没有学生时，提示不再是「未配置评分规则」。"""
        # 切到没有学生的班级
        SchoolClass.objects.filter(created_by=self.user).update(is_current=False)
        empty_cls = SchoolClass.objects.create(
            created_by=self.user, name="空班", is_current=True,
        )
        project = EvaluationProject.objects.create(
            school_class=empty_cls, name="空班项目",
            cycle="monthly",
            rules_json={"indicators": [
                {"key": "points", "label": "积分", "weight": 1.0},
            ]},
        )
        resp = self.client.post(reverse("evaluation:calculate", args=[project.pk]))
        self.assertEqual(resp.status_code, 302)
        resp2 = self.client.get(resp.url)
        self.assertContains(resp2, "没有可参与评选的学生")
        self.assertNotContains(resp2, "未配置评分规则")
