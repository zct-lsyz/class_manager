"""
Django 基础配置
适用于所有环境（开发/生产）的公共配置
"""
import os
from pathlib import Path

# 项目路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# 密钥 - 生产环境必须通过环境变量设置
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-in-production-xxxxxxxxxxxx",
)

# 调试模式 - 默认关闭
DEBUG = False

# 允许的主机
ALLOWED_HOSTS = []

# 应用定义
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    # 第三方应用占位
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.dashboard",
    "apps.classes",
    "apps.students",
    "apps.seating",
    "apps.duty",
    "apps.attendance",
    "apps.homework",
    "apps.discipline",
    "apps.dormitory",
    "apps.rewards",
    "apps.scores",
    "apps.comments",
    "apps.communications",
    "apps.activities",
    "apps.exports",
    "apps.backups",
    "apps.audit",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# 中间件
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# URL 配置
ROOT_URLCONF = "config.urls"

# 模板配置
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.classes.context_processors.current_class_info",
            ],
        },
    },
]

# WSGI 应用
WSGI_APPLICATION = "config.wsgi.application"

# 数据库 - SQLite（默认配置，生产环境应挂载持久化卷）
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "db.sqlite3",
    }
}

# 密码验证
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# 国际化 - 中文
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

# 静态文件
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# 媒体文件
MEDIA_URL = "/protected-media/"
MEDIA_ROOT = BASE_DIR / "media"

# 默认主键类型
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# 登录配置
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# 会话配置
SESSION_COOKIE_AGE = 60 * 30  # 30 分钟
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_SAVE_EVERY_REQUEST = True

# 登录失败限制
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_TIMEOUT = 300  # 5 分钟

# 上传文件限制
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 超过 5 MB 时落盘，避免挤占 2 GB 内存
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024  # 单次原卷 + 小分表上限
AI_EXAM_MAX_FILE_SIZE = int(os.environ.get("AI_EXAM_MAX_FILE_SIZE", 20 * 1024 * 1024))
AI_EXAM_MAX_PAGES = int(os.environ.get("AI_EXAM_MAX_PAGES", 30))
AI_EXAM_MAX_TEXT_CHARS = int(os.environ.get("AI_EXAM_MAX_TEXT_CHARS", 60000))
AI_EXAM_OCR_LANG = os.environ.get("AI_EXAM_OCR_LANG", "chi_sim+eng")

# 邮件发件账号只从环境变量读取，不写入数据库或备份。
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("SMTP_HOST", "")
EMAIL_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("SMTP_USERNAME", "")
EMAIL_HOST_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
EMAIL_USE_SSL = os.environ.get("SMTP_USE_SSL", "false").lower() in {"1", "true", "yes", "on"}
if EMAIL_USE_SSL:
    EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", EMAIL_HOST_USER or "noreply@localhost")

# 文件类型白名单
ALLOWED_UPLOAD_EXTENSIONS = [
    ".jpg", ".jpeg", ".png", ".gif", ".bmp",
    ".xlsx", ".xls", ".csv",
    ".pdf", ".doc", ".docx",
    ".zip", ".rar",
]
