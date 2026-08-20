from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.utils import timezone

from apps.students.models import Student, Guardian
from apps.students.forms import StudentForm, GuardianForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.audit.models import OperationLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


# ========== 学生花名册 ==========

@login_required
def student_list(request):
    """学生列表"""
    current_class = get_current_class(request.user)
    if current_class:
        students = Student.objects.filter(school_class=current_class, is_deleted=False)
    else:
        students = Student.objects.none()

    # 筛选
    gender = request.GET.get("gender", "")
    class_id = request.GET.get("class_id", "")
    search = request.GET.get("search", "")

    if gender:
        students = students.filter(gender=gender)
    if class_id:
        students = students.filter(school_class_id=class_id)
    if search:
        students = students.filter(
            Q(name__icontains=search) | Q(student_id__icontains=search)
        )

    # 分页
    paginator = Paginator(students, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    classes = SchoolClass.objects.filter(created_by=request.user)

    context = {
        "page_obj": page_obj,
        "classes": classes,
        "current_filters": {
            "gender": gender,
            "class_id": class_id,
            "search": search,
        },
    }
    return render(request, "students/student_list.html", context)


@login_required
def student_create(request):
    """新增学生"""
    if request.method == "POST":
        form = StudentForm(request.POST)
        if form.is_valid():
            student = form.save(commit=False)
            if not student.school_class:
                student.school_class = get_current_class(request.user)
            if not student.school_class:
                messages.error(request, "请先创建班级，再添加学生。")
                return redirect("classes:settings")
            student.save()
            messages.success(request, f"学生「{student.name}」添加成功。")
            OperationLog.objects.create(
                user=request.user, action="create", module="students",
                object_repr=student.name,
                detail=f"新增学生: {student.name} (学号: {student.student_id})",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("students:list")
        messages.error(request, "保存失败，请检查页面中的格式提示。")
    else:
        form = StudentForm()
        # 默认选中当前班级
        current_class = get_current_class(request.user)
        if current_class:
            form.fields["school_class"].initial = current_class.pk
    return render(request, "students/student_form.html", {"form": form, "title": "新增学生"})


@login_required
def student_edit(request, pk):
    """编辑学生"""
    current_class = get_current_class(request.user)
    student = get_object_or_404(Student, pk=pk, school_class=current_class)
    if request.method == "POST":
        form = StudentForm(request.POST, instance=student)
        if form.is_valid():
            student = form.save()
            messages.success(request, f"学生「{student.name}」信息已更新。")
            OperationLog.objects.create(
                user=request.user, action="edit", module="students",
                object_repr=student.name,
                detail=f"编辑学生: {student.name} (学号: {student.student_id})",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("students:list")
        messages.error(request, "保存失败，请检查页面中的格式提示。")
    else:
        form = StudentForm(instance=student)
    return render(request, "students/student_form.html", {
        "form": form, "student": student, "title": "编辑学生",
    })


@login_required
def student_delete(request, pk):
    """删除学生（软删除 + 写入回收站）"""
    current_class = get_current_class(request.user)
    student = get_object_or_404(Student, pk=pk, school_class=current_class)
    if request.method == "POST":
        student.soft_delete()
        # 写入回收站记录
        from datetime import timedelta
        from django.utils import timezone
        from apps.audit.models import SoftDeleteRecord
        SoftDeleteRecord.objects.create(
            model_name="student",
            object_id=student.pk,
            object_repr=f"{student.name}（学号：{student.student_id}）",
            module="students",
            serialized_data={
                "student_id": student.student_id,
                "name": student.name,
                "gender": student.gender,
            },
            deleted_by=request.user,
            expires_at=timezone.now() + timedelta(days=30),
        )
        messages.warning(request, f"学生「{student.name}」已移至回收站。")
        OperationLog.objects.create(
            user=request.user, action="delete", module="students",
            object_repr=student.name,
            detail=f"删除学生: {student.name} (学号: {student.student_id})",
            ip_address=get_client_ip(request), success=True,
        )
    return redirect("students:list")


@login_required
def student_detail(request, pk):
    """学生详情/综合档案"""
    current_class = get_current_class(request.user)
    student = get_object_or_404(Student, pk=pk, school_class=current_class, is_deleted=False)
    guardian = Guardian.objects.filter(student=student, is_deleted=False).first()

    # === 处理谈话记录 POST ===
    if request.method == "POST" and request.POST.get("action") == "add_conversation":
        from apps.communications.models import StudentConversation
        from apps.scores.models import Exam
        current_class = get_current_class(request.user)
        current_semester = Semester.objects.filter(
            school_class=current_class, is_current=True,
        ).first() if current_class else None

        exam_id = request.POST.get("exam_id", "").strip()
        conv = StudentConversation(
            school_class=student.school_class,
            semester=current_semester,
            student=student,
            exam=Exam.objects.filter(
                pk=exam_id, school_class=student.school_class,
            ).first() if exam_id else None,
            date=request.POST.get("date", "") or timezone.localdate(),
            reason=request.POST.get("reason", "").strip(),
            main_content=request.POST.get("main_content", "").strip(),
            follow_up_actions=request.POST.get("follow_up_actions", "").strip(),
        )
        if not conv.main_content:
            messages.error(request, "谈话主要内容不能为空。")
        else:
            conv.save()
            messages.success(request, "谈话记录已保存，已同步到成长时间线。")
        return redirect("students:detail", pk=student.pk)

    from apps.attendance.models import AttendanceRecord
    from apps.comments.models import StudentComment
    from apps.communications.models import StudentConversation
    from apps.discipline.models import ClassroomDisciplineRecord, DormDisciplineRecord
    from apps.rewards.models import RewardRecord
    from apps.scores.models import Score, Exam

    scores = Score.objects.filter(
        student=student, is_deleted=False, exam__is_deleted=False,
    ).select_related("exam", "exam_subject__subject").order_by("-exam__date")[:50]
    attendance_records = AttendanceRecord.objects.filter(
        student=student,
    ).order_by("-date")[:50]
    classroom_records = ClassroomDisciplineRecord.objects.filter(
        student=student, is_deleted=False,
    ).select_related("item").order_by("-date")[:50]
    dorm_records = DormDisciplineRecord.objects.filter(
        student=student, is_deleted=False,
    ).select_related("item").order_by("-date")[:50]
    reward_records = RewardRecord.objects.filter(
        student=student, is_deleted=False,
    ).select_related("item").order_by("-date")[:50]
    comments = StudentComment.objects.filter(
        student=student, is_deleted=False,
    ).order_by("-created_at")[:50]
    conversations = StudentConversation.objects.filter(
        student=student, is_deleted=False,
    ).order_by("-date")[:50]

    timeline = []
    for item in scores:
        timeline.append({"date": item.exam.date, "type": "成绩", "title": f"{item.exam.name} · {item.exam_subject.subject.name}", "detail": str(item.score) if item.score is not None else item.get_status_display()})
    for item in attendance_records:
        timeline.append({"date": item.date, "type": "考勤", "title": item.get_status_display(), "detail": item.reason})
    for item in classroom_records:
        timeline.append({"date": item.date, "type": "课堂纪律", "title": item.item.name if item.item else item.custom_content, "detail": item.description})
    for item in dorm_records:
        timeline.append({"date": item.date, "type": "宿舍纪律", "title": item.item.name if item.item else item.custom_content, "detail": item.description})
    for item in reward_records:
        timeline.append({"date": item.date, "type": "奖励", "title": item.item.name if item.item else item.custom_name, "detail": item.description})
    for item in comments:
        timeline.append({"date": item.created_at.date(), "type": "评语", "title": item.get_comment_type_display(), "detail": item.content})
    for item in conversations:
        timeline.append({"date": item.date, "type": "谈话", "title": item.reason or "学生谈话", "detail": item.main_content})
    # 评选荣誉
    from apps.evaluation.models import EvaluationResult
    honors = list(EvaluationResult.objects.filter(student=student).select_related("project").order_by("-created_at")[:50])
    for h in honors:
        timeline.append({
            "date": h.created_at.date(),
            "type": "荣誉",
            "title": f"{h.project.name} · 第{h.rank}名",
            "detail": f"{h.period_label} · {h.total_score}分",
        })
    timeline.sort(key=lambda item: item["date"], reverse=True)

    # ===== 历次考试折线图数据（总分/总排名 + 单科分/单科排名） =====
    exam_chart = {"labels": [], "totals": [], "total_ranks": [], "subjects": {}, "all_subjects": []}
    if student.school_class:
        all_exams = Exam.objects.filter(
            school_class=student.school_class, is_deleted=False,
        ).order_by("date")
        subject_series = {}
        all_subjects = set()

        for exam in all_exams:
            own_scores = list(Score.objects.filter(
                exam=exam, student=student, status="normal",
                score__isnull=False, is_deleted=False,
            ).select_related("exam_subject__subject"))
            if not own_scores:
                continue  # 该学生未参加或缺考，跳过这次考试

            idx = len(exam_chart["labels"])
            exam_chart["labels"].append(f"{exam.name}（{exam.date.strftime('%Y-%m-%d')}）")

            # 总分
            total = sum(float(s.score) for s in own_scores)
            exam_chart["totals"].append(round(total, 1))

            # 总分排名（与成绩分析页相同规则：并列跳名次）
            all_totals = Score.objects.filter(
                exam=exam, status="normal", score__isnull=False, is_deleted=False,
            ).values("student_id").annotate(total=Sum("score")).order_by("-total")
            total_rank = None
            current_r = 0
            prev_total = None
            for position, row in enumerate(all_totals, 1):
                if row["total"] != prev_total:
                    current_r = position
                    prev_total = row["total"]
                if row["student_id"] == student.pk:
                    total_rank = current_r
                    break
            exam_chart["total_ranks"].append(total_rank)

            # 单科分数与单科排名
            for s in own_scores:
                subj = s.exam_subject.subject.name
                all_subjects.add(subj)
                if subj not in subject_series:
                    subject_series[subj] = {"scores": [None] * idx, "ranks": [None] * idx}
                subject_series[subj]["scores"].append(float(s.score))
                better = Score.objects.filter(
                    exam=exam, exam_subject=s.exam_subject, status="normal",
                    score__gt=s.score, is_deleted=False,
                ).count()
                subject_series[subj]["ranks"].append(better + 1)

            # 补齐所有科目到最新长度（该考试没考的科目用 null 占位）
            for subj in subject_series:
                while len(subject_series[subj]["scores"]) < len(exam_chart["labels"]):
                    subject_series[subj]["scores"].append(None)
                    subject_series[subj]["ranks"].append(None)

        exam_chart["subjects"] = subject_series
        exam_chart["all_subjects"] = sorted(all_subjects)

    # ===== 按考试的成绩明细（用于成绩Tab表格） =====
    exam_score_detail = {}
    student_exams = []
    if student.school_class:
        student_exams = list(Exam.objects.filter(
            school_class=student.school_class, is_deleted=False,
        ).order_by("-date"))
        # 构建每个考试该学生的科目成绩 + 排名变化
        prev_exam_ranks = {}  # {subject_name: rank} 上一次考试的排名
        for exam in reversed(student_exams):  # 从早到晚遍历以计算排名变化
            own_scores = list(Score.objects.filter(
                exam=exam, student=student,
                is_deleted=False,
            ).select_related("exam_subject__subject").order_by("exam_subject__sort_order"))
            if not own_scores:
                continue
            subjects_data = []
            total_score = 0.0
            has_valid_scores = False
            for s in own_scores:
                subj_name = s.exam_subject.subject.name
                if s.status == "normal" and s.score is not None:
                    has_valid_scores = True
                    score_val = float(s.score)
                    total_score += score_val
                    current_rank = s.rank
                    # 对比上次该科目排名
                    prev_rank = prev_exam_ranks.get(subj_name)
                    if prev_rank is not None and current_rank is not None:
                        rank_change = prev_rank - current_rank  # 正值=进步
                    else:
                        rank_change = None
                    prev_exam_ranks[subj_name] = current_rank
                    subjects_data.append({
                        "subject_name": subj_name,
                        "score": score_val,
                        "rank": current_rank,
                        "rank_change": rank_change,
                    })

            if not has_valid_scores:
                continue

            # 计算总分排名
            total_rank = None
            all_totals = Score.objects.filter(
                exam=exam, status="normal", score__isnull=False, is_deleted=False,
            ).values("student_id").annotate(total=Sum("score")).order_by("-total")
            current_r = 0
            prev_total = None
            for position, row in enumerate(all_totals, 1):
                if row["total"] != prev_total:
                    current_r = position
                    prev_total = row["total"]
                if row["student_id"] == student.pk:
                    total_rank = current_r
                    break

            exam_score_detail[exam.pk] = {
                "exam": exam,
                "subjects": subjects_data,
                "total_score": round(total_score, 1),
                "total_rank": total_rank,
            }

    return render(request, "students/student_detail.html", {
        "student": student,
        "guardian": guardian,
        "scores": scores,
        "attendance_records": attendance_records,
        "classroom_records": classroom_records,
        "dorm_records": dorm_records,
        "reward_records": reward_records,
        "comments": comments,
        "conversations": conversations,
        "timeline": timeline[:100],
        "honors": honors,
        "exam_chart": exam_chart,
        "exam_score_detail": exam_score_detail,
        "student_exams": student_exams,
        "exam_filter": request.GET.get("exam_id", ""),
    })


HISTORY_MODULES = {
    "rewards": "奖惩记录", "points": "积分变动", "dormitory": "宿舍管理",
    "discipline": "课堂纪律", "attendance": "考勤管理",
    "evaluation": "评选荣誉",
}


@login_required
def growth(request):
    """成长足迹：查看每个学生的完整成长记录（多模块聚合时间线）。"""
    from apps.students.history_services import get_student_all_events
    current_class = get_current_class(request.user)
    students = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("name_pinyin", "name", "student_id") if current_class else []

    student_id = request.GET.get("student_id", "")
    selected = None
    if student_id:
        selected = Student.objects.filter(
            pk=student_id, school_class=current_class, is_deleted=False,
        ).first() if current_class else None

    events = []
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    module_filter = request.GET.get("module", "")
    if selected:
        events = get_student_all_events(selected, date_from, date_to)
        if module_filter:
            events = [e for e in events if e["module_key"] == module_filter]

    return render(request, "students/growth.html", {
        "students": students,
        "selected": selected,
        "events": events,
        "date_from": date_from,
        "date_to": date_to,
        "module_filter": module_filter,
        "modules": [
            ("", "全部"),
            ("evaluation", "荣誉评选"),
            ("rewards", "奖惩记录"),
            ("points", "积分变动"),
            ("discipline", "课堂纪律"),
            ("dormitory", "宿舍管理"),
            ("attendance", "考勤管理"),
            ("homework", "作业情况"),
            ("duty", "值日情况"),
        ],
    })


@login_required
def history_browser(request, module):
    from apps.students.history_services import get_student_events
    if module not in HISTORY_MODULES:
        return redirect("students:list")
    current_class = get_current_class(request.user)
    students = Student.objects.filter(school_class=current_class, is_deleted=False) if current_class else []
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    direction = request.GET.get("direction", "all")
    metric = request.GET.get("metric", "count")
    event_type = request.GET.get("event_type", "").strip()
    try:
        threshold = max(0, int(request.GET.get("threshold", "0") or 0))
    except ValueError:
        threshold = 0
    rows = []
    for student in students:
        events = get_student_events(student, module, date_from, date_to)
        if direction == "add":
            events = [event for event in events if event["points"] > 0]
        elif direction == "deduct":
            events = [event for event in events if event["points"] < 0 or event["adverse"]]
        if event_type:
            events = [event for event in events if event_type in event["code"] or event_type in event["item"]]
        value = len(events) if metric == "count" else sum(abs(event["points"]) for event in events)
        if not threshold or value >= threshold:
            rows.append({"student": student, "events": events, "value": value, "add_count": sum(1 for event in events if event["points"] > 0), "deduct_count": sum(1 for event in events if event["points"] < 0 or event["adverse"])})
    rows.sort(key=lambda row: (-row["value"], row["student"].student_id))
    return render(request, "students/history_browser.html", {
        "module": module, "module_name": HISTORY_MODULES[module], "rows": rows,
        "filters": {"date_from": date_from, "date_to": date_to, "direction": direction, "metric": metric, "threshold": threshold, "event_type": event_type},
    })


@login_required
def history_detail(request, module, pk):
    from apps.students.history_services import get_student_events
    if module not in HISTORY_MODULES:
        return redirect("students:list")
    current_class = get_current_class(request.user)
    student = get_object_or_404(Student, pk=pk, school_class=current_class, is_deleted=False)
    events = get_student_events(student, module, request.GET.get("date_from", ""), request.GET.get("date_to", ""))
    return render(request, "students/history_detail.html", {
        "student": student, "module": module, "module_name": HISTORY_MODULES[module], "events": events,
        "querystring": request.GET.urlencode(),
    })


# ========== 家长联系方式 ==========

@login_required
def guardian_list(request):
    """家长联系方式列表（仅本班）。

    每个学生一行：优先显示家长记录，没有家长记录时回退到学生表
    的联系人字段（旧版导入只写入了学生表），字段为空显示 -。
    """
    current_class = get_current_class(request.user)
    students = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).order_by("name_pinyin", "name", "student_id")

    search = request.GET.get("search", "")
    if search:
        students = students.filter(
            Q(name__icontains=search) | Q(student_id__icontains=search)
        )

    guardian_map = {
        g.student_id: g
        for g in Guardian.objects.filter(student__in=students, is_deleted=False)
    }
    rows = []
    for s in students:
        g = guardian_map.get(s.pk)
        if g:
            rel = g.display_contact_relation
            phone = g.display_contact_phone
            brel = g.display_backup_relation
            bphone = g.display_backup_phone
        else:
            rel, phone = s.primary_contact, s.primary_phone
            brel, bphone = s.secondary_contact, s.secondary_phone
        rows.append({
            "student": s,
            "guardian": g,
            "contact_relation": "" if rel == "未设置" else (rel or ""),
            "contact_phone": phone or "",
            "backup_relation": brel or "",
            "backup_phone": bphone or "",
        })

    paginator = Paginator(rows, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "students/guardian_list.html", {
        "page_obj": page_obj,
        "search": search,
    })


@login_required
def guardian_edit(request, pk):
    """编辑家长联系方式"""
    current_class = get_current_class(request.user)
    guardian = get_object_or_404(
        Guardian, pk=pk, student__school_class=current_class,
    )
    if request.method == "POST":
        form = GuardianForm(request.POST, instance=guardian)
        if form.is_valid():
            guardian = form.save()
            _sync_student_contact(guardian)
            messages.success(request, f"{guardian.student.name} 的家长信息已更新。")
            return redirect("students:guardian_list")
    else:
        form = GuardianForm(instance=guardian)
    return render(request, "students/guardian_form.html", {
        "form": form, "guardian": guardian,
    })


@login_required
def guardian_create(request, student_pk):
    """为指定学生创建家长联系方式"""
    current_class = get_current_class(request.user)
    student = get_object_or_404(Student, pk=student_pk, school_class=current_class)
    if request.method == "POST":
        form = GuardianForm(request.POST)
        if form.is_valid():
            guardian = form.save(commit=False)
            guardian.student = student
            guardian.save()
            _sync_student_contact(guardian)
            messages.success(request, f"{student.name} 的家长信息已添加。")
            return redirect("students:detail", pk=student.pk)
    else:
        form = GuardianForm()
    return render(request, "students/guardian_form.html", {
        "form": form, "student": student,
    })


def _sync_student_contact(guardian):
    student = guardian.student
    student.primary_contact = student.display_primary_contact
    student.primary_phone = student.display_primary_phone
    update_fields = ["primary_contact", "primary_phone"]
    if guardian.display_backup_relation:
        student.secondary_contact = guardian.display_backup_relation
        update_fields.append("secondary_contact")
    if guardian.display_backup_phone:
        student.secondary_phone = guardian.display_backup_phone
        update_fields.append("secondary_phone")
    update_fields.append("updated_at")
    student.save(update_fields=update_fields)
