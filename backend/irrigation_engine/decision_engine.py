"""
AgroRiego AI — Hybrid 3-Layer Irrigation Decision & Safety Engine
Layer 1: Real Trained scikit-learn Models (Calibration + 1h/6h/12h/24h Residual Forecast)
Layer 2: FAO-56 Agronomic Engine (including specialized Rice flood_paddy logic)
Layer 3: Deterministic Control & Safety Guardrails (Fault, Hysteresis, Cooldown, Max Runtime)
"""

import json
import math
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple
import joblib
import numpy as np
import pandas as pd

from backend.database.db import db_session

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS_DIR = os.path.join(ROOT, "ai", "models")

_MODEL_CACHE: Dict[str, Any] = {}


def load_models() -> Dict[str, Any]:
    if not _MODEL_CACHE:
        for key, fname in [
            ("cal", "model1_calibration.joblib"),
            ("1h", "model2_forecast_1h.joblib"),
            ("6h", "model2_forecast_6h.joblib"),
            ("12h", "model2_forecast_12h.joblib"),
            ("24h", "model2_forecast_24h.joblib"),
            ("cls", "model3_recommendation_clf.joblib"),
        ]:
            path = os.path.join(MODELS_DIR, fname)
            if os.path.exists(path):
                _MODEL_CACHE[key] = joblib.load(path)
    return _MODEL_CACHE


def sparkfun_adc_to_vwc(raw_adc: int) -> float:
    """Direct SparkFun Soil Moisture calibration matching Arduino firmware (0=5.0%, 800=45.0%)."""
    clamped = max(0, min(850, int(raw_adc)))
    return round(5.0 + (clamped / 800.0) * 40.0, 2)


def vwc_to_sparkfun_adc(vwc_pct: float) -> int:
    """Inverse SparkFun Soil Moisture mapping from % VWC to 10-bit ADC (0..850)."""
    return int(round(max(0.0, min(850.0, ((float(vwc_pct) - 5.0) / 40.0) * 800.0))))


def sparkfun_adc_to_hw390_equiv(raw_adc: int) -> int:
    """Domain adapter mapping SparkFun direct ADC (0 dry .. 850 wet) to EcoIrrigate HW-390 ADC (860 dry .. 450 wet)."""
    clamped = max(0, min(850, int(raw_adc)))
    return int(round(860.0 - (clamped / 850.0) * (860.0 - 450.0)))


