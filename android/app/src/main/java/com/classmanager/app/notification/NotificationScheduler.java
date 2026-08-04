package com.classmanager.app.notification;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import com.classmanager.app.data.ApiClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.time.OffsetDateTime;
import java.util.HashSet;
import java.util.Set;

public final class NotificationScheduler {
    public interface SyncCallback {
        void onComplete(boolean shouldRetry);
    }

    public static void sync(Context context) {
        sync(context, null);
    }

    public static void sync(Context context, SyncCallback callback) {
        Context app = context.getApplicationContext();
        ApiClient.get(app).get("notifications/", new ApiClient.Callback() {
            @Override public void onSuccess(JSONObject response) {
                JSONObject data = response.optJSONObject("data");
                JSONArray todos = data == null ? null : data.optJSONArray("todos");
                if (todos == null) return;
                Set<String> active = new HashSet<>();
                for (int i = 0; i < todos.length(); i++) {
                    JSONObject todo = todos.optJSONObject(i);
                    active.add(String.valueOf(todo.optInt("id")));
                    schedule(app, todo);
                }
                cancelRemoved(app, active);
                MiPushBridge.registerAndUpload(app);
                if (callback != null) callback.onComplete(false);
            }
            @Override public void onError(String message, int statusCode) {
                if (callback != null) callback.onComplete(statusCode == 0 || statusCode >= 500);
            }
        });
    }

    private static void cancelRemoved(Context context, Set<String> active) {
        SharedPreferences preferences = context.getSharedPreferences("todo_notifications", Context.MODE_PRIVATE);
        Set<String> previous = preferences.getStringSet("scheduled_ids", new HashSet<>());
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        for (String value : previous) if (!active.contains(value)) {
            Intent intent = new Intent(context, AlarmReceiver.class);
            PendingIntent pending = PendingIntent.getBroadcast(context, Integer.parseInt(value), intent,
                    PendingIntent.FLAG_NO_CREATE | PendingIntent.FLAG_IMMUTABLE);
            if (pending != null) { alarm.cancel(pending); pending.cancel(); }
        }
        preferences.edit().putStringSet("scheduled_ids", new HashSet<>(active)).apply();
    }

    private static void schedule(Context context, JSONObject todo) {
        if (todo == null) return;
        String deadline = todo.optString("deadline");
        if (deadline.isEmpty() || "null".equals(deadline)) return;
        int id = todo.optInt("id");
        String key = "todo:" + id + ":" + deadline;
        if (context.getSharedPreferences("todo_notifications", Context.MODE_PRIVATE).getBoolean(key, false)) return;
        long trigger;
        try {
            trigger = OffsetDateTime.parse(deadline).toInstant().toEpochMilli();
        } catch (Exception ignored) {
            return;
        }
        if (trigger < System.currentTimeMillis()) trigger = System.currentTimeMillis() + 1000;
        Intent intent = new Intent(context, AlarmReceiver.class);
        intent.putExtra("todo_id", id);
        intent.putExtra("title", todo.optString("title"));
        intent.putExtra("deadline", deadline.replace('T', ' '));
        intent.putExtra("delivery_key", key);
        PendingIntent pending = PendingIntent.getBroadcast(
                context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        AlarmManager alarm = (AlarmManager) context.getSystemService(Context.ALARM_SERVICE);
        if (Build.VERSION.SDK_INT >= 31 && alarm.canScheduleExactAlarms()) {
            alarm.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger, pending);
        } else {
            alarm.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, trigger, pending);
        }
    }

    private NotificationScheduler() {}
}
