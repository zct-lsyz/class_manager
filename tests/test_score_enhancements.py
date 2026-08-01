"""
三项新功能测试：
1. 成绩宽表模板语数英列名不带"赋分"后缀
2. 分析页名次进退筛选（历史考试对比 + 阈值）
3. 学生详情页历次考试成绩折线图数据
"""
import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook
from openpyxl import load_workbook

from apps.classes.models import SchoolClass, Semester
from apps.classes.subjects import Subject
from apps.students.models import Student
from apps.scores.models import Exam, ExamSubject, Score


class WideTemplateChineseMathEnglishTests(TestCase):
    """成绩宽表模板：语数英不带'赋分'后缀"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="tpl", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(1)班", is_current=True)
        self.student = Student.objects.create(
            school_class=self.cls, student_id="2026000000000000001", name="张三", gender="male",
        )

    def _download_template(self):
        response = self.client.get(reverse("scores:score_import_wide_template"))
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(io.BytesIO(response.content))
        sheet = wb["成绩导入"]
        headers = [cell.value for cell in sheet[1]]
        return headers

    def test_yuwen_shuxue_yingyu_headers_have_no_fufen(self):
        headers = self._download_template()
        # 语数英的第一列应为纯科目名，不含"赋分"
        for subj in ("语文", "数学", "英语"):
            first_score_col = headers[headers.index(subj):]
            self.assertEqual(headers[headers.index(subj)], subj)
            self.assertNotIn(f"{subj}赋分", headers)
            self.assertNotIn(f"{subj}原始", headers)
            # 名次列保留
            self.assertIn(f"{subj}班名次", headers)
            self.assertIn(f"{subj}级名次", headers)
            self.assertIn(f"{subj}市名次", headers)

    def test_other_subjects_keep_fufen(self):
        headers = self._download_template()
        # 选考科目保留"赋分"和"原始"两列
        for subj in ("物理", "化学", "生物", "政治", "历史", "地理", "日语"):
            self.assertIn(f"{subj}赋分", headers)
            self.assertIn(f"{subj}原始", headers)


class RankChangeFilterTests(TestCase):
    """分析页名次进退筛选"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="rank", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(2)班", is_current=True)
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True,
        )
        self.exam1 = Exam.objects.create(school_class=self.cls, semester=self.sem, name="月考一", date="2026-09-10")
        self.exam2 = Exam.objects.create(school_class=self.cls, semester=self.sem, name="月考二", date="2026-10-10")
        self.subj_yw = Subject.objects.create(name="语文")
        self.subj_sx = Subject.objects.create(name="数学")
        self.es1_yw = ExamSubject.objects.create(exam=self.exam1, subject=self.subj_yw, full_score=100)
        self.es1_sx = ExamSubject.objects.create(exam=self.exam1, subject=self.subj_sx, full_score=100)
        self.es2_yw = ExamSubject.objects.create(exam=self.exam2, subject=self.subj_yw, full_score=100)
        self.es2_sx = ExamSubject.objects.create(exam=self.exam2, subject=self.subj_sx, full_score=100)

        # 4 名学生，两科成绩
        self.names = ["张三", "李四", "王五", "赵六"]
        self.students = {}
        for i, name in enumerate(self.names, 1):
            s = Student.objects.create(
                school_class=self.cls, student_id=f"2026000{i}", name=name, gender="male",
            )
            self.students[name] = s

        # 月考一成绩（决定历史排名）
        # 张三180, 李四160, 王五140, 赵六120 → 排名1,2,3,4
        self._score(self.exam1, "张三", 90, 90)
        self._score(self.exam1, "李四", 80, 80)
        self._score(self.exam1, "王五", 70, 70)
        self._score(self.exam1, "赵六", 60, 60)

        # 月考二成绩（决定当前排名）
        # 李四180, 王五170, 张三160, 赵六120 → 排名1,2,3,4
        # 李四 2→1 进步1名；王五 3→2 进步1名；张三 1→3 退步2名；赵六 4→4 不变
        self._score(self.exam2, "李四", 90, 90)
        self._score(self.exam2, "王五", 85, 85)
        self._score(self.exam2, "张三", 80, 80)
        self._score(self.exam2, "赵六", 60, 60)

    def _score(self, exam, name, yw, sx):
        Score.objects.create(exam=exam, exam_subject=ExamSubject.objects.get(exam=exam, subject=self.subj_yw),
                             student=self.students[name], score=yw, status="normal")
        Score.objects.create(exam=exam, exam_subject=ExamSubject.objects.get(exam=exam, subject=self.subj_sx),
                             student=self.students[name], score=sx, status="normal")

    def _analysis(self, **params):
        params.setdefault("exam_id", str(self.exam2.pk))
        params.setdefault("history_exam_id", str(self.exam1.pk))
        return self.client.get(reverse("scores:analysis"), params)

    def test_progress_threshold_filters_improved_students(self):
        """进步阈值≥1 应筛出李四和王五"""
        response = self._analysis(rank_progress_threshold="1")
        self.assertEqual(response.status_code, 200)
        students = [rc["student"].name for rc in response.context["rank_change_students"]]
        self.assertIn("李四", students)
        self.assertIn("王五", students)
        self.assertNotIn("张三", students)
        self.assertNotIn("赵六", students)

    def test_decline_threshold_filters_declined_students(self):
        """退步阈值≥1 应筛出张三（1→3 退步2名）"""
        response = self._analysis(rank_decline_threshold="1")
        self.assertEqual(response.status_code, 200)
        students = [rc["student"].name for rc in response.context["rank_change_students"]]
        self.assertIn("张三", students)
        self.assertNotIn("李四", students)
        self.assertNotIn("王五", students)

    def test_rank_delta_values_correct(self):
        """张三 delta 应为 -2（退步2名），李四 delta 应为 +1"""
        response = self._analysis(rank_progress_threshold="1", rank_decline_threshold="1")
        deltas = {rc["student"].name: rc["delta"] for rc in response.context["rank_change_students"]}
        self.assertEqual(deltas["张三"], -2)
        self.assertEqual(deltas["李四"], 1)
        self.assertEqual(deltas["王五"], 1)

    def test_no_history_exam_returns_empty(self):
        """未选历史考试时结果为空"""
        response = self.client.get(reverse("scores:analysis"), {"exam_id": str(self.exam2.pk)})
        self.assertEqual(response.context["rank_change_students"], [])

    def test_no_threshold_returns_empty(self):
        """未设阈值时结果为空（即使选了历史考试）"""
        response = self._analysis()
        self.assertEqual(response.context["rank_change_students"], [])


