import json
import os
import urllib.parse
import urllib.request

from django.utils import timezone

from apps.mobile_api.models import MobileNotificationDelivery, MobilePushDevice


XIAOMI_PUSH_URL = "https://api.xmpush.xiaomi.com/v2/message/regid"


def send_xiaomi(registration_ids, title, description, payload, notify_id=0):
    secret = os.environ.get("XIAOMI_PUSH_APP_SECRET", "").strip()
    package_name = os.environ.get("XIAOMI_PUSH_PACKAGE_NAME", "com.classmanager.app").strip()
    if not secret:
        raise RuntimeError("服务器未配置 XIAOMI_PUSH_APP_SECRET")
    form = urllib.parse.urlencode({
        "registration_id": ",".join(registration_ids),
        "restricted_package_name": package_name,
        "title": title[:49],
        "description": description[:127],
        "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        "notify_id": notify_id,
        "time_to_live": 864000000,
        "extra.notify_foreground": "1",
        "extra.notify_effect": "1",
    }).encode("utf-8")
    request = urllib.request.Request(
        XIAOMI_PUSH_URL, data=form, method="POST",
        headers={
            "Authorization": f"key={secret}",
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))
    if result.get("result") != "ok" or result.get("code", 0) != 0:
        raise RuntimeError(result.get("description") or result.get("reason") or "小米推送失败")
    return result


def dispatch_due_todos(now=None):
    from apps.todos.models import TodoItem
    now = now or timezone.now()
    if not os.environ.get("XIAOMI_PUSH_APP_SECRET", "").strip():
        return {"sent": 0, "failed": 0, "skipped": "xiaomi_not_configured"}
    todos = TodoItem.objects.filter(
        is_deleted=False, is_completed=False, deadline__isnull=False,
        deadline__lte=now,
    ).select_related("created_by", "student").order_by("deadline")[:500]
    sent = 0
    failed = 0
    for todo in todos:
        devices = MobilePushDevice.objects.filter(
            user=todo.created_by, provider="xiaomi", is_active=True,
        ).exclude(registration_id="")
        for device in devices:
            key = f"todo:{todo.pk}:{int(todo.deadline.timestamp())}:{device.pk}"
            delivery, created = MobileNotificationDelivery.objects.get_or_create(
                notification_key=key,
                defaults={"device": device, "todo": todo},
            )
            if not created and delivery.status == "sent":
                continue
            try:
                result = send_xiaomi(
                    [device.registration_id], "待办提醒", todo.title,
                    {"type": "todo", "id": todo.pk, "deadline": todo.deadline.isoformat()},
                    notify_id=todo.pk % 2147483647,
                )
                delivery.status = "sent"
                delivery.response_data = result
                delivery.error_message = ""
                delivery.sent_at = timezone.now()
                sent += 1
            except Exception as exc:
                delivery.status = "failed"
                delivery.error_message = str(exc)
                failed += 1
            delivery.save(update_fields=["status", "response_data", "error_message", "sent_at"])
    return {"sent": sent, "failed": failed}
