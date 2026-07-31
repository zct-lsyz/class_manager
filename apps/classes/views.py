from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.classes.models import (
    SchoolClass, Semester, CommitteeRole, CommitteeMember, StudyGroup, CourseScheduleEntry,
)
from apps.classes.forms import SchoolClassForm, SemesterForm
from apps.classes.subjects import Subject
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
    classes = SchoolClass.objects.all()
    semesters = Semester.objects.select_related("school_class").all()

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
            cls = form.save()
            # 如果设为当前班级，清除其他班级的 current 标志
            if cls.is_current:
                SchoolClass.objects.exclude(pk=cls.pk).update(is_current=False)
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
    cls = get_object_or_404(SchoolClass, pk=pk)
    if request.method == "POST":
        form = SchoolClassForm(request.POST, instance=cls)
        if form.is_valid():
            old_name = cls.name
            cls = form.save()
            if cls.is_current:
                SchoolClass.objects.exclude(pk=cls.pk).update(is_current=False)
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
def semester_create(request):
    """新增学期"""
    if request.method == "POST":
        form = SemesterForm(request.POST)
        if form.is_valid():
            sem = form.save()
            if sem.is_current:
                Semester.objects.exclude(pk=sem.pk).update(is_current=False)
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
    sem = get_object_or_404(Semester, pk=pk)
    if request.method == "POST":
        form = SemesterForm(request.POST, instance=sem)
        if form.is_valid():
            sem = form.save()
            if sem.is_current:
                Semester.objects.exclude(pk=sem.pk).update(is_current=False)
            messages.success(request, f"学期更新成功。")
            return redirect("classes:settings")
    else:
        form = SemesterForm(instance=sem)
    return render(request, "classes/semester_form.html", {"form": form, "sem": sem})


@login_required
def semester_archive(request, pk):
    """归档学期"""
    sem = get_object_or_404(Semester, pk=pk)
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
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    roles = CommitteeRole.objects.filter(school_class=current_class, is_active=True) if current_class else []
    members = CommitteeMember.objects.filter(
        is_active=True, semester=current_semester
    ).select_related("student", "role") if current_semester else []

    return render(request, "classes/committee_list.html", {
        "roles": roles, "members": members,
        "all_students": Student.objects.filter(
            school_class=current_class, is_deleted=False
        ).order_by("student_id") if current_class else [],
    })


@login_required
def committee_role_create(request):
    """新增班委职务"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
def committee_member_create(request):
    """任命班委"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
                Student, pk=student_id, school_class=current_class, is_deleted=False,
            )
            CommitteeMember.objects.update_or_create(
                role=role, student=student, semester=current_semester,
                defaults={"is_active": True},
            )
            _sync_student_positions(student)
            messages.success(request, f"{student.name} 已任命为「{role.name}」。")
        else:
            messages.error(request, "请选择职务和学生。")
    return redirect("classes:committee_list")


@login_required
def committee_member_remove(request, pk):
    """卸任班委"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
    current_class = SchoolClass.objects.filter(is_current=True).first()
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
def study_group_create(request):
    """创建学习小组"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()
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
    group = get_object_or_404(StudyGroup, pk=pk)
    if request.method == "POST":
        group.is_active = False
        group.save()
        messages.info(request, f"小组「{group.name}」已解散。")
    return redirect("classes:study_groups")


# ====== 课程表 ======

@login_required
def course_schedule(request):
    """课程表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    entries = CourseScheduleEntry.objects.filter(
        school_class=current_class, semester=current_semester
    ) if current_class else []

    # 构建网格: {weekday: {period: entry}}
    grid = {}
    max_period = 8
    for d in range(1, 8):
        grid[d] = {}
    for e in entries:
        grid[e.weekday][e.period] = e
        max_period = max(max_period, e.period)

    # 可选课程（统一科目主数据入口）
    subjects = Subject.objects.filter(is_active=True)

    if request.method == "POST":
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            CourseScheduleEntry.objects.filter(
                school_class=current_class, semester=current_semester
            ).delete()
            count = 0
            for key, value in request.POST.items():
                if key.startswith("cell_") and value.strip():
                    try:
                        _, weekday, period = key.split("_")
                        weekday, period = int(weekday), int(period)
                        CourseScheduleEntry.objects.create(
                            school_class=current_class, semester=current_semester,
                            weekday=weekday, period=period,
                            subject=value.strip(),
                            teacher=request.POST.get(f"teacher_{weekday}_{period}", "").strip(),
                            location=request.POST.get(f"location_{weekday}_{period}", "").strip(),
                        )
                        count += 1
                    except (ValueError, TypeError):
                        continue
        messages.success(request, f"课程表已保存（{count} 节课）。")
        return redirect("classes:course_schedule")

    return render(request, "classes/course_schedule.html", {
        "grid": grid, "max_period": max_period, "subjects": subjects,
        "periods": range(1, max_period + 1),
        "weekdays": range(1, 8),
    })
