import json
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Avg, Max, Min, Count, Q, Sum
from django.utils import timezone
from django.db import transaction

from apps.scores.models import (
    Exam, ExamSubject, Score, SupportPlan, SupportFollowUp,
    ExternalClass, ExternalScore, ExternalTotal, ExamTotal, GradeLine,
)
from apps.scores.forms import ExamForm, ExamSubjectForm, ScoreForm, SupportPlanForm
from apps.scores.analysis_services import (
    compute_score_stats,
    apply_criteria,
    build_comparison_data,
    import_external_scores,
)
from apps.classes.subjects import Subject
from apps.classes.decorators import require_current_class
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.audit.services import soft_delete
from apps.audit.models import OperationLog
from apps.students.models import Student


WIDE_SCORE_COLUMNS = [
    # 语数英为原始分，优先匹配纯科目名列；"赋分"保留为旧格式兜底
    ("语文", ["语文", "语文赋分", "语文原始"], 150),
    ("数学", ["数学", "数学赋分", "数学原始"], 150),
    ("英语", ["英语", "英语赋分", "外语赋分", "英语原始", "外语原始", "外语"], 150),
    ("日语", ["日语赋分", "日语原始", "日语"], 150),
    ("物理", ["物理赋分", "物理原始", "物理"], 100),
    ("化学", ["化学赋分", "化学原始", "化学"], 100),
    ("生物", ["生物赋分", "生物原始", "生物"], 100),
    ("政治", ["政治赋分", "政治原始", "政治"], 100),
    ("历史", ["历史赋分", "历史原始", "历史"], 100),
    ("地理", ["地理赋分", "地理原始", "地理"], 100),
]

RANK_KEYWORDS = ("名次", "排名", "校名", "班名")


def _parse_rank(value):
    """解析名次值，空值或非法值返回 None。"""
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_int(value):
    """解析正整数，空值或非法值返回 None。"""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compute_total_ranks(exam):
    """计算某次考试全体学生的总分排名，返回 {student_id: rank}。

    排名规则：总分降序，相同总分名次并列（跳名次）。
    """
    totals = Score.objects.filter(
        exam=exam, status="normal", score__isnull=False, is_deleted=False,
    ).values("student_id").annotate(total=Sum("score")).order_by("-total")
    ranks = {}
    current_rank = 0
    prev_total = None
    for position, row in enumerate(totals, 1):
        if row["total"] != prev_total:
            current_rank = position
            prev_total = row["total"]
        ranks[row["student_id"]] = current_rank
    return ranks


def _get_or_compute_total_ranks(exam):
    """获取学生总分及三种排名（总分班名次/总分级排名/总分市排名）。

    优先使用已导入的 ExamTotal（官方总分与排名）；未导入的学生
    从分科成绩聚合计算总分与班级名次（grade_rank/city_rank 为 None）。

    返回 {student_id: {total_score, class_rank, grade_rank, city_rank}}
    """
    result = {
        et.student_id: {
            "total_score": float(et.total_score) if et.total_score is not None else None,
            "class_rank": et.class_rank,
            "grade_rank": et.grade_rank,
            "city_rank": et.city_rank,
        }
        for et in ExamTotal.objects.filter(exam=exam)
    }
    aggregated = Score.objects.filter(
        exam=exam, status="normal", score__isnull=False, is_deleted=False,
    ).values("student_id").annotate(total=Sum("score")).order_by("-total")
    current_rank = 0
    prev_total = None
    for position, row in enumerate(aggregated, 1):
        if row["total"] != prev_total:
            current_rank = position
            prev_total = row["total"]
        if row["student_id"] not in result:
            result[row["student_id"]] = {
                "total_score": float(row["total"]),
                "class_rank": current_rank,
                "grade_rank": None,
                "city_rank": None,
            }
    return result


def _wide_match_columns(header_map, subject_name, score_aliases):
    """灵活匹配某科目在表头中的各列（分数 + 三种名次）。

    匹配规则：
      - 分数列：优先精确命中别名（赋分 > 原始 > 科目名）；否则只要表头包含科目名即算匹配
      - 班名次：表头含「班名次」/「班名」，或含通用「名次/排名」
      - 级名次：表头含「级名次」/「级部名次」
      - 市名次：表头含「市名次」
    任一列缺失均允许（如某考试没有市名次、没有赋分）。

    返回 (score_header, class_rank_header, grade_rank_header, city_rank_header)，均可能为 None。
    """
    score_header = None
    class_rank_header = None
    grade_rank_header = None
    city_rank_header = None

    # 1. 分数列精确匹配（按优先级）
    for alias in score_aliases:
        if alias in header_map:
            score_header = alias
            break

    # 2. 遍历表头，识别该科目的名次列与分数兜底
    for header_text in header_map:
        if not header_text:
            continue
        if subject_name in ("英语", "外语"):
            belongs = ("外语" in header_text) or ("英语" in header_text)
        else:
            belongs = subject_name in header_text
        if not belongs:
            continue

        if any(kw in header_text for kw in RANK_KEYWORDS):
            if "班名次" in header_text or header_text.endswith("班名"):
                if class_rank_header is None:
                    class_rank_header = header_text
            elif "级名次" in header_text or "级部名次" in header_text:
                if grade_rank_header is None:
                    grade_rank_header = header_text
            elif "市名次" in header_text:
                if city_rank_header is None:
                    city_rank_header = header_text
            elif class_rank_header is None:
                # 通用「名次/排名」列默认视为班名次
                class_rank_header = header_text
            continue

        # 3. 分数列兜底：表头包含科目名且不是名次列
        if score_header is None:
            score_header = header_text

    return score_header, class_rank_header, grade_rank_header, city_rank_header


def _match_total_columns(header_map):
    """匹配宽表中「总分」相关列。

    匹配规则（表头 → 列索引）：
      - 「总分」：总分（不含名次关键词）
      - 「总分班名次」：总分班名次（含「总分」且含「班名次」/「班名」）
      - 「总分级名次」「总分级排名」「总分级部名次」：总分级排名
      - 「总分市名次」：总分市排名

    返回 (total_score_col, class_rank_col, grade_rank_col, city_rank_col)，均可能为 None。
    """
    total_score_col = None
    class_rank_col = None
    grade_rank_col = None
    city_rank_col = None

    for header_text in header_map:
        if not header_text:
            continue
        if "总分" not in header_text:
            continue
        if "班名次" in header_text or "班名" in header_text:
            if class_rank_col is None:
                class_rank_col = header_text
        elif "级名次" in header_text or "级排名" in header_text or "级部名次" in header_text:
            if grade_rank_col is None:
                grade_rank_col = header_text
        elif "市名次" in header_text or "市排名" in header_text:
            if city_rank_col is None:
                city_rank_col = header_text
        elif total_score_col is None:
            total_score_col = header_text

    return total_score_col, class_rank_col, grade_rank_col, city_rank_col


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


@login_required
def exam_list(request):
    """考试管理"""
    current_class = get_current_class(request.user)
    exams = Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []

    paginator = Paginator(exams, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "scores/exam_list.html", {"page_obj": page_obj})


