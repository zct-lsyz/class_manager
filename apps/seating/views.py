from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.seating.models import ClassroomLayout, SeatPlan, SeatAssignment
from apps.seating.forms import ClassroomLayoutForm, SeatPlanForm
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.audit.models import OperationLog
from apps.seating.services import (
    DEFAULT_PRIORITIES, PRIORITY_LABELS, arrange_students,
    attach_student_seat_metadata, normalize_priorities, rotate_due_plans,
)


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


def _build_grid(layout, assignments):
    """将座位分配转换为网格字典 {row: {col: student}}"""
    grid = {}
    rows = range(layout.rows - 1, -1, -1) if layout.podium_position == "back" else range(layout.rows)
    for r in rows:
        grid[r] = {}
        for c in range(layout.cols):
            grid[r][c] = None
    for a in assignments:
        if a.row in grid and a.col in grid[a.row]:
            grid[a.row][a.col] = a.student
    return grid


@login_required
def plan_export(request):
    """导出当前座位方案为 Excel。"""
    current_class = get_current_class(request.user)
    current_plan = SeatPlan.objects.filter(
        school_class=current_class, is_active=True,
    ).first() if current_class else None
    if not current_plan or not current_plan.layout:
        messages.error(request, "暂无可用座位方案。")
        return redirect("seating:index")

    layout = current_plan.layout
    assignments = list(SeatAssignment.objects.filter(
        seat_plan=current_plan,
    ).select_related("student"))
    grid = _build_grid(layout, assignments)

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    from django.http import HttpResponse

    wb = Workbook()
    ws = wb.active
    ws.title = "座位表"
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", start_color="1A73E8")

    # 讲台行
    if layout.podium_position == "back":
        ws.cell(1, 1, "讲台").font = Font(bold=True, color="FFFFFF")
        ws.cell(1, 1).fill = header_fill
        ws.cell(1, 1).alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=layout.cols)
        start_row = 2
    else:
        start_row = 1

    rows = range(layout.rows - 1, -1, -1) if layout.podium_position == "back" else range(layout.rows)
    for i, r in enumerate(rows):
        row_idx = start_row + i
        for c in range(layout.cols):
            student = grid.get(r, {}).get(c)
            cell = ws.cell(row_idx, c + 1)
            cell.border = border
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            if student:
                cell.value = student.name
                cell.font = Font(bold=True)

    # 讲台（在前方）
    if layout.podium_position != "back":
        podium_row = start_row + layout.rows
        ws.cell(podium_row, 1, "讲台").font = Font(bold=True, color="FFFFFF")
        ws.cell(podium_row, 1).fill = header_fill
        ws.cell(podium_row, 1).alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=podium_row, start_column=1, end_row=podium_row, end_column=layout.cols)

    for c in range(1, layout.cols + 1):
        ws.column_dimensions[chr(64 + c)].width = 14
    for i in range(start_row, start_row + layout.rows + 1):
        ws.row_dimensions[i].height = 22

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="seating_plan.xlsx"'
    wb.save(response)
    return response


@login_required
def index(request):
    """座位表 - 可视化排座"""
    current_class = get_current_class(request.user)
    if current_class:
        rotate_due_plans(school_class=current_class)
    current_plan = SeatPlan.objects.filter(
        school_class=current_class, is_active=True
    ).first() if current_class else None

    assignments = []
    grid = {}
    layout = None
    if current_plan:
        layout = current_plan.layout
        if layout:
            assignments = list(SeatAssignment.objects.filter(
                seat_plan=current_plan
            ).select_related("student"))
            grid = _build_grid(layout, assignments)

    # 未分配学生
    assigned_ids = {a.student_id for a in assignments}
    unassigned = list(Student.objects.filter(
        Q(school_class=current_class) | Q(school_class__isnull=True), is_deleted=False
    ).exclude(id__in=assigned_ids)) if current_class else []
    if current_class:
        attach_student_seat_metadata([a.student for a in assignments] + unassigned, current_class)

    plans = SeatPlan.objects.filter(school_class=current_class).order_by("-created_at") if current_class else []
    layouts = (
        ClassroomLayout.objects.filter(school_class=current_class).order_by("-is_current", "-updated_at")
        if current_class else ClassroomLayout.objects.none()
    )
    priorities = normalize_priorities(
        current_plan.arrangement_priorities if current_plan else DEFAULT_PRIORITIES
    )

    context = {
        "current_plan": current_plan,
        "layout": layout,
        "grid": grid,
        "unassigned": unassigned,
        "plans": plans,
        "layouts": layouts,
        "aisle_positions": layout.aisle_positions if layout else [],
        "priority_rows": list(enumerate(priorities, start=1)),
        "priority_options": PRIORITY_LABELS.items(),
        "rotation_interval": current_plan.rotation_interval_months or 1 if current_plan else 1,
    }
    return render(request, "seating/index.html", context)