def calibrate_hw390_adc(
    raw_adc: int,
    board_temp_c: float = 25.0,
    soil_temp_c: float = 24.5,
    air_temp_c: float = 26.0,
    sensor_voltage_v: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Returns (model1_ecoirrigate_vwc_pct, agronomic_scaled_vwc_pct).
    - model1_ecoirrigate_vwc_pct: Inference from real Model 1 trained on EcoIrrigate via HW-390 domain adapter.
    - agronomic_scaled_vwc_pct: Direct SparkFun Soil Moisture calibration (0 dry -> 5.0%, 800 wet -> 45.0%).
    """
    models = load_models()
    now = datetime.now()
    hour_rad = 2.0 * math.pi * (now.hour + now.minute / 60.0) / 24.0
    hw390_adc = sparkfun_adc_to_hw390_equiv(raw_adc)
    v_supply = sensor_voltage_v if sensor_voltage_v is not None else round(max(1.2, min(3.3, (hw390_adc / 1023.0) * 3.3)), 3)

    cal_bundle = models.get("cal")
    ecoirr_vwc = 12.0
    if cal_bundle is not None:
        X_cal = pd.DataFrame([{
            "Raw_Capacitive_ADC": float(np.clip(hw390_adc, 450, 860)),
            "Sensor_Board_Temperature_C": float(board_temp_c),
            "Sensor_Voltage_V": float(v_supply),
            "Soil_Temperature_C": float(soil_temp_c),
            "Atm_Temperature_C": float(air_temp_c),
            "Hour_sin": math.sin(hour_rad),
            "Hour_cos": math.cos(hour_rad),
        }])[cal_bundle["features"]]
        ecoirr_vwc = float(cal_bundle["model"].predict(X_cal)[0])

    scaled_vwc = sparkfun_adc_to_vwc(raw_adc)
    return round(ecoirr_vwc, 2), scaled_vwc


def forecast_moisture_horizons(
    current_vwc_pct: float,
    raw_adc: int,
    air_temp_c: float,
    soil_temp_c: float,
    rh_pct: Optional[float],
    pressure_inhg: float,
    etc_mm_day: float,
    recent_vwc_history: Optional[list] = None,
    simulated_rain_mm: float = 0.0,
) -> Dict[str, Any]:
    """
    Runs real Model 2 residual delta models (1h, 6h, 12h, 24h) and combines
    with agronomic ETc water-balance drift when operating outside EcoIrrigate's sandy-loam range.
    """
    models = load_models()
    now = datetime.now()
    hour_rad = 2.0 * math.pi * (now.hour + now.minute / 60.0) / 24.0

    hist = recent_vwc_history or [current_vwc_pct]
    lag_15m = hist[-2] if len(hist) >= 2 else current_vwc_pct
    lag_1h = hist[-4] if len(hist) >= 4 else current_vwc_pct
    lag_4h = hist[-16] if len(hist) >= 16 else lag_1h
    lag_6h = hist[-24] if len(hist) >= 24 else lag_4h
    lag_12h = hist[0] if len(hist) >= 48 else lag_6h
    lag_24h = hist[0] if len(hist) >= 96 else lag_12h
    roll_mean_4h = float(np.mean(hist[-16:])) if hist else current_vwc_pct
    roll_std_4h = float(np.std(hist[-16:])) if len(hist) > 1 else 0.05
    roll_mean_24h = float(np.mean(hist[-96:])) if hist else current_vwc_pct

    eff_sparkfun_adc = raw_adc if raw_adc is not None else 450
    hw390_adc = sparkfun_adc_to_hw390_equiv(eff_sparkfun_adc)

    # Build feature vector matching Model 2 training schema
    row_dict = {
        "Volumetric_Moisture_Pct": float(current_vwc_pct),
        "Raw_Capacitive_ADC": float(hw390_adc),
        "Sensor_Board_Temperature_C": float(soil_temp_c + 0.5),
        "Sensor_Voltage_V": float(round(max(1.2, min(3.3, (hw390_adc / 1023.0) * 3.3)), 3)),
        "Atm_Pressure_inHg": float(pressure_inhg),
        "Atm_Temperature_C": float(air_temp_c),
        "Soil_Temperature_C": float(soil_temp_c),
        "temp_gradient_c": float(air_temp_c - soil_temp_c),
        "board_soil_temp_diff_c": 0.5,
        "Hour_sin": math.sin(hour_rad),
        "Hour_cos": math.cos(hour_rad),
        "vwc_lag_15m": float(lag_15m),
        "vwc_lag_1h": float(lag_1h),
        "vwc_lag_4h": float(lag_4h),
        "vwc_lag_6h": float(lag_6h),
        "vwc_lag_12h": float(lag_12h),
        "vwc_lag_24h": float(lag_24h),
        "adc_lag_1h": float(hw390_adc),
        "adc_lag_6h": float(hw390_adc),
        "soil_temp_lag_1h": float(soil_temp_c),
        "soil_temp_lag_6h": float(soil_temp_c),
        "vwc_rolling_mean_4h": roll_mean_4h,
        "vwc_rolling_std_4h": roll_std_4h,
        "vwc_rolling_mean_24h": roll_mean_24h,
        "vwc_rate_1h": float(current_vwc_pct - lag_1h),
        "vwc_rate_6h": float(current_vwc_pct - lag_6h),
        "atm_temp_rolling_mean_6h": float(air_temp_c),
    }

    preds = {}
    deltas_ml = {}
    temp_stress_factor = 1.0 + max(0.0, (air_temp_c - 26.0) * 0.04)
    rh_factor = 1.0 + max(0.0, (65.0 - (rh_pct if rh_pct is not None else 65.0)) * 0.008)

    for h_label, hours_num in [("1h", 1), ("6h", 6), ("12h", 12), ("24h", 24)]:
        bundle = models.get(h_label)
        ml_delta = 0.0
        if bundle is not None:
            X = pd.DataFrame([row_dict])[bundle["features"]]
            raw_pred = float(bundle["model"].predict(X)[0])
            ml_delta = float(np.clip(raw_pred, -0.8 * hours_num, 0.8 * hours_num))
        deltas_ml[h_label] = round(ml_delta, 3)

        # Combine ML delta with FAO-56 ETc depletion physics + any simulated rain infiltration
        etc_hourly_vwc_drop = (etc_mm_day / 24.0) * 0.14 * temp_stress_factor * rh_factor
        rain_gain = simulated_rain_mm * 0.45 * min(1.0, hours_num / 6.0) if simulated_rain_mm > 0 else 0.0
        combined_delta = (0.55 * ml_delta) - (etc_hourly_vwc_drop * hours_num * 0.45) + rain_gain
        preds[h_label] = round(float(np.clip(current_vwc_pct + combined_delta, 4.0, 55.0)), 2)

    drivers = []
    if air_temp_c >= 30.0:
        drivers.append(f"Temperatura ambiental elevada ({air_temp_c:.1f} °C) acelera tasa de evapotranspiración")
    if rh_pct is not None and rh_pct <= 55.0:
        drivers.append(f"Humedad relativa baja ({rh_pct:.0f} % HR) incrementa déficit de presión de vapor")
    if simulated_rain_mm > 0:
        drivers.append(f"Evento de lluvia simulado (+{simulated_rain_mm:.1f} mm) aporta recarga superficial")
    drivers.append(f"Tendencia ML residual (Δ6h={deltas_ml.get('6h', 0.0):+.2f} % VWC) con demanda ETc={etc_mm_day:.2f} mm/día")

    return {
        "predictions": preds,
        "ml_raw_deltas": deltas_ml,
        "model_version": "model2_forecast_v1.1.0",
        "drivers": drivers,
    }


def process_zone_telemetry(
    zone_id: str,
    raw_adc: Optional[int] = None,
    measured_vwc_pct: Optional[float] = None,
    air_temp_c: float = 25.5,
    soil_temp_c: float = 24.2,
    rh_pct: Optional[float] = 68.0,
    pressure_inhg: float = 29.92,
    water_lamina_mm: Optional[float] = None,
    source_type: str = "tinkercad_serial",
    simulated_rain_mm: float = 0.0,
    simulated_runtime_min: float = 0.0,
    manual_pump_override: Optional[bool] = None,
    tinkercad_pump_active: Optional[bool] = None,
    tinkercad_safety_cutoff: Optional[bool] = None,
    live_ai_loop: bool = False,
) -> Dict[str, Any]:
    """
    Full End-to-End Pipeline for one zone measurement:
    1. Sensor Integrity Check -> 2. ML Calibration -> 3. ML Multi-Horizon Forecast ->
    4. Agronomic Evaluation (including Rice Paddy) -> 5. Deterministic Safety Guardrails ->
    6. Persist Readings, Recommendations, Events, Alerts -> 7. Return Bidirectional Actuator Command.
    """
    now_dt = datetime.now()
    now_iso = now_dt.isoformat(timespec="seconds")

    with db_session() as conn:
        zone = conn.execute("SELECT * FROM zones WHERE zone_id = ?", (zone_id,)).fetchone()
        if not zone:
            raise ValueError(f"Zone '{zone_id}' not found")

        crop = conn.execute("SELECT * FROM crops WHERE crop_id = ?", (zone["crop_id"],)).fetchone()
        profile = conn.execute("SELECT * FROM crop_profiles WHERE crop_id = ?", (zone["crop_id"],)).fetchone()
        stage = conn.execute(
            "SELECT * FROM growth_stages WHERE crop_id = ? AND stage_key = ?",
            (zone["crop_id"], zone["active_stage_key"]),
        ).fetchone()
        sensor = conn.execute("SELECT * FROM sensors WHERE zone_id = ?", (zone_id,)).fetchone()

        kc = float(stage["kc_value"]) if stage else 1.0
        et0 = float(profile["et0_reference_mm_day"])
        etc_mm_day = round(kc * et0 * (1.0 + max(0.0, (air_temp_c - 25.0) * 0.03)), 2)

        # Determine Arduino command prefix for hardware demo zones
        cmd_prefix = "Z1" if zone_id == "zone_01" else ("Z2" if zone_id == "zone_02" else f"V_{zone['crop_id'].upper()}")

        # -----------------------------------------------------
        # STEP 1 & 5A: HARDWARE SENSOR FAULT CHECK (raw < 0 or raw > 1015 for SparkFun Soil Moisture Sensor)
        # -----------------------------------------------------
        is_fault = False
        if raw_adc is not None and (raw_adc < 0 or raw_adc > 1015):
            is_fault = True

        if is_fault:
            arduino_cmd = f"{cmd_prefix}:PUMP=0"
            conn.execute(
                """UPDATE zones SET pump_active=0, sensor_fault=1, last_raw_adc=?, current_moisture_pct=NULL, updated_at=? WHERE zone_id=?""",
                (raw_adc, now_iso, zone_id),
            )
            conn.execute(
                """INSERT INTO sensor_readings (
                    timestamp, zone_id, crop_id, source_type, sensor_id, raw_value,
                    soil_moisture_pct, soil_temperature_c, air_temperature_c, relative_humidity_pct,
                    atmospheric_pressure_inhg, water_lamina_mm, irrigation_state, water_volume_liters,
                    dataset_id, calibration_version
                ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, 0, 0.0, NULL, 'fault_bypass')""",
                (now_iso, zone_id, zone["crop_id"], source_type, sensor["sensor_id"], raw_adc, soil_temp_c, air_temp_c, rh_pct, pressure_inhg, water_lamina_mm),
            )
            conn.execute(
                """INSERT INTO irrigation_recommendations (
                    timestamp, zone_id, crop_id, stage_key, current_moisture_pct,
                    predicted_1h_pct, predicted_6h_pct, predicted_12h_pct, predicted_24h_pct,
                    etc_mm_day, decision, recommended_liters, recommended_duration_min,
                    confidence_note, explanation, model_version
                ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?, 'SAFE_SHUTOFF', 0.0, 0.0, 'Bloqueo de seguridad determinista', ?, 'safety_guard_v1')""",
                (now_iso, zone_id, zone["crop_id"], zone["active_stage_key"], etc_mm_day,
                 f"Lectura ADC={raw_adc} fuera de rango físico (0..1015). Bomba forzada a OFF por protección."),
            )
            conn.execute(
                """INSERT INTO alerts (
                    created_at, zone_id, crop_id, alert_type, severity, title, description, cause, recommendation, status, detection_source, is_simulated
                ) VALUES (?, ?, ?, 'SENSOR_DISCONNECTED', 'CRITICAL', ?, ?, ?, ?, 'ACTIVE', ?, 1)""",
                (
                    now_iso, zone_id, zone["crop_id"],
                    f"Fallo crítico de sensor en {zone['zone_name']}",
                    f"Lectura ADC={raw_adc} indica sensor desconectado o cortocircuito.",
                    "Cable de señal A0/A1 abierto (<0 o >1015 cuentas ADC).",
                    "Inspeccionar cableado físico/Tinkercad. El motor de seguridad bloqueó el actuador en estado OFF.",
                    "simulated_tinkercad" if source_type == "tinkercad_serial" else "simulated_scenario",
                ),
            )
            if zone["pump_active"] == 1:
                conn.execute(
                    """INSERT INTO irrigation_events (timestamp, zone_id, crop_id, action, trigger_mode, duration_minutes, water_volume_liters, volume_nature, reason, arduino_command)
                       VALUES (?, ?, ?, 'STOP', 'SAFETY_GUARD', 0.0, 0.0, 'simulated', 'Apagado inmediato por fallo de sensor ADC.', ?)""",
                    (now_iso, zone_id, zone["crop_id"], arduino_cmd),
                )

            return {
                "zone_id": zone_id,
                "crop_id": zone["crop_id"],
                "source_type": source_type,
                "raw_adc": raw_adc,
                "calibrated_ecoirrigate_vwc_pct": None,
                "soil_moisture_pct": None,
                "water_lamina_mm": water_lamina_mm,
                "sensor_fault": True,
                "safety_cutoff": bool(zone["safety_cutoff"]),
                "pump_active": False,
                "decision": "SAFE_SHUTOFF",
                "arduino_command": arduino_cmd,
                "predictions": None,
                "etc_mm_day": etc_mm_day,
                "explanation": f"Estado seguro activado: lectura ADC={raw_adc} fuera de rango válido [0, 1015].",
                "timestamp": now_iso,
            }

        # -----------------------------------------------------
        # STEP 2: CALIBRATION (Model 1 + SparkFun Scaled Curve)
        # -----------------------------------------------------
        eff_raw_for_cal = raw_adc if raw_adc is not None else vwc_to_sparkfun_adc(measured_vwc_pct if measured_vwc_pct is not None else 25.0)
        ecoirr_vwc, scaled_vwc = calibrate_hw390_adc(
            eff_raw_for_cal,
            soil_temp_c=soil_temp_c,
            air_temp_c=air_temp_c,
        )
        current_vwc = round(float(measured_vwc_pct), 2) if measured_vwc_pct is not None else scaled_vwc
        eff_raw = raw_adc if raw_adc is not None else vwc_to_sparkfun_adc(current_vwc)

        # Fetch recent readings for lag construction
        hist_rows = conn.execute(
            "SELECT soil_moisture_pct FROM sensor_readings WHERE zone_id = ? AND soil_moisture_pct IS NOT NULL ORDER BY reading_id DESC LIMIT 96",
            (zone_id,),
        ).fetchall()
        hist_vals = [float(r["soil_moisture_pct"]) for r in reversed(hist_rows)] + [current_vwc]

        # -----------------------------------------------------
        # STEP 3: MULTI-HORIZON FORECAST (Model 2)
        # -----------------------------------------------------
        fc = forecast_moisture_horizons(
            current_vwc_pct=current_vwc,
            raw_adc=eff_raw,
            air_temp_c=air_temp_c,
            soil_temp_c=soil_temp_c,
            rh_pct=rh_pct,
            pressure_inhg=pressure_inhg,
            etc_mm_day=etc_mm_day,
            recent_vwc_history=hist_vals,
            simulated_rain_mm=simulated_rain_mm,
        )
        preds = fc["predictions"]

        # -----------------------------------------------------
        # STEP 4 & 5B: AGRONOMIC + DETERMINISTIC SAFETY ENGINE
        # -----------------------------------------------------
        opt_min = float(profile["optimal_min_vwc_pct"])
        hyst_band = float(profile["hysteresis_band_pct"])
        stop_threshold = round(opt_min + hyst_band, 2)
        excess_vwc = float(profile["excess_moisture_vwc_pct"])
        crit_vwc = float(profile["critical_stress_vwc_pct"])
        max_runtime = float(profile["max_irrigation_duration_minutes"])
        cooldown_min = int(profile["min_cooldown_minutes"])
        flow_l_min = float(profile["nominal_flow_l_min"])
        op_mode = zone["operating_mode"]
        prev_pump = bool(zone["pump_active"])

        # Cooldown check (demo live_ai_loop uses 3 s matching firmware; field uses crop min_cooldown_minutes)
        eff_cooldown_min = 0.05 if live_ai_loop else cooldown_min
        cooldown_active = False
        if not prev_pump and zone["last_pump_stop_ts"]:
            try:
                elapsed_min = (now_dt - datetime.fromisoformat(zone["last_pump_stop_ts"])).total_seconds() / 60.0
                if elapsed_min < eff_cooldown_min:
                    cooldown_active = True
            except Exception:
                pass

        # Max runtime check
        safety_cutoff = False
        if simulated_runtime_min > max_runtime:
            safety_cutoff = True
        elif prev_pump and zone["pump_start_ts"]:
            try:
                running_min = (now_dt - datetime.fromisoformat(zone["pump_start_ts"])).total_seconds() / 60.0
                if running_min >= max_runtime:
                    safety_cutoff = True
            except Exception:
                pass

        decision = "HOLD"
        target_pump = prev_pump
        recommended_min = 0.0
        recommended_liters = 0.0
        explanation_parts = []
        alert_to_emit = None

        # SPECIALIZED RICE FLOOD PADDY LOGIC
        lamina_val = water_lamina_mm if water_lamina_mm is not None else zone["current_water_lamina_mm"]
        if zone["crop_id"] == "arroz" and profile["paddy_lamina_json"]:
            paddy_cfg = json.loads(profile["paddy_lamina_json"]).get(zone["active_stage_key"], {})
            min_lam = float(paddy_cfg.get("min_water_lamina_mm", 25.0))
            target_lam = float(paddy_cfg.get("target_water_lamina_mm", 50.0))
            max_lam = float(paddy_cfg.get("max_water_lamina_mm", 80.0))
            drain_req = bool(paddy_cfg.get("drainage_required", False))
            lamina_val = float(lamina_val if lamina_val is not None else target_lam)

            if drain_req:
                decision = "DRAINAGE_PHASE"
                target_pump = False
                explanation_parts.append(
                    f"Arroz en etapa final (maduración): se requiere drenaje pre-cosecha (lámina objetivo 0–15 mm, actual {lamina_val:.1f} mm). Riego bloqueado."
                )
            elif safety_cutoff:
                decision = "SAFE_SHUTOFF"
                target_pump = False
                explanation_parts.append(f"Límite máximo continuo de {max_runtime:.0f} min superado en melga de arroz. Apagado de seguridad.")
                alert_to_emit = ("MAX_RUNTIME_CUTOFF", "CRITICAL", "Tiempo máximo de riego excedido (Arroz)",
                                 f"Duración alcanzó {simulated_runtime_min:.1f} min (límite {max_runtime:.0f} min).",
                                 "Protección automática contra desborde de melga.", "Verificar compuerta/bomba antes de reiniciar.")
            elif lamina_val < min_lam or current_vwc < 42.0:
                decision = "IRRIGATE"
                needed_mm = max(5.0, target_lam - lamina_val)
                recommended_min = round(min(max_runtime, needed_mm * 0.6), 1)
                recommended_liters = round(recommended_min * flow_l_min, 1)
                explanation_parts.append(
                    f"Arroz ({zone['active_stage_key']}): lámina actual {lamina_val:.1f} mm < mínimo {min_lam:.1f} mm (VWC={current_vwc:.1f}%). Requiere reposición hasta {target_lam:.0f} mm."
                )
                if op_mode == "AUTO_SIMULATED" and not cooldown_active:
                    target_pump = True
                elif cooldown_active:
                    decision = "WAIT_COOLDOWN"
                    target_pump = False
                    explanation_parts.append("En periodo de espera mínimo (cooldown) entre pulsos.")
                alert_to_emit = ("PADDY_LOW_LAMINA", "WARNING", "Lámina de inundación baja en Arroz",
                                 f"Lámina {lamina_val:.1f} mm por debajo de {min_lam:.1f} mm.",
                                 "Evapotranspiración e infiltración en melga.", f"Reponer {recommended_liters} L estimados hasta {target_lam:.0f} mm.")
            elif lamina_val > max_lam:
                decision = "HOLD"
                target_pump = False
                explanation_parts.append(f"Lámina {lamina_val:.1f} mm supera el límite de rebalse ({max_lam:.1f} mm). Bomba detenida.")
                alert_to_emit = ("PADDY_OVERFLOW", "WARNING", "Riesgo de rebalse en melga de Arroz",
                                 f"Lámina actual {lamina_val:.1f} mm > máximo {max_lam:.1f} mm.",
                                 "Aporte excesivo o lluvia intensa.", "Abrir aliviadero de drenaje controlado.")
            else:
                decision = "HOLD"
                target_pump = False
                explanation_parts.append(
                    f"Arroz en régimen óptimo de inundación: lámina {lamina_val:.1f} mm (banda {min_lam:.0f}–{max_lam:.0f} mm) y saturación {current_vwc:.1f}% VWC."
                )
        else:
            # UPLAND CROPS LOGIC (Tomate, Lechuga, Café, Maíz, Frijol, Chile dulce)
            if safety_cutoff:
                decision = "SAFE_SHUTOFF"
                target_pump = False
                explanation_parts.append(
                    f"Límite máximo continuo de riego ({max_runtime:.0f} min) superado (ejecución={simulated_runtime_min:.1f} min). Bomba apagada por seguridad."
                )
                alert_to_emit = ("MAX_RUNTIME_CUTOFF", "CRITICAL", f"Límite de tiempo de riego superado en {zone['zone_name']}",
                                 f"Tiempo activo ({simulated_runtime_min:.1f} min) superó el máximo seguro ({max_runtime:.0f} min).",
                                 "Posible fuga hidráulica o sensor estancado sin registrar aumento de humedad.",
                                 "Revisar mangueras, goteros y calibración del sensor antes de restablecer.")
            elif current_vwc >= excess_vwc:
                decision = "HOLD"
                target_pump = False
                explanation_parts.append(
                    f"Exceso hídrico detectado ({current_vwc:.1f}% VWC >= {excess_vwc:.1f}%). Riesgo de anoxia/patógenos radiculares en {crop['common_name']}."
                )
                alert_to_emit = ("EXCESS_MOISTURE", "WARNING", f"Exceso de humedad en {crop['common_name']}",
                                 f"Humedad {current_vwc:.1f}% VWC excede el umbral seguro de {excess_vwc:.1f}%.",
                                 "Sobre-riego o precipitación intensa.", "Suspender riego y verificar drenaje del lote.")
            elif current_vwc < opt_min or (preds["6h"] < opt_min and current_vwc < stop_threshold):
                deficit_pct = max(0.5, stop_threshold - current_vwc)
                recommended_min = round(min(max_runtime, deficit_pct * 2.2), 1)
                recommended_liters = round(recommended_min * flow_l_min, 1)
                if cooldown_active and op_mode == "AUTO_SIMULATED" and not prev_pump:
                    decision = "WAIT_COOLDOWN"
                    target_pump = False
                    explanation_parts.append(
                        f"Déficit detectado ({current_vwc:.1f}% VWC / 6h={preds['6h']:.1f}% < {opt_min:.1f}%), pero zona en cooldown mínimo de {cooldown_min} min."
                    )
                else:
                    decision = "IRRIGATE"
                    trigger_cause = "humedad actual bajo umbral" if current_vwc < opt_min else f"pronóstico IA a 6h ({preds['6h']:.1f}%)"
                    explanation_parts.append(
                        f"Necesidad hídrica en {crop['common_name']} ({zone['active_stage_key']}): {trigger_cause} debajo del límite óptimo ({opt_min:.1f}% VWC). Histéresis de parada: {stop_threshold:.1f}%."
                    )
                    if op_mode == "AUTO_SIMULATED":
                        target_pump = True
                    elif op_mode in ("MONITORING", "RECOMMENDATION"):
                        target_pump = False
                        explanation_parts.append(f"Modo {op_mode}: se emite recomendación sin activar bomba automáticamente.")
                sev = "CRITICAL" if current_vwc <= crit_vwc else "WARNING"
                alert_to_emit = ("LOW_MOISTURE", sev,
                                 f"Déficit hídrico {'crítico' if sev=='CRITICAL' else 'preventivo'} en {crop['common_name']}",
                                 f"VWC actual={current_vwc:.1f}% (óptimo >= {opt_min:.1f}%, crítico <= {crit_vwc:.1f}%). Predicción 6h={preds['6h']:.1f}%.",
                                 f"Agotamiento de humedad radicular con ETc={etc_mm_day:.2f} mm/día.",
                                 f"Aplicar pulso estimado de {recommended_min} min (~{recommended_liters} L).")
            elif prev_pump and current_vwc < stop_threshold:
                # Inside hysteresis band while pump was already ON -> keep pumping until stop_threshold
                decision = "IRRIGATE"
                target_pump = True if op_mode == "AUTO_SIMULATED" else False
                explanation_parts.append(
                    f"Banda de histéresis activa ({current_vwc:.1f}% entre {opt_min:.1f}% y {stop_threshold:.1f}%): manteniendo riego hasta alcanzar {stop_threshold:.1f}% VWC."
                )
            else:
                decision = "HOLD"
                target_pump = False
                explanation_parts.append(
                    f"Humedad óptima en {crop['common_name']}: {current_vwc:.1f}% VWC (objetivo {opt_min:.1f}–{profile['optimal_max_vwc_pct']:.1f}%). Predicción 6h={preds['6h']:.1f}% VWC."
                )

        # Handle explicit manual mode override safely
        if op_mode == "MANUAL_SIMULATED" and not safety_cutoff:
            desired_manual = prev_pump if manual_pump_override is None else manual_pump_override
            if desired_manual and current_vwc < excess_vwc:
                target_pump = True
                decision = "IRRIGATE"
                explanation_parts.append("Control manual simulado: bomba activa tras superar guardas de seguridad.")
            else:
                target_pump = False
                decision = "HOLD"
                explanation_parts.append("Control manual simulado: bomba detenida.")

        if source_type == "tinkercad_serial" and tinkercad_safety_cutoff is True:
            safety_cutoff = True
            target_pump = False
            decision = "SAFE_SHUTOFF"
            explanation_parts.append("Corte de seguridad físico activado en firmware Arduino (MAX_PUMP_RUNTIME_MS).")

        arduino_cmd = f"{cmd_prefix}:PUMP={'1' if target_pump else '0'}"

        # Persist Zone update
        pump_start_ts = zone["pump_start_ts"]
        last_stop_ts = zone["last_pump_stop_ts"]
        if target_pump and not prev_pump:
            pump_start_ts = now_iso
        elif not target_pump and prev_pump:
            last_stop_ts = now_iso
            pump_start_ts = None

        conn.execute(
            """UPDATE zones SET
                operating_mode = ?, pump_active = ?, sensor_fault = 0, safety_cutoff = ?,
                last_raw_adc = ?, current_moisture_pct = ?, current_water_lamina_mm = ?,
                pump_start_ts = ?, last_pump_stop_ts = ?, updated_at = ?
               WHERE zone_id = ?""",
            (op_mode, 1 if target_pump else 0, 1 if safety_cutoff else 0, eff_raw, current_vwc, lamina_val, pump_start_ts, last_stop_ts, now_iso, zone_id),
        )

        # Persist Reading
        sim_vol = round(flow_l_min * 2.0, 2) if target_pump else 0.0
        conn.execute(
            """INSERT INTO sensor_readings (
                timestamp, zone_id, crop_id, source_type, sensor_id, raw_value,
                soil_moisture_pct, soil_temperature_c, air_temperature_c, relative_humidity_pct,
                atmospheric_pressure_inhg, water_lamina_mm, irrigation_state, water_volume_liters,
                dataset_id, calibration_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'sparkfun_soil_model1_v2')""",
            (now_iso, zone_id, zone["crop_id"], source_type, sensor["sensor_id"], eff_raw, current_vwc, soil_temp_c, air_temp_c, rh_pct, pressure_inhg, lamina_val, 1 if target_pump else 0, sim_vol),
        )

        # Persist Recommendation
        full_explanation = " ".join(explanation_parts) + " Factores IA: " + "; ".join(fc["drivers"])
        conn.execute(
            """INSERT INTO irrigation_recommendations (
                timestamp, zone_id, crop_id, stage_key, current_moisture_pct,
                predicted_1h_pct, predicted_6h_pct, predicted_12h_pct, predicted_24h_pct,
                etc_mm_day, decision, recommended_liters, recommended_duration_min,
                confidence_note, explanation, model_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now_iso, zone_id, zone["crop_id"], zone["active_stage_key"], current_vwc,
                preds["1h"], preds["6h"], preds["12h"], preds["24h"], etc_mm_day,
                decision, recommended_liters, recommended_min,
                "Recomendación híbrida (ML residual EcoIrrigate + FAO-56 + Guardas deterministas). No constituye verdad absoluta sin validación en campo.",
                full_explanation, fc["model_version"],
            ),
        )

        # Persist Event on transition or safety cutoff
        if safety_cutoff:
            conn.execute(
                """INSERT INTO irrigation_events (timestamp, zone_id, crop_id, action, trigger_mode, duration_minutes, water_volume_liters, volume_nature, reason, arduino_command)
                   VALUES (?, ?, ?, 'SAFETY_CUTOFF', ?, ?, ?, 'simulated', ?, ?)""",
                (now_iso, zone_id, zone["crop_id"], op_mode, simulated_runtime_min, round(simulated_runtime_min * flow_l_min, 2), explanation_parts[0], arduino_cmd),
            )
        elif target_pump != prev_pump:
            action = "START" if target_pump else "STOP"
            dur = recommended_min if target_pump else 2.0
            vol = round(dur * flow_l_min, 2) if target_pump else round(2.0 * flow_l_min, 2)
            conn.execute(
                """INSERT INTO irrigation_events (timestamp, zone_id, crop_id, action, trigger_mode, duration_minutes, water_volume_liters, volume_nature, reason, arduino_command)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'simulated', ?, ?)""",
                (now_iso, zone_id, zone["crop_id"], action, op_mode, dur, vol, explanation_parts[0], arduino_cmd),
            )

        # Persist Alert if triggered
        if alert_to_emit:
            a_type, a_sev, a_title, a_desc, a_cause, a_rec = alert_to_emit
            conn.execute(
                """INSERT INTO alerts (created_at, zone_id, crop_id, alert_type, severity, title, description, cause, recommendation, status, detection_source, is_simulated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, 1)""",
                (now_iso, zone_id, zone["crop_id"], a_type, a_sev, a_title, a_desc, a_cause, a_rec,
                 "simulated_tinkercad" if source_type == "tinkercad_serial" else "simulated_scenario"),
            )

        return {
            "zone_id": zone_id,
            "crop_id": zone["crop_id"],
            "crop_name": crop["common_name"],
            "stage_key": zone["active_stage_key"],
            "irrigation_regime": crop["irrigation_regime"],
            "source_type": source_type,
            "raw_adc": eff_raw,
            "calibrated_ecoirrigate_vwc_pct": ecoirr_vwc,
            "soil_moisture_pct": current_vwc,
            "water_lamina_mm": lamina_val,
            "sensor_fault": False,
            "safety_cutoff": safety_cutoff,
            "cooldown_active": cooldown_active,
            "pump_active": target_pump,
            "decision": decision,
            "recommended_duration_min": recommended_min,
            "recommended_liters": recommended_liters,
            "arduino_command": arduino_cmd,
            "thresholds": {
                "optimal_min_vwc_pct": opt_min,
                "hysteresis_stop_vwc_pct": stop_threshold,
                "critical_stress_vwc_pct": crit_vwc,
                "excess_moisture_vwc_pct": excess_vwc,
            },
            "predictions": preds,
            "ml_raw_deltas": fc["ml_raw_deltas"],
            "etc_mm_day": etc_mm_day,
            "drivers": fc["drivers"],
            "explanation": full_explanation,
            "timestamp": now_iso,
        }