@login_required
def exam_create(request):
    """新建考试"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    if not current_class:
        messages.error(request, "请先在班级与学期设置中指定当前班级。")
        return redirect("classes:settings")
    if not current_semester:
        # 尝试智能匹配：如果该班级只有一个未归档的学期，自动使用它
        semesters = Semester.objects.filter(
            school_class=current_class, is_archived=False,
        ).order_by("-academic_year", "-semester_type")
        if semesters.count() == 1:
            semesters.update(is_current=True)
            current_semester = semesters.first()
        else:
            messages.error(
                request,
                "当前班级没有指定「当前学期」。请在「班级与学期设置」中为该班级的学期勾选「设为当前学期」。",
            )
            return redirect("classes:settings")

    if request.method == "POST":
        form = ExamForm(request.POST)
        if form.is_valid():
            exam = form.save(commit=False)
            exam.school_class = current_class
            exam.semester = current_semester
            exam.save()
            messages.success(request, f"考试「{exam.name}」已创建。")
            return redirect("scores:exam_list")
    else:
        form = ExamForm()

    return render(request, "scores/exam_form.html", {"form": form})


@login_required
def exam_detail(request, pk):
    """考试详情：科目管理 + 发布状态"""
    current_class = get_current_class(request.user)
    exam = get_object_or_404(
        Exam.objects.select_related("semester"),
        pk=pk, school_class=current_class, is_deleted=False,
    )
    exam_subjects = ExamSubject.objects.filter(exam=exam).select_related("subject")

    # 统计各科已录入成绩数
    for es in exam_subjects:
        es.score_count = Score.objects.filter(exam_subject=es, is_deleted=False).count()

    # 未加入考试的科目（本用户 + 系统默认）
    added_subject_ids = exam_subjects.values_list("subject_id", flat=True)
    available_subjects = Subject.objects.filter(
        Q(created_by=request.user) | Q(created_by__isnull=True),
        is_active=True,
    ).exclude(id__in=added_subject_ids)

    # 发布/取消发布
    if request.method == "POST" and request.POST.get("toggle_publish"):
        exam.is_published = not exam.is_published
        exam.save()
        messages.success(request, f"考试已{'发布' if exam.is_published else '取消发布'}。")
        return redirect("scores:exam_detail", pk=exam.pk)

    return render(request, "scores/exam_detail.html", {
        "exam": exam,
        "exam_subjects": exam_subjects,
        "available_subjects": available_subjects,
    })


@login_required
def exam_delete(request, pk):
    current_class = get_current_class(request.user)
    exam = get_object_or_404(
        Exam, pk=pk, school_class=current_class, is_deleted=False,
    )
    if request.method == "POST":
        soft_delete(
            exam,
            user=request.user,
            module="scores",
            model_name="exam",
        )
        messages.info(request, "考试已移入回收站。")
    return redirect("scores:exam_list")


@login_required
def exam_subject_create(request, pk):
    """为考试添加科目"""
    current_class = get_current_class(request.user)
    exam = get_object_or_404(
        Exam, pk=pk, school_class=current_class, is_deleted=False,
    )
    if request.method == "POST":
        subject_id = request.POST.get("subject", "")
        full_score = request.POST.get("full_score", "100")
        if subject_id:
            try:
                full_score = int(full_score)
            except (ValueError, TypeError):
                full_score = 100
            if full_score <= 0:
                messages.error(request, "满分必须大于 0。")
                return redirect("scores:exam_detail", pk=exam.pk)
            subject = get_object_or_404(Subject, pk=subject_id)
            if ExamSubject.objects.filter(exam=exam, subject=subject).exists():
                messages.warning(request, f"科目「{subject.name}」已添加。")
            else:
                ExamSubject.objects.create(
                    exam=exam, subject=subject, full_score=full_score,
                )
                messages.success(request, f"科目「{subject.name}」（满分{full_score}）已添加。")
        else:
            messages.error(request, "请选择科目。")
    return redirect("scores:exam_detail", pk=exam.pk)


@login_required
def exam_subject_delete(request, pk):
    """删除考试科目"""
    current_class = get_current_class(request.user)
    es = get_object_or_404(
        ExamSubject, pk=pk, exam__school_class=current_class,
    )
    exam_pk = es.exam.pk
    if request.method == "POST":
        has_scores = Score.objects.filter(exam_subject=es, is_deleted=False).exists()
        if has_scores:
            messages.error(request, f"科目「{es.subject.name}」已有成绩记录，不能删除。可先删除对应成绩。")
        else:
            messages.info(request, f"科目「{es.subject.name}」已移除。")
            es.delete()
    return redirect("scores:exam_detail", pk=exam_pk)


@login_required
def score_entry(request):
    """成绩录入"""
    current_class = get_current_class(request.user)

    exam_id = request.GET.get("exam_id", "")
    subject_id = request.GET.get("subject_id", "")
    exam = None
    exam_subject = None
    scores = []

    if exam_id and not subject_id:
        exam = get_object_or_404(Exam, pk=exam_id, school_class=current_class, is_deleted=False)

    if exam_id and subject_id:
        exam = get_object_or_404(Exam, pk=exam_id, school_class=current_class, is_deleted=False)
        exam_subject = get_object_or_404(ExamSubject, pk=subject_id, exam=exam)
        existing_scores = {
            item.student_id: item for item in Score.objects.filter(
            exam_subject=exam_subject, is_deleted=False
            ).select_related("student")
        }
        scores = [
            existing_scores.get(student.pk) or Score(
                exam=exam, exam_subject=exam_subject, student=student, status="normal",
            )
            for student in Student.objects.filter(
                school_class=current_class, is_deleted=False,
            ).order_by("student_id")
        ]

    # 批量保存成绩（POST 提交 score_{student_id} 字段）
    if request.method == "POST" and exam_id and subject_id:
        exam = get_object_or_404(Exam, pk=exam_id, school_class=current_class, is_deleted=False)
        exam_subject = get_object_or_404(ExamSubject, pk=subject_id, exam=exam)

        saved_count = 0
        cleared_count = 0
        submissions = []
        errors = []
        valid_statuses = {key for key, _label in Score.STATUS_CHOICES}
        student_ids = set(Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).values_list("pk", flat=True))
        for key, value in request.POST.items():
            if not key.startswith("score_"):
                continue
            student_id = key.replace("score_", "")
            if not student_id.isdigit():
                continue
            student_pk = int(student_id)
            if student_pk not in student_ids:
                errors.append(f"学生记录 {student_id} 不属于当前班级。")
                continue

            # 状态字段
            status = request.POST.get(f"status_{student_id}", "normal")
            if status not in valid_statuses:
                errors.append(f"学生记录 {student_id} 的成绩状态无效。")
                continue
            score_val = value.strip() if value else ""
            if score_val == "":
                submissions.append((student_pk, None, status))
                continue

            try:
                score_num = float(score_val)
            except (ValueError, TypeError):
                errors.append(f"学生记录 {student_id} 的成绩格式无效。")
                continue

            if score_num < 0 or score_num > exam_subject.full_score:
                errors.append(f"学生记录 {student_id} 的成绩须在 0 至 {exam_subject.full_score} 之间。")
                continue
            submissions.append((student_pk, score_num, status))

        if errors:
            messages.error(request, "本次未保存：" + "；".join(errors[:10]))
            return redirect(f"{request.path}?exam_id={exam_id}&subject_id={subject_id}")

        with transaction.atomic():
            for student_pk, score_num, status in submissions:
                score_obj, created = Score.objects.get_or_create(
                    exam_subject=exam_subject, student_id=student_pk,
                    defaults={"exam": exam, "status": status, "score": score_num, "is_deleted": False},
                )
                was_scored = score_obj.score is not None
                score_obj.is_deleted = False
                score_obj.score = score_num
                score_obj.status = status
                score_obj.exam = exam
                score_obj.save()
                if score_num is None and was_scored:
                    cleared_count += 1
                elif score_num is not None:
                    saved_count += 1

            # 重新计算名次
            _update_ranks(exam_subject)

        from apps.audit.models import OperationLog
        OperationLog.objects.create(
            user=request.user, action="edit", module="scores",
            object_repr=f"{exam.name} - {exam_subject.subject.name}",
            detail=f"批量录入成绩：保存 {saved_count} 条，清空 {cleared_count} 条",
            ip_address=get_client_ip(request) if hasattr(request, 'META') else None,
            success=True,
        )
        messages.success(request, f"成绩已保存：录入 {saved_count} 条，清空 {cleared_count} 条。")
        return redirect(f"{request.path}?exam_id={exam_id}&subject_id={subject_id}")

    exams = Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []
    subjects = ExamSubject.objects.filter(exam_id=exam_id, exam__school_class=current_class, exam__is_deleted=False).select_related("subject") if exam_id else []

    context = {
        "exams": exams,
        "subjects": subjects,
        "exam": exam,
        "exam_subject": exam_subject,
        "scores": scores,
        "status_choices": Score.STATUS_CHOICES,
    }
    return render(request, "scores/score_entry.html", context)


def _update_ranks(exam_subject):
    """按成绩重新计算班级名次（缺考不计名次）"""
    scores = list(Score.objects.filter(
        exam_subject=exam_subject, status="normal", score__isnull=False,
        is_deleted=False,
    ).order_by("-score"))
    rank = 0
    prev = None
    for i, s in enumerate(scores, 1):
        if s.score != prev:
            rank = i
            prev = s.score
        s.rank = rank
        Score.objects.filter(pk=s.pk).update(rank=rank)


@login_required
def score_delete(request, pk):
    current_class = get_current_class(request.user)
    score = get_object_or_404(
        Score.objects.select_related("exam", "exam_subject__subject", "student"),
        pk=pk, exam__school_class=current_class, is_deleted=False,
    )
    if request.method == "POST":
        soft_delete(score, user=request.user, module="scores", model_name="score")
        _update_ranks(score.exam_subject)
        messages.info(request, "成绩记录已移入回收站。")
    return redirect(f"/scores/entry/?exam_id={score.exam_id}&subject_id={score.exam_subject_id}")


def _filter_students(exam, exam_subjects, dimension, field, op, value):
    """按维度（总分/某科目）筛选学生，返回满足条件的学生 id 集合。

    dimension: "total" 或 "subject:科目名"
    field: score / class_rank / grade_rank / city_rank
    op: gte(≥) / lte(≤)
    """
    try:
        threshold = float(value)
    except (TypeError, ValueError):
        return set()

    def _check(v):
        if v is None:
            return False
        return v >= threshold if op == "gte" else v <= threshold

    if dimension == "total":
        total_data = _get_or_compute_total_ranks(exam)
        if field == "score":
            return {
                sid for sid, d in total_data.items()
                if d["total_score"] is not None and _check(d["total_score"])
            }
        rank_field = {
            "class_rank": "class_rank",
            "grade_rank": "grade_rank",
            "city_rank": "city_rank",
        }.get(field)
        if rank_field:
            return {
                sid for sid, d in total_data.items()
                if d[rank_field] is not None and _check(d[rank_field])
            }
        return set()

    if dimension.startswith("subject:"):
        subject_name = dimension.split(":", 1)[1]
        es = next((e for e in exam_subjects if e.subject.name == subject_name), None)
        if not es:
            return set()
        field_map = {
            "score": "score",
            "class_rank": "rank",
            "grade_rank": "grade_rank",
            "city_rank": "city_rank",
        }
        db_field = field_map.get(field)
        if not db_field:
            return set()
        sids = set()
        for s in Score.objects.filter(
            exam_subject=es, status="normal", is_deleted=False,
        ).only("student_id", db_field):
            if _check(getattr(s, db_field)):
                sids.add(s.student_id)
        return sids
    return set()


@login_required
def analysis(request):
    """成绩分析：完整统计 + 优生筛选（仅本班数据与图表）"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    exams = Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []
    exam_id = request.GET.get("exam_id", "")
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    ) if exam_id else None

    # 优生筛选：维度（总分/某科） + 条件（字段/运算符/数值）
    filter_dimension = request.GET.get("filter_dimension", "")
    filter_field = request.GET.get("filter_field", "")
    filter_op = request.GET.get("filter_op", "gte")
    filter_value = request.GET.get("filter_value", "")
    is_filtering = bool(filter_dimension and filter_field and filter_value)

    analysis_data = {}
    rank_distribution = {}
    rank_chart_type = "bar"
    exam_subjects = []
    class_averages = {}
    grade_lines = {}
    class_total_table = []
    class_averages_total = 0
    filtered_student_ids = None
    filter_count = 0

    if exam:
        exam_subjects = list(ExamSubject.objects.filter(exam=exam).select_related("subject"))

        # 计算筛选学生集合（一旦筛选，所有统计均基于该集合）
        if is_filtering:
            filtered_student_ids = _filter_students(
                exam, exam_subjects, filter_dimension, filter_field, filter_op, filter_value,
            )
            filter_count = len(filtered_student_ids)

        # 1. 本班各科统计
        for es in exam_subjects:
            scores = list(Score.objects.filter(
                exam_subject=es, is_deleted=False, status="normal", score__isnull=False,
            ))
            if filtered_student_ids is not None:
                scores = [s for s in scores if s.student_id in filtered_student_ids]
            analysis_data[es.subject.name] = {
                "full_score": es.full_score,
                **compute_score_stats(scores, es.full_score),
            }

        # 1.5 总分统计（含导入的总分班/级/市排名，缺失时自动聚合计算）
        total_data = _get_or_compute_total_ranks(exam)
        if filtered_student_ids is not None:
            total_data = {
                sid: d for sid, d in total_data.items()
                if sid in filtered_student_ids
            }
        total_score_objs = [
            SimpleNamespace(
                score=d["total_score"],
                rank=d["class_rank"],
                grade_rank=d["grade_rank"],
                city_rank=d["city_rank"],
            )
            for d in total_data.values()
            if d["total_score"] is not None
        ]
        analysis_data["总分"] = {
            "full_score": exam.total_score or sum(es.full_score for es in exam_subjects) or 0,
            **compute_score_stats(total_score_objs, None),
        }

        # 2. 总分排名分布（基于筛选后的学生）
        total_scores = list(Score.objects.filter(
            exam=exam, status="normal", score__isnull=False, is_deleted=False,
        ).values("student_id").annotate(total=Sum("score")).order_by("-total"))
        if filtered_student_ids is not None:
            total_scores = [r for r in total_scores if r["student_id"] in filtered_student_ids]
        previous_total = None
        current_rank = 0
        for position, row in enumerate(total_scores, 1):
            if row["total"] != previous_total:
                current_rank = position
                previous_total = row["total"]
            rank_distribution[str(current_rank)] = rank_distribution.get(str(current_rank), 0) + 1
        rank_chart_type = "line" if len(rank_distribution) > 12 else "bar"

        # 3. 各科班级平均分（供弱势判断与颜色，基于筛选后的学生）
        for es in exam_subjects:
            scores = list(Score.objects.filter(
                exam_subject=es, is_deleted=False, status="normal", score__isnull=False,
            ))
            if filtered_student_ids is not None:
                scores = [s for s in scores if s.student_id in filtered_student_ids]
            values = [float(s.score) for s in scores if s.score is not None]
            class_averages[es.subject.name] = round(sum(values) / len(values), 1) if values else 0

        # 4. 本科线/合格线
        for es in exam_subjects:
            gl = GradeLine.objects.filter(exam_subject=es).first()
            grade_lines[es.pk] = {
                "undergraduate_line": gl.undergraduate_line if gl else None,
                "pass_line": gl.pass_line if gl else None,
            }

        # 5. 班级总成绩分析表（仅显示筛选后的学生）
        students = list(Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("sort_order", "student_id"))

        for student in students:
            if filtered_student_ids is not None and student.pk not in filtered_student_ids:
                continue
            student_scores = {}
            total = 0.0
            has_any_score = False
            weak_subjects = []
            for es in exam_subjects:
                score_obj = Score.objects.filter(
                    exam_subject=es, student=student, is_deleted=False,
                ).first()
                if score_obj and score_obj.status == "normal" and score_obj.score is not None:
                    has_any_score = True
                    subject_name = es.subject.name
                    score_val = float(score_obj.score)
                    total += score_val
                    avg = class_averages.get(subject_name, 0)
                    is_below_avg = score_val < avg if avg > 0 else False
                    if is_below_avg:
                        weak_subjects.append(subject_name)
                    display_rank = score_obj.grade_rank if score_obj.grade_rank is not None else score_obj.rank
                    student_scores[subject_name] = {
                        "score": score_val,
                        "grade_rank": display_rank,
                        "is_below_avg": is_below_avg,
                    }
                else:
                    student_scores[es.subject.name] = None

            if not has_any_score:
                continue

            student_total = total_data.get(student.pk, {})
            stored_score = student_total.get("total_score")
            class_total_table.append({
                "student": student,
                "total_score": (
                    stored_score if stored_score is not None else round(total, 1)
                ),
                "stored_class_rank": student_total.get("class_rank"),
                "total_grade_rank": student_total.get("grade_rank"),
                "total_city_rank": student_total.get("city_rank"),
                "subjects": student_scores,
                "weak_subjects": weak_subjects,
            })

        # 按总分降序排名（并列跳名次）；有官方导入班名次的用导入值覆盖
        class_total_table.sort(key=lambda x: -(x["total_score"] or 0))
        prev_total = None
        for i, row in enumerate(class_total_table):
            if row["total_score"] != prev_total:
                row["rank"] = i + 1
                prev_total = row["total_score"]
            else:
                row["rank"] = class_total_table[i - 1]["rank"]
        for row in class_total_table:
            if row["stored_class_rank"] is not None:
                row["rank"] = row["stored_class_rank"]
            row.pop("stored_class_rank", None)

        # 班级总分平均（用于"优秀学生"筛选）
        all_totals = [r["total_score"] for r in class_total_table]
        class_averages_total = round(sum(all_totals) / len(all_totals), 1) if all_totals else 0

    # 名次进退筛选（对比历史考试，按总分排名变化）
    history_exam_id = request.GET.get("history_exam_id", "").strip()
    history_exam = get_object_or_404(
        Exam, pk=history_exam_id, school_class=current_class, is_deleted=False,
    ) if history_exam_id else None
    rank_progress_threshold = _parse_int(request.GET.get("rank_progress_threshold", ""))
    rank_decline_threshold = _parse_int(request.GET.get("rank_decline_threshold", ""))
    rank_change_students = []
    if exam and history_exam and (rank_progress_threshold or rank_decline_threshold):
        current_ranks = _compute_total_ranks(exam)
        history_ranks = _compute_total_ranks(history_exam)
        for sid, cur_r in current_ranks.items():
            hist_r = history_ranks.get(sid)
            if hist_r is None:
                continue
            delta = hist_r - cur_r
            if (rank_progress_threshold and delta >= rank_progress_threshold) or \
               (rank_decline_threshold and delta <= -rank_decline_threshold):
                student = Student.objects.filter(pk=sid).first()
                if student:
                    rank_change_students.append({
                        "student": student,
                        "current_rank": cur_r,
                        "history_rank": hist_r,
                        "delta": delta,
                        "delta_abs": abs(delta),
                        "category": "progress" if delta > 0 else "decline",
                    })
        rank_change_students.sort(key=lambda x: -x["delta"])

    # 学生个人趋势
    student_id = request.GET.get("student_id", "")
    student_trend = None
    selected_student = Student.objects.filter(
        pk=student_id, school_class=current_class, is_deleted=False,
    ).first() if student_id else None
    if selected_student and exam:
        student = selected_student
        exams_qs = Exam.objects.filter(
            school_class=current_class, is_deleted=False
        ).order_by("date")
        trend = []
        for e in exams_qs:
            total = 0
            count = 0
            for es in ExamSubject.objects.filter(exam=e):
                s = Score.objects.filter(
                    exam_subject=es, student=student, status="normal", is_deleted=False,
                ).first()
                if s and s.score is not None:
                    total += float(s.score)
                    count += 1
            if count > 0:
                trend.append({"exam": e.name, "date": e.date.strftime("%m-%d"), "score": round(total, 1)})
        student_trend = {"student": student, "trend": trend}

    return render(request, "scores/analysis.html", {
        "exams": exams, "exam": exam, "analysis_data": analysis_data,
        "student_trend": student_trend, "student_id": student_id, "selected_student": selected_student,
        "rank_distribution": rank_distribution, "rank_chart_type": rank_chart_type,
        "band_chart_data": {name: data["bands"] for name, data in analysis_data.items()},
        "student_list": Student.objects.filter(
            school_class=current_class, is_deleted=False
        ).order_by("student_id") if current_class else [],
        # 优生筛选
        "filter_dimension": filter_dimension,
        "filter_field": filter_field,
        "filter_op": filter_op,
        "filter_value": filter_value,
        "is_filtering": is_filtering,
        "filter_count": filter_count,
        # AI 分析配置状态
        "ai_config": _get_ai_config(current_class),
        "ai_subjects": _get_ai_subjects(exam),
        "latest_ai_result": _get_latest_ai_result(current_class, exam),
        # 名次进退
        "history_exam_id": history_exam_id,
        "history_exam": history_exam,
        "rank_change_students": rank_change_students,
        "rank_progress_threshold": rank_progress_threshold,
        "rank_decline_threshold": rank_decline_threshold,
        "all_exams_for_comparison": exams,
        # 班级总成绩分析表
        "exam_subjects": exam_subjects if exam else [],
        "class_total_table": class_total_table if exam else [],
        "class_averages": class_averages if exam else {},
        "class_averages_total": class_averages_total if exam else 0,
        "grade_lines": grade_lines if exam else {},
    })


