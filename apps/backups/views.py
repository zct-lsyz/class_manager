import os
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone

from apps.backups.models import BackupRecord
from apps.backups.services import create_backup, verify_backup, restore_backup
from apps.classes.models import SchoolClass
from apps.audit.models import OperationLog


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "")


@login_required
def index(request):
    """备份管理首页"""
    backups = BackupRecord.objects.all().order_by("-created_at")
    paginator = Paginator(backups, 20)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    return render(request, "backups/index.html", {"page_obj": page_obj})


@login_required
def create_backup_view(request):
    """手动创建完整备份"""
    if request.method == "POST":
        current_class = SchoolClass.objects.filter(is_current=True).first()
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
    record = get_object_or_404(BackupRecord, pk=pk)
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
    record = get_object_or_404(BackupRecord, pk=pk)
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
    record = get_object_or_404(BackupRecord, pk=pk)
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
