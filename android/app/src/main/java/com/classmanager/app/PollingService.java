package com.classmanager.app;

import android.app.AlarmManager;
import android.app.IntentService;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.SystemClock;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class PollingService extends IntentService {

    private static final long POLL_INTERVAL_MS = 5 * 60 * 1000; // 5 分钟
    private static final int NOTIFICATION_ID_BASE = 2000;

    public PollingService() {
        super("PollingService");
    }

    public static void schedule(Context context) {
        AlarmManager alarmManager = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (alarmManager == null) return;
        Intent intent = new Intent(context, PollAlarmReceiver.class);
        PendingIntent pendingIntent = PendingIntent.getBroadcast(
                context, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        alarmManager.setInexactRepeating(
                AlarmManager.ELAPSED_REALTIME_WAKEUP,
                SystemClock.elapsedRealtime() + POLL_INTERVAL_MS,
                POLL_INTERVAL_MS,
                pendingIntent
        );
    }

    @Override
    protected void onHandleIntent(Intent intent) {
        SharedPreferences sp = getSharedPreferences(MainActivity.PREFS, Context.MODE_PRIVATE);
        String serverUrl = sp.getString(MainActivity.KEY_SERVER_URL, "");
        if (serverUrl.isEmpty() || serverUrl.contains("你的服务器域名")) return;

        String apiUrl = serverUrl.replaceAll("/+$", "") + "/dashboard/api/notifications/";
        String json = httpGet(apiUrl);
        if (json == null) return;

        try {
            JSONObject obj = new JSONObject(json);
            boolean hasDuty = obj.optBoolean("has_duty_today", false) || obj.has("today_duty");
            JSONObject duty = obj.has("today_duty") && !obj.isNull("today_duty")
                    ? obj.optJSONObject("today_duty") : null;
            int warningCount = obj.optInt("warning_count", 0);
            boolean backupAlert = obj.optBoolean("today_backup_alert", false);

            if (duty != null) {
                String summary = duty.optString("summary", "");
                if (!summary.isEmpty()) {
                    NotificationHelper.show(this, "今日值日提醒", summary, NOTIFICATION_ID_BASE + 1);
                }
            }
            if (warningCount > 0) {
                NotificationHelper.show(this, "学生预警提醒",
                        "当前有 " + warningCount + " 位学生达到预警条件，请及时处理。", NOTIFICATION_ID_BASE + 2);
            }
            if (backupAlert) {
                NotificationHelper.show(this, "备份失败提醒",
                        "今日存在失败的备份任务，请检查。", NOTIFICATION_ID_BASE + 3);
            }
        } catch (Exception e) {
            // 忽略解析错误
        }
    }

    private String httpGet(String urlString) {
        try {
            URL url = new URL(urlString);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            conn.setInstanceFollowRedirects(true);
            conn.setRequestProperty("Accept", "application/json");
            // 复用 WebView 登录后的会话 Cookie，使轮询能访问受登录保护的通知接口
            try {
                String cookie = android.webkit.CookieManager.getInstance().getCookie(urlString);
                if (cookie != null && !cookie.isEmpty()) {
                    conn.setRequestProperty("Cookie", cookie);
                }
            } catch (Exception ignored) {
            }
            int code = conn.getResponseCode();
            if (code != 200) return null;
            BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream(), "UTF-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                sb.append(line);
            }
            reader.close();
            conn.disconnect();
            return sb.toString();
        } catch (Exception e) {
            return null;
        }
    }
}