@login_required
def analysis_export(request, fmt):
    """导出班级成绩分析（Excel / PDF，服务端生成）。"""
    from apps.scores.analysis_exports import export_analysis_excel, export_analysis_pdf
    from django.http import HttpResponse
    current_class = get_current_class(request.user)
    exam_id = request.GET.get("exam_id", "")
    exam = None
    if exam_id:
        exam = get_object_or_404(
            Exam, pk=exam_id, school_class=current_class, is_deleted=False,
        )
    if not exam:
        messages.error(request, "请先选择考试。")
        return redirect("scores:analysis")

    if fmt == "excel":
        content, filename = export_analysis_excel(current_class, exam)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content, filename = export_analysis_pdf(current_class, exam)
        content_type = "application/pdf"
    response = HttpResponse(content, content_type=content_type)
    from urllib.parse import quote
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@login_required
def comparison_export(request):
    """导出多班对比 Excel。"""
    from apps.scores.analysis_exports import export_comparison_excel
    from django.http import HttpResponse
    from urllib.parse import quote
    current_class = get_current_class(request.user)
    exam_id = request.GET.get("exam_id", "")
    exam = None
    if exam_id:
        exam = get_object_or_404(
            Exam, pk=exam_id, school_class=current_class, is_deleted=False,
        )
    if not exam:
        messages.error(request, "请先选择考试。")
        return redirect("scores:comparison")
    content, filename = export_comparison_excel(current_class, exam)
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@login_required
def student_analysis_export(request, pk, fmt="excel"):
    """导出学生历次成绩（Excel / PDF，含各科+总分折线图）。"""
    from apps.scores.analysis_exports import export_student_excel, export_student_pdf
    from django.http import HttpResponse
    from urllib.parse import quote
    current_class = get_current_class(request.user)
    student = get_object_or_404(
        Student, pk=pk, school_class=current_class, is_deleted=False,
    )
    if fmt == "pdf":
        content, filename = export_student_pdf(student)
        if content is None:
            messages.error(request, "该学生暂无成绩记录。")
            return redirect("scores:student_analysis_detail", pk=student.pk)
        content_type = "application/pdf"
    else:
        content, filename = export_student_excel(student)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(filename)}"
    return response


