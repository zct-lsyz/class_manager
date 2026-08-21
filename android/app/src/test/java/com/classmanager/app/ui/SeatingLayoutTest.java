package com.classmanager.app.ui;

import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import android.app.Application;
import android.content.Context;
import android.util.DisplayMetrics;
import android.view.View;
import android.view.ViewGroup;
import android.widget.HorizontalScrollView;
import android.widget.TableLayout;
import android.widget.TableRow;
import android.widget.TextView;

import androidx.test.core.app.ApplicationProvider;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;

/**
 * 座次表布局验证：
 * 1. 常见列数（含用户实际 8 列 3 过道）时整张表应在一屏内完整显示，
 *    最右侧一列不再被屏幕边缘遮住（无需横向滚动）。
 * 2. 列数过多、无法清晰容纳时退化为横向滚动，但所有列仍完整落在表格自身宽度内。
 */
@RunWith(RobolectricTestRunner.class)
@Config(sdk = 34, qualifiers = "w411dp-h891dp-xxhdpi", application = SeatingLayoutTest.TestApp.class)
public class SeatingLayoutTest {

    /** 轻量 Application：跳过 WorkManager 等真实初始化，仅用于布局测试。 */
    public static class TestApp extends Application {
        @Override
        public void onCreate() {
            super.onCreate();
        }
    }

    private static JSONObject seatingData(int rows, int cols, int[] aisles) throws Exception {
        JSONObject layout = new JSONObject();
        layout.put("rows", rows);
        layout.put("cols", cols);
        layout.put("aisle_positions", new JSONArray(java.util.Arrays.stream(aisles).boxed()
                .collect(java.util.stream.Collectors.toList())));
        layout.put("podium_position", "back");
        JSONObject plan = new JSONObject();
        plan.put("id", 2);
        plan.put("version", "3");
        plan.put("reason", "月度调整");
        plan.put("layout", layout);
        JSONArray assignments = new JSONArray();
        String[] names = {"张三丰", "李四", "王小明", "欧阳娜娜", "赵六", "孙七", "周八", "吴九", "郑十"};
        for (int r = 0; r < rows; r++) {
            for (int c = 0; c < cols; c++) {
                JSONObject a = new JSONObject();
                a.put("row", r);
                a.put("col", c);
                a.put("student_name", names[(r * cols + c) % names.length]);
                a.put("student_gender", (r + c) % 2 == 0 ? "male" : "female");
                assignments.put(a);
            }
        }
        JSONObject data = new JSONObject();
        data.put("plan", plan);
        data.put("assignments", assignments);
        return data;
    }

    private static int dp(Context context, int value) {
        return Math.round(value * context.getResources().getDisplayMetrics().density);
    }

    private static LayoutResult renderAndMeasure(Context context, int rows, int cols, int[] aisles) throws Exception {
        View rendered = StructuredReportRenderer.render(context, "seating/", seatingData(rows, cols, aisles));
        ViewGroup container = new android.widget.FrameLayout(context);
        int widthPx = dp(context, 411);
        int heightPx = dp(context, 1800);
        container.addView(rendered, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        container.measure(
                View.MeasureSpec.makeMeasureSpec(widthPx, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(heightPx, View.MeasureSpec.AT_MOST));
        container.layout(0, 0, container.getMeasuredWidth(), container.getMeasuredHeight());

        TableLayout table = findView(rendered, TableLayout.class);
        HorizontalScrollView scroll = findView(rendered, HorizontalScrollView.class);
        if (table == null || scroll == null) fail("未找到座次表 TableLayout 或 HorizontalScrollView");

        LayoutResult result = new LayoutResult();
        result.viewport = scroll.getWidth();
        result.contentWidth = scroll.getChildAt(0).getWidth();
        result.tableWidth = table.getWidth();
        result.maxCellRight = 0;
        for (int r = 0; r < table.getChildCount(); r++) {
            View rowView = table.getChildAt(r);
            if (!(rowView instanceof TableRow)) continue;
            TableRow row = (TableRow) rowView;
            for (int c = 0; c < row.getChildCount(); c++) {
                result.maxCellRight = Math.max(result.maxCellRight, row.getChildAt(c).getRight());
            }
        }
        // 最右单元格（右侧排号列）
        View lastRow = table.getChildAt(table.getChildCount() - 1);
        if (lastRow instanceof TableRow) {
            TableRow row = (TableRow) lastRow;
            View last = row.getChildAt(row.getChildCount() - 1);
            result.lastCellRight = last.getRight();
        }
        return result;
    }

    @Test
    public void typicalEightColumnLayoutFitsScreenWithoutClipping() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        LayoutResult r = renderAndMeasure(context, 7, 8, new int[]{2, 4, 6});
        System.out.println("[SeatingLayoutTest] 8列3过道 viewport=" + r.viewport
                + " contentWidth=" + r.contentWidth + " tableWidth=" + r.tableWidth
                + " maxCellRight=" + r.maxCellRight + " lastCellRight=" + r.lastCellRight);
        // 整张表（含最右侧排号列）必须完整落在可视区域内，无需横向滚动
        assertTrue("座次表超出屏幕，最右侧一列仍会被遮住: tableWidth=" + r.tableWidth
                + " viewport=" + r.viewport, r.tableWidth <= r.viewport);
        assertTrue("最右侧一列超出可视区域: maxCellRight=" + r.maxCellRight
                + " viewport=" + r.viewport, r.maxCellRight <= r.viewport);
    }

    @Test
    public void wideLayoutFallsBackToScrollableButCellsFitTable() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        LayoutResult r = renderAndMeasure(context, 8, 12, new int[]{3, 6, 9});
        System.out.println("[SeatingLayoutTest] 12列3过道 viewport=" + r.viewport
                + " contentWidth=" + r.contentWidth + " tableWidth=" + r.tableWidth
                + " maxCellRight=" + r.maxCellRight + " lastCellRight=" + r.lastCellRight);
        // 列数过多：表格允许横向滚动（内容宽度大于视口）
        assertTrue("宽布局应可横向滚动: contentWidth=" + r.contentWidth + " viewport=" + r.viewport,
                r.contentWidth > r.viewport);
        // 但所有列仍完整落在表格自身宽度内，滚动到末尾后无内容被裁
        assertTrue("单元格超出表格自身宽度: maxCellRight=" + r.maxCellRight
                + " tableWidth=" + r.tableWidth, r.maxCellRight <= r.tableWidth);
    }

    private static final class LayoutResult {
        int viewport;
        int contentWidth;
        int tableWidth;
        int maxCellRight;
        int lastCellRight;
    }

    @SuppressWarnings("unchecked")
    private static <T extends View> T findView(View root, Class<T> type) {
        if (type.isInstance(root)) return (T) root;
        if (root instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) root;
            for (int i = 0; i < g.getChildCount(); i++) {
                T found = findView(g.getChildAt(i), type);
                if (found != null) return found;
            }
        }
        return null;
    }
}
