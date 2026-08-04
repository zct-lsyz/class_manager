package com.classmanager.app.ui;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TableLayout;
import android.widget.TableRow;
import android.widget.TextView;

import com.classmanager.app.R;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

final class StructuredReportRenderer {
    private static final int BORDER = 0xffcbd5e1;
    private static final int HEADER = 0xffe8f0fe;
    private static final int MUTED = 0xff64748b;

    static boolean supports(String endpoint) {
        return "course-schedule/".equals(endpoint) || "seating/".equals(endpoint) || "duty-roster/".equals(endpoint);
    }

    static View render(Context context, String endpoint, JSONObject data) {
        if ("course-schedule/".equals(endpoint)) return courseSchedule(context, data);
        if ("seating/".equals(endpoint)) return seating(context, data);
        return dutyRoster(context, data);
    }

    private static View courseSchedule(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        String semester = data.optString("semester");
        if (!semester.isEmpty() && !"null".equals(semester)) root.addView(infoCard(context, "当前学期", semester));

        JSONArray weekdayRows = data.optJSONArray("weekdays");
        JSONArray periodRows = data.optJSONArray("periods");
        JSONArray entryRows = data.optJSONArray("entries");
        Map<Integer, String> weekdayLabels = new HashMap<>();
        if (weekdayRows != null) for (int i = 0; i < weekdayRows.length(); i++) {
            JSONObject row = weekdayRows.optJSONObject(i);
            if (row != null) weekdayLabels.put(row.optInt("value"), row.optString("label"));
        }
        if (weekdayLabels.isEmpty()) for (int i = 1; i <= 7; i++) weekdayLabels.put(i, weekdayName(i));

        Map<Integer, JSONObject> periods = new HashMap<>();
        TreeSet<Integer> periodNumbers = new TreeSet<>();
        if (periodRows != null) for (int i = 0; i < periodRows.length(); i++) {
            JSONObject row = periodRows.optJSONObject(i);
            if (row != null) {
                periods.put(row.optInt("period"), row);
                periodNumbers.add(row.optInt("period"));
            }
        }
        Map<String, JSONObject> entries = new HashMap<>();
        if (entryRows != null) for (int i = 0; i < entryRows.length(); i++) {
            JSONObject row = entryRows.optJSONObject(i);
            if (row != null) {
                entries.put(row.optInt("weekday") + "_" + row.optInt("period"), row);
                periodNumbers.add(row.optInt("period"));
            }
        }
        if (periodNumbers.isEmpty()) {
            root.addView(empty(context, "暂未设置课程表"));
            return root;
        }

        TableLayout table = new TableLayout(context);
        TableRow header = new TableRow(context);
        header.addView(cell(context, "节次", -76, HEADER, true, 44));
        for (int weekday = 1; weekday <= 7; weekday++)
            header.addView(cell(context, weekdayLabels.get(weekday), -44, HEADER, true, 44));
        table.addView(header);
        for (Integer period : periodNumbers) {
            TableRow row = new TableRow(context);
            JSONObject setting = periods.get(period);
            String periodName = setting == null ? "" : setting.optString("name");
            if (periodName.isEmpty()) periodName = "第" + period + "节";
            String start = setting == null ? "" : setting.optString("start_time");
            String end = setting == null ? "" : setting.optString("end_time");
            String time = cleanTime(start) + (!cleanTime(start).isEmpty() && !cleanTime(end).isEmpty() ? "-" : "") + cleanTime(end);
            row.addView(cell(context, periodName + (time.isEmpty() ? "" : "\n" + time), -76, Color.WHITE, true, 44));
            for (int weekday = 1; weekday <= 7; weekday++) {
                JSONObject entry = entries.get(weekday + "_" + period);
                String course = entry == null ? "" : entry.optString("course");
                String teacher = entry == null ? "" : entry.optString("teacher");
                String text = course.isEmpty() ? "—" : course + (teacher.isEmpty() ? "" : "\n" + teacher);
                row.addView(cell(context, text, -44, course.isEmpty() ? Color.WHITE : courseColor(course), !course.isEmpty(), 44));
            }
            table.addView(row);
        }
        root.addView(horizontal(context, table));
        return root;
    }

