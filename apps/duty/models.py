from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class DutyTask(BaseModel):
    """值日任务（可配置）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="duty_tasks", verbose_name="班级",
    )
    name = models.CharField("任务名称", max_length=100)
    area = models.CharField("值日区域", max_length=100, blank=True, default="")
    default_people_count = models.PositiveSmallIntegerField("默认值日人数", default=1)
    is_active = models.BooleanField("启用", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "值日任务"
        verbose_name_plural = "值日任务"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class DutyGroup(BaseModel):
    """值日小组"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="duty_groups", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    name = models.CharField("组名", max_length=100)
    leader = models.ForeignKey(
        Student, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="led_duty_groups", verbose_name="组长",
    )
    members = models.ManyToManyField(
        Student, blank=True,
        related_name="duty_groups", verbose_name="成员",
    )
    tasks = models.ManyToManyField(
        DutyTask, blank=True,
        related_name="duty_groups", verbose_name="任务",
    )
    week = models.IntegerField("周次", default=1)
    is_active = models.BooleanField("当前小组", default=True)

    class Meta:
        verbose_name = "值日小组"
        verbose_name_plural = "值日小组"

    def __str__(self):
        return f"{self.name} (第{self.week}周)"


class DutyRecord(BaseModel):
    """值日记录"""
    group = models.ForeignKey(
        DutyGroup, on_delete=models.CASCADE,
        related_name="records", verbose_name="小组",
    )
    date = models.DateField("日期")
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="duty_records", verbose_name="学生",
    )
    is_completed = models.BooleanField("已完成", default=False)
    is_absent = models.BooleanField("缺岗", default=False)
    evaluation = models.CharField(
        "评价", max_length=20,
        choices=[
            ("excellent", "优秀"),
            ("good", "良好"),
            ("fair", "一般"),
            ("poor", "差"),
        ],
        blank=True, default="",
    )
    remark = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "值日记录"
        verbose_name_plural = "值日记录"
        unique_together = ["group", "date", "student"]


class DutyMemberTask(BaseModel):
    """值日小组内每位成员的具体任务"""
    group = models.ForeignKey(
        DutyGroup, on_delete=models.CASCADE,
        related_name="member_task_assignments", verbose_name="值日小组",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="duty_task_assignments", verbose_name="学生",
    )
    task = models.ForeignKey(
        DutyTask, on_delete=models.CASCADE,
        related_name="member_assignments", verbose_name="值日任务",
    )

    class Meta:
        verbose_name = "成员值日任务"
        verbose_name_plural = "成员值日任务"
        unique_together = ["group", "student"]


class DutyRoster(BaseModel):
    """智能值日方案（一次完整的自动排班）"""
    STATUS_CHOICES = [
        ("draft", "草稿"),
        ("active", "已生效"),
        ("archived", "已归档"),
    ]
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="duty_rosters", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    name = models.CharField("方案名称", max_length=100)
    date_start = models.DateField("开始日期")
    date_end = models.DateField("结束日期")
    day_count = models.PositiveSmallIntegerField("值日天数")
    status = models.CharField(
        "状态", max_length=20, choices=STATUS_CHOICES, default="draft",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="创建人",
    )
    is_current = models.BooleanField("当前方案", default=True)

    class Meta:
        verbose_name = "值日方案"
        verbose_name_plural = "值日方案"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class DutyRosterTask(BaseModel):
    """方案内每项任务的人数配置"""
    roster = models.ForeignKey(
        DutyRoster, on_delete=models.CASCADE,
        related_name="roster_tasks", verbose_name="值日方案",
    )
    task = models.ForeignKey(
        DutyTask, on_delete=models.CASCADE,
        related_name="roster_configs", verbose_name="值日任务",
    )
    people_count = models.PositiveSmallIntegerField("所需人数", default=1)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "方案任务配置"
        verbose_name_plural = "方案任务配置"
        ordering = ["sort_order", "pk"]
        unique_together = ["roster", "task"]

    def __str__(self):
        return f"{self.roster.name} - {self.task.name}"


class DutyRosterEntry(BaseModel):
    """方案内学生-任务-天分配记录"""
    roster = models.ForeignKey(
        DutyRoster, on_delete=models.CASCADE,
        related_name="entries", verbose_name="值日方案",
    )
    task = models.ForeignKey(
        DutyTask, on_delete=models.CASCADE,
        related_name="roster_entries", verbose_name="值日任务",
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="duty_roster_entries", verbose_name="学生",
    )
    day_index = models.PositiveSmallIntegerField("第几天")
    sort_order = models.IntegerField("组内排序", default=0)
    is_leader = models.BooleanField("当天小组组长", default=False)

    class Meta:
        verbose_name = "方案分配记录"
        verbose_name_plural = "方案分配记录"
        unique_together = ["roster", "task", "student", "day_index"]

    def __str__(self):
        return f"{self.roster.name} D{self.day_index} {self.task.name} - {self.student.name}"


class DutyAbsenceRecord(BaseModel):
    """值日缺勤记录（扣分默认 1 分，可修改，同步积分与预警）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="duty_absence_records", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    roster = models.ForeignKey(
        DutyRoster, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="absence_records", verbose_name="值日方案",
    )
    date = models.DateField("缺勤日期", db_index=True)
    task = models.ForeignKey(
        DutyTask, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="absence_records", verbose_name="当天负责的工作",
    )
    task_name = models.CharField("工作名称", max_length=100, blank=True, default="")
    group_name = models.CharField("小组", max_length=100, blank=True, default="")
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE,
        related_name="duty_absence_records", verbose_name="缺勤学生",
    )
    leader = models.ForeignKey(
        Student, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="led_duty_absences", verbose_name="所在组组长",
    )
    leader_name = models.CharField("组长姓名", max_length=50, blank=True, default="")
    points = models.PositiveSmallIntegerField("扣分", default=1)
    remark = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "值日缺勤记录"
        verbose_name_plural = "值日缺勤记录"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.student.name} {self.date} 缺勤 -{self.points}分"
