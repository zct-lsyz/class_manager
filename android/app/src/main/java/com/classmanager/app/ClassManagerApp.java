package com.classmanager.app;

import android.app.Application;

import com.classmanager.app.notification.NotificationHelper;
import com.classmanager.app.notification.TodoSyncManager;

public class ClassManagerApp extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        NotificationHelper.createChannels(this);
        TodoSyncManager.update(this);
    }
}
