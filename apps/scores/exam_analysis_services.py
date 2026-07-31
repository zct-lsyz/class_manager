"""试卷原卷与小分表的本地解析及匿名 AI 分析。"""
import io
import json
import re
from pathlib import Path

from django.conf import settings
from openpyxl import Workbook, load_workbook

from apps.scores.ai_services import AIAnalysisError, call_chat_completion, get_effective_api_key


PAPER_EXTENSIONS = {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png"}
SCORE_EXTENSIONS = {".xlsx"}
IGNORED_SCORE_COLUMNS = {"总分", "合计", "排名", "班级", "年级排名", "班级排名", "座号"}


class ExamAnalysisParseError(ValueError):
    pass


def validate_uploads(paper_file, score_file):
    paper_suffix = Path(paper_file.name).suffix.lower()
    score_suffix = Path(score_file.name).suffix.lower()
    if paper_suffix not in PAPER_EXTENSIONS:
        raise ExamAnalysisParseError("试卷仅支持 PDF、DOCX、TXT、JPG、JPEG、PNG。")
    if score_suffix not in SCORE_EXTENSIONS:
        raise ExamAnalysisParseError("小分表仅支持 XLSX。")
    max_size = settings.AI_EXAM_MAX_FILE_SIZE
    if paper_file.size > max_size or score_file.size > max_size:
        raise ExamAnalysisParseError(f"单个文件不能超过 {max_size // 1024 // 1024} MB。")


def extract_paper_text(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        text = _extract_pdf_text(path)
    elif suffix == ".docx":
        text = _extract_docx_text(path)
    elif suffix == ".txt":
        text = _extract_txt_text(path)
    elif suffix in {".jpg", ".jpeg", ".png"}:
        text = _ocr_image(path)
    else:
        raise ExamAnalysisParseError("不支持的试卷文件类型。")
    text = _normalize_text(text)
    if len(text) < 50:
        raise ExamAnalysisParseError("未能从原卷中识别出足够文字，请检查文件清晰度或 OCR 语言包。")
    return text[:settings.AI_EXAM_MAX_TEXT_CHARS]


def _extract_pdf_text(path):
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if len(reader.pages) > settings.AI_EXAM_MAX_PAGES:
        raise ExamAnalysisParseError(f"试卷 PDF 不能超过 {settings.AI_EXAM_MAX_PAGES} 页。")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if len(text.strip()) >= 200:
        return text

    import fitz
    from PIL import Image
    import pytesseract

    document = fitz.open(str(path))
    pages = []
    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            pages.append(pytesseract.image_to_string(image, lang=settings.AI_EXAM_OCR_LANG))
    finally:
        document.close()
    return "\n".join(pages)


def _extract_docx_text(path):
    from docx import Document

    document = Document(str(path))
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _extract_txt_text(path):
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExamAnalysisParseError("TXT 文件编码无法识别，请使用 UTF-8。")


def _ocr_image(path):
    from PIL import Image
    import pytesseract

    return pytesseract.image_to_string(Image.open(path), lang=settings.AI_EXAM_OCR_LANG)


def _normalize_text(text):
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line)


def _as_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _as_number(value, label):
    if value is None or _as_text(value) in {"", "-", "--", "—", "缺考"}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ExamAnalysisParseError(f"{label} 必须是数字。")


def _parse_question_header(value):
    text = _as_text(value)
    match = re.match(r"^(.+?)(?:[|｜]\s*(\d+(?:\.\d+)?)|[（(]\s*满分\s*(\d+(?:\.\d+)?)\s*[）)])$", text)
    if match:
        return match.group(1).strip(), float(match.group(2) or match.group(3))
    return text, None


def _find_header_row(sheet, required_names):
    for row_index in range(1, min(sheet.max_row, 10) + 1):
        values = {_as_text(cell.value) for cell in sheet[row_index]}
        if values.intersection(required_names):
            return row_index
    return None


def _read_question_metadata(workbook):
    if "题目" not in workbook.sheetnames:
        return {}
    sheet = workbook["题目"]
    header_row = _find_header_row(sheet, {"题号"})
    if not header_row:
        return {}
    headers = {_as_text(cell.value): cell.column for cell in sheet[header_row]}
    metadata = {}
    for row_index in range(header_row + 1, sheet.max_row + 1):
        label = _as_text(sheet.cell(row_index, headers["题号"]).value)
        if not label:
            continue
        full_score = None
        if headers.get("满分"):
            full_score = _as_number(sheet.cell(row_index, headers["满分"]).value, f"题目表第 {row_index} 行满分")
        knowledge = _as_text(sheet.cell(row_index, headers["知识点"]).value) if headers.get("知识点") else ""
        metadata[label] = {
            "question_type": _as_text(sheet.cell(row_index, headers["题型"]).value) if headers.get("题型") else "",
            "knowledge_points": [item.strip() for item in re.split(r"[、,，;；/]", knowledge) if item.strip()],
            "full_score": full_score,
        }
    return metadata


def parse_score_sheet(file_path, current_class):
    """解析小分表，仅返回逐题匿名聚合，不返回姓名或学号。"""
    from apps.students.models import Student

    workbook = load_workbook(file_path, data_only=True, read_only=False)
    sheet = workbook["小分表"] if "小分表" in workbook.sheetnames else workbook.active
    header_row = _find_header_row(sheet, {"学号", "姓名"})
    if not header_row:
        raise ExamAnalysisParseError("小分表前 10 行中未找到“学号”或“姓名”表头。")

    headers = {cell.column: _as_text(cell.value) for cell in sheet[header_row]}
    id_column = next((column for column, name in headers.items() if name == "学号"), None)
    name_column = next((column for column, name in headers.items() if name == "姓名"), None)
    question_columns = []
    metadata = _read_question_metadata(workbook)
    for column, header in headers.items():
        if not header or column in {id_column, name_column} or header in IGNORED_SCORE_COLUMNS:
            continue
        label, header_full_score = _parse_question_header(header)
        item_metadata = metadata.get(label, {})
        question_columns.append({
            "column": column,
            "label": label,
            "full_score": item_metadata.get("full_score") or header_full_score,
            "question_type": item_metadata.get("question_type", ""),
            "knowledge_points": item_metadata.get("knowledge_points", []),
            "scores": [],
        })
    if not question_columns:
        raise ExamAnalysisParseError("未找到题目得分列；请使用“题号|满分”格式，例如“1|5”。")

    students = Student.objects.filter(school_class=current_class, is_deleted=False)
    by_id = {student.student_id.strip(): student.pk for student in students if student.student_id}
    name_counts = {}
    name_pks = {}
    for student in students:
        name_counts[student.name] = name_counts.get(student.name, 0) + 1
        name_pks[student.name] = student.pk
    by_name = {name: name_pks[name] for name, count in name_counts.items() if count == 1}

    matched_students = set()
    unmatched_rows = 0
    errors = []
    for row_index in range(header_row + 1, sheet.max_row + 1):
        student_id = _as_text(sheet.cell(row_index, id_column).value) if id_column else ""
        student_name = _as_text(sheet.cell(row_index, name_column).value) if name_column else ""
        if not student_id and not student_name:
            continue
        student_pk = by_id.get(student_id) or by_name.get(student_name)
        if not student_pk:
            unmatched_rows += 1
            continue
        matched_students.add(student_pk)
        for question in question_columns:
            try:
                score = _as_number(
                    sheet.cell(row_index, question["column"]).value,
                    f"小分表第 {row_index} 行“{question['label']}”",
                )
            except ExamAnalysisParseError as exc:
                errors.append(str(exc))
                continue
            if score is None:
                continue
            if score < 0:
                errors.append(f"小分表第 {row_index} 行“{question['label']}”不能为负数。")
                continue
            if question["full_score"] is not None and score > question["full_score"]:
                errors.append(
                    f"小分表第 {row_index} 行“{question['label']}”得分 {score} 超过满分 {question['full_score']}。"
                )
                continue
            question["scores"].append(score)
    if errors:
        suffix = f"；另有 {len(errors) - 10} 处错误" if len(errors) > 10 else ""
        raise ExamAnalysisParseError("；".join(errors[:10]) + suffix)
    if not matched_students:
        raise ExamAnalysisParseError("小分表中没有学生能与当前班级花名册匹配，请检查学号或姓名。")

    warnings = []
    if unmatched_rows:
        warnings.append(f"有 {unmatched_rows} 行未匹配当前班级，已跳过。")
    summaries = []
    for order, question in enumerate(question_columns, 1):
        scores = question.pop("scores")
        if not scores:
            warnings.append(f"题目“{question['label']}”没有有效得分，已跳过。")
            continue
        full_score = question["full_score"]
        if full_score is None:
            full_score = max(scores)
            warnings.append(f"题目“{question['label']}”未填写满分，暂按最高得分 {full_score:g} 推断。")
        if full_score <= 0:
            raise ExamAnalysisParseError(f"题目“{question['label']}”满分必须大于 0。")
        average = sum(scores) / len(scores)
        summaries.append({
            "sort_order": order,
            "question_label": question["label"],
            "question_type": question["question_type"],
            "knowledge_points": question["knowledge_points"],
            "full_score": round(full_score, 2),
            "student_count": len(scores),
            "average_score": round(average, 2),
            "score_rate": round(average / full_score, 4),
            "zero_rate": round(sum(1 for score in scores if score == 0) / len(scores), 4),
            "full_rate": round(sum(1 for score in scores if score == full_score) / len(scores), 4),
        })
    if not summaries:
        raise ExamAnalysisParseError("小分表中没有可分析的有效题目得分。")
    return summaries, warnings


def _extract_json_response(content):
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise AIAnalysisError("AI 未返回可解析的 JSON 分析结果。")
        try:
            result = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise AIAnalysisError(f"AI 分析结果 JSON 格式错误：{exc}")
    if not isinstance(result, dict) or not isinstance(result.get("questions", []), list):
        raise AIAnalysisError("AI 分析结果缺少 questions 数组。")
    return result


def generate_exam_analysis(config, paper_text, question_summaries, subject_name=""):
    """向外部 AI 仅发送试题文字和匿名逐题汇总。"""
    from apps.scores.ai_prompts import DEFAULT_PROMPTS
    subject_prompt = (config.prompts or {}).get(subject_name) or DEFAULT_PROMPTS.get(subject_name, "")
    system_prompt = (
        f"你是一名严谨的{subject_name or '学科'}教学诊断专家。请结合试卷题型、题目内容和匿名逐题得分统计，"
        "识别班级主要薄弱知识点。不得推断学生身份，不得编造试卷中不存在的知识点。"
    )
    output_schema = {
        "overall_summary": "班级整体薄弱情况摘要",
        "questions": [{
            "question_label": "必须与输入题号完全一致",
            "question_type": "题型",
            "knowledge_points": ["知识点"],
            "weakness_level": "high/medium/low",
            "analysis": "结合得分率说明薄弱原因",
            "recommendation": "可执行的教学或复习建议",
        }],
    }
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            "请只返回严格 JSON，不要使用 Markdown。必须覆盖输入中的每一道题。\n"
            f"科目专属分析要求：{subject_prompt}\n"
            f"输出结构：{json.dumps(output_schema, ensure_ascii=False)}\n\n"
            f"试卷文字：\n{paper_text[:settings.AI_EXAM_MAX_TEXT_CHARS]}\n\n"
            f"匿名逐题统计：\n{json.dumps(question_summaries, ensure_ascii=False, indent=2)}"
        )},
    ]
    content, duration = call_chat_completion(
        config.base_url, get_effective_api_key(config), config.model_name,
        messages, config.temperature, timeout=180,
    )
    return _extract_json_response(content), duration


def build_score_template_bytes():
    workbook = Workbook()
    score_sheet = workbook.active
    score_sheet.title = "小分表"
    score_sheet.append(["学号", "姓名", "1|5", "2|10", "3|8"])
    score_sheet.append(["示例学号", "示例学生（下载后删除本行）", 5, 7, 4])
    question_sheet = workbook.create_sheet("题目")
    question_sheet.append(["题号", "题型", "知识点", "满分"])
    question_sheet.append(["1", "选择题", "示例知识点（下载后删除本行）", 5])
    question_sheet.append(["2", "填空题", "", 10])
    question_sheet.append(["3", "解答题", "", 8])
    note_sheet = workbook.create_sheet("填写说明")
    note_sheet.append(["说明"])
    note_sheet.append(["小分表题目列推荐写成“题号|满分”，如“1|5”；题目表中的满分优先级更高。"])
    note_sheet.append(["学号或姓名至少填写一项，并确保能与当前班级花名册匹配。"])
    note_sheet.append(["题型和知识点可留空，系统会结合原卷由 AI 识别；人工填写通常更准确。"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
