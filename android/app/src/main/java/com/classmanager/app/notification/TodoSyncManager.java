package com.classmanager.app.notification;

import android.content.Context;

import androidx.work.BackoffPolicy;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

import com.classmanager.app.data.SessionStore;

import java.util.concurrent.TimeUnit;

public final class TodoSyncManager {
    static final String UNIQUE_WORK = "todo-background-sync";

    public static void update(Context context) {
        if (SessionStore.get(context).isLoggedIn()) enable(context); else cancel(context);
    }

    public static void enable(Context context) {
        Constraints constraints = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();
        PeriodicWorkRequest request = new PeriodicWorkRequest.Builder(
                TodoSyncWorker.class, 15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build();
        WorkManager.getInstance(context.getApplicationContext()).enqueueUniquePeriodicWork(
                UNIQUE_WORK, ExistingPeriodicWorkPolicy.UPDATE, request);
    }

    public static void cancel(Context context) {
        WorkManager.getInstance(context.getApplicationContext()).cancelUniqueWork(UNIQUE_WORK);
    }

    private TodoSyncManager() {}
}
