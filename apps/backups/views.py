import os
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from apps.backups.models import BackupRecord, MediaArchiveExport, MediaArchiveImport, StorageAlertRule
from apps.backups.forms import StorageAlertRuleForm
from apps.backups.services import create_backup, verify_backup, restore_backup
from apps.backups.storage_services import (
    check_storage_alerts, clear_archived_modules, create_media_archive,
    import_media_archives,
)
from apps.classes.utils import get_current_class
from apps.classes.models import SchoolClass
from apps.audit.models import OperationLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


@login_required
def index(request):
    """备份管理首页（仅本用户 + 系统自动备份）"""
    backups = BackupRecord.objects.filter(
        Q(user=request.user) | Q(user__isnull=True),
    ).order_by("-created_at")
    paginator = Paginator(backups, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "backups/index.html", {"page_obj": page_obj})


@login_required
def create_backup_view(request):
    """手动创建完整备份"""
    if request.method == "POST":
        current_class = get_current_class(request.user)
        try:
            record = create_backup(
                backup_type="manual",
                user=request.user,
                school_class=current_class,
            )
            OperationLog.objects.create(
                user=request.user, action="backup", module="backups",
                object_repr=f"手动备份 {record.created_at:%Y-%m-%d %H:%M}",
                detail=f"手动创建完整备份，大小 {record.file_size} bytes",
                ip_address=get_client_ip(request), success=True,
            )
            messages.success(request, "备份创建成功！")
        except Exception as exc:
            messages.error(request, f"备份失败: {exc}")
    return redirect("backups:index")


@login_required
def download_backup(request, pk):
    """下载备份文件"""
    record = get_object_or_404(
        BackupRecord.objects.filter(Q(user=request.user) | Q(user__isnull=True)),
        pk=pk,
    )
    if record.status != "completed" or not record.file_path:
        messages.error(request, "该备份不可下载。")
        return redirect("backups:index")

    file_path = Path(record.file_path)
    if not file_path.exists():
        messages.error(request, "备份文件不存在（可能已被清理策略删除）。")
        return redirect("backups:index")

    # 标记已下载
    record.downloaded = True
    record.save(update_fields=["downloaded", "updated_at"])

    response = FileResponse(
        open(file_path, "rb"),
        content_type="application/zip",
    )
    response["Content-Disposition"] = f'attachment; filename="{file_path.name}"'
    return response


@login_required
def delete_backup(request, pk):
    """删除备份记录（含文件）"""
    record = get_object_or_404(
        BackupRecord.objects.filter(Q(user=request.user) | Q(user__isnull=True)),
        pk=pk,
    )
    if request.method == "POST":
        if record.file_path and Path(record.file_path).exists():
            try:
                Path(record.file_path).unlink()
            except OSError:
                pass
        OperationLog.objects.create(
            user=request.user, action="delete", module="backups",
            object_repr=f"备份 {record.created_at:%Y-%m-%d %H:%M}",
            detail="删除备份记录",
            ip_address=get_client_ip(request), success=True,
        )
        record.delete()
        messages.success(request, "备份已删除。")
    return redirect("backups:index")


@login_required
def restore_view(request, pk):
    """恢复备份"""
    record = get_object_or_404(
        BackupRecord.objects.filter(Q(user=request.user) | Q(user__isnull=True)),
        pk=pk,
    )
    if request.method == "POST":
        # 需要输入管理员密码确认（二次确认）
        password = request.POST.get("password", "")
        if not request.user.check_password(password):
            messages.error(request, "密码错误，恢复操作已取消。")
            return redirect("backups:index")

        try:
            safety = restore_backup(record, user=request.user)
            OperationLog.objects.create(
                user=request.user, action="restore", module="backups",
                object_repr=f"恢复备份 {record.created_at:%Y-%m-%d %H:%M}",
                detail=f"恢复备份，恢复前安全备份: {safety.file_path}",
                ip_address=get_client_ip(request), success=True,
            )
            messages.success(request, "备份恢复成功！恢复前已自动创建安全备份。")
        except Exception as exc:
            messages.error(request, f"恢复失败: {exc}")
    return redirect("backups:index")


@login_required
def storage_center(request):
    rules = StorageAlertRule.objects.filter(created_by=request.user)
    archives = MediaArchiveExport.objects.filter(user=request.user)[:30]
    import_history = MediaArchiveImport.objects.filter(user=request.user)[:30]
    if request.method == "POST":
        form = StorageAlertRuleForm(request.POST)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.created_by = request.user
            rule.save()
            messages.success(request, "存储空间提醒规则已保存。")
            return redirect("backups:storage_center")
    else:
        form = StorageAlertRuleForm()
    return render(request, "backups/storage_center.html", {
        "rules": rules, "archives": archives, "import_history": import_history, "form": form,
    })


@login_required
def storage_rule_delete(request, pk):
    rule = get_object_or_404(StorageAlertRule, pk=pk, created_by=request.user)
    if request.method == "POST":
        rule.delete()
        messages.info(request, "提醒规则已删除。")
    return redirect("backups:storage_center")


@login_required
def storage_check_now(request):
    if request.method == "POST":
        try:
            sent = check_storage_alerts(force=True)
            messages.success(request, f"检查完成，本次发送 {sent} 封提醒邮件。")
        except Exception as exc:
            messages.error(request, f"检查或发信失败：{exc}")
    return redirect("backups:storage_center")


@login_required
def media_archive_create(request):
    if request.method == "POST":
        try:
            archive = create_media_archive(request.POST.getlist("modules"), request.user)
            messages.success(request, "媒体数据包已生成，可在下方下载或执行导出并清除。")
        except Exception as exc:
            messages.error(request, f"归档失败：{exc}")
    return redirect("backups:storage_center")


@login_required
def media_archive_download(request, pk):
    archive = get_object_or_404(MediaArchiveExport, pk=pk, user=request.user)
    path = Path(archive.file_path)
    if not path.is_file():
        messages.error(request, "归档文件不存在。")
        return redirect("backups:storage_center")
    return FileResponse(open(path, "rb"), as_attachment=True, filename=path.name)


@login_required
def media_archive_clear(request, pk):
    archive = get_object_or_404(MediaArchiveExport, pk=pk, user=request.user)
    if request.method == "POST":
        confirmation = request.POST.get("confirmation", "").strip()
        if confirmation != "确认清除":
            messages.error(request, "必须完整输入“确认清除”四个字，未执行清理。")
        elif not request.user.check_password(request.POST.get("password", "")):
            messages.error(request, "管理员密码不正确，未执行清理。")
        else:
            clear_archived_modules(archive)
            messages.warning(request, "所选模块的服务器媒体文件已清理，数据库文字记录已保留。")
    return redirect("backups:storage_center")


@login_required
def media_archive_import(request):
    if request.method == "POST":
        files = request.FILES.getlist("archives")
        if not files:
            messages.error(request, "请至少选择一个压缩包。")
        else:
            file_names = [uploaded.name for uploaded in files]
            try:
                packages, records = import_media_archives(files)
                MediaArchiveImport.objects.create(
                    file_names=file_names, package_count=packages, record_count=records,
                    status="completed", user=request.user,
                )
                messages.success(request, f"已导入 {packages} 个数据包，共恢复 {records} 条媒体关联。")
            except Exception as exc:
                MediaArchiveImport.objects.create(
                    file_names=file_names, package_count=len(files), status="failed",
                    error_message=str(exc), user=request.user,
                )
                messages.error(request, f"导入失败：{exc}")
    return redirect("backups:storage_center")