@login_required
def grade_line_settings(request, exam_id):
    """本科线/合格线设置 —— GET 返回 JSON，POST 批量保存"""
    current_class = get_current_class(request.user)
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    )
    exam_subjects = ExamSubject.objects.filter(exam=exam).select_related("subject").order_by("sort_order")

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "无效的 JSON 数据"}, status=400)

        saved_count = 0
        for es in exam_subjects:
            key = str(es.pk)
            if key in data:
                values = data[key]
                undergraduate_line = values.get("undergraduate_line")
                pass_line = values.get("pass_line")
                # 验证
                if undergraduate_line is not None and undergraduate_line != "":
                    try:
                        undergraduate_line = int(undergraduate_line)
                    except (ValueError, TypeError):
                        undergraduate_line = None
                else:
                    undergraduate_line = None
                if pass_line is not None and pass_line != "":
                    try:
                        pass_line = int(pass_line)
                    except (ValueError, TypeError):
                        pass_line = None
                else:
                    pass_line = None

                GradeLine.objects.update_or_create(
                    exam_subject=es,
                    defaults={
                        "undergraduate_line": undergraduate_line,
                        "pass_line": pass_line,
                    },
                )
                saved_count += 1

        messages.success(request, f"本科线/合格线已保存（{saved_count} 个科目）。")
        return JsonResponse({"success": True, "saved": saved_count})

    # GET: 返回当前设置的 JSON
    grade_lines = {}
    for es in exam_subjects:
        gl = GradeLine.objects.filter(exam_subject=es).first()
        grade_lines[str(es.pk)] = {
            "subject_name": es.subject.name,
            "undergraduate_line": gl.undergraduate_line if gl else None,
            "pass_line": gl.pass_line if gl else None,
        }
    return JsonResponse(grade_lines)


