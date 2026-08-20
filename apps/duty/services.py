"""智能值日服务层：公平轮值算法。"""
import random
from collections import defaultdict

from django.utils import timezone

from apps.duty.models import DutyRosterEntry, DutyRosterTask


def build_history_scores(students, school_class=None):
    """统计每个学生对每项任务的历史值日次数，用于公平轮值。

    返回:
        duty_score: {student_id: {task_id: count}} — 某学生对某任务的历史次数
        total_score: {student_id: count} — 某学生的历史总次数
    """
    student_ids = [s.pk for s in students]
    entries = DutyRosterEntry.objects.filter(
        student_id__in=student_ids,
    ).values_list("student_id", "task_id")
    duty_score = defaultdict(lambda: defaultdict(int))
    total_score = defaultdict(int)
    for student_id, task_id in entries:
        duty_score[student_id][task_id] += 1
        total_score[student_id] += 1
    return duty_score, total_score


def generate_duty_roster(students, tasks_with_counts, day_count, school_class=None,
                         use_groups=False, previous_student_ids=None):
    """基于公平轮值规则生成值日排班。

    核心规则：
      - 上周方案中未值日的同学（previous_student_ids 之外）本周优先安排，
        且每人只安排一次；剩余的槽位由上周值过日的同学补位
        （补位同学也尽量每人一次，槽位仍不够时再轮换）。
      - use_groups=True 时按已分配小组聚合同组相邻，同组尽量同一天值日。

    参数:
        students: 学生对象列表（已过滤未删除、当前班级）
        tasks_with_counts: [(task_id, people_count), ...] 保持配置顺序
        day_count: 排班天数
        school_class: 当前班级（可选，用于历史统计与按小组分配）
        use_groups: 是否按已分配小组分配（同组尽量同一天值日）
        previous_student_ids: 上周/上一个值日方案中出现过的学生 id 集合

    返回:
        {day_index: {task_id: [student, ...]}}
        且保证同一天内每个学生最多被分配一项任务。
    """
    students = list(students)
    previous_ids = previous_student_ids or set()

    # 上周未值日者（优先，每人一次）与上周值日者（补位）
    unseen = [s for s in students if s.pk not in previous_ids]
    seen = [s for s in students if s.pk in previous_ids]

    if use_groups and school_class:
        # 同组相邻：尽量同一天值日（组内保持 unseen 在前）
        unseen = _group_order(unseen, school_class)
        seen = _group_order(seen, school_class)
    else:
        random.shuffle(unseen)
        random.shuffle(seen)

    daily_capacity = sum(count for _, count in tasks_with_counts)
    total_slots = daily_capacity * day_count

    # 分配序列：unseen 每人一次 → seen 每人一次 → 槽位仍不够时轮换补位
    queue = list(unseen) + list(seen)
    if total_slots > len(queue):
        extra_pool = seen if seen else unseen
        for i in range(total_slots - len(queue)):
            queue.append(extra_pool[i % len(extra_pool)])

    duty_score, total_score = build_history_scores(students, school_class)

    result = {}
    for day in range(day_count):
        pool = list(queue[day * daily_capacity:(day + 1) * daily_capacity])
        day_plan = {}
        for task_id, count in tasks_with_counts:
            count = max(0, count)
            # 任务内按历史次数均衡分配
            pool.sort(key=lambda s: (
                duty_score[s.pk][task_id],
                total_score[s.pk],
                s.sort_order,
                s.student_id or "",
            ))
            chosen = pool[:count]
            day_plan[task_id] = chosen
            pool = pool[count:]
            for s in chosen:
                duty_score[s.pk][task_id] += 1
                total_score[s.pk] += 1
        result[day] = day_plan
    return result


def _group_order(students, school_class):
    """把学生按已分配小组重排：同组相邻（保持传入顺序）。"""
    from apps.duty.models import DutyGroup
    ordered = []
    placed = set()
    for g in DutyGroup.objects.filter(school_class=school_class, is_active=True):
        member_ids = set(g.members.values_list("pk", flat=True))
        members = [s for s in students if s.pk in member_ids]
        ordered.extend(members)
        placed.update(s.pk for s in members)
    ordered.extend(s for s in students if s.pk not in placed)
    return ordered


def get_day_dates(date_start, day_count):
    """根据起始日期和天数返回 [date, ...] 列表（跳过周末）。"""
    from django.utils.dateparse import parse_date
    if isinstance(date_start, str):
        date_start = parse_date(date_start)
    dates = []
    current = date_start
    while len(dates) < day_count:
        if current.weekday() < 5:  # 周一至周五
            dates.append(current)
        current = current + timezone.timedelta(days=1)
    return dates


def build_roster_text(roster, class_name=""):
    """将方案渲染为纯文本（用于复制分享到家长群）。"""
    from apps.duty.models import DutyRosterEntry, DutyRosterTask

    tasks = list(
        DutyRosterTask.objects.filter(roster=roster)
        .select_related("task")
        .order_by("sort_order", "pk")
    )
    entries = list(
        DutyRosterEntry.objects.filter(roster=roster)
        .select_related("student", "task")
        .order_by("day_index", "task__sort_order", "sort_order")
    )
    by_day = defaultdict(list)
    for entry in entries:
        by_day[entry.day_index].append(entry)

    lines = [f"【{class_name} {roster.name}】"]
    lines.append(f"{roster.date_start} ~ {roster.date_end}")
    dates = get_day_dates(roster.date_start, roster.day_count)
    for day in range(roster.day_count):
        date_str = dates[day].strftime("%m月%d日") if day < len(dates) else f"第{day + 1}天"
        parts = []
        for rt in tasks:
            names = "、".join(
                e.student.name for e in by_day.get(day, []) if e.task_id == rt.task_id
            )
            if names:
                parts.append(f"{rt.task.name}：{names}")
        if parts:
            lines.append(f"{date_str}：{'；'.join(parts)}")
    return "\n".join(lines)
