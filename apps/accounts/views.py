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
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.accounts.forms import (
    LoginForm,
    CustomPasswordChangeForm,
    UsernameChangeForm,
    RegisterForm,
)
from apps.accounts.models import TrustedDevice, EmailVerificationToken
from apps.accounts.device import get_device_id, get_device_name, get_client_ip as device_get_ip
from apps.classes.utils import get_current_class
from apps.accounts.email import send_verification_email
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
                # 设备信任检查
                dev_id = get_device_id(request)
                if TrustedDevice.objects.filter(user=user, device_id=dev_id).exists():
                    # 已信任设备 → 正常登录
                    TrustedDevice.objects.filter(user=user, device_id=dev_id).update(
                        last_used_at=timezone.now(),
                    )
                elif user.email:
                    # 新设备 → 发送验证邮件
                    token = EmailVerificationToken.create_for_user(
                        user, dev_id, get_device_name(request), "device_verify",
                    )
                    send_verification_email(user.email, token, get_device_name(request), "device_verify")
                    request.session["pending_user_id"] = user.pk
                    request.session["pending_device_id"] = dev_id
                    return redirect("accounts:verify_device")
                else:
                    # 无邮箱 → 直接放行（首次初始化场景；admin 创建的账号可能无邮箱）
                    pass

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
                # 新用户没有班级 → 引导创建
                if not get_current_class(user):
                    messages.info(request, "请先创建您的班级。")
                    return redirect("classes:settings")
                return redirect(next_url)
        # 登录失败
        # 检查是否是注册了但没验证邮箱的用户
        inactive_user = User.objects.filter(
            username=request.POST.get("username", ""), is_active=False,
        ).first()
        if inactive_user and inactive_user.check_password(request.POST.get("password", "")):
            # 重发验证邮件
            dev_id = get_device_id(request)
            token = EmailVerificationToken.create_for_user(
                inactive_user, dev_id, get_device_name(request), "register",
            )
            send_verification_email(inactive_user.email, token, get_device_name(request), "register")
            request.session["pending_user_id"] = inactive_user.pk
            request.session["pending_device_id"] = dev_id
            messages.warning(
                request,
                f"该账号尚未验证邮箱。一封新的验证邮件已发送至 {inactive_user.email}，请查收。",
            )
            return redirect("accounts:verify_device")

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


# ============================================================
# 注册 + 邮箱验证 + 设备信任
# ============================================================

def register(request):
    """注册新账号 → 发送验证邮件"""
    if request.user.is_authenticated:
        return redirect("dashboard:index")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            # 如果存在未激活的同名/同邮箱账号，先删掉
            username = form.cleaned_data["username"]
            email = form.cleaned_data["email"]
            User.objects.filter(username=username, is_active=False).delete()
            User.objects.filter(email=email, is_active=False).delete()

            user = User.objects.create_user(
                username=username,
                email=email,
                password=form.cleaned_data["password1"],
                is_active=False,
            )
            dev_id = get_device_id(request)
            token = EmailVerificationToken.create_for_user(
                user, dev_id, get_device_name(request), "register",
            )
            send_verification_email(user.email, token, get_device_name(request), "register")
            request.session["pending_user_id"] = user.pk
            request.session["pending_device_id"] = dev_id
            messages.info(request, f"验证邮件已发送至 {user.email}，请查收。")
            return redirect("accounts:verify_device")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


