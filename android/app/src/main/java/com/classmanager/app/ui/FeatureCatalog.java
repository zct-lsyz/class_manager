package com.classmanager.app.ui;

import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class FeatureCatalog {
    public static final String RESOURCE = "resource";
    public static final String REPORT = "report";
    public static final String BACKUP = "backup";
    public static final String ACCOUNT = "account";

    public static final class Entry {
        public final String title;
        public final String kind;
        public final String value;

        Entry(String title, String kind, String value) {
            this.title = title;
            this.kind = kind;
            this.value = value;
        }
    }

    private static Entry r(String title, String resource) { return new Entry(title, RESOURCE, resource); }
    private static Entry p(String title, String endpoint) { return new Entry(title, REPORT, endpoint); }

    public static Map<String, List<Entry>> sections() {
        Map<String, List<Entry>> map = new LinkedHashMap<>();
        map.put("待办事项", Arrays.asList(r("全部待办", "todos")));
        map.put("学生花名册", Arrays.asList(r("学生档案", "students")));
        map.put("班级与学期", Arrays.asList(r("班级管理", "classes"), r("学期管理", "semesters")));
        map.put("家长联系方式", Arrays.asList(r("家长联系方式", "guardians")));
        map.put("课程表", Arrays.asList(p("查看当前课程表", "course-schedule/")));
        map.put("座位表", Arrays.asList(p("查看当前座位表", "seating/")));
        map.put("值日生表", Arrays.asList(p("查看值日生表", "duty-roster/")));
        map.put("考勤管理", Arrays.asList(r("异常考勤", "attendance"), r("考勤原因设置", "attendance_reasons")));
        map.put("作业检查", Arrays.asList(r("作业任务", "homework_tasks"), r("学生完成情况", "homework_records"), r("作业状态设置", "homework_statuses"), r("科目设置", "subjects")));
        map.put("课堂纪律", Arrays.asList(r("课堂纪律记录", "classroom_discipline"), r("纪律条目设置", "discipline_items")));
        map.put("宿舍管理", Arrays.asList(p("床位总览", "dormitory/"), r("宿舍楼", "dorm_buildings"), r("宿舍", "dorm_rooms"), r("住宿分配", "dorm_assignments"), r("卫生检查", "hygiene_checks"), r("卫生检查项", "hygiene_items"), r("宿舍纪律", "dorm_discipline")));
        map.put("奖惩管理", Arrays.asList(r("奖惩记录", "rewards"), r("奖惩条目", "reward_items")));
        map.put("积分排名", Arrays.asList(p("排名总览", "ranking/"), r("积分明细", "point_records"), r("排名来源设置", "ranking_settings")));
        map.put("预警管理", Arrays.asList(p("当前预警", "warnings/"), r("预警规则", "warning_rules")));
        map.put("成绩分析", Arrays.asList(p("班级成绩分析", "score-analysis/"), r("考试管理", "exams"), r("考试科目", "exam_subjects"), r("成绩录入", "scores"), r("本班考试总分", "exam_totals"), r("分数线设置", "grade_lines"), r("外部对比班级", "external_classes"), r("外部班级单科成绩", "external_scores"), r("外部班级总分", "external_totals"), r("培优补差计划", "support_plans"), r("培优补差跟进", "support_followups")));
        map.put("成长足迹", Arrays.asList(p("学生成长时间线", "growth/")));
        map.put("学生谈话", Arrays.asList(r("学生谈话", "conversations"), r("家校沟通", "home_school_contacts"), r("重点关注", "concerns")));
        map.put("备份管理", Arrays.asList(new Entry("备份与恢复", BACKUP, ""), r("存储提醒规则", "storage_alerts")));
        map.put("账户与安全", Arrays.asList(new Entry("账户与安全", ACCOUNT, "")));
        return map;
    }

    private FeatureCatalog() {}
}
