from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from apps.communications.models import StudentConversation, HomeSchoolContact, ConcernRecord
from apps.communications.forms import ConversationForm, HomeSchoolContactForm, ConcernRecordForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.students.models import Student
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
        student_ids = request.POST.getlist("students")
        if student_ids:
            students = Student.objects.filter(
                pk__in=student_ids, school_class=current_class, is_deleted=False,
            ).distinct()
            if students.exists():
                from apps.communications.models import StudentConversation
                from django.db import transaction
                with transaction.atomic():
                    created = 0
                    for st in students:
                        StudentConversation.objects.create(
                            school_class=current_class, semester=current_semester,
                            student=st, date=request.POST.get("date", "") or timezone.localdate(),
                            location=request.POST.get("location", ""),
                            reason=request.POST.get("reason", ""),
                            main_content=request.POST.get("main_content", ""),
                            follow_up_actions=request.POST.get("follow_up_actions", ""),
                        )
                        created += 1
                messages.success(request, f"已为 {created} 名学生保存谈话记录。")
                return redirect("communications:conversations")

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

    students_json = [
        {"id": s.pk, "name": s.name} for s in Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("name", "student_id")
    ] if current_class else []
    return render(request, "communications/conversation_form.html", {"form": form, "students_json": students_json})


@login_required
def conversation_delete(request, pk):
    current_class = get_current_class(request.user)
    record = get_object_or_404(
        StudentConversation, pk=pk, school_class=current_class, is_deleted=False,
    )
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
        student_ids = request.POST.getlist("students")
        if student_ids:
            students = Student.objects.filter(
                pk__in=student_ids, school_class=current_class, is_deleted=False,
            ).distinct()
            if students.exists():
                from apps.communications.models import HomeSchoolContact
                from django.db import transaction
                with transaction.atomic():
                    created = 0
                    for st in students:
                        HomeSchoolContact.objects.create(
                            school_class=current_class, semester=current_semester,
                            student=st, contact_date=request.POST.get("contact_date", "") or timezone.localdate(),
                            contact_person=request.POST.get("contact_person", ""),
                            contact_method=request.POST.get("contact_method", "phone"),
                            reason=request.POST.get("reason", ""),
                            summary=request.POST.get("summary", ""),
                            parent_feedback=request.POST.get("parent_feedback", ""),
                            follow_up_items=request.POST.get("follow_up_items", ""),
                            follow_up_date=request.POST.get("follow_up_date") or None,
                        )
                        created += 1
                messages.success(request, f"已为 {created} 名学生保存家校沟通记录。")
                return redirect("communications:home_school")

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

    students_json = [
        {"id": s.pk, "name": s.name} for s in Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("name", "student_id")
    ] if current_class else []
    return render(request, "communications/home_school_form.html", {"form": form, "students_json": students_json})


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
        student_ids = request.POST.getlist("students")
        if student_ids:
            students = Student.objects.filter(
                pk__in=student_ids, school_class=current_class, is_deleted=False,
            ).distinct()
            if students.exists():
                from apps.communications.models import ConcernRecord
                from django.db import transaction
                with transaction.atomic():
                    created = 0
                    for st in students:
                        ConcernRecord.objects.create(
                            school_class=current_class, semester=current_semester,
                            student=st,
                            concern_type=request.POST.get("concern_type", ""),
                            level=request.POST.get("level", "medium"),
                            observation=request.POST.get("observation", ""),
                            conversation_notes=request.POST.get("conversation_notes", ""),
                            action_plan=request.POST.get("action_plan", ""),
                            status=request.POST.get("status", "open"),
                        )
                        created += 1
                messages.success(request, f"已为 {created} 名学生创建重点关注记录。")
                return redirect("communications:concerns")

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
    students_json = [
        {"id": s.pk, "name": s.name} for s in Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("name", "student_id")
    ] if current_class else []
    return render(request, "communications/concern_form.html", {"form": form, "students_json": students_json})


@login_required
def concern_detail(request, pk):
    """重点关注详情"""
    current_class = get_current_class(request.user)
    record = get_object_or_404(
        ConcernRecord.objects.select_related("student"),
        pk=pk, school_class=current_class,
    )
    return render(request, "communications/concern_detail.html", {"record": record})


@login_required
def concern_update(request, pk):
    """更新重点关注（状态/跟进）"""
    current_class = get_current_class(request.user)
    record = get_object_or_404(ConcernRecord, pk=pk, school_class=current_class)
    if request.method == "POST":
        form = ConcernRecordForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, "重点关注记录已更新。")
            return redirect("communications:concerns")
    else:
        form = ConcernRecordForm(instance=record)
    students_json = [
        {"id": s.pk, "name": s.name} for s in Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("name", "student_id")
    ] if current_class else []
    return render(request, "communications/concern_form.html", {
        "form": form, "record": record, "students_json": students_json,
        "initial_selected": [{"id": record.student.pk, "name": record.student.name}],
    })
