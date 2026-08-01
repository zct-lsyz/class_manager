from django.contrib import admin

from apps.accounts.models import EmailVerificationToken, TrustedDevice


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "purpose", "device_name", "is_used", "created_at", "expires_at"]
    list_filter = ["purpose", "is_used"]
    readonly_fields = ["token", "created_at"]


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "device_name", "ip_address", "verified_at", "last_used_at"]
    readonly_fields = ["verified_at", "last_used_at"]
