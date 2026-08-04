package com.classmanager.app.ui;

import android.os.Bundle;
import android.text.InputType;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;

import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class AiAnalysisActivity extends BaseActivity {
    private LinearLayout root;
    private JSONObject data;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("AI 成绩分析", true);
        ScrollView scroll = new ScrollView(this);
        root = Ui.vertical(this);
        scroll.addView(root);
        show(scroll);
        load();
    }

    private void load() {
        root.removeAllViews();
        root.addView(Ui.text(this, "正在加载 AI 配置与历史记录…"));
        ApiClient.get(this).get("ai-analysis/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                data = response.optJSONObject("data");
                render();
            }
            @Override public void onError(String message, int statusCode) {
                root.removeAllViews();
                root.addView(Ui.text(AiAnalysisActivity.this, "加载失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void render() {
        root.removeAllViews();
        if (data == null) return;
        JSONObject config = data.optJSONObject("config");
        root.addView(Ui.title(this, "服务器 AI 配置"));
        EditText model = input("模型名称", config == null ? "deepseek-chat" : config.optString("model_name"));
        EditText baseUrl = input("API 地址", config == null ? "https://api.deepseek.com" : config.optString("base_url"));
        EditText temperature = input("温度", config == null ? "0.5" : String.valueOf(config.optDouble("temperature", 0.5)));
        temperature.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL);
        CheckBox enabled = new CheckBox(this);
        enabled.setText("启用 AI 分析");
        enabled.setChecked(config != null && config.optBoolean("is_enabled"));
        root.addView(model); root.addView(baseUrl); root.addView(temperature); root.addView(enabled);
        root.addView(Ui.text(this, config != null && config.optBoolean("has_api_key")
                ? "服务器已配置 DEEPSEEK_API_KEY。" : "服务器尚未配置 DEEPSEEK_API_KEY。"));
        Button save = Ui.button(this, "保存配置");
        save.setOnClickListener(view -> {
            JSONObject body = new JSONObject();
            try {
                body.put("action", "save"); body.put("model_name", model.getText().toString());
                body.put("base_url", baseUrl.getText().toString());
                body.put("temperature", Double.parseDouble(temperature.getText().toString()));
                body.put("is_enabled", enabled.isChecked());
            } catch (Exception exception) { toast("温度格式不正确。"); return; }
            post(body, "配置已保存。");
        });
        root.addView(save);
        Button test = Ui.button(this, "测试 AI 连接");
        test.setOnClickListener(view -> action("test", "连接测试成功。"));
        root.addView(test);
        Button reset = Ui.button(this, "恢复默认提示词");
        reset.setOnClickListener(view -> action("reset_prompts", "提示词已恢复。"));
        root.addView(reset);

        root.addView(Ui.title(this, "生成分析"));
        Spinner type = spinner(new String[]{"单科分析", "综合分析", "学生个人分析"});
        List<Option> exams = options(data.optJSONArray("exams"), "name");
        List<Option> students = options(data.optJSONArray("students"), "name");
        Spinner exam = spinner(exams);
        Spinner subject = spinner(strings(data.optJSONArray("subjects")));
        Spinner student = spinner(students);
        root.addView(type); root.addView(exam); root.addView(subject); root.addView(student);
        Button generate = Ui.button(this, "开始生成 AI 分析");
        generate.setOnClickListener(view -> {
            Option selectedExam = (Option) exam.getSelectedItem();
            if (selectedExam == null) { toast("请先创建考试并录入成绩。"); return; }
            JSONObject body = new JSONObject();
            try {
                body.put("action", "generate");
                body.put("analysis_type", type.getSelectedItemPosition() == 0 ? "subject" : type.getSelectedItemPosition() == 1 ? "comprehensive" : "student");
                body.put("exam_id", selectedExam.id);
                body.put("subject_name", subject.getSelectedItem() == null ? "" : subject.getSelectedItem().toString());
                Option selectedStudent = (Option) student.getSelectedItem();
                if (selectedStudent != null) body.put("student_id", selectedStudent.id);
            } catch (Exception ignored) {}
            post(body, "AI 分析生成成功。");
        });
        root.addView(generate);

        root.addView(Ui.title(this, "分析历史"));
        JSONArray records = data.optJSONArray("records");
        if (records == null || records.length() == 0) root.addView(Ui.text(this, "暂无分析记录。"));
        else for (int i = 0; i < records.length(); i++) {
            JSONObject row = records.optJSONObject(i);
            root.addView(Ui.text(this, row.optString("created_at").replace('T', ' ') + " · " +
                    row.optString("analysis_type_display") + " · " + row.optString("exam") + "\n" +
                    (row.optBoolean("success") ? row.optString("result") : "失败：" + row.optString("error_message"))));
        }
    }

    private EditText input(String hint, String value) {
        EditText input = new EditText(this);
        input.setHint(hint); input.setText(value); input.setSingleLine(true);
        return input;
    }

    private Spinner spinner(String[] values) {
        Spinner spinner = new Spinner(this);
        spinner.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, values));
        return spinner;
    }

    private <T> Spinner spinner(List<T> values) {
        Spinner spinner = new Spinner(this);
        spinner.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, values));
        return spinner;
    }

    private List<Option> options(JSONArray rows, String labelKey) {
        List<Option> values = new ArrayList<>();
        if (rows != null) for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            values.add(new Option(row.optInt("id"), row.optString(labelKey)));
        }
        return values;
    }

    private List<String> strings(JSONArray rows) {
        List<String> values = new ArrayList<>();
        if (rows != null) for (int i = 0; i < rows.length(); i++) values.add(rows.optString(i));
        return values;
    }

    private void action(String action, String message) {
        JSONObject body = new JSONObject();
        try { body.put("action", action); } catch (Exception ignored) {}
        post(body, message);
    }

    private void post(JSONObject body, String message) {
        toast("正在处理，请稍候…");
        ApiClient.get(this).post("ai-analysis/", body, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) { toast(message); load(); }
            @Override public void onError(String value, int statusCode) { toast(value); handleAuthError(statusCode); }
        });
    }

    private static final class Option {
        final int id; final String label;
        Option(int id, String label) { this.id = id; this.label = label; }
        @Override public String toString() { return label; }
    }
}
