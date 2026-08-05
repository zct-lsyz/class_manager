package com.classmanager.app.ui;

import android.content.Context;
import android.app.DatePickerDialog;
import android.app.TimePickerDialog;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Spinner;
import android.widget.TextView;

import com.classmanager.app.R;

import java.time.LocalDate;
import java.time.LocalTime;

public final class Ui {
    private Ui() {}

    public static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    public static LinearLayout vertical(Context context) {
        LinearLayout layout = new LinearLayout(context);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(dp(context, 16), dp(context, 16), dp(context, 16), dp(context, 16));
        return layout;
    }

    public static TextView title(Context context, String value) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(20);
        view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setTextColor(context.getColor(R.color.text_primary));
        view.setPadding(0, dp(context, 8), 0, dp(context, 8));
        return view;
    }

    public static TextView text(Context context, String value) {
        TextView view = new TextView(context);
        view.setText(value);
        view.setTextSize(15);
        view.setTextColor(0xff34495e);
        view.setLineSpacing(0, 1.15f);
        view.setPadding(0, dp(context, 4), 0, dp(context, 4));
        return view;
    }

    public static Button button(Context context, String value) {
        Button button = new Button(context);
        button.setText(value);
        button.setTextColor(Color.WHITE);
        button.setTextSize(15);
        button.setAllCaps(false);
        button.setMinHeight(dp(context, 44));
        button.setBackground(rounded(context, context.getColor(R.color.primary), 0, 10));
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, dp(context, 5), 0, dp(context, 5));
        button.setLayoutParams(params);
        return button;
    }

    public static Button outlineButton(Context context, String value) {
        Button button = button(context, value);
        button.setTextColor(context.getColor(R.color.primary));
        button.setBackground(rounded(context, Color.WHITE, context.getColor(R.color.primary), 10));
        return button;
    }

    public static void styleInput(Context context, EditText input) {
        input.setTextSize(15);
        input.setTextColor(context.getColor(R.color.text_primary));
        input.setHintTextColor(0xff94a3b8);
        input.setPadding(dp(context, 12), dp(context, 10), dp(context, 12), dp(context, 10));
        input.setMinHeight(dp(context, 46));
        input.setBackground(rounded(context, Color.WHITE, 0xffcbd5e1, 9));
    }

    public static void styleSpinner(Context context, Spinner spinner) {
        spinner.setPadding(dp(context, 10), dp(context, 5), dp(context, 10), dp(context, 5));
        spinner.setMinimumHeight(dp(context, 46));
        spinner.setBackground(rounded(context, Color.WHITE, 0xffcbd5e1, 9));
    }

    public static EditText temporalInput(Context context, String type, String value) {
        EditText input = new EditText(context);
        styleInput(context, input);
        input.setFocusable(false);
        input.setClickable(true);
        input.setHint("date".equals(type) ? "请选择日期" : "time".equals(type) ? "请选择时间" : "请选择日期和时间");
        if (value != null && !value.isEmpty() && !"null".equals(value)) {
            String display = value.replace('T', ' ');
            input.setText(display.substring(0, Math.min(display.length(), "date".equals(type) ? 10 : "time".equals(type) ? 5 : 16)));
        }
        input.setOnClickListener(view -> {
            if ("time".equals(type)) {
                showTimePicker(context, input, null);
                return;
            }
            LocalDate initial = LocalDate.now();
            String existing = input.getText().toString();
            try { if (existing.length() >= 10) initial = LocalDate.parse(existing.substring(0, 10)); } catch (Exception ignored) {}
            LocalDate selected = initial;
            new DatePickerDialog(context, (dialog, year, month, day) -> {
                String date = String.format(java.util.Locale.CHINA, "%04d-%02d-%02d", year, month + 1, day);
                if ("datetime".equals(type)) showTimePicker(context, input, date);
                else input.setText(date);
            }, selected.getYear(), selected.getMonthValue() - 1, selected.getDayOfMonth()).show();
        });
        input.setOnLongClickListener(view -> { input.setText(""); return true; });
        return input;
    }

    private static void showTimePicker(Context context, EditText input, String date) {
        LocalTime initial = LocalTime.now();
        String existing = input.getText().toString();
        try {
            int offset = existing.contains(" ") ? existing.indexOf(' ') + 1 : 0;
            if (existing.length() >= offset + 5) initial = LocalTime.parse(existing.substring(offset, offset + 5));
        } catch (Exception ignored) {}
        LocalTime selected = initial;
        new TimePickerDialog(context, (dialog, hour, minute) -> {
            String time = String.format(java.util.Locale.CHINA, "%02d:%02d", hour, minute);
            input.setText(date == null ? time : date + " " + time);
        }, selected.getHour(), selected.getMinute(), true).show();
    }

    public static ProgressBar progress(Context context) {
        ProgressBar progress = new ProgressBar(context);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.gravity = android.view.Gravity.CENTER;
        params.topMargin = dp(context, 32);
        progress.setLayoutParams(params);
        return progress;
    }

    public static GradientDrawable rounded(Context context, int fillColor, int strokeColor, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fillColor);
        if (strokeColor != 0) drawable.setStroke(dp(context, 1), strokeColor);
        drawable.setCornerRadius(dp(context, radiusDp));
        return drawable;
    }
}