@login_required
def comparison(request):
    """多班成绩对比（独立页面）：对比表 + 图表 + 外部班级导入。"""
    current_class = get_current_class(request.user)
    exam_id = request.GET.get("exam_id", "")
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    ) if exam_id else None
    exams = Exam.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("-date") if current_class else []

    comparison_classes = []
    comparison_table = []
    comparison_chart = {}
    exam_subjects = []
    if exam:
        exam_subjects = list(ExamSubject.objects.filter(exam=exam).select_related("subject"))
        ext_classes, comparison_table, comparison_chart = build_comparison_data(
            exam, exam_subjects, current_class,
        )
        comparison_classes = [{"id": None, "key": "own", "name": "本班", "school_name": ""}]
        comparison_classes.extend(
            {"id": ec.pk, "key": f"ext_{ec.pk}", "name": ec.name, "school_name": ec.school_name}
            for ec in ext_classes
        )

    external_classes = ExternalClass.objects.filter(school_class=current_class) if current_class else []

    return render(request, "scores/comparison.html", {
        "exams": exams, "exam": exam, "exam_subjects": exam_subjects,
        "comparison_classes": comparison_classes,
        "comparison_table": comparison_table,
        "comparison_chart": comparison_chart,
        "external_classes": external_classes,
    })


@login_required
@require_current_class
def external_import(request):
    """导入其他班级成绩用于多班对比。"""
    current_class = get_current_class(request.user)
    exam_id = request.GET.get("exam_id", "") or request.POST.get("exam_id", "")
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    ) if exam_id else None

    if request.method == "POST":
        if exam is None:
            messages.error(request, "请先选择要对比的考试。")
            return redirect("scores:analysis")
        uploaded = request.FILES.get("file")
        class_name = request.POST.get("class_name", "").strip()
        school_name = request.POST.get("school_name", "").strip()
        if not uploaded:
            messages.error(request, "请选择要上传的 Excel 文件。")
            return redirect("scores:external_import")
        exam_subjects = list(ExamSubject.objects.filter(exam=exam).select_related("subject"))
        try:
            external_class, created = import_external_scores(
                uploaded, current_class, exam, class_name, school_name, exam_subjects,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("scores:external_import")
        OperationLog.objects.create(
            user=request.user, action="batch_import", module="scores",
            object_repr=external_class.name,
            detail=f"导入外部班级成绩 {created} 条（考试：{exam.name}）",
            ip_address=get_client_ip(request), success=True,
        )
        messages.success(request, f"「{external_class.name}」导入成功，共 {created} 条成绩。")
        return redirect(f"{request.path}?exam_id={exam.pk}")

    external_classes = ExternalClass.objects.filter(school_class=current_class) if current_class else []
    return render(request, "scores/external_import.html", {
        "exams": Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else [],
        "exam": exam,
        "external_classes": external_classes,
        "exam_subjects": list(ExamSubject.objects.filter(exam=exam).select_related("subject")) if exam else [],
    })


@login_required
def external_import_template(request):
    """下载外部班级成绩导入模板。"""
    from apps.exports.templates_services import external_class_template
    exam_id = request.GET.get("exam_id", "")
    current_class = get_current_class(request.user)
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    ) if exam_id else None
    return external_class_template(exam)


@login_required
def external_delete(request, pk):
    """删除导入的外部对比班级。"""
    current_class = get_current_class(request.user)
    external_class = get_object_or_404(
        ExternalClass, pk=pk, school_class=current_class,
    )
    if request.method == "POST":
        name = external_class.name
        external_class.delete()
        messages.info(request, f"外部对比班级「{name}」已删除。")
    return redirect("scores:analysis")


@login_required
def class_student_overview(request):
    """班级学生情况总览：逐生展示弱势学科（低于班级均分）标签"""
    current_class = get_current_class(request.user)
    exam_id = request.GET.get("exam_id", "")

    exam = None
    if exam_id:
        exam = Exam.objects.filter(
            pk=exam_id, school_class=current_class, is_deleted=False,
        ).first()

    # 考试列表（用于切换）
    exams = Exam.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("-date")[:20] if current_class else []

    # 每个学科班级平均分
    subject_avgs = {}
    exam_subjects = []
    if exam:
        exam_subjects = list(ExamSubject.objects.filter(
            exam=exam,
        ).select_related("subject").order_by("sort_order"))

        from apps.scores.analysis_services import compute_score_stats
        for es in exam_subjects:
            scores_qs = Score.objects.filter(
                exam_subject=es, status="normal", score__isnull=False,
                is_deleted=False,
            ).select_related("student")
            stats = compute_score_stats(list(scores_qs), es.full_score)
            subject_avgs[es.subject.name] = {
                "avg": stats["avg"],
                "full_score": es.full_score,
                "exam_subject_id": es.pk,
            }

    # 逐生构建数据
    students_data = []
    if exam:
        students = Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("sort_order", "student_id")

        exam_total_map = {
            et.student_id: et
            for et in ExamTotal.objects.filter(exam=exam)
        }

        for student in students:
            weak_subjects = []
            strong_subjects = []
            for es in exam_subjects:
                score = Score.objects.filter(
                    exam_subject=es, student=student,
                    status="normal", score__isnull=False, is_deleted=False,
                ).first()
                if score is None:
                    continue
                subject_name = es.subject.name
                avg = subject_avgs.get(subject_name, {}).get("avg")
                if avg is None:
                    continue
                diff = round(float(score.score) - avg, 1)
                entry = {
                    "name": subject_name,
                    "score": float(score.score),
                    "avg": avg,
                    "diff": diff,
                }
                if diff < 0:
                    weak_subjects.append(entry)
                elif diff > 0:
                    strong_subjects.append(entry)

            et = exam_total_map.get(student.pk)
            students_data.append({
                "student": student,
                "total_score": float(et.total_score) if et and et.total_score is not None else None,
                "total_rank": et.class_rank if et else None,
                "total_grade_rank": et.grade_rank if et else None,
                "total_city_rank": et.city_rank if et else None,
                "weak_subjects": weak_subjects,
                "strong_subjects": strong_subjects,
            })

    return render(request, "scores/class_student_overview.html", {
        "exam": exam,
        "exams": exams,
        "students_data": students_data,
    })


