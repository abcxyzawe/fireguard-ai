/*
 * FIRE TURRET - He thong phun nuoc dap lua tu dong
 * ESP32-CAM + 2 Servo (Pan/Tilt) + Relay bom nuoc
 *
 * Hoat dong:
 *   1. Chup anh tu camera
 *   2. POST anh len server, nhan JSON co toa do lua
 *   3. Xoay servo (pan X, tilt Y) huong vao vi tri lua
 *   4. Bat bom nuoc (relay) neu phat hien lua
 *
 * Ket noi phan cung:
 *   - Servo Pan  (ngang): GPIO 14
 *   - Servo Tilt (doc):   GPIO 15
 *   - Relay bom nuoc:     GPIO 13
 *   - LED trang thai:     GPIO 4 (flash LED co san)
 *
 * Luu y: GPIO 14, 15, 13 an toan cho ESP32-CAM AI-Thinker
 *         (khong xung dot voi camera/SD card)
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

/* ================= CAMERA MODEL ================= */
#define CAMERA_MODEL_AI_THINKER
#include "../cam_webserver/board_config.h"

/* ================= CONFIG ================= */
// === DOI WIFI THEO MANG CUA BAN ===
const char* ssid     = "Op";
const char* password = "12345678";

// === DOI IP THEO MAY CHAY SERVER ===
const char* serverURL = "http://10.199.56.144:5000/upload?cam=cam1";

// Timing
#define CAPTURE_INTERVAL_MS  800     // ~1.2 FPS
#define WIFI_TIMEOUT_MS      15000
#define WIFI_RETRY_MS        10000
#define HTTP_TIMEOUT_MS      10000

// Servo pins
#define SERVO_PAN_PIN   14    // Ngang (X) - trai/phai
#define SERVO_TILT_PIN  15    // Doc (Y)   - len/xuong
#define RELAY_PIN       13    // Relay bom nuoc
#define LED_PIN         4     // Flash LED

// Servo goc
#define PAN_MIN    0      // Goc nho nhat (do)
#define PAN_MAX    180    // Goc lon nhat
#define PAN_CENTER 90     // Vi tri trung tam
#define TILT_MIN   30     // Khong cho ngua qua
#define TILT_MAX   150    // Khong cho cui qua
#define TILT_CENTER 90

// Anh cam: 800x600 (SVGA)
#define IMG_WIDTH   800
#define IMG_HEIGHT  600

// Bom nuoc: bat bao lau sau khi mat lua (ms)
#define PUMP_HOLD_MS  3000   // Giu bom 3s sau khi het lua

// Bu trong luc - nghieng voi len tren de nuoc roi trung lua
// Tang gia tri neu nuoc roi duoi lua, giam neu nuoc bay qua dau
#define TILT_GRAVITY_OFFSET  5   // (do) - bu 5 do len tren

/* ================= GLOBALS ================= */
Servo servoPan;
Servo servoTilt;

int currentPanAngle  = PAN_CENTER;
int currentTiltAngle = TILT_CENTER;

bool wifiConnected = false;
unsigned long lastCapture = 0;
unsigned long lastWiFiCheck = 0;
unsigned long lastFireTime = 0;    // Lan cuoi phat hien lua
bool pumpActive = false;

/* ================= WIFI ================= */
bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(ssid, password);

  Serial.print("[WiFi] Connecting");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected - IP: " + WiFi.localIP().toString());
    return true;
  }
  Serial.println("\n[WiFi] FAILED");
  return false;
}

/* ================= SERVO CONTROL ================= */
void initServos() {
  servoPan.attach(SERVO_PAN_PIN, 500, 2400);
  servoTilt.attach(SERVO_TILT_PIN, 500, 2400);

  // Di chuyen ve trung tam
  servoPan.write(PAN_CENTER);
  servoTilt.write(TILT_CENTER);
  currentPanAngle = PAN_CENTER;
  currentTiltAngle = TILT_CENTER;

  Serial.println("[SERVO] Init OK - Center position");
}