    private static View seating(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONObject plan = data.optJSONObject("plan");
        if (plan == null) {
            root.addView(empty(context, "暂无座位方案"));
            return root;
        }
        JSONObject layout = plan.optJSONObject("layout");
        if (layout == null) {
            root.addView(empty(context, "当前方案尚未设置教室布局"));
            return root;
        }
        int rows = layout.optInt("rows");
        int cols = layout.optInt("cols");
        String version = plan.optString("version");
        if (version.isEmpty()) version = String.valueOf(plan.optInt("id"));
        String detail = "v" + version + " · " + rows + "排 × " + cols + "列";
        if (!plan.optString("reason").isEmpty()) detail += "\n调整原因：" + plan.optString("reason");
        root.addView(infoCard(context, "当前座位方案", detail));

        Map<String, JSONObject> assignments = new HashMap<>();
        JSONArray assignmentRows = data.optJSONArray("assignments");
        if (assignmentRows != null) for (int i = 0; i < assignmentRows.length(); i++) {
            JSONObject row = assignmentRows.optJSONObject(i);
            if (row != null) assignments.put(row.optInt("row") + "_" + row.optInt("col"), row);
        }
        Set<Integer> aisles = integerSet(layout.optJSONArray("aisle_positions"));
        TableLayout table = new TableLayout(context);
        boolean reverse = "back".equals(layout.optString("podium_position"));
        for (int index = 0; index < rows; index++) {
            int rowNumber = reverse ? rows - index - 1 : index;
            TableRow tableRow = new TableRow(context);
            tableRow.addView(cell(context, String.valueOf(rowNumber + 1), -28, HEADER, true, 44));
            for (int col = 0; col < cols; col++) {
                JSONObject assignment = assignments.get(rowNumber + "_" + col);
                String name = assignment == null ? "空座" : assignment.optString("student_name");
                String meta = assignment == null ? "" : seatMeta(assignment);
                int background = assignment == null ? Color.rgb(248, 250, 252) : genderColor(assignment.optString("student_gender"));
                tableRow.addView(cell(context, name + (meta.isEmpty() ? "" : "\n" + meta), -52, background, assignment != null, 44));
                if (aisles.contains(col + 1)) tableRow.addView(spacer(context, 12));
            }
            tableRow.addView(cell(context, String.valueOf(rowNumber + 1), -28, HEADER, true, 44));
            table.addView(tableRow);
        }
        LinearLayout area = vertical(context);
        area.addView(table);
        TextView podium = cell(context, "讲台（教师视角）", Math.max(220, 56 + cols * 56 + aisles.size() * 12), Color.rgb(248, 250, 252), true, 40);
        LinearLayout.LayoutParams podiumParams = new LinearLayout.LayoutParams(podium.getLayoutParams());
        podiumParams.topMargin = Ui.dp(context, 12);
        podium.setLayoutParams(podiumParams);
        area.addView(podium);
        root.addView(horizontal(context, area));
        return root;
    }

    private static View dutyRoster(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONObject roster = data.optJSONObject("roster");
        if (roster == null) {
            root.addView(empty(context, "暂无值日生安排"));
            return root;
        }
        root.addView(infoCard(context, roster.optString("name"), roster.optString("date_start") + " 至 " + roster.optString("date_end")));
        JSONArray taskRows = data.optJSONArray("tasks");
        JSONArray entryRows = data.optJSONArray("entries");
        List<JSONObject> tasks = new ArrayList<>();
        if (taskRows != null) for (int i = 0; i < taskRows.length(); i++) if (taskRows.optJSONObject(i) != null) tasks.add(taskRows.optJSONObject(i));
        if (tasks.isEmpty()) {
            root.addView(empty(context, "当前方案尚未设置值日任务"));
            return root;
        }
        Map<String, List<String>> students = new HashMap<>();
        Map<Integer, String> dates = new HashMap<>();
        if (entryRows != null) for (int i = 0; i < entryRows.length(); i++) {
            JSONObject entry = entryRows.optJSONObject(i);
            if (entry == null) continue;
            int day = entry.optInt("day_index");
            dates.put(day, entry.optString("date"));
            String key = day + "_" + entry.optInt("task_id");
            if (!students.containsKey(key)) students.put(key, new ArrayList<>());
            students.get(key).add(entry.optString("student_name"));
        }
        int dayCount = roster.optInt("day_count");
        TableLayout table = new TableLayout(context);
        TableRow header = new TableRow(context);
        header.addView(cell(context, "日期", 122, HEADER, true, 64));
        for (JSONObject task : tasks) {
            String count = task.optInt("people_count") > 0 ? "\n（" + task.optInt("people_count") + "人）" : "";
            header.addView(cell(context, task.optString("name") + count, 132, HEADER, true, 64));
        }
        table.addView(header);
        for (int day = 0; day < dayCount; day++) {
            TableRow row = new TableRow(context);
            String date = dates.get(day);
            if (date == null || date.isEmpty()) date = offsetDate(roster.optString("date_start"), day);
            row.addView(cell(context, dateLabel(date), 122, Color.rgb(248, 250, 252), true, 70));
            for (JSONObject task : tasks) {
                List<String> names = students.get(day + "_" + task.optInt("id"));
                row.addView(cell(context, names == null || names.isEmpty() ? "—" : join(names), 132, Color.WHITE, false, 70));
            }
            table.addView(row);
        }
        root.addView(horizontal(context, table));
        return root;
    }