@login_required
def student_analysis_detail(request, pk):
    """学生历次成绩、趋势和手动 AI 分析（含优势/弱势学科 + 动态图表）。"""
    current_class = get_current_class(request.user)
    student = get_object_or_404(
        Student, pk=pk, school_class=current_class, is_deleted=False,
    )
    records = Score.objects.filter(
        student=student, exam__school_class=current_class, exam__is_deleted=False,
        is_deleted=False,
    ).select_related("exam", "exam_subject__subject").order_by("exam__date", "exam_subject__sort_order")

    # ----- 历次成绩历史 + 图表数据 -----
    # 已导入的官方总分优先；否则用分科之和
    exam_total_by_exam = {
        et.exam_id: et
        for et in ExamTotal.objects.filter(exam__in=Exam.objects.filter(
            school_class=current_class, is_deleted=False,
        ), student=student)
    }
    history = []
    history_map = {}
    for record in records:
        item = history_map.get(record.exam_id)
        if not item:
            item = {
                "exam": record.exam, "subjects": [], "total": 0.0,
                "full_score": 0, "score_rate": 0,
            }
            history_map[record.exam_id] = item
            history.append(item)
        item["subjects"].append(record)
        if record.status == "normal" and record.score is not None:
            item["total"] += float(record.score)
            item["full_score"] += record.exam_subject.full_score
    for item in history:
        et = exam_total_by_exam.get(item["exam"].pk)
        if et and et.total_score is not None:
            item["total"] = float(et.total_score)
        item["total"] = round(item["total"], 1)
        item["score_rate"] = round(item["total"] / item["full_score"] * 100, 1) if item["full_score"] else 0

    # ----- 全部考试列表（按日期升序） -----
    all_exams = list(Exam.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("date"))

    # ----- 全部科目 -----
    all_subjects = sorted(set(
        Score.objects.filter(
            student=student, exam__school_class=current_class,
            exam__is_deleted=False, is_deleted=False, status="normal", score__isnull=False,
        ).values_list("exam_subject__subject__name", flat=True)
    ))

    # ----- 构建图表 JSON 数据 -----
    # 结构: series[subject_name][metric] = [val per exam (None if no data)]
    from apps.scores.analysis_services import compute_score_stats
    metrics = ["分数", "班级排名", "级部排名", "市排名"]
    series = {}
    # 总分
    series["总分"] = {m: [None] * len(all_exams) for m in metrics}
    # 各科
    for subj in all_subjects:
        series[subj] = {m: [None] * len(all_exams) for m in metrics}

    total_ranks = {}
    for ei, exam in enumerate(all_exams):
        # 总分排名：班级名次计算或取导入值，级/市排名取导入值
        if ei not in total_ranks:
            total_ranks[ei] = _compute_total_ranks(exam)
        tr = total_ranks[ei].get(student.pk)
        exam_total = exam_total_by_exam.get(exam.pk)
        series["总分"]["分数"][ei] = history_map.get(exam.pk, {}).get("total", None) or None
        series["总分"]["班级排名"][ei] = (
            exam_total.class_rank if exam_total and exam_total.class_rank is not None else tr
        )
        series["总分"]["级部排名"][ei] = exam_total.grade_rank if exam_total else None
        series["总分"]["市排名"][ei] = exam_total.city_rank if exam_total else None

        # 各科
        for es in ExamSubject.objects.filter(exam=exam).select_related("subject"):
            subj_name = es.subject.name
            if subj_name not in series:
                continue
            score = Score.objects.filter(
                exam_subject=es, student=student, status="normal",
                score__isnull=False, is_deleted=False,
            ).first()
            if score:
                series[subj_name]["分数"][ei] = float(score.score)
                series[subj_name]["班级排名"][ei] = score.rank
                series[subj_name]["级部排名"][ei] = score.grade_rank
                series[subj_name]["市排名"][ei] = score.city_rank

    # ----- 优势/弱势学科（最近一次考试） -----
    weak_subjects = []
    strong_subjects = []
    if history:
        latest_item = history[-1]
        latest_exam_obj = latest_item["exam"]
        for es in ExamSubject.objects.filter(exam=latest_exam_obj).select_related("subject"):
            subj_name = es.subject.name
            scores_qs = Score.objects.filter(
                exam_subject=es, status="normal", score__isnull=False, is_deleted=False,
            )
            if not scores_qs.exists():
                continue
            stats = compute_score_stats(list(scores_qs), es.full_score)
            class_avg = stats["avg"]
            student_score = Score.objects.filter(
                exam_subject=es, student=student, status="normal",
                score__isnull=False, is_deleted=False,
            ).first()
            if not student_score:
                continue
            diff = round(float(student_score.score) - class_avg, 1)
            entry = {
                "name": subj_name,
                "score": float(student_score.score),
                "avg": class_avg,
                "diff": diff,
            }
            if diff < 0:
                weak_subjects.append(entry)
            elif diff > 0:
                strong_subjects.append(entry)

    # 按差值绝对值排序
    weak_subjects.sort(key=lambda x: x["diff"])
    strong_subjects.sort(key=lambda x: -x["diff"])

    # ----- JSON 图表数据 -----
    chart_data = {
        "exams": [{"id": e.pk, "name": e.name, "date": str(e.date)} for e in all_exams],
        "subjects": ["总分"] + all_subjects,
        "metrics": metrics,
        "series": series,
    }

    from apps.scores.ai_models import AIAnalysisRecord
    latest_ai_result = AIAnalysisRecord.objects.filter(
        school_class=current_class, student=student, analysis_type="student", success=True,
    ).order_by("-created_at").first()
    latest_exam = all_exams[-1] if all_exams else None

    return render(request, "scores/student_analysis_detail.html", {
        "student": student, "history": history, "chart_data": chart_data,
        "latest_ai_result": latest_ai_result, "latest_exam": latest_exam,
        "ai_config": _get_ai_config(current_class),
        "all_exams": all_exams,  # 供模板渲染考试选择器
        "weak_subjects": weak_subjects,
        "strong_subjects": strong_subjects,
    })


def _get_latest_ai_result(current_class, exam):
    """获取最近的 AI 分析结果（供页面展示）"""
    try:
        from apps.scores.ai_models import AIAnalysisRecord
        qs = AIAnalysisRecord.objects.filter(
            school_class=current_class, success=True,
        )
        if exam:
            qs = qs.filter(exam=exam)
        return qs.order_by("-created_at").first()
    except Exception:
        return None


def _get_ai_config(current_class):
    """获取 AI 配置状态（供页面显示）"""
    try:
        from apps.scores.ai_models import AIAnalysisConfig
        if not current_class:
            return None
        config = AIAnalysisConfig.objects.filter(school_class=current_class).first()
        if not config:
            return None
        return {
            "is_enabled": config.is_enabled,
            "has_key": config.has_api_key(),
        }
    except Exception:
        return None


def _get_ai_subjects(exam):
    """获取考试可选科目（供 AI 分析选择）"""
    if not exam:
        return []
    return [es.subject.name for es in ExamSubject.objects.filter(exam=exam).select_related("subject")]


@login_required
def subject_settings(request):
    """科目设置（仅本用户 + 系统默认科目）"""
    subjects = Subject.objects.filter(
        Q(created_by=request.user) | Q(created_by__isnull=True),
    ).order_by("sort_order")

    if request.method == "POST":
        name = request.POST.get("name", "")
        short_name = request.POST.get("short_name", "")
        sort_order = request.POST.get("sort_order", "0")
        try:
            sort_order = int(sort_order)
        except (ValueError, TypeError):
            sort_order = 0
        if name:
            Subject.objects.create(
                name=name, short_name=short_name, sort_order=sort_order,
                created_by=request.user,
            )
            messages.success(request, f"科目「{name}」已添加。")
            return redirect("scores:subject_settings")

    return render(request, "scores/subject_settings.html", {"subjects": subjects})


