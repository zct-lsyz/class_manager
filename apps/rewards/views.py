from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Sum, Q, Count
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db import transaction
from django.utils import timezone

from apps.rewards.models import RewardItem, RewardRecord, PointRecord
from apps.rewards.forms import RewardItemForm, RewardRecordForm, PointRecordForm, BatchRewardRecordForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.students.models import Student
from apps.audit.services import soft_delete


@login_required
def index(request):
    """奖励记录列表"""
    current_class = get_current_class(request.user)
    records = RewardRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "rewards/index.html", {"page_obj": page_obj})


@login_required
@require_current_class
@transaction.atomic
def reward_create(request):
    """新增奖励"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None

    if request.method == "POST":
        post_data = request.POST.copy()
        if not post_data.getlist("students") and post_data.get("student"):
            post_data.setlist("students", [post_data["student"]])
        form = BatchRewardRecordForm(post_data, request.FILES, current_class=current_class)
        if form.is_valid():
            saved_photo = ""
            for index, student in enumerate(form.cleaned_data["students"]):
                record = RewardRecord(
                    school_class=current_class, semester=current_semester, student=student,
                    date=form.cleaned_data["date"], record_type=form.cleaned_data["record_type"],
                    item=form.cleaned_data["item"], custom_name=form.cleaned_data["custom_name"],
                    level=form.cleaned_data["level"], points=form.cleaned_data["points"],
                    description=form.cleaned_data["description"],
                )
                record.points = -abs(record.points) if record.record_type == "penalty" else abs(record.points)
                if index == 0:
                    record.certificate_photo = form.cleaned_data["certificate_photo"]
                elif saved_photo:
                    record.certificate_photo = saved_photo
                record.save()
                saved_photo = record.certificate_photo.name if record.certificate_photo else ""
                _sync_point_record(record)
            messages.success(request, f"已为 {len(form.cleaned_data['students'])} 名学生保存奖惩记录。")
            return redirect("rewards:index")
    else:
        form = BatchRewardRecordForm(current_class=current_class)

    return render(request, "rewards/form.html", {"form": form, "title": "新增奖惩"})


@login_required
def reward_edit(request, pk):
    """编辑奖励记录"""
    current_class = get_current_class(request.user)
    record = get_object_or_404(RewardRecord, pk=pk, school_class=current_class)
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
    current_class = get_current_class(request.user)
    record = get_object_or_404(RewardRecord, pk=pk, school_class=current_class)
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
    """总体积分排名：按排名设置选中的模块汇总积分"""
    from collections import defaultdict
    from apps.rewards.models import RankingSetting

    current_class = get_current_class(request.user)
    setting, _ = RankingSetting.objects.get_or_create(
        school_class=current_class,
    ) if current_class else (None, False)
    enabled_types = setting.enabled_source_types() if setting else []

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    records = PointRecord.objects.filter(
        school_class=current_class, source_type__in=enabled_types, is_deleted=False,
    ).select_related("student").order_by("-date") if current_class and enabled_types else PointRecord.objects.none()
    if date_from:
        records = records.filter(date__gte=date_from)
    if date_to:
        records = records.filter(date__lte=date_to)

    # 一次查询，Python 汇总
    all_recs = list(records)
    student_data = defaultdict(lambda: {"total": 0, "reasons": defaultdict(lambda: {"total": 0, "count": 0})})
    for r in all_recs:
        d = student_data[r.student_id]
        d["total"] += r.points
        d["reasons"][r.reason]["total"] += r.points
        d["reasons"][r.reason]["count"] += 1

    students = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ) if current_class else []
    student_points = []
    for s in students:
        data = student_data.get(s.pk, {"total": 0, "reasons": {}})
        reasons = sorted(
            data["reasons"].items(),
            key=lambda kv: abs(kv[1]["total"]), reverse=True,
        )[:6]
        student_points.append({
            "student": s,
            "total": data["total"],
            "reasons": [{"reason": k, "total": v["total"], "count": v["count"]} for k, v in reasons],
        })
    student_points.sort(key=lambda x: x["total"], reverse=True)

    paginator = Paginator(all_recs, 30)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "student_points": student_points,
        "page_obj": page_obj,
        "setting": setting,
        "enabled_labels": setting.enabled_labels() if setting else [],
        "filters": {"date_from": date_from, "date_to": date_to},
    }
    return render(request, "rewards/points.html", context)


@login_required
def ranking_settings(request):
    """积分排名设置：选择参与总体排名的来源模块"""
    from apps.rewards.models import RankingSetting
    current_class = get_current_class(request.user)
    setting, _ = RankingSetting.objects.get_or_create(
        school_class=current_class,
    ) if current_class else (None, False)

    if request.method == "POST":
        setting.enable_reward = request.POST.get("enable_reward") == "on"
        setting.enable_classroom_discipline = request.POST.get("enable_classroom_discipline") == "on"
        setting.enable_dorm_discipline = request.POST.get("enable_dorm_discipline") == "on"
        setting.enable_hygiene = request.POST.get("enable_hygiene") == "on"
        setting.enable_attendance = request.POST.get("enable_attendance") == "on"
        setting.enable_homework = request.POST.get("enable_homework") == "on"
        setting.save()
        messages.success(request, "积分排名设置已保存。")
        return redirect("rewards:points")

    return render(request, "rewards/ranking_settings.html", {"setting": setting})


@login_required
@require_current_class
def rules(request):
    """奖励与积分规则设置"""
    current_class = get_current_class(request.user)
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


@login_required
def rule_delete(request, pk):
    current_class = get_current_class(request.user)
    item = get_object_or_404(RewardItem, pk=pk, school_class=current_class)
    if request.method == "POST":
        if item.records.exists():
            item.is_active = False
            item.save(update_fields=["is_active", "updated_at"])
            messages.info(request, "条目已有历史记录，已改为停用。")
        else:
            item.delete()
            messages.info(request, "奖惩条目已删除。")
    return redirect("rewards:rules")


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
