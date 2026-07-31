from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q

from apps.dormitory.models import (
    DormBuilding, DormRoom, DormBed, DormAssignment,
    DormHygieneItem, DormHygieneCheck, DormHygieneItemScore, DormHygienePhoto,
)
from apps.dormitory.forms import (
    DormBuildingForm, DormRoomForm, DormAssignmentForm,
    DormHygieneItemForm, DormHygieneCheckForm,
)
from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student
from apps.audit.models import OperationLog
from apps.audit.services import soft_delete
from apps.dormitory.photo_services import prepare_hygiene_photo


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


@login_required
def index(request):
    """宿舍管理首页"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    buildings = DormBuilding.objects.filter(school_class=current_class) if current_class else []
    rooms = DormRoom.objects.filter(building__school_class=current_class).select_related("building").prefetch_related("assignments") if current_class else []

    # 统计
    total_rooms = len(rooms)
    total_beds = sum(r.bed_count for r in rooms)
    assigned = DormAssignment.objects.filter(room__building__school_class=current_class, is_current=True).count() if current_class else 0

    # 每宿舍已分配人数
    for r in rooms:
        r.assigned_count = sum(1 for a in r.assignments.all() if a.is_current)

    return render(request, "dormitory/index.html", {
        "buildings": buildings, "rooms": rooms,
        "total_rooms": total_rooms, "total_beds": total_beds, "assigned": assigned,
    })


@login_required
def building_create(request):
    """新建宿舍楼"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = DormBuildingForm(request.POST)
        if form.is_valid():
            b = form.save(commit=False)
            b.school_class = current_class
            b.save()
            messages.success(request, f"宿舍楼「{b.name}」已创建。")
            return redirect("dormitory:index")
    else:
        form = DormBuildingForm()
    return render(request, "dormitory/building_form.html", {"form": form})


@login_required
def room_create(request):
    """新建宿舍（并自动生成床位）"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    if request.method == "POST":
        form = DormRoomForm(request.POST)
        if form.is_valid():
            room = form.save()
            # 自动生成床位
            _generate_beds(room)
            messages.success(request, f"宿舍 {room.room_number} 已创建，并自动生成 {room.bed_count} 个床位。")
            return redirect("dormitory:index")
    else:
        form = DormRoomForm()
        form.fields["building"].queryset = DormBuilding.objects.filter(school_class=current_class)
    return render(request, "dormitory/room_form.html", {"form": form})


def _generate_beds(room):
    """为宿舍生成床位（1-床位数，编号如 01、02...）"""
    existing = set(DormBed.objects.filter(room=room).values_list("bed_number", flat=True))
    for i in range(1, room.bed_count + 1):
        bed_no = f"{i:02d}"
        if bed_no not in existing:
            DormBed.objects.create(room=room, bed_number=bed_no)


@login_required
def room_detail(request, pk):
    """宿舍详情：床位列表 + 分配状态"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    room = get_object_or_404(
        DormRoom, pk=pk, building__school_class=current_class,
    )
    beds = DormBed.objects.filter(room=room)
    assignments = DormAssignment.objects.filter(
        room=room, is_current=True
    ).select_related("student", "bed")

    # 已分配床位映射
    assigned_map = {a.bed_id: a.student for a in assignments if a.bed_id}
    unassigned = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).exclude(
        id__in=assignments.values_list("student_id", flat=True)
    )

    return render(request, "dormitory/room_detail.html", {
        "room": room, "beds": beds, "assigned_map": assigned_map, "unassigned": unassigned,
    })


@login_required
@transaction.atomic
def bed_assign(request, pk):
    """分配床位"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    bed = get_object_or_404(
        DormBed, pk=pk, room__building__school_class=current_class,
    )
    if request.method == "POST":
        student_id = request.POST.get("student_id", "")
        previous_students = list(Student.objects.filter(
            dorm_assignments__is_current=True,
        ).filter(
            Q(dorm_assignments__bed=bed) | Q(pk=student_id or None)
        ).distinct())
        if student_id:
            student = get_object_or_404(
                Student, pk=student_id, school_class=current_class, is_deleted=False,
            )
            # 先取消该学生其他分配
            DormAssignment.objects.filter(student=student, is_current=True).update(is_current=False)
            # 如果床位已有学生，取消其分配
            DormAssignment.objects.filter(bed=bed, is_current=True).update(is_current=False)
            DormAssignment.objects.create(
                student=student, room=bed.room, bed=bed, is_current=True,
                semester=Semester.objects.filter(
                    school_class=current_class, is_current=True,
                ).first(),
            )
            student.dormitory = str(bed.room)
            student.bed_number = bed.bed_number
            student.save(update_fields=["dormitory", "bed_number", "updated_at"])
            messages.success(request, f"{student.name} 已分配至 {bed.room.room_number} - {bed.bed_number} 号床。")
        else:
            # 清空床位
            DormAssignment.objects.filter(bed=bed, is_current=True).update(is_current=False)
            messages.info(request, "床位已清空。")
        for previous_student in previous_students:
            if not previous_student.dorm_assignments.filter(is_current=True).exists():
                previous_student.dormitory = ""
                previous_student.bed_number = ""
                previous_student.save(update_fields=["dormitory", "bed_number", "updated_at"])
        return redirect("dormitory:room_detail", pk=bed.room.pk)
    return redirect("dormitory:index")


@login_required
def hygiene(request):
    """宿舍卫生检查列表"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    checks = DormHygieneCheck.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("room__building").order_by("-date") if current_class else []

    paginator = Paginator(checks, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "dormitory/hygiene.html", {"page_obj": page_obj})


