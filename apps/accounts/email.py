"""发送验证邮件"""
from django.conf import settings
from django.core.mail import send_mail


def send_verification_email(email, token, device_name, purpose="device_verify"):
    """发送邮箱验证邮件"""
    if purpose == "register":
        subject = "[班级教学管理平台] 请验证邮箱完成注册"
        action = "完成注册"
    else:
        subject = "[班级教学管理平台] 新设备登录验证"
        action = "完成设备验证"

    text_body = (
        f"您好，\n\n"
        f"您正在一台新设备上{action}。\n"
        f"设备信息：{device_name}\n"
        f"验证码：{token}\n\n"
        f"此验证码 10 分钟内有效。如非本人操作，请忽略此邮件。\n\n"
        f"—— 班级教学管理平台"
    )

    send_mail(
        subject,
        text_body,
        settings.DEFAULT_FROM_EMAIL,
        [email],
        fail_silently=False,
    )
