# 部署文档

## 环境要求

- 阿里云 ECS，2 核 2 GiB，Ubuntu 22.04
- Docker 和 Docker Compose
- Git

## 服务器准备

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER

# 创建项目目录
sudo mkdir -p /opt/classroom-manager
sudo chown $USER:$USER /opt/classroom-manager
```

## 首次部署

```bash
# 克隆代码
cd /opt/classroom-manager
git clone git@github.com:your-username/classroom-manager.git app

# 配置环境变量
cp app/.env.example app/.env
# 编辑 .env，设置 DJANGO_SECRET_KEY 等
# 若仅通过 Tailscale/ZeroTier 私网访问，可保持 DJANGO_SECURE_SSL_REDIRECT=false

# 构建并启动
cd app
docker compose up -d

# 创建管理员账户
docker compose exec web python manage.py createsuperuser

# 创建首次备份
docker compose exec web python manage.py create_backup
```

## 更新流程

```bash
cd /opt/classroom-manager/app

# 创建更新前备份
docker compose exec web python manage.py create_backup

# 拉取最新代码
git pull

# 重新构建
docker compose build

# 执行迁移
docker compose exec web python manage.py migrate

# 重启服务
docker compose up -d

# 检查日志
docker compose logs web --tail=20
```

## 备份管理

```bash
# 手动创建备份
docker compose exec web python manage.py create_backup

# 从页面下载备份
# 浏览器访问 /backups/
```

`backup-scheduler` 容器会按 `.env` 中的 `BACKUP_DAILY_TIME`、`BACKUP_WEEKLY_TIME` 和 `BACKUP_MONTHLY_TIME` 自动备份。完整备份包含 SQLite 一致性快照、上传附件和逐文件校验值。

## AI 原卷与小分表分析

在 `.env` 中配置：

```env
DEEPSEEK_API_KEY=你的密钥
AI_EXAM_MAX_FILE_SIZE=20971520
AI_EXAM_MAX_PAGES=30
AI_EXAM_MAX_TEXT_CHARS=60000
AI_EXAM_OCR_LANG=chi_sim+eng
```

密钥只从容器环境变量读取，不会保存到数据库或备份。试卷 OCR 在服务器本地完成，对外仅发送试题文字和匿名逐题汇总。

## 公网 HTTPS

当前 Nginx 配置默认提供 HTTP，适合只通过 Tailscale/ZeroTier 私网访问。若直接暴露到公网，应在前置代理或云负载均衡上配置有效 TLS 证书，再将 `.env` 中的 `DJANGO_SECURE_SSL_REDIRECT` 改为 `true`，并只开放必要端口。

## 回滚

```bash
# 在“备份管理”页面选择已校验的完整备份并恢复。
# 系统会在恢复前自动创建安全备份，恢复失败时回滚数据库和附件。
```
