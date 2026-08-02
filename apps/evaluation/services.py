"""评选计算引擎：指标提取 → 归一化 → 加权求和 → 排名。"""
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

from apps.evaluation.models import EvaluationResult
from apps.students.models import Student


# 可选指标定义
INDICATORS = [
    {"key": "score_rank", "label": "成绩排名", "lower_better": True},
    {"key": "score_avg", "label": "总分", "lower_better": False},
    {"key": "score_progress", "label": "成绩进步", "lower_better": False},
    {"key": "points", "label": "积分", "lower_better": False},
    {"key": "reward_count", "label": "奖励次数", "lower_better": False},
    {"key": "discipline_count", "label": "违纪次数", "lower_better": True},
    {"key": "attendance", "label": "出勤率", "lower_better": False},
    {"key": "homework", "label": "作业完成率", "lower_better": False},
]

INDICATOR_LABELS = {item["key"]: item["label"] for item in INDICATORS}


def _latest_exam(school_class):
    from apps.scores.models import Exam
    return Exam.objects.filter(
        school_class=school_class, is_deleted=False,
    ).order_by("-date", "-id").first()


def _compute_indicator(key, school_class, semester, students):
    """计算某指标对全班学生的原始值。返回 {student_id: value}。"""
    sids = list(students.values_list("pk", flat=True))
    values = {sid: 0 for sid in sids}

    if key == "score_rank" or key == "score_avg":
        exam = _latest_exam(school_class)
        if exam:
            from apps.scores.views import _get_or_compute_total_ranks
            data = _get_or_compute_total_ranks(exam)
            for sid in sids:
                row = data.get(sid)
                if not row:
                    continue
                if key == "score_rank":
                    values[sid] = row["class_rank"] if row["class_rank"] is not None else None
                else:
                    values[sid] = row["total_score"] if row["total_score"] is not None else None

    elif key == "score_progress":
        from apps.scores.models import Exam
        exams = list(Exam.objects.filter(
            school_class=school_class, is_deleted=False,
        ).order_by("-date", "-id")[:2])
        if len(exams) >= 2:
            from apps.scores.views import _get_or_compute_total_ranks
            current = _get_or_compute_total_ranks(exams[0])
            previous = _get_or_compute_total_ranks(exams[1])
            for sid in sids:
                cur = current.get(sid, {}).get("total_score")
                prev = previous.get(sid, {}).get("total_score")
                if cur is not None and prev is not None:
                    values[sid] = float(cur) - float(prev)

    elif key == "points":
        from apps.rewards.models import PointRecord
        rows = PointRecord.objects.filter(
            school_class=school_class, is_deleted=False, student_id__in=sids,
        ).values("student_id").annotate(total=Sum("points"))
        for row in rows:
            values[row["student_id"]] = row["total"] or 0

    elif key == "reward_count":
        from apps.rewards.models import RewardRecord
        rows = RewardRecord.objects.filter(
            school_class=school_class, is_deleted=False,
            record_type="reward", student_id__in=sids,
        ).values("student_id").annotate(cnt=Count("id"))
        for row in rows:
            values[row["student_id"]] = row["cnt"]

    elif key == "discipline_count":
        from apps.discipline.models import ClassroomDisciplineRecord, DormDisciplineRecord
        for model in (ClassroomDisciplineRecord, DormDisciplineRecord):
            rows = model.objects.filter(
                school_class=school_class, is_deleted=False, student_id__in=sids,
            ).values("student_id").annotate(cnt=Count("id"))
            for row in rows:
                values[row["student_id"]] = values.get(row["student_id"], 0) + row["cnt"]

    elif key == "attendance":
        from apps.attendance.models import AttendanceRecord
        rows = AttendanceRecord.objects.filter(
            school_class=school_class, student_id__in=sids,
        ).values("student_id").annotate(
            total=Count("id"), normal=Count("id", filter=Q(status="normal")),
        )
        for row in rows:
            values[row["student_id"]] = row["normal"] / row["total"] * 100 if row["total"] else 0

    elif key == "homework":
        from apps.homework.models import HomeworkRecord
        positive = {"submitted", "excellent", "corrected"}
        rows = HomeworkRecord.objects.filter(
            task__school_class=school_class, student_id__in=sids,
        ).values("student_id").annotate(
            total=Count("id"),
            done=Count("id", filter=Q(status__in=positive)),
        )
        for row in rows:
            values[row["student_id"]] = row["done"] / row["total"] * 100 if row["total"] else 0

    # 清理 None → 0
    return {sid: (v if v is not None else 0) for sid, v in values.items()}


