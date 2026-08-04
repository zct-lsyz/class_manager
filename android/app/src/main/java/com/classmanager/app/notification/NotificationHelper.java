package com.classmanager.app.notification;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import androidx.core.app.ActivityCompat;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;

import com.classmanager.app.R;
import com.classmanager.app.ui.MainActivity;

public final class NotificationHelper {
    public static final String TODO_CHANNEL = "todo_reminders";

    public static void createChannels(Context context) {
        NotificationChannel channel = new NotificationChannel(
                TODO_CHANNEL, "待办提醒", NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("待办事项到期提醒");
        channel.enableVibration(true);
        context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }

    public static void showTodo(Context context, int id, String title, String deadline) {
        if (Build.VERSION.SDK_INT >= 33 && ActivityCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return;
        Intent intent = new Intent(context, MainActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent contentIntent = PendingIntent.getActivity(
                context, id, intent, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder builder = new NotificationCompat.Builder(context, TODO_CHANNEL)
                .setSmallIcon(R.drawable.ic_app)
                .setContentTitle("待办提醒")
                .setContentText(title)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(title + (deadline.isEmpty() ? "" : "\n截止时间：" + deadline)))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setAutoCancel(true)
                .setContentIntent(contentIntent);
        NotificationManagerCompat.from(context).notify(id, builder.build());
    }

    private NotificationHelper() {}
}
