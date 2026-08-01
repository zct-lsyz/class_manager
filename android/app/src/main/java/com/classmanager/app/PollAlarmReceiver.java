package com.classmanager.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class PollAlarmReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Intent service = new Intent(context, PollingService.class);
        context.startService(service);
    }
}
