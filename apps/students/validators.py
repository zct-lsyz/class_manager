import re

from django.core.exceptions import ValidationError


PHONE_PATTERN = r"^[0-9]{11}$"
STUDENT_ID_PATTERN = r"^[0-9]{19}$"

PHONE_RE = re.compile(PHONE_PATTERN)
STUDENT_ID_RE = re.compile(STUDENT_ID_PATTERN)


def phone_validator(value):
    if value is None or str(value).strip() == "":
        return
    if not PHONE_RE.match(str(value)):
        raise ValidationError("手机号必须为11位纯数字")


def student_id_validator(value):
    if value is None or str(value).strip() == "":
        return  # 学号允许为空，导入后再补录
    if not STUDENT_ID_RE.match(str(value)):
        raise ValidationError("学号必须为19位纯数字")
