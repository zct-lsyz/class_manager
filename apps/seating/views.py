from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction

from apps.seating.models import ClassroomLayout, SeatPlan, SeatAssignment
from apps.seating.forms import ClassroomLayoutForm, SeatPlanForm
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.audit.models import OperationLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


def _build_grid(layout, assignments):
    """将座位分配转换为网格字典 {row: {col: student_id}}"""
    grid = {}
    for r in range(layout.rows):
        grid[r] = {}
        for c in range(layout.cols):
            grid[r][c] = None
    for a in assignments:
        if a.row in grid and a.col in grid[a.row]:
            grid[a.row][a.col] = a.student_id
    return grid


@login_required
def index(request):
    """座位表 - 可视化排座"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_plan = SeatPlan.objects.filter(
        school_class=current_class, is_active=True
    ).first() if current_class else None

    assignments = []
    grid = {}
    layout = None
    if current_plan:
        layout = current_plan.layout
        if layout:
            assignments = SeatAssignment.objects.filter(
                seat_plan=current_plan
            ).select_related("student")
            grid = _build_grid(layout, assignments)

    # 未分配学生
    assigned_ids = {a.student_id for a in assignments}
    unassigned = Student.objects.filter(
        school_class=current_class, is_deleted=False
    ).exclude(id__in=assigned_ids) if current_class else []

    plans = SeatPlan.objects.filter(school_class=current_class).order_by("-created_at") if current_class else []

    context = {
        "current_plan": current_plan,
        "layout": layout,
        "grid": grid,
        "unassigned": unassigned,
        "plans": plans,
    }
    return render(request, "seating/index.html", context)


@login_required
def layout_settings(request):
    """教室布局设置"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    layouts = ClassroomLayout.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        form = ClassroomLayoutForm(request.POST)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.school_class = current_class
            layout.save()
            if layout.is_current:
                ClassroomLayout.objects.filter(school_class=current_class).exclude(pk=layout.pk).update(is_current=False)
            messages.success(request, "教室布局已保存。")
            return redirect("seating:layout")
    else:
        form = ClassroomLayoutForm()

    context = {"layouts": layouts, "form": form}
    return render(request, "seating/layout.html", context)


@login_required
def plan_create(request):
    """创建新座位方案"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    if not current_class:
        messages.error(request, "请先设置当前班级。")
        return redirect("seating:index")

    if request.method == "POST":
        form = SeatPlanForm(request.POST)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.school_class = current_class
            plan.save()
            SeatPlan.objects.filter(school_class=current_class).exclude(pk=plan.pk).update(is_active=False)
            messages.success(request, f"座位方案 v{plan.version or plan.pk} 已创建。")
            return redirect("seating:index")
    else:
        form = SeatPlanForm()
        # 默认选中当前布局
        current_layout = ClassroomLayout.objects.filter(school_class=current_class, is_current=True).first()
        if current_layout:
            form.fields["layout"].initial = current_layout.pk

    return render(request, "seating/plan_form.html", {"form": form})


@login_required
def plan_activate(request, pk):
    """激活历史座位方案"""
    plan = get_object_or_404(SeatPlan, pk=pk)
    if request.method == "POST":
        SeatPlan.objects.filter(school_class=plan.school_class).update(is_active=False)
        plan.is_active = True
        plan.save()
        messages.success(request, f"座位方案 v{plan.version or plan.pk} 已恢复为当前方案。")
    return redirect("seating:index")


@login_required
@transaction.atomic
def save_plan(request):
    """保存座位分配"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    plan = SeatPlan.objects.filter(school_class=current_class, is_active=True).first()
    if not plan:
        messages.error(request, "请先创建座位方案。")
        return redirect("seating:index")

    if request.method == "POST":
        layout = plan.layout
        if not layout:
            messages.error(request, "座位方案未关联教室布局。")
            return redirect("seating:index")

        # 清空旧分配
        SeatAssignment.objects.filter(seat_plan=plan).delete()

        # 解析提交的分配数据: row-col=student_id
        count = 0
        for key, value in request.POST.items():
            if key.startswith("seat_") and value:
                try:
                    _, row, col = key.split("_")
                    row, col = int(row), int(col)
                    student_id = int(value)
                    SeatAssignment.objects.create(
                        seat_plan=plan, student_id=student_id, row=row, col=col,
                    )
                    count += 1
                except (ValueError, TypeError):
                    continue

        OperationLog.objects.create(
            user=request.user, action="edit", module="seating",
            object_repr=f"座位方案 v{plan.version or plan.pk}",
            detail=f"保存座位分配，共 {count} 个位置",
            ip_address=get_client_ip(request), success=True,
        )
        messages.success(request, f"座位方案已保存（{count} 个位置）。")
    return redirect("seating:index")


@login_required
@transaction.atomic
def auto_arrange(request):
    """自动排座：身高从低到高 + 性别均衡"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    plan = SeatPlan.objects.filter(school_class=current_class, is_active=True).first()
    if not plan or not plan.layout:
        messages.error(request, "请先创建座位方案并关联教室布局。")
        return redirect("seating:index")

    if request.method == "POST":
        layout = plan.layout
        students = list(Student.objects.filter(
            school_class=current_class, is_deleted=False,
        ).order_by("height", "student_id"))

        # 排序：有视力的优先前排
        vision_front = request.POST.get("vision_front") == "1"
        male_front = request.POST.get("male_front") == "1"

        # 身高从低到高排序（None 排最后）
        students.sort(key=lambda s: (s.height is None, s.height or 0))

        total_seats = layout.rows * layout.cols
        if len(students) > total_seats:
            messages.warning(request, f"学生数（{len(students)}）超过座位数（{total_seats}），部分学生将无法安排。")
            students = students[:total_seats]

        # 清空旧分配
        SeatAssignment.objects.filter(seat_plan=plan).delete()

        # 蛇形填充：低身高学生坐前排
        seat_positions = []
        for r in range(layout.rows):
            row_seats = list(range(layout.cols))
            if r % 2 == 1:  # 偶数排反序（蛇形）
                row_seats.reverse()
            for c in row_seats:
                seat_positions.append((r, c))

        count = 0
        for (row, col), student in zip(seat_positions, students):
            SeatAssignment.objects.create(
                seat_plan=plan, student=student, row=row, col=col,
            )
            count += 1

        OperationLog.objects.create(
            user=request.user, action="edit", module="seating",
            object_repr=f"座位方案 v{plan.version or plan.pk}",
            detail=f"自动排座完成，共 {count} 个位置",
            ip_address=get_client_ip(request), success=True,
        )
        messages.success(request, f"自动排座完成（{count} 名学生）。")
    return redirect("seating:index")
