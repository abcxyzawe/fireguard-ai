# 🎯 FireGuard Turret System

Hệ thống turret tự động bám theo lửa, dùng stereo vision (2 ESP32-CAM) tính khoảng cách + bù góc bắn nước.

## Sơ đồ kiến trúc

```
┌─────────────┐  WiFi   ┌──────────────┐
│ ESP32-CAM 1 │ ──────▶ │              │
│ (vision)    │  /upload│              │
└─────────────┘  cam=1  │              │
                        │              │   POST /control
┌─────────────┐  WiFi   │   Laptop     │   {pan,tilt,pump,burst_ms}
│ ESP32-CAM 2 │ ──────▶ │   Server     │ ──────────────▶ ┌──────────────┐
│ (vision +   │  /upload│   Flask      │                  │ ESP32-CAM 2  │
│  control)   │  cam=2  │              │                  │ + 2 servos   │
└──────▲──────┘         │   Stereo +   │                  │ + GPIO out   │
       │                │   Target     │                  └──────┬───────┘
       │                │   Lock +     │                         │ GPIO13 HIGH/LOW
       │                │   Ballistics │                         ▼
       │                └──────────────┘                  ┌──────────────┐
       │                                                  │ Arduino UNO  │
       │                                                  │ D7 input     │
       │                                                  │ D8 → relay   │
       └─── controls servos directly via PWM              └──────┬───────┘
                                                                 │
                                                                 ▼
                                                         ┌──────────────┐
                                                         │  Máy bơm     │
                                                         │  + Vòi phun  │
                                                         └──────────────┘
```

## Pin assignments

### ESP32-CAM 2 (CONTROL node)
| GPIO | Vai trò |
|------|---------|
| 14   | Servo PAN PWM signal |
| 15   | Servo TILT PWM signal |
| 13   | Pump trigger output (digital, → Arduino D7) |
| 0, 26, 27, 35, 34, 39, 36, 21, 19, 18, 5, 25, 23, 22, 32, 4 | Camera (đừng đụng) |

### Arduino UNO
| Pin | Vai trò |
|-----|---------|
| D7  | INPUT digital từ ESP32-CAM 2 GPIO13 |
| D8  | OUTPUT điều khiển coil relay (active HIGH default) |
| D9  | OUTPUT buzzer (tuỳ chọn) |
| GND | **PHẢI nối chung** với ESP32-CAM 2 GND |

## Wiring

```
ESP32-CAM 2 GPIO13  ───────►  Arduino D7
ESP32-CAM 2 GND     ───────►  Arduino GND        (BẮT BUỘC)
Arduino D8          ───────►  Relay IN
Relay COM/NO        ───────►  Pump 12V circuit
Servo PAN  signal   ───────►  ESP32-CAM 2 GPIO14
Servo TILT signal   ───────►  ESP32-CAM 2 GPIO15
Servo VCC (5V)      ───────►  External 5V supply (đừng cấp từ ESP)
Servo GND           ───────►  External 5V GND + ESP GND
```

> ⚠️ **Cấp điện servo riêng**: Servo MG996R kéo dòng 1-2A khi tải, ESP32 không kham nổi. Dùng nguồn 5V 3A riêng, GND nối chung với ESP.

## Flow điều khiển

1. **ESP32-CAM 1** gửi ảnh → server detect lửa → lưu bbox vào `last_detection_result["cam1"]`
2. **ESP32-CAM 2** gửi ảnh → server detect lửa → lưu bbox vào `last_detection_result["cam2"]`
3. **Background turret loop** (2.5 Hz) trong server:
   - Đọc bbox từ cam1 + cam2
   - Pair bbox bằng `stereo.match_bbox()` → tính disparity → distance R
   - **Target selection**: chọn bbox gần tâm ảnh nhất (cam1 = reference)
   - **Target locking**: nếu target cũ overlap (IoU > 0.2) → giữ; ngược lại pick mới
   - Tính pan/tilt từ pixel error
   - **Distance compensation**: cộng `θ = ½ arcsin(gR/v²)` vào tilt (nâng nòng lên)
   - Nếu target ở giữa frame **3 frame liên tiếp** + đã qua cooldown 4s → set `pump=true, burst_ms=2500`
