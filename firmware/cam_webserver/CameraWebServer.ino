#include "esp_camera.h"
#include <WiFi.h>

/* ================= CAMERA MODEL ================= */
#define CAMERA_MODEL_AI_THINKER
#include "board_config.h"

/* ================= CONFIG ================= */
const char *ssid     = "Op";
const char *password = "12345678";

#define WIFI_TIMEOUT_MS  15000
#define WIFI_RETRY_MS    30000

void startCameraServer();
void setupLedFlash();

bool wifiConnected = false;
unsigned long lastWiFiCheck = 0;

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
  Serial.setDebugOutput(true);
  Serial.println("\n=== CameraWebServer ===");

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
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  if (config.pixel_format == PIXFORMAT_JPEG) {
    if (psramFound()) {
      config.jpeg_quality = 10;
      config.fb_count = 2;
      config.grab_mode = CAMERA_GRAB_LATEST;
    } else {
      config.frame_size = FRAMESIZE_SVGA;
      config.fb_location = CAMERA_FB_IN_DRAM;
    }
  } else {
    config.frame_size = FRAMESIZE_240X240;
#if CONFIG_IDF_TARGET_ESP32S3
    config.fb_count = 2;
#endif
  }

#if defined(CAMERA_MODEL_ESP_EYE)
  pinMode(13, INPUT_PULLUP);
  pinMode(14, INPUT_PULLUP);
#endif

  /* Init camera */
  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init failed: 0x%x\n", err);
    while (true) { delay(1000); }  // Halt - khong chay loop() voi camera hong
  }

  /* Sensor config */
  sensor_t *s = esp_camera_sensor_get();
  if (s->id.PID == OV3660_PID) {
    s->set_vflip(s, 1);
    s->set_brightness(s, 1);
    s->set_saturation(s, -2);
  }
  if (config.pixel_format == PIXFORMAT_JPEG) {
    s->set_framesize(s, FRAMESIZE_QVGA);
  }

#if defined(CAMERA_MODEL_M5STACK_WIDE) || defined(CAMERA_MODEL_M5STACK_ESP32CAM)
  s->set_vflip(s, 1);
  s->set_hmirror(s, 1);
#endif

#if defined(CAMERA_MODEL_ESP32S3_EYE)
  s->set_vflip(s, 1);
#endif

#if defined(LED_GPIO_NUM)
  setupLedFlash();
#endif

  /* WiFi */
  wifiConnected = connectWiFi();
  if (!wifiConnected) {
    Serial.println("[WiFi] Will retry in loop()");
    return;
  }

  startCameraServer();

  Serial.print("[CAM] Ready: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/");
}

/* ================= LOOP ================= */
void loop() {
  // WiFi reconnect
  if (WiFi.status() != WL_CONNECTED) {
    if (wifiConnected) {
      Serial.println("[WiFi] Disconnected!");
      wifiConnected = false;
    }
    if (millis() - lastWiFiCheck > WIFI_RETRY_MS) {
      lastWiFiCheck = millis();
      if (connectWiFi()) {
        wifiConnected = true;
        startCameraServer();
        Serial.print("[CAM] Restarted: http://");
        Serial.print(WiFi.localIP());
        Serial.println("/");
      }
    }
  }
  delay(10000);
}
