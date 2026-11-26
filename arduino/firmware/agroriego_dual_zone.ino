/*
 * AgroRiego AI — Firmware Arduino Uno R3 (Dos Zonas Independientes)
 * Curso: Arquitectura y Organización de Computadores (UIA)
 *
 * Descripción:
 *   Controlador embebido de riego de precisión de dos zonas independientes con
 *   Sensores de Humedad de Suelo SparkFun (Tinkercad) en modo 100% comandado por IA:
 *   - Zona 1: Sensor de humedad SparkFun en A0, Etapa de potencia bomba en D8,
 *             LED bomba activa en D4, LED alerta/fallo en D5.
 *   - Zona 2: Sensor de humedad SparkFun en A1, Etapa de potencia bomba en D9,
 *             LED bomba activa en D6, LED alerta/fallo en D7.
 *   - Modo Estricto IA (MODE_AI por defecto): El Arduino NO enciende ninguna bomba por sí mismo;
 *     reporta telemetría JSON y solo activa o apaga los motores al recibir los comandos de la IA
 *     (Z1:PUMP=1/0, Z2:PUMP=1/0). MODE_AUTO queda disponible vía serial como respaldo local.
 *   - Escala SparkFun: 0 ADC = 5.0% VWC (suelo seco), 800 ADC = 45.0% VWC (saturado).
 *     Fallo de sensor únicamente cuando raw > 1015 (circuito abierto).
 *   - Protección Hardware: Las bombas DC NUNCA se conectan directo a GPIO; se conmutan
 *     mediante transistor NPN (2N2222/TIP120) con resistencia de base de 1 kOhm
 *     y diodo de retorno (flyback) 1N4007 en antiparalelo sobre la carga inductiva.
 *   - Seguridad Firmware: Guardas deterministas de hardware (> 1015), enfriamiento (cooldown)
 *     y corte máximo continuo (90 s) con protocolo serial JSON bidireccional.
 */

// ======================= CONFIGURACIÓN DE PINES =======================
const int PIN_SENSOR_Z1 = A0;
const int PIN_SENSOR_Z2 = A1;

const int PIN_PUMP_Z1   = 8;   // Hacia base de transistor Q1 (1k Ohm)
const int PIN_PUMP_Z2   = 9;   // Hacia base de transistor Q2 (1k Ohm)

const int PIN_LED_PUMP_Z1  = 4;
const int PIN_LED_FAULT_Z1 = 5;
const int PIN_LED_PUMP_Z2  = 6;
const int PIN_LED_FAULT_Z2 = 7;
const int PIN_HEARTBEAT    = 13;

// ======================= PARÁMETROS DE SEGURIDAD ======================
const int RAW_FAULT_LOW  = -1;     // Con sensor de humedad SparkFun, 0 es suelo 100% seco (válido)
const int RAW_FAULT_HIGH = 1015;   // Sensor desconectado / circuito abierto

// Calibración para Sensor de Humedad de Suelo (SparkFun Soil Moisture en Tinkercad)
// En Tinkercad: 0 ADC = Suelo Seco (0V) -> 5.0% VWC
//               800 ADC = Suelo Saturado de agua (~4.2V) -> 45.0% VWC
const int ADC_DRY_CAL = 0;         // ~5% VWC suelo muy seco
const int ADC_WET_CAL = 800;       // ~45% VWC saturado/húmedo

const unsigned long SAMPLE_INTERVAL_MS   = 1000;   // Lectura rápida cada 1 s
const unsigned long MIN_COOLDOWN_MS      = 2000;   // Espera mínima demo 2 s
const unsigned long MAX_PUMP_RUNTIME_MS  = 90000;  // Límite continuo de seguridad (demo 90s)

// ======================= MODOS Y ESTRUCTURA ===========================
const int MODE_AUTO    = 0;  // Respaldo autónomo opcional (solo si se envía MODE=AUTO)
const int MODE_AI      = 1;  // Modo estricto 100% comandado por IA (por defecto)
const int MODE_MONITOR = 2;

struct IrrigationZone {
  const char* zoneId;
  int pinSensor;
  int pinPump;
  int pinLedPump;
  int pinLedFault;

  float lowThresholdPct;     // Umbral inferior FAO-56 para encender bomba
  float highThresholdPct;    // Umbral superior para apagar (histéresis)

  int lastRaw;
  float lastMoisturePct;
  bool pumpActive;
  bool sensorFault;
  bool safetyCutoffTriggered;
  int mode;
  bool manualRequestedState;
  bool manualOverrideActive;

  unsigned long pumpStartTimeMs;
  unsigned long lastPumpStopTimeMs;
  unsigned long currentRuntimeMs;
};

IrrigationZone zones[2] = {
  {"zone_01", PIN_SENSOR_Z1, PIN_PUMP_Z1, PIN_LED_PUMP_Z1, PIN_LED_FAULT_Z1, 24.2f, 27.7f, 0, 0.0f, false, false, false, MODE_AI, false, false, 0, 0, 0},
  {"zone_02", PIN_SENSOR_Z2, PIN_PUMP_Z2, PIN_LED_PUMP_Z2, PIN_LED_FAULT_Z2, 24.9f, 27.4f, 0, 0.0f, false, false, false, MODE_AI, false, false, 0, 0, 0}
};

