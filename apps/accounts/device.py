"""设备指纹工具"""
import hashlib


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    return x_forwarded_for.split(",")[0].strip() if x_forwarded_for else request.META.get("REMOTE_ADDR", "0.0.0.0")


def get_device_id(request):
    """User-Agent + IP 前三段的 SHA256 前 32 位"""
    ua = request.META.get("HTTP_USER_AGENT", "")
    ip = get_client_ip(request)
    ip_prefix = ".".join(ip.split(".")[:3])
    raw = f"{ua}|{ip_prefix}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def get_device_name(request):
    """提取人类可读的设备名"""
    ua = request.META.get("HTTP_USER_AGENT", "")
    if "Edg" in ua:
        browser = "Edge"
    elif "Chrome" in ua:
        browser = "Chrome"
    elif "Firefox" in ua:
        browser = "Firefox"
    elif "Safari" in ua:
        browser = "Safari"
    else:
        browser = "浏览器"

    if "Windows" in ua:
        os_name = "Windows"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"
    elif "Mac" in ua:
        os_name = "Mac"
    elif "Linux" in ua:
        os_name = "Linux"
    else:
        os_name = ""

    return f"{browser} on {os_name}" if os_name else browser
