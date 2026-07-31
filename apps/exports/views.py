"""
模块数据导出视图
支持：各模块独立 Excel 导出 + 一键全量导出 ZIP
"""
import io
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.core.paginator import Paginator

from apps.exports.models import ExportTask
from apps.classes.models import SchoolClass
from apps.classes.decorators import require_current_class
from apps.exports.services import (
    export_to_excel,
    build_excel_bytes,
    make_full_export_zip,
    fmt,
)
from apps.audit.models import OperationLog
from apps.exports.module_data import MODULE_EXPORTS, collect_module_data
from apps.exports.option_services import import_options, option_template_response


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


@login_required
def export_center(request):
    """模块数据导出中心"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    tasks = ExportTask.objects.filter(school_class=current_class).order_by("-created_at")[:20] if current_class else []

    modules = [(key, name) for key, name, _path in MODULE_EXPORTS]

    return render(request, "exports/center.html", {"modules": modules, "tasks": tasks})


@login_required
def option_template(request, category):
    try:
        return option_template_response(category)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:index")


@login_required
@require_current_class
def option_import(request, category):
    redirects = {
        "classroom_discipline": "discipline:classroom_items", "dorm_discipline": "discipline:dorm_items",
        "reward": "rewards:rules", "dorm_hygiene": "dormitory:hygiene_items",
        "attendance_reason": "attendance:reasons", "duty_task": "duty:task_list",
        "homework_status": "homework:status_settings",
    }
    if request.method == "POST" and request.FILES.get("file"):
        current_class = SchoolClass.objects.filter(is_current=True).first()
        try:
            count = import_options(category, request.FILES["file"], current_class)
            messages.success(request, f"已导入或更新 {count} 个选项。")
        except Exception as exc:
            messages.error(request, f"导入失败：{exc}")
    return redirect(redirects.get(category, "dashboard:index"))


@login_required
def export_module(request, module):
    """导出指定模块数据（Excel）"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    from apps.audit.models import OperationLog as Log

    if not current_class:
        messages.error(request, "请先设置当前班级。")
        return redirect("exports:export_center")

    try:
        rows, headers, sheet_name, filename = _collect_module_data(module, current_class)
        # 写入导出任务记录
        ExportTask.objects.create(
            user=request.user,
            school_class=current_class,
            module=sheet_name,
            export_format="xlsx",
            status="completed",
            record_count=len(rows),
        )
        Log.objects.create(
            user=request.user, action="export", module=module,
            object_repr=f"{sheet_name} ({len(rows)}条)",
            detail=f"导出模块: {sheet_name}, 共 {len(rows)} 条记录",
            ip_address=get_client_ip(request), success=True,
        )
        return export_to_excel(rows, headers, filename, sheet_name)
    except Exception as exc:
        Log.objects.create(
            user=request.user, action="export", module=module,
            object_repr=module, detail=f"导出失败: {exc}",
            ip_address=get_client_ip(request), success=False,
        )
        messages.error(request, f"导出失败: {exc}")
        return redirect("exports:export_center")


