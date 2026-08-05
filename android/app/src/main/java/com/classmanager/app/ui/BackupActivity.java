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
import java.util.List;

public class BackupActivity extends BaseActivity {
    private static final int CREATE_FILE = 4102;
    private JSONArray rows = new JSONArray();
    private ListView list;
    private int pendingDownloadId;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("备份管理", true);
        LinearLayout root = Ui.vertical(this);
        Button create = Ui.button(this, "立即创建完整备份");
        create.setOnClickListener(view -> createBackup());
        root.addView(create);
        list = new ListView(this);
        root.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        list.setOnItemClickListener((parent, view, position, id) -> actions(rows.optJSONObject(position)));
        show(root);
        load();
    }

    private void load() {
        list.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, new String[]{"正在加载…"}));
        ApiClient.get(this).get("backups/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                rows = response.optJSONArray("data");
                if (rows == null) rows = new JSONArray();
                List<String> labels = new ArrayList<>();
                for (int i = 0; i < rows.length(); i++) {
                    JSONObject row = rows.optJSONObject(i);
                    labels.add(row.optString("created_at").replace('T', ' ') + "\n" +
                            row.optString("backup_type_display") + " · " + row.optString("status_display") +
                            " · " + size(row.optLong("file_size")));
                }
                if (labels.isEmpty()) labels.add("暂无备份");
                list.setAdapter(new ArrayAdapter<>(BackupActivity.this, android.R.layout.simple_list_item_1, labels));
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void createBackup() {
        new AlertDialog.Builder(this).setTitle("创建完整备份")
                .setMessage("备份包含数据库和上传附件，创建过程可能需要一些时间。")
                .setNegativeButton("取消", null)
                .setPositiveButton("创建", (dialog, which) -> ApiClient.get(this).post("backups/", new JSONObject(), new ApiClient.Callback() {
                    @Override public void onSuccess(JSONObject response) { toast("备份创建成功。"); load(); }
                    @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
                })).show();
    }

    private void actions(JSONObject row) {
        if (row == null) return;
        List<String> actions = new ArrayList<>();
        actions.add("校验备份");
        actions.add("恢复此备份");
        actions.add("删除备份");
        new AlertDialog.Builder(this)
                .setTitle(row.optString("backup_type_display") + " · " + row.optString("created_at"))
                .setItems(actions.toArray(new String[0]), (dialog, which) -> {
                    String action = actions.get(which);
                    if (action.startsWith("校验")) verify(row.optInt("id"));
                    else if (action.startsWith("恢复")) restore(row.optInt("id"));
                    else delete(row.optInt("id"));
                }).show();
    }

    private void chooseDownload(int id) {
        pendingDownloadId = id;
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.setType("application/zip");
        intent.putExtra(Intent.EXTRA_TITLE, "class-manager-backup-" + id + ".zip");
        startActivityForResult(intent, CREATE_FILE);
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == CREATE_FILE && resultCode == RESULT_OK && data != null && data.getData() != null) {
            Uri uri = data.getData();
            ApiClient.get(this).download("backups/" + pendingDownloadId + "/download/", uri, new ApiClient.Callback() {
                @Override public void onSuccess(JSONObject response) { toast("备份已保存到手机。"); load(); }
                @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
            });
        }
    }

    private void verify(int id) {
        ApiClient.get(this).get("backups/" + id + "/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                toast(data == null ? "校验完成" : data.optString("verification_message"));
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void restore(int id) {
        EditText password = new EditText(this);
        Ui.styleInput(this, password);
        password.setHint("管理员密码");
        password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        new AlertDialog.Builder(this).setTitle("确认恢复备份")
                .setMessage("系统会先自动创建恢复前安全备份，再替换当前数据库和附件。")
                .setView(password).setNegativeButton("取消", null)
                .setPositiveButton("恢复", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("password", password.getText().toString()); } catch (Exception ignored) {}
                    ApiClient.get(this).post("backups/" + id + "/restore/", body, new ApiClient.Callback() {
                        @Override public void onSuccess(JSONObject response) { toast("恢复成功。"); load(); }
                        @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
                    });
                }).show();
    }

    private void delete(int id) {
        new AlertDialog.Builder(this).setTitle("删除备份")
                .setMessage("将同时删除服务器上的备份文件，此操作不可撤销。")
                .setNegativeButton("取消", null)
                .setPositiveButton("删除", (dialog, which) -> ApiClient.get(this).delete("backups/" + id + "/", new JSONObject(), new ApiClient.Callback() {
                    @Override public void onSuccess(JSONObject response) { toast("备份已删除。"); load(); }
                    @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
                })).show();
    }

    private String size(long bytes) {
        if (bytes <= 0) return "--";
        if (bytes < 1024 * 1024) return String.format(java.util.Locale.CHINA, "%.1f KB", bytes / 1024d);
        return String.format(java.util.Locale.CHINA, "%.1f MB", bytes / 1024d / 1024d);
    }
}
