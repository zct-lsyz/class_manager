import datetime

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.accounts.email import send_verification_email
from apps.accounts.models import EmailVerificationToken, TrustedDevice
from apps.audit.models import OperationLog
from apps.mobile_api.auth import api_error, api_ok, get_client_ip, mobile_api, parse_data
from apps.mobile_api.models import MobileApiToken, MobilePushDevice


PENDING_SALT = "mobile-api-device-verification"


def _log(user, action, request, detail, success=True, object_repr=""):
    OperationLog.objects.create(
        user=user, action=action, module="accounts",
        object_repr=object_repr or (user.username if user else ""),
        detail=detail, ip_address=get_client_ip(request), success=success,
    )


def _locked(ip):
    limit = getattr(settings, "LOGIN_ATTEMPT_LIMIT", 5)
    timeout = getattr(settings, "LOGIN_ATTEMPT_TIMEOUT", 300)
    window_start = timezone.now() - datetime.timedelta(seconds=timeout)
    last_success = OperationLog.objects.filter(
        action="login", ip_address=ip, success=True,
    ).order_by("-created_at").first()
    if last_success and last_success.created_at > window_start:
        window_start = last_success.created_at
    failures = OperationLog.objects.filter(
        action="login_failed", ip_address=ip, success=False,
        created_at__gte=window_start,
    ).order_by("-created_at")
    if failures.count() < limit:
        return 0
    latest = failures.first()
    return max(1, int((latest.created_at + datetime.timedelta(seconds=timeout) - timezone.now()).total_seconds()))


