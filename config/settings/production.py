"""
生产环境配置
"""
from .base import *  # noqa: F403, F401

DEBUG = False

# 生产环境必须设置 ALLOWED_HOSTS
ALLOWED_HOSTS = os.environ.get(  # noqa: F405
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1"
).split(",")

# 生产环境数据库路径（通常通过挂载卷设置）
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get(  # noqa: F405
            "DJANGO_DB_PATH", str(BASE_DIR / "data" / "db.sqlite3")  # noqa: F405
        ),
    }
}

# 安全配置：取得证书或位于可信 HTTPS 反向代理后再开启强制 HTTPS
SECURE_SSL_REDIRECT = os.environ.get(  # noqa: F405
    "DJANGO_SECURE_SSL_REDIRECT", "false"
).lower() in {"1", "true", "yes", "on"}
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
SECURE_HSTS_PRELOAD = SECURE_SSL_REDIRECT
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# 静态文件
STATIC_ROOT = "/app/staticfiles"
STATIC_URL = "/static/"

# 媒体文件
MEDIA_ROOT = "/app/media"
MEDIA_URL = "/protected-media/"

# 日志配置
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": os.environ.get("DJANGO_LOG_FILE", "/app/logs/django.log"),  # noqa: F405
            "maxBytes": 10 * 1024 * 1024,  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["file"],
        "level": "WARNING",
    },
}
