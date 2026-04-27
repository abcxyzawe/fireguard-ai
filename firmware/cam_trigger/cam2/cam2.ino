/* ============================================================================
 * FireGuard - ESP32-CAM 2 (CONTROL node)
 * - Capture & POST images to server (cam2 = stereo right)
 * - Receive servo commands (pan, tilt) from server via HTTP /control
 * - Output digital HIGH/LOW on GPIO13 -> Arduino UNO -> Relay -> Pump
 * - Burst firing: HIGH for N ms then auto LOW
 *
 * Pin map:
 *   GPIO 14 -> Servo PAN  signal
 *   GPIO 15 -> Servo TILT signal
 *   GPIO 13 -> Pump trigger output (to Arduino digital input)
 * ========================================================================== */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>

/* ================= CAMERA PINS (AI THINKER) ================= */
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22
#define LED_GPIO_NUM       4

/* ================= ACTUATOR PINS ================= */
#define PIN_SERVO_PAN     14   // Pan servo signal
#define PIN_SERVO_TILT    15   // Tilt servo signal
#define PIN_PUMP_TRIGGER  13   // Digital out -> Arduino input

/* ================= CONFIG ================= */
const char* ssid     = "Op";
const char* password = "12345678";
const char* serverHost = "10.199.56.144";  // Laptop server IP
const int   serverPort = 5000;

#define CAPTURE_INTERVAL_MS 500   // 2 FPS for stereo pairing
#define WIFI_TIMEOUT_MS    15000
#define WIFI_RETRY_MS      10000
#define HTTP_TIMEOUT_MS     5000

// Servo limits (degrees)
#define PAN_MIN   0
#define PAN_MAX   180
#define TILT_MIN  20    // don't aim into ground
#define TILT_MAX  160
#define PAN_HOME  90
#define TILT_HOME 90

// Burst firing safety
#define BURST_MAX_MS  5000   // never longer than 5 seconds

/* ================= STATE ================= */
Servo servoPan;
Servo servoTilt;
WebServer httpServer(80);

unsigned long lastCapture = 0;
unsigned long lastWiFiCheck = 0;
bool wifiConnected = false;

int currentPan = PAN_HOME;
int currentTilt = TILT_HOME;
unsigned long pumpUntilMs = 0;   // 0 = pump off

/* ================= UTIL ================= */
int clampInt(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

void applyServos(int pan, int tilt) {
  pan  = clampInt(pan,  PAN_MIN,  PAN_MAX);
  tilt = clampInt(tilt, TILT_MIN, TILT_MAX);
  servoPan.write(pan);
  servoTilt.write(tilt);
  currentPan = pan;
  currentTilt = tilt;
}

void setPump(bool on) {
  digitalWrite(PIN_PUMP_TRIGGER, on ? HIGH : LOW);
}

void startBurst(int ms) {
  ms = clampInt(ms, 0, BURST_MAX_MS);
  if (ms <= 0) {
    pumpUntilMs = 0;
    setPump(false);
    return;
  }
  pumpUntilMs = millis() + ms;
  setPump(true);
}

/* ================= WIFI ================= */
bool connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(100);
  WiFi.setSleep(false);
  WiFi.begin(ssid, password);
  Serial.print("[WiFi] Connecting");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < WIFI_TIMEOUT_MS) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.print("[WiFi] IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }
  Serial.println("\n[WiFi] FAILED");
  return false;
}

/* ================= HTTP HANDLERS ================= */
// GET /status - simple health check
void handleStatus() {
  StaticJsonDocument<256> doc;
  doc["device"] = "ESP32-CAM-2";
  doc["ip"]     = WiFi.localIP().toString();
  doc["pan"]    = currentPan;
  doc["tilt"]   = currentTilt;
  doc["pump"]   = (pumpUntilMs != 0 && millis() < pumpUntilMs);
  String out;
  serializeJson(doc, out);
  httpServer.send(200, "application/json", out);
}

