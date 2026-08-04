package com.classmanager.app.ui;

import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
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

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        endpoint = getIntent().getStringExtra("endpoint");
        setup(getIntent().getStringExtra("title"), true);
        ScrollView scroll = new ScrollView(this);
        body = Ui.vertical(this);
        scroll.addView(body);
        show(scroll);
        if ("growth/".equals(endpoint)) loadSelector("students", "student_id");
        else if ("score-analysis/".equals(endpoint)) loadSelector("exams", "exam_id");
        else load(endpoint);
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

    private void load(String path) {
        TextView loading = Ui.text(this, "正在加载…");
        body.addView(loading);
        ApiClient.get(this).get(path, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                body.removeView(loading);
                JSONObject data = response.optJSONObject("data");
                if (data == null) body.addView(Ui.text(ReportActivity.this, "暂无数据。"));
                else renderObject(body, data, 0);
            }
            @Override public void onError(String message, int statusCode) {
                body.removeView(loading);
                body.addView(Ui.text(ReportActivity.this, "加载失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void renderObject(LinearLayout parent, JSONObject object, int depth) {
        Iterator<String> keys = object.keys();
        while (keys.hasNext()) {
            String key = keys.next();
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

    private static final class Option {
        final int id;
        final String label;
        Option(int id, String label) { this.id = id; this.label = label; }
        @Override public String toString() { return label; }
    }
}
