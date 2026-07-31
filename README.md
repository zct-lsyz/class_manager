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
| 教学管理 | 考试管理（科目配置）、成绩录入（表格批量+Excel导入）、成绩分析（图表+AI文字分析）、培优补差 | ✅ |
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

# 创建完整备份（供 cron 定时调用）
python manage.py create_backup --type auto_daily   # 每日
python manage.py create_backup --type auto_weekly  # 每周
python manage.py create_backup --type manual       # 手动

# 运行测试
python manage.py test tests
```

## 定时备份（服务器 cron 示例）

```cron
30 2 * * * cd /opt/classroom-manager && python manage.py create_backup --type auto_daily
0 3 * * 0  cd /opt/classroom-manager && python manage.py create_backup --type auto_weekly
30 3 1 * * cd /opt/classroom-manager && python manage.py create_backup --type auto_monthly
```

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
scripts/         # 辅助脚本
tests/           # 测试
nginx/           # Nginx 配置
```

## 文档

详细实现方案见 `docs/详细实现方案.md`。