def verify_email(request):
    """邮件验证链接入口（?token=xxx）"""
    token_str = request.GET.get("token", "").strip()
    if not token_str:
        messages.error(request, "缺少验证码。")
        return redirect("accounts:login")

    token_obj = EmailVerificationToken.objects.filter(
        token=token_str, is_used=False,
    ).select_related("user").first()

    if not token_obj:
        messages.error(request, "验证链接无效。")
        return redirect("accounts:login")
    if token_obj.is_expired:
        messages.error(request, "验证链接已过期，请重新登录或注册。")
        return redirect("accounts:login")

    user = token_obj.user
    token_obj.is_used = True
    token_obj.save(update_fields=["is_used"])

    # 激活用户（如果是注册验证）
    if token_obj.purpose == "register" and not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])

    # 信任当前设备
    dev_id = token_obj.device_id or get_device_id(request)
    TrustedDevice.objects.get_or_create(
        user=user, device_id=dev_id,
        defaults={
            "device_name": token_obj.device_name or get_device_name(request),
            "ip_address": get_client_ip(request),
        },
    )
    # 更新 last_used_at
    TrustedDevice.objects.filter(user=user, device_id=dev_id).update(
        last_used_at=timezone.now(),
    )

    # 自动登录
    auth_login(request, user)
    # 清除 pending
    request.session.pop("pending_user_id", None)
    request.session.pop("pending_device_id", None)

    OperationLog.objects.create(
        user=user, action="login", module="accounts",
        object_repr=user.username,
        detail=f"邮箱验证登录成功 (IP: {get_client_ip(request)})",
        ip_address=get_client_ip(request), success=True,
    )
    messages.success(request, f"验证成功，欢迎回来，{user.username}！")
    # 新用户没有班级 → 引导创建
    from apps.classes.utils import get_current_class
    if not get_current_class(user):
        messages.info(request, "请先创建您的班级。")
        return redirect("classes:settings")
    return redirect("dashboard:index")


def verify_device(request):
    """设备验证页面——输入验证码"""
    pending_user_id = request.session.get("pending_user_id")
    user = User.objects.filter(pk=pending_user_id).first() if pending_user_id else None

    if user and request.user.is_authenticated and request.user.pk == user.pk:
        # 已验证过（可能点了邮件链接）→ 跳过
        request.session.pop("pending_user_id", None)
        request.session.pop("pending_device_id", None)
        return redirect("dashboard:index")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        dev_id = request.session.get("pending_device_id", get_device_id(request))
        token_obj = EmailVerificationToken.objects.filter(
            token=code, user=user, is_used=False,
        ).first()

        if token_obj and not token_obj.is_expired:
            return _complete_verification(request, token_obj, dev_id)

        messages.error(request, "验证码无效或已过期，请重新登录。")
        return redirect("accounts:login")

    return render(request, "accounts/verify_device.html", {
        "pending_user": user,
    })


def _complete_verification(request, token_obj, dev_id):
    """完成设备验证——信任设备 + 登录"""
    user = token_obj.user
    token_obj.is_used = True
    token_obj.save(update_fields=["is_used"])

    if token_obj.purpose == "register" and not user.is_active:
        user.is_active = True
        user.save(update_fields=["is_active"])

    TrustedDevice.objects.get_or_create(
        user=user, device_id=dev_id,
        defaults={
            "device_name": token_obj.device_name,
            "ip_address": get_client_ip(request),
        },
    )
    TrustedDevice.objects.filter(user=user, device_id=dev_id).update(
        last_used_at=timezone.now(),
    )

    auth_login(request, user)
    request.session.pop("pending_user_id", None)
    request.session.pop("pending_device_id", None)

    OperationLog.objects.create(
        user=user, action="login", module="accounts",
        object_repr=user.username,
        detail=f"设备验证登录 (IP: {get_client_ip(request)})",
        ip_address=get_client_ip(request), success=True,
    )
    messages.success(request, f"设备验证成功，欢迎回来，{user.username}！")
    return redirect("dashboard:index")


# ============================================================
# 信任设备管理
# ============================================================

@login_required
@require_POST
def device_delete(request, pk):
    """删除受信任设备"""
    device = get_object_or_404(TrustedDevice, pk=pk, user=request.user)
    name = device.device_name
    device.delete()
    messages.success(request, f"已删除受信任设备「{name}」，该设备下次登录需重新验证。")
    return redirect("accounts:settings")


