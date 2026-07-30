from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q

from apps.students.models import Student, Guardian
from apps.students.forms import StudentForm, GuardianForm
from apps.classes.models import SchoolClass
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
    students = Student.objects.filter(is_deleted=False)

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

    classes = SchoolClass.objects.all()

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
            student = form.save()
            messages.success(request, f"学生「{student.name}」添加成功。")
            OperationLog.objects.create(
                user=request.user, action="create", module="students",
                object_repr=student.name,
                detail=f"新增学生: {student.name} (学号: {student.student_id})",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("students:list")
    else:
        form = StudentForm()
        # 默认选中当前班级
        current_class = SchoolClass.objects.filter(is_current=True).first()
        if current_class:
            form.fields["school_class"].initial = current_class.pk
    return render(request, "students/student_form.html", {"form": form, "title": "新增学生"})


@login_required
def student_edit(request, pk):
    """编辑学生"""
    student = get_object_or_404(Student, pk=pk)
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
    else:
        form = StudentForm(instance=student)
    return render(request, "students/student_form.html", {
        "form": form, "student": student, "title": "编辑学生",
    })


@login_required
def student_delete(request, pk):
    """删除学生（软删除）"""
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        student.soft_delete()
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
    student = get_object_or_404(Student, pk=pk)
    guardian = Guardian.objects.filter(student=student).first()
    return render(request, "students/student_detail.html", {
        "student": student,
        "guardian": guardian,
    })


# ========== 家长联系方式 ==========

@login_required
def guardian_list(request):
    """家长联系方式列表"""
    guardians = Guardian.objects.select_related("student").all()

    search = request.GET.get("search", "")
    if search:
        guardians = guardians.filter(
            Q(student__name__icontains=search) |
            Q(student__student_id__icontains=search)
        )

    paginator = Paginator(guardians, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "students/guardian_list.html", {
        "page_obj": page_obj,
        "search": search,
    })


@login_required
def guardian_edit(request, pk):
    """编辑家长联系方式"""
    guardian = get_object_or_404(Guardian, pk=pk)
    if request.method == "POST":
        form = GuardianForm(request.POST, instance=guardian)
        if form.is_valid():
            guardian = form.save()
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
    student = get_object_or_404(Student, pk=student_pk)
    if request.method == "POST":
        form = GuardianForm(request.POST)
        if form.is_valid():
            guardian = form.save(commit=False)
            guardian.student = student
            guardian.save()
            messages.success(request, f"{student.name} 的家长信息已添加。")
            return redirect("students:detail", pk=student.pk)
    else:
        form = GuardianForm()
    return render(request, "students/guardian_form.html", {
        "form": form, "student": student,
    })
