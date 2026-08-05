package com.classmanager.app.ui;

import android.os.Bundle;
import android.graphics.Typeface;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.StyleSpan;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class ReportActivity extends BaseActivity {
    private String endpoint;
    private LinearLayout body;
    private Spinner selector;
    private LinearLayout results;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        endpoint = getIntent().getStringExtra("endpoint");
        setup(getIntent().getStringExtra("title"), true);
        ScrollView scroll = new ScrollView(this);
        body = Ui.vertical(this);
        scroll.addView(body);
        show(scroll);
        if ("growth/".equals(endpoint) || "student-profile/".equals(endpoint)) loadSelector("students", "student_id");
        else if ("score-analysis/".equals(endpoint) || "score-comparison/".equals(endpoint)) loadSelector("exams", "exam_id");
        else if ("student-score-analysis/".equals(endpoint)) loadSelector("students", "student_id");
        else if (endpoint.endsWith("-stats/")) loadDateFilters();
        else { results = new LinearLayout(this); results.setOrientation(LinearLayout.VERTICAL); body.addView(results); load(endpoint); }
    }

    private void loadSelector(String resource, String parameter) {
        body.addView(Ui.text(this, "正在加载可选项…"));
        ApiClient.get(this).get("resources/" + resource + "/?page_size=100", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                body.removeAllViews();
                JSONArray rows = response.optJSONObject("data") == null ? null : response.optJSONObject("data").optJSONArray("results");
                List<Option> options = new ArrayList<>();
                if (rows != null) for (int i = 0; i < rows.length(); i++) {
                    JSONObject row = rows.optJSONObject(i);
                    options.add(new Option(row.optInt("id"), "students".equals(resource) ? row.optString("name") : row.optString("display")));
                }
                selector = new Spinner(ReportActivity.this);
                Ui.styleSpinner(ReportActivity.this, selector);
                selector.setAdapter(new ArrayAdapter<>(ReportActivity.this, android.R.layout.simple_spinner_dropdown_item, options));
                body.addView(selector);
                EditText from = "growth/".equals(endpoint) ? Ui.temporalInput(ReportActivity.this, "date", "") : null;
                EditText to = "growth/".equals(endpoint) ? Ui.temporalInput(ReportActivity.this, "date", "") : null;
                final Spinner moduleSelector;
                if (from != null) {
                    moduleSelector = new Spinner(ReportActivity.this);
                    Ui.styleSpinner(ReportActivity.this, moduleSelector);
                    moduleSelector.setAdapter(new ArrayAdapter<>(ReportActivity.this, android.R.layout.simple_spinner_dropdown_item,
                            new String[]{"全部模块", "荣誉评选", "奖惩记录", "积分变动", "课堂纪律", "宿舍管理", "考勤管理", "作业情况", "值日情况"}));
                    body.addView(moduleSelector);
                    from.setHint("选择开始日期（可留空）");
                    to.setHint("选择结束日期（可留空）");
                    body.addView(from);
                    body.addView(to);
                } else moduleSelector = null;
                Button button = Ui.button(ReportActivity.this, "查看");
                button.setOnClickListener(view -> {
                    Option selected = (Option) selector.getSelectedItem();
                    if (selected != null) load(endpoint + "?" + parameter + "=" + selected.id +
                            (moduleSelector == null || moduleSelector.getSelectedItemPosition() == 0 ? "" :
                                    "&module=" + new String[]{"", "evaluation", "rewards", "points", "discipline", "dormitory", "attendance", "homework", "duty"}[moduleSelector.getSelectedItemPosition()]) +
                            (from == null || from.getText().length() == 0 ? "" : "&date_from=" + from.getText()) +
                            (to == null || to.getText().length() == 0 ? "" : "&date_to=" + to.getText()));
                });
                body.addView(button);
                results = new LinearLayout(ReportActivity.this);
                results.setOrientation(LinearLayout.VERTICAL);
                body.addView(results);
                if (!options.isEmpty()) load(endpoint + "?" + parameter + "=" + options.get(0).id);
                else body.addView(Ui.text(ReportActivity.this, "暂无可分析数据。"));
            }
            @Override public void onError(String message, int statusCode) {
                body.removeAllViews();
                body.addView(Ui.text(ReportActivity.this, "加载失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void loadDateFilters() {
        EditText from = Ui.temporalInput(this, "date", ""); from.setHint("选择开始日期（可留空）");
        EditText to = Ui.temporalInput(this, "date", ""); to.setHint("选择结束日期（可留空）");
        body.addView(from); body.addView(to);
        Button query = Ui.button(this, "按日期统计");
        query.setOnClickListener(view -> load(endpoint + "?date_from=" + from.getText().toString().trim() + "&date_to=" + to.getText().toString().trim()));
        body.addView(query);
        results = new LinearLayout(this); results.setOrientation(LinearLayout.VERTICAL); body.addView(results);
        load(endpoint);
    }

    private void load(String path) {
        results.removeAllViews();
        TextView loading = Ui.text(this, "正在加载…");
        results.addView(loading);
        ApiClient.get(this).get(path, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                results.removeView(loading);
                JSONObject data = response.optJSONObject("data");
                if (data == null) results.addView(Ui.text(ReportActivity.this, "暂无数据。"));
                else if (StructuredReportRenderer.supports(endpoint)) results.addView(StructuredReportRenderer.render(ReportActivity.this, endpoint, data));
                else renderObject(results, data, 0);
            }
            @Override public void onError(String message, int statusCode) {
                results.removeView(loading);
                results.addView(Ui.text(ReportActivity.this, "加载失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void renderObject(LinearLayout parent, JSONObject object, int depth) {
        Iterator<String> keys = object.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            if (hiddenField(key) || object.has(key + "_label") || object.has(key + "_display")) continue;
            Object value = object.opt(key);
            if (value instanceof JSONObject) {
                LinearLayout card = card();
                card.addView(Ui.title(this, label(key)));
                renderObject(card, (JSONObject) value, depth + 1);
                parent.addView(card, cardParams());
            } else if (value instanceof JSONArray) {
                JSONArray array = (JSONArray) value;
                parent.addView(Ui.title(this, label(key) + "（" + array.length() + "）"));
                if (array.length() == 0) parent.addView(Ui.text(this, "暂无数据"));
                for (int i = 0; i < array.length(); i++) {
                    Object item = array.opt(i);
                    LinearLayout card = card();
                    if (item instanceof JSONObject) renderObject(card, (JSONObject) item, depth + 1);
                    else card.addView(Ui.text(this, String.valueOf(item)));
                    parent.addView(card, cardParams());
                }
            } else if (value != null && value != JSONObject.NULL) {
                String displayed = displayValue(value);
                if (displayed.isEmpty() || "null".equalsIgnoreCase(displayed)) continue;
                TextView line = Ui.text(this, "");
                SpannableStringBuilder text = new SpannableStringBuilder(label(key) + "：");
                text.setSpan(new StyleSpan(Typeface.BOLD), 0, text.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
                text.append(displayed);
                line.setText(text);
                parent.addView(line);
            }
        }
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        return card;
    }

    private LinearLayout.LayoutParams cardParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 5), 0, Ui.dp(this, 5));
        return params;
    }

    private String label(String key) {
        if (key.endsWith("_label")) key = key.substring(0, key.length() - 6);
        if (key.endsWith("_display")) key = key.substring(0, key.length() - 8);
        switch (key) {
            case "students": return "学生";
            case "student_name": return "学生";
            case "student": return "学生";
            case "subjects": return "科目";
            case "entries": return "安排";
            case "warnings": return "预警";
            case "ranking": return "排名";
            case "rooms": return "宿舍";
            case "beds": return "床位";
            case "tasks": return "任务";
            case "events": return "成长事件";
            case "total": return "总计";
            case "date": return "日期";
            case "name": return "名称";
            case "score": return "分数";
            case "rank": return "名次";
            case "count": return "数量";
            case "average": case "average_score": return "平均分";
            case "points": return "积分";
            case "reason": return "原因";
            case "content": return "内容";
            case "status": return "状态";
            case "type": return "类型";
            case "title": return "标题";
            case "class_name": return "班级";
            case "subject_name": return "科目";
            case "exam_name": return "考试";
            case "value": return "数值";
            case "level": return "等级";
            case "detail": return "详情";
            case "gender": return "性别";
            case "birth_date": return "出生日期";
            case "height": return "身高(cm)";
            case "vision": return "视力情况";
            case "seat_requirement": return "特殊座位需求";
            case "class_position": return "班级职务";
            case "home_address": return "家庭住址";
            case "is_league_member": return "是否团员";
            case "is_boarder": return "是否住校";
            case "dormitory": return "宿舍";
            case "bed_number": return "床位";
            case "primary_contact": return "主要联系人";
            case "primary_phone": return "主要联系电话";
            case "secondary_contact": return "备用联系人";
            case "secondary_phone": return "备用联系电话";
            case "remarks": return "备注";
            case "school_class": return "班级";
            case "summary": return "概览";
            case "latest_scores": return "最近成绩";
            case "growth_events": return "成长事件";
            case "conversations": return "学生谈话";
            case "comments": return "评语";
            case "growth_event_count": return "成长事件数";
            case "score_count": return "成绩记录数";
            case "conversation_count": return "谈话记录数";
            case "point_total": return "积分合计";
            case "main_content": return "主要内容";
            case "student_feedback": return "学生反馈";
            case "follow_up_actions": return "后续措施";
            case "created_at": return "创建时间";
            case "exam": return "考试";
            case "grade_rank": return "年级名次";
            case "city_rank": return "市名次";
            case "total_score": return "总分";
            case "published": return "已发布";
            case "threshold": return "阈值";
            case "unit": return "单位";
            case "rule": return "规则";
            case "by_status": return "按状态统计";
            case "by_student": return "按学生统计";
            case "by_reason": return "按原因统计";
            case "by_task": return "按任务统计";
            case "by_type": return "按类型统计";
            case "by_grade": return "按等级统计";
            case "by_room": return "按宿舍统计";
            case "classroom": return "课堂纪律";
            default: return "信息";
        }
    }

    private String displayValue(Object value) {
        if (value instanceof Boolean) return (Boolean) value ? "是" : "否";
        String text = String.valueOf(value);
        switch (text) {
            case "true": return "是";
            case "false": return "否";
            case "active": return "进行中";
            case "completed": return "已完成";
            case "pending": return "待处理";
            case "male": return "男";
            case "female": return "女";
            case "normal": return "正常";
            case "absent": return "缺勤";
            case "late": return "迟到";
            case "early_leave": return "早退";
            case "leave": return "请假";
            case "submitted": return "已交";
            case "unsubmitted": return "未交";
            case "excellent": return "优秀";
            case "good": return "良好";
            case "fair": return "一般";
            case "poor": return "差";
            case "needs_improvement": return "需整改";
            case "reward": return "奖励";
            case "penalty": return "惩罚";
            case "count": return "次数";
            case "points": return "积分";
            default: return text;
        }
    }

    private boolean hiddenField(String key) {
        return "id".equals(key) || key.endsWith("_id") || "row".equals(key) || "col".equals(key) ||
                "locked".equals(key) || "day_index".equals(key) || "weekday".equals(key) ||
                "sort_order".equals(key) || "source_type".equals(key) || "source_id".equals(key) ||
                "display".equals(key) || "module_key".equals(key) || "updated_at".equals(key);
    }

    private static final class Option {
        final int id;
        final String label;
        Option(int id, String label) { this.id = id; this.label = label; }
        @Override public String toString() { return label; }
    }
}
