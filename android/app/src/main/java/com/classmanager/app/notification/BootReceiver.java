package com.classmanager.app.notification;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

import com.classmanager.app.data.SessionStore;

public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (SessionStore.get(context).isLoggedIn()) NotificationScheduler.sync(context);
    }
}
