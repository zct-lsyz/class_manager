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
}
