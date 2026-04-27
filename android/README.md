# FireGuard AI — Android App

Ứng dụng Android cho hệ thống phát hiện và chữa cháy thông minh FireGuard AI.

## 📱 Tính năng

- **WebView container** load giao diện mobile từ `assets/www/` (offline) hoặc từ server Flask (online)
- **Push notification** khi phát hiện cháy / khói, kèm vibrate pattern
- **Background service** tự động poll server mỗi 3 giây
- **JS Bridge** cho phép web code gọi Android native (vibrate, toast, open settings)
- **Toggle Offline / Online** trong Settings

## 🔧 Cách build và cài đặt

### Bước 1: Mở project trong Android Studio

```
File → Open → chọn folder E:\Kiem_soat_lua\android
```

Đợi Gradle sync xong (2-5 phút lần đầu).

### Bước 2: Kết nối điện thoại

- Bật **USB Debugging** trong Settings → Developer options
- Cắm điện thoại vào máy qua USB
- Chọn "Cho phép gỡ lỗi USB" khi điện thoại hỏi
- Trên thanh công cụ Android Studio, thiết bị sẽ hiện tên

### Bước 3: Build & chạy

**Cách 1 — Chạy trực tiếp (debug):**

```
Bấm nút ▶ Run (hoặc Shift+F10)
```

Android Studio sẽ build APK và cài lên điện thoại tự động. App tên **FireGuard AI** sẽ hiện trên màn hình chính.

**Cách 2 — Build APK để cài offline:**

```
Build → Build Bundle(s) / APK(s) → Build APK(s)
```

APK xuất ra tại: `android/app/build/outputs/apk/debug/app-debug.apk`

Copy APK sang điện thoại → mở file → cho phép cài "ứng dụng không rõ nguồn gốc" → cài.

## ⚙️ Cấu hình

Mở app → menu 3 chấm góc phải → **Cài đặt**:

- **Chế độ Offline** (bật mặc định): app dùng giao diện có sẵn trong APK, không cần server. Push notification vẫn hoạt động nếu có cấu hình IP
- **Chế độ Online**: tắt switch, nhập IP server Flask + port → app tải trực tiếp dashboard từ server
- **Kiểm tra kết nối**: nút test gửi GET `/status` tới server

### IP server ở đâu?

- **PC chạy hotspot**: Windows Settings → Mạng & Internet → Hotspot di động → IP thường là `192.168.137.1`
- **PC cùng WiFi router**: Mở terminal → `ipconfig` → tìm IPv4 Address (ví dụ `192.168.1.100`)
- **Raspberry Pi**: SSH vào Pi → `hostname -I` hoặc `ip addr`

## 📂 Cấu trúc

```
android/
├── app/
│   ├── build.gradle                                  # Dependencies
│   └── src/main/
│       ├── AndroidManifest.xml                        # Permissions + activities
│       ├── assets/www/                                # HTML mobile app (giống folder mobile/)
│       │   ├── index.html, home.html, login.html ...
│       │   └── assets/
│       ├── java/com/kiemsoatlua/app/
│       │   ├── MainActivity.java                      # WebView + JS bridge
│       │   ├── FireAlertService.java                  # Background poll + notification
│       │   └── SettingsActivity.java                  # IP/port config
│       └── res/
│           ├── layout/                                # XML layouts
│           ├── values/                                # colors, strings, styles
│           ├── drawable/                              # vector icons
│           ├── mipmap-anydpi-v26/                     # adaptive launcher icon
│           └── xml/network_security_config.xml       # cho phép HTTP cleartext
├── build.gradle                                       # Project-level
├── settings.gradle
└── gradle.properties
```

## 🔔 Cách notification hoạt động

1. App khởi động → `MainActivity` start `FireAlertService`
2. `FireAlertService` là foreground service → chạy ngay cả khi app bị đóng
3. Mỗi 3 giây, service gọi GET `http://<IP>:<PORT>/status` tới Flask server
4. Nếu response có `cameras.camX.fire = true` hoặc `smoke = true` → hiện notification + vibrate
5. Cooldown 10 giây giữa các lần alert (tránh spam)

Muốn ngắt service → vuốt xuống thanh thông báo → tap "Đang giám sát · An toàn" → kéo xuống → Force Stop

## 🐛 Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách fix |
|---|---|---|
| "Không kết nối được server" | Sai IP, firewall chặn, không cùng WiFi | Kiểm tra IP bằng `ipconfig`, tắt firewall, nối cùng WiFi |
| Build failed: `Could not resolve androidx.cardview` | Gradle chưa sync | File → Sync Project with Gradle Files |
| Notification không hiện | Chưa cấp quyền | Settings điện thoại → Apps → FireGuard → Permissions → Notifications ON |
| App không chạy background | Battery optimization | Settings → Battery → FireGuard → Không giới hạn |

## 🔗 JS Bridge API

Web code trong `assets/www/` có thể gọi:

```javascript
// Mở Settings activity
AndroidNative.openSettings();

// Vibrate ms
AndroidNative.vibrate(100);

// Toast message
AndroidNative.toast('Đã lưu!');

// Get cấu hình server
const url = AndroidNative.getServerUrl();  // "http://192.168.1.100:5000"

// App version
const v = AndroidNative.getAppVersion();   // "1.0"

// Thoát app
AndroidNative.exit();
```

Check có phải trong Android không:

```javascript
if (typeof AndroidNative !== 'undefined') {
  AndroidNative.vibrate(50);
} else {
  // Web fallback
  navigator.vibrate && navigator.vibrate(50);
}
```

## 📦 Xuất APK release (ký để cài trên Play Store hoặc chia sẻ)

```
Build → Generate Signed Bundle / APK
→ APK
→ Create new keystore (lưu kỹ password)
→ release variant
→ APK xuất tại: android/app/build/outputs/apk/release/app-release.apk
```

---

**Đồ án sinh viên · ĐH Công nghệ Đông Á · 2026**
