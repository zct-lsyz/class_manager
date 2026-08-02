"""成绩分析导出：Excel（openpyxl）+ PDF（PyMuPDF + Pillow 图表）。"""
import io
import os
import tempfile

from django.db.models import Sum

from apps.students.models import Student
from apps.scores.models import Exam, ExamSubject, Score, GradeLine


def compute_analysis_data(current_class, exam):
    """计算成绩分析核心数据（供 Excel/PDF 导出复用）。"""
    if not exam:
        return None
    exam_subjects = list(ExamSubject.objects.filter(exam=exam).select_related("subject"))
    analysis_data = {}
    for es in exam_subjects:
        scores = list(Score.objects.filter(
            exam_subject=es, is_deleted=False, status="normal", score__isnull=False,
        ))
        analysis_data[es.subject.name] = {
            "full_score": es.full_score,
            "avg": round(sum(float(s.score) for s in scores) / len(scores), 1) if scores else 0,
            "count": len(scores),
            "max": max((float(s.score) for s in scores), default=None),
            "min": min((float(s.score) for s in scores), default=None),
            "pass_rate": round(sum(1 for s in scores if s.score >= es.full_score * 0.6) / len(scores) * 100, 1) if scores else 0,
            "excellent_rate": round(sum(1 for s in scores if s.score >= es.full_score * 0.85) / len(scores) * 100, 1) if scores else 0,
        }

    # 总分统计
    from apps.scores.views import _get_or_compute_total_ranks
    total_data = _get_or_compute_total_ranks(exam)
    totals = [d["total_score"] for d in total_data.values() if d["total_score"] is not None]

    # 班级总成绩表
    students = list(Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("sort_order", "student_id"))
    class_total_table = []
    for student in students:
        total = 0.0
        has_any = False
        subjects = {}
        for es in exam_subjects:
            score_obj = Score.objects.filter(
                exam_subject=es, student=student, is_deleted=False,
            ).first()
            if score_obj and score_obj.status == "normal" and score_obj.score is not None:
                has_any = True
                total += float(score_obj.score)
                subjects[es.subject.name] = float(score_obj.score)
        if not has_any:
            continue
        student_total = total_data.get(student.pk, {})
        class_total_table.append({
            "student": student,
            "total_score": student_total.get("total_score") if student_total.get("total_score") is not None else round(total, 1),
            "rank": student_total.get("class_rank"),
            "total_grade_rank": student_total.get("grade_rank"),
            "total_city_rank": student_total.get("city_rank"),
            "subjects": subjects,
        })
    class_total_table.sort(key=lambda x: -(x["total_score"] or 0))
    if not any(r["rank"] is None for r in class_total_table):
        pass  # 已用官方排名
    else:
        for i, row in enumerate(class_total_table, 1):
            if row["rank"] is None:
                row["rank"] = i

    return {
        "exam": exam,
        "exam_subjects": exam_subjects,
        "analysis_data": analysis_data,
        "class_total_table": class_total_table,
        "total_count": len(totals),
        "total_avg": round(sum(totals) / len(totals), 1) if totals else 0,
        "total_max": max(totals) if totals else None,
    }


# ==================== Excel 导出 ====================

