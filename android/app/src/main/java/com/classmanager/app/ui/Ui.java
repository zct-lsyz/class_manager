package com.classmanager.app.ui;

import android.content.Context;
import android.graphics.Typeface;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import com.classmanager.app.R;

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
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        params.setMargins(0, dp(context, 5), 0, dp(context, 5));
        button.setLayoutParams(params);
        return button;
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
}