@login_required
def subject_edit(request, pk):
    """修改科目（仅自己的）"""
    subject = get_object_or_404(Subject, pk=pk, created_by=request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        short_name = request.POST.get("short_name", "").strip()
        is_active = request.POST.get("is_active") == "on"
        sort_order = request.POST.get("sort_order", "0")
        try:
            sort_order = int(sort_order)
        except (ValueError, TypeError):
            sort_order = 0
        if not name:
            messages.error(request, "科目名称不能为空。")
        else:
            subject.name = name
            subject.short_name = short_name
            subject.is_active = is_active
            subject.sort_order = sort_order
            subject.save(update_fields=["name", "short_name", "is_active", "sort_order", "updated_at"])
            messages.success(request, f"科目「{name}」已更新。")
    return redirect("scores:subject_settings")


@login_required
def subject_delete(request, pk):
    """删除/停用科目（仅自己的）"""
    subject = get_object_or_404(Subject, pk=pk, created_by=request.user)
    if request.method == "POST":
        from apps.scores.models import ExamSubject
        if ExamSubject.objects.filter(subject=subject).exists():
            subject.is_active = False
            subject.save(update_fields=["is_active", "updated_at"])
            messages.info(request, f"科目「{subject.name}」已有考试记录，已改为停用。")
        else:
            subject.delete()
            messages.info(request, f"科目「{subject.name}」已删除。")
    return redirect("scores:subject_settings")


@login_required
def score_import(request):
    """Excel 批量导入成绩"""
    if request.method == "POST":
        current_class = get_current_class(request.user)
        exam_id = request.POST.get("exam_id", "")
        subject_id = request.POST.get("subject_id", "")
        uploaded = request.FILES.get("file")

        if not all([exam_id, subject_id, uploaded]):
            messages.error(request, "请选择考试、科目并上传文件。")
            return redirect(f"{request.path}?exam_id={exam_id}&subject_id={subject_id}")

        exam = get_object_or_404(
            Exam, pk=exam_id, school_class=current_class, is_deleted=False,
        )
        exam_subject = get_object_or_404(
            ExamSubject, pk=subject_id, exam=exam
        )

        from openpyxl import load_workbook
        try:
            wb = load_workbook(uploaded, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
        except Exception as exc:
            messages.error(request, f"文件解析失败: {exc}")
            return redirect("scores:score_entry")

        if not rows:
            messages.error(request, "文件中没有数据。")
            return redirect("scores:score_entry")

        # 表头定位
        header_row = rows[0]
        header_map = {}
        for i, h in enumerate(header_row):
            if h:
                header_map[str(h).strip()] = i
        if "学号" not in header_map or "成绩" not in header_map:
            messages.error(request, "Excel 表头必须包含「学号」和「成绩」列。")
            return redirect("scores:score_entry")

        student_map = {
            student.student_id: student
            for student in Student.objects.filter(
                school_class=exam.school_class, is_deleted=False
            )
        }
        status_map = dict(Score.STATUS_CHOICES)
        imported = 0
        skipped = []

        with transaction.atomic():
            for idx, row in enumerate(rows[1:], start=2):
                student_id = str(row[header_map["学号"]]).strip() if row[header_map["学号"]] is not None else ""
                raw_score = row[header_map["成绩"]]

                if not student_id:
                    skipped.append((idx, "", "学号为空"))
                    continue
                student = student_map.get(student_id)
                if not student:
                    skipped.append((idx, student_id, "学号不存在"))
                    continue
                if raw_score is None or str(raw_score).strip() == "":
                    skipped.append((idx, student_id, "成绩为空"))
                    continue

                try:
                    score_val = float(raw_score)
                except (ValueError, TypeError):
                    skipped.append((idx, student_id, f"成绩格式错误({raw_score})"))
                    continue

                if score_val < 0 or score_val > exam_subject.full_score:
                    skipped.append((idx, student_id, f"成绩须在0至{exam_subject.full_score}之间"))
                    continue

                # 状态（可选列）
                status = "normal"
                if "状态" in header_map:
                    raw_status = str(row[header_map["状态"]] or "").strip()
                    for key, label in Score.STATUS_CHOICES:
                        if raw_status == label:
                            status = key
                            break

                Score.objects.update_or_create(
                    exam_subject=exam_subject, student=student,
                    defaults={
                        "exam": exam,
                        "score": score_val,
                        "status": status,
                        "is_deleted": False,
                    },
                )
                imported += 1

        _update_ranks(exam_subject)

        OperationLog.objects.create(
            user=request.user, action="batch_import", module="scores",
            object_repr=f"{exam.name} - {exam_subject.subject.name}",
            detail=f"Excel导入成绩：成功 {imported} 条，跳过 {len(skipped)} 条",
            ip_address=get_client_ip(request), success=True,
        )

        if skipped:
            msgs = "；".join([f"第{r[0]}行({r[1]}): {r[2]}" for r in skipped[:10]])
            messages.warning(request, f"导入成功 {imported} 条，跳过 {len(skipped)} 条。前10条：{msgs}")
        else:
            messages.success(request, f"成绩导入成功，共 {imported} 条。")

        return redirect(f"/scores/entry/?exam_id={exam_id}&subject_id={subject_id}")

    return redirect("scores:score_entry")


@login_required
def score_import_template(request):
    """下载成绩导入 Excel 模板"""
    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "成绩导入模板"

    headers = ["学号", "姓名", "成绩", "状态"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1A73E8", end_color="1A73E8", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # 示例行
    examples = [["2026001", "张三", 85, "正常"], ["2026002", "李四", 92, "正常"], ["2026003", "王五", "", "缺考"]]
    for r, row in enumerate(examples, 2):
        for c, v in enumerate(row, 1):
            ws.cell(row=r, column=c, value=v)

    note_row = 6
    notes = [
        "填写说明：",
        "1. 「学号」必须与系统学生学号完全一致，否则该行将被跳过；",
        "2. 「成绩」填写数字，可保留1位小数，不得超过该科目满分；",
        "3. 「状态」可选：正常/缺考/缓考/免考/成绩无效/其他，留空默认为正常；",
        "4. 导入时未匹配到的学号会在页面提示，不会影响其他数据；",
        "5. 删除示例行后即可填写正式数据。",
    ]
    for i, note in enumerate(notes):
        ws.cell(row=note_row + i, column=1, value=note)

    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 12

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="score_import_template.xlsx"'
    wb.save(response)
    return response


def _excel_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _wide_exam_subject(exam, subject_name, full_score, sort_order):
    names = ["英语", "外语"] if subject_name == "英语" else [subject_name]
    exam_subject = ExamSubject.objects.filter(
        exam=exam, subject__name__in=names,
    ).select_related("subject").first()
    if exam_subject:
        return exam_subject
    owner = exam.school_class.created_by
    subject = Subject.objects.filter(
        Q(created_by=owner) | Q(created_by__isnull=True),
        name__in=names,
    ).order_by("sort_order", "pk").first()
    if not subject:
        subject = Subject.objects.create(
            name=subject_name, short_name=subject_name, sort_order=sort_order,
            created_by=owner,
        )
    return ExamSubject.objects.create(
        exam=exam, subject=subject, full_score=full_score, sort_order=sort_order,
    )


@login_required
def score_import_wide(request):
    """按参考成绩宽表一次导入一场考试的多个科目。"""
    if request.method != "POST":
        return redirect("scores:score_entry")
    current_class = get_current_class(request.user)
    exam_id = request.POST.get("exam_id", "")
    if not exam_id:
        messages.error(request, "请先选择考试。")
        return redirect("scores:score_entry")
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    )
    uploaded = request.FILES.get("file")
    if not uploaded or not uploaded.name.lower().endswith(".xlsx"):
        messages.error(request, "请上传 XLSX 成绩表。")
        return redirect(f"/scores/entry/?exam_id={exam.pk}")

    from openpyxl import load_workbook
    try:
        workbook = load_workbook(uploaded, data_only=True, read_only=True)
        rows = list(workbook.active.iter_rows(values_only=True))
    except Exception as exc:
        messages.error(request, f"文件解析失败：{exc}")
        return redirect(f"/scores/entry/?exam_id={exam.pk}")

    header_index = None
    header_map = {}
    for index, row in enumerate(rows[:10]):
        candidate = {_excel_text(value): col for col, value in enumerate(row) if _excel_text(value)}
        subject_hits = 0
        for _name, aliases, _full in WIDE_SCORE_COLUMNS:
            score_col, *_rest = _wide_match_columns(candidate, _name, aliases)
            if score_col:
                subject_hits += 1
        if ("姓名" in candidate or "学号" in candidate) and subject_hits:
            header_index = index
            header_map = candidate
            break
    if header_index is None:
        messages.error(request, "未找到有效表头：至少需要「姓名」或「学号」，并包含一个成绩列。")
        return redirect(f"/scores/entry/?exam_id={exam.pk}")

    subject_columns = []
    matched_subject_names = []
    for sort_order, (subject_name, aliases, full_score) in enumerate(WIDE_SCORE_COLUMNS, 1):
        score_col, class_rank_col, grade_rank_col, city_rank_col = _wide_match_columns(
            header_map, subject_name, aliases,
        )
        if not score_col:
            continue
        subject_columns.append((
            _wide_exam_subject(exam, subject_name, full_score, sort_order),
            header_map[score_col], score_col,
            header_map[class_rank_col] if class_rank_col else None,
            header_map[grade_rank_col] if grade_rank_col else None,
            header_map[city_rank_col] if city_rank_col else None,
        ))
        matched_subject_names.append(subject_name)

    # 总分列匹配（总分/总分班名次/总分级排名/总分市排名，均可缺失）
    total_score_col, total_class_rank_col, total_grade_rank_col, total_city_rank_col = (
        _match_total_columns(header_map)
    )
    has_total_col = total_score_col is not None

    students = list(Student.objects.filter(school_class=current_class, is_deleted=False))
    student_id_map = {student.student_id: student for student in students}
    student_name_map = {}
    for student in students:
        student_name_map.setdefault(student.name.strip(), []).append(student)
    imported = 0
    imported_students = set()
    total_imported = 0
    skipped = []

    with transaction.atomic():
        for row_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
            student = None
            student_id = _excel_text(row[header_map["学号"]]) if "学号" in header_map and header_map["学号"] < len(row) else ""
            name = _excel_text(row[header_map["姓名"]]) if "姓名" in header_map and header_map["姓名"] < len(row) else ""
            if student_id:
                student = student_id_map.get(student_id)
            if not student and name:
                matches = student_name_map.get(name, [])
                if len(matches) == 1:
                    student = matches[0]
                elif len(matches) > 1:
                    skipped.append(f"第{row_number}行「{name}」存在同名学生，请补充学号")
                    continue
            if not student:
                if student_id or name:
                    skipped.append(f"第{row_number}行未匹配学生：{student_id or name}")
                continue

            for (exam_subject, column_index, column_name,
                 class_rank_idx, grade_rank_idx, city_rank_idx) in subject_columns:
                raw_score = row[column_index] if column_index < len(row) else None
                # 成绩为空视为缺考/无成绩，跳过（但不影响其他科）
                if raw_score is None or _excel_text(raw_score) == "":
                    continue
                try:
                    score_value = float(raw_score)
                except (TypeError, ValueError):
                    skipped.append(f"第{row_number}行「{column_name}」不是数字")
                    continue
                if score_value < 0 or score_value > exam_subject.full_score:
                    skipped.append(f"第{row_number}行「{column_name}」须在0至{exam_subject.full_score}之间")
                    continue
                class_rank = _parse_rank(row[class_rank_idx]) if class_rank_idx is not None and class_rank_idx < len(row) else None
                grade_rank = _parse_rank(row[grade_rank_idx]) if grade_rank_idx is not None and grade_rank_idx < len(row) else None
                city_rank = _parse_rank(row[city_rank_idx]) if city_rank_idx is not None and city_rank_idx < len(row) else None
                Score.objects.update_or_create(
                    exam_subject=exam_subject, student=student,
                    defaults={
                        "exam": exam, "score": score_value, "status": "normal",
                        "rank": class_rank, "grade_rank": grade_rank,
                        "city_rank": city_rank, "is_deleted": False,
                    },
                )
                imported += 1
                imported_students.add(student.pk)

            # 总分列（可选）：解析总分及三种排名并写入 ExamTotal
            if has_total_col:
                total_idx = header_map[total_score_col]
                raw_total = row[total_idx] if total_idx < len(row) else None
                if raw_total is not None and _excel_text(raw_total) != "":
                    try:
                        total_value = float(raw_total)
                    except (TypeError, ValueError):
                        skipped.append(f"第{row_number}行「总分」不是数字")
                    else:
                        total_defaults = {"total_score": total_value}
                        if total_class_rank_col is not None:
                            total_defaults["class_rank"] = _parse_rank(
                                row[header_map[total_class_rank_col]]
                            ) if header_map[total_class_rank_col] < len(row) else None
                        if total_grade_rank_col is not None:
                            total_defaults["grade_rank"] = _parse_rank(
                                row[header_map[total_grade_rank_col]]
                            ) if header_map[total_grade_rank_col] < len(row) else None
                        if total_city_rank_col is not None:
                            total_defaults["city_rank"] = _parse_rank(
                                row[header_map[total_city_rank_col]]
                            ) if header_map[total_city_rank_col] < len(row) else None
                        ExamTotal.objects.update_or_create(
                            exam=exam, student=student,
                            defaults=total_defaults,
                        )
                        total_imported += 1

        # 仅在文件未提供「班名次」列时才自动计算班级名次，避免覆盖导入的官方名次
        for exam_subject, _column_index, _column_name, class_rank_idx, *_rest in subject_columns:
            if class_rank_idx is None:
                _update_ranks(exam_subject)

    total_part = f"，总分 {total_imported} 条" if total_imported else ""
    OperationLog.objects.create(
        user=request.user, action="batch_import", module="scores",
        object_repr=f"{exam.name} - 多科成绩",
        detail=f"宽表导入：{len(imported_students)}名学生，{imported}条成绩{total_part}，{len(skipped)}项跳过；匹配科目：{'、'.join(matched_subject_names) or '无'}",
        ip_address=get_client_ip(request), success=True,
    )
    if skipped:
        messages.warning(request, f"已导入 {len(imported_students)} 名学生的 {imported} 条成绩{total_part}；另有 {len(skipped)} 项未导入：" + "；".join(skipped[:8]))
    else:
        messages.success(request, f"已导入 {len(imported_students)} 名学生的 {imported} 条成绩{total_part}。")
    return redirect(f"/scores/entry/?exam_id={exam.pk}")


@login_required
def score_import_wide_template(request):
    """下载与参考文件结构兼容的九科成绩宽表模板。"""
    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    current_class = get_current_class(request.user)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "成绩导入"
    headers = ["姓名", "学号"]
    # 语数英是原始分没有赋分，直接写科目名；选考科目保留赋分+原始两列
    PLAIN_SUBJECTS = ("语文", "数学", "英语")
    for subject_name, _aliases, _full in WIDE_SCORE_COLUMNS:
        if subject_name in PLAIN_SUBJECTS:
            score_cols = [subject_name]
        else:
            score_cols = [f"{subject_name}赋分", f"{subject_name}原始"]
        headers.extend(score_cols)
        headers.extend([
            f"{subject_name}班名次", f"{subject_name}级名次", f"{subject_name}市名次",
        ])
    # 总分列（最后，在所有科目列之后；均可留空）
    headers.extend(["总分", "总分班名次", "总分级排名", "总分市排名"])
    sheet.append(headers)
    for student in Student.objects.filter(school_class=current_class, is_deleted=False).order_by("student_id") if current_class else []:
        sheet.append([student.name, student.student_id])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="1A73E8", end_color="1A73E8", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.column_dimensions["A"].width = 12
    sheet.column_dimensions["B"].width = 22
    for column in range(3, len(headers) + 1):
        sheet.column_dimensions[sheet.cell(1, column).column_letter].width = 12
    note_sheet = workbook.create_sheet("填写说明")
    note_sheet.append(["说明"])
    note_sheet.append(["本模板为参考格式。上传时系统会自动匹配表头，只要你的表格表头包含科目名（如“语文”“数学”“英语”）即可，不要求与本模板完全一致。"])
    note_sheet.append(["并非所有列都必须填写：没有赋分的考试可留空“赋分”列；没有市名次的考试可留空“市名次”列；某科缺考的学生该科成绩留空即可。"])
    note_sheet.append(["姓名或学号至少填写一项；同名学生必须填写学号。班名次/级名次/市名次为可选项，填了才会写入对应排名字段。"])
    note_sheet.append(["最后 4 列为总分相关（总分/总分班名次/总分级排名/总分市排名），可留空；留空时系统按分科成绩自动计算总分与班级名次。"])
    note_sheet.append(["英语与日语为二选一科目：选修日语的学生填日语列，选修英语的学生填英语列，另一列留空。"])
    note_sheet.column_dimensions["A"].width = 110

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="class_score_wide_import_template.xlsx"'
    workbook.save(response)
    return response
