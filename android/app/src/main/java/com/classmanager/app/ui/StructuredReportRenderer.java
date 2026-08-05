package com.classmanager.app.ui;

import android.app.AlertDialog;
import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
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
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;

final class StructuredReportRenderer {
    private static final int BORDER = 0xffcbd5e1;
    private static final int HEADER = 0xffe8f0fe;
    private static final int MUTED = 0xff64748b;

    static boolean supports(String endpoint) {
        return "course-schedule/".equals(endpoint) || "seating/".equals(endpoint) || "duty-roster/".equals(endpoint) ||
                "score-analysis/".equals(endpoint) || "student-score-analysis/".equals(endpoint) || "score-comparison/".equals(endpoint) ||
                "student-profile/".equals(endpoint) || "growth/".equals(endpoint) || "warnings/".equals(endpoint);
    }

    static View render(Context context, String endpoint, JSONObject data) {
        if ("student-profile/".equals(endpoint)) return studentProfile(context, data);
        if ("growth/".equals(endpoint)) return growth(context, data);
        if ("warnings/".equals(endpoint)) return warnings(context, data);
        if ("course-schedule/".equals(endpoint)) return courseSchedule(context, data);
        if ("seating/".equals(endpoint)) return seating(context, data);
        if ("score-analysis/".equals(endpoint)) return scoreAnalysis(context, data);
        if ("student-score-analysis/".equals(endpoint)) return studentScoreAnalysis(context, data);
        if ("score-comparison/".equals(endpoint)) return scoreComparison(context, data);
        return dutyRoster(context, data);
    }

    private static View studentProfile(Context context, JSONObject data) {
        JSONObject student = data.optJSONObject("student");
        LinearLayout information = vertical(context);
        if (student == null) return empty(context, "暂无学生档案");
        JSONObject summary = data.optJSONObject("summary");
        if (summary != null) information.addView(infoCard(context, student.optString("name") + " · 档案概览",
                "成长事件 " + summary.optInt("growth_event_count") + " 条    成绩记录 " + summary.optInt("score_count") + " 条\n" +
                "谈话记录 " + summary.optInt("conversation_count") + " 条    积分 " + number(summary, "point_total")));
        addDetail(context, information, "姓名", student.optString("name"));
        addDetail(context, information, "性别", first(student.optString("gender_display"), chineseStatus(student.optString("gender"))));
        addDetail(context, information, "班级", student.optString("school_class_label"));
        addDetail(context, information, "出生日期", student.optString("birth_date"));
        addDetail(context, information, "身高", student.isNull("height") ? "" : number(student, "height") + " cm");
        addDetail(context, information, "视力情况", student.optString("vision"));
        addDetail(context, information, "特殊座位需求", student.optString("seat_requirement"));
        addDetail(context, information, "班级职务", first(student.optString("display_class_position"), student.optString("class_position")));
        addDetail(context, information, "家庭住址", student.optString("home_address"));
        addDetail(context, information, "团员情况", student.optBoolean("is_league_member") ? "团员" : "非团员");
        addDetail(context, information, "住宿情况", student.optBoolean("is_boarder") ? "住校" : "走读");
        if (student.optBoolean("is_boarder")) {
            addDetail(context, information, "宿舍", first(student.optString("display_dormitory"), student.optString("dormitory")));
            addDetail(context, information, "床位", first(student.optString("display_bed_number"), student.optString("bed_number")));
        }
        addDetail(context, information, "主要联系人", first(student.optString("display_primary_contact"), student.optString("primary_contact")));
        addDetail(context, information, "联系电话", first(student.optString("display_primary_phone"), student.optString("primary_phone")));
        addDetail(context, information, "备用联系人", student.optString("secondary_contact"));
        addDetail(context, information, "备用电话", student.optString("secondary_phone"));
        addDetail(context, information, "备注", student.optString("remarks"));
        JSONObject guardian = data.optJSONObject("guardian");
        if (guardian != null) {
            information.addView(Ui.title(context, "家长联系方式"));
            addDetail(context, information, "父亲", contact(guardian.optString("father_name"), guardian.optString("father_phone")));
            addDetail(context, information, "母亲", contact(guardian.optString("mother_name"), guardian.optString("mother_phone")));
            addDetail(context, information, "其他监护人", guardian.optString("other_guardian"));
            addDetail(context, information, "主要联系人", guardian.optString("primary_contact_display"));
            addDetail(context, information, "家庭地址", guardian.optString("home_address"));
            addDetail(context, information, "备注", guardian.optString("remarks"));
        }

        LinearLayout latest = vertical(context);
        JSONArray exams = data.optJSONArray("latest_exams");
        if (exams == null || exams.length() == 0) latest.addView(empty(context, "暂无最近成绩"));
        for (int i = 0; exams != null && i < exams.length(); i++) {
            JSONObject exam = exams.optJSONObject(i);
            TextView row = Ui.text(context, exam.optString("exam") + "    " + exam.optString("date") + "\n" +
                    "总分：" + number(exam, "total_score") + "    总排名：" + rank(exam, "class_rank"));
            row.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            row.setPadding(Ui.dp(context, 12), Ui.dp(context, 10), Ui.dp(context, 12), Ui.dp(context, 10));
            row.setBackground(Ui.rounded(context, Color.WHITE, BORDER, 8));
            row.setOnClickListener(view -> showSubjectDetails(context, exam.optString("exam") + " · 成绩详情", exam.optJSONArray("subjects")));
            LinearLayout.LayoutParams params = cardParams(context);
            latest.addView(row, params);
        }

        LinearLayout growth = eventList(context, data.optJSONArray("growth_events"));
        LinearLayout conversations = compactRecords(context, data.optJSONArray("conversations"), "reason", "date",
                new String[][]{{"date", "日期"}, {"reason", "谈话原因"}, {"main_content", "主要内容"},
                        {"student_feedback", "学生反馈"}, {"follow_up_actions", "后续措施"}});
        LinearLayout comments = compactRecords(context, data.optJSONArray("comments"), "type", "created_at",
                new String[][]{{"type", "类型"}, {"content", "内容"}, {"status", "状态"}, {"created_at", "创建时间"}});
        return tabbed(context, new String[]{"信息", "最近成绩", "成长事件", "谈话", "评语"},
                new View[]{information, latest, growth, conversations, comments});
    }

