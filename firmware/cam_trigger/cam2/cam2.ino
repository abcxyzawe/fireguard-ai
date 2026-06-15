/* ============================================================================
 * FireGuard - ESP32-CAM 2 (CONTROL / BRIDGE node)
 *
 * Nhiem vu:
 *   - Chup anh & POST len server (cam2 = stereo right)
 *   - Nhan lenh tu server qua HTTP POST /control  {pan, tilt, pump, burst_ms}
 *   - CHUYEN TIEP lenh xuong Arduino UNO qua UART (GPIO13 -> UNO D2)
 *
 * KHONG dieu khien servo truc tiep -> UNO lo servo + relay + bom
 * (tranh xung dot timer LEDC giua camera va servo tren ESP32-CAM).
 *
 * *** KHONG can thu vien ArduinoJson - tu parse JSON bang tay ***
 *
 * Pin map:
 *   GPIO 13 -> UART TX (3.3V) -> Arduino UNO D2 (SoftwareSerial RX)
 *   GND     <->                  Arduino UNO GND   *** BAT BUOC chung GND ***
 *
 * Giao thuc UART (ESP2 -> UNO, 9600 baud):
 *   "<pan>,<tilt>,<pump>,<burst_ms>\n"
 * ========================================================================== */

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WebServer.h>

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

/* ================= UART -> ARDUINO UNO ================= */
#define PIN_UART_TX  13          // ESP2 GPIO13 -> UNO D2 (RX). RX khong dung.
#define UNO_BAUD     9600
HardwareSerial UnoSerial(1);     // UART1 cua ESP32

/* ================= CONFIG ================= */
const char* ssid     = "Op";
const char* password = "12345678";
const char* serverHost = "10.199.56.144";  // IP laptop chay server
const int   serverPort = 5000;

#define CAPTURE_INTERVAL_MS 500
#define WIFI_TIMEOUT_MS    15000
#define WIFI_RETRY_MS      10000
#define HTTP_TIMEOUT_MS     5000

#define PAN_HOME   90
#define TILT_HOME  90

/* ================= STATE ================= */
WebServer httpServer(80);
unsigned long lastCapture = 0;
unsigned long lastWiFiCheck = 0;
bool wifiConnected = false;

int  lastPan  = PAN_HOME;
int  lastTilt = TILT_HOME;
bool lastPump = false;

/* ================= PARSE JSON BANG TAY (khong can thu vien) ================= */
// Lay so nguyen cho 1 key trong chuoi JSON. VD: jsonInt(body, "pan", 90)
long jsonInt(const String& s, const char* key, long defVal) {
  String pat = String("\"") + key + "\"";
  int k = s.indexOf(pat);
  if (k < 0) return defVal;
  int colon = s.indexOf(':', k + pat.length());
  if (colon < 0) return defVal;
  int i = colon + 1;
  while (i < (int)s.length() && (s[i] == ' ' || s[i] == '\t')) i++;
  bool neg = false;
  if (i < (int)s.length() && s[i] == '-') { neg = true; i++; }
  long val = 0; bool got = false;
  while (i < (int)s.length() && isDigit(s[i])) { val = val * 10 + (s[i] - '0'); i++; got = true; }
  if (!got) return defVal;
  return neg ? -val : val;
}

// Lay boolean (true/false hoac 1/0) cho 1 key
bool jsonBool(const String& s, const char* key, bool defVal) {
  String pat = String("\"") + key + "\"";
  int k = s.indexOf(pat);
  if (k < 0) return defVal;
  int colon = s.indexOf(':', k + pat.length());
  if (colon < 0) return defVal;
  int i = colon + 1;
  while (i < (int)s.length() && (s[i] == ' ' || s[i] == '\t')) i++;
  if (s[i] == 't' || s[i] == '1') return true;
  if (s[i] == 'f' || s[i] == '0') return false;
  return defVal;
}

/* ================= GUI LENH XUONG UNO ================= */
void sendToUno(int pan, int tilt, bool pump, int burst_ms) {
  UnoSerial.print(pan);    UnoSerial.print(',');
  UnoSerial.print(tilt);   UnoSerial.print(',');
  UnoSerial.print(pump ? 1 : 0); UnoSerial.print(',');
  UnoSerial.print(burst_ms);
  UnoSerial.print('\n');
  lastPan = pan; lastTilt = tilt; lastPump = pump;
  Serial.printf("[UNO] -> %d,%d,%d,%d\n", pan, tilt, pump ? 1 : 0, burst_ms);
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
// GET /status
void handleStatus() {
  String out = "{";
  out += "\"device\":\"ESP32-CAM-2\",";
  out += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  out += "\"pan\":" + String(lastPan) + ",";
  out += "\"tilt\":" + String(lastTilt) + ",";
  out += "\"pump\":" + String(lastPump ? "true" : "false");
  out += "}";
  httpServer.send(200, "application/json", out);
}

// POST /control  body: {"pan":90,"tilt":60,"pump":true,"burst_ms":2500}
void handleControl() {
  if (httpServer.method() != HTTP_POST) {
    httpServer.send(405, "text/plain", "POST only");
    return;
  }
  String body = httpServer.arg("plain");

  int  pan      = (int)jsonInt(body, "pan",  lastPan);
  int  tilt     = (int)jsonInt(body, "tilt", lastTilt);
  bool pump     = jsonBool(body, "pump", false);
  int  burst_ms = (int)jsonInt(body, "burst_ms", 0);

  sendToUno(pan, tilt, pump, burst_ms);

  String out = "{\"ok\":true,";
  out += "\"pan\":" + String(pan) + ",";
  out += "\"tilt\":" + String(tilt) + ",";
  out += "\"pump\":" + String(pump ? "true" : "false");
  out += "}";
  httpServer.send(200, "application/json", out);
}

// GET /home -> servo ve giua, tat bom
void handleHome() {
  sendToUno(PAN_HOME, TILT_HOME, false, 0);
  httpServer.send(200, "text/plain", "homed");
}

/* ================= SETUP ================= */
void setup() {
  Serial.begin(115200);
  Serial.println("\n=== ESP32-CAM 2 (CONTROL / BRIDGE) ===");

  // UART xuong UNO: chi dung chan TX (GPIO13), RX = -1
  UnoSerial.begin(UNO_BAUD, SERIAL_8N1, -1, PIN_UART_TX);
  delay(200);
  sendToUno(PAN_HOME, TILT_HOME, false, 0);

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

  wifiConnected = connectWiFi();

  httpServer.on("/status",  HTTP_GET,  handleStatus);
  httpServer.on("/home",    HTTP_GET,  handleHome);
  httpServer.on("/control", HTTP_POST, handleControl);
  httpServer.begin();
  Serial.println("[HTTP] :80  (/control, /status, /home)");
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
  httpServer.handleClient();

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
