package com.classmanager.app.ui;

import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import com.classmanager.app.data.ApiClient;
import com.classmanager.app.data.SessionStore;
import com.classmanager.app.notification.TodoSyncManager;

import org.json.JSONObject;

public class LoginActivity extends BaseActivity {
    private EditText username;
    private EditText password;
    private EditText code;
    private Button submit;
    private ProgressBar progress;
    private String verificationToken = "";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (SessionStore.get(this).isLoggedIn()) {
            openMain();
            return;
        }
        setup("班级教学管理", false);
        render();
    }

    private void render() {
        LinearLayout root = Ui.vertical(this);
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        TextView heading = Ui.title(this, "登录到你的服务器");
        heading.setTextSize(26);
        heading.setGravity(Gravity.CENTER);
        root.addView(heading);
        TextView endpoint = Ui.text(this, "https://120.27.231.112\n使用受信任 HTTPS 连接，密码不会保存在手机中。");
        endpoint.setGravity(Gravity.CENTER);
        root.addView(endpoint);

        username = input("用户名", InputType.TYPE_CLASS_TEXT);
        password = input("密码", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        code = input("邮箱中的 6 位验证码", InputType.TYPE_CLASS_NUMBER);
        code.setVisibility(View.GONE);
        root.addView(username);
        root.addView(password);
        root.addView(code);
        submit = Ui.button(this, "登录");
        submit.setOnClickListener(view -> submit());
        root.addView(submit);
        progress = Ui.progress(this);
        progress.setVisibility(View.GONE);
        root.addView(progress);
        show(root);
    }

    private EditText input(String hint, int type) {
        EditText input = new EditText(this);
        Ui.styleInput(this, input);
        input.setHint(hint);
        input.setInputType(type);
        input.setSingleLine(true);
        input.setLayoutParams(new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        return input;
    }

    private void submit() {
        if (verificationToken.isEmpty()) login(); else verify();
    }

    private void login() {
        if (username.getText().toString().trim().isEmpty() || password.getText().toString().isEmpty()) {
            toast("请输入用户名和密码。");
            return;
        }
        setLoading(true);
        JSONObject body = new JSONObject();
        try {
            body.put("username", username.getText().toString().trim());
            body.put("password", password.getText().toString());
            body.put("device_id", SessionStore.get(this).deviceId());
            body.put("device_name", Build.MANUFACTURER + " " + Build.MODEL);
        } catch (Exception ignored) {}
        ApiClient.get(this).post("auth/login/", body, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                setLoading(false);
                JSONObject data = response.optJSONObject("data");
                if (data != null && data.optBoolean("verification_required")) {
                    verificationToken = data.optString("verification_token");
                    code.setVisibility(View.VISIBLE);
                    username.setEnabled(false);
                    password.setEnabled(false);
                    submit.setText("验证并登录");
                    toast("验证码已发送到 " + data.optString("email_hint"));
                } else {
                    saveAndOpen(data);
                }
            }
            @Override public void onError(String message, int statusCode) {
                setLoading(false);
                toast(message);
            }
        });
    }

    private void verify() {
        if (code.getText().toString().trim().length() != 6) {
            toast("请输入 6 位验证码。");
            return;
        }
        setLoading(true);
        JSONObject body = new JSONObject();
        try {
            body.put("verification_token", verificationToken);
            body.put("code", code.getText().toString().trim());
        } catch (Exception ignored) {}
        ApiClient.get(this).post("auth/verify/", body, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                setLoading(false);
                saveAndOpen(response.optJSONObject("data"));
            }
            @Override public void onError(String message, int statusCode) {
                setLoading(false);
                toast(message);
            }
        });
    }

    private void saveAndOpen(JSONObject data) {
        if (data == null || data.optString("token").isEmpty()) {
            toast("服务器没有返回登录令牌。");
            return;
        }
        JSONObject user = data.optJSONObject("user");
        SessionStore.get(this).saveSession(data.optString("token"), user == null ? "" : user.optString("username"));
        TodoSyncManager.enable(this);
        openMain();
    }

    private void setLoading(boolean value) {
        progress.setVisibility(value ? View.VISIBLE : View.GONE);
        submit.setEnabled(!value);
    }

    private void openMain() {
        startActivity(new Intent(this, MainActivity.class)
                .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK | Intent.FLAG_ACTIVITY_NEW_TASK));
        finish();
    }
}
