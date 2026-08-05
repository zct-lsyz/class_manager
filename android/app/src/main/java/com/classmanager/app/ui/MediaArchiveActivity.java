package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;

import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class MediaArchiveActivity extends BaseActivity {
    private static final int IMPORT_ARCHIVE = 4301;
    private static final int DOWNLOAD_ARCHIVE = 4302;
    private JSONArray exports = new JSONArray();
    private ListView list;
    private int pendingDownloadId;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("媒体归档与存储", true);
        LinearLayout root = Ui.vertical(this);
        Button create = Ui.button(this, "创建媒体归档");
        create.setOnClickListener(view -> createArchive());
        root.addView(create);
        Button upload = Ui.button(this, "导入媒体归档");
        upload.setOnClickListener(view -> chooseImport());
        root.addView(upload);
        Button check = Ui.button(this, "立即检查存储并发送提醒");
        check.setOnClickListener(view -> ApiClient.get(this).post("storage/check/", new JSONObject(), callback("存储检查已完成。")));
        root.addView(check);
        list = new ListView(this);
        root.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        list.setOnItemClickListener((parent, view, position, id) -> archiveActions(exports.optJSONObject(position)));
        show(root);
        load();
    }

    private void load() {
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, new String[]{"正在加载…"}));
        ApiClient.get(this).get("media-archives/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                exports = data == null || data.optJSONArray("exports") == null ? new JSONArray() : data.optJSONArray("exports");
                List<String> labels = new ArrayList<>();
                for (int i = 0; i < exports.length(); i++) {
                    JSONObject row = exports.optJSONObject(i);
                    labels.add(row.optString("created_at").replace('T', ' ') + "\n模块：" + row.optJSONArray("modules") + " · " + row.optInt("record_count") + " 条" + (row.isNull("cleared_at") ? "" : " · 已清除服务器媒体"));
                }
                if (labels.isEmpty()) labels.add("暂无媒体归档");
                list.setAdapter(new ArrayAdapter<>(MediaArchiveActivity.this, android.R.layout.simple_list_item_1, labels));
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void createArchive() {
        String[] labels = {"宿舍卫生与纪律", "奖惩附件", "班级活动附件"};
        String[] values = {"dormitory", "rewards", "activities"};
        boolean[] selected = {true, true, false};
        new AlertDialog.Builder(this).setTitle("选择归档模块")
                .setMultiChoiceItems(labels, selected, (dialog, which, checked) -> selected[which] = checked)
                .setNegativeButton("取消", null)
                .setPositiveButton("创建", (dialog, which) -> {
                    JSONArray modules = new JSONArray();
                    for (int i = 0; i < selected.length; i++) if (selected[i]) modules.put(values[i]);
                    JSONObject body = new JSONObject();
                    try { body.put("modules", modules); } catch (Exception ignored) {}
                    ApiClient.get(this).post("media-archives/", body, callback("媒体归档创建成功。"));
                }).show();
    }

    private void archiveActions(JSONObject row) {
        if (row == null) return;
        List<String> actions = new ArrayList<>();
        actions.add("下载归档到手机");
        if (row.isNull("cleared_at")) actions.add("清除已归档的服务器媒体");
        new AlertDialog.Builder(this).setTitle("媒体归档")
                .setItems(actions.toArray(new String[0]), (dialog, which) -> {
                    if (which == 0) chooseDownload(row.optInt("id"));
                    else clearArchive(row.optInt("id"));
                }).show();
    }

    private void clearArchive(int id) {
        LinearLayout form = Ui.vertical(this);
        EditText confirmation = new EditText(this); confirmation.setHint("输入：确认清除");
        EditText password = new EditText(this); password.setHint("管理员密码");
        Ui.styleInput(this, confirmation); Ui.styleInput(this, password);
        password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        form.addView(confirmation); form.addView(password);
        new AlertDialog.Builder(this).setTitle("清除服务器媒体")
                .setMessage("仅清除已写入此归档包的媒体和关联记录，请先下载并妥善保存归档。")
                .setView(form).setNegativeButton("取消", null)
                .setPositiveButton("清除", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("confirmation", confirmation.getText().toString()); body.put("password", password.getText().toString()); } catch (Exception ignored) {}
                    ApiClient.get(this).post("media-archives/" + id + "/clear/", body, callback("已清除归档对应的服务器媒体。"));
                }).show();
    }

    private void chooseImport() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.setType("application/zip");
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        startActivityForResult(intent, IMPORT_ARCHIVE);
    }

    private void chooseDownload(int id) {
        pendingDownloadId = id;
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.setType("application/zip");
        intent.putExtra(Intent.EXTRA_TITLE, "class-manager-media-" + id + ".zip");
        startActivityForResult(intent, DOWNLOAD_ARCHIVE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        if (requestCode == IMPORT_ARCHIVE) {
            Map<String, Uri> files = new LinkedHashMap<>(); files.put("archives", uri);
            ApiClient.get(this).upload("media-archives/import/", new JSONObject(), files, callback("媒体归档导入成功。"));
        } else if (requestCode == DOWNLOAD_ARCHIVE) {
            ApiClient.get(this).download("media-archives/" + pendingDownloadId + "/download/", uri, callback("媒体归档已保存到手机。"));
        }
    }

    private ApiClient.Callback callback(String message) {
        return new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) { toast(message); load(); }
            @Override public void onError(String value, int statusCode) { toast(value); handleAuthError(statusCode); }
        };
    }
}
