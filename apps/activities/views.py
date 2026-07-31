from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from apps.activities.models import ClassMeeting, Activity, ClassCultureTask
from apps.activities.forms import ClassMeetingForm, ActivityForm, ClassCultureTaskForm
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.audit.services import soft_delete


@login_required
def class_meetings(request):
    """主题班会列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    meetings = ClassMeeting.objects.filter(school_class=current_class).order_by("-date") if current_class else []
    paginator = Paginator(meetings, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)
    return render(request, "activities/class_meetings.html", {"page_obj": page_obj})


@login_required
@require_current_class
def class_meeting_create(request):
    """新建主题班会"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        form = ClassMeetingForm(request.POST, request.FILES)
        if form.is_valid():
            m = form.save(commit=False)
            m.school_class = current_class
            m.semester = current_semester
            m.save()
            form.save_m2m()
            messages.success(request, "班会记录已保存。")
            return redirect("activities:class_meetings")
    else:
        form = ClassMeetingForm()
    return render(request, "activities/meeting_form.html", {"form": form})


@login_required
def activities(request):
    """文体活动列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    acts = Activity.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []
    paginator = Paginator(acts, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)
    return render(request, "activities/activities.html", {"page_obj": page_obj})


@login_required
@require_current_class
def activity_create(request):
    """新建文体活动"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        form = ActivityForm(request.POST, request.FILES)
        if form.is_valid():
            a = form.save(commit=False)
            a.school_class = current_class
            a.semester = current_semester
            a.save()
            form.save_m2m()
            messages.success(request, "活动记录已保存。")
            return redirect("activities:activities")
    else:
        form = ActivityForm()
    return render(request, "activities/activity_form.html", {"form": form})


@login_required
def activity_delete(request, pk):
    activity = get_object_or_404(Activity, pk=pk, is_deleted=False)
    if request.method == "POST":
        soft_delete(
            activity,
            user=request.user,
            module="activities",
            model_name="activity",
        )
        messages.info(request, "活动记录已移入回收站。")
    return redirect("activities:activities")


@login_required
def culture(request):
    """班级文化"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    tasks = ClassCultureTask.objects.filter(school_class=current_class).order_by("-deadline") if current_class else []
    paginator = Paginator(tasks, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)
    return render(request, "activities/culture.html", {"page_obj": page_obj})


@login_required
@require_current_class
def culture_create(request):
    """新建文化任务"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        form = ClassCultureTaskForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.school_class = current_class
            t.semester = current_semester
            t.save()
            messages.success(request, "文化任务已创建。")
            return redirect("activities:culture")
    else:
        form = ClassCultureTaskForm()
    return render(request, "activities/culture_form.html", {"form": form})
