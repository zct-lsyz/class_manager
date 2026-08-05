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
import org.json.JSONArray;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class StructuredReportRendererTest {
    private final Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();

    @Test
    public void emptyChoicesDoNotTurnTextNumberOrDateIntoSpinners() throws Exception {
        JSONArray empty = new JSONArray();
        assertFalse(ResourceActivity.usesChoiceInput("text", null, empty));
        assertFalse(ResourceActivity.usesChoiceInput("number", null, empty));
        assertFalse(ResourceActivity.usesChoiceInput("date", null, empty));
        assertFalse(ResourceActivity.usesChoiceInput("time", null, empty));
        assertTrue(ResourceActivity.usesChoiceInput("text", null, new JSONArray("[{\"value\":\"yes\"}]")));
        assertTrue(ResourceActivity.usesChoiceInput("relation", empty, empty));
    }

    @Test
    public void rewardReasonsAreFilteredByRewardOrPenaltyType() throws Exception {
        JSONObject reward = new JSONObject("{\"item_type\":\"reward\",\"default_points\":2}");
        JSONObject penalty = new JSONObject("{\"item_type\":\"penalty\",\"default_points\":3}");
        assertTrue(ResourceActivity.rewardOptionMatches(reward, "reward"));
        assertFalse(ResourceActivity.rewardOptionMatches(reward, "penalty"));
        assertTrue(ResourceActivity.rewardOptionMatches(penalty, "penalty"));
    }

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
        JSONObject data = new JSONObject("{\"plan\":{\"id\":2,\"version\":\"3\",\"reason\":\"月度调整\",\"layout\":{\"rows\":1,\"cols\":1,\"aisle_positions\":[],\"podium_position\":\"front\"}},\"assignments\":[{\"id\":8,\"row\":0,\"col\":0,\"student_id\":6,\"student_name\":\"张三\",\"student_gender\":\"male\",\"student_dormitory\":\"101宿舍\",\"student_height\":175,\"seat_requirement\":\"靠前\",\"locked\":true}]} ");
        String text = visibleText(StructuredReportRenderer.render(context, "seating/", data));
        assertTrue(text.contains("张三"));
        assertTrue(text.contains("讲台"));
        assertFalse(text.contains("student_id"));
        assertFalse(text.contains("locked"));
        assertFalse(text.contains("row"));
        assertFalse(text.contains("col"));
        assertFalse(text.contains("101宿舍"));
        assertFalse(text.contains("175cm"));
        assertFalse(text.contains("★"));
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

    @Test
    public void scoreAnalysisRendersChineseTablesWithoutStudentIds() throws Exception {
        JSONObject data = new JSONObject("{\"exam\":{\"id\":1,\"name\":\"期中考试\",\"date\":\"2026-04-20\"},\"subjects\":[{\"name\":\"数学\",\"full_score\":100,\"count\":1,\"avg\":90,\"max\":90,\"min\":90,\"pass_rate\":100,\"excellent_rate\":100}],\"total\":{\"count\":1,\"avg\":90,\"max\":90},\"students\":[{\"student_id\":7,\"student_name\":\"王同学\",\"total_score\":90,\"rank\":1}]} ");
        String text = visibleText(StructuredReportRenderer.render(context, "score-analysis/", data));
        assertTrue(text.contains("科目统计"));
        assertTrue(text.contains("王同学"));
        assertTrue(text.contains("及格率"));
        assertFalse(text.contains("student_id"));
    }

    @Test
    public void profileGrowthAndWarningsUseCompactDedicatedViews() throws Exception {
        JSONObject profile = new JSONObject("{\"student\":{\"name\":\"张三\",\"gender_display\":\"男\",\"is_boarder\":false},\"summary\":{\"growth_event_count\":1,\"score_count\":2,\"conversation_count\":0,\"point_total\":3},\"latest_exams\":[],\"growth_events\":[{\"item\":\"课堂表现\",\"date\":\"2026-08-01\",\"adverse\":true}],\"conversations\":[],\"comments\":[]}");
        String profileText = visibleText(StructuredReportRenderer.render(context, "student-profile/", profile));
        assertTrue(profileText.contains("张三"));
        assertFalse(profileText.contains("信息："));
        assertFalse(profileText.contains("is_boarder"));

        JSONObject growth = new JSONObject("{\"student\":{\"name\":\"张三\"},\"events\":[{\"module\":\"课堂纪律\",\"item\":\"上课讲话\",\"date\":\"2026-08-01\",\"points\":-1,\"adverse\":true,\"note\":\"已提醒\"}]}");
        String growthText = visibleText(StructuredReportRenderer.render(context, "growth/", growth));
        assertTrue(growthText.contains("上课讲话"));
        assertFalse(growthText.contains("信息：是"));

        JSONObject warnings = new JSONObject("{\"students\":[{\"student_name\":\"张三\",\"warnings\":[{\"rule\":\"作业未交\",\"events\":[{\"item\":\"数学作业\"}]}]}]}");
        String warningText = visibleText(StructuredReportRenderer.render(context, "warnings/", warnings));
        assertTrue(warningText.contains("张三"));
        assertFalse(warningText.contains("成长事件"));
        assertFalse(warningText.contains("作业未交"));
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
