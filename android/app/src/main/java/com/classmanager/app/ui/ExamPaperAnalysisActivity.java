package com.classmanager.app.ui;

import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ExamPaperAnalysisActivity extends BaseActivity {
    private static final int SELECT_PAPER = 4401;
    private static final int SELECT_SCORES = 4402;
    private LinearLayout root;
    private Uri paperUri;
    private Uri scoreUri;
    private TextView paperLabel;
    private TextView scoreLabel;
    private JSONObject data;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("原卷与小分表 AI 分析", true);
        ScrollView scroll = new ScrollView(this);
        root = Ui.vertical(this);
        scroll.addView(root);
        show(scroll);
        load();
    }

    private void load() {
        root.removeAllViews();
        root.addView(Ui.text(this, "正在加载分析配置与历史记录…"));
        ApiClient.get(this).get("exam-paper-analysis/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                data = response.optJSONObject("data");
                render();
            }
            @Override public void onError(String message, int statusCode) {
                root.removeAllViews();
                root.addView(Ui.text(ExamPaperAnalysisActivity.this, "加载失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void render() {
        root.removeAllViews();
        if (data == null) return;
        root.addView(Ui.text(this, data.optBoolean("ai_ready")
                ? "服务器 AI 已就绪。小分表只提取匿名逐题统计后发送给外部 AI。"
                : "服务器 AI 尚未启用或未配置 DEEPSEEK_API_KEY。"));
        Spinner subject = spinner(strings(data.optJSONArray("subjects")));
        Spinner examSubject = spinner(options(data.optJSONArray("exam_subjects")));
        root.addView(Ui.title(this, "新建分析"));
        root.addView(Ui.text(this, "科目"));
        root.addView(subject);
        root.addView(Ui.text(this, "关联考试科目（可留空）"));
        root.addView(examSubject);
        Button paper = Ui.button(this, "选择试卷原卷（PDF/DOCX/TXT/图片）");
        paper.setOnClickListener(view -> chooseFile(SELECT_PAPER, "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain", "image/*"));
        root.addView(paper);
        paperLabel = Ui.text(this, paperUri == null ? "尚未选择原卷" : "已选择原卷：" + paperUri.getLastPathSegment());
        root.addView(paperLabel);
        Button scores = Ui.button(this, "选择匿名小分表（XLSX）");
        scores.setOnClickListener(view -> chooseFile(SELECT_SCORES, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"));
        root.addView(scores);
        scoreLabel = Ui.text(this, scoreUri == null ? "尚未选择小分表" : "已选择小分表：" + scoreUri.getLastPathSegment());
        root.addView(scoreLabel);
        CheckBox privacy = new CheckBox(this);
        privacy.setText(com.classmanager.app.R.string.confirm_anonymous_ai_data);
        root.addView(privacy);
        Button submit = Ui.button(this, "开始分析");
        submit.setEnabled(data.optBoolean("ai_ready"));
        submit.setOnClickListener(view -> upload(subject, examSubject, privacy));
        root.addView(submit);
        root.addView(Ui.title(this, "最近分析"));
        JSONArray sources = data.optJSONArray("sources");
        if (sources == null || sources.length() == 0) root.addView(Ui.text(this, "暂无分析记录。"));
        else for (int i = 0; i < sources.length(); i++) renderSource(sources.optJSONObject(i));
    }

    private void upload(Spinner subject, Spinner examSubject, CheckBox privacy) {
        if (paperUri == null || scoreUri == null) { toast("请同时选择原卷和小分表。"); return; }
        if (!privacy.isChecked()) { toast("请先确认匿名数据范围。"); return; }
        JSONObject fields = new JSONObject();
        try {
            fields.put("subject_name", String.valueOf(subject.getSelectedItem()));
            Option option = (Option) examSubject.getSelectedItem();
            if (option != null && option.id > 0) fields.put("exam_subject_id", option.id);
            fields.put("privacy_confirm", true);
        } catch (Exception ignored) {}
        Map<String, Uri> files = new LinkedHashMap<>();
        files.put("paper_file", paperUri);
        files.put("score_file", scoreUri);
        toast("正在解析并生成分析，可能需要几分钟…");
        ApiClient.get(this).upload("exam-paper-analysis/", fields, files, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                toast("分析完成。");
                paperUri = null;
                scoreUri = null;
                load();
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void renderSource(JSONObject row) {
        if (row == null) return;
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(com.classmanager.app.R.drawable.bg_card);
        card.addView(Ui.title(this, row.optString("subject_name") + " · " + row.optString("status_display")));
        card.addView(Ui.text(this, row.optString("created_at").replace('T', ' ') +
                (row.optString("exam").isEmpty() ? "" : "\n考试：" + row.optString("exam")) +
                (row.optString("overall_summary").isEmpty() ? "" : "\n" + row.optString("overall_summary")) +
                (row.optString("error_message").isEmpty() ? "" : "\n失败：" + row.optString("error_message"))));
        JSONArray weaknesses = row.optJSONArray("weaknesses");
        if (weaknesses != null) for (int i = 0; i < weaknesses.length(); i++) {
            JSONObject item = weaknesses.optJSONObject(i);
            card.addView(Ui.text(this, item.optString("question_label") + " · " + item.optString("weakness_level") +
                    " · 得分率 " + Math.round(item.optDouble("score_rate") * 100) + "%\n" +
                    item.optJSONArray("knowledge_points") + "\n" + item.optString("analysis") +
                    (item.optString("recommendation").isEmpty() ? "" : "\n建议：" + item.optString("recommendation"))));
        }
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 5), 0, Ui.dp(this, 5));
        root.addView(card, params);
    }

    private void chooseFile(int requestCode, String... mimeTypes) {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType(mimeTypes.length == 1 ? mimeTypes[0] : "*/*");
        if (mimeTypes.length > 1) intent.putExtra(Intent.EXTRA_MIME_TYPES, mimeTypes);
        startActivityForResult(intent, requestCode);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent intent) {
        super.onActivityResult(requestCode, resultCode, intent);
        if (resultCode != RESULT_OK || intent == null || intent.getData() == null) return;
        if (requestCode == SELECT_PAPER) {
            paperUri = intent.getData();
            paperLabel.setText(getString(com.classmanager.app.R.string.selected_paper, paperUri.getLastPathSegment()));
        } else if (requestCode == SELECT_SCORES) {
            scoreUri = intent.getData();
            scoreLabel.setText(getString(com.classmanager.app.R.string.selected_score_sheet, scoreUri.getLastPathSegment()));
        }
    }

    private <T> Spinner spinner(List<T> values) {
        Spinner spinner = new Spinner(this);
        spinner.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, values));
        return spinner;
    }

    private List<String> strings(JSONArray rows) {
        List<String> values = new ArrayList<>();
        if (rows != null) for (int i = 0; i < rows.length(); i++) values.add(rows.optString(i));
        return values;
    }

    private List<Option> options(JSONArray rows) {
        List<Option> values = new ArrayList<>();
        values.add(new Option(0, "不关联具体考试"));
        if (rows != null) for (int i = 0; i < rows.length(); i++) {
            JSONObject row = rows.optJSONObject(i);
            values.add(new Option(row.optInt("id"), row.optString("label")));
        }
        return values;
    }

    private static final class Option {
        final int id;
        final String label;
        Option(int id, String label) { this.id = id; this.label = label; }
        @Override public String toString() { return label; }
    }
}