    private static View growth(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONObject student = data.optJSONObject("student");
        if (student != null) root.addView(infoCard(context, student.optString("name") + " · 成长足迹",
                "点击条目可查看详细信息"));
        root.addView(eventList(context, data.optJSONArray("events")));
        return root;
    }

    private static View warnings(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONArray students = data.optJSONArray("students");
        if (students == null || students.length() == 0) return empty(context, "当前没有满足预警条件的学生");
        for (int i = 0; i < students.length(); i++) {
            JSONObject student = students.optJSONObject(i);
            TextView row = Ui.text(context, student.optString("student_name"));
            row.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            row.setTextSize(16);
            row.setPadding(Ui.dp(context, 14), Ui.dp(context, 12), Ui.dp(context, 14), Ui.dp(context, 12));
            row.setBackground(Ui.rounded(context, 0xfffffbeb, 0xfff59e0b, 8));
            row.setOnClickListener(view -> showWarningDetails(context, student));
            root.addView(row, cardParams(context));
        }
        return root;
    }

    private static View scoreAnalysis(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONObject exam = data.optJSONObject("exam");
        if (exam == null) return empty(context, "暂无可分析的考试数据");
        root.addView(infoCard(context, exam.optString("name"), exam.optString("date")));
        JSONObject total = data.optJSONObject("total");
        if (total != null) root.addView(infoCard(context, "总分概览", "参考人数：" + total.optInt("count") + "    平均分：" + number(total, "avg") + "    最高分：" + number(total, "max")));

        JSONArray subjects = data.optJSONArray("subjects");
        TableLayout subjectTable = new TableLayout(context);
        TableRow subjectHeader = new TableRow(context);
        String[] subjectLabels = {"科目", "满分", "人数", "平均", "最高", "最低", "及格率", "优秀率"};
        for (String label : subjectLabels) subjectHeader.addView(cell(context, label, 76, HEADER, true, 44));
        subjectTable.addView(subjectHeader);
        for (int i = 0; subjects != null && i < subjects.length(); i++) {
            JSONObject subject = subjects.optJSONObject(i);
            TableRow row = new TableRow(context);
            row.addView(cell(context, subject.optString("name"), 76, Color.WHITE, true, 44));
            row.addView(cell(context, number(subject, "full_score"), 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(subject, "count"), 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(subject, "avg"), 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(subject, "max"), 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(subject, "min"), 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(subject, "pass_rate") + "%", 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(subject, "excellent_rate") + "%", 76, Color.WHITE, false, 44));
            subjectTable.addView(row);
        }
        root.addView(infoCard(context, "科目统计", "横向滑动查看完整指标"));
        root.addView(horizontal(context, subjectTable));

        JSONArray students = data.optJSONArray("students");
        TableLayout studentTable = new TableLayout(context);
        TableRow studentHeader = new TableRow(context);
        studentHeader.addView(cell(context, "名次", 58, HEADER, true, 44));
        studentHeader.addView(cell(context, "姓名", 92, HEADER, true, 44));
        studentHeader.addView(cell(context, "总分", 76, HEADER, true, 44));
        studentHeader.addView(cell(context, "年级名次", 82, HEADER, true, 44));
        studentHeader.addView(cell(context, "市名次", 76, HEADER, true, 44));
        studentTable.addView(studentHeader);
        for (int i = 0; students != null && i < students.length(); i++) {
            JSONObject student = students.optJSONObject(i);
            TableRow row = new TableRow(context);
            row.addView(cell(context, number(student, "rank"), 58, Color.WHITE, true, 44));
            row.addView(cell(context, student.optString("student_name"), 92, Color.WHITE, true, 44));
            row.addView(cell(context, number(student, "total_score"), 76, Color.WHITE, false, 44));
            row.addView(cell(context, number(student, "grade_rank"), 82, Color.WHITE, false, 44));
            row.addView(cell(context, number(student, "city_rank"), 76, Color.WHITE, false, 44));
            row.setOnClickListener(view -> showSubjectDetails(context,
                    student.optString("student_name") + " · 各科成绩与排名", student.optJSONArray("subject_details")));
            studentTable.addView(row);
        }
        root.addView(infoCard(context, "学生总成绩", "共 " + (students == null ? 0 : students.length()) + " 人"));
        root.addView(horizontal(context, studentTable));
        return root;
    }

