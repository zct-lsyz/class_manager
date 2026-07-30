# 班级教学管理平台

个人自用班级教学管理平台，面向单个班级约 50 名学生，仅班主任本人使用。

## 技术栈

- **后端框架**: Django 5.2 LTS
- **前端**: Django Template + Bootstrap 5 + HTMX
- **图表**: Chart.js
- **数据库**: SQLite
- **部署**: Docker Compose + Nginx + Gunicorn
- **开发辅助**: WorkBuddy + DeepSeek API

## 开发环境启动

```bash
# 安装依赖
pip install -r requirements.txt

# 数据库迁移
python manage.py migrate

# 创建管理员账号
python manage.py createsuperuser

# 启动开发服务器
python manage.py runserver
```

## Docker 环境启动

```bash
docker compose up -d
```

## 项目结构

```
config/          # Django 配置
apps/            # 业务模块
templates/       # 页面模板
static/          # 静态文件
media/           # 上传文件
data/            # 数据库文件
backups/         # 备份文件
docs/            # 文档
scripts/         # 辅助脚本
tests/           # 测试
nginx/           # Nginx 配置
```

## 文档

详细实现方案见 `docs/` 目录。
