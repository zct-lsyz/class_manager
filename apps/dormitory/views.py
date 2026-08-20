from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.dormitory.models import (
    DormBuilding, DormRoom, DormBed, DormAssignment,
    DormHygieneItem, DormHygieneCheck, DormHygieneItemScore, DormHygienePhoto,
)
from apps.dormitory.forms import (
    DormBuildingForm, DormRoomForm, DormAssignmentForm,
    DormHygieneItemForm, DormHygieneCheckForm,
)
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass, Semester
from apps.classes.decorators import require_current_class
from apps.students.models import Student
from apps.audit.models import OperationLog
from apps.audit.services import soft_delete
from apps.dormitory.photo_services import prepare_hygiene_photo
from apps.dormitory.services import release_bed
from apps.todos.services import sync_follow_up_todo


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


@login_required
def index(request):
    """宿舍管理首页"""
    current_class = get_current_class(request.user)
    buildings = DormBuilding.objects.filter(school_class=current_class) if current_class else []
    rooms = DormRoom.objects.filter(building__school_class=current_class).select_related("building").prefetch_related("assignments") if current_class else []

    # 统计
    total_rooms = len(rooms)
    total_beds = sum(r.bed_count for r in rooms)
    assigned = DormAssignment.objects.filter(
        room__building__school_class=current_class, is_current=True, bed__isnull=False,
    ).count() if current_class else 0

    # 每宿舍已分配人数（仅统计已占床，与床位分布图一致）
    for r in rooms:
        r.assigned_count = sum(1 for a in r.assignments.all() if a.is_current and a.bed_id)

    return render(request, "dormitory/index.html", {
        "buildings": buildings, "rooms": rooms,
        "total_rooms": total_rooms, "total_beds": total_beds, "assigned": assigned,
    })


@login_required
@require_current_class
def building_create(request):
    """新建宿舍楼"""
    current_class = get_current_class(request.user)
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
@require_current_class
def building_edit(request, pk):
    """修改宿舍楼信息（楼栋名称、层数、排序）"""
    current_class = get_current_class(request.user)
    building = get_object_or_404(DormBuilding, pk=pk, school_class=current_class)
    if request.method == "POST":
        form = DormBuildingForm(request.POST, instance=building)
        if form.is_valid():
            form.save()
            messages.success(request, f"宿舍楼「{building.name}」已更新。")
            return redirect("dormitory:index")
    else:
        form = DormBuildingForm(instance=building)
    return render(request, "dormitory/building_form.html", {"form": form, "building": building})


@login_required
def building_delete(request, pk):
    """删除宿舍楼。

    楼内还有学生住宿时，先自动释放这些学生的床位
    （清空其 dormitory/bed_number 字段），再删除整栋楼。
    """
    current_class = get_current_class(request.user)
    building = get_object_or_404(DormBuilding, pk=pk, school_class=current_class)
    if request.method == "POST":
        # 释放楼内当前住宿的学生：清空宿舍/床位字段
        active_assignments = list(DormAssignment.objects.filter(
            room__building=building, is_current=True,
        ).select_related("student"))
        student_ids = [a.student_id for a in active_assignments]
        if student_ids:
            Student.objects.filter(pk__in=student_ids).update(
                dormitory="", bed_number="", updated_at=timezone.now(),
            )
        room_count = DormRoom.objects.filter(building=building).count()
        building.delete()  # 级联删除楼下的宿舍、床位及分配记录
        released = len(student_ids)
        messages.success(
            request,
            f"宿舍楼「{building.name}」已删除（含 {room_count} 间宿舍）"
            + (f"，已释放 {released} 名学生的床位。" if released else "。"),
        )
    return redirect("dormitory:index")


@login_required
@require_current_class
def room_create(request):
    """新建宿舍（并自动生成床位）"""
    current_class = get_current_class(request.user)
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


