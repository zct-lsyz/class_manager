# =====================================
# 班级教学管理平台 - Dockerfile
# 基于 Python 3.10 (Ubuntu 22.04)
# =====================================

FROM python:3.10-slim

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN sed -i \
        -e 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' \
        -e 's|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' \
        /etc/apt/sources.list \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=45 -o Acquire::https::Timeout=45 update \
    && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=45 -o Acquire::https::Timeout=45 install -y --no-install-recommends \
    gcc \
    libc6-dev \
    tesseract-ocr \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://mirrors.aliyun.com/pypi/simple --retries 3 --timeout 60 -r requirements.txt

# 复制项目代码
COPY . .

# 创建必要目录
RUN mkdir -p /app/data /app/media /app/backups /app/exports /app/logs /app/staticfiles

# 收集静态文件
RUN python manage.py collectstatic --noinput --clear

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python manage.py check --deploy || exit 1

# 启动 Gunicorn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "300", "--access-logfile", "/app/logs/gunicorn_access.log", "--error-logfile", "/app/logs/gunicorn_error.log"]