    private static View studentScoreAnalysis(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONObject student = data.optJSONObject("student");
        root.addView(infoCard(context, student == null ? "学生成绩趋势" : student.optString("name"), "历次考试成绩与名次"));
        JSONArray history = data.optJSONArray("history");
        if (history == null || history.length() == 0) {
            root.addView(empty(context, "该学生暂无成绩记录"));
            return root;
        }
        TableLayout table = new TableLayout(context);
        TableRow header = new TableRow(context);
        String[] labels = {"日期", "考试", "总分", "班名次", "年级名次", "市名次"};
        int[] widths = {92, 110, 72, 72, 82, 72};
        for (int i = 0; i < labels.length; i++) header.addView(cell(context, labels[i], widths[i], HEADER, true, 48));
        table.addView(header);
        for (int i = 0; i < history.length(); i++) {
            JSONObject item = history.optJSONObject(i);
            TableRow row = new TableRow(context);
            row.addView(cell(context, item.optString("date"), widths[0], Color.WHITE, false, 48));
            row.addView(cell(context, item.optString("exam"), widths[1], Color.WHITE, true, 48));
            row.addView(cell(context, number(item, "total"), widths[2], Color.WHITE, true, 48));
            row.addView(cell(context, number(item, "class_rank"), widths[3], Color.WHITE, false, 48));
            row.addView(cell(context, number(item, "grade_rank"), widths[4], Color.WHITE, false, 48));
            row.addView(cell(context, number(item, "city_rank"), widths[5], Color.WHITE, false, 48));
            table.addView(row);
        }
        equalizeRows(table);
        root.addView(Ui.title(context, "总成绩表"));
        root.addView(horizontal(context, table));
        addTrendCharts(context, root, history);
        for (String subjectName : subjectNames(history)) {
            TableLayout subjectTable = new TableLayout(context);
            TableRow subjectHeader = new TableRow(context);
            String[] subjectLabels = {"日期", "考试", "成绩", "班名次", "年级名次", "市名次"};
            for (int i = 0; i < subjectLabels.length; i++)
                subjectHeader.addView(cell(context, subjectLabels[i], widths[i], HEADER, true, 48));
            subjectTable.addView(subjectHeader);
            for (int i = 0; i < history.length(); i++) {
                JSONObject item = history.optJSONObject(i);
                JSONObject subject = findSubject(item.optJSONArray("subjects"), subjectName);
                TableRow row = new TableRow(context);
                row.addView(cell(context, item.optString("date"), widths[0], Color.WHITE, false, 48));
                row.addView(cell(context, item.optString("exam"), widths[1], Color.WHITE, true, 48));
                row.addView(cell(context, scoreValue(subject), widths[2], Color.WHITE, true, 48));
                row.addView(cell(context, number(subject, "rank"), widths[3], Color.WHITE, false, 48));
                row.addView(cell(context, number(subject, "grade_rank"), widths[4], Color.WHITE, false, 48));
                row.addView(cell(context, number(subject, "city_rank"), widths[5], Color.WHITE, false, 48));
                subjectTable.addView(row);
            }
            equalizeRows(subjectTable);
            root.addView(Ui.title(context, subjectName + "成绩表"));
            root.addView(horizontal(context, subjectTable));
        }
        return root;
    }

