"""
标准 Excel 模板生成
包含：学生花名册、家长联系方式、成绩导入模板
"""
from io import BytesIO

from django.http import HttpResponse

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from apps.classes.models import SchoolClass
from apps.students.models import Student


HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1A73E8", end_color="1A73E8", fill_type="solid")
NOTE_FONT = Font(name="微软雅黑", size=9, color="6C757D")
EXAMPLE_FONT = Font(name="微软雅黑", size=10, color="999999")
CENTER = Alignment(horizontal="center", vertical="center")
THIN_BORDER = Border(
    left=Side(style="thin", color="D0D0D0"),
    right=Side(style="thin", color="D0D0D0"),
    top=Side(style="thin", color="D0D0D0"),
    bottom=Side(style="thin", color="D0D0D0"),
)

REQUIRED_FILL = PatternFill(start_color="FFF3E0", end_color="FFF3E0", fill_type="solid")


def _write_sheet(ws, headers, examples, notes, col_widths, required_cols=None):
    """通用：写表头 + 示例行 + 填写说明"""
    required_cols = required_cols or []

    # 表头
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER
        cell.border = THIN_BORDER
        if col in required_cols:
            cell.fill = PatternFill(start_color="D32F2F", end_color="D32F2F", fill_type="solid")

    # 示例行（灰色）
    for r, row in enumerate(examples, 2):
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.font = EXAMPLE_FONT
            cell.border = THIN_BORDER

    # 填写说明
    note_start = len(examples) + 3
    for i, note in enumerate(notes):
        cell = ws.cell(row=note_start + i, column=1, value=note)
        cell.font = NOTE_FONT

    # 列宽
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A2"


def _build_response(wb, filename):
    buf = BytesIO()
    wb.save(buf)
    response = HttpResponse(
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def students_template():
    """学生花名册导入模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "学生花名册"

    headers = ["学号", "姓名", "性别", "出生日期", "身高(cm)", "视力",
               "座位需求", "职务", "宿舍", "床位", "联系人", "联系电话", "备注"]
    examples = [
        ["2026001", "张三", "男", "2010-03-15", 175, "左5.0 右4.8",
         "需前排座位", "班长", "1号楼 101", "01", "张先生", "13800138000", "示例行，请删除"],
        ["2026002", "李四", "女", "2010-07-22", 162, "",
         "", "", "", "", "", "", ""],
    ]
    notes = [
        "填写说明：",
        "1. 红色表头（学号、姓名、性别）为必填项；",
        "2. 「性别」只能填写：男 或 女；",
        "3. 「出生日期」格式：2010-03-15；",
        "4. 「联系电话」为11位手机号，将默认脱敏显示；",
        "5. 学号必须唯一，重复学号的行会被跳过；",
        "6. 身高填写整数（单位：厘米）；",
        "7. 导入前请先删除示例行。",
    ]
    _write_sheet(ws, headers, examples, notes, [14, 10, 8, 12, 10, 18, 16, 12, 16, 8, 12, 14, 20], required_cols=[1, 2, 3])
    return _build_response(wb, "students_import_template.xlsx")


def guardians_template():
    """家长联系方式导入模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "家长联系方式"

    headers = ["学号", "父亲姓名", "父亲电话", "母亲姓名", "母亲电话",
               "其他监护人", "主要联系人", "家庭地址", "备注"]
    examples = [
        ["2026001", "张建国", "13800138000", "王秀英", "13900139000",
         "", "father", "XX市XX区XX街道XX号", "示例行，请删除"],
        ["2026002", "李明", "", "赵丽", "13700137000",
         "", "mother", "", ""],
    ]
    notes = [
        "填写说明：",
        "1. 红色表头（学号）为必填项，且学号必须已存在于学生花名册；",
        "2. 「主要联系人」填写：father / mother / other；",
        "3. 每位学生只能有一条家长信息记录，已有记录的学生将被跳过；",
        "4. 导入前请先删除示例行。",
    ]
    _write_sheet(ws, headers, examples, notes, [14, 12, 14, 12, 14, 12, 12, 30, 20], required_cols=[1])
    return _build_response(wb, "guardians_import_template.xlsx")


def score_import_template(exam_subject=None):
    """成绩导入模板"""
    wb = Workbook()
    ws = wb.active
    ws.title = "成绩导入"

    headers = ["学号", "姓名", "成绩", "状态"]
    examples = [
        ["2026001", "张三", 85, "正常"],
        ["2026002", "李四", 92, "正常"],
        ["2026003", "王五", "", "缺考"],
    ]
    notes = [
        "填写说明：",
        "1. 「学号」必须与系统学生学号完全一致，未匹配行将被跳过并提示；",
        "2. 「成绩」填写数字，可保留1位小数；",
        "3. 「状态」可选：正常/缺考/缓考/免考/成绩无效/其他，留空默认为正常；",
        "4. 导入前请先删除示例行。",
    ]
    _write_sheet(ws, headers, examples, notes, [15, 12, 10, 12], required_cols=[1, 3])
    return _build_response(wb, "score_import_template.xlsx")


def sample_students_data_file():
    """生成一个包含当前学生数据的示例文件（导出模板预览用）"""
    wb = Workbook()
    ws = wb.active
    ws.title = "学生花名册"
    headers = ["学号", "姓名", "性别", "出生日期", "身高(cm)", "视力",
               "座位需求", "职务", "宿舍", "床位", "联系人", "联系电话", "备注"]
    _write_sheet(ws, headers, [], ["该文件为当前学生数据的导出预览"], [14, 10, 8, 12, 10, 18, 16, 12, 16, 8, 12, 14, 20])
    return _build_response(wb, "students_export_preview.xlsx")
