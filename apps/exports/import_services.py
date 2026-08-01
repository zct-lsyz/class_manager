"""
数据导入服务
支持：学生花名册、家长联系方式
流程：上传 → 解析 → 预览/校验 → 确认 → 正式导入
"""
import re
from datetime import datetime

from django.db import transaction

from openpyxl import load_workbook

from apps.classes.models import SchoolClass
from apps.students.models import Student, Guardian
from apps.students.validators import PHONE_PATTERN, STUDENT_ID_PATTERN


PHONE_RE = re.compile(PHONE_PATTERN)
STUDENT_ID_RE = re.compile(STUDENT_ID_PATTERN)


def parse_uploaded_file(uploaded_file):
    """
    解析上传的 Excel 文件，返回 (表头列表, 数据行列表)
    数据行为 dict，键为表头
    """
    wb = load_workbook(uploaded_file, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []

    headers = [str(h).strip() if h else "" for h in rows[0]]
    data_rows = []
    for row in rows[1:]:
        # 跳过全空行
        if all(v is None or str(v).strip() == "" for v in row):
            continue
        data_rows.append({headers[i]: row[i] if i < len(row) else None for i in range(len(headers))})
    return headers, data_rows


def validate_students(data_rows):
    """
    校验学生数据，返回 (有效行列表, 错误列表)
    错误格式: {row: 行号, field: 字段, value: 原始值, error: 原因}
    """
    valid_rows = []
    errors = []
    existing_ids = set(Student.objects.values_list("student_id", flat=True))

    for idx, row in enumerate(data_rows, start=2):  # 从第2行开始（跳过表头）
        student_id = str(row.get("学号", "") or "").strip()
        name = str(row.get("姓名", "") or "").strip()
        gender = str(row.get("性别", "") or "").strip()

        # 必填：姓名
        if not name:
            errors.append({"row": idx, "field": "姓名", "value": name, "error": "姓名不能为空"})
            continue
        # 学号格式（非空时校验；为空则允许导入，后续可补录）
        if student_id and not STUDENT_ID_RE.match(student_id):
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": "学号必须为19位纯数字"})
            continue
        # 学号重复（非空时校验）
        if student_id and student_id in existing_ids:
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": f"学号 {student_id} 已存在"})
            continue
        # 性别
        if gender not in ("男", "女"):
            errors.append({"row": idx, "field": "性别", "value": gender, "error": "性别必须为「男」或「女」"})
            continue
        # 手机号格式（如果有）
        phone = str(row.get("联系电话", "") or "").strip()
        if phone and not PHONE_RE.match(phone):
            errors.append({"row": idx, "field": "联系电话", "value": phone, "error": "手机号必须为11位纯数字"})
            continue
        # 身高
        height = row.get("身高(cm)", "")
        if height not in ("", None):
            try:
                height_value = float(str(height).strip())
                if not height_value.is_integer():
                    raise ValueError
                height = int(height_value)
            except (ValueError, TypeError, OverflowError):
                errors.append({"row": idx, "field": "身高(cm)", "value": height, "error": "身高必须为整数"})
                continue
            if not 50 <= height <= 250:
                errors.append({"row": idx, "field": "身高(cm)", "value": height, "error": "身高必须为50至250之间的整数"})
                continue

        valid_rows.append({
            "row": idx,
            "student_id": student_id or None,
            "name": name,
            "gender": "male" if gender == "男" else "female",
            "birth_date": row.get("出生日期", "") or None,
            "height": height if height not in ("", None) else None,
            "vision": str(row.get("视力", "") or "").strip(),
            "seat_requirement": str(row.get("座位需求", "") or "").strip(),
            "class_position": str(row.get("职务", "") or "").strip(),
            "dormitory": str(row.get("宿舍", "") or "").strip(),
            "bed_number": str(row.get("床位", "") or "").strip(),
            "primary_contact": str(row.get("联系人", "") or "").strip(),
            "primary_phone": str(row.get("联系电话", "") or "").strip(),
            "remarks": str(row.get("备注", "") or "").strip(),
        })
        if student_id:
            existing_ids.add(student_id)

    return valid_rows, errors


@transaction.atomic
def import_students(valid_rows, school_class):
    """正式导入学生数据"""
    created = 0
    for item in valid_rows:
        birth_date = item["birth_date"]
        if isinstance(birth_date, datetime):
            birth_date = birth_date.date()
        Student.objects.create(
            school_class=school_class,
            student_id=item["student_id"],
            name=item["name"],
            gender=item["gender"],
            birth_date=birth_date,
            height=item["height"],
            vision=item["vision"],
            seat_requirement=item["seat_requirement"],
            class_position=item["class_position"],
            dormitory=item["dormitory"],
            bed_number=item["bed_number"],
            primary_contact=item["primary_contact"],
            primary_phone=item["primary_phone"],
            remarks=item["remarks"],
        )
        created += 1
    return created


def validate_guardians(data_rows):
    """校验家长联系方式数据"""
    valid_rows = []
    errors = []
    student_map = {s.student_id: s for s in Student.objects.all()}

    for idx, row in enumerate(data_rows, start=2):
        student_id = str(row.get("学号", "") or "").strip()
        if not student_id:
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": "学号不能为空"})
            continue
        if not STUDENT_ID_RE.match(student_id):
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": "学号必须为19位纯数字"})
            continue
        student = student_map.get(student_id)
        if not student:
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": f"学号 {student_id} 不存在"})
            continue
        if Guardian.objects.filter(student=student).exists():
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": f"学生 {student.name} 已有家长信息"})
            continue
        father_phone = str(row.get("父亲电话", "") or "").strip()
        if father_phone and not PHONE_RE.match(father_phone):
            errors.append({"row": idx, "field": "父亲电话", "value": father_phone, "error": "手机号必须为11位纯数字"})
            continue
        mother_phone = str(row.get("母亲电话", "") or "").strip()
        if mother_phone and not PHONE_RE.match(mother_phone):
            errors.append({"row": idx, "field": "母亲电话", "value": mother_phone, "error": "手机号必须为11位纯数字"})
            continue
        # 用可序列化字段代替 Student ORM 实例，避免 session JSON 序列化崩溃
        valid_rows.append({
            "row": idx,
            "student_id": student.student_id,
            "student_name": student.name,
            "father_name": str(row.get("父亲姓名", "") or "").strip(),
            "father_phone": father_phone,
            "mother_name": str(row.get("母亲姓名", "") or "").strip(),
            "mother_phone": mother_phone,
            "other_guardian": str(row.get("其他监护人", "") or "").strip(),
            "primary_contact": str(row.get("主要联系人", "") or "").strip(),
            "home_address": str(row.get("家庭地址", "") or "").strip(),
            "remarks": str(row.get("备注", "") or "").strip(),
        })
    return valid_rows, errors


@transaction.atomic
def import_guardians(valid_rows):
    """正式导入家长数据"""
    created = 0
    for item in valid_rows:
        student = Student.objects.get(student_id=item["student_id"])
        Guardian.objects.create(
            student=student,
            father_name=item["father_name"],
            father_phone=item["father_phone"],
            mother_name=item["mother_name"],
            mother_phone=item["mother_phone"],
            other_guardian=item["other_guardian"],
            primary_contact=item.get("primary_contact", ""),
            home_address=item["home_address"],
            remarks=item["remarks"],
        )
        created += 1
    return created


def validate_student_info(data_rows):
    """
    统一校验学生信息（含简化联系人）。
    合并原 validate_students 和 validate_guardians 的字段：
    花名册字段 + 联系人关系/电话 + 备用联系人（选填）。
    """
    valid_rows = []
    errors = []
    existing_ids = set(Student.objects.values_list("student_id", flat=True))

    for idx, row in enumerate(data_rows, start=2):
        student_id = str(row.get("学号", "") or "").strip()
        name = str(row.get("姓名", "") or "").strip()
        gender = str(row.get("性别", "") or "").strip()

        # 必填：姓名
        if not name:
            errors.append({"row": idx, "field": "姓名", "value": name, "error": "姓名不能为空"})
            continue
        # 学号格式（非空时校验；为空则允许，后续补录）
        if student_id and not STUDENT_ID_RE.match(student_id):
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": "学号必须为19位纯数字"})
            continue
        # 学号重复（非空时校验）
        if student_id and student_id in existing_ids:
            errors.append({"row": idx, "field": "学号", "value": student_id, "error": f"学号 {student_id} 已存在"})
            continue
        # 性别
        if gender not in ("男", "女"):
            errors.append({"row": idx, "field": "性别", "value": gender, "error": "性别必须为「男」或「女」"})
            continue
        # 手机号格式（如果有）
        phone = str(row.get("联系人电话", "") or "").strip()
        if phone and not PHONE_RE.match(phone):
            errors.append({"row": idx, "field": "联系人电话", "value": phone, "error": "手机号必须为11位纯数字"})
            continue
        backup_phone = str(row.get("备用联系人电话", "") or "").strip()
        if backup_phone and not PHONE_RE.match(backup_phone):
            errors.append({"row": idx, "field": "备用联系人电话", "value": backup_phone, "error": "手机号必须为11位纯数字"})
            continue
        # 身高
        height = row.get("身高(cm)", "")
        if height not in ("", None):
            try:
                height_value = float(str(height).strip())
                if not height_value.is_integer():
                    raise ValueError
                height = int(height_value)
            except (ValueError, TypeError, OverflowError):
                errors.append({"row": idx, "field": "身高(cm)", "value": height, "error": "身高必须为整数"})
                continue
            if not 50 <= height <= 250:
                errors.append({"row": idx, "field": "身高(cm)", "value": height, "error": "身高必须为50至250之间的整数"})
                continue

        valid_rows.append({
            "row": idx,
            "student_id": student_id or None,
            "name": name,
            "gender": "male" if gender == "男" else "female",
            "birth_date": row.get("出生日期", "") or None,
            "height": height if height not in ("", None) else None,
            "vision": str(row.get("视力", "") or "").strip(),
            "seat_requirement": str(row.get("座位需求", "") or "").strip(),
            "class_position": str(row.get("职务", "") or "").strip(),
            "dormitory": str(row.get("宿舍", "") or "").strip(),
            "bed_number": str(row.get("床位", "") or "").strip(),
            "primary_contact": str(row.get("联系人关系", "") or "").strip(),
            "primary_phone": phone,
            "secondary_contact": str(row.get("备用联系人关系", "") or "").strip(),
            "secondary_phone": backup_phone,
            "remarks": str(row.get("备注", "") or "").strip(),
        })
        if student_id:
            existing_ids.add(student_id)

    return valid_rows, errors


@transaction.atomic
def import_student_info(valid_rows, school_class):
    """统一导入学生信息（含联系人）"""
    created = 0
    for item in valid_rows:
        birth_date = item["birth_date"]
        if isinstance(birth_date, datetime):
            birth_date = birth_date.date()
        Student.objects.create(
            school_class=school_class,
            student_id=item["student_id"],
            name=item["name"],
            gender=item["gender"],
            birth_date=birth_date,
            height=item["height"],
            vision=item["vision"],
            seat_requirement=item["seat_requirement"],
            class_position=item["class_position"],
            dormitory=item["dormitory"],
            bed_number=item["bed_number"],
            primary_contact=item["primary_contact"],
            primary_phone=item["primary_phone"],
            secondary_contact=item["secondary_contact"],
            secondary_phone=item["secondary_phone"],
            remarks=item["remarks"],
        )
        created += 1
    return created
