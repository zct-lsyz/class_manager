package com.classmanager.app.notification;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class AlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        int id = intent.getIntExtra("todo_id", 0);
        String title = intent.getStringExtra("title");
        String deadline = intent.getStringExtra("deadline");
        String key = intent.getStringExtra("delivery_key");
        NotificationHelper.showTodo(context, id, title == null ? "待办到期" : title, deadline == null ? "" : deadline);
        if (key != null) context.getSharedPreferences("todo_notifications", Context.MODE_PRIVATE)
                .edit().putBoolean(key, true).apply();
    }
}