def _issue_login(user, device_id, device_name, request):
    MobileApiToken.objects.filter(
        user=user, device_id=device_id, revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    raw = MobileApiToken.issue(user, device_id, device_name)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    _log(user, "login", request, f"Android 客户端登录成功 (IP: {get_client_ip(request)})")
    return api_ok({
        "token": raw,
        "expires_in_days": getattr(settings, "MOBILE_API_TOKEN_DAYS", 90),
        "user": {"id": user.pk, "username": user.username, "email": user.email},
    })


@mobile_api(["POST"], auth=False)
def login(request):
    data = parse_data(request)
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    device_id = str(data.get("device_id", "")).strip()[:128]
    device_name = str(data.get("device_name", "Android"))[:200]
    if not username or not password or not device_id:
        return api_error("用户名、密码和设备标识不能为空。")
    ip = get_client_ip(request)
    remaining = _locked(ip)
    if remaining:
        return api_error(f"登录失败次数过多，请等待 {remaining} 秒后重试。", 429, "login_locked")
    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active:
        _log(None, "login_failed", request, f"Android 登录失败 (IP: {ip})", False, username)
        return api_error("用户名或密码错误。", 401, "invalid_credentials")
    trusted = TrustedDevice.objects.filter(user=user, device_id=device_id).first()
    if trusted:
        TrustedDevice.objects.filter(pk=trusted.pk).update(last_used_at=timezone.now())
        return _issue_login(user, device_id, device_name, request)
    if not user.email:
        return _issue_login(user, device_id, device_name, request)
    code = EmailVerificationToken.create_for_user(
        user, device_id, device_name, "device_verify",
    )
    try:
        send_verification_email(user.email, code, device_name, "device_verify")
    except Exception:
        EmailVerificationToken.objects.filter(user=user, token=code).delete()
        return api_error("验证邮件发送失败，请检查服务器邮件配置。", 503, "email_failed")
    pending = signing.dumps(
        {"user_id": user.pk, "device_id": device_id, "device_name": device_name},
        salt=PENDING_SALT, compress=True,
    )
    return api_ok({
        "verification_required": True,
        "verification_token": pending,
        "email_hint": _mask_email(user.email),
    }, status=202)


def _mask_email(email):
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


@mobile_api(["POST"], auth=False)
def verify(request):
    data = parse_data(request)
    pending = str(data.get("verification_token", ""))
    code = str(data.get("code", "")).strip()
    try:
        payload = signing.loads(pending, salt=PENDING_SALT, max_age=600)
    except signing.BadSignature:
        return api_error("验证请求已过期，请重新登录。", 400, "verification_expired")
    user = User.objects.filter(pk=payload.get("user_id"), is_active=True).first()
    token = EmailVerificationToken.objects.filter(
        user=user, token=code, purpose="device_verify", is_used=False,
        device_id=payload.get("device_id", ""),
    ).order_by("-created_at").first()
    if not token or token.is_expired:
        return api_error("验证码无效或已过期。", 400, "invalid_verification_code")
    token.is_used = True
    token.save(update_fields=["is_used"])
    TrustedDevice.objects.update_or_create(
        user=user, device_id=payload["device_id"],
        defaults={
            "device_name": payload.get("device_name", "Android"),
            "ip_address": get_client_ip(request) or "0.0.0.0",
        },
    )
    return _issue_login(
        user, payload["device_id"], payload.get("device_name", "Android"), request,
    )


@mobile_api(["POST"])
def logout(request):
    request.mobile_token.revoked_at = timezone.now()
    request.mobile_token.save(update_fields=["revoked_at"])
    MobilePushDevice.objects.filter(
        user=request.mobile_user, device_id=request.mobile_token.device_id,
    ).update(is_active=False)
    _log(request.mobile_user, "logout", request, "Android 客户端退出登录")
    return api_ok()


@mobile_api(["GET", "PATCH"])
def profile(request):
    user = request.mobile_user
    if request.method == "PATCH":
        data = parse_data(request)
        username = str(data.get("username", user.username)).strip()
        email = str(data.get("email", user.email)).strip()
        if username != user.username and User.objects.exclude(pk=user.pk).filter(username=username).exists():
            return api_error("该用户名已被使用。", fields={"username": ["该用户名已被使用。"]})
        old = user.username
        user.username = username
        user.email = email
        user.full_clean(exclude=["password", "last_login", "date_joined"])
        user.save(update_fields=["username", "email"])
        _log(user, "username_change", request, f"移动端账户资料变更: {old} -> {username}")
    return api_ok({
        "id": user.pk, "username": user.username, "email": user.email,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    })


@mobile_api(["POST"])
def change_password(request):
    data = parse_data(request)
    old_password = str(data.get("old_password", ""))
    new_password = str(data.get("new_password", ""))
    if not request.mobile_user.check_password(old_password):
        return api_error("原密码错误。", fields={"old_password": ["原密码错误。"]})
    if len(new_password) < 8:
        return api_error("新密码至少需要 8 个字符。", fields={"new_password": ["至少 8 个字符。"]})
    request.mobile_user.set_password(new_password)
    request.mobile_user.save(update_fields=["password"])
    MobileApiToken.objects.filter(
        user=request.mobile_user, revoked_at__isnull=True,
    ).exclude(pk=request.mobile_token.pk).update(revoked_at=timezone.now())
    MobilePushDevice.objects.filter(user=request.mobile_user).exclude(
        device_id=request.mobile_token.device_id,
    ).update(is_active=False)
    _log(request.mobile_user, "password_change", request, "通过 Android 客户端修改密码")
    return api_ok()


@mobile_api(["GET"])
def devices(request):
    rows = TrustedDevice.objects.filter(user=request.mobile_user).order_by("-last_used_at")
    return api_ok([{
        "id": row.pk, "device_id": row.device_id, "device_name": row.device_name,
        "ip_address": row.ip_address, "verified_at": row.verified_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat(),
        "current": row.device_id == request.mobile_token.device_id,
    } for row in rows])


@mobile_api(["DELETE"])
def device_detail(request, pk):
    device = TrustedDevice.objects.filter(pk=pk, user=request.mobile_user).first()
    if not device:
        return api_error("设备不存在。", 404, "not_found")
    device_id = device.device_id
    device.delete()
    MobileApiToken.objects.filter(
        user=request.mobile_user, device_id=device_id, revoked_at__isnull=True,
    ).update(revoked_at=timezone.now())
    MobilePushDevice.objects.filter(
        user=request.mobile_user, device_id=device_id,
    ).update(is_active=False)
    _log(request.mobile_user, "edit", request, f"删除受信任设备: {device.device_name}")
    return api_ok()


@mobile_api(["PUT", "DELETE"])
def push_device(request):
    if request.method == "DELETE":
        MobilePushDevice.objects.filter(
            user=request.mobile_user, device_id=request.mobile_token.device_id,
        ).update(is_active=False)
        return api_ok()
    data = parse_data(request)
    provider = str(data.get("provider", "local"))
    if provider not in dict(MobilePushDevice.PROVIDER_CHOICES):
        return api_error("不支持的推送服务。")
    row, _ = MobilePushDevice.objects.update_or_create(
        user=request.mobile_user,
        device_id=str(data.get("device_id") or request.mobile_token.device_id)[:128],
        provider=provider,
        defaults={
            "registration_id": str(data.get("registration_id", ""))[:500],
            "device_name": str(data.get("device_name", ""))[:200],
            "app_version": str(data.get("app_version", ""))[:50],
            "is_active": True,
        },
    )
    return api_ok({"id": row.pk, "provider": row.provider})


@mobile_api(["POST"])
def delete_account(request):
    data = parse_data(request)
    user = request.mobile_user
    if not user.check_password(str(data.get("password", ""))):
        return api_error("密码错误，无法注销账号。", 403, "invalid_password")
    username = user.username
    from apps.accounts.views import _cascade_delete_user_data
    with transaction.atomic():
        _cascade_delete_user_data(user)
        user.delete()
    return api_ok({"deleted_username": username})
