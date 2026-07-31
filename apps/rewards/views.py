from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.utils import timezone

from apps.rewards.models import RewardItem, RewardRecord, PointRecord
from apps.rewards.forms import RewardItemForm, RewardRecordForm, PointRecordForm
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.audit.services import soft_delete


@login_required
def index(request):
    """奖励记录列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    records = RewardRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "rewards/index.html", {"page_obj": page_obj})


@login_required
def reward_create(request):
    """新增奖励"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    if request.method == "POST":
        form = RewardRecordForm(request.POST, request.FILES, current_class=current_class)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            record.points = -abs(record.points) if record.record_type == "penalty" else abs(record.points)
            record.save()
            _sync_point_record(record)
            messages.success(request, "奖惩记录已保存。")
            return redirect("rewards:index")
    else:
        form = RewardRecordForm(current_class=current_class)

    return render(request, "rewards/form.html", {"form": form, "title": "新增奖惩"})


@login_required
def reward_edit(request, pk):
    """编辑奖励记录"""
    record = get_object_or_404(RewardRecord, pk=pk)
    if request.method == "POST":
        form = RewardRecordForm(
            request.POST, request.FILES, instance=record,
            current_class=record.school_class,
        )
        if form.is_valid():
            record = form.save(commit=False)
            record.points = -abs(record.points) if record.record_type == "penalty" else abs(record.points)
            record.save()
            _sync_point_record(record)
            messages.success(request, "奖惩记录已更新。")
            return redirect("rewards:index")
    else:
        form = RewardRecordForm(instance=record, current_class=record.school_class)
    return render(request, "rewards/form.html", {"form": form, "title": "编辑奖惩"})


@login_required
def reward_delete(request, pk):
    """删除奖励记录（软删除）"""
    record = get_object_or_404(RewardRecord, pk=pk)
    if request.method == "POST":
        PointRecord.objects.filter(source_type="reward", source_id=record.pk).update(is_deleted=True)
        soft_delete(
            record,
            user=request.user,
            module="rewards",
            model_name="reward",
        )
        messages.info(request, "奖惩记录已删除。")
    return redirect("rewards:index")


@login_required
def points(request):
    """奖惩积分"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    # 获取所有学生的积分汇总
    students = Student.objects.filter(
        school_class=current_class, is_deleted=False
    ) if current_class else []

    student_points = []
    for s in students:
        total = PointRecord.objects.filter(
            student=s, semester=current_semester, is_deleted=False,
        ).aggregate(Sum("points"))["points__sum"] or 0
        student_points.append({"student": s, "total": total})

    student_points.sort(key=lambda x: x["total"], reverse=True)

    # 积分明细
    records = PointRecord.objects.filter(
        school_class=current_class, semester=current_semester, is_deleted=False
    ).select_related("student").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    context = {
        "student_points": student_points,
        "page_obj": page_obj,
    }
    return render(request, "rewards/points.html", context)


@login_required
def rules(request):
    """奖励与积分规则设置"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    items = RewardItem.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        form = RewardItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.school_class = current_class
            item.save()
            messages.success(request, f"奖励条目「{item.name}」已添加。")
            return redirect("rewards:rules")
    else:
        form = RewardItemForm()

    return render(request, "rewards/rules.html", {"items": items, "form": form})


def _sync_point_record(record):
    reason = record.custom_name or (record.item.name if record.item else record.get_record_type_display())
    point_record = PointRecord.objects.filter(
        source_type="reward", source_id=record.pk,
    ).order_by("pk").first()
    if not point_record:
        point_record = PointRecord(source_type="reward", source_id=record.pk)
    point_record.student = record.student
    point_record.school_class = record.school_class
    point_record.semester = record.semester
    point_record.date = record.date
    point_record.points = record.points
    point_record.reason = reason
    point_record.is_deleted = False
    point_record.save()
