package com.classmanager.app.data;

import android.content.Context;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.os.Handler;
import android.os.Looper;

import com.classmanager.app.BuildConfig;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.DataOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.Iterator;
import java.util.Map;

public final class ApiClient {
    public interface Callback {
        void onSuccess(JSONObject response);
        void onError(String message, int statusCode);
    }

    private static ApiClient instance;
    private final SessionStore session;
    private final Context context;
    private final ExecutorService executor = Executors.newFixedThreadPool(4);
    private final Handler main = new Handler(Looper.getMainLooper());

    private ApiClient(Context context) {
        this.context = context.getApplicationContext();
        session = SessionStore.get(context);
    }

    public static synchronized ApiClient get(Context context) {
        if (instance == null) instance = new ApiClient(context.getApplicationContext());
        return instance;
    }

    public void get(String path, Callback callback) {
        request("GET", path, null, callback);
    }

    public void post(String path, JSONObject body, Callback callback) {
        request("POST", path, body, callback);
    }

    public void put(String path, JSONObject body, Callback callback) {
        request("PUT", path, body, callback);
    }

    public void patch(String path, JSONObject body, Callback callback) {
        request("PATCH", path, body, callback);
    }

    public void delete(String path, JSONObject body, Callback callback) {
        request("DELETE", path, body, callback);
    }

    public void request(String method, String path, JSONObject body, Callback callback) {
        executor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                URL url = new URL(resolve(path));
                connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod(method);
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(60000);
                connection.setRequestProperty("Accept", "application/json");
                connection.setRequestProperty("Content-Type", "application/json; charset=UTF-8");
                String token = session.token();
                if (!token.isEmpty()) connection.setRequestProperty("Authorization", "Bearer " + token);
                if (body != null) {
                    connection.setDoOutput(true);
                    byte[] bytes = body.toString().getBytes(StandardCharsets.UTF_8);
                    connection.setFixedLengthStreamingMode(bytes.length);
                    try (OutputStream output = connection.getOutputStream()) {
                        output.write(bytes);
                    }
                }
                int status = connection.getResponseCode();
                InputStream stream = status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream();
                String text = read(stream);
                JSONObject json = text.isEmpty() ? new JSONObject() : new JSONObject(text);
                if (status >= 200 && status < 300 && json.optBoolean("ok", true)) {
                    main.post(() -> callback.onSuccess(json));
                } else {
                    String message = json.optJSONObject("error") != null
                            ? json.optJSONObject("error").optString("message", "请求失败")
                            : "请求失败（" + status + "）";
                    if (status == 401) session.clear();
                    int finalStatus = status;
                    main.post(() -> callback.onError(message, finalStatus));
                }
            } catch (Exception exception) {
                String message = exception.getMessage() == null ? "网络连接失败" : exception.getMessage();
                main.post(() -> callback.onError(message, 0));
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    public void download(String path, Uri destination, Callback callback) {
        executor.execute(() -> {
            HttpURLConnection connection = null;
            try {
                connection = (HttpURLConnection) new URL(resolve(path)).openConnection();
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(300000);
                connection.setRequestProperty("Authorization", "Bearer " + session.token());
                int status = connection.getResponseCode();
                if (status < 200 || status >= 300) {
                    int finalStatus = status;
                    main.post(() -> callback.onError("下载失败（" + finalStatus + "）", finalStatus));
                    return;
                }
                try (InputStream input = connection.getInputStream();
                     OutputStream output = context.getContentResolver().openOutputStream(destination)) {
                    if (output == null) throw new IllegalStateException("无法写入所选文件");
                    byte[] buffer = new byte[65536];
                    int count;
                    while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
                }
                main.post(() -> callback.onSuccess(new JSONObject()));
            } catch (Exception exception) {
                String message = exception.getMessage() == null ? "下载失败" : exception.getMessage();
                main.post(() -> callback.onError(message, 0));
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    public void upload(String path, JSONObject fields, Map<String, Uri> files, Callback callback) {
        executor.execute(() -> {
            HttpURLConnection connection = null;
            String boundary = "ClassManager" + System.currentTimeMillis();
            try {
                connection = (HttpURLConnection) new URL(resolve(path)).openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(15000);
                connection.setReadTimeout(120000);
                connection.setDoOutput(true);
                connection.setRequestProperty("Accept", "application/json");
                connection.setRequestProperty("Authorization", "Bearer " + session.token());
                connection.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);
                try (DataOutputStream output = new DataOutputStream(connection.getOutputStream())) {
                    Iterator<String> keys = fields.keys();
                    while (keys.hasNext()) {
                        String key = keys.next();
                        output.writeBytes("--" + boundary + "\r\n");
                        output.writeBytes("Content-Disposition: form-data; name=\"" + key + "\"\r\n\r\n");
                        output.write(String.valueOf(fields.opt(key)).getBytes(StandardCharsets.UTF_8));
                        output.writeBytes("\r\n");
                    }
                    for (Map.Entry<String, Uri> item : files.entrySet()) {
                        String name = displayName(item.getValue());
                        String mime = context.getContentResolver().getType(item.getValue());
                        output.writeBytes("--" + boundary + "\r\n");
                        output.writeBytes("Content-Disposition: form-data; name=\"" + item.getKey() + "\"; filename=\"" + name.replace("\"", "") + "\"\r\n");
                        output.writeBytes("Content-Type: " + (mime == null ? "application/octet-stream" : mime) + "\r\n\r\n");
                        try (InputStream input = context.getContentResolver().openInputStream(item.getValue())) {
                            if (input == null) throw new IllegalStateException("无法读取所选文件");
                            byte[] buffer = new byte[65536];
                            int count;
                            while ((count = input.read(buffer)) >= 0) output.write(buffer, 0, count);
                        }
                        output.writeBytes("\r\n");
                    }
                    output.writeBytes("--" + boundary + "--\r\n");
                }
                int status = connection.getResponseCode();
                String text = read(status >= 200 && status < 300 ? connection.getInputStream() : connection.getErrorStream());
                JSONObject json = text.isEmpty() ? new JSONObject() : new JSONObject(text);
                if (status >= 200 && status < 300 && json.optBoolean("ok", true)) main.post(() -> callback.onSuccess(json));
                else {
                    String message = json.optJSONObject("error") == null ? "上传失败（" + status + "）" : json.optJSONObject("error").optString("message", "上传失败");
                    int finalStatus = status;
                    main.post(() -> callback.onError(message, finalStatus));
                }
            } catch (Exception exception) {
                String message = exception.getMessage() == null ? "上传失败" : exception.getMessage();
                main.post(() -> callback.onError(message, 0));
            } finally {
                if (connection != null) connection.disconnect();
            }
        });
    }

    private String displayName(Uri uri) {
        try (android.database.Cursor cursor = context.getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst()) return cursor.getString(0);
        }
        return "upload.bin";
    }

    static String resolve(String path) {
        if (path.startsWith("http://") || path.startsWith("https://")) return path;
        String clean = path.startsWith("/") ? path.substring(1) : path;
        return BuildConfig.API_BASE_URL + clean;
    }

    private static String read(InputStream stream) throws Exception {
        if (stream == null) return "";
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) builder.append(line);
        }
        return builder.toString();
    }
}
