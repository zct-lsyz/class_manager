package com.classmanager.app.notification;

import android.content.Context;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;

import com.classmanager.app.BuildConfig;
import com.classmanager.app.data.ApiClient;
import com.classmanager.app.data.SessionStore;

import org.json.JSONObject;

import java.lang.reflect.Method;

public final class MiPushBridge {
    public static void registerAndUpload(Context context) {
        if (BuildConfig.XIAOMI_APP_ID.isEmpty() || BuildConfig.XIAOMI_APP_KEY.isEmpty()) return;
        try {
            Class<?> client = Class.forName("com.xiaomi.mipush.sdk.MiPushClient");
            Method register = client.getMethod("registerPush", Context.class, String.class, String.class);
            register.invoke(null, context, BuildConfig.XIAOMI_APP_ID, BuildConfig.XIAOMI_APP_KEY);
            uploadAfter(context, client, 3000);
            uploadAfter(context, client, 15000);
        } catch (Exception ignored) {}
    }

    private static void uploadAfter(Context context, Class<?> client, long delay) {
        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            try {
                Method getRegId = client.getMethod("getRegId", Context.class);
                String regId = String.valueOf(getRegId.invoke(null, context));
                if (regId.isEmpty() || "null".equals(regId)) return;
                JSONObject body = new JSONObject();
                body.put("provider", "xiaomi");
                body.put("device_id", SessionStore.get(context).deviceId());
                body.put("device_name", Build.MANUFACTURER + " " + Build.MODEL);
                body.put("app_version", BuildConfig.VERSION_NAME);
                body.put("registration_id", regId);
                ApiClient.get(context).put("push/device/", body, new ApiClient.Callback() {
                    @Override public void onSuccess(JSONObject response) {}
                    @Override public void onError(String message, int statusCode) {}
                });
            } catch (Exception ignored) {}
        }, delay);
    }

    private MiPushBridge() {}
}