4. Server `POST /control` đến ESP32-CAM 2 với `{pan, tilt, pump, burst_ms}`
5. **ESP32-CAM 2**:
   - `servoPan.write(pan)`, `servoTilt.write(tilt)`
   - Nếu `pump=true` → digital HIGH chân GPIO13 trong `burst_ms` mili giây → tự động LOW
6. **Arduino UNO**:
   - Đọc D7 (debounce 30ms)
   - HIGH → đóng relay → bơm chạy + buzzer kêu
   - LOW → mở relay → bơm dừng

## Công thức bù góc

User-specified ballistic:

$$\theta = \frac{1}{2} \arcsin\left(\frac{gR}{v^2}\right)$$

| Tham số | Giá trị |
|---------|---------|
| g       | 9.81 m/s² |
| v       | 67 m/s (vận tốc đầu của tia nước) |
| R       | Khoảng cách camera→mục tiêu (mét, từ stereo) |
| θ       | Góc bù (radian, +up) → convert sang degrees để cộng vào tilt |

Ví dụ:
- R = 1m  → θ ≈ 0.063°
- R = 5m  → θ ≈ 0.31°
- R = 50m → θ ≈ 3.13°

(Vận tốc cao 67 m/s nên bù rất nhỏ ở khoảng cách indoor.)

## Server endpoints (mới)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET    | `/turret/state`   | Trạng thái controller (pan, tilt, target, distance) |
| POST   | `/turret/process` | Chạy 1 chu kỳ điều khiển (manual) |
| POST   | `/turret/home`    | Reset servo về home, tắt bơm |
| GET    | `/turret/config`  | Lấy URL ESP32-CAM 2 |
| POST   | `/turret/config`  | Set URL ESP32-CAM 2 (`{"esp2_url":"http://10.199.56.103"}`) |

## Stereo calibration

User said sẽ tự calibrate. Trong `src/stereo.py`:

```python
BASELINE_M = 0.05    # khoảng cách giữa 2 cam (mét), đo bằng thước
FOCAL_PX   = 570.0   # focal length (pixel), từ checkerboard calibration
```

Update 2 hằng số này sau khi calibrate. Càng chuẩn → distance càng chính xác.

## Cấu hình lúc chạy

### Cách 1: env variable trước khi start server

```bash
# Linux / macOS
export ESP2_URL="http://192.168.1.103"
python src/server.py

# Windows PowerShell
$env:ESP2_URL = "http://192.168.1.103"
python src/server.py
```

### Cách 2: HTTP POST sau khi server chạy

```bash
curl -X POST http://localhost:5000/turret/config \
  -H "Content-Type: application/json" \
  -d '{"esp2_url":"http://192.168.1.103"}'
```

## Test thử nhanh

```bash
# 1. Server status
curl http://localhost:5000/turret/state

# 2. Chạy 1 chu kỳ thủ công
curl -X POST http://localhost:5000/turret/process

# 3. Reset turret về home
curl -X POST http://localhost:5000/turret/home

# 4. Test ESP2 trực tiếp (không qua server)
curl -X POST http://192.168.1.103/control \
  -H "Content-Type: application/json" \
  -d '{"pan":120,"tilt":80,"pump":true,"burst_ms":1000}'
```

## Cấu hình cooldown / threshold

Trong `src/turret_controller.py`:

```python
CENTER_TOLERANCE_PX  = 40      # ± px → "đã ở giữa"
STABLE_FRAMES        = 3       # số frame phải centered liên tục mới fire
BURST_DURATION_MS    = 2500    # thời gian phun mỗi lần
BURST_COOLDOWN_S     = 4.0     # khoảng cách tối thiểu giữa 2 lần phun
```

## Safety notes

- **Burst max 5 giây** (cứng trong cam2.ino) — dù server gửi 99999ms cũng chỉ chạy 5s
- **Servo limits** — cam2.ino clamp pan/tilt vào range an toàn
- **Pump auto-off** — ESP2 luôn auto-LOW sau `burst_ms` ms
- **Mất kết nối** — Arduino debounce 30ms, không phụ thuộc server
- **GND chung ESP↔Arduino** là tối quan trọng, nếu không signal HIGH/LOW không đáng tin
