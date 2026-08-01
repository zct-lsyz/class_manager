"""工作台相关模型：倒计时、每日名言、常用教学网站"""
from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True


class Countdown(BaseModel):
    """倒计时事件"""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="countdowns", verbose_name="创建者",
    )
    name = models.CharField("名称", max_length=100)
    target_date = models.DateField("目标日期")
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        verbose_name = "倒计时"
        verbose_name_plural = "倒计时"
        ordering = ["target_date"]

    def __str__(self):
        return f"{self.name}（{self.target_date}）"

    @property
    def days_remaining(self):
        from django.utils import timezone
        delta = self.target_date - timezone.localdate()
        return delta.days


class DailyQuote(BaseModel):
    """每日励志名言（每天一条，LLM 生成后缓存）"""
    date = models.DateField("日期", unique=True)
    quote = models.TextField("名言内容")
    author = models.CharField("作者/出处", max_length=200, blank=True, default="")

    class Meta:
        verbose_name = "每日名言"
        verbose_name_plural = "每日名言"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.date}：{self.quote[:40]}…"


class TeachingWebsite(BaseModel):
    """常用教学网站"""
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="teaching_websites", verbose_name="创建者",
    )
    name = models.CharField("网站名称", max_length=100)
    url = models.URLField("URL链接", max_length=500)
    sort_order = models.IntegerField("排序", default=0)

    class Meta:
        verbose_name = "教学网站"
        verbose_name_plural = "教学网站"
        ordering = ["sort_order", "name"]
        unique_together = ["created_by", "url"]

    def __str__(self):
        return self.name