unsigned long lastSampleMs = 0;
unsigned long lastSerialCharMs = 0;
String serialRxBuffer = "";

// Convierte lectura ADC 10-bit en humedad volumétrica interpretable (%)
// Compatible con sensor de humedad SparkFun de Tinkercad (0 = seco, 800 = húmedo)
float calibrateAdcToMoisturePct(int rawAdc) {
  int clamped = constrain(rawAdc, 0, 850);
  float pct = 5.0f + ((float)clamped / 800.0f) * 40.0f;
  return constrain(pct, 0.0f, 100.0f);
}

// Lee el promedio de 5 muestras para filtrar ruido analógico
int readFilteredAdc(int pin) {
  long sum = 0;
  for (int i = 0; i < 5; i++) {
    sum += analogRead(pin);
    delay(2);
  }
  return (int)(sum / 5);
}

// Aplica salidas físicas a pines de bomba y LEDs respetando estado seguro
void applyHardwareOutputs(int zIdx) {
  IrrigationZone& z = zones[zIdx];
  if (z.sensorFault || z.safetyCutoffTriggered) {
    z.pumpActive = false;
  }
  digitalWrite(z.pinPump, z.pumpActive ? HIGH : LOW);
  digitalWrite(z.pinLedPump, z.pumpActive ? HIGH : LOW);
  digitalWrite(z.pinLedFault, (z.sensorFault || z.safetyCutoffTriggered) ? HIGH : LOW);
}

// Evalúa una zona independiente con histéresis, cooldown y límites de seguridad
void evaluateZone(int zIdx, unsigned long nowMs) {
  IrrigationZone& z = zones[zIdx];
  z.lastRaw = readFilteredAdc(z.pinSensor);

  // 1. Verificación de integridad de sensor
  if (z.lastRaw < RAW_FAULT_LOW || z.lastRaw > RAW_FAULT_HIGH) {
    z.sensorFault = true;
    z.lastMoisturePct = -1.0f;
    z.manualRequestedState = false;
    if (z.pumpActive) {
      z.pumpActive = false;
      z.lastPumpStopTimeMs = nowMs;
      z.currentRuntimeMs = 0;
    }
    applyHardwareOutputs(zIdx);
    return;
  } else {
    z.sensorFault = false;
  }

  z.lastMoisturePct = calibrateAdcToMoisturePct(z.lastRaw);

  // Auto-recuperación de safety cutoff si el sensor alcanza humedad óptima (>= highThresholdPct)
  if (z.safetyCutoffTriggered && (z.lastMoisturePct >= z.highThresholdPct)) {
    z.safetyCutoffTriggered = false;
  }

  // 2. Verificación de tiempo máximo de riego continuo (Safety Cutoff)
  if (z.pumpActive) {
    z.currentRuntimeMs = nowMs - z.pumpStartTimeMs;
    if (z.currentRuntimeMs >= MAX_PUMP_RUNTIME_MS) {
      z.pumpActive = false;
      z.safetyCutoffTriggered = true;
      z.manualRequestedState = false;
      z.lastPumpStopTimeMs = nowMs;
      z.currentRuntimeMs = 0;
      applyHardwareOutputs(zIdx);
      return;
    }
  } else {
    z.currentRuntimeMs = 0;
  }

  // 3. Control según modo de operación
  bool cooldownOk = (z.lastPumpStopTimeMs == 0) || ((nowMs - z.lastPumpStopTimeMs) >= MIN_COOLDOWN_MS);

  if (z.mode == MODE_MONITOR) {
    z.manualRequestedState = false;
    if (z.pumpActive) {
      z.pumpActive = false;
      z.lastPumpStopTimeMs = nowMs;
    }
  } else if (z.mode == MODE_AI) {
    // Modo estricto comandado por IA: Arduino NUNCA enciende la bomba solo;
    // únicamente ejecuta las órdenes Zx:PUMP=1 / Zx:PUMP=0 enviadas por la IA.
    if (z.manualRequestedState && !z.pumpActive && cooldownOk && !z.safetyCutoffTriggered) {
      z.pumpActive = true;
      z.pumpStartTimeMs = nowMs;
    } else if (!z.manualRequestedState && z.pumpActive) {
      z.pumpActive = false;
      z.lastPumpStopTimeMs = nowMs;
    }
  } else {
    // Respaldo opcional MODE_AUTO por histéresis local (solo si se solicita por serial)
    if (!z.pumpActive && cooldownOk && !z.safetyCutoffTriggered && (z.lastMoisturePct < z.lowThresholdPct)) {
      z.pumpActive = true;
      z.pumpStartTimeMs = nowMs;
    } else if (z.pumpActive && (z.lastMoisturePct >= z.highThresholdPct)) {
      z.pumpActive = false;
      z.lastPumpStopTimeMs = nowMs;
    }
  }

  applyHardwareOutputs(zIdx);
}

