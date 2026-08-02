"""
数据导入服务
支持：学生花名册、家长联系方式
流程：上传 → 解析 → 预览/校验 → 确认 → 正式导入
"""
import re
from datetime import datetime

from django.db import transaction

from openpyxl import load_workbook

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student, Guardian
from apps.students.validators import PHONE_PATTERN, STUDENT_ID_PATTERN


PHONE_RE = re.compile(PHONE_PATTERN)
STUDENT_ID_RE = re.compile(STUDENT_ID_PATTERN)

# 导入学生信息时，宿舍号中的默认宿舍楼名
DEFAULT_DORM_BUILDING = "一栋"


def _parse_dormitory(dormitory_str):
    """解析宿舍字符串，返回 (楼名, 房间号)。

    支持格式：
      "1号楼 101" / "一栋 101"  → ("1号楼", "101") / ("一栋", "101")
      "一栋101" / "1号楼101"    → ("一栋", "101") / ("1号楼", "101")
      "101"                     → (None, "101")（楼名取默认）
      "A101"                    → (None, "A101")
    """
    s = str(dormitory_str or "").strip()
    if not s:
        return None, None
    # 空格分隔：最后一段为房间号，其余为楼名
    parts = s.split()
    if len(parts) >= 2:
        building = "".join(parts[:-1])
        room = parts[-1]
        return building or None, room
    # 无空格：楼名（含 栋/楼/号 结尾）+ 房间号
    m = re.match(r"^(.+?[栋楼])(\d+)$", s)
    if m:
        return m.group(1), m.group(2)
    # 纯数字房间号
    if s.isdigit():
        return None, s
    # 其它（如 A101）整段视为房间号
    return None, s


def _sync_dormitory_assignment(student, school_class):
    """根据学生 dormitory/bed_number 自动创建宿舍楼/宿舍/床位并分配。

    只在学生填写了宿舍信息时执行；未填则跳过。
    """
    if not student.dormitory:
        return
    building_name, room_number = _parse_dormitory(student.dormitory)
    if not room_number:
        return
    building_name = building_name or DEFAULT_DORM_BUILDING

    from apps.dormitory.models import DormBuilding, DormRoom, DormBed, DormAssignment

    building, _ = DormBuilding.objects.get_or_create(
        school_class=school_class, name=building_name,
        defaults={"sort_order": 0},
    )
    room, _ = DormRoom.objects.get_or_create(
        building=building, room_number=room_number,
        defaults={"bed_count": 8},
    )
    # 确保床位存在（默认 1-床位数，编号 01、02...）
    existing = set(DormBed.objects.filter(room=room).values_list("bed_number", flat=True))
    for i in range(1, room.bed_count + 1):
        bed_no = f"{i:02d}"
        if bed_no not in existing:
            DormBed.objects.create(room=room, bed_number=bed_no)

    bed = None
    bed_number = str(student.bed_number or "").strip()
    if bed_number:
        bed = DormBed.objects.filter(room=room, bed_number=bed_number).first()

    # 取消学生旧分配，创建新分配
    DormAssignment.objects.filter(student=student, is_current=True).update(is_current=False)
    DormAssignment.objects.create(
        student=student, room=room, bed=bed, is_current=True,
        semester=Semester.objects.filter(
            school_class=school_class, is_current=True,
        ).first(),
    )


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


def validate_students(data_rows, school_class=None):
    """
    校验学生数据，返回 (有效行列表, 错误列表)
    错误格式: {row: 行号, field: 字段, value: 原始值, error: 原因}
    学号重复检查仅在当前班级内进行，避免跨班误判（账户隔离）。
    """
    valid_rows = []
    errors = []
    existing_qs = Student.objects.all()
    if school_class:
        existing_qs = existing_qs.filter(school_class=school_class)
    existing_ids = set(existing_qs.values_list("student_id", flat=True))

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


def validate_guardians(data_rows, current_class=None):
    """校验家长联系方式数据"""
    valid_rows = []
    errors = []
    qs = Student.objects.all()
    if current_class:
        qs = qs.filter(school_class=current_class)
    student_map = {s.student_id: s for s in qs}

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


