"""评选管理视图"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from apps.classes.utils import get_current_class
from apps.classes.models import Semester
from apps.classes.decorators import require_current_class
from apps.audit.models import OperationLog
from apps.evaluation.models import EvaluationProject, EvaluationResult
from apps.evaluation.forms import EvaluationProjectForm
from apps.evaluation.services import INDICATORS, calculate_evaluation


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def _parse_rules(request):
    """从 POST 解析规则列表 [{key, label, weight}]。"""
    keys = request.POST.getlist("rule_keys")
    labels = request.POST.getlist("rule_labels")
    weights = request.POST.getlist("rule_weights")
    rules = []
    for i, key in enumerate(keys):
        key = (key or "").strip()
        if not key:
            continue
        try:
            weight = float(weights[i]) if i < len(weights) and weights[i] else 0
        except (TypeError, ValueError):
            weight = 0
        label = labels[i].strip() if i < len(labels) else ""
        rules.append({"key": key, "label": label or key, "weight": weight})
    # 权重和应为 1.0，做归一化
    total = sum(r["weight"] for r in rules)
    if total > 0:
        for r in rules:
            r["weight"] = round(r["weight"] / total, 4)
    return rules


@login_required
@require_current_class
def index(request):
    """评选管理首页：项目标签 + 排名表"""
    current_class = get_current_class(request.user)
    projects = EvaluationProject.objects.filter(
        school_class=current_class,
    ).order_by("sort_order", "id") if current_class else []

    project_id = request.GET.get("project", "")
    project = None
    if project_id:
        project = get_object_or_404(
            EvaluationProject, pk=project_id, school_class=current_class,
        )
    elif projects:
        project = projects[0]

    results = []
    if project:
        results = list(
            EvaluationResult.objects.filter(project=project)
            .select_related("student")
            .order_by("-created_at", "rank")
        )
        # 仅显示最新一次计算周期
        if results:
            latest_label = results[0].period_label
            results = [r for r in results if r.period_label == latest_label]

    return render(request, "evaluation/index.html", {
        "projects": projects,
        "project": project,
        "results": results,
        "indicators": INDICATORS,
    })


@login_required
@require_current_class
def project_create(request):
    """新增评选项目"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    if request.method == "POST":
        form = EvaluationProjectForm(request.POST)
        rules = _parse_rules(request)
        if form.is_valid():
            project = form.save(commit=False)
            project.school_class = current_class
            project.semester = current_semester
            project.rules_json = {"indicators": rules}
            project.save()
            OperationLog.objects.create(
                user=request.user, action="create", module="evaluation",
                object_repr=project.name, detail=f"新增评选项目：{project.name}",
                ip_address=get_client_ip(request), success=True,
            )
            messages.success(request, f"评选项目「{project.name}」已创建。")
            return redirect(f"{request.path}?project={project.pk}")
        messages.error(request, "请修正表单错误。")
    else:
        form = EvaluationProjectForm()

    return render(request, "evaluation/project_form.html", {
        "form": form, "indicators": INDICATORS, "title": "新增评选",
    })


@login_required
@require_current_class
def project_edit(request, pk):
    """编辑评选项目（含规则）"""
    current_class = get_current_class(request.user)
    project = get_object_or_404(
        EvaluationProject, pk=pk, school_class=current_class,
    )
    if request.method == "POST":
        form = EvaluationProjectForm(request.POST, instance=project)
        rules = _parse_rules(request)
        if form.is_valid():
            project = form.save(commit=False)
            project.rules_json = {"indicators": rules}
            project.save()
            OperationLog.objects.create(
                user=request.user, action="edit", module="evaluation",
                object_repr=project.name, detail=f"修改评选项目：{project.name}",
                ip_address=get_client_ip(request), success=True,
            )
            messages.success(request, f"评选项目「{project.name}」已更新。")
            return redirect(f"/evaluation/?project={project.pk}")
    else:
        form = EvaluationProjectForm(instance=project)

    return render(request, "evaluation/project_form.html", {
        "form": form, "indicators": INDICATORS,
        "title": "编辑评选", "project": project,
    })


@login_required
@require_current_class
def project_delete(request, pk):
    """删除评选项目及其历史结果"""
    current_class = get_current_class(request.user)
    project = get_object_or_404(
        EvaluationProject, pk=pk, school_class=current_class,
    )
    if request.method == "POST":
        name = project.name
        project.delete()
        OperationLog.objects.create(
            user=request.user, action="delete", module="evaluation",
            object_repr=name, detail=f"删除评选项目：{name}",
            ip_address=get_client_ip(request), success=True,
        )
        messages.info(request, f"评选项目「{name}」已删除（含历史结果）。")
    return redirect("evaluation:index")


@login_required
@require_current_class
def calculate(request, pk):
    """手动立即计算某评选项目"""
    current_class = get_current_class(request.user)
    project = get_object_or_404(
        EvaluationProject, pk=pk, school_class=current_class,
    )
    if request.method == "POST":
        results, period_label, count = calculate_evaluation(project)
        OperationLog.objects.create(
            user=request.user, action="edit", module="evaluation",
            object_repr=project.name, detail=f"重新计算评选：{project.name}，{count} 人",
            ip_address=get_client_ip(request), success=True,
        )
        if results:
            messages.success(
                request,
                f"「{project.name}」已重新计算（{period_label}），共 {count} 名学生参与。",
            )
        elif not project.rules():
            messages.warning(request, "该项目未配置评分规则，请先在「编辑」中设置指标与权重。")
        else:
            messages.warning(
                request,
                "该项目已配置评分规则，但当前没有可参与评选的学生或指标数据，无法计算。",
            )
    return redirect(f"/evaluation/?project={project.pk}")


@login_required
@require_current_class
def history(request, pk):
    """查看评选项目的历史结果"""
    current_class = get_current_class(request.user)
    project = get_object_or_404(
        EvaluationProject, pk=pk, school_class=current_class,
    )
    results = list(
        EvaluationResult.objects.filter(project=project)
        .select_related("student")
        .order_by("-created_at", "rank")
    )
    # 按周期标签分组
    grouped = {}
    for r in results:
        grouped.setdefault(r.period_label, []).append(r)
    return render(request, "evaluation/history.html", {
        "project": project, "grouped": grouped,
    })
