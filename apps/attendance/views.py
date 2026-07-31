from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone

from apps.attendance.models import AttendanceRecord
from apps.attendance.forms import AttendanceForm
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


@login_required
def index(request):
    """考勤管理首页"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()
    today = timezone.localdate()

    records = AttendanceRecord.objects.filter(
        school_class=current_class
    ).select_related("student") if current_class else AttendanceRecord.objects.none()

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
def create(request):
    """录入考勤"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = AttendanceForm(request.POST, request.FILES)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.save()
            messages.success(request, "考勤记录已保存。")
            return redirect("attendance:index")
    else:
        date = request.GET.get("date", str(timezone.localdate()))
        student_id = request.GET.get("student", "")
        form = AttendanceForm(initial={"date": date})
        if student_id:
            form.fields["student"].initial = student_id

    return render(request, "attendance/form.html", {"form": form, "title": "录入考勤"})
