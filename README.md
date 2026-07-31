# 班级教学管理平台

个人自用班级教学管理平台，面向单个班级约 50 名学生，仅班主任本人使用。

## 技术栈

- **后端框架**: Django 5.2 LTS
- **前端**: Django Template + Bootstrap 5 + HTMX + Chart.js
- **数据库**: SQLite
- **Excel**: openpyxl（导入/导出 .xlsx）
- **部署**: Docker Compose + Nginx + Gunicorn

## 功能模块

| 分类 | 模块 | 状态 |
|------|------|------|
| 工作台 | 首页统计卡片、快捷入口、待办提醒 | ✅ |
| 账户 | 登录/登出、密码修改、登录失败限制 | ✅ |
| 班级基础 | 学生花名册、学生档案、家长联系方式、班级与学期 | ✅ |
| 日常管理 | 座位表（可视化排座+自动排座）、值日、考勤、作业、课堂纪律、宿舍管理、奖励与积分 | ✅ |
| 教学管理 | 考试管理、成绩录入、成绩分析、原卷+小分表薄弱知识点 AI 分析、培优补差 | ✅ |
| 成长记录 | 学生评语、评语模板、谈话记录、家校沟通、重点关注 | ✅ |
| 班级活动 | 主题班会、文体活动、班级文化 | ✅ |
| 数据中心 | 模块导出（Excel）、全量导出（ZIP）、数据导入（Excel预览确认）、备份管理、操作日志、回收站 | ✅ |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 数据库迁移
python manage.py migrate

# 3. 创建管理员账户
python manage.py createsuperuser

# 4. 初始化默认数据（科目、纪律条目、奖励条目等）
python manage.py init_defaults

# 5. 启动开发服务器
python manage.py runserver
```

## 常用管理命令

```bash
# 初始化系统默认数据
python manage.py init_defaults --class-name "高一(1)班"

# 创建完整备份
python manage.py create_backup --type auto_daily   # 每日
python manage.py create_backup --type auto_weekly  # 每周
python manage.py create_backup --type manual       # 手动

# 运行测试
python manage.py test tests
```

## 定时备份

Docker Compose 中的 `backup-scheduler` 服务会按 `.env` 中的时间自动执行每日、每周和每月备份，无需另配 cron：

```env
BACKUP_DAILY_TIME=02:30
BACKUP_WEEKLY_TIME=03:00
BACKUP_MONTHLY_TIME=03:30
```

完整备份包含一致性 SQLite 快照、全部上传附件、迁移清单和校验值；API Key、密码和环境变量不会写入备份。

## 原卷与小分表分析

- 原卷支持 PDF、扫描 PDF、DOCX、TXT、JPG、PNG；扫描件通过服务器本地 Tesseract OCR 识别。
- 小分表使用页面提供的 XLSX 模板，按学号或姓名匹配当前班级，并校验负分和超满分。
- 仅试题文字和逐题匿名聚合会发送给 DeepSeek；姓名、学号和个人逐题成绩不会发送。
- `DEEPSEEK_API_KEY` 只能配置在服务器 `.env` 中，不写入数据库、导出包或备份。

## 项目结构

```
config/          # Django 配置（base/dev/prod 三层）
apps/            # 18 个业务模块
templates/       # 页面模板（59 个）
static/          # 静态文件
media/           # 上传文件
data/            # SQLite 数据库
backups/         # 备份文件（自动保留策略）
docs/            # 文档
tests/           # 测试
nginx/           # Nginx 配置
```

## 文档

详细实现方案见 `docs/详细实现方案.md`。
