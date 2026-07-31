from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Avg, Max, Min, Count, Q
from django.utils import timezone

from apps.scores.models import Exam, ExamSubject, Score, SupportPlan, SupportFollowUp
from apps.scores.forms import ExamForm, ExamSubjectForm, ScoreForm, SupportPlanForm
from apps.homework.models import Subject
from apps.classes.models import SchoolClass, Semester


@login_required
def exam_list(request):
    """考试管理"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    exams = Exam.objects.filter(school_class=current_class).order_by("-date") if current_class else []

    paginator = Paginator(exams, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "scores/exam_list.html", {"page_obj": page_obj})


@login_required
def exam_create(request):
    """新建考试"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

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
    exam = get_object_or_404(
        Exam.objects.select_related("semester"), pk=pk,
    )
    exam_subjects = ExamSubject.objects.filter(exam=exam).select_related("subject")

    # 统计各科已录入成绩数
    for es in exam_subjects:
        es.score_count = Score.objects.filter(exam_subject=es).count()

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
def exam_subject_create(request, pk):
    """为考试添加科目"""
    exam = get_object_or_404(Exam, pk=pk)
    if request.method == "POST":
        subject_id = request.POST.get("subject", "")
        full_score = request.POST.get("full_score", "100")
        if subject_id:
            try:
                full_score = int(full_score)
            except (ValueError, TypeError):
                full_score = 100
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
        has_scores = Score.objects.filter(exam_subject=es).exists()
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

    if exam_id and subject_id:
        exam = get_object_or_404(Exam, pk=exam_id)
        exam_subject = get_object_or_404(ExamSubject, pk=subject_id)
        scores = Score.objects.filter(
            exam_subject=exam_subject
        ).select_related("student").order_by("student__student_id")

    # 批量保存成绩（POST 提交 score_{student_id} 字段）
    if request.method == "POST" and exam_id and subject_id:
        exam = get_object_or_404(Exam, pk=exam_id)
        exam_subject = get_object_or_404(ExamSubject, pk=subject_id)
        current_semester = Semester.objects.filter(is_current=True).first()

        saved_count = 0
        cleared_count = 0
        for key, value in request.POST.items():
            if not key.startswith("score_"):
                continue
            student_id = key.replace("score_", "")
            if not student_id.isdigit():
                continue

            # 状态字段
            status = request.POST.get(f"status_{student_id}", "normal")
            score_val = value.strip() if value else ""

            # 更新或创建
            score_obj, created = Score.objects.get_or_create(
                exam_subject=exam_subject, student_id=int(student_id),
                defaults={"exam": exam, "status": "normal"},
            )

            if score_val == "":
                # 清空成绩
                if score_obj.score is not None:
                    score_obj.score = None
                    score_obj.save()
                    cleared_count += 1
                continue

            try:
                score_num = float(score_val)
            except (ValueError, TypeError):
                continue

            # 校验不超过满分
            if score_num > exam_subject.full_score:
                messages.error(request, f"学号 {student_id} 的成绩 {score_num} 超过满分 {exam_subject.full_score}，未保存。")
                continue

            score_obj.score = score_num
            score_obj.status = status
            score_obj.exam = exam
            score_obj.save()
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

    exams = Exam.objects.filter(school_class=current_class).order_by("-date") if current_class else []
    subjects = ExamSubject.objects.filter(exam_id=exam_id).select_related("subject") if exam_id else []

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
def analysis(request):
    """成绩分析"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    exams = Exam.objects.filter(school_class=current_class, is_published=True).order_by("-date") if current_class else []
    exam_id = request.GET.get("exam_id", "")
    exam = get_object_or_404(Exam, pk=exam_id) if exam_id else None

    analysis_data = {}
    if exam:
        for es in ExamSubject.objects.filter(exam=exam).select_related("subject"):
            scores_qs = Score.objects.filter(exam_subject=es)
            normal_scores = scores_qs.filter(status="normal")
            stats = normal_scores.aggregate(
                avg=Avg("score"), max=Max("score"), min=Min("score"), count=Count("id")
            )
            total_students = scores_qs.count()
            pass_count = normal_scores.filter(score__gte=es.full_score * 0.6).count()
            excellent_count = normal_scores.filter(score__gte=es.full_score * 0.85).count()

            # 分数段分布
            bands = {"0-59": 0, "60-69": 0, "70-79": 0, "80-89": 0, "90-100": 0}
            for s in normal_scores:
                v = float(s.score) if s.score is not None else None
                if v is None:
                    continue
                if v < 60:
                    bands["0-59"] += 1
                elif v < 70:
                    bands["60-69"] += 1
                elif v < 80:
                    bands["70-79"] += 1
                elif v < 90:
                    bands["80-89"] += 1
                else:
                    bands["90-100"] += 1

            analysis_data[es.subject.name] = {
                "full_score": es.full_score,
                "avg": round(stats["avg"], 1) if stats["avg"] else 0,
                "max": stats["max"],
                "min": stats["min"],
                "pass_rate": round(pass_count / total_students * 100, 1) if total_students > 0 else 0,
                "excellent_rate": round(excellent_count / total_students * 100, 1) if total_students > 0 else 0,
                "bands": bands,
            }

    # 学生个人趋势
    student_id = request.GET.get("student_id", "")
    student_trend = None
    from apps.students.models import Student
    if student_id and exam:
        student = Student.objects.filter(pk=student_id).first()
        if student:
            exams_qs = Exam.objects.filter(
                school_class=current_class, is_published=True
            ).order_by("date")
            trend = []
            for e in exams_qs:
                total = 0
                count = 0
                for es in ExamSubject.objects.filter(exam=e):
                    s = Score.objects.filter(exam_subject=es, student=student, status="normal").first()
                    if s and s.score is not None:
                        total += float(s.score)
                        count += 1
                if count > 0:
                    trend.append({"exam": e.name, "date": e.date.strftime("%m-%d"), "score": round(total, 1)})
            student_trend = {"student": student, "trend": trend}

    return render(request, "scores/analysis.html", {
        "exams": exams, "exam": exam, "analysis_data": analysis_data,
        "student_trend": student_trend, "student_id": student_id,
        "student_list": Student.objects.filter(
            school_class=current_class, is_deleted=False
        ).order_by("student_id") if current_class else [],
        # AI 分析配置状态
        "ai_config": _get_ai_config(current_class),
        "ai_subjects": _get_ai_subjects(exam),
        "latest_ai_result": _get_latest_ai_result(current_class, exam),
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

        exam = get_object_or_404(Exam, pk=exam_id)
        exam_subject = get_object_or_404(ExamSubject, pk=subject_id)

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

        student_map = {s.student_id: s for s in Student.objects.all()}
        status_map = dict(Score.STATUS_CHOICES)
        imported = 0
        skipped = []

        for idx, row in enumerate(rows[1:], start=2):
            student_id = str(row[header_map["学号"]]).strip() if row[header_map["学号"]] is not None else ""
            raw_score = row[header_map["成绩"]]

            if not student_id:
                skipped.append((idx, "", "学号为空"))
                continue
            student = student_map.get(student_id)
            if not student:
                skipped.append((idx, student_id, f"学号不存在"))
                continue
            if raw_score is None or str(raw_score).strip() == "":
                skipped.append((idx, student_id, "成绩为空"))
                continue

            try:
                score_val = float(raw_score)
            except (ValueError, TypeError):
                skipped.append((idx, student_id, f"成绩格式错误({raw_score})"))
                continue

            if score_val > exam_subject.full_score:
                skipped.append((idx, student_id, f"超过满分{exam_subject.full_score}"))
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
                defaults={"exam": exam, "score": score_val, "status": status},
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
