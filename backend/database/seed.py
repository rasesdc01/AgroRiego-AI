"""
AgroRiego AI — Idempotent Database Seeder
Populates the 15 SQLite tables from verified JSON crop configs,
raw EcoIrrigate dataset records, real trained ML metrics, and test scenarios.
"""

import glob
import json
import os
from datetime import datetime, timedelta
import pandas as pd

from backend.database.db import db_session, init_db

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CROPS_CONFIG_DIR = os.path.join(ROOT, "config", "crops")
SOURCES_PATH = os.path.join(ROOT, "datasets", "sources.json")
METRICS_PATH = os.path.join(ROOT, "ai", "reports", "metrics.json")
HIST_PATH = os.path.join(ROOT, "ai", "reports", "training_history.json")
RAW_CSV_PATH = os.path.join(ROOT, "datasets", "raw", "kolkata_unified_dataset.csv")


def seed_all(force_reset_readings: bool = False):
    init_db()
    now_iso = datetime.now().isoformat(timespec="seconds")

    with db_session() as conn:
        # 1. Seed 7 Crops, CropProfiles, GrowthStages
        crop_configs = []
        for p in sorted(glob.glob(os.path.join(CROPS_CONFIG_DIR, "*.json"))):
            with open(p, encoding="utf-8") as f:
                crop_configs.append(json.load(f))

        for cfg in crop_configs:
            cid = cfg["crop_id"]
            conn.execute(
                """INSERT OR REPLACE INTO crops (crop_id, common_name, scientific_name, family, irrigation_regime, soil_texture_recommended)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (cid, cfg["common_name"], cfg["scientific_name"], cfg["family"], cfg["irrigation_regime"], cfg["soil_texture_recommended"]),
            )
            sh = cfg["soil_hydrology_vwc_pct"]
            amb = cfg["ambient_conditions"]
            ctrl = cfg["control_parameters"]
            conn.execute(
                """INSERT OR REPLACE INTO crop_profiles (
                    profile_id, crop_id, saturation_vwc_pct, field_capacity_vwc_pct, wilting_point_vwc_pct,
                    optimal_min_vwc_pct, optimal_max_vwc_pct, critical_stress_vwc_pct, excess_moisture_vwc_pct,
                    depletion_fraction_p, et0_reference_mm_day, hysteresis_band_pct, min_cooldown_minutes,
                    max_irrigation_duration_minutes, nominal_flow_l_min, optimal_air_temp_min_c, optimal_air_temp_max_c,
                    optimal_rh_min_pct, optimal_rh_max_pct, paddy_lamina_json, sources_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    f"profile_{cid}", cid, sh["saturation_vwc_pct"], sh["field_capacity_vwc_pct"],
                    sh["wilting_point_vwc_pct"], sh["optimal_min_vwc_pct"], sh["optimal_max_vwc_pct"],
                    sh["critical_stress_vwc_pct"], sh["excess_moisture_vwc_pct"],
                    cfg["readily_available_water_fraction_p"], cfg["et0_reference_mm_day"],
                    ctrl["hysteresis_band_pct"], ctrl["min_cooldown_minutes"],
                    ctrl["max_irrigation_duration_minutes"], ctrl["nominal_flow_liters_per_min"],
                    amb["optimal_air_temp_c"][0], amb["optimal_air_temp_c"][1],
                    amb["ambient_relative_humidity_range_pct"][0], amb["ambient_relative_humidity_range_pct"][1],
                    json.dumps(cfg.get("paddy_lamina_params_mm")) if cfg.get("paddy_lamina_params_mm") else None,
                    json.dumps(cfg["sources"]),
                ),
            )
            stage_order = [("inicial", 1), ("desarrollo", 2), ("medio", 3), ("final", 4)]
            for skey, sord in stage_order:
                conn.execute(
                    """INSERT OR REPLACE INTO growth_stages (crop_id, stage_key, stage_order, duration_days, root_depth_m, kc_value)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (cid, skey, sord, cfg["stage_durations_days"][skey], cfg["root_depth_m"][skey], cfg["kc_by_stage"][skey]),
                )

        # 2. Seed Zones (2 Tinkercad Hardware Demo Zones + 7 Virtual Crop Simulation Zones)
        existing_zones = conn.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
        if existing_zones == 0:
            zone_defs = [
                ("zone_01", "Zona Hardware 01 (Arduino A0 / Bomba D8)", "HARDWARE_TINKERCAD", "A0, D8, D4, D5", "tomate", "medio", "AUTO_SIMULATED", 0, 0, 0, 520, 31.0, None, 120.0),
                ("zone_02", "Zona Hardware 02 (Arduino A1 / Bomba D9)", "HARDWARE_TINKERCAD", "A1, D9, D6, D7", "lechuga", "medio", "AUTO_SIMULATED", 0, 0, 0, 560, 33.0, None, 120.0),
                ("vzone_tomate", "Perfil Virtual — Tomate (Solanum lycopersicum)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "tomate", "medio", "RECOMMENDATION", 0, 0, 0, None, 26.5, None, 250.0),
                ("vzone_lechuga", "Perfil Virtual — Lechuga (Lactuca sativa)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "lechuga", "desarrollo", "RECOMMENDATION", 0, 0, 0, None, 27.1, None, 180.0),
                ("vzone_cafe", "Perfil Virtual — Café (Coffea arabica)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "cafe", "medio", "RECOMMENDATION", 0, 0, 0, None, 31.4, None, 850.0),
                ("vzone_arroz", "Perfil Virtual — Arroz Inundado (Oryza sativa)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "arroz", "medio", "AUTO_SIMULATED", 0, 0, 0, None, 46.5, 62.0, 600.0),
                ("vzone_maiz", "Perfil Virtual — Maíz (Zea mays)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "maiz", "medio", "RECOMMENDATION", 0, 0, 0, None, 25.8, None, 500.0),
                ("vzone_frijol", "Perfil Virtual — Frijol (Phaseolus vulgaris)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "frijol", "desarrollo", "RECOMMENDATION", 0, 0, 0, None, 24.4, None, 300.0),
                ("vzone_chile_dulce", "Perfil Virtual — Chile Dulce (Capsicum annuum)", "VIRTUAL_CROP_PROFILE", "VIRTUAL", "chile_dulce", "medio", "RECOMMENDATION", 0, 0, 0, None, 27.8, None, 220.0),
            ]
            for z in zone_defs:
                conn.execute(
                    """INSERT INTO zones (
                        zone_id, zone_name, zone_tier, hardware_pins, crop_id, active_stage_key,
                        operating_mode, pump_active, sensor_fault, safety_cutoff, last_raw_adc,
                        current_moisture_pct, current_water_lamina_mm, area_m2, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*z, now_iso),
                )

            # Sensors
            sensors = [
                ("sens_hw_a0", "zone_01", "Sensor de Humedad de Suelo (SparkFun / Tinkercad)", "Arduino ADC 10-bit", "A0", "v2.0-sparkfun"),
                ("sens_hw_a1", "zone_02", "Sensor de Humedad de Suelo (SparkFun / Tinkercad)", "Arduino ADC 10-bit", "A1", "v2.0-sparkfun"),
                ("sens_virt_tomate", "vzone_tomate", "Sensor Virtual FAO-56", "EcoIrrigate ML Twin", "V0", "model1_v1.0"),
                ("sens_virt_lechuga", "vzone_lechuga", "Sensor Virtual FAO-56", "EcoIrrigate ML Twin", "V1", "model1_v1.0"),
                ("sens_virt_cafe", "vzone_cafe", "Sensor Virtual FAO-56", "EcoIrrigate ML Twin", "V2", "model1_v1.0"),
                ("sens_virt_arroz", "vzone_arroz", "Sensor Lámina + Saturación", "Paddy Level Twin", "V3", "model1_v1.0"),
                ("sens_virt_maiz", "vzone_maiz", "Sensor Virtual FAO-56", "EcoIrrigate ML Twin", "V4", "model1_v1.0"),
                ("sens_virt_frijol", "vzone_frijol", "Sensor Virtual FAO-56", "EcoIrrigate ML Twin", "V5", "model1_v1.0"),
                ("sens_virt_chile", "vzone_chile_dulce", "Sensor Virtual FAO-56", "EcoIrrigate ML Twin", "V6", "model1_v1.0"),
            ]
            for s in sensors:
                conn.execute(
                    """INSERT OR REPLACE INTO sensors (sensor_id, zone_id, sensor_type, model_name, analog_pin, calibration_version, status)
                       VALUES (?, ?, ?, ?, ?, ?, 'ONLINE')""",
                    s,
                )

        # Ensure existing hardware sensor metadata reflects SparkFun Soil Moisture Sensor
        conn.execute(
            """UPDATE sensors
               SET sensor_type = 'Sensor de Humedad de Suelo (SparkFun / Tinkercad)',
                   calibration_version = 'v2.0-sparkfun'
               WHERE sensor_id IN ('sens_hw_a0', 'sens_hw_a1')"""
        )

        # 3. Seed Datasets
        if os.path.exists(SOURCES_PATH):
            with open(SOURCES_PATH, encoding="utf-8") as f:
                src = json.load(f)
            pds = src["primary_dataset"]
            sha0 = pds["files"][0]["sha256"] if pds.get("files") else None
            conn.execute(
                """INSERT OR REPLACE INTO datasets (dataset_id, title, authors, year, repository, doi, url, version, license, downloaded_at, total_records, sha256_primary, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pds["dataset_id"], pds["title"], "; ".join(pds["authors"]), pds["year"],
                    pds["repository"], pds["doi"], pds["doi_url"], pds["version"],
                    pds["license"], pds["downloaded_at"], pds["total_records"], sha0,
                    "DOWNLOADED_AND_TRAINED",
                ),
            )
            for rds in src.get("referenced_candidate_datasets", []):
                conn.execute(
                    """INSERT OR REPLACE INTO datasets (dataset_id, title, authors, year, repository, doi, url, version, license, downloaded_at, total_records, sha256_primary, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rds["dataset_id"], rds["title"], "; ".join(rds["authors"]), rds["year"],
                        rds["repository"], rds["doi"], rds["url"], rds["version"],
                        rds["license"], now_iso, None, None, "METADATA_VERIFIED_REFERENCE",
                    ),
                )

        # 4. Seed Models, ModelVersions & TrainingRuns from real metrics.json
        if os.path.exists(METRICS_PATH):
            with open(METRICS_PATH, encoding="utf-8") as f:
                mjson = json.load(f)
            for key, minfo in mjson.get("best_models", {}).items():
                mt = minfo["metrics"]
                conn.execute(
                    """INSERT OR REPLACE INTO models (model_id, task_name, description, active_version)
                       VALUES (?, ?, ?, ?)""",
                    (minfo["model_id"], key, f"Trained {minfo['algorithm']} for {key}", minfo["version"]),
                )
                existing_mv = conn.execute(
                    "SELECT COUNT(*) FROM model_versions WHERE model_id=? AND version_tag=?",
                    (minfo["model_id"], minfo["version"]),
                ).fetchone()[0]
                if existing_mv == 0:
                    conn.execute(
                        """INSERT INTO model_versions (model_id, version_tag, algorithm, artifact_path, trained_at, dataset_id, val_rmse, test_mae, test_rmse, test_r2, seed, features_json)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            minfo["model_id"], minfo["version"], minfo["algorithm"], minfo["artifact_path"],
                            mjson["generated_at"], "ecoirrigate_kolkata_2025",
                            mt["val_rmse"], mt["test_mae"], mt["test_rmse"], mt["test_r2"],
                            mjson["random_seed"], json.dumps(minfo["features"]),
                        ),
                    )
        if os.path.exists(HIST_PATH):
            existing_runs = conn.execute("SELECT COUNT(*) FROM training_runs").fetchone()[0]
            if existing_runs == 0:
                with open(HIST_PATH, encoding="utf-8") as f:
                    hist = json.load(f)
                for h in hist:
                    conn.execute(
                        """INSERT INTO training_runs (executed_at, dataset_id, task, algorithm, val_rmse, test_rmse, test_r2)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (h["timestamp"], "ecoirrigate_kolkata_2025", h["task"], h["algorithm"], h["val_rmse"], h["test_rmse"], h["test_r2"]),
                    )

        # 5. Seed real EcoIrrigate historical readings slice (last 300 points per farm)
        existing_hist_readings = conn.execute("SELECT COUNT(*) FROM sensor_readings WHERE source_type='historical_dataset'").fetchone()[0]
        if (existing_hist_readings == 0 or force_reset_readings) and os.path.exists(RAW_CSV_PATH):
            df = pd.read_csv(RAW_CSV_PATH)
            f1 = df[df["Farm_ID"] == "Kolkata_Farm_1"].tail(180)
            f2 = df[df["Farm_ID"] == "Kolkata_Farm_2"].tail(180)
            rows_to_insert = []
            for z_id, s_id, crop_id, sub in [
                ("zone_01", "sens_hw_a0", "tomate", f1),
                ("zone_02", "sens_hw_a1", "lechuga", f2),
            ]:
                for _, r in sub.iterrows():
                    rows_to_insert.append((
                        str(r["Timestamp"]), z_id, crop_id, "historical_dataset", s_id,
                        int(r["Raw_Capacitive_ADC"]), float(r["Volumetric_Moisture_Pct"]),
                        float(r["Soil_Temperature_C"]), float(r["Atm_Temperature_C"]),
                        None, None, float(r["Atm_Pressure_inHg"]), None, 0, 0.0,
                        "ecoirrigate_kolkata_2025", "hw390_raw_ecoirrigate",
                    ))
            conn.executemany(
                """INSERT INTO sensor_readings (
                    timestamp, zone_id, crop_id, source_type, sensor_id, raw_value,
                    soil_moisture_pct, soil_temperature_c, air_temperature_c, relative_humidity_pct,
                    light_intensity, atmospheric_pressure_inhg, water_lamina_mm, irrigation_state,
                    water_volume_liters, dataset_id, calibration_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows_to_insert,
            )

        # 6. Seed 6 mandatory simulation scenarios + agronomic test scenarios
        scenarios = [
            ("scn_1_adequate", "Escenario 1: Humedad Adecuada (Estado Reposo)", "circuit_mandatory",
             "Lectura SparkFun ADC en banda óptima (33.0 % VWC, raw=560). La bomba permanece apagada y no se genera desperdicio de agua.",
             json.dumps({"zone_id": "zone_01", "raw_adc": 560, "air_temp_c": 24.0, "rh_pct": 68.0}),
             "Bomba OFF, LED verde apagado, decisión HOLD."),
            ("scn_2_dry_trigger", "Escenario 2: Humedad Insuficiente (Activación Automática)", "circuit_mandatory",
             "Lectura SparkFun ADC en zona seca (14.0 % VWC, raw=180). La IA proyecta déficit y el motor habilita riego.",
             json.dumps({"zone_id": "zone_01", "raw_adc": 180, "air_temp_c": 29.5, "rh_pct": 52.0}),
             "Bomba ON en Zona 1, comando Z1:PUMP=1 emitido, alerta WARNING generada."),
            ("scn_3_independent_zones", "Escenario 3: Independencia Dual (Zona 1 Seca / Zona 2 Óptima)", "circuit_mandatory",
             "Demuestra independencia eléctrica y lógica: Zona 1 activa riego (raw=180) mientras Zona 2 (raw=600) permanece detenida.",
             json.dumps({"zone_01_raw": 180, "zone_02_raw": 600}),
             "Zona 1 Bomba ON; Zona 2 Bomba OFF sin interferencia."),
            ("scn_4_recovery_hysteresis", "Escenario 4: Recuperación de Humedad e Histéresis", "circuit_mandatory",
             "Tras regar, la humedad alcanza el límite superior de histéresis (34.0 % VWC, raw=580) y la bomba se apaga.",
             json.dumps({"zone_id": "zone_01", "raw_adc": 580, "air_temp_c": 23.0, "rh_pct": 72.0}),
             "Bomba OFF al cruzar banda superior de histéresis, inicia cooldown."),
            ("scn_5_sensor_fault", "Escenario 5: Sensor Inválido o Desconectado (Fallo Crítico)", "circuit_mandatory",
             "Entrada fuera de rango físico (raw=1023, >1015). El sistema bloquea actuadores por seguridad.",
             json.dumps({"zone_id": "zone_01", "raw_adc": 1023, "air_temp_c": 25.0, "rh_pct": 65.0}),
             "Bomba forzada OFF, LED rojo encendido, alerta CRITICAL SENSOR_FAULT."),
            ("scn_6_max_runtime", "Escenario 6: Límite Máximo de Tiempo de Riego (Safety Cutoff)", "circuit_mandatory",
             "Simula una válvula/bomba activa excediendo el tiempo máximo continuo permitido para evitar inundación.",
             json.dumps({"zone_id": "zone_01", "raw_adc": 180, "simulated_runtime_min": 32}),
             "Apagado forzado SAFETY_CUTOFF y alerta CRITICAL."),
            ("scn_7_rice_paddy", "Escenario 7: Arroz Inundado (Lámina de Agua vs Drenaje)", "agronomic_special",
             "Evalúa el manejo diferenciado de Oryza sativa: reposición de lámina en etapa media vs bloqueo de riego en etapa final.",
             json.dumps({"zone_id": "vzone_arroz", "water_lamina_mm": 18.0, "stage": "medio"}),
             "Recomendación de reposición de lámina hasta 70 mm sin alerta de exceso."),
        ]
        for s in scenarios:
            conn.execute(
                """INSERT OR REPLACE INTO simulation_scenarios (scenario_id, name, category, description, parameters_json, expected_outcome)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                s,
            )

        # 7. Seed initial baseline alerts & irrigation events if empty
        if conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0:
            conn.execute(
                """INSERT INTO alerts (created_at, zone_id, crop_id, alert_type, severity, title, description, cause, recommendation, status, detection_source, is_simulated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', 'real_dataset', 0)""",
                (
                    now_iso, "zone_01", "tomate", "LOW_MOISTURE_DATASET", "WARNING",
                    "Humedad baja detectada en serie histórica EcoIrrigate",
                    "Los últimos registros de Kolkata_Farm_1 oscilan entre 10.2 % y 12.8 % VWC, por debajo del umbral óptimo de tomate (24.2 % VWC).",
                    "Suelo franco-arenoso en estación seca de Kolkata (Jan-Apr 2025) sin riego reciente.",
                    "Validar el perfil agronómico del cultivo objetivo antes de trasplantar parámetros.",
                ),
            )
            conn.execute(
                """INSERT INTO alerts (created_at, zone_id, crop_id, alert_type, severity, title, description, cause, recommendation, status, detection_source, is_simulated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACKNOWLEDGED', 'simulated_tinkercad', 1)""",
                (
                    (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds"),
                    "zone_02", "lechuga", "IRRIGATION_COMPLETED", "INFO",
                    "Pulso de riego simulado completado en Zona 2",
                    "Zona Hardware 02 completó un ciclo simulado de 8 min alcanzando 27.6 % VWC.",
                    "Activación automática dentro de banda de histéresis.",
                    "Mantener intervalo mínimo de cooldown de 60 min.",
                ),
            )
        if conn.execute("SELECT COUNT(*) FROM irrigation_events").fetchone()[0] == 0:
            conn.execute(
                """INSERT INTO irrigation_events (timestamp, zone_id, crop_id, action, trigger_mode, duration_minutes, water_volume_liters, volume_nature, reason, arduino_command)
                   VALUES (?, 'zone_02', 'lechuga', 'STOP', 'AUTO_SIMULATED', 8.0, 14.4, 'simulated', 'Ciclo de demostración inicial completado dentro de histéresis.', 'Z2:PUMP=0')""",
                ((datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds"),),
            )
