from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator

from apps.comments.models import StudentComment, CommentTemplate
from apps.comments.forms import StudentCommentForm, CommentTemplateForm
from apps.classes.models import SchoolClass, Semester


@login_required
def list(request):
    """评语列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    comments = StudentComment.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student").order_by("-created_at") if current_class else []

    paginator = Paginator(comments, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "comments/list.html", {"page_obj": page_obj})


@login_required
def create(request):
    """撰写评语"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    if request.method == "POST":
        form = StudentCommentForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.school_class = current_class
            c.semester = current_semester
            c.save()
            messages.success(request, "评语已保存。")
            return redirect("comments:list")
    else:
        form = StudentCommentForm()

    return render(request, "comments/form.html", {"form": form})


@login_required
def detail(request, pk):
    """评语详情"""
    comment = get_object_or_404(
        StudentComment.objects.select_related("student", "semester"), pk=pk,
    )
    return render(request, "comments/detail.html", {"comment": comment})


@login_required
def edit(request, pk):
    """编辑评语"""
    comment = get_object_or_404(StudentComment, pk=pk)
    if request.method == "POST":
        form = StudentCommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            messages.success(request, "评语已更新。")
            return redirect("comments:list")
    else:
        form = StudentCommentForm(instance=comment)
    return render(request, "comments/form.html", {"form": form, "title": "编辑评语"})


@login_required
def delete(request, pk):
    """删除评语（软删除）"""
    comment = get_object_or_404(StudentComment, pk=pk)
    if request.method == "POST":
        comment.is_deleted = True
        comment.save(update_fields=["is_deleted"])
        messages.info(request, "评语已删除。")
    return redirect("comments:list")


@login_required
def templates(request):
    """评语模板管理"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    templates = CommentTemplate.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        form = CommentTemplateForm(request.POST)
        if form.is_valid():
            t = form.save(commit=False)
            t.school_class = current_class
            t.save()
            messages.success(request, "评语模板已添加。")
            return redirect("comments:templates")
    else:
        form = CommentTemplateForm()

    return render(request, "comments/templates.html", {"templates": templates, "form": form})