// POST /control - receive command from server
// Body JSON: { "pan": 90, "tilt": 60, "pump": true, "burst_ms": 2500 }
void handleControl() {
  if (httpServer.method() != HTTP_POST) {
    httpServer.send(405, "text/plain", "POST only");
    return;
  }
  String body = httpServer.arg("plain");
  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    httpServer.send(400, "text/plain", "Bad JSON");
    return;
  }

  bool changed = false;
  if (doc.containsKey("pan") || doc.containsKey("tilt")) {
    int pan  = doc["pan"]  | currentPan;
    int tilt = doc["tilt"] | currentTilt;
    applyServos(pan, tilt);
    changed = true;
  }

  if (doc.containsKey("pump")) {
    bool pumpOn = doc["pump"].as<bool>();
    if (pumpOn) {
      int ms = doc["burst_ms"] | 2500;  // default 2.5s burst
      startBurst(ms);
    } else {
      pumpUntilMs = 0;
      setPump(false);
    }
    changed = true;
  }

  StaticJsonDocument<128> resp;
  resp["ok"] = true;
  resp["pan"] = currentPan;
  resp["tilt"] = currentTilt;
  resp["pump"] = (pumpUntilMs != 0 && millis() < pumpUntilMs);
  String out;
  serializeJson(resp, out);
  httpServer.send(200, "application/json", out);
}

// GET /home - reset servos to home, pump off
void handleHome() {
  applyServos(PAN_HOME, TILT_HOME);
  pumpUntilMs = 0;
  setPump(false);
  httpServer.send(200, "text/plain", "homed");
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32-CAM 2 (CONTROL node) ===");

  // Pump trigger: default LOW
  pinMode(PIN_PUMP_TRIGGER, OUTPUT);
  digitalWrite(PIN_PUMP_TRIGGER, LOW);

  // Servos: attach + go home
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  servoPan.setPeriodHertz(50);
  servoTilt.setPeriodHertz(50);
  servoPan.attach(PIN_SERVO_PAN, 500, 2400);
  servoTilt.attach(PIN_SERVO_TILT, 500, 2400);
  applyServos(PAN_HOME, TILT_HOME);

  // Camera
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    config.frame_size  = FRAMESIZE_SVGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;
    config.grab_mode = CAMERA_GRAB_LATEST;
    config.fb_location = CAMERA_FB_IN_PSRAM;
  } else {
    config.frame_size = FRAMESIZE_CIF;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM2] init failed: 0x%x\n", err);
    while (true) delay(1000);
  }

  sensor_t* s = esp_camera_sensor_get();
  s->set_brightness(s, 1);
  s->set_contrast(s, 1);
  s->set_saturation(s, -1);
  s->set_sharpness(s, 1);
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
  s->set_denoise(s, 1);
  Serial.println("[CAM2] Camera ready");

  // WiFi
  wifiConnected = connectWiFi();

  // HTTP server (for /control)
  httpServer.on("/status",  HTTP_GET,  handleStatus);
  httpServer.on("/home",    HTTP_GET,  handleHome);
  httpServer.on("/control", HTTP_POST, handleControl);
  httpServer.begin();
  Serial.println("[HTTP] Server on :80 (/control, /status, /home)");
}

/* ================= LOOP ================= */
void postImage() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return;
  HTTPClient http;
  String url = "http://" + String(serverHost) + ":" + String(serverPort) + "/upload?cam=cam2";
  http.begin(url);
  http.addHeader("Content-Type", "image/jpeg");
  http.setTimeout(HTTP_TIMEOUT_MS);
  int code = http.POST(fb->buf, fb->len);
  if (code < 200 || code >= 300) {
    Serial.printf("[CAM2] POST err: %d\n", code);
  }
  http.end();
  esp_camera_fb_return(fb);
}

void loop() {
  // Handle HTTP control requests
  httpServer.handleClient();

  // Auto-stop pump when burst expires
  if (pumpUntilMs != 0 && millis() >= pumpUntilMs) {
    pumpUntilMs = 0;
    setPump(false);
    Serial.println("[PUMP] Burst done -> OFF");
  }

  // Periodic image upload
  if (millis() - lastCapture >= CAPTURE_INTERVAL_MS) {
    lastCapture = millis();

    if (WiFi.status() != WL_CONNECTED) {
      if (wifiConnected) { Serial.println("[WiFi] disconnected"); wifiConnected = false; }
      if (millis() - lastWiFiCheck > WIFI_RETRY_MS) {
        lastWiFiCheck = millis();
        wifiConnected = connectWiFi();
      }
      return;
    } else if (!wifiConnected) wifiConnected = true;

    postImage();
  }
}
