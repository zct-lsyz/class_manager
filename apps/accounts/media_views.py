import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.utils._os import safe_join


@login_required
def protected_media(request, path):
    """仅向已登录管理员提供上传附件。"""
    try:
        file_path = Path(safe_join(settings.MEDIA_ROOT, path))
    except (ValueError, TypeError):
        raise Http404("附件不存在")
    if not file_path.is_file():
        raise Http404("附件不存在")

    content_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        open(file_path, "rb"),
        content_type=content_type or "application/octet-stream",
        as_attachment=request.GET.get("download") == "1",
        filename=file_path.name,
    )

