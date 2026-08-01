from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from apps.discipline.models import ConfigurableItem, ClassroomDisciplineRecord, DormDisciplineRecord
from apps.discipline.forms import ConfigurableItemForm, ClassroomDisciplineForm, DormDisciplineForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.audit.services import soft_delete


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


def _sync_discipline_points(record):
    """课堂/宿舍纪律的加减分同步到统一积分明细。

    points_deducted 语义：正数扣分、负数加分。
    """
    from apps.rewards.services import sync_source_point
    item_name = record.item.name if record.item else record.custom_content or "纪律事件"
    reason = f"{record.get_severity_display()}：{item_name}"
    source_type = (
        "classroom_discipline"
        if isinstance(record, ClassroomDisciplineRecord)
        else "dorm_discipline"
    )
    sync_source_point(
        student=record.student, school_class=record.school_class,
        semester=record.semester, date=record.date,
        points=-record.points_deducted, reason=reason,
        source_type=source_type, source_id=record.pk,
    )


# ====== 课堂纪律条目 ======

@login_required
@require_current_class
def classroom_items(request):
    """课堂纪律条目配置"""
    current_class = get_current_class(request.user)
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
    current_class = get_current_class(request.user)
    records = ClassroomDisciplineRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "discipline/classroom_list.html", {"page_obj": page_obj})


@login_required
@require_current_class
def classroom_create(request):
    """登记课堂纪律"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    if request.method == "POST":
        form = ClassroomDisciplineForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            record.save()
            _sync_discipline_points(record)
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
            _sync_discipline_points(record)
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
        from apps.rewards.services import unsync_source_point
        unsync_source_point("classroom_discipline", record.pk)
        soft_delete(
            record,
            user=request.user,
            module="discipline",
            model_name="classroomdiscipline",
        )
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
@require_current_class
def dorm_items(request):
    """宿舍纪律条目配置"""
    current_class = get_current_class(request.user)
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
    current_class = get_current_class(request.user)
    records = DormDisciplineRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item", "dorm_room").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)
    return render(request, "discipline/dorm_list.html", {"page_obj": page_obj})


@login_required
@require_current_class
def dorm_create(request):
    """登记宿舍纪律"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        form = DormDisciplineForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            record.save()
            _sync_discipline_points(record)
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
            _sync_discipline_points(record)
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
        from apps.rewards.services import unsync_source_point
        unsync_source_point("dorm_discipline", record.pk)
        soft_delete(
            record,
            user=request.user,
            module="dormitory",
            model_name="dormdiscipline",
        )
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


# ====== 条目编辑与删除 ======

@login_required
def item_edit(request, pk):
    """编辑课堂或宿舍纪律条目。"""
    current_class = get_current_class(request.user)
    item = get_object_or_404(
        ConfigurableItem, pk=pk, school_class=current_class
    )
    if request.method == "POST":
        form = ConfigurableItemForm(request.POST, instance=item)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.module = item.module
            updated.school_class = current_class
            updated.save()
            messages.success(request, f"条目「{updated.name}」已更新。")
            target = (
                "discipline:classroom_items"
                if item.module == "classroom_discipline"
                else "discipline:dorm_items"
            )
            return redirect(target)
    else:
        form = ConfigurableItemForm(instance=item)
    return render(
        request,
        "discipline/item_form.html",
        {"form": form, "item": item},
    )

@login_required
def item_delete(request, pk):
    """删除可配置条目"""
    current_class = get_current_class(request.user)
    item = get_object_or_404(ConfigurableItem, pk=pk, school_class=current_class)
    module = item.module
    if request.method == "POST":
        used = (
            item.classroom_discipline_records.exists()
            or item.dorm_discipline_records.exists()
        )
        if used:
            item.is_active = False
            item.save(update_fields=["is_active", "updated_at"])
            messages.info(
                request,
                f"条目「{item.name}」已有历史记录，已改为停用。",
            )
        else:
            item.delete()
            messages.info(request, f"条目「{item.name}」已删除。")
    if module == "classroom_discipline":
        return redirect("discipline:classroom_items")
    return redirect("discipline:dorm_items")