    private static View scoreComparison(Context context, JSONObject data) {
        LinearLayout root = vertical(context);
        JSONObject exam = data.optJSONObject("exam");
        if (exam == null) return empty(context, "暂无可对比的考试数据");
        root.addView(infoCard(context, exam.optString("name"), exam.optString("date")));
        JSONArray classes = data.optJSONArray("classes");
        JSONArray comparison = data.optJSONArray("comparison");
        TableLayout table = new TableLayout(context);
        TableRow header = new TableRow(context);
        header.addView(cell(context, "科目", 84, HEADER, true, 54));
        header.addView(cell(context, "满分", 64, HEADER, true, 54));
        for (int i = 0; classes != null && i < classes.length(); i++)
            header.addView(cell(context, classes.optJSONObject(i).optString("name") + "\n人数 / 均分 / 最高 / 最低", 154, HEADER, true, 54));
        table.addView(header);
        for (int i = 0; comparison != null && i < comparison.length(); i++) {
            JSONObject item = comparison.optJSONObject(i);
            JSONObject values = item.optJSONObject("classes");
            TableRow row = new TableRow(context);
            row.addView(cell(context, item.optString("subject"), 84, Color.WHITE, true, 54));
            row.addView(cell(context, number(item, "full_score"), 64, Color.WHITE, false, 54));
            for (int j = 0; classes != null && j < classes.length(); j++) {
                JSONObject entry = classes.optJSONObject(j);
                JSONObject stats = values == null ? null : values.optJSONObject(entry.optString("key"));
                String value = stats == null ? "—" : number(stats, "count") + " / " + number(stats, "avg") + " / " + number(stats, "max") + " / " + number(stats, "min");
                row.addView(cell(context, value, 154, Color.WHITE, false, 54));
            }
            table.addView(row);
        }
        equalizeRows(table);
        root.addView(horizontal(context, table));
        return root;
    }

    private static String number(JSONObject object, String key) {
        if (object == null || object.isNull(key)) return "—";
        Object value = object.opt(key);
        if (value instanceof Double) {
            double number = (Double) value;
            if (number == Math.rint(number)) return String.valueOf((long) number);
        }
        return String.valueOf(value);
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
        equalizeRows(table);
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
        equalizeRows(table);
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
        equalizeRows(table);
        root.addView(horizontal(context, table));
        return root;
    }

