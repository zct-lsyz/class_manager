"""科目主数据统一入口；保留既有 homework_subject 表以避免破坏历史迁移。"""
from apps.homework.models import Subject


__all__ = ["Subject"]
