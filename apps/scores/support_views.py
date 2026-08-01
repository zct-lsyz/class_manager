"""培优补差视图"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.scores.models import Exam, ExamSubject, Score, SupportPlan, SupportFollowUp
from apps.scores.forms import SupportPlanForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


@login_required
def support_list(request):
    """培优补差名单"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(is_current=True).first()

    plans = SupportPlan.objects.filter(
        school_class=current_class, semester=current_semester
    ).select_related("student", "subject").order_by("-is_active", "plan_type", "student__name") if current_class else []

    return render(request, "scores/support_list.html", {"plans": plans})


@login_required
def support_create(request):
    """创建培优补差计划"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(is_current=True).first()

    if request.method == "POST":
        form = SupportPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.school_class = current_class
            plan.semester = current_semester
            plan.save()
            messages.success(request, f"{plan.get_plan_type_display()}计划已创建：{plan.student.name}（{plan.subject.name}）")
            return redirect("scores:support_list")
    else:
        form = SupportPlanForm()
        candidate_id = request.GET.get("candidate", "")
        if candidate_id:
            form.fields["student"].initial = candidate_id

    return render(request, "scores/support_form.html", {"form": form})


@login_required
def support_detail(request, pk):
    """培优补差详情 + 跟进记录"""
    plan = get_object_or_404(
        SupportPlan.objects.select_related("student", "subject"), pk=pk,
    )
    follow_ups = SupportFollowUp.objects.filter(plan=plan).order_by("-date")

    if request.method == "POST":
        date = request.POST.get("date", "")
        content = request.POST.get("content", "").strip()
        effect = request.POST.get("effect", "").strip()
        next_step = request.POST.get("next_step", "").strip()
        if content:
            SupportFollowUp.objects.create(
                plan=plan, date=date or timezone.localdate(),
                content=content, effect=effect, next_step=next_step,
            )
            messages.success(request, "跟进记录已添加。")
        else:
            messages.error(request, "跟进内容不能为空。")
        return redirect("scores:support_detail", pk=plan.pk)

    return render(request, "scores/support_detail.html", {"plan": plan, "follow_ups": follow_ups})


@login_required
def support_close(request, pk):
    """结束/移出计划"""
    plan = get_object_or_404(SupportPlan, pk=pk)
    if request.method == "POST":
        plan.is_active = False
        plan.end_date = timezone.localdate()
        plan.save()
        messages.info(request, f"{plan.student.name} 的{plan.get_plan_type_display()}计划已结束。")
    return redirect("scores:support_list")


@login_required
def support_candidates(request):
    """按成绩筛选培优补差候选人"""
    current_class = get_current_class(request.user)

    exam_id = request.GET.get("exam_id", "")
    plan_type = request.GET.get("plan_type", "excellent")
    threshold = request.GET.get("threshold", "")

    candidates = []
    exam = None
    if exam_id:
        exam = get_object_or_404(Exam, pk=exam_id)
        es_list = list(ExamSubject.objects.filter(exam=exam).select_related("subject"))
        total_full = sum(es.full_score for es in es_list) if es_list else 0
        students = Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("student_id")

        for s in students:
            total = 0
            count = 0
            for es in es_list:
                sc = Score.objects.filter(
                    exam_subject=es,
                    student=s,
                    status="normal",
                    is_deleted=False,
                ).first()
                if sc and sc.score is not None:
                    total += float(sc.score)
                    count += 1
            if count == 0:
                continue
            avg = total / count
            ratio = (total / total_full * 100) if total_full > 0 else 0
            candidates.append({
                "student": s, "total": round(total, 1), "avg": round(avg, 1), "ratio": round(ratio, 1),
            })

        if plan_type == "excellent":
            if threshold:
                candidates = [c for c in candidates if c["avg"] >= float(threshold)]
            else:
                candidates = [c for c in candidates if c["ratio"] >= 85]
        else:
            if threshold:
                candidates = [c for c in candidates if c["avg"] < float(threshold)]
            else:
                candidates = [c for c in candidates if c["ratio"] < 60]
        candidates.sort(key=lambda c: c["ratio"], reverse=(plan_type == "excellent"))

    exams = Exam.objects.filter(school_class=current_class, is_deleted=False).order_by("-date") if current_class else []

    return render(request, "scores/support_candidates.html", {
        "exams": exams, "exam": exam, "plan_type": plan_type,
        "threshold": threshold, "candidates": candidates,
    })
