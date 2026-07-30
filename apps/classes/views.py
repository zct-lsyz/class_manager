from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.classes.forms import SchoolClassForm, SemesterForm
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


# 占位视图：班委名单、学习小组、课程表
@login_required
def committee_list(request):
    """班委名单（占位）"""
    return render(request, "classes/placeholder.html", {
        "title": "班委名单",
        "message": "班委管理功能将在后续阶段实现。",
    })


@login_required
def study_groups(request):
    """学习小组（占位）"""
    return render(request, "classes/placeholder.html", {
        "title": "学习小组",
        "message": "学习小组功能将在后续阶段实现。",
    })


@login_required
def course_schedule(request):
    """课程表（占位）"""
    return render(request, "classes/placeholder.html", {
        "title": "课程表",
        "message": "课程表功能将在后续阶段实现。",
    })