@login_required
def layout_settings(request):
    """教室布局设置"""
    current_class = get_current_class(request.user)
    layouts = ClassroomLayout.objects.filter(school_class=current_class) if current_class else []
    current_layout = layouts.filter(is_current=True).first() if current_class else None

    if not current_class:
        messages.error(request, "请先设置当前班级。")
        return redirect("classes:settings")

    if request.method == "POST":
        form = ClassroomLayoutForm(request.POST, instance=current_layout)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.school_class = current_class
            layout.podium_position = "back"
            layout.save()
            SeatAssignment.objects.filter(seat_plan__layout=layout).filter(
                Q(row__gte=layout.rows) | Q(col__gte=layout.cols)
            ).delete()
            if layout.is_current:
                ClassroomLayout.objects.filter(school_class=current_class).exclude(pk=layout.pk).update(is_current=False)
            messages.success(request, "教室布局已保存。")
            return redirect("seating:layout")
    else:
        form = ClassroomLayoutForm(instance=current_layout)

    aisle_positions = request.POST.getlist("aisle_positions") if request.method == "POST" else (
        current_layout.aisle_positions if current_layout else [3]
    )
    context = {"layouts": layouts, "form": form, "aisle_positions": aisle_positions}
    return render(request, "seating/layout.html", context)


@login_required
def plan_create(request):
    """创建新座位方案"""
    current_class = get_current_class(request.user)
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
    current_class = get_current_class(request.user)
    plan = get_object_or_404(SeatPlan, pk=pk, school_class=current_class)
    if request.method == "POST":
        SeatPlan.objects.filter(school_class=plan.school_class).update(is_active=False)
        plan.is_active = True
        plan.save()
        messages.success(request, f"座位方案 v{plan.version or plan.pk} 已恢复为当前方案。")
    return redirect("seating:index")


