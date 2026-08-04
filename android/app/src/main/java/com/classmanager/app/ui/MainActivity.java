package com.classmanager.app.ui;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.core.app.ActivityCompat;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;
import com.classmanager.app.data.SessionStore;
import com.classmanager.app.notification.NotificationScheduler;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Map;

public class MainActivity extends BaseActivity {
    private LinearLayout root;
    private LinearLayout summary;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if (!SessionStore.get(this).isLoggedIn()) {
            startActivity(new Intent(this, LoginActivity.class));
            finish();
            return;
        }
        setup("工作台", false);
        render();
        requestNotifications();
        NotificationScheduler.sync(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (root != null) loadDashboard();
        if (SessionStore.get(this).isLoggedIn()) NotificationScheduler.sync(this);
    }

    private void render() {
        ScrollView scroll = new ScrollView(this);
        root = Ui.vertical(this);
        summary = new LinearLayout(this);
        summary.setOrientation(LinearLayout.VERTICAL);
        summary.setBackgroundResource(R.drawable.bg_card);
        root.addView(summary, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        root.addView(Ui.title(this, "工作台工具"));
        Button countdowns = Ui.button(this, "倒计时管理");
        countdowns.setOnClickListener(view -> openResource("countdowns", "倒计时管理"));
        root.addView(countdowns);
        Button websites = Ui.button(this, "常用教学网站管理");
        websites.setOnClickListener(view -> openResource("teaching_websites", "常用教学网站管理"));
        root.addView(websites);
        root.addView(Ui.title(this, "功能模块"));
        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(2);
        for (Map.Entry<String, java.util.List<FeatureCatalog.Entry>> item : FeatureCatalog.sections().entrySet()) {
            Button button = new Button(this);
            button.setText(item.getKey());
            button.setAllCaps(false);
            GridLayout.LayoutParams params = new GridLayout.LayoutParams();
            params.width = 0;
            params.height = Ui.dp(this, 64);
            params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
            params.setMargins(Ui.dp(this, 4), Ui.dp(this, 4), Ui.dp(this, 4), Ui.dp(this, 4));
            button.setLayoutParams(params);
            button.setOnClickListener(view -> {
                Intent intent = new Intent(this, SectionActivity.class);
                intent.putExtra("section", item.getKey());
                startActivity(intent);
            });
            grid.addView(button);
        }
        root.addView(grid);
        scroll.addView(root);
        show(scroll);
        loadDashboard();
    }

    private void loadDashboard() {
        summary.removeAllViews();
        summary.addView(Ui.text(this, "正在同步工作台…"));
        ApiClient.get(this).get("dashboard/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                summary.removeAllViews();
                JSONObject data = response.optJSONObject("data");
                if (data == null || !data.optBoolean("has_current_class")) {
                    summary.addView(Ui.title(MainActivity.this, "尚未设置当前班级"));
                    summary.addView(Ui.text(MainActivity.this, "请进入“班级与学期”创建并设为当前班级。"));
                    return;
                }
                JSONObject classInfo = data.optJSONObject("class");
                JSONObject semester = data.optJSONObject("semester");
                JSONObject stats = data.optJSONObject("stats");
                summary.addView(Ui.title(MainActivity.this, classInfo == null ? "当前班级" : classInfo.optString("name")));
                String semesterText = semester == null ? "未设置当前学期" : semester.optString("name");
                Object week = data.opt("teaching_week");
                summary.addView(Ui.text(MainActivity.this, semesterText + (week == null || week == JSONObject.NULL ? "" : " · 第 " + week + " 教学周")));
                if (stats != null) {
                    summary.addView(Ui.text(MainActivity.this,
                            "学生 " + stats.optInt("students") + " 人    今日异常 " + stats.optInt("today_absent") + " 人\n" +
                            "本周未交 " + stats.optInt("week_unsubmitted") + " 条    待办 " + stats.optInt("active_todos") + " 条"));
                }
                JSONObject quote = data.optJSONObject("quote");
                if (quote != null) summary.addView(Ui.text(MainActivity.this,
                        "每日一句：" + quote.optString("content") + (quote.optString("author").isEmpty() ? "" : " —— " + quote.optString("author"))));
                JSONArray countdownRows = data.optJSONArray("countdowns");
                if (countdownRows != null && countdownRows.length() > 0) {
                    summary.addView(Ui.title(MainActivity.this, "倒计时"));
                    for (int i = 0; i < countdownRows.length(); i++) {
                        JSONObject row = countdownRows.optJSONObject(i);
                        summary.addView(Ui.text(MainActivity.this, row.optString("name") + "：" + row.optInt("days_remaining") + " 天"));
                    }
                }
                JSONArray websiteRows = data.optJSONArray("websites");
                if (websiteRows != null && websiteRows.length() > 0) {
                    summary.addView(Ui.title(MainActivity.this, "常用教学网站"));
                    for (int i = 0; i < websiteRows.length(); i++) {
                        JSONObject row = websiteRows.optJSONObject(i);
                        Button link = Ui.button(MainActivity.this, row.optString("name"));
                        link.setOnClickListener(view -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(row.optString("url")))));
                        summary.addView(link);
                    }
                }
            }
            @Override public void onError(String message, int statusCode) {
                summary.removeAllViews();
                summary.addView(Ui.text(MainActivity.this, "同步失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void openResource(String resource, String title) {
        Intent intent = new Intent(this, ResourceActivity.class);
        intent.putExtra("resource", resource);
        intent.putExtra("title", title);
        startActivity(intent);
    }

    private void requestNotifications() {
        if (Build.VERSION.SDK_INT >= 33 && ActivityCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1001);
        }
    }
}
