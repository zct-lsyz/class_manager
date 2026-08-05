package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import com.classmanager.app.R;
import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.LinkedHashMap;
import java.util.Map;

public class RankingActivity extends BaseActivity {
    private LinearLayout root;
    private final Map<String, CheckBox> sourceBoxes = new LinkedHashMap<>();
    private EditText dateFromInput;
    private EditText dateToInput;
    private String dateFrom = "";
    private String dateTo = "";
    private String selectedSourceKeys = "";

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setup("积分排名", true);
        ScrollView scroll = new ScrollView(this);
        root = Ui.vertical(this);
        scroll.addView(root);
        show(scroll);
        load(false);
    }

    private void load(boolean saveSources) {
        if (root.getChildCount() == 0) root.addView(Ui.text(this, "正在加载积分排名…"));
        String path = "ranking/" + dateQuery();
        ApiClient.Callback callback = new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                render(data == null ? new JSONObject() : data);
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        };
        if (saveSources) {
            JSONArray selected = new JSONArray();
            for (Map.Entry<String, CheckBox> item : sourceBoxes.entrySet()) if (item.getValue().isChecked()) selected.put(item.getKey());
            JSONObject body = new JSONObject();
            try { body.put("sources", selected); } catch (Exception ignored) {}
            ApiClient.get(this).post(path, body, callback);
        } else ApiClient.get(this).get(path, callback);
    }

    private void render(JSONObject data) {
        root.removeAllViews();
        root.addView(Ui.title(this, "积分排名"));
        LinearLayout filters = card();
        TextView heading = Ui.text(this, "选择参与排名的项目");
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        filters.addView(heading);
        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(2);
        sourceBoxes.clear();
        JSONArray sources = data.optJSONArray("sources");
        JSONArray selected = data.optJSONArray("selected_sources");
        for (int i = 0; sources != null && i < sources.length(); i++) {
            JSONObject source = sources.optJSONObject(i);
            CheckBox box = new CheckBox(this);
            box.setText(source.optString("label"));
            box.setTextColor(getColor(R.color.text_primary));
            box.setChecked(contains(selected, source.optString("key")));
            GridLayout.LayoutParams params = new GridLayout.LayoutParams();
            params.width = 0;
            params.columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f);
            box.setLayoutParams(params);
            grid.addView(box);
            sourceBoxes.put(source.optString("key"), box);
        }
        filters.addView(grid);
        TextView dateHeading = Ui.text(this, "积分日期范围");
        dateHeading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        filters.addView(dateHeading);
        dateFromInput = Ui.temporalInput(this, "date", dateFrom);
        dateFromInput.setHint("选择开始日期（可留空）");
        filters.addView(dateFromInput);
        dateToInput = Ui.temporalInput(this, "date", dateTo);
        dateToInput.setHint("选择结束日期（可留空）");
        filters.addView(dateToInput);
        Button dateFilter = Ui.outlineButton(this, "按日期筛选");
        dateFilter.setOnClickListener(view -> { if (captureDates()) load(false); });
        filters.addView(dateFilter);
        Button apply = Ui.button(this, "保存选择并重新排名");
        apply.setOnClickListener(view -> { if (captureDates()) load(true); });
        filters.addView(apply);
        root.addView(filters, cardParams());

        LinearLayout table = card();
        table.setPadding(0, Ui.dp(this, 6), 0, Ui.dp(this, 6));
        table.addView(row("名次", "姓名", "分数", true, null));
        JSONArray ranking = data.optJSONArray("ranking");
        selectedSourceKeys = join(data.optJSONArray("selected_sources"));
        for (int i = 0; ranking != null && i < ranking.length(); i++) {
            JSONObject item = ranking.optJSONObject(i);
            View row = row(String.valueOf(item.optInt("rank")), item.optString("student_name"), signed(item.optInt("total")), false, item);
            table.addView(row);
        }
        if (ranking == null || ranking.length() == 0) table.addView(Ui.text(this, "暂无积分数据"));
        root.addView(table, cardParams());
    }

    private View row(String rank, String name, String total, boolean header, JSONObject item) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(Ui.dp(this, 12), Ui.dp(this, 11), Ui.dp(this, 12), Ui.dp(this, 11));
        row.setBackground(Ui.rounded(this, header ? 0xffe8f0fe : Color.WHITE, 0xffe2e8f0, 0));
        TextView rankView = Ui.text(this, rank);
        rankView.setGravity(Gravity.CENTER);
        TextView nameView = Ui.text(this, name);
        TextView scoreView = Ui.text(this, total);
        scoreView.setGravity(Gravity.END);
        if (header) {
            rankView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            nameView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            scoreView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        } else {
            nameView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            scoreView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            scoreView.setTextColor(item.optInt("total") < 0 ? 0xffdc3545 : getColor(R.color.primary));
            row.setOnClickListener(view -> showDetails(item));
        }
        row.addView(rankView, new LinearLayout.LayoutParams(Ui.dp(this, 54), ViewGroup.LayoutParams.WRAP_CONTENT));
        row.addView(nameView, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        row.addView(scoreView, new LinearLayout.LayoutParams(Ui.dp(this, 72), ViewGroup.LayoutParams.WRAP_CONTENT));
        return row;
    }

    private void showDetails(JSONObject student) {
        ApiClient.get(this).get("resources/point_records/?page_size=100&student=" + student.optInt("student_id") +
                "&date_from=" + android.net.Uri.encode(dateFrom) + "&date_to=" + android.net.Uri.encode(dateTo) +
                "&sources=" + android.net.Uri.encode(selectedSourceKeys.isEmpty() ? "__none__" : selectedSourceKeys), new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                JSONArray records = data == null ? null : data.optJSONArray("results");
                LinearLayout details = Ui.vertical(RankingActivity.this);
                for (int i = 0; records != null && i < records.length(); i++) {
                    JSONObject record = records.optJSONObject(i);
                    TextView line = Ui.text(RankingActivity.this,
                            record.optString("date") + "    " + signed(record.optInt("points")) + "\n" +
                            record.optString("reason") + "\n" + record.optString("source_type_display"));
                    line.setTextColor(record.optInt("points") < 0 ? 0xffb91c1c : 0xff15803d);
                    line.setBackground(Ui.rounded(RankingActivity.this, 0xfff8fafc, 0xffe2e8f0, 8));
                    line.setPadding(Ui.dp(RankingActivity.this, 12), Ui.dp(RankingActivity.this, 9), Ui.dp(RankingActivity.this, 12), Ui.dp(RankingActivity.this, 9));
                    LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
                    params.bottomMargin = Ui.dp(RankingActivity.this, 6);
                    details.addView(line, params);
                }
                if (records == null || records.length() == 0) details.addView(Ui.text(RankingActivity.this, "暂无加减分明细"));
                ScrollView scroll = new ScrollView(RankingActivity.this);
                scroll.addView(details);
                new AlertDialog.Builder(RankingActivity.this).setTitle(student.optString("student_name") + " · 加减分明细")
                        .setView(scroll).setPositiveButton("关闭", null).show();
            }
            @Override public void onError(String message, int statusCode) { toast(message); handleAuthError(statusCode); }
        });
    }

    private LinearLayout card() {
        LinearLayout card = new LinearLayout(this);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setPadding(Ui.dp(this, 14), Ui.dp(this, 12), Ui.dp(this, 14), Ui.dp(this, 12));
        card.setBackgroundResource(R.drawable.bg_card);
        return card;
    }

    private LinearLayout.LayoutParams cardParams() {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(this, 6), 0, Ui.dp(this, 6));
        return params;
    }

    private boolean contains(JSONArray values, String key) {
        for (int i = 0; values != null && i < values.length(); i++) if (key.equals(values.optString(i))) return true;
        return false;
    }

    private boolean captureDates() {
        dateFrom = dateFromInput == null ? "" : dateFromInput.getText().toString().trim();
        dateTo = dateToInput == null ? "" : dateToInput.getText().toString().trim();
        if (!dateFrom.isEmpty() && !dateTo.isEmpty() && dateFrom.compareTo(dateTo) > 0) {
            toast("开始日期不能晚于结束日期。");
            return false;
        }
        return true;
    }

    private String dateQuery() {
        if (dateFrom.isEmpty() && dateTo.isEmpty()) return "";
        return "?date_from=" + android.net.Uri.encode(dateFrom) + "&date_to=" + android.net.Uri.encode(dateTo);
    }

    private String join(JSONArray values) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; values != null && i < values.length(); i++) {
            if (result.length() > 0) result.append(',');
            result.append(values.optString(i));
        }
        return result.toString();
    }

    private String signed(int value) { return value > 0 ? "+" + value : String.valueOf(value); }
}
