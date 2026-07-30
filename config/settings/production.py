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

# 安全配置
SECURE_HSTS_SECONDS = 31536000  # 1 年
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# 静态文件
STATIC_ROOT = "/app/staticfiles"
STATIC_URL = "/static/"

# 媒体文件
MEDIA_ROOT = "/app/media"
MEDIA_URL = "/media/"

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
            "filename": "/app/logs/django.log",
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