@login_required
@transaction.atomic
def room_edit(request, pk):
    """修改宿舍（房间号、床位数、宿舍长、启用、备注）。

    床位数减少时，超出部分床位若未被占用则删除；若被占用则拒绝减少。
    """
    current_class = get_current_class(request.user)
    room = get_object_or_404(DormRoom, pk=pk, building__school_class=current_class)
    if request.method == "POST":
        form = DormRoomForm(request.POST, instance=room)
        # 注意：必须在 form.is_valid() 之前记录旧床位数——
        # ModelForm 校验时会把表单数据写入实例，之后再读会拿到新值
        old_bed_count = room.bed_count
        if form.is_valid():
            room = form.save()
            if room.bed_count < old_bed_count:
                excess = list(DormBed.objects.filter(room=room, is_active=True).order_by("-bed_number")[: old_bed_count - room.bed_count])
                occupied_ids = set(DormAssignment.objects.filter(
                    bed__in=excess, is_current=True,
                ).values_list("bed_id", flat=True))
                if occupied_ids:
                    messages.error(request, "床位数不能小于已占用床位数量，请先调整学生床位后再减少。")
                    room.bed_count = old_bed_count
                    room.save(update_fields=["bed_count", "updated_at"])
                else:
                    for bed in excess:
                        bed.delete()
                    messages.success(request, f"宿舍 {room.room_number} 已更新（{room.bed_count} 床）。")
            else:
                _generate_beds(room)  # 床位数增加时自动补齐床位
                messages.success(request, f"宿舍 {room.room_number} 已更新（{room.bed_count} 床）。")
            return redirect("dormitory:index")
    else:
        form = DormRoomForm(instance=room)
        form.fields["building"].queryset = DormBuilding.objects.filter(school_class=current_class)
    return render(request, "dormitory/room_form.html", {"form": form, "room": room})


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
    current_class = get_current_class(request.user)
    room = get_object_or_404(
        DormRoom, pk=pk, building__school_class=current_class,
    )
    beds = DormBed.objects.filter(room=room)
    assignments = DormAssignment.objects.filter(
        room=room, is_current=True
    ).select_related("student", "bed")

    # 已分配床位映射（仅统计已占床）
    assigned_map = {a.bed_id: a.student for a in assignments if a.bed_id}
    # 已分配但未占床的学生（如导入时床位号未匹配到生成的 01..08 号床）
    bedless = [a.student.name for a in assignments if not a.bed_id]
    # 可选学生 = 本班尚未占床的学生（含未分配者与已分配未占床者）
    occupied_student_ids = assignments.filter(
        bed__isnull=False,
    ).values_list("student_id", flat=True)
    unassigned = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ).exclude(id__in=occupied_student_ids)

    return render(request, "dormitory/room_detail.html", {
        "room": room, "beds": beds, "assigned_map": assigned_map,
        "unassigned": unassigned, "bedless": bedless,
    })


@login_required
def bed_set_monitor(request, pk):
    """从床位一键设置/取消该床学生为宿舍长。"""
    current_class = get_current_class(request.user)
    bed = get_object_or_404(
        DormBed, pk=pk, room__building__school_class=current_class,
    )
    room = bed.room
    if request.method == "POST":
        action = request.POST.get("action", "set")
        if action == "clear":
            room.monitor = None
            messages.info(request, f"{room.room_number} 已取消宿舍长。")
        else:
            assignment = DormAssignment.objects.filter(
                bed=bed, room=room, is_current=True,
            ).select_related("student").first()
            if assignment:
                room.monitor = assignment.student
                messages.success(request, f"已将 {assignment.student.name} 设为 {room.room_number} 宿舍长。")
            else:
                messages.error(request, "该床位暂无学生，无法设置舍长。")
        room.save(update_fields=["monitor", "updated_at"])
    return redirect("dormitory:room_detail", pk=room.pk)


@login_required
@transaction.atomic
def bed_assign(request, pk):
    """分配床位"""
    current_class = get_current_class(request.user)
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
            # 先取消该学生其他分配（释放床位，避免 OneToOne 唯一约束冲突）
            DormAssignment.objects.filter(student=student, is_current=True).update(is_current=False, bed=None)
            # 释放目标床的所有引用（含历史分配，bed_id 有全局唯一约束）
            release_bed(bed)
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
            # 清空床位（释放床位引用，含历史分配）
            release_bed(bed)
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
    current_class = get_current_class(request.user)
    checks = DormHygieneCheck.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("room__building").order_by("-date") if current_class else []

    paginator = Paginator(checks, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "dormitory/hygiene.html", {"page_obj": page_obj})


@login_required
@require_current_class
def hygiene_items(request):
    """卫生检查项目配置"""
    current_class = get_current_class(request.user)
    items = DormHygieneItem.objects.filter(school_class=current_class) if current_class else []

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        full_score = request.POST.get("full_score", "10")
        default_deduction = request.POST.get("default_deduction", "0")
        default_severity = request.POST.get("default_severity", "moderate")
        if default_severity not in dict(DormHygieneItem.SEVERITY_CHOICES):
            default_severity = "moderate"
        if name:
            try:
                full_score = int(full_score)
                default_deduction = int(default_deduction)
            except (ValueError, TypeError):
                full_score, default_deduction = 10, 0
            DormHygieneItem.objects.create(
                school_class=current_class, name=name,
                full_score=full_score, default_deduction=default_deduction,
                default_severity=default_severity,
            )
            messages.success(request, f"卫生项目「{name}」已添加。")
        else:
            messages.error(request, "项目名称不能为空。")
        return redirect("dormitory:hygiene_items")

    return render(request, "dormitory/hygiene_items.html", {"items": items})


