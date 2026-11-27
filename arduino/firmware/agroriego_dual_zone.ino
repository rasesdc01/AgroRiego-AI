/*
 * AgroRiego - Proyecto Arquitectura y Organizacion de Computadores
 * Control de riego para 2 zonas independientes con Arduino Uno
 */

// Pines de conexion
const int PIN_SENSOR_Z1 = A0;
const int PIN_SENSOR_Z2 = A1;

const int PIN_BOMBA_Z1 = 8;
const int PIN_BOMBA_Z2 = 9;

const int PIN_LED_BOMBA_Z1 = 4;
const int PIN_LED_FALLA_Z1 = 5;
const int PIN_LED_BOMBA_Z2 = 6;
const int PIN_LED_FALLA_Z2 = 7;
const int PIN_HEARTBEAT = 13;

// Constantes de seguridad y calibracion del sensor
const int SENSOR_DESCONECTADO = 1015; // si pasa de esto el sensor esta en circuito abierto
const unsigned long INTERVALO_LECTURA = 1000;  // cada 1 seg
const unsigned long TIEMPO_COOLDOWN = 2000;    // espera minima entre riegos (2s para pruebas)
const unsigned long TIEMPO_MAX_RIEGO = 90000;  // maximo 90s continuos de bomba

// Modos de trabajo
const int MODO_AUTO = 0;
const int MODO_AI = 1;      // por defecto controlado desde la IA
const int MODO_MONITOR = 2;

// Estructura para agrupar los datos de cada zona
struct Zona {
  char id[8];
  int pinSensor;
  int pinBomba;
  int pinLedBomba;
  int pinLedFalla;

  float umbralBajo;
  float umbralAlto;

  int valorRaw;
  float humedad;
  bool bombaPrendida;
  bool errorSensor;
  bool corteSeguridad;
  int modo;
  bool ordenBombaManual;

  unsigned long inicioRiego;
  unsigned long finRiego;
  unsigned long tiempoRiegoActual;
};

// Inicializamos las dos zonas (valores por defecto)
Zona zonas[2] = {
  {"zone_01", PIN_SENSOR_Z1, PIN_BOMBA_Z1, PIN_LED_BOMBA_Z1, PIN_LED_FALLA_Z1, 24.2, 27.7, 0, 0.0, false, false, false, MODO_AI, false, 0, 0, 0},
  {"zone_02", PIN_SENSOR_Z2, PIN_BOMBA_Z2, PIN_LED_BOMBA_Z2, PIN_LED_FALLA_Z2, 24.9, 27.4, 0, 0.0, false, false, false, MODO_AI, false, 0, 0, 0}
};

unsigned long tiempoUltimaLectura = 0;
unsigned long tiempoUltimoCaracter = 0;
String bufferSerial = "";

// Conversion del ADC a porcentaje aproximado de humedad
float calcularHumedad(int raw) {
  int valor = constrain(raw, 0, 850);
  float porcentaje = 5.0 + ((float)valor / 800.0) * 40.0;
  return constrain(porcentaje, 0.0, 100.0);
}

// Promedio de 5 lecturas para que no baile tanto el valor
int leerSensorPromedio(int pin) {
  long suma = 0;
  for (int i = 0; i < 5; i++) {
    suma += analogRead(pin);
    delay(2);
  }
  return suma / 5;
}

// Actualiza los pines fisicos (reles/transistores y leds)
void actualizarSalidas(int i) {
  // si hay algun error la bomba no puede estar encendida
  if (zonas[i].errorSensor || zonas[i].corteSeguridad) {
    zonas[i].bombaPrendida = false;
  }
  digitalWrite(zonas[i].pinBomba, zonas[i].bombaPrendida ? HIGH : LOW);
  digitalWrite(zonas[i].pinLedBomba, zonas[i].bombaPrendida ? HIGH : LOW);
  digitalWrite(zonas[i].pinLedFalla, (zonas[i].errorSensor || zonas[i].corteSeguridad) ? HIGH : LOW);
}