    private static LinearLayout vertical(Context context) {
        LinearLayout layout = new LinearLayout(context);
        layout.setOrientation(LinearLayout.VERTICAL);
        return layout;
    }

    private static HorizontalScrollView horizontal(Context context, View child) {
        HorizontalScrollView scroll = new HorizontalScrollView(context);
        scroll.setFillViewport(false);
        scroll.setHorizontalScrollBarEnabled(true);
        scroll.addView(child);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(context, 10), 0, Ui.dp(context, 12));
        scroll.setLayoutParams(params);
        return scroll;
    }

    private static TextView cell(Context context, String text, int widthDp, int background, boolean strong, int minHeightDp) {
        TextView view = new TextView(context);
        view.setText(text == null ? "" : text);
        view.setTextSize(14);
        view.setTextColor(context.getColor(R.color.text_primary));
        view.setGravity(Gravity.CENTER);
        view.setPadding(Ui.dp(context, 5), Ui.dp(context, 6), Ui.dp(context, 5), Ui.dp(context, 6));
        view.setMinHeight(Ui.dp(context, minHeightDp));
        if (strong) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setBackground(box(background, 0));
        view.setLayoutParams(new TableRow.LayoutParams(
            widthDp > 0 ? Ui.dp(context, widthDp) : ViewGroup.LayoutParams.WRAP_CONTENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ));
        if (widthDp < 0) view.setMinWidth(Ui.dp(context, -widthDp));
        return view;
    }

    private static View spacer(Context context, int widthDp) {
        View view = new View(context);
        view.setBackgroundColor(Color.WHITE);
        view.setLayoutParams(new TableRow.LayoutParams(Ui.dp(context, widthDp), 1));
        return view;
    }

    private static View infoCard(Context context, String title, String detail) {
        LinearLayout card = new LinearLayout(context);
        card.setOrientation(LinearLayout.VERTICAL);
        card.setBackgroundResource(R.drawable.bg_card);
        card.addView(Ui.title(context, title));
        TextView text = Ui.text(context, detail);
        text.setTextColor(MUTED);
        card.addView(text);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, 0, 0, Ui.dp(context, 8));
        card.setLayoutParams(params);
        return card;
    }

    private static TextView empty(Context context, String text) {
        TextView view = Ui.text(context, text);
        view.setGravity(Gravity.CENTER);
        view.setTextColor(MUTED);
        view.setPadding(Ui.dp(context, 12), Ui.dp(context, 36), Ui.dp(context, 12), Ui.dp(context, 36));
        view.setBackgroundResource(R.drawable.bg_card);
        return view;
    }

    private static GradientDrawable box(int color, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setStroke(1, BORDER);
        drawable.setCornerRadius(radiusDp);
        return drawable;
    }

    private static int courseColor(String course) {
        float hue = Math.abs(course.hashCode() % 360);
        return Color.HSVToColor(new float[]{hue, 0.16f, 0.98f});
    }

    private static int genderColor(String gender) {
        if ("male".equals(gender)) return Color.rgb(219, 234, 254);
        if ("female".equals(gender)) return Color.rgb(252, 231, 243);
        return Color.rgb(239, 246, 255);
    }

    private static String seatMeta(JSONObject assignment) {
        List<String> values = new ArrayList<>();
        String dormitory = assignment.optString("student_dormitory");
        if (!dormitory.isEmpty()) values.add(dormitory);
        if (assignment.optInt("student_height") > 0) values.add(assignment.optInt("student_height") + "cm");
        if (!assignment.optString("seat_requirement").isEmpty()) values.add("★");
        return join(values);
    }

    private static Set<Integer> integerSet(JSONArray values) {
        Set<Integer> result = new HashSet<>();
        if (values != null) for (int i = 0; i < values.length(); i++) result.add(values.optInt(i));
        return result;
    }

    private static String cleanTime(String value) {
        return value == null || value.isEmpty() || "null".equals(value) ? "" : value;
    }

    private static String weekdayName(int weekday) {
        String[] values = {"", "周一", "周二", "周三", "周四", "周五", "周六", "周日"};
        return weekday >= 1 && weekday <= 7 ? values[weekday] : "";
    }

    private static String offsetDate(String start, int days) {
        try { return LocalDate.parse(start).plusDays(days).toString(); }
        catch (Exception ignored) { return start; }
    }

    private static String dateLabel(String date) {
        try {
            LocalDate value = LocalDate.parse(date);
            return value.format(DateTimeFormatter.ofPattern("MM-dd")) + "\n" + weekdayName(value.getDayOfWeek().getValue());
        } catch (Exception ignored) {
            return date;
        }
    }

    private static String join(List<String> values) {
        StringBuilder result = new StringBuilder();
        for (String value : values) {
            if (value == null || value.isEmpty()) continue;
            if (result.length() > 0) result.append("、");
            result.append(value);
        }
        return result.toString();
    }

    private StructuredReportRenderer() {}
}