    private static View tabbed(Context context, String[] labels, View[] panels) {
        LinearLayout root = vertical(context);
        LinearLayout tabBar = new LinearLayout(context);
        tabBar.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout content = vertical(context);
        Button[] buttons = new Button[labels.length];
        for (int i = 0; i < labels.length; i++) {
            int index = i;
            Button button = Ui.outlineButton(context, labels[i]);
            LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            params.setMargins(0, 0, Ui.dp(context, 6), 0);
            button.setLayoutParams(params);
            button.setMinWidth(Ui.dp(context, 76));
            button.setOnClickListener(view -> {
                content.removeAllViews();
                content.addView(panels[index]);
                for (int j = 0; j < buttons.length; j++) {
                    buttons[j].setTextColor(j == index ? Color.WHITE : context.getColor(R.color.primary));
                    buttons[j].setBackground(Ui.rounded(context,
                            j == index ? context.getColor(R.color.primary) : Color.WHITE,
                            context.getColor(R.color.primary), 10));
                }
            });
            buttons[i] = button;
            tabBar.addView(button);
        }
        HorizontalScrollView scroll = new HorizontalScrollView(context);
        scroll.setHorizontalScrollBarEnabled(false);
        scroll.addView(tabBar);
        root.addView(scroll);
        if (panels.length > 0) content.addView(panels[0]);
        root.addView(content);
        if (buttons.length > 0) {
            buttons[0].setTextColor(Color.WHITE);
            buttons[0].setBackground(Ui.rounded(context, context.getColor(R.color.primary), context.getColor(R.color.primary), 10));
        }
        return root;
    }

    private static LinearLayout eventList(Context context, JSONArray events) {
        LinearLayout root = vertical(context);
        if (events == null || events.length() == 0) {
            root.addView(empty(context, "暂无成长事件"));
            return root;
        }
        for (int i = 0; i < events.length(); i++) {
            JSONObject event = events.optJSONObject(i);
            if (event == null) continue;
            String module = event.optString("module");
            String title = event.optString("item");
            String points = event.optInt("points") == 0 ? "" : "    积分 " + signed(event.optInt("points"));
            TextView row = Ui.text(context, (isBlank(module) ? "" : module + " · ") + title + "\n" + event.optString("date") + points);
            row.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            row.setTextColor(event.optBoolean("adverse") ? 0xffb91c1c : 0xff1d4ed8);
            row.setPadding(Ui.dp(context, 12), Ui.dp(context, 9), Ui.dp(context, 12), Ui.dp(context, 9));
            row.setBackground(Ui.rounded(context, event.optBoolean("adverse") ? 0xfffff1f2 : 0xffeff6ff,
                    event.optBoolean("adverse") ? 0xfffecaca : 0xffbfdbfe, 8));
            row.setOnClickListener(view -> showEventDetails(context, event));
            root.addView(row, cardParams(context));
        }
        return root;
    }

    private static LinearLayout compactRecords(Context context, JSONArray rows, String titleKey, String dateKey, String[][] fields) {
        LinearLayout root = vertical(context);
        if (rows == null || rows.length() == 0) {
            root.addView(empty(context, "暂无记录"));
            return root;
        }
        for (int i = 0; i < rows.length(); i++) {
            JSONObject item = rows.optJSONObject(i);
            String title = item == null ? "" : item.optString(titleKey);
            if (isBlank(title)) title = "记录详情";
            TextView row = Ui.text(context, title + "\n" + item.optString(dateKey));
            row.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            row.setPadding(Ui.dp(context, 12), Ui.dp(context, 9), Ui.dp(context, 12), Ui.dp(context, 9));
            row.setBackground(Ui.rounded(context, Color.WHITE, BORDER, 8));
            String dialogTitle = title;
            row.setOnClickListener(view -> showRecordDetails(context, dialogTitle, item, fields));
            root.addView(row, cardParams(context));
        }
        return root;
    }

    private static void showEventDetails(Context context, JSONObject event) {
        LinearLayout details = vertical(context);
        addDetail(context, details, "模块", event.optString("module"));
        addDetail(context, details, "条目", event.optString("item"));
        addDetail(context, details, "日期", event.optString("date"));
        if (event.optInt("points") != 0) addDetail(context, details, "积分", signed(event.optInt("points")));
        addDetail(context, details, "备注", event.optString("note"));
        showDialog(context, event.optString("item", "成长事件详情"), details);
    }

