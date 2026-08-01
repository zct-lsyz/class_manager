from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from apps.communications.models import StudentConversation, HomeSchoolContact, ConcernRecord
from apps.communications.forms import ConversationForm, HomeSchoolContactForm, ConcernRecordForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.audit.services import soft_delete


@login_required
def conversations(request):
    """学生谈话列表"""
    current_class = get_current_class(request.user)
    records = StudentConversation.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "communications/conversations.html", {"page_obj": page_obj})


@login_required
@require_current_class
def conversation_create(request):
    """新建谈话记录"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    if request.method == "POST":
        form = ConversationForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.school_class = current_class
            c.semester = current_semester
            c.save()
            messages.success(request, "谈话记录已保存。")
            return redirect("communications:conversations")
    else:
        form = ConversationForm()

    return render(request, "communications/conversation_form.html", {"form": form})


@login_required
def conversation_delete(request, pk):
    record = get_object_or_404(StudentConversation, pk=pk, is_deleted=False)
    if request.method == "POST":
        soft_delete(
            record,
            user=request.user,
            module="communications",
            model_name="conversation",
        )
        messages.info(request, "谈话记录已移入回收站。")
    return redirect("communications:conversations")


@login_required
def home_school(request):
    """家校沟通列表"""
    current_class = get_current_class(request.user)
    records = HomeSchoolContact.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student").order_by("-contact_date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "communications/home_school.html", {"page_obj": page_obj})


@login_required
@require_current_class
def home_school_create(request):
    """新建家校沟通"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    if request.method == "POST":
        form = HomeSchoolContactForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.school_class = current_class
            c.semester = current_semester
            c.save()
            messages.success(request, "家校沟通记录已保存。")
            return redirect("communications:home_school")
    else:
        form = HomeSchoolContactForm()

    return render(request, "communications/home_school_form.html", {"form": form})


# ====== 重点关注 ======

@login_required
def concerns(request):
    """重点关注列表"""
    current_class = get_current_class(request.user)
    records = ConcernRecord.objects.filter(
        school_class=current_class
    ).select_related("student").order_by("-created_at") if current_class else []

    status = request.GET.get("status", "")
    if status:
        records = records.filter(status=status)

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "communications/concerns.html", {
        "page_obj": page_obj, "current_status": status,
    })


@login_required
@require_current_class
def concern_create(request):
    """新建重点关注"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    if request.method == "POST":
        form = ConcernRecordForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.school_class = current_class
            c.semester = current_semester
            c.save()
            messages.success(request, "重点关注记录已创建。")
            return redirect("communications:concerns")
    else:
        form = ConcernRecordForm()
    return render(request, "communications/concern_form.html", {"form": form})


@login_required
def concern_detail(request, pk):
    """重点关注详情"""
    record = get_object_or_404(
        ConcernRecord.objects.select_related("student"), pk=pk,
    )
    return render(request, "communications/concern_detail.html", {"record": record})


@login_required
def concern_update(request, pk):
    """更新重点关注（状态/跟进）"""
    record = get_object_or_404(ConcernRecord, pk=pk)
    if request.method == "POST":
        form = ConcernRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "重点关注记录已更新。")
            return redirect("communications:concerns")
    else:
        form = ConcernRecordForm(instance=record)
    return render(request, "communications/concern_form.html", {"form": form, "record": record})