def _collect_module_data(module, current_class):
    """收集模块数据，返回 (rows, headers, sheet_name, filename)"""
    try:
        return collect_module_data(module, current_class)
    except KeyError:
        pass
    # 学生花名册
    if module == "students":
        from apps.students.models import Student
        qs = Student.objects.filter(is_deleted=False)
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            s.student_id, s.name,
            "男" if s.gender == "male" else "女",
            fmt(s.birth_date), fmt(s.height), s.vision,
            s.seat_requirement, s.class_position, s.dormitory,
            s.bed_number, s.primary_contact, s.primary_phone, s.remarks,
        ] for s in qs]
        return rows, ["学号", "姓名", "性别", "出生日期", "身高(cm)", "视力", "座位需求", "职务", "宿舍", "床位", "联系人", "电话", "备注"], "学生花名册", "students.xlsx"

    # 家长联系方式
    if module == "guardians":
        from apps.students.models import Guardian
        qs = Guardian.objects.select_related("student").all()
        if current_class:
            qs = qs.filter(student__school_class=current_class)
        rows = [[
            g.student.student_id, g.student.name,
            g.father_name, g.father_phone, g.mother_name, g.mother_phone,
            g.other_guardian, g.primary_contact, g.home_address, g.remarks,
        ] for g in qs]
        return rows, ["学号", "姓名", "父亲姓名", "父亲电话", "母亲姓名", "母亲电话", "其他监护人", "主要联系人", "家庭地址", "备注"], "家长联系方式", "guardians.xlsx"

    # 考勤
    if module == "attendance":
        from apps.attendance.models import AttendanceRecord
        qs = AttendanceRecord.objects.select_related("student")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            fmt(r.date), r.student.student_id, r.student.name,
            r.get_period_display(), r.get_status_display(), r.reason,
        ] for r in qs]
        return rows, ["日期", "学号", "姓名", "时段", "状态", "原因"], "考勤记录", "attendance.xlsx"

    # 课堂纪律
    if module == "discipline":
        from apps.discipline.models import ClassroomDisciplineRecord
        qs = ClassroomDisciplineRecord.objects.filter(is_deleted=False).select_related("student", "item")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            fmt(r.date), r.student.student_id, r.student.name,
            r.item.name if r.item else r.custom_content,
            r.get_severity_display(), r.points_deducted,
            r.description, r.action_taken, r.remarks,
        ] for r in qs]
        return rows, ["日期", "学号", "姓名", "条目", "严重程度", "扣分", "事件经过", "处理措施", "备注"], "课堂纪律", "classroom_discipline.xlsx"

    # 奖励
    if module == "rewards":
        from apps.rewards.models import RewardRecord
        qs = RewardRecord.objects.filter(is_deleted=False).select_related("student", "item")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            fmt(r.date), r.student.student_id, r.student.name,
            r.item.name if r.item else r.custom_name,
            r.get_level_display(), r.points, r.description,
        ] for r in qs]
        return rows, ["日期", "学号", "姓名", "奖励", "等级", "加分", "说明"], "奖励记录", "rewards.xlsx"

    # 积分
    if module == "points":
        from apps.rewards.models import PointRecord
        qs = PointRecord.objects.filter(is_deleted=False).select_related("student")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            fmt(r.date), r.student.student_id, r.student.name,
            r.points, r.reason, r.get_source_type_display(),
        ] for r in qs]
        return rows, ["日期", "学号", "姓名", "分值", "原因", "来源"], "积分明细", "points.xlsx"

    # 成绩
    if module == "scores":
        from apps.scores.models import Score
        qs = Score.objects.filter().select_related("student", "exam_subject__subject", "exam")
        if current_class:
            qs = qs.filter(exam__school_class=current_class)
        rows = [[
            r.exam.name if r.exam else "", r.exam_subject.subject.name if r.exam_subject else "",
            r.student.student_id, r.student.name, fmt(r.score), r.get_status_display(), r.rank,
        ] for r in qs]
        return rows, ["考试", "科目", "学号", "姓名", "成绩", "状态", "名次"], "成绩", "scores.xlsx"

    # 评语
    if module == "comments":
        from apps.comments.models import StudentComment
        qs = StudentComment.objects.filter(is_deleted=False).select_related("student")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            r.student.student_id, r.student.name,
            r.get_comment_type_display(), r.content,
            r.get_status_display(), fmt(r.created_at),
        ] for r in qs]
        return rows, ["学号", "姓名", "类型", "内容", "状态", "创建时间"], "学生评语", "comments.xlsx"

    # 谈话记录
    if module == "conversations":
        from apps.communications.models import StudentConversation
        qs = StudentConversation.objects.filter(is_deleted=False).select_related("student")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            fmt(r.date), r.student.student_id, r.student.name,
            r.reason, r.main_content, r.student_feedback,
            fmt(r.follow_up_date), "私密" if r.is_private else "公开",
        ] for r in qs]
        return rows, ["日期", "学号", "姓名", "原因", "主要内容", "学生反馈", "跟进日期", "可见性"], "谈话记录", "conversations.xlsx"

    # 活动
    if module == "activities":
        from apps.activities.models import Activity
        qs = Activity.objects.all()
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            a.name, a.get_activity_type_display(), fmt(a.date),
            a.person_in_charge, a.result, a.award, a.summary,
        ] for a in qs]
        return rows, ["名称", "类型", "日期", "负责人", "结果", "获奖", "总结"], "文体活动", "activities.xlsx"

    # 宿舍
    if module == "dormitory":
        from apps.dormitory.models import DormRoom, DormAssignment
        rooms = DormRoom.objects.select_related("building", "monitor")
        if current_class:
            rooms = rooms.filter(building__school_class=current_class)
        rows = []
        for r in rooms:
            members = DormAssignment.objects.filter(room=r, is_current=True).select_related("student")
            member_names = "、".join([m.student.name for m in members])
            rows.append([
                r.building.name if r.building else "", r.room_number, r.floor,
                r.get_room_type_display(), r.bed_count,
                r.monitor.name if r.monitor else "", member_names, r.remarks,
            ])
        return rows, ["宿舍楼", "房间号", "楼层", "类型", "床位数", "宿舍长", "成员", "备注"], "宿舍", "dormitory.xlsx"

    # 作业
    if module == "homework":
        from apps.homework.models import HomeworkTask
        qs = HomeworkTask.objects.select_related("subject")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            t.title, t.subject.name if t.subject else "", t.content,
            fmt(t.assigned_date), fmt(t.due_date), t.person_in_charge, t.remarks,
        ] for t in qs]
        return rows, ["作业名称", "科目", "内容", "布置日期", "截止日期", "负责人", "备注"], "作业任务", "homework.xlsx"

    # 座位
    if module == "seating":
        from apps.seating.models import SeatPlan, SeatAssignment
        plans = SeatPlan.objects.all()
        if current_class:
            plans = plans.filter(school_class=current_class)
        rows = []
        for p in plans:
            for a in SeatAssignment.objects.filter(seat_plan=p).select_related("student"):
                rows.append([
                    p.version or str(p.pk), fmt(p.created_at),
                    a.student.student_id, a.student.name, a.row, a.col,
                ])
        return rows, ["方案", "创建时间", "学号", "姓名", "排", "列"], "座位分配", "seating.xlsx"

    # 值日
    if module == "duty":
        from apps.duty.models import DutyGroup
        qs = DutyGroup.objects.prefetch_related("members", "leader")
        if current_class:
            qs = qs.filter(school_class=current_class)
        rows = [[
            g.name, g.week, g.leader.name if g.leader else "",
            "、".join([m.name for m in g.members.all()]),
            "是" if g.is_active else "否",
        ] for g in qs]
        return rows, ["组名", "周次", "组长", "成员", "当前"], "值日小组", "duty.xlsx"

    raise ValueError(f"不支持的模块: {module}")


