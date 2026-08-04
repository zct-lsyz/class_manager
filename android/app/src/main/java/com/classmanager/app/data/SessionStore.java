package com.classmanager.app.data;

import android.content.Context;
import android.content.SharedPreferences;
import android.provider.Settings;
import android.util.Base64;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.SecureRandom;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class SessionStore {
    private static final String PREFS = "secure_session";
    private static final String KEY_ALIAS = "class_manager_api_token";
    private static final String TOKEN = "token";
    private static final String USERNAME = "username";
    private static SessionStore instance;

    private final Context context;
    private final SharedPreferences preferences;

    private SessionStore(Context context) {
        this.context = context.getApplicationContext();
        this.preferences = this.context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    public static synchronized SessionStore get(Context context) {
        if (instance == null) instance = new SessionStore(context);
        return instance;
    }

    public void saveSession(String token, String username) {
        preferences.edit().putString(TOKEN, encrypt(token)).putString(USERNAME, username).apply();
    }

    public String token() {
        String encrypted = preferences.getString(TOKEN, "");
        if (encrypted.isEmpty()) return "";
        try {
            return decrypt(encrypted);
        } catch (Exception ignored) {
            clear();
            return "";
        }
    }

    public String username() {
        return preferences.getString(USERNAME, "");
    }

    public boolean isLoggedIn() {
        return !token().isEmpty();
    }

    public void clear() {
        preferences.edit().clear().apply();
    }

    public String deviceId() {
        String id = Settings.Secure.getString(context.getContentResolver(), Settings.Secure.ANDROID_ID);
        if (id != null && !id.isEmpty()) return id;
        String fallback = preferences.getString("fallback_device_id", "");
        if (fallback.isEmpty()) {
            byte[] bytes = new byte[16];
            new SecureRandom().nextBytes(bytes);
            fallback = Base64.encodeToString(bytes, Base64.NO_WRAP | Base64.URL_SAFE);
            preferences.edit().putString("fallback_device_id", fallback).apply();
        }
        return fallback;
    }

    private String encrypt(String value) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key());
            byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
            return Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP) + "." +
                    Base64.encodeToString(encrypted, Base64.NO_WRAP);
        } catch (Exception exception) {
            throw new IllegalStateException("无法安全保存登录状态", exception);
        }
    }

    private String decrypt(String value) throws Exception {
        String[] parts = value.split("\\.", 2);
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)));
        return new String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), StandardCharsets.UTF_8);
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance("AndroidKeyStore");
        store.load(null);
        if (!store.containsAlias(KEY_ALIAS)) {
            KeyGenerator generator = KeyGenerator.getInstance("AES", "AndroidKeyStore");
            generator.init(new android.security.keystore.KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    android.security.keystore.KeyProperties.PURPOSE_ENCRYPT |
                            android.security.keystore.KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                    .build());
            generator.generateKey();
        }
        return ((KeyStore.SecretKeyEntry) store.getEntry(KEY_ALIAS, null)).getSecretKey();
    }
}
