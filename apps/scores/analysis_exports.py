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
    from openpyxl.utils import get_column_letter
    for col_idx in range(1, len(headers) + 1):
        ws2.column_dimensions[get_column_letter(col_idx)].width = 10

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
    from openpyxl.utils import get_column_letter
    for col in range(3, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 12

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
    from openpyxl.utils import get_column_letter
    for col in range(3, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 10

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

    exam_labels = [item["exam"].date.strftime("%Y-%m-%d") for item in exam_items]
    subjects = sorted({r.exam_subject.subject.name for r in records})

    # 总分排名（每场考试的班级名次）
    from apps.scores.views import _get_or_compute_total_ranks
    total_ranks_by_exam = {exam.pk: _get_or_compute_total_ranks(exam) for exam in [item["exam"] for item in exam_items]}

    # 构建每项的 分数+排名 序列
    chart_specs = []
    total_scores = [round(item["total"], 1) for item in exam_items]
    total_ranks = [total_ranks_by_exam[item["exam"].pk].get(student.pk, {}).get("class_rank") for item in exam_items]
    chart_specs.append(("总分", total_scores, total_ranks))
    for s in subjects:
        scores, ranks = [], []
        for item in exam_items:
            rec = next((r for r in item["subjects"] if r.exam_subject.subject.name == s), None)
            scores.append(float(rec.score) if rec and rec.score is not None else None)
            display_rank = rec.grade_rank if rec and rec.grade_rank is not None else (rec.rank if rec else None)
            ranks.append(display_rank)
        chart_specs.append((s, scores, ranks))

    doc = fitz.open()
    page = doc.new_page(width=842, height=595)  # A4 横向
    fnt = _ensure_page_font(page)
    page.insert_text((30, 36), f"{student.name} 历次成绩分析", fontsize=18, fontname=fnt, color=(0.1, 0.2, 0.4))
    page.insert_text((30, 54), f"共 {len(exam_items)} 次考试 | 各科与总成绩的分数与排名趋势", fontsize=12, fontname=fnt)

    # 每张图 2 张/行排列
    chart_w, chart_h = 395, 200
    x_positions = [30, 30 + chart_w + 10]
    y = 64
    for idx, (title, scores, ranks) in enumerate(chart_specs):
        png = _chart_score_rank(exam_labels, scores, ranks, title)
        if not png:
            continue
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(png)
        tmp.close()
        cx = x_positions[idx % 2]
        if idx % 2 == 0 and idx > 0:
            y += chart_h + 6
        if y + chart_h > 575:
            page = doc.new_page(width=842, height=595)
            y = 40
        page.insert_image(fitz.Rect(cx, y, cx + chart_w, y + chart_h), filename=tmp.name)
        os.unlink(tmp.name)

    # 历史成绩表（新页）
    page = doc.new_page(width=842, height=595)
    fnt = _ensure_page_font(page)
    page.insert_text((30, 36), "历次成绩明细", fontsize=16, fontname=fnt)
    y = 46
    headers = ["考试", "日期"] + subjects + ["总分", "得分率%"]
    col_widths = [110, 70] + [52] * len(subjects) + [60, 60]
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
    _write_pdf_table(page, y, headers, rows, col_widths, font_size=10)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue(), f"{student.name}_成绩分析.pdf"


# ==================== PDF 导出（PyMuPDF + Pillow） ====================

def _chart_score_rank(exam_labels, scores, ranks, title):
    """生成单科/总成绩的双轴折线图 PNG（左轴分数，右轴排名反向）。"""
    from PIL import Image, ImageDraw, ImageFont
    if not exam_labels:
        return None
    SCALE = 2  # 提高清晰度
    W, H = 820 * SCALE, 360 * SCALE
    margin_l, margin_b, margin_t, margin_r = 60 * SCALE, 46 * SCALE, 40 * SCALE, 60 * SCALE
    plot_w = W - margin_l - margin_r
    plot_h = H - margin_t - margin_b
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    try:
        font_title = _chart_font(20 * SCALE) or ImageFont.load_default()
        font_small = _chart_font(13 * SCALE) or font_title
    except Exception:
        font_title = font_small = ImageFont.load_default()

    # 标题
    draw.text((W / 2, 14), title, fill="#1a237e", font=font_title, anchor="ma")

    score_vals = [v for v in scores if v is not None]
    rank_vals = [v for v in ranks if v is not None]

    # 分数轴范围
    s_lo, s_hi = 0, 100
    if score_vals:
        s_hi = max(score_vals) * 1.15 or 100
        s_lo = min(score_vals) * 0.85
        if s_lo < 0:
            s_lo = 0
    # 排名轴范围（反向：排名1在顶部）
    r_lo, r_hi = 1, 10
    if rank_vals:
        r_hi = max(rank_vals) * 1.3 or 10
        r_lo = 1

    def x_of(i):
        if len(exam_labels) == 1:
            return margin_l + plot_w / 2
        return margin_l + plot_w * i / (len(exam_labels) - 1)

    def y_score(v):
        return margin_t + plot_h - plot_h * (v - s_lo) / (s_hi - s_lo)

    def y_rank(v):
        # 排名越小（越好）越靠上
        return margin_t + plot_h * (v - r_lo) / (r_hi - r_lo)

    # 网格 + 分数左轴刻度
    for i in range(0, 6):
        val = s_lo + (s_hi - s_lo) * i / 5
        y = y_score(val)
        draw.line([(margin_l, y), (W - margin_r, y)], fill="#eeeeee")
        draw.text((4, y - 7), f"{val:.0f}", fill="gray", font=font_small)
    # 排名右轴刻度
    for i in range(0, 6):
        val = r_lo + (r_hi - r_lo) * i / 5
        y = y_rank(val)
        draw.line([(W - margin_r, y), (W - margin_r + 5, y)], fill="#cccccc")
        draw.text((W - margin_r + 8, y - 7), f"{val:.0f}", fill="gray", font=font_small)
    # X 刻度（标签为 %Y-%m-%d，取前 7 位显示年月，如 2026-06）
    for i, label in enumerate(exam_labels):
        draw.text((x_of(i), margin_t + plot_h + 8), str(label)[:7], fill="#333", font=font_small, anchor="ma")

    # 分数折线（蓝）
    s_points = [(x_of(i), y_score(v)) for i, v in enumerate(scores) if v is not None]
    if len(s_points) == 1:
        draw.ellipse([s_points[0][0]-4, s_points[0][1]-4, s_points[0][0]+4, s_points[0][1]+4], fill="#1a73e8")
    elif len(s_points) >= 2:
        draw.line(s_points, fill="#1a73e8", width=2)
        for p in s_points:
            draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill="#1a73e8")
    # 排名折线（红，虚线）
    r_points = [(x_of(i), y_rank(v)) for i, v in enumerate(ranks) if v is not None]
    if len(r_points) == 1:
        draw.ellipse([r_points[0][0]-4, r_points[0][1]-4, r_points[0][0]+4, r_points[0][1]+4], fill="#dc3545")
    elif len(r_points) >= 2:
        for j in range(len(r_points) - 1):
            draw.line([r_points[j], r_points[j+1]], fill="#dc3545", width=2)
        for p in r_points:
            draw.ellipse([p[0]-3, p[1]-3, p[0]+3, p[1]+3], fill="#dc3545")

    # 图例
    draw.rectangle([W/2 - 90, H - 24, W/2 - 70, H - 14], fill="#1a73e8")
    draw.text((W/2 - 64, H - 28), "分数", fill="#333", font=font_small)
    draw.rectangle([W/2 + 10, H - 24, W/2 + 30, H - 14], fill="#dc3545")
    draw.text((W/2 + 36, H - 28), "排名", fill="#333", font=font_small)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _find_cjk_font():
    """查找系统可用的中文字体文件路径（可用环境变量 CJK_FONT_PATH 指定）。"""
    candidates = [
        os.environ.get("CJK_FONT_PATH", ""),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
        r"C:\Windows\Fonts\simhei.ttf",   # 黑体
        r"C:\Windows\Fonts\simsun.ttc",   # 宋体
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _chart_font(size):
    """加载可渲染中文的 Pillow 字体（供图表使用）。

    优先使用系统 CJK 字体；找不到时提取 PyMuPDF 内置中文字体（china-s），
    保证在未安装系统字体的环境（如 Docker 精简镜像）中也能正常显示中文。
    全部失败返回 None（调用方回退 ImageFont.load_default）。
    """
    from PIL import ImageFont

    path = _find_cjk_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    try:
        import fitz
        font = fitz.Font("china-s")
        buf = getattr(font, "buffer", None)
        if buf:
            return ImageFont.truetype(io.BytesIO(buf), size)
    except Exception:
        pass
    return None


def _ensure_page_font(page):
    """在 PyMuPDF 页面注册真实中文字体（subset 只嵌入用到的字形，避免 PDF 过大）。

    返回该页使用的字体名。
    """
    font_path = _find_cjk_font()
    if font_path:
        try:
            page.insert_font(fontname="cjk", fontfile=font_path, subset=True)
            return "cjk"
        except Exception:
            pass
    return "china-s"


def _chart_avg_bar(analysis_data):
    """生成各科均分柱状图 PNG（Pillow）。"""
    from PIL import Image, ImageDraw, ImageFont
    subjects = list(analysis_data.keys())
    avgs = [analysis_data[s]["avg"] for s in subjects]
    if not subjects:
        return None
    SCALE = 2
    W, H = 760 * SCALE, 340 * SCALE
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    margin = 60 * SCALE
    max_val = max(avgs) * 1.2 or 100
    plot_w = W - margin * 2
    plot_h = H - margin * 2
    bar_w = plot_w / len(subjects) * 0.6
    try:
        font = _chart_font(18 * SCALE) or ImageFont.load_default()
        font_small = _chart_font(14 * SCALE) or font
    except Exception:
        font = font_small = ImageFont.load_default()

    # 网格线 + 数值
    for i in range(0, 6):
        y = margin + plot_h - plot_h * i / 5
        val = max_val * i / 5
        draw.line([(margin, y), (W - margin, y)], fill="#eeeeee")
        draw.text((5, y - 6 * SCALE), f"{val:.0f}", fill="gray", font=font_small)

    for idx, (subj, avg) in enumerate(zip(subjects, avgs)):
        x0 = margin + idx * (plot_w / len(subjects)) + (plot_w / len(subjects) - bar_w) / 2
        h = plot_h * (avg / max_val) if avg else 0
        draw.rectangle([x0, margin + plot_h - h, x0 + bar_w, margin + plot_h], fill="#1a73e8")
        draw.text((x0, margin + plot_h - h - 20 * SCALE), f"{avg:.1f}", fill="#1a73e8", font=font_small)
        # 科目名
        label = subj if len(subj) <= 3 else subj[:3]
        draw.text((x0 + bar_w / 2, margin + plot_h + 8 * SCALE), label, fill="#333", font=font_small, anchor="ma")
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


CJK_FONT = "china-s"  # PyMuPDF 内置简体中文字体


def _text_width(text, fs):
    """计算指定字体下文本宽度（真实 TTF 用 fitz.Font，回退到内置中文字体）。"""
    from pymupdf import Font, get_text_length
    font_path = _find_cjk_font()
    if font_path:
        try:
            return Font(fontfile=font_path).text_length(text, fontsize=fs)
        except Exception:
            pass
    return get_text_length(text, fontname="china-s", fontsize=fs)


def _write_pdf_table(page, y, headers, rows, col_widths, font_size=10):
    """在 PyMuPDF 页面绘制表格（真实中文字体，比例数字），返回结束 y 坐标。"""
    from pymupdf import Rect, Point
    doc = page.parent
    page_height = page.rect.height
    left = 36
    row_h = 22 if font_size > 9 else 18
    header_h = 26

    def _center_text(p, r, text, fs, color, fn):
        # 用 insert_text 居中绘制（不裁剪，避免单元格过小导致文字不显示）
        if not text:
            return
        tw = _text_width(text, fs)
        cx = (r.x0 + r.x1) / 2
        cy = (r.y0 + r.y1) / 2 + fs * 0.35
        p.insert_text(Point(cx - tw / 2, cy), text, fontsize=fs, fontname=fn, color=color)

    def draw_header(p, start_y, fn):
        for i, h in enumerate(headers):
            r = Rect(left + sum(col_widths[:i]), start_y, left + sum(col_widths[:i + 1]), start_y + header_h)
            p.draw_rect(r, color=(0.1, 0.45, 0.91), fill=(0.1, 0.45, 0.91))
            _center_text(p, r, str(h), font_size, (1, 1, 1), fn)

    fnt = _ensure_page_font(page)
    # 表头
    draw_header(page, y, fnt)
    y += header_h

    # 数据行（跨页时切新页）
    for row in rows:
        if y + row_h > page_height - 40:
            page = doc.new_page(width=page.rect.width, height=page.rect.height)
            fnt = _ensure_page_font(page)
            draw_header(page, 36, fnt)
            y = 36 + header_h
        for i, val in enumerate(row):
            r = Rect(left + sum(col_widths[:i]), y, left + sum(col_widths[:i + 1]), y + row_h)
            page.draw_rect(r, color=(0.8, 0.8, 0.8))
            text = str(val) if val is not None else ""
            _center_text(page, r, text, font_size, (0.2, 0.2, 0.2), fnt)
        y += row_h
    return y


def export_analysis_pdf(current_class, exam):
    """生成班级成绩分析 PDF（含柱状图与表格）。"""
    import fitz
    data = compute_analysis_data(current_class, exam)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4 纵向
    fnt = _ensure_page_font(page)

    y = 50
    page.insert_text((36, y), f"{exam.name} 班级成绩分析", fontsize=17, fontname=fnt, color=(0.1, 0.2, 0.4))
    y += 13
    page.insert_text((36, y), f"共 {data['total_count']} 人参与 | 总分平均 {data['total_avg']} | 最高总分 {data['total_max']}", fontsize=12, fontname=fnt)
    y += 28

    # 各科均分柱状图
    chart_png = _chart_avg_bar(data["analysis_data"])
    if chart_png:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(chart_png)
        tmp.close()
        img_w = 523
        img_h = int(img_w * 340 / 760)
        page.insert_text((36, y), "各科平均分", fontsize=14, fontname=fnt)
        y += 9
        page.insert_image(fitz.Rect(36, y, 36 + img_w, y + img_h), filename=tmp.name)
        os.unlink(tmp.name)
        y += img_h + 14

    # 整体统计表
    page.insert_text((36, y), "整体统计", fontsize=14, fontname=fnt)
    y += 9
    headers = ["科目", "人数", "平均分", "最高", "最低", "及格率%", "优秀率%"]
    col_widths = [70, 55, 75, 75, 75, 90, 90]
    rows = [[name, d["count"], d["avg"], d["max"] or "", d["min"] or "", d["pass_rate"], d["excellent_rate"]]
            for name, d in data["analysis_data"].items()]
    y = _write_pdf_table(page, y, headers, rows, col_widths) + 16

    # 班级总成绩表
    if y > 740:
        page = doc.new_page(width=595, height=842)
        fnt = _ensure_page_font(page)
        y = 40
    page.insert_text((36, y), "班级总成绩（前 30 名）", fontsize=14, fontname=fnt)
    y += 9
    subjects = [es.subject.name for es in data["exam_subjects"]]
    headers = ["排名", "姓名", "总分"] + subjects
    col_widths = [40, 60, 55] + [50] * len(subjects)
    rows = []
    for row in data["class_total_table"][:30]:
        values = [row["rank"], row["student"].name, row["total_score"]]
        values += [row["subjects"].get(s, "") for s in subjects]
        rows.append(values)
    _write_pdf_table(page, y, headers, rows, col_widths, font_size=9)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue(), f"{exam.name}_成绩分析.pdf"
