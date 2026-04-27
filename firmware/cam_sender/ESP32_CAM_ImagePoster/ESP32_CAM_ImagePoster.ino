#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

/* ================= AI THINKER ESP32-CAM PINS ================= */
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

/* ================= CONFIG ================= */
// === DOI WIFI THEO MANG CUA BAN ===
// Neu dung hotspot laptop: ten hotspot va mat khau
const char* ssid = "Op";
const char* password = "12345678";

// === DOI IP THEO MAY CHAY SERVER ===
// Hotspot laptop: 192.168.137.1 | Cung WiFi router: IP may tinh
const char* serverURL = "http://10.199.56.144:5000/upload?cam=cam1";

#define CAPTURE_INTERVAL_MS 100  // 10 FPS
#define WIFI_TIMEOUT_MS 15000    // 15s timeout
#define WIFI_RETRY_MS 10000      // Retry moi 10s
#define HTTP_TIMEOUT_MS 10000    // HTTP timeout

unsigned long lastCapture = 0;
unsigned long lastWiFiCheck = 0;
bool wifiConnected = false;

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
    Serial.println("\n[WiFi] Connected");
    Serial.print("[WiFi] IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("\n[WiFi] FAILED");
  return false;
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  Serial.setDebugOutput(false);
  Serial.println("\n=== ESP32-CAM Image Poster ===");

  /* Camera config - zero init */
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
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

  // Chat luong anh - SVGA net, double buffer
  config.frame_size = FRAMESIZE_SVGA;     // 800x600 - detect lua nho tot hon
  config.jpeg_quality = 10;               // 10 = chat luong tot
  config.fb_count = 2;                    // Double buffer - chup lien tuc
  config.grab_mode = CAMERA_GRAB_LATEST;  // Luon lay frame moi nhat
  config.fb_location = CAMERA_FB_IN_PSRAM;

  if (!psramFound()) {
    Serial.println("[CAM] No PSRAM - lowering quality");
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  /* Init camera */
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init failed: 0x%x\n", err);
    while (true) { delay(1000); }  // Halt
  }

  /* Sensor tuning cho fire/smoke */
  sensor_t* s = esp_camera_sensor_get();
  s->set_brightness(s, 1);
  s->set_contrast(s, 1);
  s->set_saturation(s, -1);
  s->set_sharpness(s, 1);
  s->set_vflip(s, 1);    // Xoay doc 180
  s->set_hmirror(s, 1);  // Xoay ngang (guong)
  s->set_gain_ctrl(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_whitebal(s, 1);
  s->set_awb_gain(s, 1);
  s->set_denoise(s, 1);
  s->set_ae_level(s, 0);
  // hmirror va vflip da bat o tren (xoay 180)

  Serial.println("[CAM] Camera ready");

  /* WiFi */
  wifiConnected = connectWiFi();
  if (!wifiConnected) {
    Serial.println("[WiFi] Will retry in loop()");
  }
}

/* ================= LOOP ================= */
void loop() {
  // Rate limit
  if (millis() - lastCapture < CAPTURE_INTERVAL_MS) {
    delay(5);
    return;
  }
  lastCapture = millis();

  // WiFi check & reconnect
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
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] Capture failed");
    return;
  }

  // POST to server
  HTTPClient http;
  http.begin(serverURL);
  http.addHeader("Content-Type", "image/jpeg");
  http.setTimeout(HTTP_TIMEOUT_MS);

  int code = http.POST(fb->buf, fb->len);

  if (code >= 200 && code < 300) {
    Serial.printf("[POST] OK (%d) - %u bytes\n", code, fb->len);
  } else if (code > 0) {
    Serial.printf("[POST] Server error: %d\n", code);
  } else {
    Serial.printf("[POST] Failed: %s\n", http.errorToString(code).c_str());
  }

  http.end();
  esp_camera_fb_return(fb);
}
