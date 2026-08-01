"""智能值日服务层：公平轮值算法。"""
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


def generate_duty_roster(students, tasks_with_counts, day_count, school_class=None):
    """基于公平轮值规则生成值日排班。

    参数:
        students: 学生对象列表（已过滤未删除、当前班级）
        tasks_with_counts: [(task_id, people_count), ...] 保持配置顺序
        day_count: 排班天数
        school_class: 当前班级（可选，用于历史统计）

    返回:
        {day_index: {task_id: [student, ...]}}
        且保证同一天内每个学生最多被分配一项任务。
    """
    students = list(students)
    students.sort(key=lambda s: (s.sort_order, s.student_id or ""))

    duty_score, total_score = build_history_scores(students, school_class)

    result = {}
    for day in range(day_count):
        day_plan = {}
        assigned_today = set()
        remaining = list(students)

        # 每项任务独立选人；每天每个学生只被分配一次
        for task_id, count in tasks_with_counts:
            count = max(0, count)
            if count == 0:
                day_plan[task_id] = []
                continue
            candidates = [s for s in remaining if s.pk not in assigned_today]

            def sort_key(student):
                return (
                    duty_score[student.pk][task_id],   # 该任务历史次数最少优先
                    total_score[student.pk],           # 总次数最少优先（均衡）
                    student.sort_order,
                    student.student_id or "",
                )

            candidates.sort(key=sort_key)
            chosen = candidates[:count]
            day_plan[task_id] = chosen
            for s in chosen:
                assigned_today.add(s.pk)
                remaining.remove(s)
                duty_score[s.pk][task_id] += 1
                total_score[s.pk] += 1

        result[day] = day_plan
    return result


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
