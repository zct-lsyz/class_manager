from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from apps.discipline.models import ConfigurableItem, ClassroomDisciplineRecord, DormDisciplineRecord
from apps.discipline.forms import ConfigurableItemForm, ClassroomDisciplineForm, DormDisciplineForm
from apps.classes.models import SchoolClass, Semester


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


# ====== 课堂纪律条目 ======

@login_required
def classroom_items(request):
    """课堂纪律条目配置"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    items = ConfigurableItem.objects.filter(
        school_class=current_class, module="classroom_discipline"
    ) if current_class else []

    if request.method == "POST":
        form = ConfigurableItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.school_class = current_class
            item.module = "classroom_discipline"
            item.save()
            messages.success(request, f"条目「{item.name}」已添加。")
            return redirect("discipline:classroom_items")
    else:
        form = ConfigurableItemForm()

    return render(request, "discipline/item_list.html", {
        "items": items, "form": form, "module": "classroom_discipline", "title": "课堂纪律条目",
    })


# ====== 课堂纪律事件 ======

@login_required
def classroom_list(request):
    """课堂纪律列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    records = ClassroomDisciplineRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "discipline/classroom_list.html", {"page_obj": page_obj})


@login_required
def classroom_create(request):
    """登记课堂纪律"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    if request.method == "POST":
        form = ClassroomDisciplineForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            record.save()
            messages.success(request, "课堂纪律记录已保存。")
            return redirect("discipline:classroom_list")
    else:
        form = ClassroomDisciplineForm()

    return render(request, "discipline/classroom_form.html", {"form": form, "title": "登记课堂纪律"})


@login_required
def classroom_edit(request, pk):
    """编辑课堂纪律事件"""
    record = get_object_or_404(ClassroomDisciplineRecord, pk=pk)
    if request.method == "POST":
        form = ClassroomDisciplineForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "课堂纪律记录已更新。")
            return redirect("discipline:classroom_list")
    else:
        form = ClassroomDisciplineForm(instance=record)
    return render(request, "discipline/classroom_form.html", {"form": form, "title": "编辑课堂纪律"})


@login_required
def classroom_delete(request, pk):
    """删除课堂纪律事件（软删除）"""
    record = get_object_or_404(ClassroomDisciplineRecord, pk=pk)
    if request.method == "POST":
        record.is_deleted = True
        record.save(update_fields=["is_deleted"])
        messages.info(request, "课堂纪律记录已删除。")
    return redirect("discipline:classroom_list")


@login_required
def classroom_follow_up(request, pk):
    """处理跟进"""
    record = get_object_or_404(ClassroomDisciplineRecord, pk=pk)
    if request.method == "POST":
        record.follow_up_date = request.POST.get("follow_up_date") or None
        record.follow_up_result = request.POST.get("follow_up_result", "").strip()
        record.needs_follow_up = False
        record.save()
        messages.success(request, "跟进处理已保存。")
    return redirect("discipline:classroom_list")


# ====== 宿舍纪律条目 ======

@login_required
def dorm_items(request):
    """宿舍纪律条目配置"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    items = ConfigurableItem.objects.filter(
        school_class=current_class, module="dorm_discipline"
    ) if current_class else []

    if request.method == "POST":
        form = ConfigurableItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.school_class = current_class
            item.module = "dorm_discipline"
            item.save()
            messages.success(request, f"条目「{item.name}」已添加。")
            return redirect("discipline:dorm_items")
    else:
        form = ConfigurableItemForm()

    return render(request, "discipline/item_list.html", {
        "items": items, "form": form, "module": "dorm_discipline", "title": "宿舍纪律条目",
    })


# ====== 宿舍纪律事件 ======

@login_required
def dorm_list(request):
    """宿舍纪律列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    records = DormDisciplineRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item", "dorm_room").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)
    return render(request, "discipline/dorm_list.html", {"page_obj": page_obj})


@login_required
def dorm_create(request):
    """登记宿舍纪律"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = DormDisciplineForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            record.save()
            messages.success(request, "宿舍纪律记录已保存。")
            return redirect("discipline:dorm_list")
    else:
        form = DormDisciplineForm()
    return render(request, "discipline/dorm_form.html", {"form": form, "title": "登记宿舍纪律"})


@login_required
def dorm_edit(request, pk):
    """编辑宿舍纪律"""
    record = get_object_or_404(DormDisciplineRecord, pk=pk)
    if request.method == "POST":
        form = DormDisciplineForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "宿舍纪律记录已更新。")
            return redirect("discipline:dorm_list")
    else:
        form = DormDisciplineForm(instance=record)
    return render(request, "discipline/dorm_form.html", {"form": form, "title": "编辑宿舍纪律"})


@login_required
def dorm_delete(request, pk):
    """删除宿舍纪律"""
    record = get_object_or_404(DormDisciplineRecord, pk=pk)
    if request.method == "POST":
        record.is_deleted = True
        record.save(update_fields=["is_deleted"])
        messages.info(request, "宿舍纪律记录已删除。")
    return redirect("discipline:dorm_list")


@login_required
def dorm_follow_up(request, pk):
    """宿舍纪律跟进处理"""
    record = get_object_or_404(DormDisciplineRecord, pk=pk)
    if request.method == "POST":
        record.follow_up_date = request.POST.get("follow_up_date") or None
        record.follow_up_result = request.POST.get("follow_up_result", "").strip()
        record.needs_follow_up = False
        record.save()
        messages.success(request, "跟进处理已保存。")
    return redirect("discipline:dorm_list")


# ====== 条目删除 ======

@login_required
def item_delete(request, pk):
    """删除可配置条目"""
    item = get_object_or_404(ConfigurableItem, pk=pk)
    module = item.module
    if request.method == "POST":
        item.delete()
        messages.info(request, f"条目「{item.name}」已删除。")
    if module == "classroom_discipline":
        return redirect("discipline:classroom_items")
    return redirect("discipline:dorm_items")