// Logica de control de cada zona
void revisarZona(int i, unsigned long ahora) {
  zonas[i].valorRaw = leerSensorPromedio(zonas[i].pinSensor);

  // 1. Ver si el sensor esta fallando o desconectado
  if (zonas[i].valorRaw > SENSOR_DESCONECTADO) {
    zonas[i].errorSensor = true;
    zonas[i].humedad = -1.0;
    zonas[i].ordenBombaManual = false;
    if (zonas[i].bombaPrendida) {
      zonas[i].bombaPrendida = false;
      zonas[i].finRiego = ahora;
      zonas[i].tiempoRiegoActual = 0;
    }
    actualizarSalidas(i);
    return;
  } else {
    zonas[i].errorSensor = false;
  }

  zonas[i].humedad = calcularHumedad(zonas[i].valorRaw);

  // Si la humedad ya subio al nivel optimo, quitamos la alerta de seguridad
  if (zonas[i].corteSeguridad && (zonas[i].humedad >= zonas[i].umbralAlto)) {
    zonas[i].corteSeguridad = false;
  }

  // 2. Proteccion por tiempo maximo de bomba encendida
  if (zonas[i].bombaPrendida) {
    zonas[i].tiempoRiegoActual = ahora - zonas[i].inicioRiego;
    if (zonas[i].tiempoRiegoActual >= TIEMPO_MAX_RIEGO) {
      zonas[i].bombaPrendida = false;
      zonas[i].corteSeguridad = true;
      zonas[i].ordenBombaManual = false;
      zonas[i].finRiego = ahora;
      zonas[i].tiempoRiegoActual = 0;
      actualizarSalidas(i);
      return;
    }
  } else {
    zonas[i].tiempoRiegoActual = 0;
  }

  // 3. Control segun el modo seleccionado
  bool descansoOk = (zonas[i].finRiego == 0) || ((ahora - zonas[i].finRiego) >= TIEMPO_COOLDOWN);

  if (zonas[i].modo == MODO_MONITOR) {
    zonas[i].ordenBombaManual = false;
    if (zonas[i].bombaPrendida) {
      zonas[i].bombaPrendida = false;
      zonas[i].finRiego = ahora;
    }
  } 
  else if (zonas[i].modo == MODO_AI) {
    // Modo IA: la bomba solo se mueve si la IA manda el comando
    if (zonas[i].ordenBombaManual && !zonas[i].bombaPrendida && descansoOk && !zonas[i].corteSeguridad) {
      zonas[i].bombaPrendida = true;
      zonas[i].inicioRiego = ahora;
    } else if (!zonas[i].ordenBombaManual && zonas[i].bombaPrendida) {
      zonas[i].bombaPrendida = false;
      zonas[i].finRiego = ahora;
    }
  } 
  else {
    // Modo AUTO: control local con umbrales por histeresis
    if (!zonas[i].bombaPrendida && descansoOk && !zonas[i].corteSeguridad && (zonas[i].humedad < zonas[i].umbralBajo)) {
      zonas[i].bombaPrendida = true;
      zonas[i].inicioRiego = ahora;
    } else if (zonas[i].bombaPrendida && (zonas[i].humedad >= zonas[i].umbralAlto)) {
      zonas[i].bombaPrendida = false;
      zonas[i].finRiego = ahora;
    }
  }

  actualizarSalidas(i);
}

// Imprime por serial el JSON que espera el backend de Python
void enviarTelemetria(int i, unsigned long ahora) {
  bool descansoActivo = (!zonas[i].bombaPrendida && zonas[i].finRiego > 0 && (ahora - zonas[i].finRiego) < TIEMPO_COOLDOWN);
  
  String nombreModo = "AI";
  if (zonas[i].modo == MODO_AUTO) nombreModo = "AUTO";
  else if (zonas[i].modo == MODO_MONITOR) nombreModo = "MONITOR";

  Serial.print("{\"timestamp_ms\":");
  Serial.print(ahora);
  Serial.print(",\"zone\":\"");
  Serial.print(zonas[i].id);
  Serial.print("\",\"raw\":");
  Serial.print(zonas[i].valorRaw);
  Serial.print(",\"moisture_pct\":");
  Serial.print(zonas[i].humedad, 2);
  Serial.print(",\"pump\":");
  Serial.print(zonas[i].bombaPrendida ? "true" : "false");
  Serial.print(",\"fault\":");
  Serial.print(zonas[i].errorSensor ? "true" : "false");
  Serial.print(",\"safety_cutoff\":");
  Serial.print(zonas[i].corteSeguridad ? "true" : "false");
  Serial.print(",\"cooldown_active\":");
  Serial.print(descansoActivo ? "true" : "false");
  Serial.print(",\"runtime_ms\":");
  Serial.print(zonas[i].tiempoRiegoActual);
  Serial.print(",\"mode\":\"");
  Serial.print(nombreModo);
  Serial.println("\"}");
}