def _parse_seat_plan_excel(file_obj):
    """解析“导出的座位表Excel”模板。

    返回 (seat_rows, podium_top)：
    - seat_rows：学生姓名网格 list[list[str]]（已剔除“讲台”行，空座位为空串）
    - podium_top：讲台是否在学生区上方
    """
    from openpyxl import load_workbook

    workbook = load_workbook(file_obj, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        raw_rows = []
        for row in sheet.iter_rows(values_only=True):
            raw_rows.append(["" if value is None else str(value).strip() for value in row])
    finally:
        workbook.close()

    podium_rows = []
    seat_rows = []
    for index, texts in enumerate(raw_rows):
        if "讲台" in "".join(texts):
            podium_rows.append(index)
            continue
        if any(texts):
            seat_rows.append(texts)

    podium_top = True  # 默认按“讲台在上”（本页导出的标准样式）
    if podium_rows:
        first_seat = next(
            (index for index, texts in enumerate(raw_rows)
             if index not in podium_rows and any(texts)),
            None,
        )
        podium_top = min(podium_rows) < (first_seat if first_seat is not None else 10 ** 9)

    # 统一各行宽度（保留中间空座位的位置）
    width = max((len(row) for row in seat_rows), default=0)
    if width:
        seat_rows = [row + [""] * (width - len(row)) for row in seat_rows]
    return seat_rows, podium_top


def _map_file_row_to_grid(podium_top, total_rows, file_index):
    """Excel 里第 file_index 个学生行（0 起）对应的布局排号（0 起）。

    讲台在上：文件自上而下是第 total_rows-1 排 → 第 0 排，需反转；
    讲台在下：文件自上而下即第 0 排 → 第 total_rows-1 排，保持不变。
    """
    if podium_top:
        return total_rows - 1 - file_index
    return file_index


@login_required
@transaction.atomic
def plan_import(request):
    """按“导出的座位表Excel”模板导入，新建并启用一个座位方案。"""
    current_class = get_current_class(request.user)
    if not current_class:
        messages.error(request, "请先设置当前班级。")
        return redirect("seating:index")
    if request.method != "POST":
        return redirect("seating:index")

    upload = request.FILES.get("file")
    if not upload:
        messages.error(request, "请选择要导入的 Excel 文件。")
        return redirect("seating:index")
    filename = (upload.name or "").strip().lower()
    if not filename.endswith(".xlsx"):
        messages.error(request, "仅支持 .xlsx 文件，可先用本页「导出Excel」下载模板。")
        return redirect("seating:index")

    try:
        layout = ClassroomLayout.objects.get(
            pk=int(request.POST.get("layout") or 0),
            school_class=current_class,
        )
    except (ClassroomLayout.DoesNotExist, TypeError, ValueError):
        messages.error(request, "请选择有效的教室布局。")
        return redirect("seating:index")

    try:
        seat_rows, podium_top = _parse_seat_plan_excel(upload)
    except Exception as exc:
        messages.error(request, f"无法解析 Excel 文件（请确认是 .xlsx 且未损坏）：{exc}")
        return redirect("seating:index")

    if not seat_rows or not any(any(cell) for cell in seat_rows):
        messages.error(request, "表格中没有识别到学生姓名，请检查文件是否为座位表格式（讲台行 + 学生姓名）。")
        return redirect("seating:index")

    detected_rows, detected_cols = len(seat_rows), len(seat_rows[0])
    if detected_rows != layout.rows:
        messages.error(
            request,
            f"表格中识别到 {detected_rows} 排学生行（不含讲台行），"
            f"但布局「{layout}」是 {layout.rows} 排，请选择匹配的布局或修正文件。",
        )
        return redirect("seating:index")
    if detected_cols > layout.cols:
        messages.error(
            request,
            f"表格中识别到 {detected_cols} 列，超过布局「{layout}」的 {layout.cols} 列。",
        )
        return redirect("seating:index")

    students = list(Student.objects.filter(
        Q(school_class=current_class) | Q(school_class__isnull=True), is_deleted=False,
    ))
    by_name = {}
    for student in students:
        by_name.setdefault(student.name.strip(), []).append(student)

    version = (request.POST.get("version") or "").strip()
    reason = (request.POST.get("reason") or "").strip()

    assignments = []
    placed_ids = set()
    skipped = []
    for file_row, row in enumerate(seat_rows):
        grid_row = _map_file_row_to_grid(podium_top, layout.rows, file_row)
        for col, cell in enumerate(row):
            name = cell.strip()
            if not name:
                continue
            matches = by_name.get(name, [])
            if not matches:
                skipped.append(f"第{file_row + 1}行第{col + 1}列「{name}」不在学生花名册中")
            elif len(matches) > 1:
                skipped.append(f"第{file_row + 1}行第{col + 1}列「{name}」花名册中有多个同名，已跳过")
            elif matches[0].pk in placed_ids:
                skipped.append(f"第{file_row + 1}行第{col + 1}列「{name}」重复出现，已跳过")
            else:
                placed_ids.add(matches[0].pk)
                assignments.append((grid_row, col, matches[0]))

    if not assignments:
        messages.error(
            request,
            "未能匹配到任何学生，未创建方案。"
            + ("；".join(skipped[:8]) + ("；…" if len(skipped) > 8 else "") if skipped else ""),
        )
        return redirect("seating:index")

    plan = SeatPlan.objects.create(
        school_class=current_class, layout=layout, version=version, reason=reason,
    )
    SeatPlan.objects.filter(school_class=current_class).exclude(pk=plan.pk).update(is_active=False)
    SeatAssignment.objects.bulk_create([
        SeatAssignment(seat_plan=plan, student=student, row=row, col=col)
        for (row, col, student) in assignments
    ])
    Student.objects.filter(pk__in=placed_ids, school_class__isnull=True).update(
        school_class=current_class,
    )

    OperationLog.objects.create(
        user=request.user, action="import", module="seating",
        object_repr=f"座位方案 v{plan.version or plan.pk}",
        detail=f"Excel 导入 {len(assignments)} 个位置；文件 {upload.name}；跳过 {len(skipped)} 处",
        ip_address=get_client_ip(request), success=True,
    )

    messages.success(request, f"已按 Excel 导入并启用座位方案 v{plan.version or plan.pk}，共安排 {len(assignments)} 名学生。")
    if skipped:
        preview = "；".join(skipped[:8]) + ("；…" if len(skipped) > 8 else "")
        messages.warning(request, f"有 {len(skipped)} 处未能安排：{preview}")
    return redirect("seating:index")


@login_required
@transaction.atomic
def save_plan(request):
    """保存座位分配"""
    current_class = get_current_class(request.user)
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
                    if row not in range(layout.rows) or col not in range(layout.cols):
                        continue
                    student_id = int(value)
                    student = Student.objects.filter(
                        Q(school_class=current_class) | Q(school_class__isnull=True),
                        pk=student_id, is_deleted=False,
                    ).first()
                    if not student:
                        continue
                    if not student.school_class:
                        student.school_class = current_class
                        student.save(update_fields=["school_class", "updated_at"])
                    SeatAssignment.objects.create(
                        seat_plan=plan, student=student, row=row, col=col,
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
    """按用户优先级执行确定性智能排座。"""
    current_class = get_current_class(request.user)
    plan = SeatPlan.objects.filter(school_class=current_class, is_active=True).first()
    if not plan or not plan.layout:
        messages.error(request, "请先创建座位方案并关联教室布局。")
        return redirect("seating:index")

    if request.method == "POST":
        layout = plan.layout
        students = list(Student.objects.filter(
            Q(school_class=current_class) | Q(school_class__isnull=True), is_deleted=False,
        ).order_by("student_id"))
        attach_student_seat_metadata(students, current_class)

        total_seats = layout.rows * layout.cols
        if len(students) > total_seats:
            messages.warning(request, f"学生数（{len(students)}）超过座位数（{total_seats}），部分学生将无法安排。")

        priorities = normalize_priorities([
            request.POST.get(f"priority_{index}", "") for index in range(1, 6)
        ])
        try:
            rotation_interval = min(12, max(0, int(request.POST.get("rotation_interval_months", "1"))))
        except (TypeError, ValueError):
            rotation_interval = 1
        arranged = arrange_students(layout, students, priorities)

        SeatAssignment.objects.filter(seat_plan=plan).delete()
        SeatAssignment.objects.bulk_create([
            SeatAssignment(seat_plan=plan, student=student, row=row, col=col)
            for (row, col), student in arranged.items()
        ])
        Student.objects.filter(
            pk__in=[student.pk for student in arranged.values()], school_class__isnull=True,
        ).update(school_class=current_class)
        plan.arrangement_priorities = priorities
        plan.rotation_interval_months = rotation_interval
        plan.last_rotated_at = timezone.localdate() if rotation_interval else None
        plan.save(update_fields=[
            "arrangement_priorities", "rotation_interval_months", "last_rotated_at", "updated_at",
        ])
        count = len(arranged)

        OperationLog.objects.create(
            user=request.user, action="edit", module="seating",
            object_repr=f"座位方案 v{plan.version or plan.pk}",
            detail=f"智能排座完成，共 {count} 个位置；优先级：{'、'.join(PRIORITY_LABELS[item] for item in priorities)}",
            ip_address=get_client_ip(request), success=True,
        )
        messages.success(request, f"自动排座完成（{count} 名学生）。")
    return redirect("seating:index")


@login_required
def print_plan(request):
    """打印当前座位表，仅显示学生姓名。"""
    current_class = get_current_class(request.user)
    plan = SeatPlan.objects.filter(school_class=current_class, is_active=True).select_related("layout").first()
    if not plan or not plan.layout:
        messages.error(request, "暂无可打印的座位方案。")
        return redirect("seating:index")
    assignments = SeatAssignment.objects.filter(seat_plan=plan).select_related("student")
    return render(request, "seating/print.html", {
        "current_class": current_class,
        "plan": plan,
        "layout": plan.layout,
        "grid": _build_grid(plan.layout, assignments),
        "aisle_positions": plan.layout.aisle_positions or [],
    })
