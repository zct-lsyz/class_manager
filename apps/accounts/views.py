import datetime
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login as auth_login,
    logout as auth_logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, redirect
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.forms import (
    LoginForm,
    CustomPasswordChangeForm,
    UsernameChangeForm,
)
from apps.audit.models import OperationLog

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """获取客户端 IP 地址"""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def login_view(request):
    """登录页面"""
    if request.user.is_authenticated:
        return redirect("dashboard:index")

    # 检查登录失败次数限制
    ip = get_client_ip(request)
    lockout_key = f"login_lockout_{ip}"
    attempt_key = f"login_attempts_{ip}"
    limit = getattr(settings, "LOGIN_ATTEMPT_LIMIT", 5)
    timeout = getattr(settings, "LOGIN_ATTEMPT_TIMEOUT", 300)
    window_start = timezone.now() - datetime.timedelta(seconds=timeout)
    last_success = OperationLog.objects.filter(
        action="login", ip_address=ip, success=True,
    ).order_by("-created_at").first()
    if last_success and last_success.created_at > window_start:
        window_start = last_success.created_at
    recent_failures = OperationLog.objects.filter(
        action="login_failed", ip_address=ip, success=False,
        created_at__gte=window_start,
    )
    if recent_failures.count() >= limit:
        latest_failure = recent_failures.order_by("-created_at").first()
        lockout_until = latest_failure.created_at + datetime.timedelta(seconds=timeout)
        remaining = max(1, int((lockout_until - timezone.now()).total_seconds()))
        messages.error(request, f"登录失败次数过多，请等待 {remaining} 秒后重试。")
        return render(request, "accounts/login.html", {"form": LoginForm()})

    if request.session.get(lockout_key):
        lockout_until_value = request.session.get(f"{lockout_key}_until")
        lockout_until = (
            datetime.datetime.fromtimestamp(
                lockout_until_value, tz=datetime.timezone.utc,
            )
            if isinstance(lockout_until_value, (int, float)) else None
        )
        if lockout_until and timezone.now() < lockout_until:
            remaining = int((lockout_until - timezone.now()).total_seconds())
            messages.error(
                request,
                f"登录失败次数过多，请等待 {remaining} 秒后重试。",
            )
            return render(request, "accounts/login.html", {"form": LoginForm()})
        else:
            # 锁定时间已过，清除锁定状态
            del request.session[lockout_key]
            del request.session[f"{lockout_key}_until"]
            request.session[attempt_key] = 0

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            user = authenticate(request, username=username, password=password)
            if user is not None and user.is_active:
                auth_login(request, user)
                # 清除失败次数记录
                if attempt_key in request.session:
                    del request.session[attempt_key]
                # 记录登录日志
                OperationLog.objects.create(
                    user=user,
                    action="login",
                    module="accounts",
                    object_repr=user.username,
                    detail=f"用户登录成功 (IP: {ip})",
                    ip_address=ip,
                    success=True,
                )
                # 记录最后登录 IP
                user.last_login = timezone.now()
                user.save(update_fields=["last_login"])
                messages.success(request, f"欢迎回来，{user.username}！")
                next_url = request.GET.get("next", "")
                if not url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    next_url = "dashboard:index"
                return redirect(next_url)
        # 登录失败
        attempts = recent_failures.count() + 1
        request.session[attempt_key] = attempts
        remaining = max(0, limit - attempts)
        if remaining > 0:
            messages.warning(request, f"用户名或密码错误，还剩 {remaining} 次尝试机会。")
        else:
            # 触发锁定
            request.session[lockout_key] = True
            request.session[f"{lockout_key}_until"] = (
                timezone.now() + datetime.timedelta(seconds=timeout)
            ).timestamp()
            messages.error(request, f"登录失败次数过多，请等待 {timeout // 60} 分钟后重试。")
        # 记录失败日志
        OperationLog.objects.create(
            user=None,
            action="login_failed",
            module="accounts",
            object_repr=request.POST.get("username", ""),
            detail=f"登录失败 (IP: {ip}, 第 {attempts} 次)",
            ip_address=ip,
            success=False,
        )
    else:
        form = LoginForm()

    return render(request, "accounts/login.html", {"form": form})


@login_required
def logout_view(request):
    """退出登录"""
    ip = get_client_ip(request)
    username = request.user.username
    OperationLog.objects.create(
        user=request.user,
        action="logout",
        module="accounts",
        object_repr=username,
        detail=f"用户登出 (IP: {ip})",
        ip_address=ip,
        success=True,
    )
    auth_logout(request)
    messages.info(request, "您已成功退出登录。")
    return redirect("accounts:login")


@login_required
def account_settings(request):
    """账户与安全设置页面"""
    return render(request, "accounts/settings.html", {
        "user": request.user,
    })


@login_required
def password_change(request):
    """修改密码"""
    if request.method == "POST":
        form = CustomPasswordChangeForm(request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            # 更新会话，使用户不会在修改密码后被迫登出
            update_session_auth_hash(request, user)
            OperationLog.objects.create(
                user=request.user,
                action="password_change",
                module="accounts",
                object_repr=request.user.username,
                detail="用户修改密码",
                ip_address=get_client_ip(request),
                success=True,
            )
            messages.success(request, "密码修改成功。")
            return redirect("accounts:settings")
    else:
        form = CustomPasswordChangeForm(request.user)
    return render(request, "accounts/password_change.html", {"form": form})


@login_required
def username_change(request):
    """修改用户名"""
    if request.method == "POST":
        form = UsernameChangeForm(request.POST, instance=request.user)
        if form.is_valid():
            old_username = request.user.username
            form.save()
            OperationLog.objects.create(
                user=request.user,
                action="username_change",
                module="accounts",
                object_repr=f"{old_username} -> {request.user.username}",
                detail=f"用户名变更: {old_username} -> {request.user.username}",
                ip_address=get_client_ip(request),
                success=True,
            )
            messages.success(request, "用户名修改成功。")
            return redirect("accounts:settings")
    else:
        form = UsernameChangeForm(instance=request.user)
    return render(request, "accounts/username_change.html", {"form": form})
