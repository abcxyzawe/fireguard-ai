# 🔥 FireGuard AI

**Hệ thống phát hiện và chữa cháy thông minh bằng AI**

Đồ án sinh viên — Đại học Công nghệ Đông Á (EAUT) · 2026

---

## 📌 Tổng quan

Hệ thống phát hiện lửa và khói tự động trong môi trường trong nhà bằng **AI thị giác máy (YOLOv8)** kết hợp ESP32-CAM, Raspberry Pi, Arduino và cơ cấu chấp hành (servo + relay + máy bơm). Phát hiện trong **< 1 giây**, tự động dập cháy bằng vòi phun định hướng.

### Điểm nổi bật

- **AI Detection**: YOLOv8s (mAP 88.2%) + 5 tiêu chí xác minh (color, core, gradient, texture, edge)
- **Smoke verification**: bộ lọc loại trừ + 3 tiêu chí (xám, texture thấp, cạnh thấp)
- **Motion check**: phân biệt lửa thật vs đèn LED, phản chiếu (vật tĩnh)
- **SAHI fallback**: phát hiện lửa nhỏ (bật lửa, tàn thuốc)
- **3 chế độ**: safe / sensitive / ultra_sensitive
- **Realtime** xử lý multi-camera, dashboard web + app Android + landing page

---

## 🗂️ Cấu trúc dự án

```
Kiem_soat_lua/
├── src/                    # Python Flask server + YOLO + verification logic
│   ├── server.py           # Main HTTP server (port 5000)
│   ├── fire_utils.py       # Verification, motion, flicker detector
│   ├── train.py, detect.py # Training & inference utilities
│   └── config.json         # Mode + threshold config
├── firmware/               # Arduino C++ code
│   ├── cam_sender/         # ESP32-CAM cam1 (push-mode HTTP POST)
│   ├── cam_trigger/cam2/   # ESP32-CAM cam2 (pull-mode trigger)
│   └── fire_turret/        # ESP32 + servo + bơm tích hợp
├── android/                # Native Android app (WebView + JS bridge)
│   ├── app/src/main/
│   │   ├── java/com/kiemsoatlua/app/   # MainActivity, FireAlertService
│   │   └── assets/www/                 # Bundled mobile UI
│   └── README.md
├── mobile/                 # HTML mobile app (cùng nguồn với android/assets/www)
├── client/                 # Web client app (dashboard cho user)
├── website/                # Landing page (marketing)
├── web/                    # Old React dashboard (legacy)
├── models/                 # YOLO weights (.pt - không commit, tải riêng)
└── output/                 # Generated artifacts (slides, charts) - không commit
```

---

## 🚀 Cách chạy

### 1. Server (Python + YOLO)

```bash
# Cài dependencies
pip install flask ultralytics opencv-python numpy sahi pyserial

# Tải model best.pt vào models/ (link Drive sẽ chia sẻ)

# Chạy
cd src
python server.py
```

Server: `http://localhost:5000`

### 2. ESP32-CAM (cam1 - push mode)

Mở `firmware/cam_sender/ESP32_CAM_ImagePoster/ESP32_CAM_ImagePoster.ino` trong Arduino IDE → đổi WiFi SSID/password và `serverUrl` → upload.

### 3. ESP32-CAM (cam2 - trigger mode)

Mở `firmware/cam_trigger/cam2/cam2.ino` → đổi WiFi → upload. Server tự gọi `/trigger` mỗi 3s.

### 4. Web client (dashboard cho user)

```bash
cd client
python -m http.server 9878
```

Mở `http://localhost:9878/`

### 5. Landing website

```bash
cd website
python -m http.server 9877
```

### 6. Android app

Mở `android/` trong Android Studio → Run ▶ trên điện thoại (đã bật USB debugging).

Xem chi tiết: [`android/README.md`](android/README.md).

---

## 🔧 Hardware

| Thiết bị | Vai trò |
|---|---|
| ESP32-CAM AI Thinker × 2 | Camera giám sát (cam1 + cam2) |
| Raspberry Pi 4 (6/8GB) | Server xử lý YOLO + Flask |
| Arduino UNO/Mega | Điều khiển servo + relay |
| Servo MG996R × 2 | Pan + tilt vòi phun |
| Relay 5V | Đóng/ngắt máy bơm |
| Máy bơm nước 12V | Phun nước dập lửa |

---

## 📱 App Mobile

App Android native (Java + WebView) ở folder `android/`. Build ra APK cài trên điện thoại, có:

- Push notification khi phát hiện cháy
- Background polling Flask server mỗi 3s
- Toggle Offline (UI có sẵn) / Online (server thật)
- JS bridge: vibrate, biometric, settings

---

## 📊 Mô hình AI

- **Architecture**: YOLOv8s
- **Dataset**: 38,517 ảnh train + 10,456 ảnh val (D-Fire + Indoor + NEWFireSmokeDataset)
- **Classes**: `[smoke, fire]`
- **Resolution**: 640×640
- **mAP50**: 88.2%
- **Latency**: ~15-30ms/ảnh trên RTX 4070, ~800-1500ms trên Raspberry Pi 4

---

## 👥 Team

- **Nguyễn Cảnh Trường** — DCCNTT13.10.3 — 20220443@eaut.edu.vn
- **Đỗ Quốc Anh** — DCCNTT14.C.2 — 20231996@eaut.edu.vn
- **Đào Việt Quang Huy** — DCCNTT14.C.2 — 20231907@eaut.edu.vn

**GVHD:** ThS. Đỗ Thị Huyền

---

## 📜 License

Đồ án sinh viên — Sử dụng cho mục đích học tập và nghiên cứu.

🔥 Made with ❤️ in Vietnam · 2026
