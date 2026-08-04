import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class MobileApiToken(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="mobile_api_tokens",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    device_id = models.CharField(max_length=128)
    device_name = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_used_at"]
        indexes = [models.Index(fields=["user", "device_id"], name="mobile_api__user_id_9b4899_idx")]

    @classmethod
    def issue(cls, user, device_id, device_name=""):
        raw = secrets.token_urlsafe(48)
        lifetime = getattr(settings, "MOBILE_API_TOKEN_DAYS", 90)
        cls.objects.create(
            user=user,
            token_hash=cls.hash_token(raw),
            device_id=device_id,
            device_name=device_name,
            expires_at=timezone.now() + timezone.timedelta(days=lifetime),
        )
        return raw

    @staticmethod
    def hash_token(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @property
    def is_valid(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class MobilePushDevice(models.Model):
    PROVIDER_CHOICES = (("xiaomi", "小米推送"), ("local", "本地通知"))

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="mobile_push_devices",
    )
    device_id = models.CharField(max_length=128)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="local")
    registration_id = models.CharField(max_length=500, blank=True, default="")
    device_name = models.CharField(max_length=200, blank=True, default="")
    app_version = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "device_id", "provider"]


class MobileNotificationDelivery(models.Model):
    device = models.ForeignKey(
        MobilePushDevice, on_delete=models.CASCADE,
        related_name="deliveries",
    )
    todo = models.ForeignKey(
        "todos.TodoItem", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="mobile_deliveries",
    )
    notification_key = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=20, default="pending")
    response_data = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