    private static void showRecordDetails(Context context, String title, JSONObject item, String[][] fields) {
        LinearLayout details = vertical(context);
        for (String[] field : fields) addDetail(context, details, field[1], item.optString(field[0]));
        showDialog(context, title, details);
    }

    private static void showWarningDetails(Context context, JSONObject student) {
        LinearLayout details = vertical(context);
        JSONArray warnings = student.optJSONArray("warnings");
        for (int i = 0; warnings != null && i < warnings.length(); i++) {
            JSONObject warning = warnings.optJSONObject(i);
            String unit = "points".equals(warning.optString("unit")) ? "分" : "次";
            details.addView(Ui.title(context, warning.optString("rule") + "（" + number(warning, "value") + unit + "）"));
            JSONArray events = warning.optJSONArray("events");
            TableLayout table = new TableLayout(context);
            TableRow header = new TableRow(context);
            String[] labels = {"日期", "条目", "扣分", "备注"};
            int[] widths = {92, 150, 64, 180};
            for (int j = 0; j < labels.length; j++) header.addView(cell(context, labels[j], widths[j], HEADER, true, 44));
            table.addView(header);
            for (int j = 0; events != null && j < events.length(); j++) {
                JSONObject event = events.optJSONObject(j);
                TableRow row = new TableRow(context);
                row.addView(cell(context, event.optString("date"), widths[0], Color.WHITE, false, 44));
                row.addView(cell(context, event.optString("item"), widths[1], Color.WHITE, true, 44));
                row.addView(cell(context, event.optInt("points") == 0 ? "—" : signed(event.optInt("points")), widths[2], Color.WHITE, false, 44));
                row.addView(cell(context, emptyDash(event.optString("note")), widths[3], Color.WHITE, false, 44));
                table.addView(row);
            }
            equalizeRows(table);
            details.addView(horizontal(context, table));
        }
        showDialog(context, student.optString("student_name") + " · 预警详情", details);
    }

    private static void showSubjectDetails(Context context, String title, JSONArray subjects) {
        TableLayout table = new TableLayout(context);
        TableRow header = new TableRow(context);
        String[] labels = {"科目", "满分", "成绩", "班名次", "年级名次", "市名次"};
        int[] widths = {90, 66, 76, 74, 82, 72};
        for (int i = 0; i < labels.length; i++) header.addView(cell(context, labels[i], widths[i], HEADER, true, 46));
        table.addView(header);
        for (int i = 0; subjects != null && i < subjects.length(); i++) {
            JSONObject subject = subjects.optJSONObject(i);
            TableRow row = new TableRow(context);
            row.addView(cell(context, first(subject.optString("subject"), subject.optString("name")), widths[0], Color.WHITE, true, 46));
            row.addView(cell(context, number(subject, "full_score"), widths[1], Color.WHITE, false, 46));
            row.addView(cell(context, scoreValue(subject), widths[2], Color.WHITE, true, 46));
            row.addView(cell(context, number(subject, subject.has("class_rank") ? "class_rank" : "rank"), widths[3], Color.WHITE, false, 46));
            row.addView(cell(context, number(subject, "grade_rank"), widths[4], Color.WHITE, false, 46));
            row.addView(cell(context, number(subject, "city_rank"), widths[5], Color.WHITE, false, 46));
            table.addView(row);
        }
        if (subjects == null || subjects.length() == 0) {
            TableRow row = new TableRow(context);
            row.addView(cell(context, "暂无科目明细", 460, Color.WHITE, false, 48));
            table.addView(row);
        }
        equalizeRows(table);
        showDialog(context, title, horizontal(context, table));
    }

    private static void showDialog(Context context, String title, View content) {
        ScrollView scroll = new ScrollView(context);
        scroll.addView(content);
        new AlertDialog.Builder(context).setTitle(title).setView(scroll).setPositiveButton("关闭", null).show();
    }

