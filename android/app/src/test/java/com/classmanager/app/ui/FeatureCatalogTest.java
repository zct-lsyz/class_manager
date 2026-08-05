package com.classmanager.app.ui;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FeatureCatalogTest {
    @Test
    public void exposesEveryRequestedFeatureSection() {
        String[] expected = {
                "待办事项", "学生花名册", "班级与学期", "家长联系方式",
                "课程表", "座位表", "值日生表", "考勤管理", "作业检查",
                "课堂纪律", "宿舍管理", "奖惩管理", "积分排名", "预警管理",
                "成绩分析", "成长足迹", "学生谈话", "备份管理", "账户与安全"
        };
        assertEquals(expected.length, FeatureCatalog.sections().size());
        for (String section : expected) assertTrue(section, FeatureCatalog.sections().containsKey(section));
    }

    @Test
    public void viewOnlyModulesUseReportEndpoints() {
        assertEquals(FeatureCatalog.REPORT, FeatureCatalog.sections().get("课程表").get(0).kind);
        assertEquals(FeatureCatalog.REPORT, FeatureCatalog.sections().get("座位表").get(0).kind);
        assertEquals(FeatureCatalog.REPORT, FeatureCatalog.sections().get("值日生表").get(0).kind);
    }

    @Test
    public void followsWebsiteNavigationGroupOrder() {
        assertEquals(
                java.util.Arrays.asList("工作台", "班级基础", "日常管理", "教学管理", "成长记录", "数据中心", "系统设置"),
                new java.util.ArrayList<>(FeatureCatalog.groups().keySet())
        );
    }

    @Test
    public void viewOnlyModulesHaveDedicatedTableRenderers() {
        assertTrue(StructuredReportRenderer.supports("course-schedule/"));
        assertTrue(StructuredReportRenderer.supports("seating/"));
        assertTrue(StructuredReportRenderer.supports("duty-roster/"));
    }

    @Test
    public void dormitoryAndScoreSectionsExposeOnlyRequestedFunctions() {
        assertEquals(
                java.util.Arrays.asList("查询舍长及床位分配", "录入卫生检查", "录入宿舍纪律"),
                FeatureCatalog.sections().get("宿舍管理").stream().map(item -> item.title).collect(java.util.stream.Collectors.toList())
        );
        for (FeatureCatalog.Entry item : FeatureCatalog.sections().get("成绩分析"))
            assertTrue(!FeatureCatalog.RESOURCE.equals(item.kind));
        assertEquals(FeatureCatalog.RANKING, FeatureCatalog.sections().get("积分排名").get(0).kind);
    }

    @Test
    public void scoreAnalysisPagesHaveDedicatedTableRenderers() {
        assertTrue(StructuredReportRenderer.supports("score-analysis/"));
        assertTrue(StructuredReportRenderer.supports("student-score-analysis/"));
        assertTrue(StructuredReportRenderer.supports("score-comparison/"));
        assertTrue(StructuredReportRenderer.supports("student-profile/"));
        assertTrue(StructuredReportRenderer.supports("growth/"));
        assertTrue(StructuredReportRenderer.supports("warnings/"));
    }
}
