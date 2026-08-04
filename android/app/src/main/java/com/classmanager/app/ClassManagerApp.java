package com.classmanager.app;

import android.app.Application;

import com.classmanager.app.notification.NotificationHelper;

public class ClassManagerApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        NotificationHelper.createChannels(this);
    }
}
