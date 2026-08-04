import json
from functools import wraps

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from apps.mobile_api.models import MobileApiToken


def api_error(message, status=400, code="invalid_request", fields=None):
    payload = {"ok": False, "error": {"code": code, "message": message}}
    if fields:
        payload["error"]["fields"] = fields
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def api_ok(data=None, status=200, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return JsonResponse(payload, status=status, json_dumps_params={"ensure_ascii": False})


def parse_data(request):
    content_type = request.content_type or ""
    if content_type.startswith("application/json"):
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValidationError("请求 JSON 格式无效。")
    data = request.POST.dict()
    for key in request.POST:
        values = request.POST.getlist(key)
        if len(values) > 1:
            data[key] = values
    return data


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")


def mobile_api(methods=None, auth=True):
    allowed = set(methods or ["GET"])

    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method == "OPTIONS":
                response = api_ok()
                response["Allow"] = ", ".join(sorted(allowed | {"OPTIONS"}))
                return response
            if request.method not in allowed:
                return api_error("不支持该请求方法。", 405, "method_not_allowed")
            if auth:
                header = request.META.get("HTTP_AUTHORIZATION", "")
                if not header.startswith("Bearer "):
                    return api_error("请先登录。", 401, "authentication_required")
                raw = header[7:].strip()
                token = MobileApiToken.objects.select_related("user").filter(
                    token_hash=MobileApiToken.hash_token(raw), revoked_at__isnull=True,
                    expires_at__gt=timezone.now(), user__is_active=True,
                ).first()
                if not token:
                    return api_error("登录状态已失效，请重新登录。", 401, "invalid_token")
                MobileApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
                request.mobile_token = token
                request.mobile_user = token.user
            try:
                return view(request, *args, **kwargs)
            except ValidationError as exc:
                if hasattr(exc, "message_dict"):
                    return api_error("提交内容校验失败。", 400, "validation_error", exc.message_dict)
                return api_error("；".join(exc.messages), 400, "validation_error")
        return wrapped
    return decorator
