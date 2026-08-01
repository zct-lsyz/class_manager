"""成绩分析服务：统计计算、优生筛选、外部班级导入与对比。"""
import statistics

from django.db import transaction
from django.utils import timezone

from apps.scores.models import ExamTotal, ExternalClass, ExternalScore, ExternalTotal


def compute_score_stats(scores, full_score):
    """对一组成绩（含位次字段）计算完整统计量。

    参数:
        scores: 可迭代的 Score 或 ExternalScore，含 score/rank/grade_rank/city_rank
        full_score: 科目满分（用于及格率/优秀率/分数段）
    """
    values = [float(s.score) for s in scores if getattr(s, "score", None) is not None]
    n = len(values)
    stats = {
        "count": n,
        "avg": round(statistics.mean(values), 1) if values else 0,
        "median": statistics.median(values) if values else None,
        "variance": round(statistics.pvariance(values), 2) if len(values) > 1 else 0,
        "stddev": round(statistics.pstdev(values), 2) if len(values) > 1 else 0,
        "max": max(values) if values else None,
        "min": min(values) if values else None,
    }
    if full_score and n:
        stats["pass_rate"] = round(
            sum(1 for v in values if v >= full_score * 0.6) / n * 100, 1
        )
        stats["excellent_rate"] = round(
            sum(1 for v in values if v >= full_score * 0.85) / n * 100, 1
        )
    else:
        stats["pass_rate"] = 0
        stats["excellent_rate"] = 0

    # 位次：最高位次 = 数值最小（名次靠前）；最低位次 = 数值最大
    stats["max_class_rank"] = min((s.rank for s in scores if getattr(s, "rank", None)), default=None)
    stats["min_class_rank"] = max((s.rank for s in scores if getattr(s, "rank", None)), default=None)
    stats["max_grade_rank"] = min((s.grade_rank for s in scores if getattr(s, "grade_rank", None)), default=None)
    stats["min_grade_rank"] = max((s.grade_rank for s in scores if getattr(s, "grade_rank", None)), default=None)
    stats["max_city_rank"] = min((s.city_rank for s in scores if getattr(s, "city_rank", None)), default=None)
    stats["min_city_rank"] = max((s.city_rank for s in scores if getattr(s, "city_rank", None)), default=None)

    # 分数段分布
    bands = {"0-59%": 0, "60-69%": 0, "70-79%": 0, "80-89%": 0, "90-100%": 0}
    for v in values:
        ratio = v / full_score if full_score else 0
        if ratio < 0.6:
            bands["0-59%"] += 1
        elif ratio < 0.7:
            bands["60-69%"] += 1
        elif ratio < 0.8:
            bands["70-79%"] += 1
        elif ratio < 0.9:
            bands["80-89%"] += 1
        else:
            bands["90-100%"] += 1
    stats["bands"] = bands
    return stats


def is_top_student(score, criteria):
    """判断某条成绩是否满足优生条件。

    criteria: dict，含 score_threshold / class_rank_threshold / grade_rank_threshold /
              city_rank_threshold / combine_mode（"any" 或 "all"）
    任一条件留空（None/0）则忽略该条件。
    """
    score_val = getattr(score, "score", None)
    rank = getattr(score, "rank", None)
    grade_rank = getattr(score, "grade_rank", None)
    city_rank = getattr(score, "city_rank", None)

    conds = {}
    threshold = criteria.get("score_threshold")
    if threshold:
        conds["score"] = score_val is not None and float(score_val) >= float(threshold)
    threshold = criteria.get("class_rank_threshold")
    if threshold:
        conds["class_rank"] = rank is not None and rank <= int(threshold)
    threshold = criteria.get("grade_rank_threshold")
    if threshold:
        conds["grade_rank"] = grade_rank is not None and grade_rank <= int(threshold)
    threshold = criteria.get("city_rank_threshold")
    if threshold:
        conds["city_rank"] = city_rank is not None and city_rank <= int(threshold)

    if not conds:
        return True  # 未设置任何条件则不做筛选
    if criteria.get("combine_mode") == "all":
        return all(conds.values())
    return any(conds.values())