class StudentDetailChartTests(TestCase):
    """学生详情页历次考试成绩折线图数据"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="chart", password="pass")
        self.client.force_login(self.user)
        self.cls = SchoolClass.objects.create(created_by=self.user, name="高一(3)班", is_current=True)
        self.sem = Semester.objects.create(
            school_class=self.cls, academic_year="2026-2027", semester_type="first", is_current=True,
        )
        self.student = Student.objects.create(
            school_class=self.cls, student_id="2026000000000000001", name="张三", gender="male",
        )
        self.student2 = Student.objects.create(
            school_class=self.cls, student_id="2026000000000000002", name="李四", gender="male",
        )
        self.subj_yw = Subject.objects.create(name="语文")
        self.subj_sx = Subject.objects.create(name="数学")
        self.exam1 = Exam.objects.create(school_class=self.cls, semester=self.sem, name="月考一", date="2026-09-10")
        self.exam2 = Exam.objects.create(school_class=self.cls, semester=self.sem, name="月考二", date="2026-10-10")
        for exam in (self.exam1, self.exam2):
            ExamSubject.objects.create(exam=exam, subject=self.subj_yw, full_score=100)
            ExamSubject.objects.create(exam=exam, subject=self.subj_sx, full_score=100)

    def _add_score(self, exam, student, subject, value):
        es = ExamSubject.objects.get(exam=exam, subject=subject)
        Score.objects.create(exam=exam, exam_subject=es, student=student, score=value, status="normal")

    def _detail(self):
        return self.client.get(reverse("students:detail", args=[self.student.pk]))

    def test_exam_chart_has_two_exams_and_totals(self):
        """两次考试的总分数据正确"""
        self._add_score(self.exam1, self.student, self.subj_yw, 90)
        self._add_score(self.exam1, self.student, self.subj_sx, 80)
        self._add_score(self.exam2, self.student, self.subj_yw, 95)
        self._add_score(self.exam2, self.student, self.subj_sx, 85)
        # 其他学生也录入，确保排名计算
        self._add_score(self.exam1, self.student2, self.subj_yw, 50)
        self._add_score(self.exam1, self.student2, self.subj_sx, 50)
        self._add_score(self.exam2, self.student2, self.subj_yw, 40)
        self._add_score(self.exam2, self.student2, self.subj_sx, 40)

        response = self._detail()
        chart = response.context["exam_chart"]
        self.assertEqual(len(chart["labels"]), 2)
        self.assertEqual(chart["totals"], [170.0, 180.0])
        # 张三总分领先 → 排名第1
        self.assertEqual(chart["total_ranks"], [1, 1])
        self.assertIn("语文", chart["all_subjects"])
        self.assertIn("数学", chart["all_subjects"])
        self.assertEqual(chart["subjects"]["语文"]["scores"], [90.0, 95.0])

    def test_exam_chart_skips_exam_without_scores(self):
        """学生未参加的考试应跳过"""
        self._add_score(self.exam1, self.student, self.subj_yw, 90)
        self._add_score(self.exam1, self.student, self.subj_sx, 80)
        # 月考二该学生无成绩
        response = self._detail()
        chart = response.context["exam_chart"]
        self.assertEqual(len(chart["labels"]), 1)
        self.assertEqual(chart["totals"], [170.0])

    def test_detail_page_renders_chart(self):
        """详情页包含 canvas 元素"""
        self._add_score(self.exam1, self.student, self.subj_yw, 90)
        self._add_score(self.exam1, self.student, self.subj_sx, 80)
        self._add_score(self.exam2, self.student, self.subj_yw, 95)
        self._add_score(self.exam2, self.student, self.subj_sx, 85)
        response = self._detail()
        self.assertContains(response, "totalScoreChart")
        self.assertContains(response, "subjectScoreChart")
        self.assertContains(response, "subjectRankChart")
