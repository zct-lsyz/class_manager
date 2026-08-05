package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.GridLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

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
    private int selectedRoom;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("查询舍长及床位分配", true);
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
                render();
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
        LinearLayout roomTabs = new LinearLayout(this);
        roomTabs.setOrientation(LinearLayout.HORIZONTAL);
        for (int i = 0; i < rooms.length(); i++) {
            JSONObject room = rooms.optJSONObject(i);
            TextView tab = Ui.text(this, room.optString("room_number"));
            tab.setTextColor(i == selectedRoom ? android.graphics.Color.WHITE : getColor(R.color.primary));
            tab.setBackground(Ui.rounded(this, i == selectedRoom ? getColor(R.color.primary) : android.graphics.Color.WHITE, getColor(R.color.primary), 10));
            tab.setPadding(Ui.dp(this, 14), Ui.dp(this, 9), Ui.dp(this, 14), Ui.dp(this, 9));
            int index = i;
            tab.setOnClickListener(view -> { selectedRoom = index; render(); });
            LinearLayout.LayoutParams tabParams = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            tabParams.setMargins(0, 0, Ui.dp(this, 7), Ui.dp(this, 7));
            roomTabs.addView(tab, tabParams);
        }
        HorizontalScrollView roomTabScroll = new HorizontalScrollView(this);
        roomTabScroll.setHorizontalScrollBarEnabled(false);
        roomTabScroll.addView(roomTabs);
        root.addView(roomTabScroll);
        for (int i = 0; i < rooms.length(); i++) {
            if (i != selectedRoom) continue;
            JSONObject room = rooms.optJSONObject(i);
            LinearLayout card = new LinearLayout(this);
            card.setOrientation(LinearLayout.VERTICAL);
            card.setPadding(Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12), Ui.dp(this, 12));
            card.setBackgroundResource(R.drawable.bg_card);
            card.addView(Ui.title(this, room.optString("building") + " · " + room.optString("room_number")));
            TextView monitor = Ui.text(this, "舍长：" + (room.optString("monitor_name").isEmpty() ? "未设置" : room.optString("monitor_name")));
            monitor.setTextColor(0xff64748b);
            card.addView(monitor);
            JSONArray beds = room.optJSONArray("beds");
            GridLayout bedGrid = new GridLayout(this);
            bedGrid.setColumnCount(4);
            for (int j = 0; beds != null && j < beds.length(); j++) {
                JSONObject bed = beds.optJSONObject(j);
                TextView block = Ui.text(this, bed.optString("bed_number") + "号床\n" + (bed.optString("student_name").isEmpty() ? "空床" : bed.optString("student_name")));
                block.setGravity(android.view.Gravity.CENTER);
                block.setTextSize(13);
                block.setBackground(Ui.rounded(this, bed.optString("student_name").isEmpty() ? 0xfff8fafc : 0xffe8f0fe, 0xffcbd5e1, 8));
                block.setPadding(Ui.dp(this, 3), Ui.dp(this, 7), Ui.dp(this, 3), Ui.dp(this, 7));
                GridLayout.LayoutParams blockParams = new GridLayout.LayoutParams();
                blockParams.width = ViewGroup.LayoutParams.WRAP_CONTENT;
                blockParams.setMargins(Ui.dp(this, 2), Ui.dp(this, 2), Ui.dp(this, 2), Ui.dp(this, 2));
                bedGrid.addView(block, blockParams);
            }
            card.addView(bedGrid);
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
            options.add(new Option(row.optInt("id"), row.optString("name")));
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