    private static void addDetail(Context context, LinearLayout parent, String label, String value) {
        if (isBlank(value)) return;
        LinearLayout row = new LinearLayout(context);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(Ui.dp(context, 10), Ui.dp(context, 8), Ui.dp(context, 10), Ui.dp(context, 8));
        row.setBackground(Ui.rounded(context, Color.WHITE, 0xffe2e8f0, 0));
        TextView name = Ui.text(context, label);
        name.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        name.setTextColor(0xff475569);
        TextView content = Ui.text(context, value);
        row.addView(name, new LinearLayout.LayoutParams(Ui.dp(context, 108), ViewGroup.LayoutParams.WRAP_CONTENT));
        row.addView(content, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1));
        parent.addView(row);
    }

    private static void addTrendCharts(Context context, LinearLayout root, JSONArray history) {
        List<String> labels = new ArrayList<>();
        List<Float> totals = new ArrayList<>();
        List<Float> totalRanks = new ArrayList<>();
        Map<String, List<Float>> scores = new LinkedHashMap<>();
        Map<String, List<Float>> ranks = new LinkedHashMap<>();
        for (int i = 0; i < history.length(); i++) {
            JSONObject exam = history.optJSONObject(i);
            labels.add(exam.optString("exam") + "\n" + exam.optString("date"));
            totals.add(nullableNumber(exam, "total"));
            totalRanks.add(nullableNumber(exam, "class_rank"));
            for (List<Float> values : scores.values()) values.add(null);
            for (List<Float> values : ranks.values()) values.add(null);
            JSONArray subjects = exam.optJSONArray("subjects");
            for (int j = 0; subjects != null && j < subjects.length(); j++) {
                JSONObject subject = subjects.optJSONObject(j);
                String name = subject.optString("subject");
                if (!scores.containsKey(name)) {
                    scores.put(name, nullValues(i + 1));
                    ranks.put(name, nullValues(i + 1));
                }
                scores.get(name).set(i, nullableNumber(subject, "score"));
                ranks.get(name).set(i, nullableNumber(subject, "rank"));
            }
        }
        if (hasValue(totals)) root.addView(chartCard(context, "总分变化曲线",
                new TrendChartView(context, labels, java.util.Collections.singletonList(
                        new TrendChartView.Series("总分", 0xff1a73e8, totals)), false)));
        if (hasValue(totalRanks)) root.addView(chartCard(context, "总排名变化曲线（越低越好）",
                new TrendChartView(context, labels, java.util.Collections.singletonList(
                        new TrendChartView.Series("总排名", 0xffdc3545, totalRanks)), true)));
        int[] colors = {0xff1a73e8, 0xffdc3545, 0xff28a745, 0xffff9800, 0xff6f42c1, 0xff20c997, 0xffe83e8c, 0xff0dcaf0};
        List<TrendChartView.Series> scoreSeries = new ArrayList<>();
        List<TrendChartView.Series> rankSeries = new ArrayList<>();
        int index = 0;
        for (String name : scores.keySet()) {
            int color = colors[index++ % colors.length];
            if (hasValue(scores.get(name))) scoreSeries.add(new TrendChartView.Series(name, color, scores.get(name)));
            if (hasValue(ranks.get(name))) rankSeries.add(new TrendChartView.Series(name, color, ranks.get(name)));
        }
        if (!scoreSeries.isEmpty()) root.addView(chartCard(context, "各科成绩变化曲线",
                new TrendChartView(context, labels, scoreSeries, false)));
        if (!rankSeries.isEmpty()) root.addView(chartCard(context, "各科排名变化曲线（越低越好）",
                new TrendChartView(context, labels, rankSeries, true)));
    }

    private static View chartCard(Context context, String title, View chart) {
        LinearLayout card = vertical(context);
        card.setPadding(Ui.dp(context, 12), Ui.dp(context, 8), Ui.dp(context, 12), Ui.dp(context, 8));
        card.setBackgroundResource(R.drawable.bg_card);
        card.addView(Ui.title(context, title));
        card.addView(chart, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(context, 250)));
        return card;
    }

    private static Set<String> subjectNames(JSONArray history) {
        Set<String> names = new LinkedHashSet<>();
        for (int i = 0; history != null && i < history.length(); i++) {
            JSONArray subjects = history.optJSONObject(i).optJSONArray("subjects");
            for (int j = 0; subjects != null && j < subjects.length(); j++) names.add(subjects.optJSONObject(j).optString("subject"));
        }
        names.remove("");
        return names;
    }

    private static JSONObject findSubject(JSONArray subjects, String name) {
        for (int i = 0; subjects != null && i < subjects.length(); i++) {
            JSONObject subject = subjects.optJSONObject(i);
            if (subject != null && name.equals(subject.optString("subject"))) return subject;
        }
        return null;
    }

    private static String scoreValue(JSONObject subject) {
        if (subject == null) return "—";
        if (!subject.isNull("score")) return number(subject, "score");
        return first(subject.optString("status_display"), chineseStatus(subject.optString("status")), "—");
    }

    private static Float nullableNumber(JSONObject object, String key) {
        if (object == null || object.isNull(key)) return null;
        Object value = object.opt(key);
        if (value instanceof Number) return ((Number) value).floatValue();
        try { return Float.parseFloat(String.valueOf(value)); }
        catch (Exception ignored) { return null; }
    }

    private static List<Float> nullValues(int size) {
        List<Float> values = new ArrayList<>();
        for (int i = 0; i < size; i++) values.add(null);
        return values;
    }

    private static boolean hasValue(List<Float> values) {
        for (Float value : values) if (value != null) return true;
        return false;
    }

    private static LinearLayout.LayoutParams cardParams(Context context) {
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, Ui.dp(context, 5), 0, Ui.dp(context, 5));
        return params;
    }

    private static String contact(String name, String phone) {
        if (isBlank(name)) return phone;
        return isBlank(phone) ? name : name + "（" + phone + "）";
    }

    private static String rank(JSONObject object, String key) {
        String value = number(object, key);
        return "—".equals(value) ? value : "第" + value + "名";
    }

    private static String signed(int value) { return value > 0 ? "+" + value : String.valueOf(value); }

    private static String emptyDash(String value) { return isBlank(value) ? "—" : value; }

    private static boolean isBlank(String value) {
        return value == null || value.trim().isEmpty() || "null".equalsIgnoreCase(value.trim());
    }

    private static String first(String... values) {
        for (String value : values) if (!isBlank(value)) return value;
        return "";
    }

    private static String chineseStatus(String value) {
        if ("male".equals(value)) return "男";
        if ("female".equals(value)) return "女";
        if ("normal".equals(value)) return "正常";
        if ("absent".equals(value)) return "缺考";
        if ("deferred".equals(value)) return "缓考";
        if ("exempted".equals(value)) return "免考";
        if ("invalid".equals(value)) return "成绩无效";
        if ("other".equals(value)) return "其他";
        return value;
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
            ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        if (widthDp < 0) view.setMinWidth(Ui.dp(context, -widthDp));
        return view;
    }

    private static void equalizeRows(TableLayout table) {
        for (int rowIndex = 0; rowIndex < table.getChildCount(); rowIndex++) {
            View child = table.getChildAt(rowIndex);
            if (child instanceof TableRow) {
                ((TableRow) child).setBaselineAligned(false);
                ((TableRow) child).setGravity(Gravity.TOP);
            }
        }
        table.post(() -> {
            for (int rowIndex = 0; rowIndex < table.getChildCount(); rowIndex++) {
                View child = table.getChildAt(rowIndex);
                if (!(child instanceof TableRow)) continue;
                TableRow row = (TableRow) child;
                row.setBaselineAligned(false);
                row.setGravity(Gravity.TOP);
                int height = 0;
                for (int column = 0; column < row.getChildCount(); column++)
                    height = Math.max(height, row.getChildAt(column).getMeasuredHeight());
                for (int column = 0; column < row.getChildCount(); column++) {
                    row.getChildAt(column).setMinimumHeight(height);
                    row.getChildAt(column).getLayoutParams().height = height;
                }
                row.requestLayout();
            }
        });
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
