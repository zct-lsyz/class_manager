from django.conf import settings
from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """基类模型"""
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class SchoolClass(BaseModel):
    """班级"""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="school_classes", verbose_name="创建者",
        null=True, blank=True,  # 仅为了兼容历史数据迁移，业务逻辑层保证必填
    )
    name = models.CharField("班级名称", max_length=100)
    grade = models.CharField("年级", max_length=50, blank=True, default="")
    school_name = models.CharField("学校名称", max_length=200, blank=True, default="")
    head_teacher = models.CharField("班主任", max_length=50, blank=True, default="")
    classroom_name = models.CharField("教室名称", max_length=100, blank=True, default="")
    is_current = models.BooleanField("当前班级", default=True)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "班级"
        verbose_name_plural = "班级"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["created_by", "name"], name="unique_class_per_user",
            ),
        ]

    def __str__(self):
        return self.name


class Semester(BaseModel):
    """学年与学期"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="semesters", verbose_name="班级",
    )
    academic_year = models.CharField("学年", max_length=20, help_text="例如：2026-2027")
    semester_type = models.CharField(
        "学期",
        max_length=10,
        choices=[
            ("first", "第一学期"),
            ("second", "第二学期"),
        ],
    )
    is_current = models.BooleanField("当前学期", default=False)
    is_archived = models.BooleanField("已归档", default=False)
    start_date = models.DateField("开始日期", null=True, blank=True)
    end_date = models.DateField("结束日期", null=True, blank=True)

    class Meta:
        verbose_name = "学期"
        verbose_name_plural = "学期"
        ordering = ["-academic_year", "-semester_type"]
        unique_together = ["school_class", "academic_year", "semester_type"]

    def get_display_name(self):
        semester_display = dict(self._meta.get_field("semester_type").choices).get(
            self.semester_type, self.semester_type
        )
        return f"{self.academic_year}学年 {semester_display}"

    def __str__(self):
        return f"{self.school_class.name} - {self.get_display_name()}"


class CommitteeRole(BaseModel):
    """班委职务（可配置）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="committee_roles", verbose_name="班级",
    )
    name = models.CharField("职务名称", max_length=50)
    description = models.TextField("职责说明", blank=True, default="")
    sort_order = models.IntegerField("排序", default=0)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "班委职务"
        verbose_name_plural = "班委职务"
        ordering = ["sort_order"]

    def __str__(self):
        return self.name


class CommitteeMember(BaseModel):
    """班委成员"""
    role = models.ForeignKey(
        CommitteeRole, on_delete=models.CASCADE,
        related_name="members", verbose_name="职务",
    )
    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE,
        related_name="committee_memberships", verbose_name="学生",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="任期学期",
    )
    is_active = models.BooleanField("在职", default=True)
    appointment_date = models.DateField("任命日期", null=True, blank=True)

    class Meta:
        verbose_name = "班委成员"
        verbose_name_plural = "班委成员"
        unique_together = ["role", "student", "semester"]

    def __str__(self):
        return f"{self.student.name} - {self.role.name}"


class StudyGroup(BaseModel):
    """学习小组"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="study_groups", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    name = models.CharField("组名", max_length=50)
    leader = models.ForeignKey(
        "students.Student", on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="led_study_groups", verbose_name="组长",
    )
    members = models.ManyToManyField(
        "students.Student", blank=True,
        related_name="study_groups", verbose_name="成员",
    )
    is_active = models.BooleanField("当前小组", default=True)
    remarks = models.TextField("备注", blank=True, default="")

    class Meta:
        verbose_name = "学习小组"
        verbose_name_plural = "学习小组"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Course(BaseModel):
    """课程（含授课教师），供课程表选择"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="courses", verbose_name="班级",
    )
    name = models.CharField("课程名称", max_length=50)
    teacher = models.CharField("授课教师", max_length=50, blank=True, default="")
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "课程"
        verbose_name_plural = "课程"
        ordering = ["sort_order", "name"]
        unique_together = ["school_class", "name"]

    def __str__(self):
        return f"{self.name}（{self.teacher}）" if self.teacher else self.name


class CourseScheduleEntry(BaseModel):
    """课程表条目"""
    WEEKDAY_CHOICES = [
        (1, "周一"), (2, "周二"), (3, "周三"),
        (4, "周四"), (5, "周五"), (6, "周六"), (7, "周日"),
    ]

    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="course_entries", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="课程",
    )
    weekday = models.IntegerField("星期", choices=WEEKDAY_CHOICES)
    period = models.IntegerField("节次")
    subject = models.CharField("科目", max_length=50, blank=True, default="")
    teacher = models.CharField("任课教师", max_length=50, blank=True, default="")
    remarks = models.CharField("备注", max_length=100, blank=True, default="")

    class Meta:
        verbose_name = "课程表"
        verbose_name_plural = "课程表"
        ordering = ["weekday", "period"]
        unique_together = ["school_class", "semester", "weekday", "period"]

    def __str__(self):
        return f"周{self.weekday} 第{self.period}节 {self.subject or '自习'}"


class CoursePeriod(BaseModel):
    """课程表节次时间设置"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="course_periods", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    period = models.IntegerField("节次")
    start_time = models.TimeField("开始时间", null=True, blank=True)
    end_time = models.TimeField("结束时间", null=True, blank=True)

    class Meta:
        verbose_name = "课程节次"
        verbose_name_plural = "课程节次"
        ordering = ["period"]
        unique_together = ["school_class", "semester", "period"]


class CourseScheduleSnapshot(BaseModel):
    """课程表历史快照（每次保存生成一个版本）"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="course_snapshots", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    label = models.CharField("版本标签", max_length=100, blank=True, default="")
    data = models.JSONField("课表数据", default=dict)

    class Meta:
        verbose_name = "课程表快照"
        verbose_name_plural = "课程表快照"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label}（{self.created_at:%Y-%m-%d %H:%M}）"
