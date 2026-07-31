"""
通用导出服务
支持：Excel(.xlsx)、CSV、JSON、ZIP打包导出
"""
import csv
import hashlib
import io
import json
import os
import zipfile
from datetime import datetime

from django.http import HttpResponse
from django.utils import timezone

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter


# ---------- 样式常量 ----------
HEADER_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="1A73E8", end_color="1A73E8", fill_type="solid")
BODY_FONT = Font(name="微软雅黑", size=10)
THIN_BORDER = Border(
    left=Side(style="thin", color="D0D0D0"),
    right=Side(style="thin", color="D0D0D0"),
    top=Side(style="thin", color="D0D0D0"),
    bottom=Side(style="thin", color="D0D0D0"),
)
CENTER_ALIGN = Alignment(horizontal="center", vertical="center")


def export_to_excel(rows, headers, filename, sheet_name="数据"):
    """
    将数据导出为 Excel 文件（HttpResponse）
    rows: 列表，每项为一个列表，顺序与 headers 对应
    headers: 表头列表
    """
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:30]

    # 写表头
    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    # 写数据
    for row_idx, row in enumerate(rows, 2):
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER

    # 自适应列宽
    for col_idx in range(1, len(headers) + 1):
        max_len = len(str(headers[col_idx - 1]))
        for row_idx in range(2, min(len(rows) + 2, 200)):
            value = ws.cell(row=row_idx, column=col_idx).value
            if value is not None:
                max_len = max(max_len, len(str(value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 4, 40)

    # 冻结表头
    ws.freeze_panes = "A2"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


def export_to_csv(rows, headers, filename):
    """导出 CSV"""
    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def export_to_json(data, filename):
    """导出 JSON"""
    response = HttpResponse(
        json.dumps(data, ensure_ascii=False, indent=2, default=str),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def make_full_export_zip(module_files, filename_prefix, current_class=None):
    """
    全量导出打包 ZIP
    module_files: [(zip内路径, file内容bytes, 记录数), ...]
    """
    from apps.classes.models import SchoolClass, Semester

    current_class = current_class or SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(school_class=current_class, is_current=True).first() if current_class else None

    buf = io.BytesIO()
    manifest = {
        "export_time": timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": os.environ.get("APP_VERSION", "1.0.0"),
        "class_name": current_class.name if current_class else "",
        "semester": current_semester.get_display_name() if current_semester else "",
        "files": {},
    }

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content, record_count in module_files:
            zf.writestr(path, content)
            manifest["files"][path] = {
                "record_count": record_count,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }

        # README
        readme = (
            "班级教学管理平台 - 全量数据导出\n"
            f"导出时间：{manifest['export_time']}\n"
            f"班级：{manifest['class_name']}\n"
            f"学期：{manifest['semester']}\n"
            "说明：本包为可阅读的数据包，不等同于系统备份。\n"
        )
        zf.writestr("README.txt", readme)
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buf.seek(0)
    filename = f"{filename_prefix}_{timezone.now():%Y%m%d_%H%M%S}.zip"
    response = HttpResponse(buf.read(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def build_excel_bytes(rows, headers, sheet_name="数据"):
    """生成 Excel 文件 bytes（用于打包进 ZIP）"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:30]

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    for row_idx, row in enumerate(rows, 2):
        for col_idx, value in enumerate(row, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.font = BODY_FONT
            cell.border = THIN_BORDER

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def fmt(v, default="", empty="-"):
    """格式化值，空值显示 -"""
    if v is None or v == "":
        return default if default else empty
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return str(v)