@login_required
def hygiene_item_delete(request, pk):
    """删除卫生项目"""
    current_class = get_current_class(request.user)
    item = get_object_or_404(DormHygieneItem, pk=pk, school_class=current_class)
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
    current_class = get_current_class(request.user)
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


def _create_hygiene_deductions(current_class, current_semester, check, students, deduction, severity="moderate", item_name="卫生检查不达标"):
    """卫生检查不达标时，为选中学生各创建一条宿舍纪律扣分记录并同步积分。"""
    from apps.discipline.models import DormDisciplineRecord
    from apps.rewards.services import sync_source_point
    created = 0
    with transaction.atomic():
        for st in students:
            record = DormDisciplineRecord.objects.create(
                school_class=current_class,
                semester=current_semester,
                student=st,
                dorm_room=check.room,
                date=check.date,
                time=check.check_time,
                item=None,
                custom_content=item_name,
                severity=severity,
                description=f"卫生检查扣分：{check.room}，扣 {deduction} 分",
                action_taken=check.rectification,
                points_deducted=deduction,
                needs_follow_up=False,
                remarks="",
                source_check=check,
            )
            sync_source_point(
                student=st, school_class=current_class,
                semester=current_semester, date=record.date,
                points=-deduction, reason=item_name,
                source_type="dorm_discipline", source_id=record.pk,
            )
            created += 1
    return created


@login_required
def hygiene_create(request):
    """录入卫生检查（含项目得分；不达标时给选中的学生同步扣分）"""
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()
    items = DormHygieneItem.objects.filter(school_class=current_class, is_active=True) if current_class else []
    rooms = DormRoom.objects.filter(building__school_class=current_class).select_related("building") if current_class else []
    dorm_room_students = _build_room_students(current_class)

    if request.method == "POST":
        form = DormHygieneCheckForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                check = form.save(commit=False)
                check.school_class = current_class
                check.semester = current_semester
                check.save()
                sync_follow_up_todo(check, request.user)

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

                # 保存父记录后写项目得分：扣分事项（下拉）→ 扣分分数 → 得分 = 满分 - 扣分
                total = 0
                deduction = 0
                checked_item = None
                item_id = request.POST.get("deduct_item", "")
                if item_id.isdigit():
                    checked_item = next(
                        (i for i in items if i.pk == int(item_id)), None,
                    )
                if checked_item:
                    raw = request.POST.get("deduct_points", "").strip()
                    try:
                        deduct = int(raw) if raw else checked_item.default_deduction
                    except (ValueError, TypeError):
                        deduct = checked_item.default_deduction
                    deduct = max(0, min(deduct, checked_item.full_score))
                    score = checked_item.full_score - deduct
                    total = score
                    deduction = deduct
                    DormHygieneItemScore.objects.create(
                        check_record=check, item=checked_item, score=score,
                        deduction_reason=f"{checked_item.name}扣{deduct}分" if deduct else "",
                    )
                check.total_score = total
                if items:
                    full = sum(item.full_score for item in items)
                    if full > 0:
                        deduct_ratio = deduction / full
                        if deduct_ratio == 0:
                            check.grade = "excellent"
                        elif deduct_ratio <= 0.1:
                            check.grade = "good"
                        elif deduct_ratio <= 0.2:
                            check.grade = "fair"
                        else:
                            check.grade = "poor"
                check.save(update_fields=["total_score", "grade", "updated_at"])

            # 卫生不达标（有扣分）→ 给选中的学生同步扣分
            deducted_count = 0
            if deduction > 0:
                student_mode = request.POST.get("student_mode", "one")
                if student_mode == "all":
                    students = _room_students(check.room)
                elif student_mode == "selected":
                    student_ids = request.POST.getlist("students")
                    students = Student.objects.filter(
                        pk__in=student_ids, school_class=current_class, is_deleted=False,
                        dorm_assignments__room=check.room, dorm_assignments__is_current=True,
                    ).distinct()
                else:
                    students = Student.objects.none()
                if students.exists():
                    item_name = f"{checked_item.name}不合格" if checked_item else "卫生检查不达标"
                    deducted_count = _create_hygiene_deductions(
                        current_class, current_semester, check, students, deduction,
                        item_name=item_name,
                    )
                    OperationLog.objects.create(
                        user=request.user, action="create", module="dormitory",
                        object_repr=f"{check.room} 卫生检查",
                        detail=f"卫生不达标同步扣分：{deducted_count} 人，每人扣 {deduction} 分",
                        ip_address=get_client_ip(request), success=True,
                    )
            msg = f"卫生检查已保存（总分 {total} 分"
            if deducted_count:
                msg += f"，{deducted_count} 名学生各扣 {deduction} 分"
            msg += "）。"
            messages.success(request, msg)
            return redirect("dormitory:hygiene")
    else:
        form = DormHygieneCheckForm()

    form.fields["room"].queryset = rooms

    return render(request, "dormitory/hygiene_form.html", {
        "form": form, "items": items, "rooms": rooms,
        "dorm_room_students": dorm_room_students,
    })


