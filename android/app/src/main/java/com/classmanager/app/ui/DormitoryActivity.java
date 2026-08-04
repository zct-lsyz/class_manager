package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

public class DormitoryActivity extends BaseActivity {
    private LinearLayout root;
    private JSONArray rooms = new JSONArray();
    private JSONArray students = new JSONArray();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("宿舍床位与舍长", true);
        ScrollView scroll = new ScrollView(this);
        root = Ui.vertical(this);
        scroll.addView(root);
        show(scroll);
        load();
    }

    private void load() {
        root.removeAllViews();
        root.addView(Ui.text(this, "正在加载宿舍与床位…"));
        ApiClient.get(this).get("dormitory/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                rooms = data == null || data.optJSONArray("rooms") == null ? new JSONArray() : data.optJSONArray("rooms");
                loadStudents();
            }
            @Override public void onError(String message, int statusCode) { root.removeAllViews(); root.addView(Ui.text(DormitoryActivity.this, message)); handleAuthError(statusCode); }
        });
    }

    private void loadStudents() {
        ApiClient.get(this).get("resources/students/?page_size=100", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                students = data == null || data.optJSONArray("results") == null ? new JSONArray() : data.optJSONArray("results");
                render();
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private void render() {
        root.removeAllViews();
        if (rooms.length() == 0) {
            root.addView(Ui.text(this, "暂无宿舍。请先在宿舍管理中创建宿舍楼和宿舍。"));
            return;
        }
        for (int i = 0; i < rooms.length(); i++) {
            JSONObject room = rooms.optJSONObject(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12));
            card.setBackgroundResource(R.drawable.bg_card);
            card.addView(Ui.title(this, room.optString("building") + " · " + room.optString("room_number")));
            Button monitor = Ui.button(this, "舍长：" + (room.optString("monitor_name").isEmpty() ? "未设置" : room.optString("monitor_name")));
            monitor.setOnClickListener(view -> chooseMonitor(room));
            card.addView(monitor);
            JSONArray beds = room.optJSONArray("beds");
            for (int j = 0; beds != null && j < beds.length(); j++) {
                JSONObject bed = beds.optJSONObject(j);
                Button button = Ui.button(this, bed.optString("bed_number") + "号床：" + (bed.optString("student_name").isEmpty() ? "空闲" : bed.optString("student_name")));
                button.setEnabled(bed.optBoolean("active", true));
                button.setOnClickListener(view -> chooseStudent(bed));
                card.addView(button);
            }
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            params.setMargins(0, Ui.dp(this, 6), 0, Ui.dp(this, 6));
            root.addView(card, params);
        }
    }

    private void chooseStudent(JSONObject bed) {
        List<Option> options = new ArrayList<>();
        options.add(new Option(0, "释放床位"));
        for (int i = 0; i < students.length(); i++) {
            JSONObject row = students.optJSONObject(i);
            options.add(new Option(row.optInt("id"), row.optString("student_id") + " · " + row.optString("name")));
        }
        new AlertDialog.Builder(this).setTitle(bed.optString("bed_number") + "号床")
                .setItems(options.stream().map(Option::toString).toArray(String[]::new), (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("student_id", options.get(which).id == 0 ? JSONObject.NULL : options.get(which).id); } catch (Exception ignored) {}
                    ApiClient.get(this).post("dorm-beds/" + bed.optInt("id") + "/assign/", body, callback("床位分配已更新。"));
                }).show();
    }

    private void chooseMonitor(JSONObject room) {
        List<Option> options = new ArrayList<>();
        options.add(new Option(0, "取消舍长"));
        JSONArray beds = room.optJSONArray("beds");
        for (int i = 0; beds != null && i < beds.length(); i++) {
            JSONObject bed = beds.optJSONObject(i);
            if (bed.optInt("student_id") > 0) options.add(new Option(bed.optInt("student_id"), bed.optString("student_name")));
        }
        new AlertDialog.Builder(this).setTitle("设置舍长")
                .setItems(options.stream().map(Option::toString).toArray(String[]::new), (dialog, which) -> {
                    JSONObject body = new JSONObject();
                    try { body.put("student_id", options.get(which).id == 0 ? JSONObject.NULL : options.get(which).id); } catch (Exception ignored) {}
                    ApiClient.get(this).post("dormitory/rooms/" + room.optInt("id") + "/monitor/", body, callback("舍长已更新。"));
                }).show();
    }

    private ApiClient.Callback callback(String message) {
        return new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) { toast(message); load(); }
            @Override public void onError(String value, int statusCode) { toast(value); handleAuthError(statusCode); }
        };
    }

    private static final class Option {
        final int id; final String label;
        Option(int id, String label) { this.id = id; this.label = label; }
        @Override public String toString() { return label; }
    }
}