void moveToTarget(int imgX, int imgY) {
  /*
   * Chuyen toa do anh (pixel) sang goc servo (do)
   *
   * imgX: 0 (trai) -> 640 (phai)
   * imgY: 0 (tren) -> 480 (duoi)
   *
   * Servo Pan:  0 (trai) -> 180 (phai)
   * Servo Tilt: 30 (tren) -> 150 (duoi)
   */

  // Map toa do anh -> goc servo
  int panAngle  = map(imgX, 0, IMG_WIDTH,  PAN_MIN, PAN_MAX);
  int tiltAngle = map(imgY, 0, IMG_HEIGHT, TILT_MIN, TILT_MAX);

  // Bu trong luc - nghieng len tren de nuoc roi trung muc tieu
  tiltAngle -= TILT_GRAVITY_OFFSET;

  // Constrain an toan
  panAngle  = constrain(panAngle,  PAN_MIN, PAN_MAX);
  tiltAngle = constrain(tiltAngle, TILT_MIN, TILT_MAX);

  // Di chuyen muot (smooth) - khong nhay dot ngot
  int panStep  = (panAngle > currentPanAngle) ? 1 : -1;
  int tiltStep = (tiltAngle > currentTiltAngle) ? 1 : -1;

  // Di chuyen tung buoc nho
  while (currentPanAngle != panAngle || currentTiltAngle != tiltAngle) {
    if (currentPanAngle != panAngle) {
      currentPanAngle += panStep;
      servoPan.write(currentPanAngle);
    }
    if (currentTiltAngle != tiltAngle) {
      currentTiltAngle += tiltStep;
      servoTilt.write(currentTiltAngle);
    }
    delay(5);  // Toc do di chuyen (~200 do/giay)
  }

  Serial.printf("[SERVO] Target: img(%d,%d) -> angle(pan=%d, tilt=%d)\n",
                imgX, imgY, panAngle, tiltAngle);
}

void returnToCenter() {
  moveToTarget(IMG_WIDTH / 2, IMG_HEIGHT / 2);
}

/* ================= PUMP CONTROL ================= */
void initPump() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);   // Tat bom
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial.println("[PUMP] Init OK - OFF");
}

void setPump(bool on) {
  if (on && !pumpActive) {
    digitalWrite(RELAY_PIN, HIGH);
    digitalWrite(LED_PIN, HIGH);   // LED bao dang phun
    pumpActive = true;
    Serial.println("[PUMP] ON - PHUN NUOC!");
  } else if (!on && pumpActive) {
    digitalWrite(RELAY_PIN, LOW);
    digitalWrite(LED_PIN, LOW);
    pumpActive = false;
    Serial.println("[PUMP] OFF");
  }
}

