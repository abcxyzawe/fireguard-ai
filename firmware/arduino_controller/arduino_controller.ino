/*
 * ARDUINO CONTROLLER - Nhan lenh tu Server qua Serial
 * Dieu khien 2 Servo (Pan/Tilt) + Relay bom nuoc + Buzzer
 *
 * Giao thuc Serial (9600 baud):
 *   SERVO:90,90    -> Xoay servo pan=90, tilt=90
 *   BEEP           -> Bat buzzer
 *   STOP           -> Tat buzzer
 *   PUMP:ON        -> Bat relay bom nuoc
 *   PUMP:OFF       -> Tat relay bom nuoc
 *   CENTER         -> Servo ve vi tri trung tam
 *
 * Ket noi phan cung:
 *   Servo Pan  (ngang): Pin 9
 *   Servo Tilt (doc):   Pin 10
 *   Relay bom nuoc:     Pin 7
 *   Buzzer:              Pin 8
 */

#include <Servo.h>

/* ================= PIN CONFIG ================= */
#define SERVO_PAN_PIN   9     // Servo ngang
#define SERVO_TILT_PIN  10    // Servo doc
#define RELAY_PIN       7     // Relay bom nuoc
#define BUZZER_PIN      8     // Buzzer canh bao

/* ================= SERVO LIMITS ================= */
#define PAN_MIN     0
#define PAN_MAX     180
#define PAN_CENTER  90
#define TILT_MIN    30
#define TILT_MAX    150
#define TILT_CENTER 90

/* ================= GLOBALS ================= */
Servo servoPan;
Servo servoTilt;

int currentPan = PAN_CENTER;
int currentTilt = TILT_CENTER;
bool pumpOn = false;
bool buzzerOn = false;

String inputBuffer = "";

/* ================= SETUP ================= */
void setup() {
  Serial.begin(9600);

  // Servo
  servoPan.attach(SERVO_PAN_PIN);
  servoTilt.attach(SERVO_TILT_PIN);
  servoPan.write(PAN_CENTER);
  servoTilt.write(TILT_CENTER);

  // Relay
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  // Buzzer
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  Serial.println("[ARDUINO] Ready - Fire Controller v1.0");
  Serial.println("[ARDUINO] Waiting for commands...");
}

/* ================= SMOOTH SERVO MOVE ================= */
void smoothMove(int targetPan, int targetTilt) {
  // Gioi han
  targetPan = constrain(targetPan, PAN_MIN, PAN_MAX);
  targetTilt = constrain(targetTilt, TILT_MIN, TILT_MAX);

  // Di chuyen muot tung buoc
  while (currentPan != targetPan || currentTilt != targetTilt) {
    if (currentPan < targetPan) currentPan++;
    else if (currentPan > targetPan) currentPan--;

    if (currentTilt < targetTilt) currentTilt++;
    else if (currentTilt > targetTilt) currentTilt--;

    servoPan.write(currentPan);
    servoTilt.write(currentTilt);
    delay(3);  // Toc do di chuyen
  }

  Serial.print("[SERVO] pan=");
  Serial.print(currentPan);
  Serial.print(" tilt=");
  Serial.println(currentTilt);
}

/* ================= PARSE COMMAND ================= */
void processCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  // SERVO:pan,tilt
  if (cmd.startsWith("SERVO:")) {
    String params = cmd.substring(6);
    int comma = params.indexOf(',');
    if (comma > 0) {
      int pan = params.substring(0, comma).toInt();
      int tilt = params.substring(comma + 1).toInt();
      smoothMove(pan, tilt);

      // Tu dong bat bom khi servo xoay vao lua
      if (!pumpOn) {
        digitalWrite(RELAY_PIN, HIGH);
        pumpOn = true;
        Serial.println("[PUMP] ON - AUTO");
      }
    }
  }
  // BEEP
  else if (cmd == "BEEP") {
    digitalWrite(BUZZER_PIN, HIGH);
    buzzerOn = true;
    Serial.println("[BUZZER] ON");
  }
  // STOP
  else if (cmd == "STOP") {
    digitalWrite(BUZZER_PIN, LOW);
    buzzerOn = false;
    Serial.println("[BUZZER] OFF");

    // Tat bom khi het lua
    if (pumpOn) {
      delay(2000);  // Giu bom them 2s
      digitalWrite(RELAY_PIN, LOW);
      pumpOn = false;
      Serial.println("[PUMP] OFF");

      // Servo ve trung tam
      smoothMove(PAN_CENTER, TILT_CENTER);
    }
  }
  // PUMP:ON / PUMP:OFF
  else if (cmd == "PUMP:ON") {
    digitalWrite(RELAY_PIN, HIGH);
    pumpOn = true;
    Serial.println("[PUMP] ON");
  }
  else if (cmd == "PUMP:OFF") {
    digitalWrite(RELAY_PIN, LOW);
    pumpOn = false;
    Serial.println("[PUMP] OFF");
  }
  // CENTER
  else if (cmd == "CENTER") {
    smoothMove(PAN_CENTER, TILT_CENTER);
    Serial.println("[SERVO] Centered");
  }
  else {
    Serial.print("[CMD] Unknown: ");
    Serial.println(cmd);
  }
}

/* ================= LOOP ================= */
void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      processCommand(inputBuffer);
      inputBuffer = "";
    } else if (c != '\r') {
      inputBuffer += c;
    }
  }
}
