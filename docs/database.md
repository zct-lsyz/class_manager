# 数据库设计文档

## 概述

本项目使用 SQLite 作为数据库，所有模型统一继承 `BaseModel`，包含 `created_at` 和 `updated_at` 字段。

## 模型列表

### accounts（账户）
使用 Django 内置 `User` 模型。

### classes（班级与学期）
- **SchoolClass** - 班级信息
- **Semester** - 学年与学期

### audit（操作日志）
- **OperationLog** - 操作日志记录

### students（学生）
- **Student** - 学生基本信息
- **Guardian** - 家长/监护人联系方式

### seating（座位）
- **ClassroomLayout** - 教室布局
- **SeatPlan** - 座位方案
- **SeatAssignment** - 学生座位分配

### duty（值日）
- **DutyGroup** - 值日小组
- **DutyTask** - 值日任务

### attendance（考勤）
- **AttendanceRecord** - 考勤记录

### homework（作业）
- **HomeworkTask** - 作业任务
- **HomeworkRecord** - 学生作业状态

### discipline（纪律）
- **ConfigurableItem** - 可编辑条目（通用）
- **ClassroomDisciplineRecord** - 课堂纪律
- **DormDisciplineRecord** - 宿舍纪律

### dormitory（宿舍）
- **DormBuilding** - 宿舍楼
- **DormRoom** - 宿舍
- **DormBed** - 床位
- **DormAssignment** - 学生住宿分配
- **DormHygieneCheck** - 宿舍卫生检查

### rewards（奖励与积分）
- **RewardRecord** - 奖励与表扬
- **PointRecord** - 积分明细

### scores（成绩）
- **Exam** - 考试
- **Subject** - 科目
- **ExamSubject** - 考试科目
- **Score** - 学生成绩

### comments（评语）
- **StudentComment** - 学生评语

### communications（沟通）
- **StudentConversation** - 学生谈话
- **HomeSchoolContact** - 家校沟通
- **ConcernRecord** - 重点关注

### activities（活动）
- **ClassMeeting** - 主题班会
- **Activity** - 文体活动
- **ClassCultureTask** - 班级文化

### exports（导出）
- **ExportTask** - 导出任务

### backups（备份）
- **BackupRecord** - 备份记录