@login_required
def hygiene_detail(request, pk):
    """卫生检查详情（含项目得分）"""
    current_class = get_current_class(request.user)
    check = get_object_or_404(
        DormHygieneCheck.objects.select_related("room__building"),
        pk=pk, school_class=current_class, is_deleted=False,
    )
    scores = DormHygieneItemScore.objects.filter(check_record=check).select_related("item")
    for s in scores:
        s.deduction = (s.item.full_score - s.score) if s.item else 0
    return render(request, "dormitory/hygiene_detail.html", {"check": check, "scores": scores})


@login_required
def hygiene_delete(request, pk):
    current_class = get_current_class(request.user)
    check = get_object_or_404(
        DormHygieneCheck, pk=pk, school_class=current_class, is_deleted=False,
    )
    if request.method == "POST":
        # 同步处理的纪律扣分记录：撤销积分并一并软删除
        from apps.discipline.models import DormDisciplineRecord
        from apps.audit.services import _linked_discipline_records
        for record in _linked_discipline_records(check):
            from apps.rewards.services import unsync_source_point
            unsync_source_point("dorm_discipline", record.pk)
            if not record.is_deleted:
                soft_delete(
                    record,
                    user=request.user,
                    module="dormitory",
                    model_name="dormdiscipline",
                )
        soft_delete(
            check,
            user=request.user,
            module="dormitory",
            model_name="hygienecheck",
        )
        messages.info(request, "卫生检查已移入回收站，关联扣分与积分已同步撤销。")
    return redirect("dormitory:hygiene")


@login_required
def discipline(request):
    """宿舍纪律（列表）"""
    from apps.discipline.models import DormDisciplineRecord
    current_class = get_current_class(request.user)
    records = DormDisciplineRecord.objects.filter(
        school_class=current_class, is_deleted=False
    ).select_related("student", "item", "dorm_room").order_by("-date") if current_class else []

    paginator = Paginator(records, 30)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "dormitory/discipline_list.html", {"page_obj": page_obj})


def _room_students(room):
    """获取宿舍当前分配的学生。"""
    return Student.objects.filter(
        dorm_assignments__room=room, dorm_assignments__is_current=True,
        is_deleted=False,
    ).distinct()


def _create_dorm_discipline_records(current_class, current_semester, room, students, request, points, item):
    """为多个学生创建宿舍纪律记录并同步积分。返回创建条数。"""
    from apps.discipline.models import DormDisciplineRecord
    from apps.rewards.services import sync_source_point
    from datetime import date as _date, time as _time

    def _as_date(name, default=None):
        v = request.POST.get(name, "")
        try:
            return _date.fromisoformat(v) if v else default
        except ValueError:
            return default

    def _as_time(name):
        v = request.POST.get(name, "")
        try:
            hh, mm = v.split(":")
            return _time(int(hh), int(mm))
        except (ValueError, TypeError):
            return None

    created = 0
    with transaction.atomic():
        for st in students:
            record = DormDisciplineRecord.objects.create(
                school_class=current_class,
                semester=current_semester,
                student=st,
                dorm_room=room,
                date=_as_date("date", timezone.localdate()),
                time=_as_time("time"),
                item=item,
                custom_content=request.POST.get("custom_content", "").strip(),
                severity=request.POST.get("severity", "moderate"),
                description=request.POST.get("description", "").strip(),
                action_taken=request.POST.get("action_taken", "").strip(),
                points_deducted=points,
                needs_follow_up=request.POST.get("needs_follow_up") == "on",
                follow_up_date=_as_date("follow_up_date"),
                follow_up_result=request.POST.get("follow_up_result", "").strip(),
                remarks=request.POST.get("remarks", "").strip(),
            )
            # 同步到统一积分（正的 points_deducted 记扣分）
            if points:
                item_name = item.name if item else (record.custom_content or "宿舍纪律")
                sync_source_point(
                    student=st, school_class=current_class,
                    semester=current_semester, date=record.date,
                    points=-points, reason=f"{record.get_severity_display()}：{item_name}",
                    source_type="dorm_discipline", source_id=record.pk,
                )
            sync_follow_up_todo(record, request.user)
            created += 1
    return created


