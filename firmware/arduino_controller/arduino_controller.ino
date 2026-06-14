/* ============================================================================
 * FireGuard - ARDUINO UNO (Turret Controller)
 *
 * Nhan lenh tu ESP32-CAM 2 qua UART (SoftwareSerial), dieu khien:
 *   - Servo PAN  (SG90S) + Servo TILT (SG90), quay tu tu (muot)
 *   - Relay may bom nuoc 24V
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
 *   D9  -> Servo PAN  (SG90S - truc ngang, quay trai/phai)
 *   D10 -> Servo TILT (SG90  - truc doc,  ngua len/cui xuong)
 *   D7  -> Relay (may bom 24V). HIGH = bom chay
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
#define PIN_SERVO_PAN    9     // SG90S - truc ngang (pan, quay trai/phai)
#define PIN_SERVO_TILT   10    // SG90  - truc doc  (tilt, ngua/cui)
#define PIN_RELAY        7     // Relay - may bom
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

/* ================= SERVO MUOT (smooth) ================= */
#define SERVO_STEP_MS     15       // 15ms / 1 do  -> ~66 do/giay (muot, khong giat)

/* ================= STATE ================= */
SoftwareSerial espSerial(PIN_RX_FROM_ESP, PIN_TX_DUMMY);
Servo servoPan;
Servo servoTilt;

int  curPan     = PAN_HOME;   // goc dang xuat ra servo
int  curTilt    = TILT_HOME;
int  targetPan  = PAN_HOME;   // goc muc tieu (servo tu tu tien toi)
int  targetTilt = TILT_HOME;
unsigned long lastServoStep = 0;

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

// Dat goc muc tieu - servo se tu tu tien toi trong loop (khong giat)
void setServoTargets(int pan, int tilt) {
  targetPan  = clampInt(pan,  PAN_MIN,  PAN_MAX);
  targetTilt = clampInt(tilt, TILT_MIN, TILT_MAX);
}

// Goi lien tuc trong loop: moi SERVO_STEP_MS dich 1 do ve phia target
void updateServosSmooth() {
  if (millis() - lastServoStep < SERVO_STEP_MS) return;
  lastServoStep = millis();
  if      (curPan  < targetPan)  { curPan++;  servoPan.write(curPan); }
  else if (curPan  > targetPan)  { curPan--;  servoPan.write(curPan); }
  if      (curTilt < targetTilt) { curTilt++; servoTilt.write(curTilt); }
  else if (curTilt > targetTilt) { curTilt--; servoTilt.write(curTilt); }
}

// Luc khoi dong: quay TU TU ve trung tam (blocking, chi 1 lan trong setup)
void smoothHomeStartup() {
  // Pan ve giua luon (servo attach mac dinh da ~giua nen khong giat manh).
  // Tilt bat dau chuc thap roi TU TU nang len trung tam -> muot + an toan.
  curPan  = PAN_HOME;
  curTilt = TILT_MIN;
  servoPan.write(curPan);
  servoTilt.write(curTilt);
  delay(500);                       // cho servo on dinh o diem bat dau
  while (curTilt < TILT_HOME) {     // tu tu nang len giua
    curTilt++;
    servoTilt.write(curTilt);
    delay(SERVO_STEP_MS);
  }
  targetPan  = PAN_HOME;
  targetTilt = TILT_HOME;
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

  // 1) Servo - dat muc tieu, loop se dich tu tu (muot)
  setServoTargets(pan, tilt);

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
  smoothHomeStartup();           // quay TU TU ve trung tam khi cap dien

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

  // 2) Dich servo tu tu ve muc tieu (muot, khong giat)
  updateServosSmooth();

  // 3) Tu tat bom khi het burst
  if (pumpUntilMs != 0 && millis() >= pumpUntilMs) {
    pumpUntilMs = 0;
    setPump(false);
    Serial.println(F("[PUMP] Burst xong -> OFF"));
  }

  // 4) An toan: mat lenh qua lau -> tat bom (servo giu nguyen)
  if (pumpOn && (millis() - lastCmdMs > CMD_TIMEOUT_MS)) {
    pumpUntilMs = 0;
    setPump(false);
    Serial.println(F("[SAFETY] Mat lenh ESP2 -> tat bom"));
  }
}
