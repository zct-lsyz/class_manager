import logging

from django.contrib.auth.decorators import login_required
import logging

from django.shortcuts import render
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester


logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


@login_required
def index(request):
    """工作台首页"""
    today = timezone.localdate()

    # 当前班级和学期
    current_class = SchoolClass.objects.filter(is_current=True).first()
    current_semester = Semester.objects.filter(is_current=True).first()

    # ----- 统计数据 -----
    # 学生统计（依赖 students 模块，后续完善）
    total_students = 0
    male_count = 0
    female_count = 0
    try:
        from apps.students.models import Student
        qs = Student.objects.all()
        if current_class:
            qs = qs.filter(school_class=current_class)
        total_students = qs.count()
        male_count = qs.filter(gender="male").count()
        female_count = qs.filter(gender="female").count()
    except Exception:
        logger.exception("工作台学生统计加载失败")
        pass

    # 今日缺勤（依赖 attendance 模块）
    today_absent = 0
    try:
        from apps.attendance.models import AttendanceRecord
        today_absent = AttendanceRecord.objects.filter(
            date=today, status__in=["absent", "late"]
        ).count()
    except Exception:
        logger.exception("工作台考勤统计加载失败")
        pass

    # 本周未交作业（依赖 homework 模块）
    week_start = today - timezone.timedelta(days=today.weekday())
    week_unsubmitted = 0
    try:
        from apps.homework.models import HomeworkRecord
        week_unsubmitted = HomeworkRecord.objects.filter(
            submission_date__gte=week_start,
            status__in=["unsubmitted", "late"],
        ).count()
    except Exception:
        logger.exception("工作台作业统计加载失败")
        pass

    # 本周课堂纪律（依赖 discipline 模块）
    week_discipline = 0
    try:
        from apps.discipline.models import ClassroomDisciplineRecord
        week_discipline = ClassroomDisciplineRecord.objects.filter(
            date__gte=week_start
        ).count()
    except Exception:
        logger.exception("工作台课堂纪律统计加载失败")
        pass

    # 本周宿舍纪律（依赖 discipline 模块）
    week_dorm_discipline = 0
    try:
        from apps.discipline.models import DormDisciplineRecord
        week_dorm_discipline = DormDisciplineRecord.objects.filter(
            date__gte=week_start
        ).count()
    except Exception:
        logger.exception("工作台宿舍纪律统计加载失败")
        pass

    # 本月奖励（依赖 rewards 模块）
    this_month_rewards = 0
    try:
        from apps.rewards.models import RewardRecord
        this_month_rewards = RewardRecord.objects.filter(
            date__month=today.month, date__year=today.year
        ).count()
    except Exception:
        logger.exception("工作台奖励统计加载失败")
        pass

    # 最近考试均分（依赖 scores 模块）
    latest_exam = None
    exam_avg_score = None
    try:
        from apps.scores.models import Exam, Score
        if current_semester:
            latest_exam = Exam.objects.filter(
                semester=current_semester, is_deleted=False
            ).order_by("-date").first()
            if latest_exam:
                from django.db.models import Avg
                result = Score.objects.filter(
                    exam=latest_exam, status="normal", is_deleted=False
                ).aggregate(avg=Avg("score"))
                exam_avg_score = result["avg"]
    except Exception:
        logger.exception("工作台成绩统计加载失败")
        pass

    # 待完成评语（依赖 comments 模块）
    pending_comments = 0
    try:
        from apps.comments.models import StudentComment
        if current_semester:
            pending_comments = StudentComment.objects.filter(
                semester=current_semester,
                status__in=["draft", "pending"],
            ).count()
    except Exception:
        logger.exception("工作台评语统计加载失败")
        pass

    # 出勤率
    attendance_rate = None
    try:
        from apps.attendance.models import AttendanceRecord
        this_month_attendance_count = AttendanceRecord.objects.filter(
            date__month=today.month, date__year=today.year
        ).count()
        total_days_this_month = AttendanceRecord.objects.filter(
            date__month=today.month, date__year=today.year
        ).values("date").distinct().count()
        if total_days_this_month > 0 and total_students > 0:
            total_possible = total_students * total_days_this_month
            if total_possible > 0:
                attendance_rate = round(
                    (total_possible - this_month_attendance_count)
                    / total_possible * 100, 1
                )
    except Exception:
        logger.exception("工作台提醒加载失败")
        pass

    # ----- 提醒事项 -----
    reminders = []
    # 自动备份状态检查
    try:
        from apps.backups.models import BackupRecord
        last_backup = BackupRecord.objects.filter(
            backup_type="auto"
        ).order_by("-created_at").first()
        if last_backup and not last_backup.success:
            reminders.append({
                "type": "danger",
                "icon": "bi-exclamation-triangle",
                "text": "最近一次自动备份失败，请检查备份配置。",
            })
    except Exception:
        logger.exception("工作台近期事件加载失败")
        pass

    # 长时间未下载备份提醒
    try:
        from apps.backups.models import BackupRecord
        recent_download = BackupRecord.objects.filter(
            downloaded=True
        ).order_by("-created_at").first()
        if recent_download:
            days_since = (today - recent_download.created_at.date()).days
            if days_since > 14:
                reminders.append({
                    "type": "warning",
                    "icon": "bi-download",
                    "text": f"已 {days_since} 天未下载异地备份，建议定期下载到本地。",
                })
    except Exception:
        logger.exception("工作台趋势统计加载失败")
        pass

    context = {
        "today": today,
        "current_class": current_class,
        "current_semester": current_semester,
        # 统计卡片
        "total_students": total_students,
        "male_count": male_count,
        "female_count": female_count,
        "today_absent": today_absent,
        "attendance_rate": attendance_rate,
        "week_unsubmitted": week_unsubmitted,
        "week_discipline": week_discipline,
        "week_dorm_discipline": week_dorm_discipline,
        "this_month_rewards": this_month_rewards,
        "exam_avg_score": exam_avg_score,
        "latest_exam": latest_exam,
        "pending_comments": pending_comments,
        # 提醒
        "reminders": reminders,
    }
    return render(request, "dashboard/index.html", context)