// Emite trama JSON estructurada hacia el Backend / Monitor Serial
void publishZoneTelemetry(int zIdx, unsigned long nowMs) {
  const IrrigationZone& z = zones[zIdx];
  bool cooldownActive = (!z.pumpActive && z.lastPumpStopTimeMs > 0 && (nowMs - z.lastPumpStopTimeMs) < MIN_COOLDOWN_MS);
  const char* modeStr = (z.mode == MODE_AUTO) ? "AUTO" : ((z.mode == MODE_AI) ? "AI" : "MONITOR");

  Serial.print("{\"timestamp_ms\":");
  Serial.print(nowMs);
  Serial.print(",\"zone\":\"");
  Serial.print(z.zoneId);
  Serial.print("\",\"raw\":");
  Serial.print(z.lastRaw);
  Serial.print(",\"moisture_pct\":");
  Serial.print(z.lastMoisturePct, 2);
  Serial.print(",\"pump\":");
  Serial.print(z.pumpActive ? "true" : "false");
  Serial.print(",\"fault\":");
  Serial.print(z.sensorFault ? "true" : "false");
  Serial.print(",\"safety_cutoff\":");
  Serial.print(z.safetyCutoffTriggered ? "true" : "false");
  Serial.print(",\"cooldown_active\":");
  Serial.print(cooldownActive ? "true" : "false");
  Serial.print(",\"runtime_ms\":");
  Serial.print(z.currentRuntimeMs);
  Serial.print(",\"mode\":\"");
  Serial.print(modeStr);
  Serial.println("\"}");
}

// Procesa comandos entrantes del Backend (ej: Z1:PUMP=1, Z1:MODE=AUTO, Z1:THRESH=24.2,27.7)
void processSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.length() < 4) return;

  int idx = -1;
  if (cmd.startsWith("Z1:")) idx = 0;
  else if (cmd.startsWith("Z2:")) idx = 1;
  else return;

  IrrigationZone& z = zones[idx];
  String body = cmd.substring(3);

  if (body == "PUMP=1") {
    z.mode = MODE_AI;
    z.manualRequestedState = true;
    z.manualOverrideActive = true;
  } else if (body == "PUMP=0") {
    z.mode = MODE_AI;
    z.manualRequestedState = false;
    z.manualOverrideActive = true;
  } else if (body == "MODE=AI") {
    z.mode = MODE_AI;
    z.manualOverrideActive = false;
  } else if (body == "MODE=AUTO" || body == "AUTO") {
    z.mode = MODE_AUTO;
    z.manualOverrideActive = false;
    z.manualRequestedState = false;
  } else if (body == "MODE=MONITOR") {
    z.mode = MODE_MONITOR;
    z.manualRequestedState = false;
    z.manualOverrideActive = true;
  } else if (body == "RESET_FAULT") {
    z.safetyCutoffTriggered = false;
    z.sensorFault = false;
  } else if (body.startsWith("THRESH=")) {
    String vals = body.substring(7);
    int comma = vals.indexOf(',');
    if (comma > 0) {
      float low = vals.substring(0, comma).toFloat();
      float high = vals.substring(comma + 1).toFloat();
      if (low > 5.0f && high > low && high < 95.0f) {
        z.lowThresholdPct = low;
        z.highThresholdPct = high;
      }
    }
  }

  unsigned long nowMs = millis();
  evaluateZone(idx, nowMs);
  publishZoneTelemetry(idx, nowMs);
}

void setup() {
  Serial.begin(9600);
  pinMode(PIN_PUMP_Z1, OUTPUT);
  pinMode(PIN_PUMP_Z2, OUTPUT);
  pinMode(PIN_LED_PUMP_Z1, OUTPUT);
  pinMode(PIN_LED_FAULT_Z1, OUTPUT);
  pinMode(PIN_LED_PUMP_Z2, OUTPUT);
  pinMode(PIN_LED_FAULT_Z2, OUTPUT);
  pinMode(PIN_HEARTBEAT, OUTPUT);

  digitalWrite(PIN_PUMP_Z1, LOW);
  digitalWrite(PIN_PUMP_Z2, LOW);
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r' || c == ';') {
      if (serialRxBuffer.length() > 0) {
        processSerialCommand(serialRxBuffer);
        serialRxBuffer = "";
      }
    } else {
      serialRxBuffer += c;
      lastSerialCharMs = millis();
    }
  }

  unsigned long nowMs = millis();
  if (serialRxBuffer.length() > 0 && (nowMs - lastSerialCharMs) >= 120) {
    processSerialCommand(serialRxBuffer);
    serialRxBuffer = "";
  }

  if (nowMs - lastSampleMs >= SAMPLE_INTERVAL_MS) {
    lastSampleMs = nowMs;
    digitalWrite(PIN_HEARTBEAT, !digitalRead(PIN_HEARTBEAT));

    for (int i = 0; i < 2; i++) {
      evaluateZone(i, nowMs);
      publishZoneTelemetry(i, nowMs);
    }
  }
}
