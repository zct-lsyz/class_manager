"""原卷小分表分析服务测试。"""
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from openpyxl import Workbook

from apps.classes.models import SchoolClass
from apps.scores.exam_analysis_services import ExamAnalysisParseError, generate_exam_analysis, parse_score_sheet
from apps.students.models import Student


class ExamScoreSheetTests(TestCase):

    def setUp(self):
        self.school_class = SchoolClass.objects.create(name="高一(1)班", is_current=True)
        Student.objects.create(
            school_class=self.school_class, student_id="2026001", name="张三", gender="male",
        )
        Student.objects.create(
            school_class=self.school_class, student_id="2026002", name="李四", gender="female",
        )

    def _save_workbook(self, score_rows):
        workbook = Workbook()
        score_sheet = workbook.active
        score_sheet.title = "小分表"
        score_sheet.append(["学号", "姓名", "1|5", "2|10"])
        for row in score_rows:
            score_sheet.append(row)
        question_sheet = workbook.create_sheet("题目")
        question_sheet.append(["题号", "题型", "知识点", "满分"])
        question_sheet.append(["1", "选择题", "集合", 5])
        question_sheet.append(["2", "解答题", "函数、方程", 10])
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "scores.xlsx"
        workbook.save(path)
        return temp_dir, path

    def test_parser_returns_anonymous_question_aggregates(self):
        temp_dir, path = self._save_workbook([
            ["2026001", "张三", 5, 8],
            ["2026002", "李四", 3, 6],
        ])
        try:
            summaries, warnings = parse_score_sheet(path, self.school_class)
        finally:
            temp_dir.cleanup()
        self.assertEqual(warnings, [])
        self.assertEqual(summaries[0]["average_score"], 4)
        self.assertEqual(summaries[0]["score_rate"], 0.8)
        serialized = json.dumps(summaries, ensure_ascii=False)
        self.assertNotIn("张三", serialized)
        self.assertNotIn("李四", serialized)
        self.assertNotIn("2026001", serialized)

    def test_parser_rejects_score_above_full_score(self):
        temp_dir, path = self._save_workbook([["2026001", "张三", 6, 8]])
        try:
            with self.assertRaises(ExamAnalysisParseError):
                parse_score_sheet(path, self.school_class)
        finally:
            temp_dir.cleanup()

    @patch("apps.scores.exam_analysis_services.call_chat_completion")
    def test_selected_subject_uses_subject_prompt(self, mocked_chat):
        mocked_chat.return_value = (json.dumps({"overall_summary": "", "questions": []}), 10)
        config = SimpleNamespace(
            prompts={"语文": "语文专用提示词"}, base_url="https://example.com",
            model_name="test-model", temperature=0.2,
        )

        generate_exam_analysis(config, "试卷文本", [], "语文")

        messages = mocked_chat.call_args.args[3]
        self.assertIn("语文专用提示词", messages[1]["content"])
