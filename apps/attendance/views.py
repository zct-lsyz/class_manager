from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone

from apps.attendance.models import AttendanceRecord, AttendanceReason
from apps.attendance.forms import AttendanceForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.students.models import Student


@login_required
def index(request):
    """考勤管理首页"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first() if current_class else None
    today = timezone.localdate()

    records = AttendanceRecord.objects.filter(
        school_class=current_class
    ).exclude(status="normal").select_related("student") if current_class else AttendanceRecord.objects.none()

    # 筛选
    date_from = request.GET.get("date_from", str(today))
    date_to = request.GET.get("date_to", "")
    status = request.GET.get("status", "")
    student_name = request.GET.get("student_name", "")

    if date_from:
        records = records.filter(date__gte=date_from)
    if date_to:
        records = records.filter(date__lte=date_to)
    if status:
        records = records.filter(status=status)
    if student_name:
        records = records.filter(student__name__icontains=student_name)

    records = records.order_by("-date", "student__student_id")

    # 分页
    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    # 统计
    today_absent = AttendanceRecord.objects.filter(
        school_class=current_class, date=today
    ).exclude(status="normal").count() if current_class else 0

    context = {
        "page_obj": page_obj,
        "today": today,
        "today_absent": today_absent,
        "current_filters": {
            "date_from": date_from,
            "date_to": date_to,
            "status": status,
            "student_name": student_name,
        },
        "status_choices": AttendanceRecord.STATUS_CHOICES,
    }
    return render(request, "attendance/index.html", context)


@login_required
@require_current_class
def create(request):
    """录入考勤"""
    current_class = get_current_class(request.user)
    if request.method == "POST":
        form = AttendanceForm(request.POST, request.FILES, current_class=current_class)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.save()
            messages.success(request, "考勤记录已保存。")
            return redirect("attendance:index")
    else:
        date = request.GET.get("date", str(timezone.localdate()))
        student_id = request.GET.get("student", "")
        form = AttendanceForm(initial={"date": date}, current_class=current_class)
        if student_id:
            form.fields["student"].initial = student_id

    reasons = AttendanceReason.objects.filter(school_class=current_class, is_active=True) if current_class else []
    return render(request, "attendance/form.html", {"form": form, "title": "新增异常考勤", "reasons": reasons})


@login_required
def edit(request, pk):
    """修改单个学生的异常考勤"""
    current_class = get_current_class(request.user)
    record = get_object_or_404(AttendanceRecord, pk=pk, school_class=current_class)
    if request.method == "POST":
        form = AttendanceForm(
            request.POST, request.FILES, instance=record, current_class=current_class,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "异常考勤已更新。")
            return redirect("attendance:index")
    else:
        form = AttendanceForm(instance=record, current_class=current_class)
    reasons = AttendanceReason.objects.filter(school_class=current_class, is_active=True) if current_class else []
    return render(request, "attendance/form.html", {"form": form, "title": "修改异常考勤", "reasons": reasons})


@login_required
@require_current_class
def reasons(request):
    current_class = get_current_class(request.user)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name and current_class:
            AttendanceReason.objects.update_or_create(school_class=current_class, name=name, defaults={"is_active": True})
            messages.success(request, "考勤原因项已添加。")
            return redirect("attendance:reasons")
        messages.error(request, "原因项不能为空。")
    items = AttendanceReason.objects.filter(school_class=current_class) if current_class else []
    return render(request, "attendance/reasons.html", {"items": items})


@login_required
def reason_delete(request, pk):
    current_class = get_current_class(request.user)
    item = get_object_or_404(AttendanceReason, pk=pk, school_class=current_class)
    if request.method == "POST":
        item.delete()
        messages.info(request, "考勤原因项已删除。历史考勤中的文字不会丢失。")
    return redirect("attendance:reasons")
