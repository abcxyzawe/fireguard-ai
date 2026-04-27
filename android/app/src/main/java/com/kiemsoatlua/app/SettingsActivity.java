package com.kiemsoatlua.app;

import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Bundle;
import android.widget.Button;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.WindowCompat;

public class SettingsActivity extends AppCompatActivity {

    private EditText etServerIp, etServerPort;
    private Switch swUseLocal;
    private TextView tvStatus;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_settings);

        // Edge-to-edge dark theme
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        getWindow().setStatusBarColor(Color.parseColor("#05070B"));
        getWindow().setNavigationBarColor(Color.parseColor("#05070B"));

        if (getSupportActionBar() != null) {
            getSupportActionBar().setDisplayHomeAsUpEnabled(true);
            getSupportActionBar().setTitle("Cài đặt");
        }

        etServerIp   = findViewById(R.id.etServerIp);
        etServerPort = findViewById(R.id.etServerPort);
        swUseLocal   = findViewById(R.id.swUseLocal);
        tvStatus     = findViewById(R.id.tvStatus);
        Button btnSave = findViewById(R.id.btnSave);
        Button btnTest = findViewById(R.id.btnTest);

        SharedPreferences prefs = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE);
        etServerIp.setText(prefs.getString(MainActivity.KEY_SERVER_IP, ""));
        etServerPort.setText(prefs.getString(MainActivity.KEY_SERVER_PORT, "5000"));
        swUseLocal.setChecked(prefs.getBoolean(MainActivity.KEY_USE_LOCAL, true));

        updateStatus();

        swUseLocal.setOnCheckedChangeListener((CompoundButton btn, boolean checked) -> updateStatus());
        btnSave.setOnClickListener(v -> saveSettings());
        btnTest.setOnClickListener(v -> testConnection());
    }

    private void updateStatus() {
        if (swUseLocal.isChecked()) {
            tvStatus.setText("📴 Chế độ Offline · App dùng giao diện mặc định, không cần server");
            tvStatus.setTextColor(Color.parseColor("#7FDBFF"));
        } else {
            tvStatus.setText("🌐 Chế độ Online · App tải dashboard từ server Raspberry Pi / PC");
            tvStatus.setTextColor(Color.parseColor("#FF9B66"));
        }
    }

    private void saveSettings() {
        String ip   = etServerIp.getText().toString().trim();
        String port = etServerPort.getText().toString().trim();
        boolean useLocal = swUseLocal.isChecked();

        if (!useLocal && ip.isEmpty()) {
            etServerIp.setError("Nhập IP server hoặc bật chế độ Offline");
            return;
        }
        if (port.isEmpty()) port = "5000";

        SharedPreferences.Editor e = getSharedPreferences(MainActivity.PREFS, MODE_PRIVATE).edit();
        e.putString(MainActivity.KEY_SERVER_IP, ip);
        e.putString(MainActivity.KEY_SERVER_PORT, port);
        e.putBoolean(MainActivity.KEY_USE_LOCAL, useLocal);
        e.putBoolean(MainActivity.KEY_IP_CHANGED, true);
        e.apply();

        Toast.makeText(this,
                useLocal ? "Đã lưu · Chế độ Offline" : "Đã lưu · " + ip + ":" + port,
                Toast.LENGTH_SHORT).show();
        finish();
    }

    private void testConnection() {
        String ip = etServerIp.getText().toString().trim();
        String port = etServerPort.getText().toString().trim();
        if (ip.isEmpty()) { Toast.makeText(this, "Nhập IP trước", Toast.LENGTH_SHORT).show(); return; }
        if (port.isEmpty()) port = "5000";

        final String url = "http://" + ip + ":" + port + "/status";
        Toast.makeText(this, "Đang kết nối " + url, Toast.LENGTH_SHORT).show();

        new Thread(() -> {
            try {
                java.net.URL u = new java.net.URL(url);
                java.net.HttpURLConnection c = (java.net.HttpURLConnection) u.openConnection();
                c.setConnectTimeout(3000);
                c.setReadTimeout(3000);
                int code = c.getResponseCode();
                c.disconnect();
                runOnUiThread(() -> {
                    if (code == 200) Toast.makeText(this, "✅ Kết nối thành công!", Toast.LENGTH_LONG).show();
                    else Toast.makeText(this, "⚠️ Server trả về: " + code, Toast.LENGTH_LONG).show();
                });
            } catch (Exception ex) {
                runOnUiThread(() -> Toast.makeText(this,
                        "❌ Không kết nối được · " + ex.getMessage(), Toast.LENGTH_LONG).show());
            }
        }).start();
    }

    @Override public boolean onSupportNavigateUp() { finish(); return true; }
}
