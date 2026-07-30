from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """所有模型的基类，包含创建时间和更新时间"""
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True
