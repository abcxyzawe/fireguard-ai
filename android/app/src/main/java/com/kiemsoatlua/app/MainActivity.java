package com.kiemsoatlua.app;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.Menu;
import android.view.MenuItem;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsControllerCompat;

public class MainActivity extends AppCompatActivity {

    public static final String PREFS = "fire_app";
    public static final String KEY_SERVER_IP   = "server_ip";
    public static final String KEY_SERVER_PORT = "server_port";
    public static final String KEY_USE_LOCAL   = "use_local";
    public static final String KEY_IP_CHANGED  = "ip_changed";

    public static final String CHANNEL_ID = "fire_alert_channel";
    private static final int NOTIF_PERM_CODE = 100;

    private WebView webView;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Edge-to-edge dark theme
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        getWindow().setStatusBarColor(Color.parseColor("#05070B"));
        getWindow().setNavigationBarColor(Color.parseColor("#05070B"));
        WindowInsetsControllerCompat c = WindowCompat.getInsetsController(getWindow(), getWindow().getDecorView());
        if (c != null) {
            c.setAppearanceLightStatusBars(false);
            c.setAppearanceLightNavigationBars(false);
        }

        if (getSupportActionBar() != null) getSupportActionBar().hide();

        createNotificationChannel();
        requestNotificationPermission();

        webView = findViewById(R.id.webView);
        setupWebView();
        loadApp();

        // Start fire alert background service (defer to make activity fully foreground first)
        webView.postDelayed(() -> {
            try {
                Intent svc = new Intent(this, FireAlertService.class);
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(svc);
                else startService(svc);
            } catch (Exception e) {
                android.util.Log.w("MainActivity", "Cannot start FireAlertService: " + e.getMessage());
                // Not critical — app still works without background polling
            }
        }, 500);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void setupWebView() {
        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(false); // we control viewport via meta tag

        webView.setBackgroundColor(Color.parseColor("#05070B"));

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                if ((url.startsWith("http://") || url.startsWith("https://"))
                        && !url.contains("localhost") && !url.contains("10.0.2.2")
                        && !url.startsWith(getBaseServerUrl())) {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
                    return true;
                }
                return false;
            }

            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                String html = "<html><head><meta name='viewport' content='width=device-width,initial-scale=1'>" +
                        "<style>body{background:#05070B;color:#F1F5F9;font-family:-apple-system,system-ui,sans-serif;" +
                        "text-align:center;padding:60px 24px;margin:0}" +
                        ".box{max-width:420px;margin:0 auto}" +
                        "h2{font-size:22px;margin:0 0 10px;color:#FF6F2C}" +
                        "p{color:#94A3B8;line-height:1.6}" +
                        "code{background:#12161F;padding:2px 6px;border-radius:4px;color:#FF9B66;font-size:12px}" +
                        "button{margin-top:24px;background:linear-gradient(135deg,#F04E17,#D13904);border:0;color:white;" +
                        "padding:12px 24px;border-radius:12px;font-weight:600;font-size:14px}</style></head>" +
                        "<body><div class='box'>" +
                        "<div style='font-size:48px;margin-bottom:12px'>📡</div>" +
                        "<h2>Không kết nối được server</h2>" +
                        "<p>Kiểm tra lại IP và port trong Cài đặt, hoặc chuyển sang chế độ Offline.</p>" +
                        "<p>Lỗi: <code>" + description + "</code></p>" +
                        "<button onclick='AndroidNative.openSettings()'>Mở cài đặt</button>" +
                        "</div></body></html>";
                view.loadDataWithBaseURL(null, html, "text/html", "utf-8", null);
            }
        });
        webView.setWebChromeClient(new WebChromeClient());
        webView.addJavascriptInterface(new JsBridge(this), "AndroidNative");
    }

    private void loadApp() {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        boolean useLocal = prefs.getBoolean(KEY_USE_LOCAL, true); // default: bundled app

        if (useLocal) {
            webView.loadUrl("file:///android_asset/www/index.html");
        } else {
            webView.loadUrl(getBaseServerUrl());
        }
    }

    private String getBaseServerUrl() {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String ip   = prefs.getString(KEY_SERVER_IP, "192.168.1.100");
        String port = prefs.getString(KEY_SERVER_PORT, "5000");
        return "http://" + ip + ":" + port;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "Cảnh báo cháy", NotificationManager.IMPORTANCE_HIGH);
            ch.setDescription("Thông báo khi FireGuard phát hiện lửa hoặc khói");
            ch.enableVibration(true);
            ch.setVibrationPattern(new long[]{0, 400, 150, 400, 150, 600});
            NotificationManager m = getSystemService(NotificationManager.class);
            if (m != null) m.createNotificationChannel(ch);
        }
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                ActivityCompat.requestPermissions(this,
                        new String[]{Manifest.permission.POST_NOTIFICATIONS}, NOTIF_PERM_CODE);
            }
        }
    }

    @Override
    public boolean onCreateOptionsMenu(Menu menu) {
        menu.add(0, 1, 0, "Cài đặt").setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER);
        menu.add(0, 2, 0, "Làm mới").setShowAsAction(MenuItem.SHOW_AS_ACTION_NEVER);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == 1) {
            startActivity(new Intent(this, SettingsActivity.class));
            return true;
        } else if (item.getItemId() == 2) {
            loadApp();
            Toast.makeText(this, "Đã làm mới", Toast.LENGTH_SHORT).show();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onResume() {
        super.onResume();
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        if (prefs.getBoolean(KEY_IP_CHANGED, false)) {
            prefs.edit().putBoolean(KEY_IP_CHANGED, false).apply();
            loadApp();
        }
    }

    /** JS bridge: call from web code as window.AndroidNative.* */
    public static class JsBridge {
        private final MainActivity act;
        JsBridge(MainActivity a) { this.act = a; }

        @JavascriptInterface
        public void openSettings() {
            act.runOnUiThread(() -> act.startActivity(new Intent(act, SettingsActivity.class)));
        }

        @JavascriptInterface
        public void vibrate(int ms) {
            act.runOnUiThread(() -> {
                android.os.Vibrator v = (android.os.Vibrator) act.getSystemService(VIBRATOR_SERVICE);
                if (v == null) return;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    v.vibrate(android.os.VibrationEffect.createOneShot(ms, android.os.VibrationEffect.DEFAULT_AMPLITUDE));
                } else {
                    v.vibrate(ms);
                }
            });
        }

        @JavascriptInterface
        public void toast(String msg) {
            act.runOnUiThread(() -> Toast.makeText(act, msg, Toast.LENGTH_SHORT).show());
        }

        @JavascriptInterface
        public String getServerUrl() {
            return act.getBaseServerUrl();
        }

        @JavascriptInterface
        public String getAppVersion() {
            try {
                return act.getPackageManager().getPackageInfo(act.getPackageName(), 0).versionName;
            } catch (Exception e) { return "1.0"; }
        }

        @JavascriptInterface
        public void exit() {
            act.runOnUiThread(act::finishAndRemoveTask);
        }
    }
}
