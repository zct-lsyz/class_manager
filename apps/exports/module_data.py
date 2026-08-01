"""所有可独立导出的模块定义与数据收集。"""
import json
from django.db.models import Avg, Max, Min, Q

from apps.exports.services import fmt


MODULE_EXPORTS = [
    ("students", "学生花名册", "students/students.xlsx"),
    ("guardians", "家长联系方式", "students/guardians.xlsx"),
    ("seating", "座位与历史", "class_management/seating.xlsx"),
    ("duty_tasks", "值日任务", "class_management/duty_tasks.xlsx"),
    ("duty_groups", "值日小组", "class_management/duty_groups.xlsx"),
    ("duty_records", "值日记录", "class_management/duty_records.xlsx"),
    ("attendance", "考勤记录", "daily_management/attendance.xlsx"),
    ("homework_tasks", "作业任务", "daily_management/homework_tasks.xlsx"),
    ("homework_records", "作业完成记录", "daily_management/homework_records.xlsx"),
    ("homework_statuses", "作业状态设置", "settings/homework_statuses.xlsx"),
    ("classroom_items", "课堂纪律条目", "settings/classroom_discipline_items.xlsx"),
    ("discipline", "课堂纪律", "daily_management/classroom_discipline.xlsx"),
    ("dorm_rooms", "宿舍与床位", "daily_management/dorm_rooms.xlsx"),
    ("dorm_assignments", "住宿分配历史", "daily_management/dorm_assignments.xlsx"),
    ("dorm_hygiene_items", "宿舍卫生项目", "settings/dorm_hygiene_items.xlsx"),
    ("dorm_hygiene", "宿舍卫生", "daily_management/dorm_hygiene.xlsx"),
    ("dorm_items", "宿舍纪律条目", "settings/dorm_discipline_items.xlsx"),
    ("dorm_discipline", "宿舍纪律", "daily_management/dorm_discipline.xlsx"),
    ("reward_items", "奖励条目", "settings/reward_items.xlsx"),
    ("rewards", "奖励与表扬", "daily_management/rewards.xlsx"),
    ("points", "奖惩积分", "daily_management/points.xlsx"),
    ("course_schedule", "课程表", "class_management/course_schedule.xlsx"),
    ("committee", "班委名单", "class_management/committee.xlsx"),
    ("study_groups", "学习小组", "class_management/study_groups.xlsx"),
    ("exams", "考试与科目", "teaching/exams.xlsx"),
    ("scores", "成绩", "teaching/scores.xlsx"),
    ("score_analysis", "成绩分析", "teaching/score_analysis.xlsx"),
    ("ai_records", "AI 成绩分析记录", "teaching/ai_analysis_records.xlsx"),
    ("ai_exam_analysis", "原卷小分分析", "teaching/ai_exam_analysis.xlsx"),
    ("ai_settings", "AI 分析设置", "settings/ai_analysis_settings.xlsx"),
    ("support", "培优补差", "teaching/support_plans.xlsx"),
    ("comment_templates", "评语模板", "settings/comment_templates.xlsx"),
    ("comments", "学生评语", "growth/comments.xlsx"),
    ("conversations", "学生谈话", "growth/conversations.xlsx"),
    ("home_school", "家校沟通", "growth/home_school_contacts.xlsx"),
    ("concerns", "重点关注", "growth/concerns.xlsx"),
    ("class_meetings", "主题班会", "activities/class_meetings.xlsx"),
    ("activities", "文体活动", "activities/activities.xlsx"),
    ("culture", "班级文化", "activities/culture_tasks.xlsx"),
    ("operation_logs", "操作日志", "system/operation_logs.xlsx"),
    ("backup_records", "备份记录", "system/backup_records.xlsx"),
]


def _result(rows, headers, sheet_name, filename):
    return rows, headers, sheet_name, filename


