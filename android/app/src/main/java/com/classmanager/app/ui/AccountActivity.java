package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.text.InputType;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;

import com.classmanager.app.data.ApiClient;
import com.classmanager.app.data.SessionStore;
import com.classmanager.app.notification.NotificationScheduler;
import com.classmanager.app.notification.TodoSyncManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class AccountActivity extends BaseActivity {
    private LinearLayout profile;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("账户与安全", true);
        ScrollView scroll = new ScrollView(this);
        LinearLayout root = Ui.vertical(this);
        profile = new LinearLayout(this);
        profile.setOrientation(LinearLayout.VERTICAL);
        root.addView(profile);
        Button edit = Ui.button(this, "修改用户名和邮箱");
        edit.setOnClickListener(view -> editProfile());
        root.addView(edit);
        Button password = Ui.button(this, "修改密码");
        password.setOnClickListener(view -> changePassword());
        root.addView(password);
        Button devices = Ui.button(this, "受信任设备管理");
        devices.setOnClickListener(view -> devices());
        root.addView(devices);
        root.addView(Ui.text(this, "后台每约 15 分钟自动同步网站待办；同步成功后由安卓系统通知在到期时提醒。"));
        Button sync = Ui.button(this, "立即同步待办提醒");
        sync.setOnClickListener(view -> NotificationScheduler.sync(this, retry -> runOnUiThread(() -> toast(retry ? "同步失败，后台将自动重试。" : "待办提醒已同步。"))));
        root.addView(sync);
        Button alarm = Ui.button(this, "允许准时显示待办通知");
        alarm.setOnClickListener(view -> {
            if (Build.VERSION.SDK_INT >= 31) startActivity(new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:" + getPackageName())));
            else toast("当前系统已支持精确提醒。");
        });
        root.addView(alarm);
        Button logout = Ui.button(this, "退出登录");
        logout.setOnClickListener(view -> logout());
        root.addView(logout);
        Button delete = Ui.button(this, "永久注销账户");
        delete.setOnClickListener(view -> deleteAccount());
        root.addView(delete);
        scroll.addView(root);
        show(scroll);
        loadProfile();
    }

    private void loadProfile() {
        profile.removeAllViews();
        profile.addView(Ui.text(this, "正在加载账户信息…"));
        ApiClient.get(this).get("account/profile/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                profile.removeAllViews();
                JSONObject data = response.optJSONObject("data");
                profile.addView(Ui.title(AccountActivity.this, data == null ? "账户" : data.optString("username")));
                profile.addView(Ui.text(AccountActivity.this, "邮箱：" + (data == null ? "" : data.optString("email")) + "\n最近登录：" + (data == null ? "" : data.optString("last_login"))));
                profile.setTag(data);
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void editProfile() {
        JSONObject current = profile.getTag() instanceof JSONObject ? (JSONObject) profile.getTag() : new JSONObject();
        LinearLayout form = Ui.vertical(this);
        EditText username = input("用户名", false);
        EditText email = input("邮箱", false);
        username.setText(current.optString("username"));
        email.setText(current.optString("email"));
        form.addView(username);
        form.addView(email);
        new AlertDialog.Builder(this).setTitle("修改账户资料").setView(form)
                .setNegativeButton("取消", null)
                .setPositiveButton("保存", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("username", username.getText().toString().trim()); body.put("email", email.getText().toString().trim()); } catch (Exception ignored) {}
                    ApiClient.get(this).patch("account/profile/", body, callback("账户资料已更新。", this::loadProfile));
                }).show();
    }

    private void changePassword() {
        LinearLayout form = Ui.vertical(this);
        EditText oldPassword = input("原密码", true);
        EditText newPassword = input("新密码（至少 8 位）", true);
        form.addView(oldPassword);
        form.addView(newPassword);
        new AlertDialog.Builder(this).setTitle("修改密码").setView(form)
                .setNegativeButton("取消", null)
                .setPositiveButton("修改", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("old_password", oldPassword.getText().toString()); body.put("new_password", newPassword.getText().toString()); } catch (Exception ignored) {}
                    ApiClient.get(this).post("account/password/", body, callback("密码已修改，其他设备的登录令牌已撤销。", null));
                }).show();
    }

    private void devices() {
        ApiClient.get(this).get("account/devices/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONArray rows = response.optJSONArray("data");
                List<String> labels = new ArrayList<>();
                if (rows != null) for (int i = 0; i < rows.length(); i++) {
                    JSONObject row = rows.optJSONObject(i);
                    labels.add(row.optString("device_name") + (row.optBoolean("current") ? "（当前设备）" : "") + "\n" + row.optString("ip_address"));
                }
                if (labels.isEmpty()) labels.add("暂无受信任设备");
                JSONArray finalRows = rows;
                new AlertDialog.Builder(AccountActivity.this).setTitle("点击设备可删除信任")
                        .setAdapter(new ArrayAdapter<>(AccountActivity.this, android.R.layout.simple_list_item_1, labels), (dialog, which) -> {
                            if (finalRows == null || which >= finalRows.length()) return;
                            JSONObject row = finalRows.optJSONObject(which);
                            confirmDeviceDelete(row);
                        }).setNegativeButton("关闭", null).show();
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void confirmDeviceDelete(JSONObject row) {
        new AlertDialog.Builder(this).setTitle("删除受信任设备")
                .setMessage(row.optString("device_name") + " 下次登录将需要邮箱验证，且该设备当前令牌会立即失效。")
                .setNegativeButton("取消", null)
                .setPositiveButton("删除", (dialog, which) -> ApiClient.get(this).delete("account/devices/" + row.optInt("id") + "/", new JSONObject(), callback("设备信任已删除。", null))).show();
    }

    private void pushRegistration() {
        EditText regId = input("小米推送 RegId", false);
        new AlertDialog.Builder(this).setTitle("注册小米服务器推送")
                .setMessage("小米开发者凭据和客户端 SDK 配置完成后，App 会自动上报 RegId；当前也可手动填入 RegId 进行服务器联调。")
                .setView(regId).setNegativeButton("取消", null)
                .setPositiveButton("注册", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try {
                        body.put("provider", "xiaomi");
                        body.put("device_id", SessionStore.get(this).deviceId());
                        body.put("device_name", Build.MANUFACTURER + " " + Build.MODEL);
                        body.put("app_version", "2.0.0");
                        body.put("registration_id", regId.getText().toString().trim());
                    } catch (Exception ignored) {}
                    ApiClient.get(this).put("push/device/", body, callback("推送设备已登记。", null));
                }).show();
    }

    private void logout() {
        ApiClient.get(this).post("auth/logout/", new JSONObject(), new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) { leave(); }
            @Override public void onError(String message, int statusCode) { leave(); }
        });
    }

    private void deleteAccount() {
        EditText password = input("管理员密码", true);
        new AlertDialog.Builder(this).setTitle("永久注销账户")
                .setMessage("此操作不可撤销，将删除账户、班级、学生、附件和备份。")
                .setView(password).setNegativeButton("取消", null)
                .setPositiveButton("永久删除", (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("password", password.getText().toString()); } catch (Exception ignored) {}
                    ApiClient.get(this).post("account/delete/", body, new ApiClient.Callback() {
                        @Override public void onSuccess(JSONObject response) { leave(); }
                        @Override public void onError(String message, int statusCode) { toast(message); }
                    });
                }).show();
    }

    private EditText input(String hint, boolean password) {
        EditText input = new EditText(this);
        Ui.styleInput(this, input);
        input.setHint(hint);
        if (password) input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        input.setLayoutParams(new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return input;
    }

    private ApiClient.Callback callback(String success, Runnable after) {
        return new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) { toast(success); if (after != null) after.run(); }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        };
    }

    private void leave() {
        SessionStore.get(this).clear();
        TodoSyncManager.cancel(this);
        startActivity(new Intent(this, LoginActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }
}
