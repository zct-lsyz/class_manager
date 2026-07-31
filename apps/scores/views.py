from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Avg, Max, Min, Count, Q, Sum
from django.utils import timezone
from django.db import transaction

from apps.scores.models import Exam, ExamSubject, Score, SupportPlan, SupportFollowUp
from apps.scores.forms import ExamForm, ExamSubjectForm, ScoreForm, SupportPlanForm
from apps.classes.subjects import Subject
from apps.classes.models import SchoolClass, Semester
from apps.audit.services import soft_delete
from apps.audit.models import OperationLog
from apps.students.models import Student


WIDE_SCORE_COLUMNS = [
    ("语文", ["语文赋分", "语文原始", "语文"], 150),
    ("数学", ["数学赋分", "数学原始", "数学"], 150),
    ("英语", ["英语赋分", "外语赋分", "英语原始", "外语原始", "英语", "外语"], 150),
    ("物理", ["物理赋分", "物理原始", "物理"], 100),
    ("化学", ["化学赋分", "化学原始", "化学"], 100),
    ("生物", ["生物赋分", "生物原始", "生物"], 100),
    ("政治", ["政治赋分", "政治原始", "政治"], 100),
    ("历史", ["历史赋分", "历史原始", "历史"], 100),
    ("地理", ["地理赋分", "地理原始", "地理"], 100),
]


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


@login_required
def exam_list(request):
    """考试管理"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    exams = Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []

    paginator = Paginator(exams, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "scores/exam_list.html", {"page_obj": page_obj})


@login_required
def exam_create(request):
    """新建考试"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    if not current_class:
        messages.error(request, "请先在班级与学期设置中指定当前班级。")
        return redirect("classes:settings")
    if not current_semester:
        messages.error(request, "请先为当前班级指定当前学期。")
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
    current_class = SchoolClass.objects.filter(is_current=True).first()
    exam = get_object_or_404(
        Exam.objects.select_related("semester"),
        pk=pk, school_class=current_class, is_deleted=False,
    )
    exam_subjects = ExamSubject.objects.filter(exam=exam).select_related("subject")

    # 统计各科已录入成绩数
    for es in exam_subjects:
        es.score_count = Score.objects.filter(exam_subject=es, is_deleted=False).count()

    # 未加入考试的科目
    added_subject_ids = exam_subjects.values_list("subject_id", flat=True)
    available_subjects = Subject.objects.filter(is_active=True).exclude(id__in=added_subject_ids)

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
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
    es = get_object_or_404(ExamSubject, pk=pk)
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
    current_class = SchoolClass.objects.filter(is_current=True).first()

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
    current_class = SchoolClass.objects.filter(is_current=True).first()
    score = get_object_or_404(
        Score.objects.select_related("exam", "exam_subject__subject", "student"),
        pk=pk, exam__school_class=current_class, is_deleted=False,
    )
    if request.method == "POST":
        soft_delete(score, user=request.user, module="scores", model_name="score")
        _update_ranks(score.exam_subject)
        messages.info(request, "成绩记录已移入回收站。")
    return redirect(f"/scores/entry/?exam_id={score.exam_id}&subject_id={score.exam_subject_id}")