def collect_module_data(module, current_class):
    if module == "students":
        from apps.students.models import Student
        queryset = Student.objects.filter(is_deleted=False)
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[
            item.student_id, item.name, item.get_gender_display(), fmt(item.birth_date),
            item.height, item.vision, item.seat_requirement, item.display_class_position,
            item.display_dormitory, item.display_bed_number, item.display_primary_contact,
            item.display_primary_phone, item.remarks,
        ] for item in queryset]
        return _result(rows, ["学号", "姓名", "性别", "出生日期", "身高", "视力", "座位需求", "班级职务", "宿舍", "床位", "联系人", "联系电话", "备注"], "学生花名册", "students.xlsx")

    if module == "guardians":
        from apps.students.models import Guardian
        queryset = Guardian.objects.filter(is_deleted=False).select_related("student")
        if current_class:
            queryset = queryset.filter(student__school_class=current_class)
        rows = [[
            item.student.student_id, item.student.name, item.father_name,
            item.father_phone, item.mother_name, item.mother_phone,
            item.other_guardian, item.primary_contact, item.home_address,
            item.remarks,
        ] for item in queryset]
        return _result(rows, ["学号", "姓名", "父亲姓名", "父亲电话", "母亲姓名", "母亲电话", "其他监护人", "主要联系人", "家庭地址", "备注"], "家长联系方式", "guardians.xlsx")

    if module == "seating":
        from apps.seating.models import SeatAssignment
        queryset = SeatAssignment.objects.select_related("seat_plan", "student")
        if current_class:
            queryset = queryset.filter(seat_plan__school_class=current_class)
        rows = [[
            item.seat_plan.layout.name if item.seat_plan.layout else "", item.seat_plan.version,
            item.seat_plan.is_active, fmt(item.seat_plan.created_at),
            item.student.student_id, item.student.name, item.row, item.col,
        ] for item in queryset]
        return _result(rows, ["方案", "版本", "当前方案", "创建时间", "学号", "姓名", "排", "列"], "座位与历史", "seating.xlsx")

    if module in {"duty_tasks", "duty_groups", "duty_records"}:
        from apps.duty.models import DutyTask, DutyGroup, DutyRecord
        if module == "duty_tasks":
            queryset = DutyTask.objects.all()
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.name, item.area, item.default_people_count, item.is_active, item.sort_order] for item in queryset]
            return _result(rows, ["任务", "区域", "默认人数", "启用", "排序"], "值日任务", "duty_tasks.xlsx")
        if module == "duty_groups":
            queryset = DutyGroup.objects.select_related("leader").prefetch_related("members", "tasks")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[
                item.name, item.week, item.leader.name if item.leader else "",
                "、".join(member.name for member in item.members.all()),
                "、".join(task.name for task in item.tasks.all()), item.is_active,
            ] for item in queryset]
            return _result(rows, ["组名", "周次", "组长", "成员", "任务", "当前"], "值日小组", "duty_groups.xlsx")
        queryset = DutyRecord.objects.select_related("group", "student")
        if current_class:
            queryset = queryset.filter(group__school_class=current_class)
        rows = [[fmt(item.date), item.group.name, item.student.student_id, item.student.name, item.is_completed, item.is_absent, item.get_evaluation_display(), item.remark] for item in queryset]
        return _result(rows, ["日期", "小组", "学号", "姓名", "完成", "缺岗", "评价", "备注"], "值日记录", "duty_records.xlsx")

    if module == "attendance":
        from apps.attendance.models import AttendanceRecord
        queryset = AttendanceRecord.objects.select_related("student", "semester")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[fmt(item.date), item.student.student_id, item.student.name, item.get_period_display(), item.get_status_display(), item.reason, item.leave_proof.name] for item in queryset]
        return _result(rows, ["日期", "学号", "姓名", "时段", "状态", "原因", "请假证明"], "考勤记录", "attendance.xlsx")

    if module in {"homework_tasks", "homework_records", "homework_statuses"}:
        from apps.homework.models import HomeworkTask, HomeworkRecord, HomeworkStatus
        if module == "homework_tasks":
            queryset = HomeworkTask.objects.select_related("subject", "semester")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.title, item.subject.name if item.subject else "", item.content, fmt(item.assigned_date), fmt(item.due_date), item.person_in_charge, item.remarks] for item in queryset]
            return _result(rows, ["作业", "科目", "内容", "布置日期", "截止日期", "负责人", "备注"], "作业任务", "homework_tasks.xlsx")
        if module == "homework_records":
            queryset = HomeworkRecord.objects.select_related("task", "student")
            if current_class:
                queryset = queryset.filter(task__school_class=current_class)
            rows = [[item.task.title, item.student.student_id, item.student.name, item.status_display, fmt(item.submission_date), fmt(item.correction_deadline), item.correction_result, item.remark] for item in queryset]
            return _result(rows, ["作业", "学号", "姓名", "状态", "提交日期", "补交期限", "补交结果", "备注"], "作业完成记录", "homework_records.xlsx")
        queryset = HomeworkStatus.objects.all()
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.name, item.is_positive, item.is_active, item.sort_order] for item in queryset]
        return _result(rows, ["状态", "积极状态", "启用", "排序"], "作业状态设置", "homework_statuses.xlsx")

    if module in {"classroom_items", "dorm_items", "discipline", "dorm_discipline"}:
        from apps.discipline.models import ConfigurableItem, ClassroomDisciplineRecord, DormDisciplineRecord
        if module in {"classroom_items", "dorm_items"}:
            item_module = "classroom_discipline" if module == "classroom_items" else "dorm_discipline"
            queryset = ConfigurableItem.objects.filter(module=item_module)
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.name, item.category, item.get_default_severity_display(), item.default_points, item.needs_follow_up, item.is_active, item.sort_order, item.description] for item in queryset]
            return _result(rows, ["名称", "分类", "严重程度", "默认分值", "需跟进", "启用", "排序", "说明"], "纪律条目", f"{module}.xlsx")
        model = ClassroomDisciplineRecord if module == "discipline" else DormDisciplineRecord
        queryset = model.objects.filter(is_deleted=False).select_related("student", "item")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[fmt(item.date), item.student.student_id, item.student.name, item.item.name if item.item else item.custom_content, item.get_severity_display(), item.points_deducted, item.description, item.action_taken, item.needs_follow_up, fmt(item.follow_up_date), item.follow_up_result, item.remarks] for item in queryset]
        return _result(rows, ["日期", "学号", "姓名", "条目", "严重程度", "扣分", "经过", "处理", "需跟进", "跟进日期", "结果", "备注"], "纪律记录", f"{module}.xlsx")

    if module in {"dorm_rooms", "dorm_assignments", "dorm_hygiene_items", "dorm_hygiene"}:
        from apps.dormitory.models import DormRoom, DormBed, DormAssignment, DormHygieneItem, DormHygieneCheck
        if module == "dorm_rooms":
            rooms = DormRoom.objects.select_related("building", "monitor")
            if current_class:
                rooms = rooms.filter(building__school_class=current_class)
            rows = []
            for room in rooms:
                beds = "、".join(DormBed.objects.filter(room=room).values_list("bed_number", flat=True))
                rows.append([room.building.name, room.room_number, room.floor, room.get_room_type_display(), room.bed_count, beds, room.monitor.name if room.monitor else "", room.is_active, room.remarks])
            return _result(rows, ["宿舍楼", "房间", "楼层", "类型", "床位数", "床位编号", "宿舍长", "启用", "备注"], "宿舍与床位", "dorm_rooms.xlsx")
        if module == "dorm_assignments":
            queryset = DormAssignment.objects.select_related("student", "room__building", "bed", "semester")
            if current_class:
                queryset = queryset.filter(room__building__school_class=current_class)
            rows = [[item.student.student_id, item.student.name, item.room.building.name, item.room.room_number, item.bed.bed_number if item.bed else "", item.semester.get_display_name() if item.semester else "", item.is_current, fmt(item.assigned_date), fmt(item.end_date)] for item in queryset]
            return _result(rows, ["学号", "姓名", "宿舍楼", "房间", "床位", "学期", "当前", "分配日期", "结束日期"], "住宿分配历史", "dorm_assignments.xlsx")
        if module == "dorm_hygiene_items":
            queryset = DormHygieneItem.objects.all()
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.name, item.full_score, item.default_deduction, item.is_active, item.sort_order] for item in queryset]
            return _result(rows, ["项目", "满分", "默认扣分", "启用", "排序"], "宿舍卫生项目", "dorm_hygiene_items.xlsx")
        queryset = DormHygieneCheck.objects.filter(is_deleted=False).select_related("room__building", "semester").prefetch_related("item_scores__item")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = []
        for check in queryset:
            detail = "；".join(f"{score.item.name if score.item else '已停用项目'}:{score.score}" for score in check.item_scores.all())
            rows.append([fmt(check.date), check.room.building.name, check.room.room_number, check.inspector, check.total_score, check.get_grade_display(), detail, check.rectification, fmt(check.rectification_deadline), check.rectification_result, check.photo.name, check.remarks])
        return _result(rows, ["日期", "宿舍楼", "房间", "检查人", "总分", "等级", "项目得分", "整改要求", "期限", "结果", "照片", "备注"], "宿舍卫生", "dorm_hygiene.xlsx")

    if module in {"reward_items", "rewards", "points"}:
        from apps.rewards.models import RewardItem, RewardRecord, PointRecord
        if module == "reward_items":
            queryset = RewardItem.objects.all()
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.name, item.category, item.default_points, item.is_active, item.sort_order] for item in queryset]
            return _result(rows, ["名称", "分类", "默认加分", "启用", "排序"], "奖励条目", "reward_items.xlsx")
        if module == "rewards":
            queryset = RewardRecord.objects.filter(is_deleted=False).select_related("student", "item")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[fmt(item.date), item.student.student_id, item.student.name, item.item.name if item.item else item.custom_name, item.get_level_display(), item.points, item.description, item.certificate_photo.name] for item in queryset]
            return _result(rows, ["日期", "学号", "姓名", "奖励", "等级", "加分", "说明", "奖状照片"], "奖励与表扬", "rewards.xlsx")
        queryset = PointRecord.objects.filter(is_deleted=False).select_related("student")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[fmt(item.date), item.student.student_id, item.student.name, item.points, item.reason, item.get_source_type_display(), item.source_id, item.manual_reason] for item in queryset]
        return _result(rows, ["日期", "学号", "姓名", "分值", "原因", "来源", "来源ID", "调整说明"], "奖惩积分", "points.xlsx")

    if module in {"course_schedule", "committee", "study_groups"}:
        from apps.classes.models import CourseScheduleEntry, CommitteeMember, StudyGroup
        if module == "course_schedule":
            queryset = CourseScheduleEntry.objects.select_related("semester")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.semester.get_display_name() if item.semester else "", item.get_weekday_display(), item.period, item.subject, item.teacher, item.location, item.remarks] for item in queryset]
            return _result(rows, ["学期", "星期", "节次", "科目", "教师", "地点", "备注"], "课程表", "course_schedule.xlsx")
        if module == "committee":
            queryset = CommitteeMember.objects.select_related("role", "student", "semester")
            if current_class:
                queryset = queryset.filter(role__school_class=current_class)
            rows = [[item.role.name, item.student.student_id, item.student.name, item.semester.get_display_name() if item.semester else "", item.is_active, fmt(item.appointment_date)] for item in queryset]
            return _result(rows, ["职务", "学号", "姓名", "学期", "在职", "任命日期"], "班委名单", "committee.xlsx")
        queryset = StudyGroup.objects.select_related("leader", "semester").prefetch_related("members")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.name, item.semester.get_display_name() if item.semester else "", item.leader.name if item.leader else "", "、".join(member.name for member in item.members.all()), item.is_active, item.remarks] for item in queryset]
        return _result(rows, ["组名", "学期", "组长", "成员", "当前", "备注"], "学习小组", "study_groups.xlsx")

    if module in {"exams", "scores", "score_analysis", "support"}:
        from apps.scores.models import Exam, ExamSubject, Score, SupportPlan
        if module == "exams":
            queryset = ExamSubject.objects.filter(exam__is_deleted=False).select_related("exam", "subject")
            if current_class:
                queryset = queryset.filter(exam__school_class=current_class)
            rows = [[item.exam.name, item.exam.get_exam_type_display(), fmt(item.exam.date), item.subject.name, item.full_score, item.exam.is_published, item.exam.remarks] for item in queryset]
            return _result(rows, ["考试", "类型", "日期", "科目", "满分", "发布", "备注"], "考试与科目", "exams.xlsx")
        if module == "scores":
            queryset = Score.objects.filter(is_deleted=False, exam__is_deleted=False).select_related("exam", "exam_subject__subject", "student")
            if current_class:
                queryset = queryset.filter(exam__school_class=current_class)
            rows = [[item.exam.name, item.exam_subject.subject.name, item.student.student_id, item.student.name, item.score, item.get_status_display(), item.rank, item.remarks] for item in queryset]
            return _result(rows, ["考试", "科目", "学号", "姓名", "成绩", "状态", "名次", "备注"], "成绩", "scores.xlsx")
        if module == "score_analysis":
            exam_subjects = ExamSubject.objects.filter(exam__is_deleted=False).select_related("exam", "subject")
            if current_class:
                exam_subjects = exam_subjects.filter(exam__school_class=current_class)
            rows = []
            for exam_subject in exam_subjects:
                scores = Score.objects.filter(exam_subject=exam_subject, status="normal", score__isnull=False, is_deleted=False)
                stats = scores.aggregate(avg=Avg("score"), high=Max("score"), low=Min("score"))
                count = scores.count()
                pass_count = scores.filter(score__gte=exam_subject.full_score * 0.6).count()
                excellent_count = scores.filter(score__gte=exam_subject.full_score * 0.85).count()
                rows.append([exam_subject.exam.name, exam_subject.subject.name, exam_subject.full_score, count, stats["avg"], stats["high"], stats["low"], round(pass_count / count * 100, 1) if count else 0, round(excellent_count / count * 100, 1) if count else 0])
            return _result(rows, ["考试", "科目", "满分", "有效人数", "均分", "最高", "最低", "及格率%", "优秀率%"], "成绩分析", "score_analysis.xlsx")
        queryset = SupportPlan.objects.select_related("student", "subject", "semester")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.student.student_id, item.student.name, item.get_plan_type_display(), item.subject.name, item.target_score, item.stage_goal, item.is_active, fmt(item.start_date), fmt(item.end_date)] for item in queryset]
        return _result(rows, ["学号", "姓名", "类型", "科目", "目标分数", "阶段目标", "进行中", "开始", "结束"], "培优补差", "support_plans.xlsx")

    if module in {"ai_records", "ai_exam_analysis", "ai_settings"}:
        from apps.scores.ai_models import AIAnalysisConfig, AIAnalysisRecord, AIExamAnalysisSource
        if module == "ai_records":
            queryset = AIAnalysisRecord.objects.select_related("exam", "student", "created_by")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[fmt(item.created_at), item.get_analysis_type_display(), item.exam.name if item.exam else "", item.subject_name, item.student.name if item.student else "", item.model_name, item.duration_ms, item.success, item.result, item.error_message] for item in queryset]
            return _result(rows, ["时间", "类型", "考试", "科目", "学生", "模型", "耗时ms", "成功", "结果", "错误"], "AI 成绩分析记录", "ai_analysis_records.xlsx")
        if module == "ai_exam_analysis":
            queryset = AIExamAnalysisSource.objects.select_related("exam_subject__exam", "exam_subject__subject").prefetch_related("weaknesses")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = []
            for source in queryset:
                if not source.weaknesses.exists():
                    rows.append([fmt(source.created_at), source.exam_subject.exam.name, source.exam_subject.subject.name, source.get_status_display(), source.paper_file.name, source.score_file.name, "", "", "", "", "", source.overall_summary, source.error_message])
                for item in source.weaknesses.all():
                    rows.append([fmt(source.created_at), source.exam_subject.exam.name, source.exam_subject.subject.name, source.get_status_display(), source.paper_file.name, source.score_file.name, item.question_label, item.question_type, "、".join(item.knowledge_points), item.full_score, item.score_rate, item.analysis, item.recommendation])
            return _result(rows, ["时间", "考试", "科目", "状态", "原卷文件", "小分表文件", "题号", "题型", "知识点", "满分", "得分率", "分析", "建议/错误"], "原卷小分分析", "ai_exam_analysis.xlsx")
        queryset = AIAnalysisConfig.objects.all()
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.model_name, item.base_url, item.temperature, item.is_enabled, json.dumps(item.prompts, ensure_ascii=False), fmt(item.last_used_at), item.last_error] for item in queryset]
        return _result(rows, ["模型", "API 地址", "温度", "启用", "科目提示词", "最后使用", "最后错误"], "AI 分析设置", "ai_analysis_settings.xlsx")

    if module in {"comment_templates", "comments"}:
        from apps.comments.models import CommentTemplate, StudentComment
        if module == "comment_templates":
            queryset = CommentTemplate.objects.all()
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.title, item.get_category_display(), item.content, item.is_active] for item in queryset]
            return _result(rows, ["标题", "分类", "内容", "启用"], "评语模板", "comment_templates.xlsx")
        queryset = StudentComment.objects.filter(is_deleted=False).select_related("student", "semester")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.student.student_id, item.student.name, item.semester.get_display_name(), item.get_comment_type_display(), item.content, item.get_status_display(), fmt(item.created_at)] for item in queryset]
        return _result(rows, ["学号", "姓名", "学期", "类型", "内容", "状态", "创建时间"], "学生评语", "comments.xlsx")

    if module in {"conversations", "home_school", "concerns"}:
        from apps.communications.models import StudentConversation, HomeSchoolContact, ConcernRecord
        if module == "conversations":
            queryset = StudentConversation.objects.filter(is_deleted=False).select_related("student")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[fmt(item.date), item.student.student_id, item.student.name, item.location, item.reason, item.main_content, item.student_feedback, item.follow_up_actions, fmt(item.follow_up_date), item.is_private] for item in queryset]
            return _result(rows, ["日期", "学号", "姓名", "地点", "原因", "内容", "反馈", "后续措施", "跟进日期", "私密"], "学生谈话", "conversations.xlsx")
        if module == "home_school":
            queryset = HomeSchoolContact.objects.filter(is_deleted=False).select_related("student")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[fmt(item.contact_date), item.student.student_id, item.student.name, item.contact_person, item.get_contact_method_display(), item.reason, item.summary, item.parent_feedback, item.follow_up_items, fmt(item.follow_up_date), item.is_private] for item in queryset]
            return _result(rows, ["日期", "学号", "姓名", "联系对象", "方式", "原因", "摘要", "家长反馈", "后续事项", "跟进日期", "私密"], "家校沟通", "home_school_contacts.xlsx")
        queryset = ConcernRecord.objects.select_related("student")
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.student.student_id, item.student.name, item.get_concern_type_display(), item.get_level_display(), item.observation, item.conversation_notes, item.action_plan, fmt(item.next_follow_up), item.get_status_display(), item.is_private, fmt(item.end_date)] for item in queryset]
        return _result(rows, ["学号", "姓名", "类型", "等级", "观察", "谈话", "计划", "下次跟进", "状态", "私密", "结束日期"], "重点关注", "concerns.xlsx")

    if module in {"class_meetings", "activities", "culture"}:
        from apps.activities.models import ClassMeeting, Activity, ClassCultureTask
        if module == "class_meetings":
            queryset = ClassMeeting.objects.prefetch_related("participants")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.topic, fmt(item.date), item.goal, item.agenda, item.host, "、".join(student.name for student in item.participants.all()), item.materials.name, item.summary, item.follow_up] for item in queryset]
            return _result(rows, ["主题", "日期", "目标", "流程", "主持人", "参与学生", "材料", "总结", "后续"], "主题班会", "class_meetings.xlsx")
        if module == "activities":
            queryset = Activity.objects.filter(is_deleted=False).prefetch_related("participants")
            if current_class:
                queryset = queryset.filter(school_class=current_class)
            rows = [[item.name, item.get_activity_type_display(), fmt(item.date), "、".join(student.name for student in item.participants.all()), item.person_in_charge, item.result, item.award, item.summary, item.photo.name] for item in queryset]
            return _result(rows, ["活动", "类型", "日期", "学生", "负责人", "结果", "获奖", "总结", "照片"], "文体活动", "activities.xlsx")
        queryset = ClassCultureTask.objects.all()
        if current_class:
            queryset = queryset.filter(school_class=current_class)
        rows = [[item.get_task_type_display(), item.title, item.person_in_charge, fmt(item.deadline), item.is_completed, item.summary] for item in queryset]
        return _result(rows, ["类型", "标题", "负责人", "截止时间", "完成", "总结"], "班级文化", "culture_tasks.xlsx")

    if module == "operation_logs":
        from apps.audit.models import OperationLog
        queryset = OperationLog.objects.select_related("user")
        rows = [[fmt(item.created_at), item.user.username if item.user else "", item.get_action_display(), item.module, item.object_repr, item.detail, item.ip_address, item.success] for item in queryset]
        return _result(rows, ["时间", "用户", "操作", "模块", "对象", "详情", "IP", "成功"], "操作日志", "operation_logs.xlsx")

    if module == "backup_records":
        from apps.backups.models import BackupRecord
        queryset = BackupRecord.objects.all()
        if current_class:
            queryset = queryset.filter(Q(school_class=current_class) | Q(school_class__isnull=True))
        rows = [[fmt(item.created_at), item.get_backup_type_display(), item.get_status_display(), item.file_size, item.checksum, item.version_info, item.migration_version, item.record_count, item.exam_count, item.attachment_count, item.downloaded, item.error_message] for item in queryset]
        return _result(rows, ["时间", "类型", "状态", "大小", "校验值", "版本", "迁移", "学生数", "考试数", "附件数", "已下载", "错误"], "备份记录", "backup_records.xlsx")

    raise KeyError(module)