def apply_criteria(scores, criteria):
    """按优生条件筛选成绩，返回筛选后的列表。"""
    return [s for s in scores if is_top_student(s, criteria)]


@transaction.atomic
def import_external_scores(uploaded, current_class, exam, class_name, school_name, exam_subjects):
    """导入外部班级成绩。

    Excel 格式：第一行表头为 学生标识 + 每科目 4 列（成绩/班名次/级名次/市名次）。
    返回 (external_class, 导入条数)。
    """
    from openpyxl import load_workbook
    from io import BytesIO

    workbook = load_workbook(BytesIO(uploaded.read()), data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ValueError("文件为空")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    subject_by_name = {es.subject.name: es for es in exam_subjects}

    # 解析列：主科目列为科目名本身，附带 班名次/级名次/市名次 列
    column_map = {}  # column_index -> (exam_subject, field)
    for idx, header in enumerate(headers):
        if header in subject_by_name:
            column_map[idx] = (subject_by_name[header], "score")
        elif header.endswith("班名次") and header[:-3] in subject_by_name:
            column_map[idx] = (subject_by_name[header[:-3]], "class_rank")
        elif header.endswith("级名次") and header[:-3] in subject_by_name:
            column_map[idx] = (subject_by_name[header[:-3]], "grade_rank")
        elif header.endswith("市名次") and header[:-3] in subject_by_name:
            column_map[idx] = (subject_by_name[header[:-3]], "city_rank")

    # 总分列：总分/总分班名次/总分级排名/总分市排名（均可缺失）
    total_cols = {}  # column_index -> field_name
    for idx, header in enumerate(headers):
        if header == "总分":
            total_cols[idx] = "total_score"
        elif header == "总分班名次":
            total_cols[idx] = "class_rank"
        elif header in ("总分级排名", "总分级名次"):
            total_cols[idx] = "grade_rank"
        elif header == "总分市排名":
            total_cols[idx] = "city_rank"

    if not any(field == "score" for _, field in column_map.values()):
        raise ValueError("未找到与考试科目匹配的成绩列，请使用下载的模板填写。")

    external_class, _ = ExternalClass.objects.get_or_create(
        school_class=current_class,
        name=class_name.strip() or "外部班级",
        defaults={"school_name": (school_name or "").strip()},
    )

    created = 0
    for row in rows[1:]:
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        label = str(row[0]).strip() if row and row[0] is not None else ""
        for idx, (es, field) in column_map.items():
            raw = row[idx] if idx < len(row) else None
            value = None
            if raw not in (None, ""):
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    value = None
            if field == "score" and value is None:
                continue
            ExternalScore.objects.update_or_create(
                external_class=external_class,
                exam=exam,
                exam_subject=es,
                student_label=label,
                defaults={field: value},
            )
            created += 1

        # 总分列（可选）：解析总分及三种排名并写入 ExternalTotal
        if total_cols:
            total_defaults = {}
            for idx, field in total_cols.items():
                raw = row[idx] if idx < len(row) else None
                if raw in (None, ""):
                    continue
                try:
                    total_defaults[field] = float(raw) if field == "total_score" else int(float(raw))
                except (TypeError, ValueError):
                    continue
            if "total_score" in total_defaults:
                ExternalTotal.objects.update_or_create(
                    external_class=external_class,
                    exam=exam,
                    student_label=label,
                    defaults=total_defaults,
                )
                created += 1
    if created == 0:
        raise ValueError("未能从文件中解析出任何成绩记录。")
    return external_class, created


def _total_stats_for(total_values, full_score):
    """对一组成绩总分（含三种排名）计算统计量，输出与 compute_score_stats 兼容的结构。

    total_values: 可迭代的 dict，含 total_score/class_rank/grade_rank/city_rank
    """
    from types import SimpleNamespace

    objs = [
        SimpleNamespace(
            score=v.get("total_score"),
            rank=v.get("class_rank"),
            grade_rank=v.get("grade_rank"),
            city_rank=v.get("city_rank"),
        )
        for v in total_values
        if v.get("total_score") is not None
    ]
    return compute_score_stats(objs, full_score)


def build_comparison_data(exam, exam_subjects, current_class, criteria=None):
    """构建多班对比数据。

    返回:
        class_list: [{id, name, label}] 含本班 + 外部班级
        chart_data: 每个指标的 {metric: {class_id: value}}
        comparison_table: 每科目 × 每班级的统计（末尾含「总分」行）
    """
    own_scores_by_subject = {}
    for es in exam_subjects:
        scores = list(es.scores.filter(is_deleted=False, status="normal", score__isnull=False))
        own_scores_by_subject[es.id] = scores

    external_classes = ExternalClass.objects.filter(school_class=current_class)
    external_scores_by_subject = {}
    for ec in external_classes:
        for es in exam_subjects:
            scores = list(ExternalScore.objects.filter(
                external_class=ec, exam=exam, exam_subject=es, score__isnull=False,
            ))
            external_scores_by_subject[(ec.id, es.id)] = scores

    # 总分对比数据（ExamTotal / ExternalTotal，缺失时留空）
    own_totals = [
        {
            "total_score": float(et.total_score),
            "class_rank": et.class_rank,
            "grade_rank": et.grade_rank,
            "city_rank": et.city_rank,
        }
        for et in ExamTotal.objects.filter(exam=exam)
    ]
    ext_totals = {}
    for ec in external_classes:
        ext_totals[ec.id] = [
            {
                "total_score": float(et.total_score),
                "class_rank": et.class_rank,
                "grade_rank": et.grade_rank,
                "city_rank": et.city_rank,
            }
            for et in ExternalTotal.objects.filter(external_class=ec, exam=exam)
        ]

    comparison_table = []
    chart_data = {}
    metrics = [
        "avg", "variance", "max", "min",
        "max_class_rank", "min_class_rank",
        "max_grade_rank", "min_grade_rank",
        "max_city_rank", "min_city_rank",
    ]

    for es in exam_subjects:
        row = {"subject": es.subject.name, "full_score": es.full_score, "classes": {}}
        own = own_scores_by_subject[es.id]
        if criteria:
            own = apply_criteria(own, criteria)
        own_stats = compute_score_stats(own, es.full_score)
        row["classes"]["own"] = own_stats
        for ec in external_classes:
            ext = external_scores_by_subject.get((ec.id, es.id), [])
            if criteria:
                ext = apply_criteria(ext, criteria)
            ext_stats = compute_score_stats(ext, es.full_score)
            row["classes"][f"ext_{ec.pk}"] = ext_stats
        comparison_table.append(row)

        for metric in metrics:
            chart_data.setdefault(metric, {})[es.subject.name] = {
                "own": own_stats.get(metric),
                **{
                    f"ext_{ec.pk}": row["classes"].get(f"ext_{ec.pk}", {}).get(metric)
                    for ec in external_classes
                },
            }

    # 总分行
    total_full_score = exam.total_score or sum(es.full_score for es in exam_subjects) or 0
    total_row = {"subject": "总分", "full_score": total_full_score, "classes": {}}
    total_row["classes"]["own"] = _total_stats_for(own_totals, None)
    for ec in external_classes:
        total_row["classes"][f"ext_{ec.pk}"] = _total_stats_for(ext_totals.get(ec.id, []), None)
    comparison_table.append(total_row)

    for metric in metrics:
        chart_data.setdefault(metric, {})["总分"] = {
            "own": total_row["classes"]["own"].get(metric),
            **{
                f"ext_{ec.pk}": total_row["classes"][f"ext_{ec.pk}"].get(metric)
                for ec in external_classes
            },
        }

    return external_classes, comparison_table, chart_data