@login_required
def full_export(request):
    """一键全量导出所有模块（ZIP）"""
    current_class = SchoolClass.objects.filter(is_current=True).first()

    if not current_class:
        messages.error(request, "请先设置当前班级。")
        return redirect("exports:export_center")
    if request.method != "POST":
        return render(request, "exports/full_export.html", {"module_count": len(MODULE_EXPORTS)})
    if request.POST.get("confirm") != "1":
        messages.error(request, "请确认导出范围和敏感数据风险。")
        return redirect("exports:full_export")

    module_files = []
    include_attachments = request.POST.get("include_attachments") == "1"
    try:
        for module, _name, zip_path in MODULE_EXPORTS:
            rows, headers, sheet_name, filename = _collect_module_data(module, current_class)
            content = build_excel_bytes(rows, headers, sheet_name)
            module_files.append((zip_path, content, len(rows)))
        if include_attachments:
            media_root = Path(settings.MEDIA_ROOT)
            if media_root.exists():
                for attachment in sorted(path for path in media_root.rglob("*") if path.is_file()):
                    relative_path = attachment.relative_to(media_root).as_posix()
                    module_files.append((f"attachments/{relative_path}", attachment.read_bytes(), 1))
    except Exception as exc:
        ExportTask.objects.create(
            user=request.user, school_class=current_class, module="全部模块",
            export_format="zip", status="failed", is_full_export=True,
            include_sensitive=True, include_attachments=include_attachments,
            error_message=str(exc),
        )
        OperationLog.objects.create(
            user=request.user, action="full_export", module="exports",
            object_repr="全量导出失败", detail=f"全量导出失败: {exc}",
            ip_address=get_client_ip(request), success=False,
        )
        messages.error(request, f"全量导出失败，未生成不完整的数据包：{exc}")
        return redirect("exports:export_center")

    ExportTask.objects.create(
        user=request.user, school_class=current_class, module="全部模块",
        export_format="zip", status="completed", is_full_export=True,
        include_sensitive=True, include_attachments=include_attachments,
        record_count=sum(record_count for _path, _content, record_count in module_files),
    )

    OperationLog.objects.create(
        user=request.user, action="full_export", module="exports",
        object_repr=f"全量导出 {len(MODULE_EXPORTS)} 个模块",
        detail=f"一键全量导出，共 {len(MODULE_EXPORTS)} 个模块，包含附件：{'是' if include_attachments else '否'}",
        ip_address=get_client_ip(request), success=True,
    )
    return make_full_export_zip(module_files, "class_platform_full_export", current_class=current_class)


