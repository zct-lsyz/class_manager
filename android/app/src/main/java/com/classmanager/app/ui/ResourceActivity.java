package com.classmanager.app.ui;

import android.Manifest;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.speech.RecognizerIntent;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.StyleSpan;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.AdapterView;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import androidx.appcompat.widget.AppCompatButton;
import androidx.core.app.ActivityCompat;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;
import com.classmanager.app.notification.NotificationScheduler;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

public class ResourceActivity extends BaseActivity {
    private String resource;
    private String title;
    private LinearLayout root;
    private EditText search;
    private ListView list;
    private JSONArray records = new JSONArray();
    private JSONObject schema;
    private FileButton pendingFileButton;
    private EditText pendingVoiceInput;
    private int pendingHygieneCheckId;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        resource = getIntent().getStringExtra("resource");
        title = getIntent().getStringExtra("title");
        setup(title == null ? "数据管理" : title, true);
        render();
        load("");
    }

    private void render() {
        root = Ui.vertical(this);
        root.addView(Ui.title(this, title == null ? "数据管理" : title));
        LinearLayout controls = new LinearLayout(this);
        controls.setOrientation(LinearLayout.HORIZONTAL);
        search = new EditText(this);
        search.setHint("搜索");
        Ui.styleInput(this, search);
        controls.addView(search, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button searchButton = Ui.outlineButton(this, "查询");
        searchButton.setOnClickListener(view -> load(search.getText().toString().trim()));
        LinearLayout.LayoutParams actionParams = new LinearLayout.LayoutParams(Ui.dp(this, 82), ViewGroup.LayoutParams.WRAP_CONTENT);
        actionParams.leftMargin = Ui.dp(this, 8);
        controls.addView(searchButton, actionParams);
        root.addView(controls);
        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        Button add = Ui.button(this, supportsBatch() ? "新增 / 批量登记" : "新增");
        add.setOnClickListener(view -> { if (supportsBatch()) batchEdit(); else edit(null); });
        actions.addView(add, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        root.addView(actions);
        if ("students".equals(resource)) root.addView(studentHeader());
        list = new ListView(this);
        list.setDivider(new android.graphics.drawable.ColorDrawable(0xffe2e8f0));
        list.setDividerHeight(Ui.dp(this, 1));
        list.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 16));
        list.setClipToPadding(false);
        root.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        list.setOnItemClickListener((parent, view, position, id) -> {
            JSONObject record = records.optJSONObject(position);
            if ("hygiene_checks".equals(resource)) hygieneActions(record);
            else showDetail(record);
        });
        list.setOnItemLongClickListener((parent, view, position, id) -> {
            confirmDelete(records.optJSONObject(position));
            return true;
        });
        show(root);
    }

    private void load(String query) {
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, new String[]{"正在加载…"}));
        String path = "resources/" + resource + "/?page_size=100";
        if (!query.isEmpty()) path += "&search=" + android.net.Uri.encode(query);
        ApiClient.get(this).get(path, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                records = data == null ? new JSONArray() : data.optJSONArray("results");
                if (records == null) records = new JSONArray();
                schema = data == null ? null : data.optJSONObject("schema");
                list.setAdapter(new RecordAdapter());
            }
            @Override public void onError(String message, int statusCode) {
                list.setAdapter(new ArrayAdapter<>(ResourceActivity.this, android.R.layout.simple_list_item_1, new String[]{"加载失败：" + message}));
                handleAuthError(statusCode);
            }
        });
    }

    private String rowLabel(JSONObject row) {
        return summaryText(row).toString();
    }

    private void showDetail(JSONObject record) {
        if (record == null || schema == null) return;
        LinearLayout details = Ui.vertical(this);
        JSONArray fields = schema.optJSONArray("fields");
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || hiddenField(field.optString("name"), true)) continue;
            CharSequence value = fieldValue(record, field);
            if (value.length() == 0) continue;
            TextView line = Ui.text(this, "");
            SpannableStringBuilder text = new SpannableStringBuilder();
            appendBold(text, field.optString("label") + "：");
            text.append(value);
            line.setText(text);
            line.setPadding(Ui.dp(this, 12), Ui.dp(this, 9), Ui.dp(this, 12), Ui.dp(this, 9));
            if (i % 2 == 0) line.setBackgroundColor(0xfff8fafc);
            details.addView(line);
        }
        ScrollView scroll = new ScrollView(this);
        scroll.addView(details);
        AlertDialog.Builder builder = new AlertDialog.Builder(this)
                .setTitle(recordTitle(record)).setView(scroll).setNegativeButton("关闭", null);
        if (schema.optBoolean("allow_edit", true)) builder.setPositiveButton("编辑", (dialog, which) -> edit(record));
        builder.show();
    }

    private CharSequence summaryText(JSONObject row) {
        SpannableStringBuilder result = new SpannableStringBuilder();
        appendBold(result, recordTitle(row));
        JSONArray fields = schema == null ? null : schema.optJSONArray("fields");
        int appended = 0;
        for (int i = 0; fields != null && i < fields.length() && appended < 3; i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || hiddenField(field.optString("name"), false)) continue;
            CharSequence value = fieldValue(row, field);
            if (value.length() == 0 || "—".contentEquals(value) || value.toString().equals(recordTitle(row))) continue;
            result.append('\n');
            appendBold(result, field.optString("label") + "：");
            result.append(value);
            appended++;
        }
        return result;
    }

    private CharSequence guardianText(JSONObject row) {
        SpannableStringBuilder result = new SpannableStringBuilder();
        appendBold(result, "学生：");
        result.append(cleanStudentLabel(row.optString("student_label")));
        result.append('\n');
        appendBold(result, "主要联系人：");
        result.append(valueOrEmpty(row, "primary_contact"));
        result.append('\n');
        appendBold(result, "其他监护人：");
        result.append(emptyAsDash(row.optString("other_guardian")));
        return result;
    }

    private String recordTitle(JSONObject row) {
        if (row == null) return "记录";
        if ("todos".equals(resource)) return row.optString("title", "待办事项");
        if ("students".equals(resource)) return row.optString("name", "学生档案");
        if ("guardians".equals(resource)) return cleanStudentLabel(row.optString("student_label")) + "的家长联系方式";
        if (row.has("student_label")) return cleanStudentLabel(row.optString("student_label"));
        String display = row.optString("display");
        if (!display.isEmpty() && !display.matches(".*#\\d+$")) return cleanStudentLabel(display);
        JSONArray fields = schema == null ? null : schema.optJSONArray("fields");
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field != null && !hiddenField(field.optString("name"), false)) {
                CharSequence value = fieldValue(row, field);
                if (value.length() > 0) return value.toString();
            }
        }
        return "记录";
    }

    private CharSequence fieldValue(JSONObject row, JSONObject field) {
        String name = field.optString("name");
        if ("points_sign".equals(name)) {
            int points = row.optInt("points_deducted");
            return "attendance".equals(resource) ? (points >= 0 ? "加分" : "扣分") : (points < 0 ? "加分" : "扣分");
        }
        if ("points_deducted".equals(name) && ("attendance".equals(resource) ||
                "classroom_discipline".equals(resource) || "dorm_discipline".equals(resource)))
            return String.valueOf(Math.abs(row.optInt(name)));
        Object raw = row.opt(name);
        String value;
        if (row.has(name + "_display")) value = row.optString(name + "_display");
        else if (row.has(name + "_label")) value = row.optString(name + "_label");
        else if (raw instanceof Boolean) value = (Boolean) raw ? "是" : "否";
        else if (raw instanceof JSONArray) value = joinArray((JSONArray) raw);
        else value = raw == null || raw == JSONObject.NULL ? "" : String.valueOf(raw);
        if ("student".equals(name)) value = cleanStudentLabel(value);
        return emptyAsDash(chineseValue(value));
    }

    private String valueOrEmpty(JSONObject row, String name) {
        String value = row.optString(name + "_display", row.optString(name + "_label", row.optString(name)));
        return emptyAsDash(chineseValue(value));
    }

    private String chineseValue(String value) {
        if (value == null || value.isEmpty() || "null".equals(value)) return "";
        switch (value) {
            case "true": return "是";
            case "false": return "否";
            case "male": return "男";
            case "female": return "女";
            case "active": return "进行中";
            case "completed": return "已完成";
            case "pending": return "待处理";
            case "normal": return "正常";
            default: return value;
        }
    }

    private boolean hiddenField(String name, boolean detail) {
        if ("id".equals(name) || name.endsWith("_id") || "source_id".equals(name) || "source_type".equals(name) ||
                "sort_order".equals(name) || "created_at".equals(name) || "updated_at".equals(name) || "is_deleted".equals(name)) return true;
        if ("student_id".equals(name)) return true;
        if (!detail && ("school_class".equals(name) || "completed_at".equals(name))) return true;
        return false;
    }

    private String cleanStudentLabel(String value) {
        if (value == null) return "";
        int chinese = value.indexOf('（');
        int ascii = value.indexOf('(');
        int index = chinese >= 0 ? chinese : ascii;
        if (index > 0) {
            String suffix = value.substring(index);
            if (suffix.matches(".*\\d{6,}.*") || suffix.contains("学号")) return value.substring(0, index).trim();
        }
        return value;
    }

    private void appendBold(SpannableStringBuilder builder, String value) {
        int start = builder.length();
        builder.append(value);
        builder.setSpan(new StyleSpan(Typeface.BOLD), start, builder.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
    }

    private String emptyAsDash(String value) { return value == null || value.isEmpty() || "null".equals(value) ? "—" : value; }

    private String joinArray(JSONArray values) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < values.length(); i++) {
            if (i > 0) result.append("、");
            result.append(values.optString(i));
        }
        return result.toString();
    }

    private final class RecordAdapter extends BaseAdapter {
        @Override public int getCount() { return Math.max(1, records.length()); }
        @Override public Object getItem(int position) { return records.optJSONObject(position); }
        @Override public long getItemId(int position) { JSONObject row = records.optJSONObject(position); return row == null ? 0 : row.optLong("id"); }
        @Override public boolean isEnabled(int position) { return records.length() > 0; }

        @Override public View getView(int position, View convertView, ViewGroup parent) {
            if (records.length() == 0) {
                TextView empty = Ui.text(ResourceActivity.this, "暂无记录，点击“新增”开始录入。");
                empty.setGravity(Gravity.CENTER);
                empty.setTextColor(0xff64748b);
                empty.setPadding(0, Ui.dp(ResourceActivity.this, 36), 0, Ui.dp(ResourceActivity.this, 36));
                return empty;
            }
            JSONObject row = records.optJSONObject(position);
            if ("todos".equals(resource)) return todoRow(row);
            if ("students".equals(resource)) return studentRow(row);
            TextView text = Ui.text(ResourceActivity.this, "");
            text.setText("guardians".equals(resource) ? guardianText(row) : summaryText(row));
            text.setTextSize(15);
            text.setPadding(Ui.dp(ResourceActivity.this, 14), Ui.dp(ResourceActivity.this, 10), Ui.dp(ResourceActivity.this, 14), Ui.dp(ResourceActivity.this, 10));
            text.setBackgroundColor(Color.WHITE);
            return text;
        }
    }

    private View studentRow(JSONObject row) {
        LinearLayout container = new LinearLayout(this);
        container.setOrientation(LinearLayout.VERTICAL);
        container.setPadding(Ui.dp(this, 10), Ui.dp(this, 5), Ui.dp(this, 10), Ui.dp(this, 5));
        container.setBackgroundColor(Color.WHITE);
        LinearLayout main = new LinearLayout(this);
        main.setOrientation(LinearLayout.HORIZONTAL);
        TextView number = Ui.text(this, row.optString("student_id"));
        number.setTextSize(11);
        number.setSingleLine(true);
        number.setTextColor(0xff64748b);
        TextView name = Ui.text(this, row.optString("name"));
        name.setSingleLine(true);
        name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        TextView gender = Ui.text(this, row.optString("gender_display", chineseValue(row.optString("gender"))));
        gender.setSingleLine(true);
        gender.setGravity(Gravity.END);
        gender.setTextColor("male".equals(row.optString("gender")) ? getColor(R.color.primary) : 0xffdc3545);
        main.addView(number, new LinearLayout.LayoutParams(Ui.dp(this, 170), ViewGroup.LayoutParams.WRAP_CONTENT));
        main.addView(name, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        main.addView(gender, new LinearLayout.LayoutParams(Ui.dp(this, 36), ViewGroup.LayoutParams.WRAP_CONTENT));
        container.addView(main);
        String detail = emptyAsDash(row.optString("school_class_label")) + " · " +
                emptyAsDash(row.optString("class_position")) + " · " + emptyAsDash(row.optString("dormitory"));
        detail = detail.replace("— · ", "").replace(" · —", "");
        TextView sub = Ui.text(this, detail);
        sub.setTextSize(12);
        sub.setTextColor(0xff64748b);
        sub.setVisibility(View.GONE);
        container.addView(sub);
        return container;
    }

    private View studentHeader() {
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setPadding(Ui.dp(this, 10), Ui.dp(this, 7), Ui.dp(this, 10), Ui.dp(this, 7));
        header.setBackgroundColor(0xffe8f0fe);
        TextView number = Ui.text(this, "学号");
        TextView name = Ui.text(this, "姓名");
        TextView gender = Ui.text(this, "性别");
        number.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        gender.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        gender.setGravity(Gravity.END);
        header.addView(number, new LinearLayout.LayoutParams(Ui.dp(this, 170), ViewGroup.LayoutParams.WRAP_CONTENT));
        header.addView(name, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        header.addView(gender, new LinearLayout.LayoutParams(Ui.dp(this, 36), ViewGroup.LayoutParams.WRAP_CONTENT));
        return header;
    }

    private View todoRow(JSONObject row) {
        int priority = row.optInt("priority", 2);
        int accent = priority == 1 ? 0xffdc3545 : priority == 2 ? 0xfff57c00 : 0xff64748b;
        int fill = priority == 1 ? 0xfffff1f2 : priority == 2 ? 0xfffff7ed : 0xfff8fafc;
        LinearLayout container = new LinearLayout(this);
        container.setOrientation(LinearLayout.HORIZONTAL);
        container.setGravity(Gravity.CENTER_VERTICAL);
        container.setPadding(Ui.dp(this, 8), Ui.dp(this, 8), Ui.dp(this, 10), Ui.dp(this, 8));
        container.setBackground(Ui.rounded(this, fill, accent, 8));
        CheckBox check = new CheckBox(this);
        check.setFocusable(false);
        check.setChecked(row.optBoolean("is_completed"));
        check.setContentDescription(row.optBoolean("is_completed") ? "恢复为未完成" : "标记为已完成");
        check.setOnClickListener(view -> toggleTodo(row, check.isChecked()));
        container.addView(check);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        TextView titleView = Ui.text(this, row.optString("title"));
        titleView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        if (row.optBoolean("is_completed")) titleView.setPaintFlags(titleView.getPaintFlags() | Paint.STRIKE_THRU_TEXT_FLAG);
        body.addView(titleView);
        String meta = row.optString("priority_display", priority == 1 ? "高" : priority == 2 ? "中" : "低");
        String deadline = row.optString("deadline").replace('T', ' ');
        if (deadline.length() > 16) deadline = deadline.substring(0, 16);
        if (!deadline.isEmpty() && !"null".equals(deadline)) meta += " · " + deadline;
        String student = cleanStudentLabel(row.optString("student_label"));
        if (!student.isEmpty()) meta += "\n学生：" + student;
        TextView metaView = Ui.text(this, meta);
        metaView.setTextSize(12);
        metaView.setTextColor(accent);
        body.addView(metaView);
        container.addView(body, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        return container;
    }

    private void toggleTodo(JSONObject row, boolean completed) {
        JSONObject body = new JSONObject();
        try { body.put("is_completed", completed); } catch (Exception ignored) {}
        ApiClient.get(this).patch("resources/todos/" + row.optInt("id") + "/", body, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                NotificationScheduler.sync(ResourceActivity.this);
                load(search.getText().toString().trim());
            }
            @Override public void onError(String message, int statusCode) { toast(message); load(search.getText().toString().trim()); handleAuthError(statusCode); }
        });
    }

    private void edit(JSONObject record) {
        if (schema == null) {
            toast("数据结构尚未加载完成。");
            return;
        }
        JSONArray fields = schema.optJSONArray("fields");
        LinearLayout form = Ui.vertical(this);
        Map<String, View> inputs = new LinkedHashMap<>();
        Map<String, JSONObject> definitions = new LinkedHashMap<>();
        Map<String, TextView> labels = new LinkedHashMap<>();
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || field.optBoolean("read_only")) continue;
            String name = field.optString("name");
            if ("dorm_discipline".equals(resource) && "custom_content".equals(name)) continue;
            TextView label = Ui.text(this, field.optString("label") + (field.optBoolean("required") ? " *" : ""));
            label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            label.setTextColor(0xff475569);
            label.setPadding(0, Ui.dp(this, 10), 0, Ui.dp(this, 5));
            form.addView(label);
            View input = buildInput(field, record);
            form.addView(input);
            if (input instanceof CheckBox) label.setVisibility(View.GONE);
            if ("conversations".equals(resource) && "main_content".equals(name) && input instanceof EditText) {
                Button voice = Ui.outlineButton(this, "录音转文字");
                voice.setOnClickListener(view -> startVoiceRecognition((EditText) input));
                form.addView(voice);
            }
            inputs.put(name, input);
            definitions.put(name, field);
            labels.put(name, label);
        }
        applyConditionalFields(inputs, labels);
        if (record == null) bindDisciplineItemDefaults(inputs);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(form);
        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle(record == null ? "新增" + title : "编辑" + title)
                .setView(scroll)
                .setNegativeButton("取消", null)
                .setPositiveButton("保存", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            JSONObject body = collect(inputs, definitions);
            if (body == null) return;
            save(record, body, collectFiles(inputs), dialog);
        }));
        dialog.show();
    }

    private boolean supportsBatch() {
        return "attendance".equals(resource) || "homework_records".equals(resource) ||
                "classroom_discipline".equals(resource) || "dorm_discipline".equals(resource) ||
                "rewards".equals(resource) || "conversations".equals(resource) || "hygiene_checks".equals(resource);
    }

    private void batchEdit() {
        if ("dorm_discipline".equals(resource) || "hygiene_checks".equals(resource)) {
            roomStudentBatchEdit();
            return;
        }
        if (schema == null) {
            toast("数据结构尚未加载完成。");
            return;
        }
        JSONArray fields = schema.optJSONArray("fields");
        JSONObject studentField = null;
        LinearLayout form = Ui.vertical(this);
        Map<String, View> inputs = new LinkedHashMap<>();
        Map<String, JSONObject> definitions = new LinkedHashMap<>();
        Map<String, TextView> fieldLabels = new LinkedHashMap<>();
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || field.optBoolean("read_only")) continue;
            if ("student".equals(field.optString("name"))) {
                studentField = field;
                continue;
            }
            TextView fieldLabel = Ui.text(this, field.optString("label") + (field.optBoolean("required") ? " *" : ""));
            fieldLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            form.addView(fieldLabel);
            View input = buildInput(field, null);
            form.addView(input);
            if (input instanceof CheckBox) fieldLabel.setVisibility(View.GONE);
            if ("conversations".equals(resource) && "main_content".equals(field.optString("name")) && input instanceof EditText) {
                Button voice = Ui.outlineButton(this, "录音转文字");
                voice.setOnClickListener(view -> startVoiceRecognition((EditText) input));
                form.addView(voice);
            }
            inputs.put(field.optString("name"), input);
            definitions.put(field.optString("name"), field);
            fieldLabels.put(field.optString("name"), fieldLabel);
        }
        applyConditionalFields(inputs, fieldLabels);
        bindDisciplineItemDefaults(inputs);
        if (studentField == null || studentField.optJSONArray("options") == null) {
            toast("无法加载学生列表。");
            return;
        }
        JSONArray studentOptions = studentField.optJSONArray("options");
        String[] labels = new String[studentOptions.length()];
        boolean[] selected = new boolean[studentOptions.length()];
        for (int i = 0; i < studentOptions.length(); i++) labels[i] = cleanStudentLabel(studentOptions.optJSONObject(i).optString("label"));
        TextView selectedSummary = Ui.text(this, "尚未选择学生");
        selectedSummary.setTextColor(0xff64748b);
        Button selectStudents = Ui.outlineButton(this, "选择学生");
        selectStudents.setOnClickListener(view -> new AlertDialog.Builder(this)
                .setTitle("选择学生")
                .setMultiChoiceItems(labels, selected, (d, which, checked) -> {
                    selected[which] = checked;
                    int count = 0;
                    for (boolean value : selected) if (value) count++;
                    selectedSummary.setText(count == 0 ? "尚未选择学生" : "已选择 " + count + " 名学生");
                })
                .setNegativeButton("关闭", null)
                .show());
        form.addView(selectStudents, 0);
        form.addView(selectedSummary, 1);
        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("批量登记" + title)
                .setView(new ScrollView(this) {{ addView(form); }})
                .setNegativeButton("取消", null)
                .setPositiveButton("批量保存", null)
                .create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            JSONObject body = collect(inputs, definitions);
            if (body == null) return;
            JSONArray ids = new JSONArray();
            for (int i = 0; i < selected.length; i++) if (selected[i]) ids.put(studentOptions.optJSONObject(i).opt("value"));
            if (ids.length() == 0) {
                toast("请至少选择一名学生。");
                return;
            }
            try { body.put("student_ids", ids); } catch (Exception ignored2) {}
            ApiClient.Callback callback = new ApiClient.Callback() {
                @Override public void onSuccess(JSONObject response) {
                    dialog.dismiss();
                    toast("批量保存完成。");
                    load(search.getText().toString().trim());
                }
                @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
            };
            Map<String, Uri> files = collectFiles(inputs);
            if (files.isEmpty()) ApiClient.get(this).post("batch/" + resource + "/", body, callback);
            else ApiClient.get(this).upload("batch/" + resource + "/", body, files, callback);
        }));
        dialog.show();
    }

    private void roomStudentBatchEdit() {
        if (schema == null) {
            toast("数据结构尚未加载完成。");
            return;
        }
        JSONArray fields = schema.optJSONArray("fields");
        String roomName = "hygiene_checks".equals(resource) ? "room" : "dorm_room";
        JSONObject roomField = findField(fields, roomName);
        JSONObject studentField = findField(fields, "student");
        if (roomField == null || studentField == null || studentField.optJSONArray("options") == null) {
            toast("无法加载宿舍与学生列表。");
            return;
        }
        LinearLayout form = Ui.vertical(this);
        Map<String, View> inputs = new LinkedHashMap<>();
        Map<String, JSONObject> definitions = new LinkedHashMap<>();
        Map<String, TextView> fieldLabels = new LinkedHashMap<>();
        addBatchField(form, roomField, inputs, definitions, fieldLabels);

        TextView studentLabel = Ui.text(this, "选择学生 *");
        studentLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        TextView selectedSummary = Ui.text(this, "所有学生");
        selectedSummary.setTextColor(0xff64748b);
        Button selectStudents = Ui.outlineButton(this, "选择学生");
        form.addView(studentLabel);
        form.addView(selectStudents);
        form.addView(selectedSummary);
        boolean[] allStudents = {true};
        List<String> selectedIds = new ArrayList<>();
        JSONArray studentOptions = studentField.optJSONArray("options");

        Spinner[] hygieneItemInput = {null};
        Spinner[] hygieneSeverityInput = {null};
        EditText[] hygienePointsInput = {null};
        if ("hygiene_checks".equals(resource)) {
            JSONArray items = schema.optJSONArray("hygiene_items");
            if (items != null && items.length() > 0) {
                TextView heading = Ui.text(this, "卫生条目 *");
                heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                heading.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 4));
                form.addView(heading);
                hygieneItemInput[0] = new Spinner(this);
                Ui.styleSpinner(this, hygieneItemInput[0]);
                List<Option> hygieneItems = new ArrayList<>();
                for (int i = 0; i < items.length(); i++) {
                    JSONObject item = items.optJSONObject(i);
                    if (item == null) continue;
                    hygieneItems.add(new Option(String.valueOf(item.optInt("item_id", item.optInt("id"))), item.optString("name"), item));
                }
                hygieneItemInput[0].setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, hygieneItems));
                form.addView(hygieneItemInput[0]);
                TextView severityLabel = Ui.text(this, "严重程度");
                severityLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                form.addView(severityLabel);
                hygieneSeverityInput[0] = new Spinner(this);
                Ui.styleSpinner(this, hygieneSeverityInput[0]);
                hygieneSeverityInput[0].setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, new Option[]{
                        new Option("mild", "轻微"), new Option("moderate", "一般"),
                        new Option("serious", "严重"), new Option("critical", "非常严重")
                }));
                hygieneSeverityInput[0].setEnabled(false);
                form.addView(hygieneSeverityInput[0]);
                TextView pointsLabel = Ui.text(this, "分值（扣分）");
                pointsLabel.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
                form.addView(pointsLabel);
                hygienePointsInput[0] = new EditText(this);
                Ui.styleInput(this, hygienePointsInput[0]);
                hygienePointsInput[0].setInputType(InputType.TYPE_CLASS_NUMBER);
                form.addView(hygienePointsInput[0]);
                hygieneItemInput[0].setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
                    @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                        Option option = (Option) hygieneItemInput[0].getSelectedItem();
                        if (option == null || option.metadata == null) return;
                        setSpinnerValue(hygieneSeverityInput[0], option.metadata.optString("severity"));
                        hygienePointsInput[0].setText(String.valueOf(option.metadata.optInt("points_deducted")));
                    }
                    @Override public void onNothingSelected(AdapterView<?> parent) {}
                });
            }
        }
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || field.optBoolean("read_only") || roomName.equals(field.optString("name")) || "student".equals(field.optString("name"))) continue;
            if ("dorm_discipline".equals(resource) && "custom_content".equals(field.optString("name"))) continue;
            addBatchField(form, field, inputs, definitions, fieldLabels);
        }
        applyConditionalFields(inputs, fieldLabels);
        bindDisciplineItemDefaults(inputs);

        Spinner roomInput = (Spinner) inputs.get(roomName);
        Runnable resetStudents = () -> {
            allStudents[0] = true;
            selectedIds.clear();
            selectedSummary.setText("所有学生");
        };
        roomInput.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) { resetStudents.run(); }
            @Override public void onNothingSelected(AdapterView<?> parent) { resetStudents.run(); }
        });
        selectStudents.setOnClickListener(view -> {
            Option room = (Option) roomInput.getSelectedItem();
            List<Option> eligible = roomStudents(studentOptions, room == null ? "" : room.value);
            String[] choices = new String[eligible.size() + 1];
            boolean[] checked = new boolean[eligible.size() + 1];
            choices[0] = "所有学生";
            checked[0] = allStudents[0];
            for (int i = 0; i < eligible.size(); i++) {
                choices[i + 1] = eligible.get(i).label;
                checked[i + 1] = selectedIds.contains(eligible.get(i).value);
            }
            new AlertDialog.Builder(this).setTitle("选择该宿舍的学生")
                    .setMultiChoiceItems(choices, checked, (dialog, which, value) -> {
                        if (which == 0) {
                            allStudents[0] = value;
                            if (value) selectedIds.clear();
                            for (int i = 1; value && i < checked.length; i++) ((AlertDialog) dialog).getListView().setItemChecked(i, false);
                        } else {
                            allStudents[0] = false;
                            ((AlertDialog) dialog).getListView().setItemChecked(0, false);
                            String id = eligible.get(which - 1).value;
                            if (value && !selectedIds.contains(id)) selectedIds.add(id);
                            else if (!value) selectedIds.remove(id);
                        }
                        selectedSummary.setText(allStudents[0] ? "所有学生" : selectedIds.isEmpty() ? "尚未选择学生" : "已选择 " + selectedIds.size() + " 名学生");
                    }).setNegativeButton("完成", null).show();
        });

        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("hygiene_checks".equals(resource) ? "录入卫生检查" : "录入宿舍纪律")
                .setView(new ScrollView(this) {{ addView(form); }})
                .setNegativeButton("取消", null).setPositiveButton("保存", null).create();
        dialog.setOnShowListener(ignored -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
            JSONObject body = collect(inputs, definitions);
            if (body == null) return;
            Option room = (Option) roomInput.getSelectedItem();
            List<Option> eligible = roomStudents(studentOptions, room == null ? "" : room.value);
            JSONArray ids = new JSONArray();
            for (Option option : eligible) if (allStudents[0] || selectedIds.contains(option.value)) ids.put(option.value);
            if (ids.length() == 0) {
                toast("请选择至少一名学生（或该宿舍暂无已分配学生）。");
                return;
            }
            try {
                body.put("student_ids", ids);
                if ("hygiene_checks".equals(resource)) {
                    if (hygieneItemInput[0] == null || hygieneItemInput[0].getSelectedItem() == null) {
                        toast("暂无可用卫生条目，请先配置卫生项目。");
                        return;
                    }
                    body.put("student_mode", allStudents[0] ? "all" : "selected");
                    JSONArray scores = new JSONArray();
                    Option selectedItem = (Option) hygieneItemInput[0].getSelectedItem();
                    int deduction = Integer.parseInt(hygienePointsInput[0].getText().toString().trim());
                    int fullScore = selectedItem.metadata.optInt("full_score");
                    if (deduction < 0 || deduction > fullScore) {
                        toast("卫生扣分必须在 0 到 " + fullScore + " 之间。");
                        return;
                    }
                    JSONObject score = new JSONObject();
                    score.put("item_id", Integer.parseInt(selectedItem.value));
                    score.put("score", fullScore - deduction);
                    scores.put(score);
                    body.put("scores", scores);
                }
            } catch (Exception exception) {
                toast("卫生项目得分必须是非负整数。");
                return;
            }
            ApiClient.get(this).post("batch/" + resource + "/", body, new ApiClient.Callback() {
                @Override public void onSuccess(JSONObject response) { dialog.dismiss(); toast("保存完成。"); load(search.getText().toString().trim()); }
                @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
            });
        }));
        dialog.show();
    }

    private JSONObject findField(JSONArray fields, String name) {
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field != null && name.equals(field.optString("name"))) return field;
        }
        return null;
    }

    private void addBatchField(LinearLayout form, JSONObject field, Map<String, View> inputs,
                               Map<String, JSONObject> definitions, Map<String, TextView> labels) {
        String name = field.optString("name");
        TextView label = Ui.text(this, field.optString("label") + (field.optBoolean("required") ? " *" : ""));
        label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        form.addView(label);
        View input = buildInput(field, null);
        form.addView(input);
        if (input instanceof CheckBox) label.setVisibility(View.GONE);
        inputs.put(name, input);
        definitions.put(name, field);
        labels.put(name, label);
    }

    private List<Option> roomStudents(JSONArray options, String roomId) {
        List<Option> result = new ArrayList<>();
        for (int i = 0; options != null && i < options.length(); i++) {
            JSONObject row = options.optJSONObject(i);
            if (row == null) continue;
            if ("all".equals(String.valueOf(row.opt("value")))) continue;
            String optionRoom = String.valueOf(row.opt("room_id"));
            if (roomId.equals(optionRoom) || row.isNull("room_id") || !row.has("room_id"))
                result.add(new Option(String.valueOf(row.opt("value")), cleanStudentLabel(row.optString("label")), row));
        }
        return result;
    }

    private View buildInput(JSONObject field, JSONObject record) {
        String name = field.optString("name");
        String type = field.optString("type");
        Object current = record == null ? null : record.opt(name);
        if (record == null && "date".equals(type) && ("date".equals(name) || "assigned_date".equals(name) || "contact_date".equals(name)))
            current = java.time.LocalDate.now().toString();
        if (record == null && "time".equals(type) && "check_time".equals(name))
            current = java.time.LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"));
        if ("points_sign".equals(name) && record != null) {
            int points = record.optInt("points_deducted");
            current = "attendance".equals(resource) ? (points >= 0 ? "add" : "deduct") : (points < 0 ? "add" : "deduct");
        }
        if (("points_deducted".equals(name) || "rewards".equals(resource) && "points".equals(name)) && current instanceof Number)
            current = Math.abs(((Number) current).doubleValue());
        JSONArray options = field.optJSONArray("options");
        JSONArray choices = field.optJSONArray("choices");
        if ("boolean".equals(type)) {
            CheckBox box = new CheckBox(this);
            box.setText(field.optString("label"));
            box.setTextColor(getColor(R.color.text_primary));
            box.setChecked(current instanceof Boolean ? (Boolean) current : current == null ? "is_boarder".equals(name) || "is_active".equals(name) : Boolean.parseBoolean(String.valueOf(current)));
            return box;
        }
        if ("file".equals(type)) {
            FileButton button = new FileButton();
            button.setText(current == null || current == JSONObject.NULL || String.valueOf(current).isEmpty() ? "选择附件" : "保留现有附件（点此替换）");
            button.setTextColor(getColor(R.color.primary));
            button.setBackground(Ui.rounded(this, Color.WHITE, getColor(R.color.primary), 10));
            button.setOnClickListener(view -> {
                pendingFileButton = button;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.setType("*/*");
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                startActivityForResult(intent, 4201);
            });
            return button;
        }
        if ("relation".equals(type) || options != null || choices != null) {
            JSONArray values = options != null ? options : choices != null ? choices : new JSONArray();
            Spinner spinner = new Spinner(this);
            Ui.styleSpinner(this, spinner);
            List<Option> items = new ArrayList<>();
            if (values.length() == 0) items.add(new Option("", "暂无可选项"));
            else if (!field.optBoolean("required")) items.add(new Option("", "未选择"));
            for (int i = 0; i < values.length(); i++) {
                JSONObject option = values.optJSONObject(i);
                if (option != null) items.add(new Option(
                        String.valueOf(option.opt("value")),
                        "student".equals(name) ? cleanStudentLabel(option.optString("label")) : option.optString("label"),
                        option));
            }
            spinner.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, items));
            String selected = current == null || current == JSONObject.NULL ? "" : String.valueOf(current);
            for (int i = 0; i < items.size(); i++) if (items.get(i).value.equals(selected)) spinner.setSelection(i);
            return spinner;
        }
        if ("date".equals(type) || "datetime".equals(type) || "time".equals(type))
            return Ui.temporalInput(this, type, current == null || current == JSONObject.NULL ? "" : String.valueOf(current));
        EditText input = new EditText(this);
        Ui.styleInput(this, input);
        input.setHint(hintFor(type));
        input.setText(current == null || current == JSONObject.NULL ? "" : String.valueOf(current));
        if ("number".equals(type)) input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL |
                (field.optDouble("min", -1) >= 0 || "attendance".equals(resource) && "points_deducted".equals(name) ? 0 : InputType.TYPE_NUMBER_FLAG_SIGNED));
        else if ("multiline".equals(type)) {
            input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
            input.setMinLines(3);
        } else input.setInputType(InputType.TYPE_CLASS_TEXT);
        return input;
    }

    private void applyConditionalFields(Map<String, View> inputs, Map<String, TextView> labels) {
        bindVisibility(inputs, labels, "is_boarder", "dormitory", "bed_number");
        bindVisibility(inputs, labels, "needs_follow_up", "follow_up_date");
    }

    private void bindDisciplineItemDefaults(Map<String, View> inputs) {
        if (!("classroom_discipline".equals(resource) || "dorm_discipline".equals(resource))) return;
        if (!(inputs.get("item") instanceof Spinner)) return;
        Spinner item = (Spinner) inputs.get("item");
        item.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override public void onItemSelected(AdapterView<?> parent, View view, int position, long id) {
                Option option = (Option) item.getSelectedItem();
                if (option == null || option.metadata == null) return;
                setSpinnerValue(inputs.get("severity"), option.metadata.optString("severity"));
                setSpinnerValue(inputs.get("points_sign"), option.metadata.optString("points_sign"));
                if (inputs.get("points_deducted") instanceof EditText && option.metadata.has("points_deducted"))
                    ((EditText) inputs.get("points_deducted")).setText(String.valueOf(option.metadata.optInt("points_deducted")));
            }
            @Override public void onNothingSelected(AdapterView<?> parent) {}
        });
    }

    private void setSpinnerValue(View view, String value) {
        if (!(view instanceof Spinner) || value.isEmpty()) return;
        Spinner spinner = (Spinner) view;
        for (int i = 0; i < spinner.getCount(); i++)
            if (((Option) spinner.getItemAtPosition(i)).value.equals(value)) spinner.setSelection(i);
    }

    private void bindVisibility(Map<String, View> inputs, Map<String, TextView> labels, String controller, String... targets) {
        View value = inputs.get(controller);
        if (!(value instanceof CheckBox)) return;
        CheckBox box = (CheckBox) value;
        Runnable update = () -> {
            int visibility = box.isChecked() ? View.VISIBLE : View.GONE;
            for (String target : targets) {
                if (inputs.get(target) != null) inputs.get(target).setVisibility(visibility);
                if (labels.get(target) != null) labels.get(target).setVisibility(visibility);
            }
        };
        box.setOnCheckedChangeListener((button, checked) -> update.run());
        update.run();
    }

    private String hintFor(String type) {
        if ("date".equals(type)) return "YYYY-MM-DD";
        if ("datetime".equals(type)) return "YYYY-MM-DDTHH:MM:SS+08:00";
        if ("time".equals(type)) return "HH:MM";
        if ("file".equals(type)) return "选择附件";
        return "请输入";
    }

    private JSONObject collect(Map<String, View> inputs, Map<String, JSONObject> definitions) {
        JSONObject body = new JSONObject();
        try {
            for (Map.Entry<String, View> item : inputs.entrySet()) {
                JSONObject definition = definitions.get(item.getKey());
                View view = item.getValue();
                Object value;
                if (view instanceof CheckBox) value = ((CheckBox) view).isChecked();
                else if (view instanceof Spinner) value = ((Option) ((Spinner) view).getSelectedItem()).value;
                else if (view instanceof FileButton) continue;
                else value = ((EditText) view).getText().toString().trim();
                if (definition.optBoolean("required") && String.valueOf(value).isEmpty()) {
                    toast(definition.optString("label") + "不能为空。");
                    return null;
                }
                if ("number".equals(definition.optString("type")) && !String.valueOf(value).isEmpty()) {
                    String number = String.valueOf(value);
                    value = number.contains(".") ? Double.parseDouble(number) : Long.parseLong(number);
                    if (definition.has("min") && ((Number) value).doubleValue() < definition.optDouble("min")) {
                        toast(definition.optString("label") + "不能小于 " + definition.optString("min") + "。");
                        return null;
                    }
                }
                if ("datetime".equals(definition.optString("type")) && !String.valueOf(value).isEmpty()) {
                    value = LocalDateTime.parse(String.valueOf(value), DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm"))
                            .atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
                }
                if ("time".equals(definition.optString("type")) && String.valueOf(value).length() == 5)
                    value = value + ":00";
                if (!"points_sign".equals(item.getKey())) body.put(item.getKey(), value);
            }
            if (inputs.containsKey("points_sign") && body.has("points_deducted")) {
                String sign = ((Option) ((Spinner) inputs.get("points_sign")).getSelectedItem()).value;
                int points = Math.abs(body.optInt("points_deducted"));
                body.put("points_deducted", "attendance".equals(resource) ? ("add".equals(sign) ? points : -points) : ("add".equals(sign) ? -points : points));
            }
            return body;
        } catch (Exception exception) {
            toast("表单内容格式有误：" + exception.getMessage());
            return null;
        }
    }

    private Map<String, Uri> collectFiles(Map<String, View> inputs) {
        Map<String, Uri> files = new LinkedHashMap<>();
        for (Map.Entry<String, View> item : inputs.entrySet()) {
            if (item.getValue() instanceof FileButton && ((FileButton) item.getValue()).uri != null)
                files.put(item.getKey(), ((FileButton) item.getValue()).uri);
        }
        return files;
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == 4201 && resultCode == RESULT_OK && data != null && data.getData() != null && pendingFileButton != null) {
            pendingFileButton.uri = data.getData();
            pendingFileButton.setText("已选择附件");
        }
        if (requestCode == 4202 && resultCode == RESULT_OK && data != null && pendingVoiceInput != null) {
            ArrayList<String> results = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS);
            if (results != null && !results.isEmpty()) {
                String current = pendingVoiceInput.getText().toString().trim();
                pendingVoiceInput.setText(current.isEmpty() ? results.get(0) : current + "\n" + results.get(0));
                pendingVoiceInput.setSelection(pendingVoiceInput.length());
            }
        }
        if (requestCode == 4204 && resultCode == RESULT_OK && data != null && data.getData() != null && pendingHygieneCheckId > 0) {
            JSONObject fields = new JSONObject();
            Map<String, Uri> files = new LinkedHashMap<>();
            try { fields.put("check_record", pendingHygieneCheckId); } catch (Exception ignored) {}
            files.put("image", data.getData());
            ApiClient.get(this).upload("resources/hygiene_photos/", fields, files, new ApiClient.Callback() {
                @Override public void onSuccess(JSONObject response) { toast("现场照片已添加，可继续添加其他照片。"); }
                @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
            });
        }
    }

    private void startVoiceRecognition(EditText input) {
        pendingVoiceInput = input;
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{Manifest.permission.RECORD_AUDIO}, 4203);
            return;
        }
        launchVoiceRecognition();
    }

    private void launchVoiceRecognition() {
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "zh-CN");
        intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "请说出谈话内容");
        try { startActivityForResult(intent, 4202); }
        catch (ActivityNotFoundException exception) { toast("当前手机没有可用的语音识别服务。"); }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == 4203 && grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED)
            launchVoiceRecognition();
    }

    private void save(JSONObject record, JSONObject body, Map<String, Uri> files, AlertDialog dialog) {
        ApiClient.Callback callback = new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                dialog.dismiss();
                toast("保存成功。");
                if ("todos".equals(resource)) NotificationScheduler.sync(ResourceActivity.this);
                load(search.getText().toString().trim());
            }
            @Override public void onError(String message, int statusCode) {
                toast(message);
                handleAuthError(statusCode);
            }
        };
        if (!files.isEmpty()) ApiClient.get(this).upload("resources/" + resource + "/" + (record == null ? "" : record.optInt("id") + "/"), body, files, callback);
        else if (record == null) ApiClient.get(this).post("resources/" + resource + "/", body, callback);
        else ApiClient.get(this).patch("resources/" + resource + "/" + record.optInt("id") + "/", body, callback);
    }

    private void confirmDelete(JSONObject record) {
        if (record == null || schema == null || !schema.optBoolean("allow_delete")) {
            toast("该记录不允许删除。");
            return;
        }
        EditText confirmation = new EditText(this);
        boolean classDelete = "classes".equals(resource);
        confirmation.setHint(classDelete ? "输入完整班级名称确认" : "可直接确认");
        new AlertDialog.Builder(this)
                .setTitle("确认删除")
                .setMessage(classDelete ? "删除班级会同时删除该班全部业务数据，此操作不可撤销。" : "将按网站现有规则删除或移入回收站。")
                .setView(confirmation)
                .setNegativeButton("取消", null)
                .setPositiveButton("删除", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("confirmation", confirmation.getText().toString().trim()); } catch (Exception ignored) {}
                    ApiClient.get(this).delete("resources/" + resource + "/" + record.optInt("id") + "/", body, new ApiClient.Callback() {
                        @Override public void onSuccess(JSONObject response) { toast("删除完成。"); if ("todos".equals(resource)) NotificationScheduler.sync(ResourceActivity.this); load(search.getText().toString().trim()); }
                        @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
                    });
                }).show();
    }

    private void hygieneActions(JSONObject record) {
        new AlertDialog.Builder(this).setTitle(record.optString("display"))
                .setItems(new String[]{"查看详情", "编辑检查信息", "填写各项目得分", "添加现场照片"}, (dialog, which) -> {
                    if (which == 0) showDetail(record);
                    else if (which == 1) edit(record);
                    else if (which == 2) editHygieneScores(record.optInt("id"));
                    else chooseHygienePhoto(record.optInt("id"));
                }).show();
    }

    private void chooseHygienePhoto(int checkId) {
        pendingHygieneCheckId = checkId;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.setType("image/*");
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(intent, 4204);
    }

    private void editHygieneScores(int id) {
        ApiClient.get(this).get("dormitory/hygiene/" + id + "/scores/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                JSONArray items = data == null ? null : data.optJSONArray("items");
                LinearLayout form = Ui.vertical(ResourceActivity.this);
                Map<Integer, EditText[]> inputs = new LinkedHashMap<>();
                for (int i = 0; items != null && i < items.length(); i++) {
                    JSONObject item = items.optJSONObject(i);
                    form.addView(Ui.text(ResourceActivity.this, item.optString("name") + "（满分 " + item.optInt("full_score") + "）"));
                    EditText score = new EditText(ResourceActivity.this);
                    Ui.styleInput(ResourceActivity.this, score);
                    score.setHint("得分");
                    score.setInputType(InputType.TYPE_CLASS_NUMBER);
                    if (!item.isNull("score")) score.setText(String.valueOf(item.optInt("score")));
                    EditText reason = new EditText(ResourceActivity.this);
                    Ui.styleInput(ResourceActivity.this, reason);
                    reason.setHint("扣分原因");
                    reason.setText(item.optString("deduction_reason"));
                    form.addView(score); form.addView(reason);
                    inputs.put(item.optInt("item_id"), new EditText[]{score, reason});
                }
                ScrollView scroll = new ScrollView(ResourceActivity.this);
                scroll.addView(form);
                AlertDialog editor = new AlertDialog.Builder(ResourceActivity.this)
                        .setTitle("卫生项目评分").setView(scroll)
                        .setNegativeButton("取消", null).setPositiveButton("保存", null).create();
                editor.setOnShowListener(ignored -> editor.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(view -> {
                    JSONArray scores = new JSONArray();
                    try {
                        for (Map.Entry<Integer, EditText[]> item : inputs.entrySet()) {
                            if (item.getValue()[0].getText().toString().trim().isEmpty()) continue;
                            JSONObject value = new JSONObject();
                            value.put("item_id", item.getKey());
                            value.put("score", Integer.parseInt(item.getValue()[0].getText().toString()));
                            value.put("deduction_reason", item.getValue()[1].getText().toString());
                            scores.put(value);
                        }
                        JSONObject body = new JSONObject(); body.put("scores", scores);
                        ApiClient.get(ResourceActivity.this).put("dormitory/hygiene/" + id + "/scores/", body, new ApiClient.Callback() {
                            @Override public void onSuccess(JSONObject result) { editor.dismiss(); toast("项目得分已保存并重算总分。"); load(search.getText().toString().trim()); }
                            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
                        });
                    } catch (Exception exception) { toast("得分必须是整数。"); }
                }));
                editor.show();
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private static final class Option {
        final String value;
        final String label;
        final JSONObject metadata;
        Option(String value, String label) { this(value, label, null); }
        Option(String value, String label, JSONObject metadata) { this.value = value; this.label = label; this.metadata = metadata; }
        @Override public String toString() { return label; }
    }

    private final class FileButton extends AppCompatButton {
        Uri uri;
        FileButton() { super(ResourceActivity.this); }
    }
}
