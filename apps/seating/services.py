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

# —— 智能排座默认前提（始终生效，先于用户可调的优先级链）——
# 1. 男女间隔：同一列前后连续同性别最多 3 人（第 4 人硬性阻止）；
#    尽量不超过 2 排（连续第 3 人施加软惩罚）。
# 2. 身高相近：相邻同学身高差越小越好，且两项合并加权，
#    避免为了性别间隔而牺牲身高（两个高个子中间夹两排矮个子）。
MAX_COLUMN_SAME_GENDER = 3   # 同一列允许的最大连续同性别排数
GENDER_RUN_WEIGHT = 30       # 列内连续同性别达到第 3 排时的软惩罚权重
HEIGHT_DIFF_CAP = 60         # 单个相邻同学身高差计入惩罚的上限(cm)


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


def _column_gender_run(assigned, row, col, gender):
    """统计 (row, col) 正上方已就座且与 candidate 同性的连续学生数。

    行优先填充时，同一列当前行上方的座位均已就座，因此可以准确判断
    放入 candidate 后该列会形成多长的连续同性别队列。
    """
    run = 0
    r = row - 1
    while r >= 0:
        item = assigned.get((r, col))
        if item is None or item.gender != gender:
            break
        run += 1
        r -= 1
    return run


def _run_at(assigned, layout, row, col):
    """返回包含 (row, col) 的连续同性别长度。"""
    student = assigned.get((row, col))
    if student is None:
        return 0
    gender = student.gender
    run = 1
    r = row - 1
    while r >= 0:
        item = assigned.get((r, col))
        if item is None or item.gender != gender:
            break
        run += 1
        r -= 1
    r = row + 1
    while r < layout.rows:
        item = assigned.get((r, col))
        if item is None or item.gender != gender:
            break
        run += 1
        r += 1
    return run


def _height_span(assigned, layout, row, col):
    """位置上下相邻身高差之和（身高缺失的同学贡献 0）。"""
    total = 0
    student = assigned[(row, col)]
    for r in (row - 1, row + 1):
        if 0 <= r < layout.rows:
            neighbor = assigned.get((r, col))
            if (neighbor is not None and student.height is not None
                    and neighbor.height is not None):
                total += abs(student.height - neighbor.height)
    return total


def _find_run_violation(assigned, layout):
    """返回第一个连续同性别超过上限的位置（串内最后越界者），没有则返回 None。"""
    for col in range(layout.cols):
        run = 0
        prev = None
        for row in range(layout.rows):
            student = assigned.get((row, col))
            if student is None:
                run, prev = 0, None
                continue
            gender = student.gender
            run = run + 1 if gender == prev else 1
            if run > MAX_COLUMN_SAME_GENDER:
                return (row, col)
            prev = gender
    return None


def _find_swap_target(assigned, layout, row, col):
    """寻找可与 (row, col) 交换的异性学生位置，交换后两侧都不产生新违规。

    优先选择身高扰动最小的位置，避免修复本身破坏“身高相近”的默认前提；
    不移动有特殊座位要求的学生。
    """
    student = assigned.get((row, col))
    if student is None or student.seat_requirement.strip():
        return None
    gender = student.gender
    best = None
    best_score = None
    for r2 in range(layout.rows):
        for c2 in range(layout.cols):
            if (r2, c2) == (row, col):
                continue
            other = assigned.get((r2, c2))
            if other is None or other.gender == gender or other.seat_requirement.strip():
                continue
            assigned[(row, col)], assigned[(r2, c2)] = other, assigned[(row, col)]
            if (_run_at(assigned, layout, row, col) <= MAX_COLUMN_SAME_GENDER
                    and _run_at(assigned, layout, r2, c2) <= MAX_COLUMN_SAME_GENDER):
                score = _height_span(assigned, layout, row, col) + _height_span(assigned, layout, r2, c2)
                if best_score is None or score < best_score:
                    best_score = score
                    best = (r2, c2)
            assigned[(row, col)], assigned[(r2, c2)] = assigned[(r2, c2)], assigned[(row, col)]
    return best


