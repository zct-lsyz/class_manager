package com.classmanager.app.ui;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.GridLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.core.app.ActivityCompat;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;
import com.classmanager.app.data.SessionStore;
import com.classmanager.app.notification.NotificationScheduler;
import com.classmanager.app.notification.TodoSyncManager;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;
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
        TodoSyncManager.enable(this);
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
        root.addView(Ui.title(this, "工作台首页"));
        summary = new LinearLayout(this);
        summary.setOrientation(LinearLayout.VERTICAL);
        root.addView(summary, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
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
                renderDashboardData(data);
            }
            @Override public void onError(String message, int statusCode) {
                summary.removeAllViews();
                summary.addView(Ui.text(MainActivity.this, "同步失败：" + message));
                handleAuthError(statusCode);
            }
        });
    }

    private void renderDashboardData(JSONObject data) {
        JSONObject classInfo = data.optJSONObject("class");
        JSONObject semester = data.optJSONObject("semester");
        JSONObject stats = data.optJSONObject("stats");
        Object week = data.opt("teaching_week");
        TextView realtime = Ui.text(this, data.optString("today") + (week == null || week == JSONObject.NULL ? "" : "  ·  第 " + week + " 教学周"));
        realtime.setTextColor(0xff64748b);
        realtime.setGravity(Gravity.END);
        summary.addView(realtime);

        if (stats != null) {
            LinearLayout statRow = new LinearLayout(this);
            statRow.setOrientation(LinearLayout.HORIZONTAL);
            LinearLayout.LayoutParams statParams = new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
            statParams.setMargins(Ui.dp(this, 3), Ui.dp(this, 3), Ui.dp(this, 3), Ui.dp(this, 3));
            statRow.addView(stat("全班人数\n男 " + stats.optInt("male") + " · 女 " + stats.optInt("female"), stats.optInt("students"), getColor(R.color.primary)), new LinearLayout.LayoutParams(statParams));
            statRow.addView(stat("今日异常", stats.optInt("today_absent"), 0xfff57c00), new LinearLayout.LayoutParams(statParams));
            statRow.addView(stat("本周未交", stats.optInt("week_unsubmitted"), 0xffdc3545), new LinearLayout.LayoutParams(statParams));
            summary.addView(statRow);
        }

        LinearLayout todoCard = dashboardCard("待办及倒计时");
        TextView todoHeading = Ui.text(this, "待办事项");
        todoHeading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        todoHeading.setTextColor(getColor(R.color.primary));
        todoCard.addView(todoHeading);
        JSONArray todos = data.optJSONArray("todos");
        if (todos == null || todos.length() == 0) todoCard.addView(muted("暂无待办事项"));
        else for (int i = 0; i < Math.min(todos.length(), 5); i++) todoCard.addView(todoItem(todos.optJSONObject(i)));
        todoCard.addView(actionLink("查看全部待办", view -> openSection("待办事项")));
        TextView countdownHeading = Ui.text(this, "倒计时");
        countdownHeading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        countdownHeading.setTextColor(0xfff57c00);
        countdownHeading.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 4));
        todoCard.addView(countdownHeading);
        JSONArray countdowns = data.optJSONArray("countdowns");
        if (countdowns == null || countdowns.length() == 0) todoCard.addView(muted("暂无倒计时"));
        else {
            LinearLayout countdownRow = new LinearLayout(this);
            countdownRow.setOrientation(LinearLayout.HORIZONTAL);
            for (int i = 0; i < Math.min(countdowns.length(), 6); i++) countdownRow.addView(countdownItem(countdowns.optJSONObject(i)));
            HorizontalScrollView countdownScroll = new HorizontalScrollView(this);
            countdownScroll.setHorizontalScrollBarEnabled(false);
            countdownScroll.addView(countdownRow);
            todoCard.addView(countdownScroll);
        }
        todoCard.addView(actionLink("管理倒计时", view -> openResource("countdowns", "倒计时管理")));
        addDashboardCard(todoCard);

        LinearLayout quickCard = dashboardCard("快捷操作");
        GridLayout quickGrid = new GridLayout(this);
        quickGrid.setColumnCount(2);
        addQuickAction(quickGrid, "录入考勤", "考勤管理", 0xffe8f0fe);
        addQuickAction(quickGrid, "登记课堂纪律", "课堂纪律", 0xfffff3e0);
        addQuickAction(quickGrid, "登记宿舍卫生", "宿舍管理", 0xffe8f5e9);
        addQuickAction(quickGrid, "登记宿舍纪律", "宿舍管理", 0xffeceff1);
        addQuickAction(quickGrid, "登记作业未交", "作业检查", 0xffffebee);
        addQuickAction(quickGrid, "成绩分析", "成绩分析", 0xffe0f7fa);
        addQuickAction(quickGrid, "查看座位", "座位表", 0xffede7f6);
        addQuickAction(quickGrid, "学生谈话", "学生谈话", 0xfffce4ec);
        addQuickAction(quickGrid, "执行备份", "备份管理", 0xffeceff1);
        quickCard.addView(quickGrid);
        addDashboardCard(quickCard);

        LinearLayout infoCard = dashboardCard("基本信息");
        addKeyValue(infoCard, "班级", classInfo == null ? "未设置" : classInfo.optString("name", "未设置"));
        addKeyValue(infoCard, "学期", semester == null ? "未设置" : semester.optString("name", "未设置"));
        TextView headTeacher = addKeyValue(infoCard, "班主任", classInfo == null ? "未设置" : classInfo.optString("head_teacher", "未设置"));
        TextView schoolName = addKeyValue(infoCard, "学校", classInfo == null ? "未设置" : classInfo.optString("school_name", "未设置"));
        if (classInfo != null && (isUnset(headTeacher) || isUnset(schoolName)))
            loadClassIdentity(classInfo.optInt("id"), headTeacher, schoolName);
        JSONObject quote = data.optJSONObject("quote");
        if (quote != null) infoCard.addView(quoteCard(quote));
        addDashboardCard(infoCard);
    }

    private LinearLayout dashboardCard(String title) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        TextView heading = Ui.title(this, title);
        heading.setTextSize(17);
        heading.setTextColor(getColor(R.color.primary));
        card.addView(heading);
        return card;
    }

    private void addDashboardCard(LinearLayout card) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 8), 0, Ui.dp(this, 8));
        summary.addView(card, params);
    }

    private LinearLayout todoItem(JSONObject row) {
        String deadline = row == null ? "" : row.optString("deadline");
        if (!deadline.isEmpty() && !"null".equals(deadline)) {
            deadline = deadline.replace('T', ' ');
            if (deadline.length() > 16) deadline = deadline.substring(0, 16);
        }
        int priority = row == null ? 3 : row.optInt("priority", 3);
        int accent = priority == 1 ? 0xffdc3545 : priority == 2 ? 0xfff57c00 : getColor(R.color.primary);
        int fill = priority == 1 ? 0xfffff1f2 : priority == 2 ? 0xfffff7ed : 0xfff8fafc;
        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.HORIZONTAL);
        item.setGravity(Gravity.CENTER_VERTICAL);
        item.setBackground(Ui.rounded(this, fill, accent, 8));
        item.setPadding(Ui.dp(this, 7), Ui.dp(this, 6), Ui.dp(this, 10), Ui.dp(this, 6));
        CheckBox check = new CheckBox(this);
        check.setFocusable(false);
        check.setChecked(row != null && row.optBoolean("is_completed"));
        check.setContentDescription("标记为已完成");
        check.setOnClickListener(view -> toggleDashboardTodo(row, check.isChecked()));
        item.addView(check);
        TextView text = Ui.text(this, (row == null ? "" : row.optString("title")) + (deadline.isEmpty() ? "" : "\n" + deadline));
        text.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        if (row != null && row.optBoolean("is_completed")) text.setPaintFlags(text.getPaintFlags() | Paint.STRIKE_THRU_TEXT_FLAG);
        text.setOnClickListener(view -> openSection("待办事项"));
        item.addView(text, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 4), 0, Ui.dp(this, 4));
        item.setLayoutParams(params);
        return item;
    }

    private void toggleDashboardTodo(JSONObject row, boolean completed) {
        if (row == null) return;
        JSONObject body = new JSONObject();
        try { body.put("is_completed", completed); } catch (Exception ignored) {}
        ApiClient.get(this).patch("resources/todos/" + row.optInt("id") + "/", body, new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) { NotificationScheduler.sync(MainActivity.this); loadDashboard(); }
            @Override public void onError(String message, int statusCode) { toast(message); loadDashboard(); handleAuthError(statusCode); }
        });
    }

    private LinearLayout countdownItem(JSONObject row) {
        LinearLayout item = new LinearLayout(this);
        item.setOrientation(LinearLayout.VERTICAL);
        item.setGravity(Gravity.CENTER);
        item.setBackground(Ui.rounded(this, Color.WHITE, 0xffe9ecef, 12));
        item.setPadding(Ui.dp(this, 10), Ui.dp(this, 10), Ui.dp(this, 10), Ui.dp(this, 10));
        int days = row.optInt("days_remaining");
        TextView number = Ui.text(this, days == 0 ? "今天" : days < 0 ? "已过期" : String.valueOf(days));
        number.setTextSize(days == 0 ? 18 : 24);
        number.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        number.setTextColor(days <= 3 ? 0xffdc3545 : days <= 7 ? 0xfff57c00 : getColor(R.color.primary));
        number.setGravity(Gravity.CENTER);
        TextView unit = Ui.text(this, days > 0 ? "天" : "");
        unit.setTextSize(11);
        unit.setGravity(Gravity.CENTER);
        TextView name = Ui.text(this, row.optString("name"));
        name.setTextSize(12);
        name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        name.setGravity(Gravity.CENTER);
        item.addView(number);
        item.addView(unit);
        item.addView(name);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(Ui.dp(this, 108), ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 4), Ui.dp(this, 8), Ui.dp(this, 4));
        item.setLayoutParams(params);
        return item;
    }

    private void addQuickAction(GridLayout grid, String label, String section, int background) {
        TextView item = Ui.text(this, label);
        item.setTextSize(14);
        item.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        item.setTextColor(getColor(R.color.primary));
        item.setGravity(Gravity.CENTER);
        item.setBackground(Ui.rounded(this, background, 0, 10));
        item.setOnClickListener(view -> openSection(section));
        GridLayout.LayoutParams params = new GridLayout.LayoutParams();
        params.width = 0;
        params.height = Ui.dp(this, 54);
        params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
        params.setMargins(Ui.dp(this, 4), Ui.dp(this, 4), Ui.dp(this, 4), Ui.dp(this, 4));
        item.setLayoutParams(params);
        grid.addView(item);
    }

    private TextView addKeyValue(LinearLayout parent, String label, String value) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        TextView key = Ui.text(this, label);
        key.setTextColor(0xff6c757d);
        row.addView(key, new LinearLayout.LayoutParams(Ui.dp(this, 72), ViewGroup.LayoutParams.WRAP_CONTENT));
        TextView content = Ui.text(this, value == null || value.isEmpty() ? "未设置" : value);
        content.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        row.addView(content, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        parent.addView(row);
        return content;
    }

    private boolean isUnset(TextView view) {
        return "未设置".contentEquals(view.getText());
    }

    private void loadClassIdentity(int classId, TextView headTeacher, TextView schoolName) {
        if (classId <= 0) return;
        ApiClient.get(this).get("resources/classes/" + classId + "/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject row = response.optJSONObject("data");
                if (row == null) return;
                String teacher = row.optString("head_teacher");
                String school = row.optString("school_name");
                if (!teacher.isEmpty() && !"null".equals(teacher)) headTeacher.setText(teacher);
                if (!school.isEmpty() && !"null".equals(school)) schoolName.setText(school);
            }
            @Override public void onError(String message, int statusCode) { handleAuthError(statusCode); }
        });
    }

    private TextView quoteCard(JSONObject quote) {
        String author = quote.optString("author");
        TextView view = Ui.text(this, "每日励志名言\n“" + quote.optString("content") + "”" + (author.isEmpty() ? "" : "\n—— " + author));
        view.setTextColor(Color.WHITE);
        view.setTextSize(15);
        view.setLineSpacing(0, 1.25f);
        view.setBackground(Ui.rounded(this, 0xff667eea, 0, 10));
        view.setPadding(Ui.dp(this, 14), Ui.dp(this, 12), Ui.dp(this, 14), Ui.dp(this, 12));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 10), 0, 0);
        view.setLayoutParams(params);
        return view;
    }

    private TextView muted(String value) {
        TextView view = Ui.text(this, value);
        view.setTextColor(0xff6c757d);
        return view;
    }

    private TextView actionLink(String value, android.view.View.OnClickListener listener) {
        TextView view = Ui.text(this, value + "  ›");
        view.setTextColor(getColor(R.color.primary));
        view.setGravity(Gravity.END);
        view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setOnClickListener(listener);
        return view;
    }

    private void renderFeatureGroups() {
        for (Map.Entry<String, List<String>> group : FeatureCatalog.groups().entrySet()) {
            TextView heading = Ui.text(this, group.getKey());
            heading.setTextSize(13);
            heading.setTextColor(0xff64748b);
            heading.setPadding(Ui.dp(this, 4), Ui.dp(this, 14), 0, Ui.dp(this, 5));
            root.addView(heading);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setBackgroundResource(R.drawable.bg_card);
            for (int i = 0; i < group.getValue().size(); i++) {
                String section = group.getValue().get(i);
                TextView item = Ui.text(this, getString(R.string.module_navigation_item, section));
                item.setTextSize(16);
                item.setPadding(Ui.dp(this, 4), Ui.dp(this, 11), Ui.dp(this, 4), Ui.dp(this, 11));
                item.setOnClickListener(view -> openSection(section));
                card.addView(item);
                if (i < group.getValue().size() - 1) {
                    android.view.View divider = new android.view.View(this);
                    divider.setBackgroundColor(0xffe2e8f0);
                    card.addView(divider, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(this, 1)));
                }
            }
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            params.setMargins(0, 0, 0, Ui.dp(this, 4));
            root.addView(card, params);
        }
    }

    private void openSection(String section) {
        List<FeatureCatalog.Entry> entries = FeatureCatalog.sections().get(section);
        if (entries != null && entries.size() == 1) {
            startActivity(SectionActivity.intentFor(this, entries.get(0)));
            return;
        }
        Intent intent = new Intent(this, SectionActivity.class);
        intent.putExtra("section", section);
        startActivity(intent);
    }

    private LinearLayout stat(String label, int value, int color) {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setGravity(Gravity.CENTER);
        card.setBackground(Ui.rounded(this, Color.WHITE, 0xffe9ecef, 12));
        card.setPadding(Ui.dp(this, 3), Ui.dp(this, 10), Ui.dp(this, 3), Ui.dp(this, 10));
        TextView number = Ui.text(this, String.valueOf(value));
        number.setTextSize(24);
        number.setTextColor(color);
        number.setGravity(android.view.Gravity.CENTER);
        number.setTypeface(android.graphics.Typeface.DEFAULT, android.graphics.Typeface.BOLD);
        TextView caption = Ui.text(this, label);
        caption.setTextSize(12);
        caption.setTextColor(0xff6c757d);
        caption.setGravity(android.view.Gravity.CENTER);
        card.addView(number);
        card.addView(caption);
        return card;
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