# ============================================================
# 注销账号 + 数据级联清理
# ============================================================

@login_required
def delete_account(request):
    """注销账号——需密码确认，不可撤销"""
    if request.method == "POST":
        password = request.POST.get("password", "")
        if not request.user.check_password(password):
            messages.error(request, "密码错误，无法注销账号。")
            return redirect("accounts:settings")

        # 级联清理所有关联数据
        _cascade_delete_user_data(request.user)
        username = request.user.username
        request.user.delete()
        messages.success(request, f"账号「{username}」已注销，所有关联数据已清除。")
        return redirect("accounts:login")

    return render(request, "accounts/delete_account.html")


def _cascade_delete_user_data(user):
    """删除用户创建/拥有的所有数据"""
    # TodoItem —— 唯一 CASCADE 的
    try:
        from apps.todos.models import TodoItem
        TodoItem.objects.filter(created_by=user).delete()
    except Exception:
        pass
    # DutyRoster
    try:
        from apps.duty.models import DutyRoster
        DutyRoster.objects.filter(created_by=user).delete()
    except Exception:
        pass
    # AI 分析
    try:
        from apps.scores.ai_models import AIAnalysisRecord, AIExamAnalysisSource
        AIAnalysisRecord.objects.filter(created_by=user).delete()
        AIExamAnalysisSource.objects.filter(created_by=user).delete()
    except Exception:
        pass
    # 备份：注销即彻底清除所有备份（含系统自动备份）及物理文件，避免遗留数据
    try:
        from pathlib import Path as _Path
        import shutil as _shutil
        from apps.backups.models import BackupRecord, MediaArchiveExport, MediaArchiveImport
        from apps.backups.services import _safe_remove, BACKUP_DIR
        for record in BackupRecord.objects.all():
            if record.file_path:
                _safe_remove(_Path(record.file_path))
        BackupRecord.objects.all().delete()
        for model in (MediaArchiveExport, MediaArchiveImport):
            for row in model.objects.all():
                if row.file_path:
                    _safe_remove(_Path(row.file_path))
            model.objects.all().delete()
        # 备份目录里的残留文件（含失败备份、临时文件）一并清除
        if BACKUP_DIR.exists():
            for child in BACKUP_DIR.iterdir():
                if child.is_dir():
                    _shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
    except Exception:
        pass
    # 操作日志与回收站：单账号系统，注销即清空全部审计记录
    try:
        from apps.audit.models import OperationLog, SoftDeleteRecord
        OperationLog.objects.all().delete()
        SoftDeleteRecord.objects.all().delete()
    except Exception:
        pass
    # 媒体文件（考勤证明/宿舍照片/奖惩照片/评语附件等）：从服务器上物理删除
    try:
        from pathlib import Path as _Path
        from django.conf import settings as _settings
        media_root = _Path(_settings.MEDIA_ROOT)
        if media_root.exists():
            for child in media_root.iterdir():
                if child.is_dir():
                    import shutil as _shutil
                    _shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
    except Exception:
        pass
    # 导出
    try:
        from apps.exports.models import ExportTask
        ExportTask.objects.filter(user=user).delete()
    except Exception:
        pass
    # 验证令牌和信任设备
    EmailVerificationToken.objects.filter(user=user).delete()
    TrustedDevice.objects.filter(user=user).delete()
    # 学生：school_class 外键是 SET_NULL，不会随班级删除级联，
    # 若不显式删除，学生记录会成为孤儿且学号仍占用全库唯一约束，
    # 导致注销后重新导入同一花名册时报「学号已存在」。
    from apps.students.models import Student
    Student.objects.filter(school_class__created_by=user).delete()
    # 班级及所有关联数据（考试/成绩/考勤/纪律… CASCADE 自动级联）
    from apps.classes.models import SchoolClass
    SchoolClass.objects.filter(created_by=user).delete()