@login_required
def discipline_create(request):
    """登记宿舍纪律（先选宿舍→多选该宿舍学生或全体同步加减分）"""
    from apps.discipline.forms import DormDisciplineForm
    from apps.discipline.models import ConfigurableItem
    current_class = get_current_class(request.user)
    current_semester = Semester.objects.filter(
        school_class=current_class, is_current=True,
    ).first()

    rooms = DormRoom.objects.filter(
        building__school_class=current_class,
    ).select_related("building").order_by("building", "room_number") if current_class else []

    if request.method == "POST":
        student_mode = request.POST.get("student_mode", "one")

        if student_mode in ("all", "selected"):
            room_id = request.POST.get("dorm_room", "")
            room = None
            if room_id:
                room = get_object_or_404(
                    DormRoom, pk=room_id, building__school_class=current_class,
                )
            if not room:
                messages.error(request, "请先选择宿舍。")
                return redirect("dormitory:discipline_create")

            item = None
            item_id = request.POST.get("item", "")
            if item_id:
                item = ConfigurableItem.objects.filter(
                    pk=item_id, module="dorm_discipline", school_class=current_class,
                ).first()
            try:
                points = abs(int(request.POST.get("points_deducted", "0") or "0"))
            except (ValueError, TypeError):
                points = 0
            # 分值恒为正；纪律中 points_deducted 正=扣分、负=加分
            if request.POST.get("points_sign") == "add":
                points = -points

            if student_mode == "all":
                students = _room_students(room)
            else:
                student_ids = request.POST.getlist("students")
                students = Student.objects.filter(
                    pk__in=student_ids, school_class=current_class, is_deleted=False,
                    dorm_assignments__room=room, dorm_assignments__is_current=True,
                ).distinct()

            if not students.exists():
                messages.error(request, "请选择至少一名学生（或该宿舍暂无分配学生）。")
                return redirect("dormitory:discipline_create")

            created = _create_dorm_discipline_records(
                current_class, current_semester, room, students, request, points, item,
            )
            messages.success(
                request,
                f"已为 {created} 名学生登记宿舍纪律（每人{'扣' if points else '加'} {abs(points)} 分）。",
            )
            OperationLog.objects.create(
                user=request.user, action="create", module="dormitory",
                object_repr=f"{room} 宿舍纪律",
                detail=f"宿舍纪律登记：{created} 人，{points} 分",
                ip_address=get_client_ip(request), success=True,
            )
            return redirect("dormitory:discipline")

        # 单学生模式（表单含完整学生字段）
        form = DormDisciplineForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.school_class = current_class
            record.semester = current_semester
            # 分值恒为正；纪律中 points_deducted 正=扣分、负=加分
            value = abs(record.points_deducted or 0)
            record.points_deducted = -value if request.POST.get("points_sign") == "add" else value
            record.save()
            sync_follow_up_todo(record, request.user)
            messages.success(request, "宿舍纪律记录已保存。")
            return redirect("dormitory:discipline")
        return render(request, "dormitory/discipline_form.html", {
            "form": form, "rooms": rooms, "dorm_room_students": _build_room_students(current_class),
        })

    form = DormDisciplineForm()
    form.fields["dorm_room"].queryset = rooms
    form.fields["student"].queryset = Student.objects.filter(
        school_class=current_class, is_deleted=False,
    ) if current_class else Student.objects.none()

    return render(request, "dormitory/discipline_form.html", {
        "form": form, "rooms": rooms, "dorm_room_students": _build_room_students(current_class),
    })


def _build_room_students(current_class):
    """构建 {room_id: [{id, name, bed}]} 宿舍→当前分配学生映射，供前端联动。"""
    data = {}
    if not current_class:
        return data
    assignments = DormAssignment.objects.filter(
        room__building__school_class=current_class, is_current=True,
    ).select_related("room", "student", "bed").order_by("room_id", "bed__bed_number", "student__name")
    for a in assignments:
        data.setdefault(a.room_id, []).append({
            "id": a.student_id,
            "name": a.student.name,
            "bed": a.bed.bed_number if a.bed else "",
        })
    return data
