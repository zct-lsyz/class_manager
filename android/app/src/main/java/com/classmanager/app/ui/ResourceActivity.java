package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import androidx.appcompat.widget.AppCompatButton;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;
import com.classmanager.app.notification.NotificationScheduler;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class ResourceActivity extends BaseActivity {
    private String resource;
    private String title;
    private LinearLayout root;
    private EditText search;
    private ListView list;
    private JSONArray records = new JSONArray();
    private JSONObject schema;
    private FileButton pendingFileButton;

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
        controls.addView(search, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        Button searchButton = new Button(this);
        searchButton.setText("查询");
        searchButton.setOnClickListener(view -> load(search.getText().toString().trim()));
        controls.addView(searchButton);
        Button add = new Button(this);
        add.setText("新增");
        add.setOnClickListener(view -> edit(null));
        controls.addView(add);
        if (supportsBatch()) {
            Button batch = new Button(this);
            batch.setText("批量");
            batch.setOnClickListener(view -> batchEdit());
            controls.addView(batch);
        }
        root.addView(controls);
        list = new ListView(this);
        list.setDivider(new android.graphics.drawable.ColorDrawable(android.graphics.Color.TRANSPARENT));
        list.setDividerHeight(Ui.dp(this, 8));
        list.setPadding(0, Ui.dp(this, 8), 0, Ui.dp(this, 16));
        list.setClipToPadding(false);
        root.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        list.setOnItemClickListener((parent, view, position, id) -> {
            JSONObject record = records.optJSONObject(position);
            if ("hygiene_checks".equals(resource)) hygieneActions(record);
            else edit(record);
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
                List<String> labels = new ArrayList<>();
                for (int i = 0; i < records.length(); i++) labels.add(rowLabel(records.optJSONObject(i)));
                if (labels.isEmpty()) labels.add("暂无记录，点击右上方“新增”开始录入。");
                list.setAdapter(new ArrayAdapter<String>(ResourceActivity.this, android.R.layout.simple_list_item_2, android.R.id.text1, labels) {
                    @Override public View getView(int position, View convertView, ViewGroup parent) {
                        View view = super.getView(position, convertView, parent);
                        TextView text = view.findViewById(android.R.id.text1);
                        text.setSingleLine(false);
                        text.setPadding(Ui.dp(ResourceActivity.this, 16), Ui.dp(ResourceActivity.this, 12), Ui.dp(ResourceActivity.this, 16), Ui.dp(ResourceActivity.this, 12));
                        text.setTextColor(getColor(R.color.text_primary));
                        text.setTextSize(15);
                        text.setBackgroundResource(R.drawable.bg_card);
                        return view;
                    }
                });
            }
            @Override public void onError(String message, int statusCode) {
                list.setAdapter(new ArrayAdapter<>(ResourceActivity.this, android.R.layout.simple_list_item_1, new String[]{"加载失败：" + message}));
                handleAuthError(statusCode);
            }
        });
    }

    private String rowLabel(JSONObject row) {
        if (row == null) return "";
        StringBuilder result = new StringBuilder(row.optString("display", "记录 #" + row.optInt("id")));
        JSONArray fields = schema == null ? null : schema.optJSONArray("fields");
        if (fields == null) return result.toString();
        int appended = 0;
        for (int i = 0; i < fields.length() && appended < 3; i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null) continue;
            String name = field.optString("name");
            String value = row.optString(name + "_display", row.optString(name + "_label", row.optString(name, "")));
            if (value.isEmpty() || value.equals("null") || value.equals(row.optString("display"))) continue;
            result.append(appended == 0 ? "\n" : " · ").append(field.optString("label")).append("：").append(value);
            appended++;
        }
        return result.toString();
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
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || field.optBoolean("read_only")) continue;
            String name = field.optString("name");
            TextView label = Ui.text(this, field.optString("label") + (field.optBoolean("required") ? " *" : ""));
            form.addView(label);
            View input = buildInput(field, record);
            form.addView(input);
            inputs.put(name, input);
            definitions.put(name, field);
        }
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
                "rewards".equals(resource) || "conversations".equals(resource) ||
                "home_school_contacts".equals(resource) || "concerns".equals(resource) ||
                "scores".equals(resource);
    }

    private void batchEdit() {
        if (schema == null) {
            toast("数据结构尚未加载完成。");
            return;
        }
        JSONArray fields = schema.optJSONArray("fields");
        JSONObject studentField = null;
        LinearLayout form = Ui.vertical(this);
        Map<String, View> inputs = new LinkedHashMap<>();
        Map<String, JSONObject> definitions = new LinkedHashMap<>();
        for (int i = 0; fields != null && i < fields.length(); i++) {
            JSONObject field = fields.optJSONObject(i);
            if (field == null || field.optBoolean("read_only")) continue;
            if ("student".equals(field.optString("name"))) {
                studentField = field;
                continue;
            }
            form.addView(Ui.text(this, field.optString("label") + (field.optBoolean("required") ? " *" : "")));
            View input = buildInput(field, null);
            form.addView(input);
            inputs.put(field.optString("name"), input);
            definitions.put(field.optString("name"), field);
        }
        if (studentField == null || studentField.optJSONArray("options") == null) {
            toast("无法加载学生列表。");
            return;
        }
        JSONArray studentOptions = studentField.optJSONArray("options");
        String[] labels = new String[studentOptions.length()];
        boolean[] selected = new boolean[studentOptions.length()];
        for (int i = 0; i < studentOptions.length(); i++) labels[i] = studentOptions.optJSONObject(i).optString("label");
        final JSONObject finalStudentField = studentField;
        AlertDialog dialog = new AlertDialog.Builder(this)
                .setTitle("选择学生")
                .setMultiChoiceItems(labels, selected, (d, which, checked) -> selected[which] = checked)
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
            ApiClient.get(this).post("batch/" + resource + "/", body, new ApiClient.Callback() {
                @Override public void onSuccess(JSONObject response) {
                    dialog.dismiss();
                    toast("批量保存完成。");
                    load(search.getText().toString().trim());
                }
                @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
            });
        }));
        dialog.show();
    }

    private View buildInput(JSONObject field, JSONObject record) {
        String name = field.optString("name");
        String type = field.optString("type");
        Object current = record == null ? null : record.opt(name);
        JSONArray options = field.optJSONArray("options");
        JSONArray choices = field.optJSONArray("choices");
        if ("boolean".equals(type)) {
            CheckBox box = new CheckBox(this);
            box.setChecked(current instanceof Boolean ? (Boolean) current : Boolean.parseBoolean(String.valueOf(current)));
            return box;
        }
        if ("file".equals(type)) {
            FileButton button = new FileButton();
            button.setText(current == null || current == JSONObject.NULL || String.valueOf(current).isEmpty() ? "选择附件" : "保留现有附件（点此替换）");
            button.setOnClickListener(view -> {
                pendingFileButton = button;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.setType("*/*");
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                startActivityForResult(intent, 4201);
            });
            return button;
        }
        if ((options != null && options.length() > 0) || (choices != null && choices.length() > 0)) {
            JSONArray values = options != null && options.length() > 0 ? options : choices;
            Spinner spinner = new Spinner(this);
            List<Option> items = new ArrayList<>();
            if (!field.optBoolean("required")) items.add(new Option("", "未选择"));
            for (int i = 0; i < values.length(); i++) {
                JSONObject option = values.optJSONObject(i);
                if (option != null) items.add(new Option(String.valueOf(option.opt("value")), option.optString("label")));
            }
            spinner.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, items));
            String selected = current == null || current == JSONObject.NULL ? "" : String.valueOf(current);
            for (int i = 0; i < items.size(); i++) if (items.get(i).value.equals(selected)) spinner.setSelection(i);
            return spinner;
        }
        EditText input = new EditText(this);
        input.setHint(hintFor(type));
        input.setText(current == null || current == JSONObject.NULL ? "" : String.valueOf(current));
        if ("number".equals(type)) input.setInputType(InputType.TYPE_CLASS_NUMBER | InputType.TYPE_NUMBER_FLAG_DECIMAL | InputType.TYPE_NUMBER_FLAG_SIGNED);
        else if ("multiline".equals(type)) {
            input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
            input.setMinLines(3);
        } else input.setInputType(InputType.TYPE_CLASS_TEXT);
        return input;
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
                }
                body.put(item.getKey(), value);
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
                .setItems(new String[]{"编辑检查信息", "填写各项目得分"}, (dialog, which) -> {
                    if (which == 0) edit(record);
                    else editHygieneScores(record.optInt("id"));
                }).show();
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
                    score.setHint("得分");
                    score.setInputType(InputType.TYPE_CLASS_NUMBER);
                    if (!item.isNull("score")) score.setText(String.valueOf(item.optInt("score")));
                    EditText reason = new EditText(ResourceActivity.this);
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
        Option(String value, String label) { this.value = value; this.label = label; }
        @Override public String toString() { return label; }
    }

    private final class FileButton extends AppCompatButton {
        Uri uri;
        FileButton() { super(ResourceActivity.this); }
    }
}
