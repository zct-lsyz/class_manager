import re

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.scores.models import Exam, Score
from apps.seating.models import SeatAssignment, SeatPlan


DEFAULT_PRIORITIES = ["height", "gender", "score", "dormitory", "special"]
PRIORITY_LABELS = {
    "height": "身高/视力",
    "gender": "男女均衡",
    "score": "优差搭配",
    "dormitory": "宿舍号",
    "special": "特殊要求",
}


def attach_student_seat_metadata(students, school_class):
    """为座位人物块补充宿舍、最近考试总分和班级名次。"""
    students = list(students)
    latest_exam = Exam.objects.filter(
        school_class=school_class, is_deleted=False, scores__is_deleted=False,
    ).distinct().order_by("-date", "-pk").first()
    totals = {}
    if latest_exam:
        totals = {
            row["student_id"]: float(row["total"])
            for row in Score.objects.filter(
                exam=latest_exam, is_deleted=False, score__isnull=False,
            ).values("student_id").annotate(total=Sum("score"))
        }
    ordered_totals = sorted(set(totals.values()), reverse=True)
    rank_map = {total: index + 1 for index, total in enumerate(ordered_totals)}
    for student in students:
        student.seat_dormitory = student.display_dormitory or "未住宿"
        student.seat_score = totals.get(student.pk)
        student.seat_rank = rank_map.get(student.seat_score)
    return students


def normalize_priorities(values):
    priorities = []
    for value in values:
        if value in PRIORITY_LABELS and value not in priorities:
            priorities.append(value)
    for value in DEFAULT_PRIORITIES:
        if value not in priorities:
            priorities.append(value)
    return priorities


def _vision_key(student):
    vision = (student.vision or "").lower()
    values = [float(value) for value in re.findall(r"\d+(?:\.\d+)?", vision)]
    is_poor = any(word in vision for word in ("近视", "弱视", "视力差", "看不清"))
    if values and min(values) < 4.8:
        is_poor = True
    return 0 if is_poor else 1


def _special_penalty(student, row, col, layout):
    requirement = (student.seat_requirement or "").lower()
    if not requirement:
        return 0
    penalty = 0
    front_limit = max(1, (layout.rows + 2) // 3)
    if any(word in requirement for word in ("前排", "靠前", "多动", "注意力", "看不清", "视力")):
        penalty += max(0, row - front_limit + 1) * 10
    if "后排" in requirement:
        penalty += max(0, layout.rows - 1 - row) * 10
    if any(word in requirement for word in ("远离窗", "过敏")) and col in (0, layout.cols - 1):
        penalty += 20
    if "靠窗" in requirement and col not in (0, layout.cols - 1):
        penalty += 10
    if "中间" in requirement:
        penalty += int(abs(col - (layout.cols - 1) / 2) * 3)
    return penalty


def _adjacent_students(assigned, row, col, layout):
    positions = []
    aisles = set(layout.aisle_positions or [])
    if col > 0 and col not in aisles:
        positions.append((row, col - 1))
    if col < layout.cols - 1 and col + 1 not in aisles:
        positions.append((row, col + 1))
    if row > 0:
        positions.append((row - 1, col))
    return [assigned[position] for position in positions if position in assigned]


def _desk_mate(assigned, row, col):
    mate_col = col + 1 if col % 2 == 0 else col - 1
    return assigned.get((row, mate_col))


def _candidate_key(student, row, col, layout, assigned, priorities):
    key = []
    neighbors = _adjacent_students(assigned, row, col, layout)
    for priority in priorities:
        if priority == "height":
            key.extend((_vision_key(student), student.height is None, student.height or 999))
        elif priority == "gender":
            male_count = sum(item.gender == "male" for (r, _), item in assigned.items() if r == row)
            female_count = sum(item.gender == "female" for (r, _), item in assigned.items() if r == row)
            male_count += student.gender == "male"
            female_count += student.gender == "female"
            column_same_gender = sum(
                item.gender == student.gender for (r, c), item in assigned.items() if c == col
            )
            key.extend((abs(male_count - female_count), column_same_gender))
        elif priority == "score":
            neighbor_scores = [item.seat_score for item in neighbors if item.seat_score is not None]
            if student.seat_score is None:
                key.extend((1, 0))
            elif neighbor_scores:
                key.extend((0, -sum(abs(student.seat_score - score) for score in neighbor_scores)))
            else:
                key.extend((0, -student.seat_score))
        elif priority == "dormitory":
            dormitory = student.seat_dormitory
            key.append(sum(item.seat_dormitory == dormitory and dormitory != "未住宿" for item in neighbors))
        elif priority == "special":
            key.append(_special_penalty(student, row, col, layout))
    key.append(student.student_id)
    return tuple(key)


def arrange_students(layout, students, priorities):
    """按优先级和硬约束生成 {(row, col): student}。"""
    priorities = normalize_priorities(priorities)
    remaining = list(students)
    positions = [(row, col) for row in range(layout.rows) for col in range(layout.cols)]
    assigned = {}

    special_students = [student for student in remaining if student.seat_requirement.strip()]
    special_students.sort(key=lambda student: (-len(student.seat_requirement), student.student_id))
    for student in special_students:
        if not positions:
            break
        compatible = []
        for position in positions:
            mate = _desk_mate(assigned, *position)
            if not mate or mate.gender == student.gender:
                compatible.append(position)
        choices = compatible or positions
        position = min(
            choices,
            key=lambda seat: (
                _special_penalty(student, seat[0], seat[1], layout),
                seat[0] if _vision_key(student) == 0 else 0,
                seat[0], seat[1],
            ),
        )
        assigned[position] = student
        positions.remove(position)
        remaining.remove(student)

    for row, col in positions:
        if not remaining:
            break
        mate = _desk_mate(assigned, row, col)
        candidates = remaining
        if mate:
            same_gender = [student for student in remaining if student.gender == mate.gender]
            if same_gender:
                candidates = same_gender
        student = min(
            candidates,
            key=lambda item: _candidate_key(item, row, col, layout, assigned, priorities),
        )
        assigned[(row, col)] = student
        remaining.remove(student)
    return assigned


@transaction.atomic
def rotate_plan(plan, rotated_on=None):
    """按两列一组向右轮换：1-2→3-4，末组回到1-2。"""
    layout = plan.layout
    assignments = list(SeatAssignment.objects.filter(seat_plan=plan))
    rotated_on = rotated_on or timezone.localdate()
    if layout and assignments:
        SeatAssignment.objects.filter(seat_plan=plan).update(col=F("col") + layout.cols)
        shift = 2 if layout.cols > 1 else 1
        for assignment in assignments:
            assignment.col = (assignment.col + shift) % layout.cols
        SeatAssignment.objects.bulk_update(assignments, ["col"])
    plan.last_rotated_at = rotated_on
    plan.save(update_fields=["last_rotated_at", "updated_at"])
    return len(assignments)


def rotate_due_plans(today=None, school_class=None):
    today = today or timezone.localdate()
    plans = SeatPlan.objects.filter(
        is_active=True, rotation_interval_months__gt=0, layout__isnull=False,
    ).select_related("layout")
    if school_class:
        plans = plans.filter(school_class=school_class)
    rotated = 0
    for plan in plans:
        if not plan.last_rotated_at:
            plan.last_rotated_at = today
            plan.save(update_fields=["last_rotated_at", "updated_at"])
            continue
        elapsed_months = (
            (today.year - plan.last_rotated_at.year) * 12
            + today.month - plan.last_rotated_at.month
        )
        if elapsed_months >= plan.rotation_interval_months:
            rotate_plan(plan, today)
            rotated += 1
    return rotated