@login_required
def template_download(request, template_type):
    """下载标准 Excel 导入模板"""
    from apps.exports.templates_services import (
        students_template, guardians_template, score_import_template,
    )
    try:
        if template_type == "students":
            return students_template()
        elif template_type == "guardians":
            return guardians_template()
        elif template_type == "scores":
            return score_import_template()
        messages.error(request, f"未知的模板类型: {template_type}")
    except Exception as exc:
        messages.error(request, f"模板生成失败: {exc}")
    return redirect("exports:import_data")


@login_required
@require_current_class
def import_data(request):
    """数据导入：上传 → 预览 → 确认 → 正式导入"""
    current_class = SchoolClass.objects.filter(is_current=True).first()
    import_type = request.GET.get("type", "students")

    # 确认导入
    if request.method == "POST" and request.POST.get("confirm") == "1":
        preview_key = request.POST.get("preview_key", "")
        import_type = request.POST.get("import_type", "students")
        preview_data = request.session.get(f"import_preview_{preview_key}")
        if not preview_data:
            messages.error(request, "预览数据已过期，请重新上传。")
            return redirect(f"{request.path}?type={import_type}")

        if import_type == "students":
            from apps.exports.import_services import import_students
            count = import_students(preview_data["valid_rows"], current_class)
            OperationLog.objects.create(
                user=request.user, action="batch_import", module="students",
                object_repr=f"导入学生 {count} 名",
                detail=f"Excel批量导入学生，成功 {count} 名",
                ip_address=get_client_ip(request), success=True,
            )
            messages.success(request, f"成功导入 {count} 名学生！")
        elif import_type == "guardians":
            from apps.exports.import_services import import_guardians
            count = import_guardians(preview_data["valid_rows"])
            OperationLog.objects.create(
                user=request.user, action="batch_import", module="guardians",
                object_repr=f"导入家长信息 {count} 条",
                detail=f"Excel批量导入家长信息，成功 {count} 条",
                ip_address=get_client_ip(request), success=True,
            )
            messages.success(request, f"成功导入 {count} 条家长信息！")

        # 清理 session
        request.session.pop(f"import_preview_{preview_key}", None)
        return redirect("exports:import_data")

    # 上传解析
    preview_data = None
    if request.method == "POST" and request.FILES.get("file"):
        uploaded = request.FILES["file"]
        import_type = request.POST.get("import_type", "students")

        try:
            from apps.exports.import_services import (
                parse_uploaded_file, validate_students, validate_guardians,
            )
            headers, data_rows = parse_uploaded_file(uploaded)
            if not data_rows:
                messages.error(request, "文件中没有数据行。")
            else:
                if import_type == "students":
                    valid_rows, errors = validate_students(data_rows)
                else:
                    valid_rows, errors = validate_guardians(data_rows)

                import uuid
                key = uuid.uuid4().hex[:8]
                request.session[f"import_preview_{key}"] = {
                    "valid_rows": valid_rows,
                    "errors": errors,
                    "headers": headers,
                    "total": len(data_rows),
                }
                preview_data = request.session[f"import_preview_{key}"]
                preview_data["key"] = key
                preview_data["import_type"] = import_type
        except Exception as exc:
            messages.error(request, f"文件解析失败：{exc}")

    return render(request, "exports/import.html", {
        "preview_data": preview_data,
        "import_type": import_type,
        "has_class": bool(current_class),
    })
