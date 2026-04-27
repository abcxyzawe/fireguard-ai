package com.kiemsoatlua.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Iterator;

/**
 * Background service polling the Flask server for fire/smoke alerts.
 * Shows high-priority notification with vibration when detected.
 */
public class FireAlertService extends Service {

    private static final String TAG = "FireAlertService";
    private static final String CHANNEL_FG = "fire_fg_channel";
    private static final int POLL_INTERVAL = 3000; // 3s
    private static final int FG_NOTIFICATION_ID = 1000;
    private static final int ALERT_ID_BASE = 2000;
    private static final long ALERT_COOLDOWN = 10_000L; // 10s per camera

    private Handler handler;
    private long lastAlertTime = 0;
    private boolean lastAlertState = false;

    @Override
    public void onCreate() {
        super.onCreate();
        handler = new Handler(Looper.getMainLooper());
        createForegroundChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(FG_NOTIFICATION_ID, buildForegroundNotification("Đang giám sát"),
                        android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC);
            } else {
                startForeground(FG_NOTIFICATION_ID, buildForegroundNotification("Đang giám sát"));
            }
            if (handler != null) startPolling();
        } catch (Exception e) {
            Log.w(TAG, "startForeground failed: " + e.getMessage());
            // Fallback: just run as regular service
        }
        return START_STICKY;
    }

    private void createForegroundChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_FG, "Dịch vụ nền", NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("Giám sát phát hiện cháy chạy nền");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    private Notification buildForegroundNotification(String text) {
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        return new NotificationCompat.Builder(this, CHANNEL_FG)
                .setContentTitle("FireGuard AI")
                .setContentText(text)
                .setSmallIcon(R.drawable.ic_notification)
                .setColor(0xFFF04E17)
                .setContentIntent(pi)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build();
    }

    private void updateForegroundText(String text) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.notify(FG_NOTIFICATION_ID, buildForegroundNotification(text));
    }

    private void startPolling() {
        handler.postDelayed(new Runnable() {
            @Override public void run() {
                pollServer();
                handler.postDelayed(this, POLL_INTERVAL);
            }
        }, POLL_INTERVAL);
    }

    private void pollServer() {
        new Thread(() -> {
            try {
                SharedPreferences prefs = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
                String ip   = prefs.getString(MainActivity.KEY_SERVER_IP, "");
                String port = prefs.getString(MainActivity.KEY_SERVER_PORT, "5000");
                if (ip.isEmpty()) {
                    updateForegroundText("Chưa cấu hình server");
                    return;
                }
                String urlStr = "http://" + ip + ":" + port + "/status";

                URL url = new URL(urlStr);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3000);

                BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();

                JSONObject json = new JSONObject(sb.toString());
                boolean anyFire = false, anySmoke = false;
                String alertCamId = null;

                // Multi-camera format: { cameras: { cam1: {...}, cam2: {...} } }
                JSONObject cams = json.optJSONObject("cameras");
                if (cams != null && cams.length() > 0) {
                    Iterator<String> keys = cams.keys();
                    while (keys.hasNext()) {
                        String camId = keys.next();
                        JSONObject det = cams.optJSONObject(camId);
                        if (det == null) continue;
                        if (det.optBoolean("fire", false)) { anyFire = true; alertCamId = camId; break; }
                        if (det.optBoolean("smoke", false)) { anySmoke = true; alertCamId = camId; }
                    }
                } else {
                    // Legacy: last_detection
                    JSONObject det = json.optJSONObject("last_detection");
                    if (det != null) {
                        anyFire = det.optBoolean("fire", false);
                        anySmoke = det.optBoolean("smoke", false);
                        alertCamId = "cam1";
                    }
                }

                boolean alertState = anyFire || anySmoke;
                if (alertState && !lastAlertState) {
                    long now = System.currentTimeMillis();
                    if (now - lastAlertTime > ALERT_COOLDOWN) {
                        lastAlertTime = now;
                        sendFireNotification(anyFire, anySmoke, alertCamId);
                        vibrate();
                    }
                }
                lastAlertState = alertState;

                // Update persistent notification
                if (alertState) {
                    updateForegroundText((anyFire ? "⚠️ PHÁT HIỆN CHÁY" : "Phát hiện khói") + " · " + (alertCamId != null ? alertCamId.toUpperCase() : ""));
                } else {
                    updateForegroundText("Đang giám sát · An toàn");
                }
            } catch (Exception e) {
                Log.w(TAG, "Poll failed: " + e.getMessage());
                updateForegroundText("Mất kết nối server");
            }
        }).start();
    }

    private void sendFireNotification(boolean fire, boolean smoke, String camId) {
        Intent intent = new Intent(this, MainActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);

        String title = fire ? "🔥 CẢNH BÁO CHÁY!" : "💨 Phát hiện khói";
        String text = fire
                ? "Hệ thống phát hiện ngọn lửa — kiểm tra ngay!"
                : "Phát hiện khói bất thường — hãy xác nhận tình trạng.";
        if (camId != null) text += " · " + camId.toUpperCase();

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, MainActivity.CHANNEL_ID)
                .setSmallIcon(R.drawable.ic_notification)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setAutoCancel(true)
                .setContentIntent(pi)
                .setVibrate(new long[]{0, 500, 200, 500, 200, 500})
                .setDefaults(NotificationCompat.DEFAULT_SOUND)
                .setColor(fire ? 0xFFEF4444 : 0xFFF97316);

        NotificationManager nm = getSystemService(NotificationManager.class);
        if (nm != null) nm.notify(ALERT_ID_BASE, builder.build());
    }

    private void vibrate() {
        Vibrator v = (Vibrator) getSystemService(VIBRATOR_SERVICE);
        if (v == null) return;
        long[] pattern = {0, 500, 200, 500, 200, 500};
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            v.vibrate(VibrationEffect.createWaveform(pattern, -1));
        } else {
            v.vibrate(pattern, -1);
        }
    }

    @Override public IBinder onBind(Intent intent) { return null; }

    @Override
    public void onDestroy() {
        super.onDestroy();
        if (handler != null) handler.removeCallbacksAndMessages(null);
    }
}
