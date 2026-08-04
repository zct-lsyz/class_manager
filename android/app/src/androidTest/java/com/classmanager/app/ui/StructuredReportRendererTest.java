package com.classmanager.app.ui;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class StructuredReportRendererTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();

    @Test
    public void courseScheduleRendersWebsiteStyleGridWithoutInternalFields() throws Exception {
        JSONObject data = new JSONObject("{\"semester\":\"2026-2027学年第一学期\",\"weekdays\":[{\"value\":1,\"label\":\"周一\"}],\"periods\":[{\"period\":1,\"name\":\"第一节\",\"start_time\":\"08:00\",\"end_time\":\"08:45\"}],\"entries\":[{\"id\":9,\"weekday\":1,\"period\":1,\"course\":\"语文\",\"teacher\":\"王老师\"}]} ");
        String text = visibleText(StructuredReportRenderer.render(context, "course-schedule/", data));
        assertTrue(text.contains("节次"));
        assertTrue(text.contains("语文"));
        assertTrue(text.contains("王老师"));
        assertFalse(text.contains("weekday"));
        assertFalse(text.contains("id"));
    }

    @Test
    public void seatingRendersSeatGridWithoutCoordinateOrLockFields() throws Exception {
        JSONObject data = new JSONObject("{\"plan\":{\"id\":2,\"version\":\"3\",\"reason\":\"月度调整\",\"layout\":{\"rows\":1,\"cols\":1,\"aisle_positions\":[],\"podium_position\":\"front\"}},\"assignments\":[{\"id\":8,\"row\":0,\"col\":0,\"student_id\":6,\"student_name\":\"张三\",\"student_gender\":\"male\",\"locked\":true}]} ");
        String text = visibleText(StructuredReportRenderer.render(context, "seating/", data));
        assertTrue(text.contains("张三"));
        assertTrue(text.contains("讲台"));
        assertFalse(text.contains("student_id"));
        assertFalse(text.contains("locked"));
        assertFalse(text.contains("row"));
        assertFalse(text.contains("col"));
    }

    @Test
    public void dutyRosterRendersDateByTaskTableWithoutIds() throws Exception {
        JSONObject data = new JSONObject("{\"roster\":{\"id\":1,\"name\":\"第一周值日\",\"date_start\":\"2026-08-03\",\"date_end\":\"2026-08-03\",\"day_count\":1},\"tasks\":[{\"id\":4,\"name\":\"擦黑板\",\"people_count\":1}],\"entries\":[{\"id\":7,\"day_index\":0,\"date\":\"2026-08-03\",\"task_id\":4,\"student_id\":6,\"student_name\":\"李四\"}]} ");
        String text = visibleText(StructuredReportRenderer.render(context, "duty-roster/", data));
        assertTrue(text.contains("日期"));
        assertTrue(text.contains("擦黑板"));
        assertTrue(text.contains("李四"));
        assertFalse(text.contains("task_id"));
        assertFalse(text.contains("student_id"));
    }

    private String visibleText(View view) {
        StringBuilder result = new StringBuilder();
        appendText(view, result);
        return result.toString();
    }

    private void appendText(View view, StringBuilder result) {
        if (view instanceof TextView) result.append(((TextView) view).getText()).append('\n');
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) appendText(group.getChildAt(i), result);
        }
    }
}
