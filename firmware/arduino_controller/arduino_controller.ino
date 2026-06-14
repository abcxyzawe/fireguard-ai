/* ============================================================================
 * FireGuard - ARDUINO UNO (Turret Controller)
 *
 * Nhan lenh tu ESP32-CAM 2 qua UART (SoftwareSerial), dieu khien:
 *   - 2 servo MG90:  PAN (ngang) + TILT (doc)
 *   - Relay may bom nuoc
 *   - Buzzer canh bao (keu khi bom chay)
 *
 * Giao thuc UART (ESP2 -> UNO, 9600 baud, moi lenh 1 dong):
 *   "<pan>,<tilt>,<pump>,<burst_ms>\n"
 *   vd:  "90,60,1,2500\n"  = pan 90, tilt 60, bom BAT 2500ms roi tu tat
 *        "90,60,0,0\n"     = pan 90, tilt 60, bom TAT
 *
 * Pin map (Arduino UNO):
 *   D2  <- SoftwareSerial RX  <- ESP32-CAM2 GPIO13 (TX, 3.3V)  *** chi 1 chieu ***
 *   D3  -> SoftwareSerial TX  (khong dung, thu vien yeu cau khai bao)
 *   D9  -> Servo PAN  (MG90S - truc ngang)
 *   D10 -> Servo TILT (MG90  - truc doc)
 *   D7  -> Relay (may bom).  RELAY_ACTIVE_HIGH=true: HIGH = bom chay
 *   D8  -> Buzzer (tuy chon)
 *   GND <-> ESP32-CAM2 GND   *** BAT BUOC chung GND ***
 *
 * Luu y phan cung:
 *   - ESP2 TX 3.3V -> UNO RX (D2): UNO doc 3.3V la HIGH -> OK, an toan.
 *   - KHONG noi UNO TX (5V) vao ESP2 (se hong ESP32). Chi giao tiep 1 chieu.
 *   - Servo cap nguon 5V RIENG (buck), GND chung. Khong cap tu chan 5V UNO.
 * ========================================================================== */

#include <Servo.h>
#include <SoftwareSerial.h>

/* ================= PIN ================= */
#define PIN_RX_FROM_ESP  2     // SoftwareSerial RX  <- ESP2 GPIO13
#define PIN_TX_DUMMY     3     // SoftwareSerial TX  (khong dung)
#define PIN_SERVO_PAN    9     // MG90S - truc ngang
#define PIN_SERVO_TILT   10    // MG90  - truc doc
#define PIN_RELAY        7     // Relay bom
#define PIN_BUZZER       8     // Buzzer

#define RELAY_ACTIVE_HIGH true // false neu module relay la active-LOW
#define BUZZER_HZ        2200

/* ================= SERVO LIMITS ================= */
#define PAN_MIN    0
#define PAN_MAX    180
#define TILT_MIN   20         // khong chia xuong dat
#define TILT_MAX   160
#define PAN_HOME   90
#define TILT_HOME  90

/* ================= SAFETY ================= */
#define BURST_MAX_MS      5000UL   // bom toi da 5s/lan du lenh gui dai hon
#define CMD_TIMEOUT_MS    8000UL   // mat lenh > 8s -> tat bom (an toan)

/* ================= STATE ================= */
SoftwareSerial espSerial(PIN_RX_FROM_ESP, PIN_TX_DUMMY);
Servo servoPan;
Servo servoTilt;

int  curPan  = PAN_HOME;
int  curTilt = TILT_HOME;
bool pumpOn  = false;

unsigned long pumpUntilMs = 0;      // 0 = bom tat
unsigned long lastCmdMs   = 0;      // luc nhan lenh gan nhat

char  buf[48];
uint8_t bufLen = 0;

/* ================= HELPERS ================= */
int clampInt(int v, int lo, int hi) {
  if (v < lo) return lo;
  if (v > hi) return hi;
  return v;
}