@login_required
def analysis(request):
    """成绩分析"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    exams = Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []
    exam_id = request.GET.get("exam_id", "")
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    ) if exam_id else None

    analysis_data = {}
    rank_distribution = {}
    rank_chart_type = "bar"
    if exam:
        for es in ExamSubject.objects.filter(exam=exam).select_related("subject"):
            scores_qs = Score.objects.filter(exam_subject=es, is_deleted=False)
            normal_scores = scores_qs.filter(status="normal", score__isnull=False)
            stats = normal_scores.aggregate(
                avg=Avg("score"), max=Max("score"), min=Min("score"), count=Count("id")
            )
            total_students = normal_scores.count()
            pass_count = normal_scores.filter(score__gte=es.full_score * 0.6).count()
            excellent_count = normal_scores.filter(score__gte=es.full_score * 0.85).count()

            # 分数段分布
            bands = {"0-59%": 0, "60-69%": 0, "70-79%": 0, "80-89%": 0, "90-100%": 0}
            for s in normal_scores:
                v = float(s.score) if s.score is not None else None
                if v is None:
                    continue
                ratio = v / es.full_score if es.full_score else 0
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

            analysis_data[es.subject.name] = {
                "full_score": es.full_score,
                "avg": round(stats["avg"], 1) if stats["avg"] else 0,
                "max": stats["max"],
                "min": stats["min"],
                "pass_rate": round(pass_count / total_students * 100, 1) if total_students > 0 else 0,
                "excellent_rate": round(excellent_count / total_students * 100, 1) if total_students > 0 else 0,
                "bands": bands,
            }

        total_scores = list(Score.objects.filter(
            exam=exam, status="normal", score__isnull=False, is_deleted=False,
        ).values("student_id").annotate(total=Sum("score")).order_by("-total"))
        previous_total = None
        current_rank = 0
        for position, row in enumerate(total_scores, 1):
            if row["total"] != previous_total:
                current_rank = position
                previous_total = row["total"]
            rank_distribution[str(current_rank)] = rank_distribution.get(str(current_rank), 0) + 1
        rank_chart_type = "line" if len(rank_distribution) > 12 else "bar"

    # 学生个人趋势
    student_id = request.GET.get("student_id", "")
    student_trend = None
    selected_student = Student.objects.filter(
        pk=student_id, school_class=current_class, is_deleted=False,
    ).first() if student_id else None
    if selected_student and exam:
        student = selected_student
        if student:
            exams_qs = Exam.objects.filter(
                school_class=current_class, is_deleted=False
            ).order_by("date")
            trend = []
            for e in exams_qs:
                total = 0
                count = 0
                for es in ExamSubject.objects.filter(exam=e):
                    s = Score.objects.filter(
                        exam_subject=es,
                        student=student,
                        status="normal",
                        is_deleted=False,
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
        # AI 分析配置状态
        "ai_config": _get_ai_config(current_class),
        "ai_subjects": _get_ai_subjects(exam),
        "latest_ai_result": _get_latest_ai_result(current_class, exam),
    })


@login_required
def student_analysis_detail(request, pk):
    """学生历次成绩、趋势和手动 AI 分析。"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    student = get_object_or_404(
        Student, pk=pk, school_class=current_class, is_deleted=False,
    )
    records = Score.objects.filter(
        student=student, exam__school_class=current_class, exam__is_deleted=False,
        is_deleted=False,
    ).select_related("exam", "exam_subject__subject").order_by("exam__date", "exam_subject__sort_order")
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
        item["total"] = round(item["total"], 1)
        item["score_rate"] = round(item["total"] / item["full_score"] * 100, 1) if item["full_score"] else 0

    from apps.scores.ai_models import AIAnalysisRecord
    latest_ai_result = AIAnalysisRecord.objects.filter(
        school_class=current_class, student=student, analysis_type="student", success=True,
    ).order_by("-created_at").first()
    latest_exam = Exam.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("-date").first()
    chart_data = {
        "labels": [f"{item['exam'].name}（{item['exam'].date:%Y-%m-%d}）" for item in history],
        "rates": [item["score_rate"] for item in history],
        "totals": [item["total"] for item in history],
    }
    return render(request, "scores/student_analysis_detail.html", {
        "student": student, "history": history, "chart_data": chart_data,
        "latest_ai_result": latest_ai_result, "latest_exam": latest_exam,
        "ai_config": _get_ai_config(current_class),
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
    """科目设置"""
    subjects = Subject.objects.all().order_by("sort_order")

    if request.method == "POST":
        name = request.POST.get("name", "")
        short_name = request.POST.get("short_name", "")
        if name:
            Subject.objects.create(name=name, short_name=short_name)
            messages.success(request, f"科目「{name}」已添加。")
            return redirect("scores:subject_settings")

    return render(request, "scores/subject_settings.html", {"subjects": subjects})


@login_required
def score_import(request):
    """Excel 批量导入成绩"""
    if request.method == "POST":
        exam_id = request.POST.get("exam_id", "")
        subject_id = request.POST.get("subject_id", "")
        uploaded = request.FILES.get("file")

        if not all([exam_id, subject_id, uploaded]):
            messages.error(request, "请选择考试、科目并上传文件。")
            return redirect(f"{request.path}?exam_id={exam_id}&subject_id={subject_id}")

        exam = get_object_or_404(Exam, pk=exam_id, is_deleted=False)
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
    subject = Subject.objects.filter(name__in=names).order_by("sort_order", "pk").first()
    if not subject:
        subject = Subject.objects.create(
            name=subject_name, short_name=subject_name, sort_order=sort_order,
        )
    return ExamSubject.objects.create(
        exam=exam, subject=subject, full_score=full_score, sort_order=sort_order,
    )


@login_required
def score_import_wide(request):
    """按参考成绩宽表一次导入一场考试的多个科目。"""
    if request.method != "POST":
        return redirect("scores:score_entry")
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
        subject_hits = sum(any(alias in candidate for alias in aliases) for _name, aliases, _full in WIDE_SCORE_COLUMNS)
        if ("姓名" in candidate or "学号" in candidate) and subject_hits:
            header_index = index
            header_map = candidate
            break
    if header_index is None:
        messages.error(request, "未找到有效表头：至少需要「姓名」或「学号」，并包含一个九科成绩列。")
        return redirect(f"/scores/entry/?exam_id={exam.pk}")

    subject_columns = []
    for sort_order, (subject_name, aliases, full_score) in enumerate(WIDE_SCORE_COLUMNS, 1):
        matched = next((alias for alias in aliases if alias in header_map), None)
        if matched:
            subject_columns.append((
                _wide_exam_subject(exam, subject_name, full_score, sort_order),
                header_map[matched], matched,
            ))

    students = list(Student.objects.filter(school_class=current_class, is_deleted=False))
    student_id_map = {student.student_id: student for student in students}
    student_name_map = {}
    for student in students:
        student_name_map.setdefault(student.name.strip(), []).append(student)
    imported = 0
    imported_students = set()
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

            for exam_subject, column_index, column_name in subject_columns:
                raw_score = row[column_index] if column_index < len(row) else None
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
                Score.objects.update_or_create(
                    exam_subject=exam_subject, student=student,
                    defaults={
                        "exam": exam, "score": score_value, "status": "normal", "is_deleted": False,
                    },
                )
                imported += 1
                imported_students.add(student.pk)

        for exam_subject, _column_index, _column_name in subject_columns:
            _update_ranks(exam_subject)

    OperationLog.objects.create(
        user=request.user, action="batch_import", module="scores",
        object_repr=f"{exam.name} - 多科成绩",
        detail=f"参考宽表导入：{len(imported_students)}名学生，{imported}条成绩，{len(skipped)}项跳过",
        ip_address=get_client_ip(request), success=True,
    )
    if skipped:
        messages.warning(request, f"已导入 {len(imported_students)} 名学生的 {imported} 条成绩；另有 {len(skipped)} 项未导入：" + "；".join(skipped[:8]))
    else:
        messages.success(request, f"已导入 {len(imported_students)} 名学生的 {imported} 条成绩。")
    return redirect(f"/scores/entry/?exam_id={exam.pk}")


@login_required
def score_import_wide_template(request):
    """下载与参考文件结构兼容的九科成绩宽表模板。"""
    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    current_class = SchoolClass.objects.filter(is_current=True).first()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "九科成绩导入"
    headers = [
        "姓名", "学号", "总分原始", "总分赋分", "校名", "班名", "语数外", "三科校名", "三科班名",
        "语文", "语文校名", "语文班名", "数学", "数学校名", "数学班名", "外语", "外语校名", "外语班名",
        "物理原始", "物理赋分", "物理校名", "物理班名", "化学原始", "化学赋分", "化学校名", "化学班名",
        "生物原始", "生物赋分", "生物校名", "生物班名", "政治原始", "政治赋分", "政治校名", "政治班名",
        "历史原始", "历史赋分", "历史校名", "历史班名", "地理原始", "地理赋分", "地理校名", "地理班名",
    ]
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
    note_sheet.append(["可直接粘贴参考成绩表；系统优先读取“赋分”，没有赋分列时读取“原始”或科目名列。"])
    note_sheet.append(["姓名或学号至少填写一项；同名学生必须填写学号。总分、校名、班名等统计列用于留存原表结构，不重复写入单科成绩。"])
    note_sheet.column_dimensions["A"].width = 110

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="class_score_wide_import_template.xlsx"'
    workbook.save(response)
    return response
