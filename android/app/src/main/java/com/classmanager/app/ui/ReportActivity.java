package com.classmanager.app.ui;

import android.os.Bundle;
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
                    options.add(new Option(row.optInt("id"), row.optString("display")));
                }
                selector = new Spinner(ReportActivity.this);
                selector.setAdapter(new ArrayAdapter<>(ReportActivity.this, android.R.layout.simple_spinner_dropdown_item, options));
                body.addView(selector);
                Button button = Ui.button(ReportActivity.this, "查看分析");
                button.setOnClickListener(view -> {
                    Option selected = (Option) selector.getSelectedItem();
                    if (selected != null) load(endpoint + "?" + parameter + "=" + selected.id);
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
        EditText from = new EditText(this); from.setHint("开始日期 YYYY-MM-DD（可留空）");
        EditText to = new EditText(this); to.setHint("结束日期 YYYY-MM-DD（可留空）");
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
            if (hiddenField(key)) continue;
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
                parent.addView(Ui.text(this, label(key) + "：" + value));
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
        switch (key) {
            case "students": return "学生";
            case "student_name": return "学生";
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
            default: return key.replace('_', ' ');
        }
    }

    private boolean hiddenField(String key) {
        return "id".equals(key) || key.endsWith("_id") || "row".equals(key) || "col".equals(key) ||
                "locked".equals(key) || "day_index".equals(key) || "weekday".equals(key);
    }

    private static final class Option {
        final int id;
        final String label;
        Option(int id, String label) { this.id = id; this.label = label; }
        @Override public String toString() { return label; }
    }
}