void setRelay(bool on) {
  if (RELAY_ACTIVE_HIGH) digitalWrite(PIN_RELAY, on ? HIGH : LOW);
  else                   digitalWrite(PIN_RELAY, on ? LOW  : HIGH);
}

void setBuzzer(bool on) {
  if (on) tone(PIN_BUZZER, BUZZER_HZ);
  else    noTone(PIN_BUZZER);
}

void setPump(bool on) {
  if (on == pumpOn) return;
  pumpOn = on;
  setRelay(on);
  setBuzzer(on);
  Serial.print(F("[PUMP] "));
  Serial.println(on ? F("ON  (bom chay)") : F("OFF (bom tat)"));
}

void applyServos(int pan, int tilt) {
  pan  = clampInt(pan,  PAN_MIN,  PAN_MAX);
  tilt = clampInt(tilt, TILT_MIN, TILT_MAX);
  if (pan != curPan)  { servoPan.write(pan);   curPan  = pan; }
  if (tilt != curTilt){ servoTilt.write(tilt); curTilt = tilt; }
}

/* ================= PARSE 1 LENH ================= */
// Chuoi: "pan,tilt,pump,burst_ms"
void handleCommand(char *line) {
  // Tach 4 truong bang dau phay
  char *p1 = strtok(line, ",");
  char *p2 = strtok(NULL, ",");
  char *p3 = strtok(NULL, ",");
  char *p4 = strtok(NULL, ",");
  if (!p1 || !p2 || !p3) return;   // thieu truong -> bo qua

  int pan      = atoi(p1);
  int tilt     = atoi(p2);
  int pump     = atoi(p3);
  long burstMs = p4 ? atol(p4) : 0;

  lastCmdMs = millis();

  // 1) Servo
  applyServos(pan, tilt);

  // 2) Bom
  if (pump == 1) {
    unsigned long ms = (burstMs <= 0) ? 2500UL : (unsigned long)burstMs;
    if (ms > BURST_MAX_MS) ms = BURST_MAX_MS;
    pumpUntilMs = millis() + ms;
    setPump(true);
  } else {
    pumpUntilMs = 0;
    setPump(false);
  }
}

/* ================= SETUP ================= */
void setup() {
  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  setRelay(false);
  setBuzzer(false);

  servoPan.attach(PIN_SERVO_PAN);
  servoTilt.attach(PIN_SERVO_TILT);
  applyServos(PAN_HOME, TILT_HOME);

  Serial.begin(115200);          // USB debug
  espSerial.begin(9600);         // link tu ESP2

  Serial.println(F("[UNO] Turret controller ready."));
  Serial.println(F("Doc lenh tu ESP2 qua D2 (9600). Format: pan,tilt,pump,burst_ms"));
  lastCmdMs = millis();
}

/* ================= LOOP ================= */
void loop() {
  // 1) Doc UART tu ESP2 -> gom thanh dong
  while (espSerial.available()) {
    char c = (char)espSerial.read();
    if (c == '\n' || c == '\r') {
      if (bufLen > 0) {
        buf[bufLen] = '\0';
        handleCommand(buf);
        bufLen = 0;
      }
    } else if (bufLen < sizeof(buf) - 1) {
      buf[bufLen++] = c;
    } else {
      bufLen = 0;  // overflow -> reset buffer
    }
  }

  // 2) Tu tat bom khi het burst
  if (pumpUntilMs != 0 && millis() >= pumpUntilMs) {
    pumpUntilMs = 0;
    setPump(false);
    Serial.println(F("[PUMP] Burst xong -> OFF"));
  }

  // 3) An toan: mat lenh qua lau -> tat bom (servo giu nguyen)
  if (pumpOn && (millis() - lastCmdMs > CMD_TIMEOUT_MS)) {
    pumpUntilMs = 0;
    setPump(false);
    Serial.println(F("[SAFETY] Mat lenh ESP2 -> tat bom"));
  }
}
