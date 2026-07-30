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

# 查看备份列表
docker compose exec web python manage.py list_backups

# 从页面下载备份
# 浏览器访问 /backups/
```

## 回滚

```bash
# 恢复之前的备份
# 通过页面备份管理恢复，或手动操作：

# 1. 停止服务
docker compose down

# 2. 还原数据库文件
cp /path/to/backup/db.sqlite3 /opt/classroom-manager/app/data/

# 3. 重启服务
docker compose up -d
```