def validate_student_info(data_rows, school_class=None):
    """
    统一校验学生信息（含简化联系人）。
    合并原 validate_students 和 validate_guardians 的字段：
    花名册字段 + 联系人关系/电话 + 备用联系人（选填）。
    学号重复检查仅在当前班级内进行（账户隔离）。
    """
    valid_rows = []
    errors = []
    existing_qs = Student.objects.all()
    if school_class:
        existing_qs = existing_qs.filter(school_class=school_class)
    existing_ids = set(existing_qs.values_list("student_id", flat=True))

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

        # 是否团员
        league_raw = str(row.get("是否团员", "") or "").strip()
        is_league_member = False
        if league_raw in ("是", "1", "true", "True", "yes", "Yes"):
            is_league_member = True
        elif league_raw and league_raw not in ("否", "0", "false", "False", "no", "No"):
            errors.append({"row": idx, "field": "是否团员", "value": league_raw, "error": "只能填写「是」或「否」"})
            continue

        # 是否住校
        boarder_raw = str(row.get("是否住校", "") or "").strip()
        is_boarder = True  # 默认住校
        if boarder_raw in ("否", "0", "false", "False", "no", "No"):
            is_boarder = False
        elif boarder_raw and boarder_raw not in ("是", "1", "true", "True", "yes", "Yes"):
            errors.append({"row": idx, "field": "是否住校", "value": boarder_raw, "error": "只能填写「是」或「否」"})
            continue

        # 宿舍/床位：不住校时允许为空
        dormitory = str(row.get("宿舍", "") or "").strip()
        bed_number = str(row.get("床位", "") or "").strip()

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
            "home_address": str(row.get("家庭住址", "") or "").strip(),
            "is_league_member": is_league_member,
            "is_boarder": is_boarder,
            "dormitory": dormitory,
            "bed_number": bed_number,
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
    """统一导入学生信息（含联系人），并自动为有联系人的学生创建家长记录"""
    created = 0
    for item in valid_rows:
        birth_date = item["birth_date"]
        if isinstance(birth_date, datetime):
            birth_date = birth_date.date()
        student = Student.objects.create(
            school_class=school_class,
            student_id=item["student_id"],
            name=item["name"],
            gender=item["gender"],
            birth_date=birth_date,
            height=item["height"],
            vision=item["vision"],
            seat_requirement=item["seat_requirement"],
            class_position=item["class_position"],
            home_address=item.get("home_address", ""),
            is_league_member=item.get("is_league_member", False),
            is_boarder=item.get("is_boarder", True),
            dormitory=item["dormitory"],
            bed_number=item["bed_number"],
            primary_contact=item["primary_contact"],
            primary_phone=item["primary_phone"],
            secondary_contact=item.get("secondary_contact", ""),
            secondary_phone=item.get("secondary_phone", ""),
            remarks=item["remarks"],
        )
        created += 1
        # 根据导入的联系人关系自动匹配创建家长记录
        _create_guardian_from_import(student, item)
        # 有宿舍/床号时自动创建宿舍楼/宿舍/床位并分配
        if item.get("dormitory") or item.get("bed_number"):
            _sync_dormitory_assignment(student, school_class)
    return created


_FATHER_KEYWORDS = ("父亲", "爸爸", "老爸", "爹")
_MOTHER_KEYWORDS = ("母亲", "妈妈", "老妈", "娘")


def _is_father(relation):
    return relation in _FATHER_KEYWORDS or relation.startswith("爸") or relation.startswith("爹")


def _is_mother(relation):
    return relation in _MOTHER_KEYWORDS or relation.startswith("妈") or relation.startswith("娘")


def _create_guardian_from_import(student, item):
    """根据导入行的联系人关系，自动为学生的家长标签页创建 Guardian 记录。"""
    contacts = []
    if item.get("primary_contact"):
        contacts.append((item["primary_contact"], item.get("primary_phone", "")))
    if item.get("secondary_contact"):
        contacts.append((item["secondary_contact"], item.get("secondary_phone", "")))
    if not contacts:
        return

    father_name = ""
    father_phone = ""
    mother_name = ""
    mother_phone = ""
    other_guardian = ""

    for relation, phone in contacts:
        if _is_father(relation):
            father_name = father_name or relation
            father_phone = father_phone or phone
        elif _is_mother(relation):
            mother_name = mother_name or relation
            mother_phone = mother_phone or phone
        else:
            entry = f"{relation} {phone}".strip() if phone else relation
            other_guardian = f"{other_guardian}；{entry}" if other_guardian else entry

    # 主要联系人：以"联系人关系"（第一个联系人）的关系为准
    primary_relation = contacts[0][0]
    if _is_father(primary_relation):
        primary_key = "father"
    elif _is_mother(primary_relation):
        primary_key = "mother"
    else:
        primary_key = "other"

    Guardian.objects.update_or_create(
        student=student,
        defaults={
            "father_name": father_name,
            "father_phone": father_phone,
            "mother_name": mother_name,
            "mother_phone": mother_phone,
            "other_guardian": other_guardian,
            "primary_contact": primary_key,
            "home_address": item.get("home_address", ""),
        },
    )