// Interpreta los comandos enviados por la app / backend
void procesarComando(String cmd) {
  cmd.trim();
  if (cmd.length() < 4) return;

  int idx = -1;
  if (cmd.startsWith("Z1:")) idx = 0;
  else if (cmd.startsWith("Z2:")) idx = 1;
  else return;

  String accion = cmd.substring(3);

  if (accion == "PUMP=1") {
    zonas[idx].modo = MODO_AI;
    zonas[idx].ordenBombaManual = true;
  } else if (accion == "PUMP=0") {
    zonas[idx].modo = MODO_AI;
    zonas[idx].ordenBombaManual = false;
  } else if (accion == "MODE=AI") {
    zonas[idx].modo = MODO_AI;
  } else if (accion == "MODE=AUTO" || accion == "AUTO") {
    zonas[idx].modo = MODO_AUTO;
    zonas[idx].ordenBombaManual = false;
  } else if (accion == "MODE=MONITOR") {
    zonas[idx].modo = MODO_MONITOR;
    zonas[idx].ordenBombaManual = false;
  } else if (accion == "RESET_FAULT") {
    zonas[idx].corteSeguridad = false;
    zonas[idx].errorSensor = false;
  } else if (accion.startsWith("THRESH=")) {
    String valores = accion.substring(7);
    int coma = valores.indexOf(',');
    if (coma > 0) {
      float bajo = valores.substring(0, coma).toFloat();
      float alto = valores.substring(coma + 1).toFloat();
      if (bajo > 5.0 && alto > bajo && alto < 95.0) {
        zonas[idx].umbralBajo = bajo;
        zonas[idx].umbralAlto = alto;
      }
    }
  }

  unsigned long ahora = millis();
  revisarZona(idx, ahora);
  enviarTelemetria(idx, ahora);
}

void setup() {
  Serial.begin(9600);

  pinMode(PIN_BOMBA_Z1, OUTPUT);
  pinMode(PIN_BOMBA_Z2, OUTPUT);
  pinMode(PIN_LED_BOMBA_Z1, OUTPUT);
  pinMode(PIN_LED_FALLA_Z1, OUTPUT);
  pinMode(PIN_LED_BOMBA_Z2, OUTPUT);
  pinMode(PIN_LED_FALLA_Z2, OUTPUT);
  pinMode(PIN_HEARTBEAT, OUTPUT);

  // Iniciar bombas apagadas
  digitalWrite(PIN_BOMBA_Z1, LOW);
  digitalWrite(PIN_BOMBA_Z2, LOW);
}

void loop() {
  // Leer caracteres del puerto serial
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r' || c == ';') {
      if (bufferSerial.length() > 0) {
        procesarComando(bufferSerial);
        bufferSerial = "";
      }
    } else {
      bufferSerial += c;
      tiempoUltimoCaracter = millis();
    }
  }

  unsigned long ahora = millis();

  // Por si llego un comando sin enter/salto de linea
  if (bufferSerial.length() > 0 && (ahora - tiempoUltimoCaracter) >= 120) {
    procesarComando(bufferSerial);
    bufferSerial = "";
  }

  // Tarea periodica de medicion y envio de datos
  if (ahora - tiempoUltimaLectura >= INTERVALO_LECTURA) {
    tiempoUltimaLectura = ahora;
    
    // Parpadeo del led testigo (heartbeat)
    digitalWrite(PIN_HEARTBEAT, !digitalRead(PIN_HEARTBEAT));

    for (int i = 0; i < 2; i++) {
      revisarZona(i, ahora);
      enviarTelemetria(i, ahora);
    }
  }
}