@login_required
def hygiene_items(request):
    """卫生检查项目配置"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    items = DormHygieneItem.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        full_score = request.POST.get("full_score", "10")
        default_deduction = request.POST.get("default_deduction", "0")
        if name:
            try:
                full_score = int(full_score)
                default_deduction = int(default_deduction)
            except (ValueError, TypeError):
                full_score, default_deduction = 10, 0
            DormHygieneItem.objects.create(
                school_class=current_class, name=name,
                full_score=full_score, default_deduction=default_deduction,
            )
            messages.success(request, f"卫生项目「{name}」已添加。")
        else:
            messages.error(request, "项目名称不能为空。")
        return redirect("dormitory:hygiene_items")

    return render(request, "dormitory/hygiene_items.html", {"items": items})


@login_required
def hygiene_item_delete(request, pk):
    """删除卫生项目"""
    item = get_object_or_404(DormHygieneItem, pk=pk)
    if request.method == "POST":
        if item.dormhygieneitemscore_set.exists():
            item.is_active = False
            item.save(update_fields=["is_active", "updated_at"])
            messages.info(
                request,
                f"卫生项目「{item.name}」已有历史记录，已改为停用。",
            )
        else:
            item.delete()
            messages.info(request, f"卫生项目「{item.name}」已删除。")
    return redirect("dormitory:hygiene_items")


@login_required
def hygiene_item_edit(request, pk):
    current_class = SchoolClass.objects.filter(is_current=True).first()
    item = get_object_or_404(
        DormHygieneItem, pk=pk, school_class=current_class
    )
    if request.method == "POST":
        form = DormHygieneItemForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, f"卫生项目「{item.name}」已更新。")
            return redirect("dormitory:hygiene_items")
    else:
        form = DormHygieneItemForm(instance=item)
    return render(
        request,
        "dormitory/hygiene_item_form.html",
        {"form": form, "item": item},
    )


@login_required
def hygiene_create(request):
    """录入卫生检查（含项目得分）"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()
    items = DormHygieneItem.objects.filter(school_class=current_class, is_active=True) if current_class else []

    if request.method == "POST":
        form = DormHygieneCheckForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                check = form.save(commit=False)
                check.school_class = current_class
                check.semester = current_semester
                check.save()

                for uploaded in form.cleaned_data["photos"]:
                    image_file, original_size = prepare_hygiene_photo(uploaded)
                    photo = DormHygienePhoto(
                        check_record=check,
                        original_name=uploaded.name,
                        original_size=original_size,
                    )
                    photo.image.save(image_file.name, image_file, save=False)
                    photo.stored_size = image_file.size
                    photo.save()

                # 保存父记录后再写项目得分
                total = 0
                for item in items:
                    score_val = request.POST.get(f"item_{item.pk}", "")
                    if score_val == "":
                        continue
                    try:
                        score = int(score_val)
                    except (ValueError, TypeError):
                        score = 0
                    score = max(0, min(score, item.full_score))
                    total += score
                    DormHygieneItemScore.objects.create(
                        check_record=check, item=item, score=score,
                    )
                check.total_score = total
                if items:
                    full = sum(item.full_score for item in items)
                    if full > 0:
                        ratio = total / full
                        if ratio >= 0.9:
                            check.grade = "excellent"
                        elif ratio >= 0.8:
                            check.grade = "good"
                        elif ratio >= 0.6:
                            check.grade = "fair"
                        else:
                            check.grade = "poor"
                check.save(update_fields=["total_score", "grade", "updated_at"])
            messages.success(request, f"卫生检查已保存（总分 {total} 分）。")
            return redirect("dormitory:hygiene")
    else:
        form = DormHygieneCheckForm()

    rooms = DormRoom.objects.filter(building__school_class=current_class).select_related("building") if current_class else []
    form.fields["room"].queryset = rooms

    return render(request, "dormitory/hygiene_form.html", {
        "form": form, "items": items,
    })


@login_required
def hygiene_detail(request, pk):
    """卫生检查详情（含项目得分）"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    check = get_object_or_404(
        DormHygieneCheck.objects.select_related("room__building"),
        pk=pk, school_class=current_class, is_deleted=False,
    )
    scores = DormHygieneItemScore.objects.filter(check_record=check).select_related("item")
    return render(request, "dormitory/hygiene_detail.html", {"check": check, "scores": scores})


@login_required
def hygiene_delete(request, pk):
    current_class = SchoolClass.objects.filter(is_current=True).first()
    check = get_object_or_404(
        DormHygieneCheck, pk=pk, school_class=current_class, is_deleted=False,
    )
    if request.method == "POST":
        soft_delete(
            check,
            user=request.user,
            module="dormitory",
            model_name="hygienecheck",
        )
        messages.info(request, "卫生检查已移入回收站。")
    return redirect("dormitory:hygiene")


@login_required
def discipline(request):
    """宿舍纪律（列表）"""
    from apps.discipline.models import DormDisciplineRecord
    current_class = SchoolClass.objects.filter(is_current=True).first()
    records = DormDisciplineRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item", "dorm_room").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "dormitory/discipline_list.html", {"page_obj": page_obj})


@login_required
def discipline_create(request):
    """登记宿舍纪律"""
    from apps.discipline.models import DormDisciplineRecord
    from apps.discipline.forms import DormDisciplineForm
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    if request.method == "POST":
        form = DormDisciplineForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            record.save()
            messages.success(request, "宿舍纪律记录已保存。")
            return redirect("dormitory:discipline")
    else:
        form = DormDisciplineForm()

    return render(request, "dormitory/discipline_form.html", {"form": form})
