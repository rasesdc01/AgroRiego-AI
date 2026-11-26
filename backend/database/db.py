"""
AgroRiego AI — SQLite Database Connection & 15-Table Relational Schema
"""

import os
import sqlite3
from contextlib import contextmanager

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(ROOT, "backend", "database", "agroriego.db")


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS crops (
    crop_id TEXT PRIMARY KEY,
    common_name TEXT NOT NULL,
    scientific_name TEXT NOT NULL,
    family TEXT NOT NULL,
    irrigation_regime TEXT NOT NULL,
    soil_texture_recommended TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crop_profiles (
    profile_id TEXT PRIMARY KEY,
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    saturation_vwc_pct REAL NOT NULL,
    field_capacity_vwc_pct REAL NOT NULL,
    wilting_point_vwc_pct REAL NOT NULL,
    optimal_min_vwc_pct REAL NOT NULL,
    optimal_max_vwc_pct REAL NOT NULL,
    critical_stress_vwc_pct REAL NOT NULL,
    excess_moisture_vwc_pct REAL NOT NULL,
    depletion_fraction_p REAL NOT NULL,
    et0_reference_mm_day REAL NOT NULL,
    hysteresis_band_pct REAL NOT NULL,
    min_cooldown_minutes INTEGER NOT NULL,
    max_irrigation_duration_minutes INTEGER NOT NULL,
    nominal_flow_l_min REAL NOT NULL,
    optimal_air_temp_min_c REAL NOT NULL,
    optimal_air_temp_max_c REAL NOT NULL,
    optimal_rh_min_pct REAL NOT NULL,
    optimal_rh_max_pct REAL NOT NULL,
    paddy_lamina_json TEXT,
    sources_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS growth_stages (
    stage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    stage_key TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    duration_days INTEGER NOT NULL,
    root_depth_m REAL NOT NULL,
    kc_value REAL NOT NULL,
    UNIQUE(crop_id, stage_key)
);

CREATE TABLE IF NOT EXISTS zones (
    zone_id TEXT PRIMARY KEY,
    zone_name TEXT NOT NULL,
    zone_tier TEXT NOT NULL, -- 'HARDWARE_TINKERCAD' or 'VIRTUAL_CROP_PROFILE'
    hardware_pins TEXT,
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    active_stage_key TEXT NOT NULL DEFAULT 'medio',
    operating_mode TEXT NOT NULL DEFAULT 'AUTO_SIMULATED',
    pump_active INTEGER NOT NULL DEFAULT 0,
    sensor_fault INTEGER NOT NULL DEFAULT 0,
    safety_cutoff INTEGER NOT NULL DEFAULT 0,
    last_raw_adc INTEGER,
    current_moisture_pct REAL,
    current_water_lamina_mm REAL,
    last_pump_stop_ts TEXT,
    pump_start_ts TEXT,
    area_m2 REAL NOT NULL DEFAULT 120.0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sensors (
    sensor_id TEXT PRIMARY KEY,
    zone_id TEXT NOT NULL REFERENCES zones(zone_id),
    sensor_type TEXT NOT NULL,
    model_name TEXT NOT NULL,
    analog_pin TEXT,
    calibration_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ONLINE'
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    zone_id TEXT NOT NULL REFERENCES zones(zone_id),
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    source_type TEXT NOT NULL, -- 'tinkercad_serial', 'internal_simulation', 'historical_dataset', 'evaluation_split'
    sensor_id TEXT NOT NULL REFERENCES sensors(sensor_id),
    raw_value INTEGER,
    soil_moisture_pct REAL,
    soil_temperature_c REAL,
    air_temperature_c REAL,
    relative_humidity_pct REAL,
    light_intensity REAL,
    atmospheric_pressure_inhg REAL,
    water_lamina_mm REAL,
    irrigation_state INTEGER NOT NULL DEFAULT 0,
    water_volume_liters REAL NOT NULL DEFAULT 0.0,
    dataset_id TEXT,
    calibration_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_readings_zone_ts ON sensor_readings(zone_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_readings_source ON sensor_readings(source_type);

CREATE TABLE IF NOT EXISTS irrigation_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    zone_id TEXT NOT NULL REFERENCES zones(zone_id),
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    action TEXT NOT NULL, -- 'START', 'STOP', 'SAFETY_CUTOFF', 'DRAINAGE_HOLD'
    trigger_mode TEXT NOT NULL,
    duration_minutes REAL NOT NULL DEFAULT 0.0,
    water_volume_liters REAL NOT NULL DEFAULT 0.0,
    volume_nature TEXT NOT NULL DEFAULT 'simulated', -- 'simulated' or 'estimated'
    reason TEXT NOT NULL,
    arduino_command TEXT
);

CREATE TABLE IF NOT EXISTS irrigation_recommendations (
    rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    zone_id TEXT NOT NULL REFERENCES zones(zone_id),
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    stage_key TEXT NOT NULL,
    current_moisture_pct REAL,
    predicted_1h_pct REAL,
    predicted_6h_pct REAL,
    predicted_12h_pct REAL,
    predicted_24h_pct REAL,
    etc_mm_day REAL NOT NULL,
    decision TEXT NOT NULL, -- 'IRRIGATE', 'HOLD', 'WAIT_COOLDOWN', 'SAFE_SHUTOFF', 'DRAINAGE_PHASE'
    recommended_liters REAL NOT NULL DEFAULT 0.0,
    recommended_duration_min REAL NOT NULL DEFAULT 0.0,
    confidence_note TEXT NOT NULL,
    explanation TEXT NOT NULL,
    model_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    zone_id TEXT NOT NULL REFERENCES zones(zone_id),
    crop_id TEXT NOT NULL REFERENCES crops(crop_id),
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL, -- 'CRITICAL', 'WARNING', 'INFO'
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    cause TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE', -- 'ACTIVE', 'ACKNOWLEDGED', 'RESOLVED'
    detection_source TEXT NOT NULL, -- 'simulated_tinkercad', 'simulated_scenario', 'real_dataset', 'safety_guard'
    is_simulated INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    task_name TEXT NOT NULL,
    description TEXT NOT NULL,
    active_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_versions (
    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL REFERENCES models(model_id),
    version_tag TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    trained_at TEXT NOT NULL,
    dataset_id TEXT NOT NULL,
    val_rmse REAL,
    test_mae REAL,
    test_rmse REAL,
    test_r2 REAL,
    seed INTEGER NOT NULL,
    features_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT NOT NULL,
    year INTEGER NOT NULL,
    repository TEXT NOT NULL,
    doi TEXT NOT NULL,
    url TEXT NOT NULL,
    version TEXT NOT NULL,
    license TEXT NOT NULL,
    downloaded_at TEXT NOT NULL,
    total_records INTEGER,
    sha256_primary TEXT,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    executed_at TEXT NOT NULL,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    task TEXT NOT NULL,
    algorithm TEXT NOT NULL,
    val_rmse REAL NOT NULL,
    test_rmse REAL NOT NULL,
    test_r2 REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL,
    report_type TEXT NOT NULL,
    period_label TEXT NOT NULL,
    data_source_note TEXT NOT NULL,
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_scenarios (
    scenario_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    parameters_json TEXT NOT NULL,
    expected_outcome TEXT NOT NULL
);
"""


def init_db():
    with db_session() as conn:
        conn.executescript(SCHEMA_SQL)
