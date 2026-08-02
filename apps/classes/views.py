from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Q

from apps.classes.utils import get_current_class
from apps.classes.models import (
    SchoolClass, Semester, CommitteeRole, CommitteeMember, StudyGroup,
    CourseScheduleEntry, CoursePeriod, Course, CourseScheduleSnapshot,
)
from apps.classes.forms import SchoolClassForm, SemesterForm
from apps.classes.subjects import Subject
from apps.classes.decorators import require_current_class
from apps.students.models import Student
from apps.audit.models import OperationLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


@login_required
def settings(request):
    """班级与学期设置"""
    classes = SchoolClass.objects.filter(created_by=request.user)
    semesters = Semester.objects.select_related("school_class").filter(school_class__created_by=request.user)

    class_form = SchoolClassForm()
    semester_form = SemesterForm()
    semester_form.fields["school_class"].queryset = classes

    context = {
        "classes": classes,
        "semesters": semesters,
        "class_form": class_form,
        "semester_form": semester_form,
    }
    return render(request, "classes/settings.html", context)


@login_required
def class_create(request):
    """新增班级"""
    if request.method == "POST":
        form = SchoolClassForm(request.POST)
        if form.is_valid():
            cls = form.save(commit=False)
            cls.created_by = request.user
            cls.save()
            # 如果设为当前班级，清除同一用户其他班级的 current 标志
            if cls.is_current:
                SchoolClass.objects.filter(created_by=request.user).exclude(pk=cls.pk).update(is_current=False)
            messages.success(request, f"班级「{cls.name}」创建成功。")
            OperationLog.objects.create(
                user=request.user, action="create", module="classes",
                object_repr=cls.name, detail=f"创建班级: {cls.name}",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("classes:settings")
        else:
            messages.error(request, "请修正表单中的错误。")
    return redirect("classes:settings")


@login_required
def class_edit(request, pk):
    """编辑班级"""
    cls = get_object_or_404(SchoolClass, pk=pk, created_by=request.user)
    if request.method == "POST":
        form = SchoolClassForm(request.POST, instance=cls)
        if form.is_valid():
            old_name = cls.name
            cls = form.save()
            if cls.is_current:
                SchoolClass.objects.filter(created_by=request.user).exclude(pk=cls.pk).update(is_current=False)
            messages.success(request, f"班级「{cls.name}」更新成功。")
            OperationLog.objects.create(
                user=request.user, action="edit", module="classes",
                object_repr=f"{old_name} -> {cls.name}",
                detail=f"编辑班级: {old_name} -> {cls.name}",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("classes:settings")
    else:
        form = SchoolClassForm(instance=cls)
    return render(request, "classes/class_form.html", {"form": form, "cls": cls})


@login_required
def class_delete(request, pk):
    """删除班级（需输入班级名称二次确认）。
    级联删除：该班级的学期、学生，以及学生相关的成绩/评语/谈话/考勤/奖惩等全部数据。
    """
    cls = get_object_or_404(SchoolClass, pk=pk, created_by=request.user)
    if request.method == "POST":
        confirm_name = request.POST.get("confirm_name", "").strip()
        if confirm_name != cls.name:
            messages.error(request, "输入的班级名称不匹配，删除已取消。")
            return redirect("classes:settings")

        from django.db import transaction
        student_count = Student.objects.filter(school_class=cls).count()
        with transaction.atomic():
            # 学生.school_class 为 SET_NULL，需先手动删除学生（CASCADE 清理学生全部关联数据）
            Student.objects.filter(school_class=cls).delete()
            # 班级删除后，CASCADE 到学期、考试、值日、宿舍、评语模板、课程表等
            cls.delete()

        OperationLog.objects.create(
            user=request.user, action="delete", module="classes",
            object_repr=cls.name,
            detail=f"删除班级: {cls.name}（含 {student_count} 名学生及全部关联数据）",
            ip_address=get_client_ip(request), success=True,
        )
        messages.warning(request, f"班级「{cls.name}」已删除，含 {student_count} 名学生及全部关联数据。")
    return redirect("classes:settings")


@login_required
def semester_create(request):
    """新增学期"""
    if request.method == "POST":
        form = SemesterForm(request.POST)
        form.fields["school_class"].queryset = SchoolClass.objects.filter(
            created_by=request.user,
        )
        if form.is_valid():
            sem = form.save(commit=False)
            # 如果该班级没有当前学期，自动将新创建的学期设为当前学期
            if not sem.is_current:
                has_current = Semester.objects.filter(
                    school_class=sem.school_class, is_current=True,
                ).exists()
                if not has_current:
                    sem.is_current = True
            sem.save()
            if sem.is_current:
                Semester.objects.filter(
                    school_class=sem.school_class,
                ).exclude(pk=sem.pk).update(is_current=False)
            messages.success(request, f"学期「{sem.get_display_name()}」创建成功。")
            OperationLog.objects.create(
                user=request.user, action="create", module="semesters",
                object_repr=sem.get_display_name(),
                detail=f"创建学期: {sem.get_display_name()}",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("classes:settings")
        else:
            messages.error(request, "请修正表单中的错误。")
    return redirect("classes:settings")


@login_required
def semester_edit(request, pk):
    """编辑学期"""
    sem = get_object_or_404(Semester, pk=pk, school_class__created_by=request.user)
    if request.method == "POST":
        form = SemesterForm(request.POST, instance=sem)
        if form.is_valid():
            sem = form.save()
            if sem.is_current:
                Semester.objects.filter(
                    school_class=sem.school_class,
                ).exclude(pk=sem.pk).update(is_current=False)
            messages.success(request, f"学期「{sem.get_display_name()}」更新成功。")
            return redirect("classes:settings")
    else:
        form = SemesterForm(instance=sem)
    return render(request, "classes/semester_form.html", {"form": form, "sem": sem})


@login_required
def semester_archive(request, pk):
    """归档学期"""
    sem = get_object_or_404(Semester, pk=pk, school_class__created_by=request.user)
    if request.method == "POST":
        sem.is_archived = True
        if sem.is_current:
            sem.is_current = False
        sem.save()
        messages.success(request, f"学期「{sem.get_display_name()}」已归档。")
        OperationLog.objects.create(
            user=request.user, action="archive", module="semesters",
            object_repr=sem.get_display_name(),
            detail=f"归档学期: {sem.get_display_name()}",
            ip_address=get_client_ip(request), success=True,
        )
    return redirect("classes:settings")


# ====== 班委名单 ======

@login_required
def committee_list(request):
    """班委名单"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    roles = CommitteeRole.objects.filter(school_class=current_class, is_active=True) if current_class else []
    members = CommitteeMember.objects.filter(
        is_active=True, role__school_class=current_class,
    ).select_related("student", "role") if current_class else []
    if current_semester:
        members = members.filter(Q(semester=current_semester) | Q(semester__isnull=True))

    return render(request, "classes/committee_list.html", {
        "roles": roles, "members": members,
        "all_students": Student.objects.filter(
            Q(school_class=current_class) | Q(school_class__isnull=True), is_deleted=False
        ).order_by("student_id") if current_class else [],
    })


@login_required
@require_current_class
def committee_role_create(request):
    """新增班委职务"""
    current_class = get_current_class(request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        if name:
            CommitteeRole.objects.create(
                school_class=current_class, name=name, description=description,
            )
            messages.success(request, f"职务「{name}」已添加。")
        else:
            messages.error(request, "职务名称不能为空。")
    return redirect("classes:committee_list")


@login_required
@require_current_class
def committee_member_create(request):
    """任命班委"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        role_id = request.POST.get("role", "")
        student_id = request.POST.get("student", "")
        if role_id and student_id:
            from apps.students.models import Student
            role = get_object_or_404(
                CommitteeRole, pk=role_id, school_class=current_class,
            )
            student = get_object_or_404(
                Student, Q(school_class=current_class) | Q(school_class__isnull=True),
                pk=student_id, is_deleted=False,
            )
            if not student.school_class:
                student.school_class = current_class
                student.save(update_fields=["school_class", "updated_at"])
            member, created = CommitteeMember.objects.get_or_create(
                role=role, student=student, semester=current_semester,
                defaults={"is_active": True, "appointment_date": timezone.localdate()},
            )
            if not created:
                member.is_active = True
                # 首次任命时自动记录任命日期；已有任命日期则保留
                if not member.appointment_date:
                    member.appointment_date = timezone.localdate()
                member.save(update_fields=["is_active", "appointment_date", "updated_at"])
            _sync_student_positions(student)
            messages.success(request, f"{student.name} 已任命为「{role.name}」。")
        else:
            messages.error(request, "请选择职务和学生。")
    return redirect("classes:committee_list")


@login_required
def committee_member_remove(request, pk):
    """卸任班委"""
    current_class = get_current_class(request.user)
    member = get_object_or_404(
        CommitteeMember, pk=pk, role__school_class=current_class,
    )
    if request.method == "POST":
        member.is_active = False
        member.save()
        _sync_student_positions(member.student)
        messages.info(request, f"{member.student.name} 已卸任「{member.role.name}」。")
    return redirect("classes:committee_list")


def _sync_student_positions(student):
    student.class_position = "、".join(
        student.committee_memberships.filter(
            is_active=True, role__is_active=True,
        ).select_related("role").values_list("role__name", flat=True)
    )
    student.save(update_fields=["class_position", "updated_at"])


# ====== 学习小组 ======

@login_required
def study_groups(request):
    """学习小组"""
    current_class = get_current_class(request.user)
    groups = StudyGroup.objects.filter(
        school_class=current_class, is_active=True
    ).select_related("leader").prefetch_related("members") if current_class else []

    ungrouped = Student.objects.filter(
        school_class=current_class, is_deleted=False
    ).exclude(study_groups__in=[g.pk for g in groups]) if current_class else []

    return render(request, "classes/study_groups.html", {
        "groups": groups, "ungrouped": ungrouped,
        "all_students": Student.objects.filter(
            school_class=current_class, is_deleted=False
        ).order_by("student_id") if current_class else [],
    })


@login_required
@require_current_class
def study_group_create(request):
    """创建学习小组"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        leader_id = request.POST.get("leader", "")
        member_ids = request.POST.getlist("members")
        if name:
            group = StudyGroup.objects.create(
                school_class=current_class, semester=current_semester,
                name=name,
                leader_id=int(leader_id) if leader_id else None,
            )
            if member_ids:
                group.members.set(member_ids)
            messages.success(request, f"小组「{name}」已创建（{len(member_ids)} 名成员）。")
        else:
            messages.error(request, "组名不能为空。")
    return redirect("classes:study_groups")


@login_required
def study_group_delete(request, pk):
    """删除学习小组"""
    current_class = get_current_class(request.user)
    group = get_object_or_404(StudyGroup, pk=pk, school_class=current_class)
    if request.method == "POST":
        group.is_active = False
        group.save()
        messages.info(request, f"小组「{group.name}」已解散。")
    return redirect("classes:study_groups")


# ====== 课程表 ======

@login_required
@require_current_class
def course_schedule(request):
    """课程表：课程管理 + 下拉选课 + 调课 + 保存快照"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    entries = CourseScheduleEntry.objects.filter(
        school_class=current_class, semester=current_semester,
    ).select_related("course") if current_class else []

    # 构建网格: {weekday: {period: entry}}
    grid = {}
    period_rows = CoursePeriod.objects.filter(
        school_class=current_class, semester=current_semester,
    ) if current_class else []
    period_settings = {row.period: row for row in period_rows}
    max_period = max(period_settings.keys(), default=8)
    for d in range(1, 8):
        grid[d] = {}
    for e in entries:
        grid[e.weekday][e.period] = e
        max_period = max(max_period, e.period)

    # 当前班级已添加的课程（含授课教师）
    courses = Course.objects.filter(
        school_class=current_class,
    ).order_by("sort_order", "name") if current_class else []

    if request.method == "POST":
        if not current_class:
            messages.error(request, "请先设置当前班级。")
            return redirect("classes:settings")
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            try:
                max_period = min(20, max(1, int(request.POST.get("period_count", max_period))))
            except (TypeError, ValueError):
                max_period = 8
            CoursePeriod.objects.filter(
                school_class=current_class, semester=current_semester,
                period__gt=max_period,
            ).delete()
            for period in range(1, max_period + 1):
                period_name = request.POST.get(f"period_name_{period}", "").strip()
                CoursePeriod.objects.update_or_create(
                    school_class=current_class, semester=current_semester, period=period,
                    defaults={
                        "name": period_name,
                        "start_time": request.POST.get(f"start_time_{period}") or None,
                        "end_time": request.POST.get(f"end_time_{period}") or None,
                    },
                )
            # 收集新网格数据用于快照
            course_map = {str(c.pk): c for c in courses}
            new_grid_data = {}
            count = 0
            for key, value in request.POST.items():
                if not key.startswith("cell_"):
                    continue
                try:
                    _, weekday, period = key.split("_")
                    weekday, period = int(weekday), int(period)
                    if weekday not in range(1, 8) or period not in range(1, max_period + 1):
                        continue
                except (ValueError, TypeError):
                    continue
                cell_value = value.strip()
                if not cell_value:
                    continue
                course_obj = course_map.get(cell_value)
                subject_name = course_obj.name if course_obj else cell_value
                teacher_name = course_obj.teacher if course_obj else ""
                CourseScheduleEntry.objects.update_or_create(
                    school_class=current_class, semester=current_semester,
                    weekday=weekday, period=period,
                    defaults={
                        "course": course_obj,
                        "subject": subject_name,
                        "teacher": teacher_name,
                    },
                )
                new_grid_data[f"{weekday}_{period}"] = {
                    "subject": subject_name,
                    "teacher": teacher_name,
                }
                count += 1
            # 清掉这次没有填的空格子（保留原条目，避免误删历史）
            existing_keys = {f"{e.weekday}_{e.period}" for e in entries}
            for key in existing_keys - set(new_grid_data.keys()):
                w, p = key.split("_")
                CourseScheduleEntry.objects.filter(
                    school_class=current_class, semester=current_semester,
                    weekday=int(w), period=int(p),
                ).delete()

            # 生成历史快照（内容有变化才生成）
            if new_grid_data:
                latest = CourseScheduleSnapshot.objects.filter(
                    school_class=current_class, semester=current_semester,
                ).order_by("-created_at").first()
                if not latest or latest.data != new_grid_data:
                    version = CourseScheduleSnapshot.objects.filter(
                        school_class=current_class, semester=current_semester,
                    ).count() + 1
                    CourseScheduleSnapshot.objects.create(
                        school_class=current_class, semester=current_semester,
                        label=f"课表 v{version}",
                        data=new_grid_data,
                    )
        messages.success(request, f"课程表已保存（{count} 节课），已生成历史快照。")
        return redirect("classes:course_schedule")

    edit_mode = request.GET.get("edit") == "1"
    return render(request, "classes/course_schedule.html", {
        "grid": grid, "max_period": max_period, "courses": courses,
        "period_settings": period_settings,
        "periods": range(1, max_period + 1),
        "weekdays": range(1, 8),
        "edit_mode": edit_mode,
    })


def _course_color(name):
    """与前端一致的科目哈希背景色（hsl(hash%360 70% 92%) → RGB hex）"""
    if not name:
        return None
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    hue = h % 360
    s, l = 0.70, 0.92
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = l - c / 2
    if hue < 60:
        r, g, b = c, x, 0
    elif hue < 120:
        r, g, b = x, c, 0
    elif hue < 180:
        r, g, b = 0, c, x
    elif hue < 240:
        r, g, b = 0, x, c
    elif hue < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return "%02X%02X%02X" % (
        round((r + m) * 255), round((g + m) * 255), round((b + m) * 255),
    )


@login_required
def course_schedule_export(request):
    """导出课程表 Excel（保留各科目背景色）。"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None
    if not current_class:
        return redirect("classes:settings")

    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Alignment, Font, Border, Side
    from openpyxl.utils import get_column_letter
    from django.http import HttpResponse

    entries = {
        (e.weekday, e.period): e for e in CourseScheduleEntry.objects.filter(
            school_class=current_class, semester=current_semester,
        )
    }
    period_settings = {
        p.period: p for p in CoursePeriod.objects.filter(
            school_class=current_class, semester=current_semester,
        )
    }
    max_period = max([p for (_d, p) in entries.keys()] + list(period_settings.keys()) + [8])

    wb = Workbook()
    ws = wb.active
    ws.title = "课程表"
    weekday_labels = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    ws.cell(1, 1, "节次")
    for d in range(1, 8):
        ws.cell(1, d + 1, weekday_labels[d])

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", start_color="1A73E8")
    for col in range(1, 9):
        cell = ws.cell(1, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for period in range(1, max_period + 1):
        row = period + 1
        ps = period_settings.get(period)
        # 行标题以手动命名的节次名称为准；无命名则只显示时间
        time_label = ps.name if ps and ps.name else ""
        if ps and ps.start_time:
            time_label += f"\n{ps.start_time.strftime('%H:%M')}" + (
                f"-{ps.end_time.strftime('%H:%M')}" if ps.end_time else ""
            )
        cell = ws.cell(row, 1, time_label)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = border
        for d in range(1, 8):
            entry = entries.get((d, period))
            cell = ws.cell(row, d + 1)
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            if entry:
                cell.value = entry.subject + (f"\n{entry.teacher}" if entry.teacher else "")
                color = _course_color(entry.subject)
                if color:
                    cell.fill = PatternFill("solid", start_color=color)

    ws.column_dimensions["A"].width = 14
    for d in range(1, 8):
        ws.column_dimensions[get_column_letter(d + 1)].width = 16
    ws.row_dimensions[1].height = 22

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="course_schedule.xlsx"'
    wb.save(response)
    return response


# ====== 课程表 Excel 导入 ======

@login_required
@require_current_class
def course_schedule_import(request):
    """从 Excel 导入课程表（格式与导出模板一致：节次 + 周一~周日 各列）"""
    current_class = get_current_class(request.user)
    if request.method != "POST":
        return redirect("classes:course_schedule")
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    uploaded = request.FILES.get("file")
    if not uploaded or not uploaded.name.lower().endswith(".xlsx"):
        messages.error(request, "请上传 XLSX 课表文件。")
        return redirect("classes:course_schedule")

    from django.db import transaction
    from openpyxl import load_workbook
    from django.utils import timezone
    from datetime import datetime, time as dtime
    try:
        wb = load_workbook(uploaded, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    except Exception as exc:
        messages.error(request, f"文件解析失败：{exc}")
        return redirect("classes:course_schedule")
    if not rows:
        messages.error(request, "文件为空。")
        return redirect("classes:course_schedule")

    # 定位表头行（含「节次」）
    header_idx = None
    for i, row in enumerate(rows):
        texts = [str(c).strip() if c is not None else "" for c in row]
        if any("节次" in t for t in texts):
            header_idx = i
            break
    if header_idx is None:
        messages.error(request, "未找到表头（需含「节次」列）。")
        return redirect("classes:course_schedule")

    headers = [str(c).strip() if c is not None else "" for c in rows[header_idx]]
    # 周列索引：周一~周日
    weekday_cols = {}
    for idx, h in enumerate(headers):
        for d in range(1, 8):
            if h == f"周{d}" or h in ("周一", "周二", "周三", "周四", "周五", "周六", "周日"):
                wd = d if h == f"周{d}" else ("周一", "周二", "周三", "周四", "周五", "周六", "周日").index(h) + 1
                weekday_cols[wd] = idx
    if not weekday_cols:
        messages.error(request, "未找到周一~周日列。")
        return redirect("classes:course_schedule")

    imported = 0
    created_courses = 0
    max_period = 0
    with transaction.atomic():
        for row in rows[header_idx + 1:]:
            if row is None or all(c is None or str(c).strip() == "" for c in row):
                continue
            period_label = str(row[0]).strip() if row[0] is not None else ""
            if not period_label:
                continue
            # 第1行数据 = 第1节，行顺序即节次
            period = max_period + 1
            max_period = period

            # 解析节次名称与起止时间：名称[换行]HH:MM-HH:MM
            name = period_label.splitlines()[0].strip() if period_label else ""
            times = None
            for line in period_label.splitlines()[1:]:
                if "-" in line and ":" in line:
                    times = line.strip()
                    break
            start_t, end_t = None, None
            if times:
                try:
                    s_part, e_part = times.split("-", 1)
                    start_t = datetime.strptime(s_part.strip(), "%H:%M").time()
                    end_t = datetime.strptime(e_part.strip(), "%H:%M").time()
                except (ValueError, TypeError):
                    pass

            CoursePeriod.objects.update_or_create(
                school_class=current_class, semester=current_semester, period=period,
                defaults={
                    "name": name,
                    "start_time": start_t,
                    "end_time": end_t,
                },
            )

            for d, col in weekday_cols.items():
                if col >= len(row):
                    continue
                cell = row[col]
                if cell is None or str(cell).strip() == "":
                    continue
                cell_text = str(cell).strip()
                lines = cell_text.splitlines()
                course_name = lines[0].strip() if lines else ""
                teacher = lines[1].strip() if len(lines) > 1 else ""
                if not course_name:
                    continue
                course, created = Course.objects.get_or_create(
                    school_class=current_class, name=course_name,
                    defaults={"teacher": teacher},
                )
                if created:
                    created_courses += 1
                CourseScheduleEntry.objects.update_or_create(
                    school_class=current_class, semester=current_semester,
                    weekday=d, period=period,
                    defaults={
                        "course": course,
                        "subject": course_name,
                        "teacher": teacher,
                    },
                )
                imported += 1

    # 节数调整到导入的最大节次
    CoursePeriod.objects.filter(
        school_class=current_class, semester=current_semester,
        period__gt=max_period,
    ).delete()

    messages.success(
        request,
        f"课表导入完成：共 {imported} 节课"
        + (f"，自动新增 {created_courses} 门课程" if created_courses else "")
        + "。",
    )
    return redirect("classes:course_schedule")


# ====== 课程管理 ======

@login_required
@require_current_class
def course_create(request):
    """添加课程（含授课教师）"""
    current_class = get_current_class(request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        teacher = request.POST.get("teacher", "").strip()
        if not name:
            messages.error(request, "课程名称不能为空。")
        elif Course.objects.filter(school_class=current_class, name=name).exists():
            messages.warning(request, f"课程「{name}」已存在。")
        else:
            Course.objects.create(
                school_class=current_class, name=name, teacher=teacher,
            )
            messages.success(request, f"课程「{name}」已添加。")
    return redirect("classes:course_schedule")


@login_required
@require_current_class
def course_edit(request, pk):
    """修改课程"""
    current_class = get_current_class(request.user)
    course = get_object_or_404(Course, pk=pk, school_class=current_class)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        teacher = request.POST.get("teacher", "").strip()
        if not name:
            messages.error(request, "课程名称不能为空。")
        else:
            dup = Course.objects.filter(
                school_class=current_class, name=name,
            ).exclude(pk=course.pk).exists()
            if dup:
                messages.warning(request, f"课程「{name}」已存在。")
            else:
                old_name = course.name
                course.name = name
                course.teacher = teacher
                course.save(update_fields=["name", "teacher", "updated_at"])
                # 同步已排课表条目中的科目名
                CourseScheduleEntry.objects.filter(course=course).update(
                    subject=name, teacher=teacher,
                )
                messages.success(request, f"课程「{old_name}」已更新为「{name}」。")
    return redirect("classes:course_schedule")


@login_required
@require_current_class
def course_delete(request, pk):
    """删除课程"""
    current_class = get_current_class(request.user)
    course = get_object_or_404(Course, pk=pk, school_class=current_class)
    if request.method == "POST":
        # 课表条目解除关联并清空科目（SET_NULL 后清空 subject 显示）
        CourseScheduleEntry.objects.filter(course=course).update(
            course=None, subject="", teacher="",
        )
        messages.info(request, f"课程「{course.name}」已删除，相关课表位置已清空。")
        course.delete()
    return redirect("classes:course_schedule")


# ====== 课程表历史 ======

@login_required
@require_current_class
def course_schedule_history(request):
    """课程表历史版本列表"""
    current_class = get_current_class(request.user)
    snapshots = CourseScheduleSnapshot.objects.filter(
        school_class=current_class,
    ).select_related("semester").order_by("-created_at")
    return render(request, "classes/course_schedule_history.html", {
        "snapshots": snapshots,
    })


@login_required
@require_current_class
def course_schedule_view(request, pk):
    """查看某个历史版本的课表（只读）"""
    current_class = get_current_class(request.user)
    snapshot = get_object_or_404(
        CourseScheduleSnapshot, pk=pk, school_class=current_class,
    )
    period_settings = {
        row.period: row for row in CoursePeriod.objects.filter(
            school_class=current_class, semester=snapshot.semester,
        )
    }
    max_period = max(
        [int(k.split("_")[1]) for k in snapshot.data.keys()] + [8]
    )
    return render(request, "classes/course_schedule_view.html", {
        "snapshot": snapshot,
        "period_settings": period_settings,
        "max_period": max_period,
        "periods": range(1, max_period + 1),
        "weekdays": range(1, 8),
    })
