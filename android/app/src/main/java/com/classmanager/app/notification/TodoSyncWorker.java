package com.classmanager.app.notification;

import android.content.Context;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import com.classmanager.app.data.SessionStore;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class TodoSyncWorker extends Worker {
    public TodoSyncWorker(@NonNull Context context, @NonNull WorkerParameters parameters) {
        super(context, parameters);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context context = getApplicationContext();
        if (!SessionStore.get(context).isLoggedIn()) {
            TodoSyncManager.cancel(context);
            return Result.success();
        }
        CountDownLatch completed = new CountDownLatch(1);
        AtomicBoolean retry = new AtomicBoolean(true);
        NotificationScheduler.sync(context, shouldRetry -> {
            retry.set(shouldRetry);
            completed.countDown();
        });
        try {
            if (!completed.await(75, TimeUnit.SECONDS)) return Result.retry();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return Result.retry();
        }
        return retry.get() ? Result.retry() : Result.success();
    }
}
