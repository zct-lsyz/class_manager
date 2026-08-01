"""
邮箱验证令牌 + 受信任设备
"""
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class EmailVerificationToken(models.Model):
    """邮箱验证令牌（注册验证 / 新设备登录验证）"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="verification_tokens",
    )
    token = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=20)  # "register" / "device_verify"
    device_id = models.CharField(max_length=64)
    device_name = models.CharField("设备名称", max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "邮箱验证令牌"
        verbose_name_plural = verbose_name

    @classmethod
    def create_for_user(cls, user, device_id, device_name, purpose="device_verify", ttl_minutes=10):
        """生成一个验证令牌并返回 token 字符串。"""
        token = secrets.token_hex(16)
        cls.objects.create(
            user=user,
            token=token,
            purpose=purpose,
            device_id=device_id,
            device_name=device_name,
            expires_at=timezone.now() + timezone.timedelta(minutes=ttl_minutes),
        )
        return token

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class TrustedDevice(models.Model):
    """受信任设备——验证通过后永久免验，除非手动删除"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="trusted_devices",
    )
    device_id = models.CharField(max_length=64)
    device_name = models.CharField("设备名称", max_length=200)
    ip_address = models.GenericIPAddressField()
    verified_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "受信任设备"
        verbose_name_plural = verbose_name
        unique_together = ["user", "device_id"]