def _repair_column_runs(assigned, layout, max_iterations=60):
    """交换修复：保证同一列连续同性别不超过 MAX_COLUMN_SAME_GENDER。

    行优先贪心在性别比例与身高差异较大时，可能在某列堆出超过上限的连续
    同性别（另一种性别在其余列被先消耗完）。此处通过跨列交换拆开违规串，
    每次交换只影响两个格子所在列的局部连续串，且交换后两侧均校验不超过
    上限，因此修复只会减少违规、不会制造新违规。实在找不到合适交换对象
    （性别严重失衡）时才保留原状。
    """
    for _ in range(max_iterations):
        violation = _find_run_violation(assigned, layout)
        if violation is None:
            break
        repaired = False
        # 优先交换串的最后一个（越界者），失败则尝试串内更靠前的位置
        for row in range(violation[0], violation[0] - MAX_COLUMN_SAME_GENDER, -1):
            target = _find_swap_target(assigned, layout, row, violation[1])
            if target is not None:
                assigned[(row, violation[1])], assigned[target] = (
                    assigned[target], assigned[(row, violation[1])],
                )
                repaired = True
                break
        if not repaired:
            break
    return assigned


def _candidate_key(student, row, col, layout, assigned, priorities):
    key = []
    neighbors = _adjacent_students(assigned, row, col, layout)

    # —— 默认前提（先于用户优先级链）：男女间隔 + 相邻身高相近 ——
    # 列内上方连续同性别超过 1 排（即放入后达到第 3 排）开始软惩罚；
    # 与已就座相邻同学的身高差之和也计入惩罚。两项合并为一个加权得分：
    # 性别间隔偏好与身高相近偏好互相制约，避免为岔开男女而把很矮的学生
    # 夹在两位很高的同学之间（此时身高惩罚会超过性别间隔惩罚，允许连坐 3 排）。
    run = _column_gender_run(assigned, row, col, student.gender)
    run_penalty = max(0, run - 1) * GENDER_RUN_WEIGHT
    height_diff = 0.0
    if student.height is not None:
        for item in neighbors:
            if item.height is not None:
                height_diff += min(abs(item.height - student.height), HEIGHT_DIFF_CAP)
    key.append(run_penalty + height_diff)

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
    """按优先级和硬约束生成 {(row, col): student}。

    默认前提（始终生效，先于优先级链）：
    - 男女间隔：同一列前后不允许出现连续 4 个同性别（尽量不超过 2 排）；
    - 身高相近：相邻同学身高差尽量小，且不与性别间隔冲突（不为岔开男女
      而在两位高个子中间夹两排矮个子）。
    """
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
        # 硬约束：特殊学生同样不能造成同一列连续 4 个同性别
        run_safe = [
            position for position in choices
            if _column_gender_run(assigned, position[0], position[1], student.gender)
            < MAX_COLUMN_SAME_GENDER
        ]
        if run_safe:
            choices = run_safe
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
        # 硬约束：同一列不允许出现连续 4 个同性别（实在没有其他选择时才破例）
        run_safe = [
            student for student in candidates
            if _column_gender_run(assigned, row, col, student.gender)
            < MAX_COLUMN_SAME_GENDER
        ]
        if run_safe:
            candidates = run_safe
        if mate:
            same_gender = [student for student in candidates if student.gender == mate.gender]
            if same_gender:
                candidates = same_gender
        student = min(
            candidates,
            key=lambda item: _candidate_key(item, row, col, layout, assigned, priorities),
        )
        assigned[(row, col)] = student
        remaining.remove(student)
    # 兜底：修复贪心在个别列可能堆出的超长连续同性别（跨列交换拆开）
    _repair_column_runs(assigned, layout)
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