/* ================= PARSE RESPONSE ================= */
void handleServerResponse(String& payload) {
  /*
   * JSON response tu server:
   * {
   *   "fire": true/false,
   *   "smoke": true/false,
   *   "primary_target": { "x": 320, "y": 240, "conf": 0.85 },
   *   "fire_targets": [{ "center": [320,240], "bbox": [x1,y1,x2,y2] }],
   *   "image_size": [640, 480]
   * }
   */

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, payload);

  if (err) {
    Serial.printf("[JSON] Parse error: %s\n", err.c_str());
    return;
  }

  bool hasFire  = doc["fire"] | false;
  bool hasSmoke = doc["smoke"] | false;

  if (hasFire) {
    // Co lua! Lay toa do primary target
    JsonObject target = doc["primary_target"];
    if (!target.isNull()) {
      int tx = target["x"] | (IMG_WIDTH / 2);
      int ty = target["y"] | (IMG_HEIGHT / 2);
      float conf = target["conf"] | 0.0;

      Serial.printf("[FIRE] Phat hien lua tai (%d, %d) conf=%.1f%%\n",
                    tx, ty, conf * 100);

      // Xoay sung ve phia lua
      moveToTarget(tx, ty);

      // Bat bom nuoc
      setPump(true);
      lastFireTime = millis();
    }

    // In tat ca fire targets
    JsonArray targets = doc["fire_targets"];
    if (targets) {
      for (int i = 0; i < targets.size(); i++) {
        JsonObject t = targets[i];
        JsonArray center = t["center"];
        if (center) {
          Serial.printf("  [TARGET %d] center=(%d,%d) conf=%.0f%%\n",
                        i + 1,
                        (int)center[0], (int)center[1],
                        (float)(t["conf"] | 0) * 100);
        }
        JsonArray bbox = t["bbox"];
        if (bbox) {
          Serial.printf("             bbox=(%d,%d)-(%d,%d) area=%.1f%%\n",
                        (int)bbox[0], (int)bbox[1],
                        (int)bbox[2], (int)bbox[3],
                        (float)(t["area_percent"] | 0));
        }
      }
    }
  }
  else if (hasSmoke) {
    Serial.println("[SMOKE] Phat hien khoi - canh bao");
    // Chi canh bao, chua ban
  }
  else {
    Serial.println("[OK] An toan");

    // Tat bom sau PUMP_HOLD_MS ke tu lan cuoi thay lua
    if (pumpActive && (millis() - lastFireTime > PUMP_HOLD_MS)) {
      setPump(false);
      returnToCenter();
    }
  }
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  Serial.println("\n============================");
  Serial.println("  FIRE TURRET v1.0");
  Serial.println("  Phun nuoc dap lua tu dong");
  Serial.println("============================\n");

  // Init servo + pump
  initServos();
  initPump();

  // Camera config
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;

  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = FRAMESIZE_SVGA;     // 800x600
  config.jpeg_quality = 10;
  config.fb_count     = 1;
  config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location  = CAMERA_FB_IN_PSRAM;

  if (!psramFound()) {
    Serial.println("[CAM] No PSRAM");
    config.frame_size  = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_location  = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init failed: 0x%x\n", err);
    while (true) { delay(1000); }
  }

  sensor_t *s = esp_camera_sensor_get();
  s->set_brightness(s, 1);
  s->set_contrast(s, 1);
  s->set_saturation(s, -1);
  s->set_sharpness(s, 1);
  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);

  Serial.println("[CAM] Camera ready");

  // WiFi
  wifiConnected = connectWiFi();
}

/* ================= MAIN LOOP ================= */
void loop() {
  // Rate limit
  if (millis() - lastCapture < CAPTURE_INTERVAL_MS) {
    // Kiem tra tat bom khi khong co lua
    if (pumpActive && (millis() - lastFireTime > PUMP_HOLD_MS)) {
      setPump(false);
      returnToCenter();
    }
    delay(5);
    return;
  }
  lastCapture = millis();

  // WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    if (wifiConnected) {
      Serial.println("[WiFi] Disconnected!");
      wifiConnected = false;
    }
    if (millis() - lastWiFiCheck > WIFI_RETRY_MS) {
      lastWiFiCheck = millis();
      wifiConnected = connectWiFi();
    }
    return;
  } else if (!wifiConnected) {
    wifiConnected = true;
  }

  // Capture
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] Capture failed");
    return;
  }

  // POST anh len server
  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "image/jpeg");
  http.setTimeout(HTTP_TIMEOUT_MS);

  int code = http.POST(fb->buf, fb->len);

  if (code >= 200 && code < 300) {
    // Doc JSON response chua toa do lua
    String payload = http.getString();
    handleServerResponse(payload);
  } else if (code > 0) {
    Serial.printf("[POST] Server error: %d\n", code);
  } else {
    Serial.printf("[POST] Failed: %s\n", http.errorToString(code).c_str());
  }

  http.end();
  esp_camera_fb_return(fb);
}
