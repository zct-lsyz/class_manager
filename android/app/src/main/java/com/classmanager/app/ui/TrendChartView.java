package com.classmanager.app.ui;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Path;
import android.util.TypedValue;
import android.view.View;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

final class TrendChartView extends View {
    static final class Series {
        final String name;
        final int color;
        final List<Float> values;

        Series(String name, int color, List<Float> values) {
            this.name = name;
            this.color = color;
            this.values = values;
        }
    }

    private final List<String> labels;
    private final List<Series> series;
    private final boolean reverseY;
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);

    TrendChartView(Context context, List<String> labels, List<Series> series, boolean reverseY) {
        super(context);
        this.labels = labels == null ? new ArrayList<>() : labels;
        this.series = series == null ? new ArrayList<>() : series;
        this.reverseY = reverseY;
        setMinimumHeight(Ui.dp(context, 250));
        setContentDescription(reverseY ? "排名变化曲线" : "成绩变化曲线");
    }

    @Override
    protected void onMeasure(int widthMeasureSpec, int heightMeasureSpec) {
        int width = resolveSize(Ui.dp(getContext(), 320), widthMeasureSpec);
        int height = resolveSize(Ui.dp(getContext(), 250), heightMeasureSpec);
        setMeasuredDimension(width, height);
    }

    @Override
    protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        float left = Ui.dp(getContext(), 48);
        float right = getWidth() - Ui.dp(getContext(), 12);
        int legendRows = Math.max(1, (series.size() + 2) / 3);
        float top = Ui.dp(getContext(), 12 + legendRows * 20);
        float bottom = getHeight() - Ui.dp(getContext(), 48);
        if (labels.isEmpty() || series.isEmpty() || right <= left || bottom <= top) {
            drawEmpty(canvas);
            return;
        }

        float min = Float.POSITIVE_INFINITY;
        float max = Float.NEGATIVE_INFINITY;
        for (Series item : series) for (Float value : item.values) if (value != null) {
            min = Math.min(min, value);
            max = Math.max(max, value);
        }
        if (!Float.isFinite(min) || !Float.isFinite(max)) {
            drawEmpty(canvas);
            return;
        }
        if (min == max) {
            min -= 1;
            max += 1;
        }

        paint.setTypeface(android.graphics.Typeface.DEFAULT);
        paint.setTextSize(sp(10));
        paint.setStrokeWidth(Ui.dp(getContext(), 1));
        for (int i = 0; i <= 4; i++) {
            float y = top + (bottom - top) * i / 4f;
            paint.setColor(0xffe2e8f0);
            canvas.drawLine(left, y, right, y, paint);
            float value = reverseY ? min + (max - min) * i / 4f : max - (max - min) * i / 4f;
            paint.setColor(0xff64748b);
            paint.setTextAlign(Paint.Align.RIGHT);
            canvas.drawText(number(value), left - Ui.dp(getContext(), 6), y + sp(3), paint);
        }

        int labelStep = Math.max(1, (int) Math.ceil(labels.size() / 6d));
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setColor(0xff64748b);
        for (int i = 0; i < labels.size(); i += labelStep) {
            float x = xFor(i, left, right);
            canvas.save();
            canvas.rotate(-28, x, bottom + Ui.dp(getContext(), 14));
            canvas.drawText(shortLabel(labels.get(i)), x, bottom + Ui.dp(getContext(), 18), paint);
            canvas.restore();
        }

        for (Series item : series) {
            paint.setColor(item.color);
            paint.setStyle(Paint.Style.STROKE);
            paint.setStrokeWidth(Ui.dp(getContext(), 2));
            Path path = new Path();
            boolean connected = false;
            int count = Math.min(labels.size(), item.values.size());
            for (int i = 0; i < count; i++) {
                Float value = item.values.get(i);
                if (value == null) {
                    connected = false;
                    continue;
                }
                float x = xFor(i, left, right);
                float ratio = (value - min) / (max - min);
                float y = reverseY ? top + ratio * (bottom - top) : bottom - ratio * (bottom - top);
                if (connected) path.lineTo(x, y); else path.moveTo(x, y);
                connected = true;
            }
            canvas.drawPath(path, paint);
            paint.setStyle(Paint.Style.FILL);
            for (int i = 0; i < count; i++) {
                Float value = item.values.get(i);
                if (value == null) continue;
                float ratio = (value - min) / (max - min);
                float y = reverseY ? top + ratio * (bottom - top) : bottom - ratio * (bottom - top);
                canvas.drawCircle(xFor(i, left, right), y, Ui.dp(getContext(), 3), paint);
            }
        }
        drawLegend(canvas);
    }

    private void drawLegend(Canvas canvas) {
        paint.setTextAlign(Paint.Align.LEFT);
        paint.setTextSize(sp(11));
        int columnWidth = Math.max(Ui.dp(getContext(), 96), getWidth() / 3);
        for (int i = 0; i < series.size(); i++) {
            int row = i / 3;
            int column = i % 3;
            float x = Ui.dp(getContext(), 12) + column * columnWidth;
            float y = Ui.dp(getContext(), 18 + row * 20);
            paint.setColor(series.get(i).color);
            canvas.drawCircle(x, y - Ui.dp(getContext(), 3), Ui.dp(getContext(), 4), paint);
            paint.setColor(0xff334155);
            canvas.drawText(shortName(series.get(i).name), x + Ui.dp(getContext(), 8), y, paint);
        }
    }

    private void drawEmpty(Canvas canvas) {
        paint.setColor(0xff64748b);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(sp(14));
        canvas.drawText("暂无可绘制的数据", getWidth() / 2f, getHeight() / 2f, paint);
    }

    private float xFor(int index, float left, float right) {
        return labels.size() <= 1 ? (left + right) / 2f : left + (right - left) * index / (labels.size() - 1f);
    }

    private float sp(int value) {
        return TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_SP, value, getResources().getDisplayMetrics());
    }

    private String number(float value) {
        if (Math.abs(value - Math.round(value)) < .001f) return String.valueOf(Math.round(value));
        return String.format(Locale.CHINA, "%.1f", value);
    }

    private String shortLabel(String value) {
        if (value == null) return "";
        return value.length() > 9 ? value.substring(0, 9) : value;
    }

    private String shortName(String value) {
        if (value == null) return "";
        return value.length() > 7 ? value.substring(0, 7) : value;
    }
}