def _normalize(values, lower_better=False):
    """min-max 归一化到 0-100。lower_better=True 时反转（值越小分越高）。"""
    vals = [v for v in values.values() if v is not None]
    if not vals:
        return {sid: 0 for sid in values}
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return {sid: 50.0 for sid in values}
    result = {}
    for sid, v in values.items():
        if v is None:
            result[sid] = 0.0
            continue
        ratio = (v - lo) / (hi - lo)
        if lower_better:
            ratio = 1 - ratio
        result[sid] = round(ratio * 100, 1)
    return result


def _make_period_label(cycle):
    today = timezone.localdate()
    if cycle == "weekly":
        # 所在周的周一
        monday = today - timezone.timedelta(days=today.weekday())
        return f"{monday:%Y}年第{monday.isocalendar()[1]}周"
    if cycle == "semester":
        return f"{today:%Y}年{((today.month - 1) // 6) + 1}学期"
    return f"{today:%Y}年{today.month}月"


def calculate_evaluation(project, semester=None):
    """按项目规则计算全班学生排名，生成 EvaluationResult 记录。

    返回 (results, period_label, student_count)。
    """
    school_class = project.school_class
    students = Student.objects.filter(
        school_class=school_class, is_deleted=False,
    )
    rules = project.rules() or []
    if not rules:
        return [], _make_period_label(project.cycle), 0

    # 汇总各指标原始值（lower_better 从指标定义读取，而非规则配置）
    raw_by_key = {}
    for indicator in rules:
        key = indicator.get("key")
        if not key:
            continue
        lower_better = next(
            (i.get("lower_better", False) for i in INDICATORS if i["key"] == key),
            False,
        )
        raw = _compute_indicator(key, school_class, semester, students)
        raw_by_key[key] = {"raw": raw, "lower_better": lower_better}

    # 加权求和
    scores = {sid: 0.0 for sid in raw_by_key[next(iter(raw_by_key))]["raw"]} if raw_by_key else {}
    details = {sid: {} for sid in scores}
    for indicator in rules:
        key = indicator.get("key")
        if key not in raw_by_key:
            continue
        weight = float(indicator.get("weight", 0) or 0)
        info = raw_by_key[key]
        normalized = _normalize(info["raw"], info["lower_better"])
        label = indicator.get("label") or INDICATOR_LABELS.get(key, key)
        for sid in scores:
            val = normalized.get(sid, 0)
            scores[sid] += val * weight
            details[sid][key] = {
                "label": label,
                "raw": info["raw"].get(sid),
                "score": val,
                "weight": weight,
            }

    # 排序并写入
    period_label = _make_period_label(project.cycle)
    ranked = sorted(scores.items(), key=lambda x: (-x[1], details[x[0]].get("score_rank", {}).get("raw") or 9999))
    results = []
    with transaction.atomic():
        EvaluationResult.objects.filter(project=project, period_label=period_label).delete()
        for rank, (sid, total) in enumerate(ranked, 1):
            result = EvaluationResult.objects.create(
                project=project, student_id=sid, period_label=period_label,
                total_score=round(total, 1), rank=rank,
                score_details=details[sid],
            )
            results.append(result)
    return results, period_label, len(ranked)
