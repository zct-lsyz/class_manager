from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Avg, Max, Min, Count, Q
from django.utils import timezone
from django.db import transaction

from apps.scores.models import Exam, ExamSubject, Score, SupportPlan, SupportFollowUp
from apps.scores.forms import ExamForm, ExamSubjectForm, ScoreForm, SupportPlanForm
from apps.classes.subjects import Subject
from apps.classes.models import SchoolClass, Semester
from apps.audit.services import soft_delete
from apps.students.models import Student


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
    current_semester = Semester.objects.filter(is_current=True).first()

    exams = Exam.objects.filter(school_class=current_class, is_published=True, is_deleted=False).order_by("-date") if current_class else []
    exam_id = request.GET.get("exam_id", "")
    exam = get_object_or_404(
        Exam, pk=exam_id, school_class=current_class, is_deleted=False,
    ) if exam_id else None

    analysis_data = {}
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

    # 学生个人趋势
    student_id = request.GET.get("student_id", "")
    student_trend = None
    from apps.students.models import Student
    if student_id and exam:
        student = Student.objects.filter(pk=student_id).first()
        if student:
            exams_qs = Exam.objects.filter(
                school_class=current_class, is_published=True, is_deleted=False
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
