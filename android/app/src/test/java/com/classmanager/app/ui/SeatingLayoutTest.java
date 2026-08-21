package com.classmanager.app.ui;

import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

import android.app.Application;
import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
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
 * 1. 所有姓名单行完整显示（不换行、不挤成两行）。
 * 2. 横向滚动容器能精确滚到最右一列：滚动到末尾后最右单元格完整落在可视区域内。
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

    /** 按 ReportActivity 的真实层级挂载并测量：ScrollView → 内边距 LinearLayout → 结果容器 → 渲染视图。 */
    private static LayoutResult renderAndMeasure(Context context, int rows, int cols, int[] aisles) throws Exception {
        View rendered = StructuredReportRenderer.render(context, "seating/", seatingData(rows, cols, aisles));

        ScrollView scrollView = new ScrollView(context);
        LinearLayout body = new LinearLayout(context);
        body.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(context, 16);
        body.setPadding(pad, pad, pad, pad);
        scrollView.addView(body, new ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        LinearLayout results = new LinearLayout(context);
        results.setOrientation(LinearLayout.VERTICAL);
        body.addView(results, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        results.addView(rendered, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        int widthPx = dp(context, 411);
        int heightPx = dp(context, 2400);
        scrollView.measure(
                View.MeasureSpec.makeMeasureSpec(widthPx, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(heightPx, View.MeasureSpec.AT_MOST));
        scrollView.layout(0, 0, scrollView.getMeasuredWidth(), scrollView.getMeasuredHeight());

        TableLayout table = findView(scrollView, TableLayout.class);
        HorizontalScrollView scroll = findView(scrollView, HorizontalScrollView.class);
        if (table == null || scroll == null) fail("未找到座次表 TableLayout 或 HorizontalScrollView");

        LayoutResult result = new LayoutResult();
        result.viewport = scroll.getWidth();
        result.contentWidth = scroll.getChildAt(0).getWidth();
        result.tableWidth = table.getWidth();
        result.maxCellRight = 0;
        int lineCountOk = 0;
        int lineCountBad = 0;
        for (int r = 0; r < table.getChildCount(); r++) {
            View rowView = table.getChildAt(r);
            if (!(rowView instanceof TableRow)) continue;
            TableRow row = (TableRow) rowView;
            for (int c = 0; c < row.getChildCount(); c++) {
                View cell = row.getChildAt(c);
                result.maxCellRight = Math.max(result.maxCellRight, cell.getRight());
                TextView tv = textViewInside(cell);
                if (tv != null) {
                    if (tv.getLineCount() > 1) lineCountBad++;
                    else lineCountOk++;
                }
            }
        }
        result.lineCountBad = lineCountBad;
        result.lineCountOk = lineCountOk;

        // 最后一行的最右单元格（右侧排号列）
        View lastRow = table.getChildAt(table.getChildCount() - 1);
        if (lastRow instanceof TableRow) {
            TableRow row = (TableRow) lastRow;
            result.lastCellRight = row.getChildAt(row.getChildCount() - 1).getRight();
        }

        // 模拟滚动到最右端
        result.maxScroll = Math.max(0, result.contentWidth - result.viewport);
        scroll.scrollTo(result.maxScroll, 0);
        result.lastCellRightAtMaxScroll = result.lastCellRight - scroll.getScrollX();
        return result;
    }

    @Test
    public void eightColumnLayoutShowsSingleLineNamesAndScrollsToLastColumn() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        LayoutResult r = renderAndMeasure(context, 7, 8, new int[]{2, 4, 6});
        System.out.println("[SeatingLayoutTest] 8列3过道 viewport=" + r.viewport
                + " contentWidth=" + r.contentWidth + " tableWidth=" + r.tableWidth
                + " maxCellRight=" + r.maxCellRight + " lastCellRight=" + r.lastCellRight
                + " maxScroll=" + r.maxScroll + " lastVisibleAtMaxScroll=" + r.lastCellRightAtMaxScroll);

        // 1) 所有姓名单行显示
        assertTrue("存在换行显示的名字单元格: " + r.lineCountBad + " 个", r.lineCountBad == 0);

        // 2) 所有列都完整落在表格自身宽度内
        assertTrue("单元格超出表格宽度: maxCellRight=" + r.maxCellRight + " tableWidth=" + r.tableWidth,
                r.maxCellRight <= r.tableWidth);

        // 3) 滚动到最右端后，最右单元格完整可见
        assertTrue("滚动到最右端后最右列仍超出可视区域: lastCellRight=" + r.lastCellRight
                + " maxScroll=" + r.maxScroll + " viewport=" + r.viewport,
                r.lastCellRightAtMaxScroll <= r.viewport);
    }

    @Test
    public void wideLayoutStillScrollsToLastColumn() throws Exception {
        Context context = ApplicationProvider.getApplicationContext();
        LayoutResult r = renderAndMeasure(context, 8, 12, new int[]{3, 6, 9});
        System.out.println("[SeatingLayoutTest] 12列3过道 viewport=" + r.viewport
                + " contentWidth=" + r.contentWidth + " tableWidth=" + r.tableWidth
                + " maxCellRight=" + r.maxCellRight + " lastCellRight=" + r.lastCellRight
                + " maxScroll=" + r.maxScroll + " lastVisibleAtMaxScroll=" + r.lastCellRightAtMaxScroll);

        assertTrue("存在换行显示的名字单元格: " + r.lineCountBad + " 个", r.lineCountBad == 0);
        assertTrue("单元格超出表格宽度: maxCellRight=" + r.maxCellRight + " tableWidth=" + r.tableWidth,
                r.maxCellRight <= r.tableWidth);
        assertTrue("宽表格应可横向滚动: contentWidth=" + r.contentWidth + " viewport=" + r.viewport,
                r.contentWidth > r.viewport);
        assertTrue("滚动到最右端后最右列仍超出可视区域: lastCellRight=" + r.lastCellRight
                + " maxScroll=" + r.maxScroll + " viewport=" + r.viewport,
                r.lastCellRightAtMaxScroll <= r.viewport);
    }

    private static final class LayoutResult {
        int viewport;
        int contentWidth;
        int tableWidth;
        int maxCellRight;
        int lastCellRight;
        int maxScroll;
        int lastCellRightAtMaxScroll;
        int lineCountOk;
        int lineCountBad;
    }

    private static TextView textViewInside(View view) {
        if (view instanceof TextView) return (TextView) view;
        if (view instanceof ViewGroup) {
            ViewGroup g = (ViewGroup) view;
            for (int i = 0; i < g.getChildCount(); i++) {
                TextView found = textViewInside(g.getChildAt(i));
                if (found != null) return found;
            }
        }
        return null;
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
