from django.core.validators import RegexValidator


PHONE_PATTERN = r"^[0-9]{11}$"
STUDENT_ID_PATTERN = r"^[0-9]{19}$"

phone_validator = RegexValidator(
    regex=PHONE_PATTERN,
    message="手机号必须为11位纯数字",
)
student_id_validator = RegexValidator(
    regex=STUDENT_ID_PATTERN,
    message="学号必须为19位纯数字",
)