def export_analysis_excel(current_class, exam):
    """导出班级成绩分析 Excel（统计 + 学生总成绩 + AI）。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

    data = compute_analysis_data(current_class, exam)
    wb = Workbook()
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", start_color="1A73E8")
    header_font = Font(bold=True, color="FFFFFF")
    center = Alignment(horizontal="center", vertical="center")

    def style_header(ws):
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border

    # Sheet 1: 整体统计
    ws = wb.active
    ws.title = "整体统计"
    ws.append(["科目", "满分", "人数", "平均分", "最高分", "最低分", "及格率%", "优秀率%"])
    style_header(ws)
    for name, d in data["analysis_data"].items():
        ws.append([name, d["full_score"], d["count"], d["avg"], d["max"] or "", d["min"] or "", d["pass_rate"], d["excellent_rate"]])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
    for col, w in zip("ABCDEFGH", [12, 8, 8, 10, 10, 10, 10, 10]):
        ws.column_dimensions[col].width = w

    # Sheet 2: 学生总成绩
    ws2 = wb.create_sheet("学生总成绩")
    headers = ["排名", "姓名", "总分", "总分级排名", "总分市排名"] + [es.subject.name for es in data["exam_subjects"]]
    ws2.append(headers)
    style_header(ws2)
    for row in data["class_total_table"]:
        values = [row["rank"], row["student"].name, row["total_score"], row["total_grade_rank"] or "", row["total_city_rank"] or ""]
        values += [row["subjects"].get(es.subject.name, "") for es in data["exam_subjects"]]
        ws2.append(values)
    for row in ws2.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
    ws2.column_dimensions["A"].width = 6
    ws2.column_dimensions["B"].width = 12
    ws2.column_dimensions["C"].width = 8
    for col_idx in range(1, len(headers) + 1):
        ws2.column_dimensions[chr(64 + col_idx)].width = 10

    # Sheet 3: AI 分析
    from apps.scores.ai_models import AIAnalysisRecord
    latest = AIAnalysisRecord.objects.filter(
        exam=exam, success=True, analysis_type__in=["class", "subject"],
    ).order_by("-created_at").first()
    if latest:
        ws3 = wb.create_sheet("AI分析")
        ws3.append([latest.created_at.strftime("%Y-%m-%d %H:%M"), latest.get_analysis_type_display()])
        ws3.append([latest.result])
        ws3.column_dimensions["A"].width = 100

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue(), f"{exam.name}_成绩分析.xlsx"


# ==================== 多班对比导出 ====================

def export_comparison_excel(current_class, exam):
    """导出多班对比 Excel（科目 × 班级统计 + 总分行）。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from apps.scores.analysis_services import build_comparison_data

    external_classes, comparison_table, _chart = build_comparison_data(
        exam, list(ExamSubject.objects.filter(exam=exam).select_related("subject")), current_class,
    )
    wb = Workbook()
    ws = wb.active
    ws.title = "多班对比"
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", start_color="1A73E8")
    header_font = Font(bold=True, color="FFFFFF")
    center = Alignment(horizontal="center", vertical="center")

    classes = [("own", "本班")] + [(f"ext_{ec.pk}", ec.name) for ec in external_classes]
    headers = ["科目", "满分"]
    for _key, name in classes:
        headers += [f"{name} 人数", f"{name} 均分", f"{name} 方差", f"{name} 最高", f"{name} 最低"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = border

    for row in comparison_table:
        line = [row["subject"], row["full_score"]]
        for key, _name in classes:
            stats = row["classes"].get(key, {})
            line += [stats.get("count", ""), stats.get("avg", ""), stats.get("variance", ""), stats.get("max", ""), stats.get("min", "")]
        ws.append(line)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 8
    for col in range(3, len(headers) + 1):
        ws.column_dimensions[chr(64 + col)].width = 12

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue(), f"{exam.name}_多班对比.xlsx"


# ==================== 个人分析导出 ====================

def export_student_excel(student):
    """导出学生历次成绩 Excel（历史 + 积分概览）。"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from apps.scores.models import Score, ExamSubject, Exam

    records = Score.objects.filter(
        student=student, exam__is_deleted=False, is_deleted=False,
    ).select_related("exam", "exam_subject__subject").order_by("exam__date")

    history_map = {}
    for record in records:
        item = history_map.setdefault(record.exam_id, {
            "exam": record.exam, "subjects": [], "total": 0.0, "full_score": 0,
        })
        item["subjects"].append(record)
        if record.status == "normal" and record.score is not None:
            item["total"] += float(record.score)
            item["full_score"] += record.exam_subject.full_score

    wb = Workbook()
    ws = wb.active
    ws.title = "历次成绩"
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", start_color="1A73E8")
    header_font = Font(bold=True, color="FFFFFF")

    # 科目集合
    subjects = sorted({r.exam_subject.subject.name for r in records})
    # 每科：分数 + 班名次 + 级名次 + 市名次（与上传数据完备性一致）
    headers = ["考试", "日期"]
    for s in subjects:
        headers += [s, f"{s}班名次", f"{s}级名次", f"{s}市名次"]
    headers += ["总分", "得分率%"]
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = border

    for item in history_map.values():
        info_by_subj = {}
        for r in item["subjects"]:
            info_by_subj[r.exam_subject.subject.name] = r
        line = [item["exam"].name, item["exam"].date.strftime("%Y-%m-%d")]
        for s in subjects:
            r = info_by_subj.get(s)
            if r and r.score is not None:
                line += [
                    float(r.score),
                    r.rank if r.rank is not None else "",
                    r.grade_rank if r.grade_rank is not None else "",
                    r.city_rank if r.city_rank is not None else "",
                ]
            else:
                line += ["", "", "", ""]
        rate = item["total"] / item["full_score"] * 100 if item["full_score"] else 0
        line += [round(item["total"], 1), round(rate, 1)]
        ws.append(line)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 12
    for col in range(3, len(headers) + 1):
        ws.column_dimensions[chr(64 + col)].width = 10

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue(), f"{student.name}_成绩分析.xlsx"


def export_student_pdf(student):
    """生成学生个人历次成绩 PDF（各科+总分折线图 + 历史表）。"""
    import fitz
    from apps.scores.models import Score

    records = list(Score.objects.filter(
        student=student, exam__is_deleted=False, is_deleted=False,
    ).select_related("exam", "exam_subject__subject").order_by("exam__date"))

    # 按考试组织
    history_map = {}
    for record in records:
        item = history_map.setdefault(record.exam_id, {
            "exam": record.exam, "subjects": [], "total": 0.0, "full_score": 0,
        })
        item["subjects"].append(record)
        if record.status == "normal" and record.score is not None:
            item["total"] += float(record.score)
            item["full_score"] += record.exam_subject.full_score

    exam_items = [history_map[k] for k in sorted(history_map.keys(),
                  key=lambda eid: history_map[eid]["exam"].date)]
    if not exam_items:
        return None, None

    exam_labels = [item["exam"].date.strftime("%m-%d") for item in exam_items]
    subjects = sorted({r.exam_subject.subject.name for r in records})

    # 构建序列
    series = {"总分": [round(item["total"], 1) for item in exam_items]}
    for s in subjects:
        vals = []
        for item in exam_items:
            rec = next((r for r in item["subjects"] if r.exam_subject.subject.name == s and r.score is not None), None)
            vals.append(float(rec.score) if rec else None)
        series[s] = vals

    chart_png = _chart_student_trends(exam_labels, series)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    page.insert_text((36, y), f"{student.name} 历次成绩分析", fontsize=16, fontname=CJK_FONT, color=(0.1, 0.2, 0.4))
    y += 12
    page.insert_text((36, y), f"共 {len(exam_items)} 次考试", fontsize=11, fontname=CJK_FONT)
    y += 30

    if chart_png:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(chart_png)
        tmp.close()
        img_w = 523
        img_h = int(img_w * 380 / 820)
        page.insert_text((36, y), "各科与总分趋势", fontsize=13, fontname=CJK_FONT)
        y += 8
        page.insert_image(fitz.Rect(36, y, 36 + img_w, y + img_h), filename=tmp.name)
        os.unlink(tmp.name)
        y += img_h + 14

    # 历史成绩表
    if y > 600:
        page = doc.new_page(width=595, height=842)
        y = 40
    page.insert_text((36, y), "历次成绩明细", fontsize=13, fontname=CJK_FONT)
    y += 8
    headers = ["考试", "日期"] + subjects + ["总分", "得分率%"]
    col_widths = [90, 50] + [45] * len(subjects) + [50, 50]
    rows = []
    for item in exam_items:
        info = {r.exam_subject.subject.name: r for r in item["subjects"]}
        line = [item["exam"].name, item["exam"].date.strftime("%Y-%m-%d")]
        for s in subjects:
            r = info.get(s)
            line.append(float(r.score) if r and r.score is not None else "")
        rate = item["total"] / item["full_score"] * 100 if item["full_score"] else 0
        line += [round(item["total"], 1), round(rate, 1)]
        rows.append(line)
    _write_pdf_table(page, y, headers, rows, col_widths, font_size=8)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue(), f"{student.name}_成绩分析.pdf"


# ==================== PDF 导出（PyMuPDF + Pillow） ====================

def _chart_student_trends(exam_labels, series):
    """生成学生历次成绩折线图 PNG（各科 + 总分，多线）。"""
    from PIL import Image, ImageDraw, ImageFont
    names = [n for n, vals in series.items() if any(v is not None for v in vals)]
    if not names or not exam_labels:
        return None
    W, H = 820, 380
    margin_l, margin_b, margin_t, margin_r = 56, 44, 30, 30
    plot_w = W - margin_l - margin_r
    plot_h = H - margin_t - margin_b
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    cjk_font_path = _find_cjk_font()
    try:
        font = ImageFont.truetype(cjk_font_path, 14) if cjk_font_path else ImageFont.load_default()
        font_small = ImageFont.truetype(cjk_font_path, 11) if cjk_font_path else font
    except Exception:
        font = font_small = ImageFont.load_default()

    # 数值范围
    all_vals = [v for vals in series.values() for v in vals if v is not None]
    if not all_vals:
        return None
    lo, hi = min(all_vals), max(all_vals)
    if hi == lo:
        hi = lo + 10
    pad = (hi - lo) * 0.1
    lo -= pad
    hi += pad

    def x_of(i):
        if len(exam_labels) == 1:
            return margin_l + plot_w / 2
        return margin_l + plot_w * i / (len(exam_labels) - 1)

    def y_of(v):
        return margin_t + plot_h - plot_h * (v - lo) / (hi - lo)

    # 网格 + Y 刻度
    for i in range(0, 6):
        val = lo + (hi - lo) * i / 5
        y = y_of(val)
        draw.line([(margin_l, y), (W - margin_r, y)], fill="#eeeeee")
        draw.text((4, y - 7), f"{val:.0f}", fill="gray", font=font_small)
    # X 刻度
    for i, label in enumerate(exam_labels):
        draw.text((x_of(i), margin_t + plot_h + 8), str(label)[:6], fill="#333", font=font_small, anchor="ma")

    colors = ["#1a73e8", "#dc3545", "#28a745", "#f57c00", "#7c3aed", "#00acc1", "#e91e63", "#5e35b1", "#8d6e63", "#c0ca33"]
    legend_y = margin_t
    for idx, (name, vals) in enumerate(series.items()):
        if not any(v is not None for v in vals):
            continue
        color = colors[idx % len(colors)]
        points = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            points.append((x_of(i), y_of(v)))
        if len(points) == 1:
            draw.ellipse([points[0][0] - 3, points[0][1] - 3, points[0][0] + 3, points[0][1] + 3], fill=color)
        elif len(points) >= 2:
            draw.line(points, fill=color, width=2)
            for p in points:
                draw.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=color)
        # 图例
        draw.rectangle([margin_l + idx * 95, legend_y, margin_l + idx * 95 + 14, legend_y + 10], fill=color)
        draw.text((margin_l + idx * 95 + 18, legend_y - 3), name, fill="#333", font=font_small)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _find_cjk_font():
    """查找系统可用的中文字体文件路径。"""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
        r"C:\Windows\Fonts\simhei.ttf",   # 黑体
        r"C:\Windows\Fonts\simsun.ttc",   # 宋体
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _chart_avg_bar(analysis_data):
    """生成各科均分柱状图 PNG（Pillow）。"""
    from PIL import Image, ImageDraw, ImageFont
    subjects = list(analysis_data.keys())
    avgs = [analysis_data[s]["avg"] for s in subjects]
    if not subjects:
        return None
    W, H = 760, 340
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    margin = 60
    max_val = max(avgs) * 1.2 or 100
    plot_w = W - margin * 2
    plot_h = H - margin * 2
    bar_w = plot_w / len(subjects) * 0.6
    cjk_font_path = _find_cjk_font()
    try:
        if cjk_font_path:
            font = ImageFont.truetype(cjk_font_path, 16)
            font_small = ImageFont.truetype(cjk_font_path, 13)
        else:
            raise OSError("no cjk font")
    except Exception:
        font = font_small = ImageFont.load_default()

    # 网格线 + 数值
    for i in range(0, 6):
        y = margin + plot_h - plot_h * i / 5
        val = max_val * i / 5
        draw.line([(margin, y), (W - margin, y)], fill="#eeeeee")
        draw.text((5, y - 6), f"{val:.0f}", fill="gray", font=font_small)

    for idx, (subj, avg) in enumerate(zip(subjects, avgs)):
        x0 = margin + idx * (plot_w / len(subjects)) + (plot_w / len(subjects) - bar_w) / 2
        h = plot_h * (avg / max_val) if avg else 0
        draw.rectangle([x0, margin + plot_h - h, x0 + bar_w, margin + plot_h], fill="#1a73e8")
        draw.text((x0, margin + plot_h - h - 20), f"{avg:.1f}", fill="#1a73e8", font=font_small)
        # 科目名
        label = subj if len(subj) <= 3 else subj[:3]
        draw.text((x0 + bar_w / 2, margin + plot_h + 8), label, fill="#333", font=font_small, anchor="ma")
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


CJK_FONT = "china-s"  # PyMuPDF 内置简体中文字体


def _write_pdf_table(page, y, headers, rows, col_widths, font_size=9):
    """在 PyMuPDF 页面绘制表格（中文字体），返回结束 y 坐标。"""
    from pymupdf import Rect
    doc = page.parent
    page_height = page.rect.height
    left = 36
    row_h = 20 if font_size > 9 else 16
    header_h = 24
    table_w = sum(col_widths)

    def draw_header(p, start_y):
        for i, h in enumerate(headers):
            r = Rect(left + sum(col_widths[:i]), start_y, left + sum(col_widths[:i + 1]), start_y + header_h)
            p.draw_rect(r, color=(0.1, 0.45, 0.91), fill=(0.1, 0.45, 0.91))
            p.insert_textbox(r + (1, 3, -1, -3), str(h), fontsize=font_size, fontname=CJK_FONT, color=(1, 1, 1), align=1)

    # 表头
    draw_header(page, y)
    y += header_h

    # 数据行（跨页时切新页）
    for row in rows:
        if y + row_h > page_height - 40:
            page = doc.new_page(width=page.rect.width, height=page.rect.height)
            draw_header(page, 36)
            y = 36 + header_h
        for i, val in enumerate(row):
            r = Rect(left + sum(col_widths[:i]), y, left + sum(col_widths[:i + 1]), y + row_h)
            page.draw_rect(r, color=(0.8, 0.8, 0.8))
            text = str(val) if val is not None else ""
            page.insert_textbox(r + (2, 2, -2, -2), text, fontsize=font_size, fontname=CJK_FONT, color=(0.2, 0.2, 0.2), align=1)
        y += row_h
    return y


def export_analysis_pdf(current_class, exam):
    """生成班级成绩分析 PDF（含柱状图与表格）。"""
    import fitz
    data = compute_analysis_data(current_class, exam)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 纵向

    y = 50
    page.insert_text((36, y), f"{exam.name} 班级成绩分析", fontsize=16, fontname="china-s", color=(0.1, 0.2, 0.4))
    y += 12
    page.insert_text((36, y), f"共 {data['total_count']} 人参与 | 总分平均 {data['total_avg']} | 最高总分 {data['total_max']}", fontsize=11)
    y += 26

    # 各科均分柱状图
    chart_png = _chart_avg_bar(data["analysis_data"])
    if chart_png:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(chart_png)
        tmp.close()
        img_w = 523
        img_h = int(img_w * 340 / 760)
        page.insert_text((36, y), "各科平均分", fontsize=13, fontname="china-s")
        y += 8
        page.insert_image(fitz.Rect(36, y, 36 + img_w, y + img_h), filename=tmp.name)
        os.unlink(tmp.name)
        y += img_h + 12

    # 整体统计表
    page.insert_text((36, y), "整体统计", fontsize=13, fontname="china-s")
    y += 8
    headers = ["科目", "人数", "平均分", "最高", "最低", "及格率%", "优秀率%"]
    col_widths = [70, 55, 75, 75, 75, 90, 90]
    rows = [[name, d["count"], d["avg"], d["max"] or "", d["min"] or "", d["pass_rate"], d["excellent_rate"]]
            for name, d in data["analysis_data"].items()]
    y = _write_pdf_table(page, y, headers, rows, col_widths) + 14

    # 班级总成绩表
    if y > 740:
        page = doc.new_page(width=595, height=842)
        y = 40
    page.insert_text((36, y), "班级总成绩（前 30 名）", fontsize=13, fontname="china-s")
    y += 8
    subjects = [es.subject.name for es in data["exam_subjects"]]
    headers = ["排名", "姓名", "总分"] + subjects
    col_widths = [40, 60, 55] + [50] * len(subjects)
    rows = []
    for row in data["class_total_table"][:30]:
        values = [row["rank"], row["student"].name, row["total_score"]]
        values += [row["subjects"].get(s, "") for s in subjects]
        rows.append(values)
    _write_pdf_table(page, y, headers, rows, col_widths, font_size=7)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue(), f"{exam.name}_成绩分析.pdf"
