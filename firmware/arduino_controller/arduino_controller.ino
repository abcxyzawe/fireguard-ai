/* ============================================================================
 * FireGuard - ARDUINO UNO (Relay Controller)
 *
 * Nhận tín hiệu HIGH/LOW từ ESP32-CAM 2 qua 1 chân digital.
 * - HIGH -> đóng relay -> máy bơm chạy
 * - LOW  -> mở relay  -> máy bơm tắt
 *
 * Có buzzer cảnh báo: kêu khi pump ON.
 * Có debounce nhỏ để chống nhiễu cạnh.
 *
 * Pin map:
 *   D7  <- INPUT  từ ESP32-CAM2 GPIO13 (pump trigger)
 *   D8  -> OUTPUT relay control (active HIGH; nếu module relay active LOW thì đảo ở RELAY_ACTIVE_HIGH)
 *   D9  -> OUTPUT buzzer
 *   GND chung với ESP32-CAM2 GND  *** BẮT BUỘC ***
 * ========================================================================== */

#define PIN_PUMP_IN    7    // Digital input from ESP32-CAM 2
#define PIN_RELAY      8    // Digital output to relay coil
#define PIN_BUZZER     9    // Optional buzzer

#define RELAY_ACTIVE_HIGH true   // false nếu module relay là active-LOW

#define DEBOUNCE_MS    30
#define BUZZER_HZ      2200      // tần số bíp khi pump ON

unsigned long lastChangeMs = 0;
int  lastReading  = LOW;
int  stableState  = LOW;
bool pumpOn       = false;

void setRelay(bool on) {
  if (RELAY_ACTIVE_HIGH) digitalWrite(PIN_RELAY, on ? HIGH : LOW);
  else                   digitalWrite(PIN_RELAY, on ? LOW  : HIGH);
}

void setBuzzer(bool on) {
  if (on) tone(PIN_BUZZER, BUZZER_HZ);
  else    noTone(PIN_BUZZER);
}

void setup() {
  pinMode(PIN_PUMP_IN, INPUT_PULLDOWN);  // (UNO: dùng INPUT thường, ESP2 drive HIGH/LOW rõ ràng)
  // Note: UNO không có INPUT_PULLDOWN sẵn — dùng resistor 10kΩ kéo xuống GND, hoặc đổi:
  pinMode(PIN_PUMP_IN, INPUT);

  pinMode(PIN_RELAY, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);

  setRelay(false);
  setBuzzer(false);

  Serial.begin(9600);
  Serial.println(F("[ARDUINO] Relay controller ready."));
  Serial.println(F("Reading PIN 7 from ESP32-CAM2 GPIO13."));
}

void loop() {
  int reading = digitalRead(PIN_PUMP_IN);

  // Debounce
  if (reading != lastReading) {
    lastChangeMs = millis();
    lastReading  = reading;
  }

  if (millis() - lastChangeMs > DEBOUNCE_MS && reading != stableState) {
    stableState = reading;
    bool wantPump = (stableState == HIGH);
    if (wantPump != pumpOn) {
      pumpOn = wantPump;
      setRelay(pumpOn);
      setBuzzer(pumpOn);
      Serial.print(F("[PUMP] "));
      Serial.println(pumpOn ? F("ON  (relay closed - bom chay)") : F("OFF (relay opened - bom tat)"));
    }
  }
}
