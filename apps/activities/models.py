from django.db import models
from django.utils import timezone

from apps.classes.models import SchoolClass, Semester
from apps.students.models import Student


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class ClassMeeting(BaseModel):
    """主题班会"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="class_meetings", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    topic = models.CharField("主题", max_length=200)
    date = models.DateField("日期")
    goal = models.TextField("目标", blank=True, default="")
    agenda = models.TextField("流程", blank=True, default="")
    host = models.CharField("主持人", max_length=100, blank=True, default="")
    participants = models.ManyToManyField(
        Student, blank=True,
        related_name="class_meetings", verbose_name="参与学生",
    )
    materials = models.FileField(
        "材料附件", upload_to="meetings/", blank=True,
    )
    summary = models.TextField("班会总结", blank=True, default="")
    follow_up = models.TextField("后续事项", blank=True, default="")

    class Meta:
        verbose_name = "主题班会"
        verbose_name_plural = "主题班会"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.topic} ({self.date})"


class Activity(BaseModel):
    """文体活动"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="activities", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    name = models.CharField("活动名称", max_length=200)
    activity_type = models.CharField(
        "活动类型", max_length=50,
        choices=[
            ("sports", "体育"),
            ("arts", "文艺"),
            ("competition", "竞赛"),
            ("outing", "外出"),
            ("other", "其他"),
        ],
        default="other",
    )
    date = models.DateField("活动日期", null=True, blank=True)
    participants = models.ManyToManyField(
        Student, blank=True,
        related_name="activities", verbose_name="报名学生",
    )
    person_in_charge = models.CharField("负责人", max_length=100, blank=True, default="")
    result = models.TextField("活动结果", blank=True, default="")
    award = models.TextField("获奖情况", blank=True, default="")
    summary = models.TextField("活动总结", blank=True, default="")
    photo = models.FileField(
        "照片", upload_to="activities/", blank=True,
    )
    is_deleted = models.BooleanField("已删除", default=False)

    class Meta:
        verbose_name = "文体活动"
        verbose_name_plural = "文体活动"
        ordering = ["-date"]

    def __str__(self):
        return self.name


class ClassCultureTask(BaseModel):
    """班级文化任务"""
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.CASCADE,
        related_name="culture_tasks", verbose_name="班级",
    )
    semester = models.ForeignKey(
        Semester, on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name="学期",
    )
    task_type = models.CharField(
        "任务类型", max_length=50,
        choices=[
            ("blackboard", "黑板报"),
            ("wall", "文化墙"),
            ("logo", "班徽"),
            ("publicity", "宣传任务"),
            ("other", "其他"),
        ],
        default="other",
    )
    title = models.CharField("标题", max_length=200)
    person_in_charge = models.CharField("负责人", max_length=100, blank=True, default="")
    deadline = models.DateField("截止时间", null=True, blank=True)
    is_completed = models.BooleanField("已完成", default=False)
    summary = models.TextField("总结", blank=True, default="")

    class Meta:
        verbose_name = "班级文化"
        verbose_name_plural = "班级文化"
        ordering = ["-deadline"]

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.title}"
