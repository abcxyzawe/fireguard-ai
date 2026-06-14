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
│  bridge)    │  cam=2  │              │                  │ (cam+WiFi+   │
└──────▲──────┘         │   Stereo +   │                  │  bridge)     │
       │                │   Target     │                  └──────┬───────┘
       │                │   Lock +     │            UART GPIO13 → │ "pan,tilt,pump,burst\n"
       │                │   Ballistics │                  (3.3V)  ▼  → UNO D2
       │                └──────────────┘                  ┌──────────────┐
       │                                                  │ Arduino UNO  │
       │                                                  │ D9  → Servo PAN  │
       │                                                  │ D10 → Servo TILT │
       │                                                  │ D7  → Relay      │
       │                                                  └──────┬───────┘
       │                                                         │
       │                                                         ▼
       │                                                  ┌──────────────┐
       │                                                  │  Máy bơm     │
       │                                                  │  + Vòi phun  │
       │                                                  └──────────────┘
```

> **Kiến trúc:** ESP32-CAM 2 KHÔNG điều khiển servo trực tiếp (tránh xung đột timer
> LEDC với camera). Nó chỉ là **cầu nối**: nhận lệnh từ server qua WiFi rồi đẩy
> xuống Arduino UNO qua UART. UNO lo toàn bộ servo + relay + bơm.

## Pin assignments

### ESP32-CAM 2 (CONTROL / BRIDGE node)
| GPIO | Vai trò |
|------|---------|
| 13   | UART TX (3.3V) → Arduino UNO D2 (gửi lệnh "pan,tilt,pump,burst\n") |
| 0, 26, 27, 35, 34, 39, 36, 21, 19, 18, 5, 25, 23, 22, 32, 4 | Camera (đừng đụng) |

### Arduino UNO
| Pin | Vai trò |
|-----|---------|
| D2  | SoftwareSerial RX ← ESP32-CAM 2 GPIO13 (nhận lệnh, 9600 baud) |
| D3  | SoftwareSerial TX (không dùng, thư viện yêu cầu khai báo) |
| D9  | Servo PAN (MG90S — trục ngang) |
| D10 | Servo TILT (MG90 — trục dọc) |
| D7  | Relay điều khiển máy bơm (active HIGH default) |
| D8  | Buzzer (tuỳ chọn) |
| GND | **PHẢI nối chung** với ESP32-CAM 2 GND |

## Wiring

```
ESP32-CAM 2 GPIO13  ───────►  Arduino D2        (UART, 1 chiều, 3.3V→5V an toàn)
ESP32-CAM 2 GND     ───────►  Arduino GND       (BẮT BUỘC)
Arduino D9          ───────►  Servo PAN  signal (MG90S)
Arduino D10         ───────►  Servo TILT signal (MG90)
Arduino D7          ───────►  Relay IN
Arduino D8          ───────►  Buzzer (+)
Relay COM/NO        ───────►  Pump 12V circuit
Servo VCC (5V)      ───────►  Buck 5V riêng (đừng cấp từ chân 5V UNO)
Servo GND           ───────►  Buck GND + UNO GND chung
```

> ⚠️ **CHỈ nối 1 chiều ESP2 TX → UNO RX.** KHÔNG nối UNO TX (5V) vào ESP32 (3.3V)
> kẻo cháy ESP. Vì UNO không cần gửi ngược lại nên bỏ luôn chiều đó.
>
> ⚠️ **Cấp điện servo riêng** qua buck 5V, GND nối chung. MG90 nhẹ nhưng dòng đỉnh
> vẫn ~0.8A/con, cấp từ UNO sẽ gây reset.

## Nguồn điện (2× 18650)

```
2× 18650 NỐI TIẾP (2S = 7.4V)
   ├→ Arduino UNO (Vin 7.4V)
   ├→ Buck 5V  → 2× ESP32-CAM + Relay module
   └→ Buck 5V  → Servo PAN + Servo TILT   (+ tụ 2200µF)

Máy bơm → nguồn 12V RIÊNG (qua relay, GND chung)
```

- Servo MG90/MG90S nhẹ → pin 18650 thường (loại 5A) là đủ, không cần high-drain.
- Chạy được ~7-8 giờ với 2 pin 3000mAh.

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
5. **ESP32-CAM 2** (cầu nối): chuyển thành 1 dòng UART `"pan,tilt,pump,burst_ms\n"`
   gửi xuống UNO qua GPIO13 (9600 baud)
6. **Arduino UNO**:
   - Parse dòng lệnh
   - `servoPan.write(pan)`, `servoTilt.write(tilt)` (tự clamp góc an toàn)
   - Nếu `pump=1` → đóng relay → bơm chạy + buzzer kêu, tự tắt sau `burst_ms` (tối đa 5s)
   - Nếu `pump=0` → mở relay → bơm dừng
   - **An toàn**: mất lệnh từ ESP2 quá 8s → tự tắt bơm

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
