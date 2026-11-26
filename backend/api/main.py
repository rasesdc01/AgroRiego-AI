"""
AgroRiego AI — FastAPI REST Backend & Dashboard Static Server
Orchestrates SQLite persistence, trained scikit-learn inference, FAO-56 agronomic engine,
deterministic irrigation safety guardrails, CSV/PDF reports, and Tinkercad serial integration.
"""

import csv
import json
import os
import time
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.database.db import db_session
from backend.database.seed import seed_all
from backend.irrigation_engine.decision_engine import (
    calibrate_hw390_adc,
    forecast_moisture_horizons,
    process_zone_telemetry,
)
from backend.services.report_generator import (
    build_report_summary,
    export_readings_csv,
    export_summary_pdf,
)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DASHBOARD_DIR = os.path.join(ROOT, "dashboard")
REPORTS_DIR = os.path.join(ROOT, "ai", "reports")
SOURCES_PATH = os.path.join(ROOT, "datasets", "sources.json")
KNOWLEDGE_CROPS_DIR = os.path.join(ROOT, "knowledge", "crops")

app = FastAPI(title="AgroRiego AI Precision Platform", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_private_network_access_headers(request, call_next):
    if request.method == "OPTIONS":
        resp = Response(status_code=204)
    else:
        resp = await call_next(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Private-Network"] = "true"
    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.on_event("startup")
def on_startup():
    seed_all()


# ---------------------------------------------------------
# PYDANTIC REQUEST SCHEMAS
# ---------------------------------------------------------
class ZoneIngestRequest(BaseModel):
    raw_adc: Optional[int] = Field(default=None, ge=0, le=1023)
    measured_vwc_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    air_temp_c: float = Field(default=25.5, ge=-10.0, le=60.0)
    soil_temp_c: float = Field(default=24.2, ge=-5.0, le=55.0)
    rh_pct: Optional[float] = Field(default=68.0, ge=0.0, le=100.0)
    pressure_inhg: float = Field(default=29.92, ge=25.0, le=32.0)
    water_lamina_mm: Optional[float] = Field(default=None, ge=0.0, le=300.0)
    source_type: str = Field(default="tinkercad_serial")
    simulated_rain_mm: float = Field(default=0.0, ge=0.0, le=200.0)
    simulated_runtime_min: float = Field(default=0.0, ge=0.0, le=300.0)
    tinkercad_pump_active: Optional[bool] = None
    tinkercad_safety_cutoff: Optional[bool] = None
    live_ai_loop: bool = False
    inpage_bridge: bool = False


class ZoneControlRequest(BaseModel):
    operating_mode: Optional[str] = None
    crop_id: Optional[str] = None
    active_stage_key: Optional[str] = None
    manual_pump_state: Optional[bool] = None
    reset_faults: bool = False
    reset_cooldown: bool = False


class ZoneConfigRequest(BaseModel):
    hysteresis_band_pct: Optional[float] = Field(default=None, ge=0.5, le=15.0)
    min_cooldown_minutes: Optional[int] = Field(default=None, ge=1, le=720)
    max_irrigation_duration_minutes: Optional[int] = Field(default=None, ge=1, le=240)
    optimal_min_vwc_pct: Optional[float] = Field(default=None, ge=5.0, le=60.0)


class SimulatorRunRequest(BaseModel):
    zone_id: str = "zone_01"
    crop_id: Optional[str] = None
    stage_key: Optional[str] = None
    raw_adc: Optional[int] = Field(default=None, ge=0, le=1023)
    moisture_pct: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    air_temp_c: float = 26.0
    soil_temp_c: float = 24.5
    rh_pct: float = 65.0
    rain_mm: float = 0.0
    water_lamina_mm: Optional[float] = None
    simulated_runtime_min: float = 0.0
    scenario_preset: Optional[str] = None


class PredictPreviewRequest(BaseModel):
    crop_id: str = "tomate"
    stage_key: str = "medio"
    raw_adc: int = Field(default=620, ge=0, le=1023)
    air_temp_c: float = 27.5
    soil_temp_c: float = 25.0
    rh_pct: float = 62.0
    simulated_rain_mm: float = 0.0


_LAST_INPAGE_BRIDGE_MONO: float = 0.0


# ---------------------------------------------------------
# OVERVIEW & HEALTH
# ---------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "AgroRiego AI",
        "inpage_bridge_active": (time.monotonic() - _LAST_INPAGE_BRIDGE_MONO) < 6.0,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/overview")
def get_overview():
    with db_session() as conn:
        zones = [dict(r) for r in conn.execute(
            """SELECT z.*, c.common_name as crop_name, c.scientific_name, c.irrigation_regime,
                      cp.optimal_min_vwc_pct, cp.optimal_max_vwc_pct, cp.critical_stress_vwc_pct,
                      cp.excess_moisture_vwc_pct, cp.hysteresis_band_pct, gs.kc_value
               FROM zones z
               JOIN crops c ON z.crop_id = c.crop_id
               JOIN crop_profiles cp ON z.crop_id = cp.crop_id
               LEFT JOIN growth_stages gs ON z.crop_id = gs.crop_id AND z.active_stage_key = gs.stage_key
               ORDER BY CASE WHEN z.zone_tier='HARDWARE_TINKERCAD' THEN 0 ELSE 1 END, z.zone_id"""
        ).fetchall()]

        active_alerts = [dict(r) for r in conn.execute(
            "SELECT * FROM alerts WHERE status = 'ACTIVE' ORDER BY alert_id DESC LIMIT 12"
        ).fetchall()]

        recent_recs = [dict(r) for r in conn.execute(
            """SELECT r.*, c.common_name as crop_name
               FROM irrigation_recommendations r
               JOIN crops c ON r.crop_id = c.crop_id
               ORDER BY r.rec_id DESC LIMIT 12"""
        ).fetchall()]

        recent_readings = [dict(r) for r in conn.execute(
            """SELECT timestamp, zone_id, soil_moisture_pct, raw_value, air_temperature_c, source_type
               FROM sensor_readings
               WHERE soil_moisture_pct IS NOT NULL
               ORDER BY reading_id DESC LIMIT 96"""
        ).fetchall()]

        sim_water = conn.execute("SELECT COALESCE(SUM(water_volume_liters), 0) FROM irrigation_events").fetchone()[0]
        total_readings = conn.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
        hist_count = conn.execute("SELECT COUNT(*) FROM sensor_readings WHERE source_type='historical_dataset'").fetchone()[0]
        tinkercad_count = conn.execute("SELECT COUNT(*) FROM sensor_readings WHERE source_type='tinkercad_serial'").fetchone()[0]

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "connection_status": {
            "tinkercad_adapter": "OPERATIONAL_SERIAL_JSON_TWIN",
            "ml_models_loaded": True,
            "active_dataset": "EcoIrrigate (DOI: 10.17632/8x4v7yy3ds.1)",
        },
        "kpis": {
            "hardware_zones_count": sum(1 for z in zones if z["zone_tier"] == "HARDWARE_TINKERCAD"),
            "virtual_crop_profiles_count": sum(1 for z in zones if z["zone_tier"] == "VIRTUAL_CROP_PROFILE"),
            "active_pumps_count": sum(1 for z in zones if z["pump_active"] == 1),
            "active_alerts_count": len(active_alerts),
            "simulated_water_liters": round(float(sim_water), 2),
            "total_readings_stored": total_readings,
            "real_dataset_readings": hist_count,
            "tinkercad_serial_readings": tinkercad_count,
        },
        "zones": zones,
        "active_alerts": active_alerts,
        "recent_recommendations": recent_recs,
        "recent_timeseries": list(reversed(recent_readings)),
    }


# ---------------------------------------------------------
# CROPS (7 SCIENTIFIC PROFILES)
# ---------------------------------------------------------
@app.get("/api/crops")
def list_crops():
    with db_session() as conn:
        crops = [dict(r) for r in conn.execute(
            """SELECT c.*, cp.*
               FROM crops c
               JOIN crop_profiles cp ON c.crop_id = cp.crop_id
               ORDER BY c.common_name"""
        ).fetchall()]
        for c in crops:
            c["sources"] = json.loads(c["sources_json"])
            c["paddy_lamina_params_mm"] = json.loads(c["paddy_lamina_json"]) if c["paddy_lamina_json"] else None
            c["stages"] = [dict(s) for s in conn.execute(
                "SELECT * FROM growth_stages WHERE crop_id = ? ORDER BY stage_order", (c["crop_id"],)
            ).fetchall()]
            c["zone"] = dict(conn.execute(
                "SELECT * FROM zones WHERE zone_tier = 'VIRTUAL_CROP_PROFILE' AND crop_id = ?", (c["crop_id"],)
            ).fetchone() or {})
    return {"crops": crops}


@app.get("/api/crops/{crop_id}")
def get_crop_detail(crop_id: str):
    with db_session() as conn:
        c = conn.execute(
            """SELECT c.*, cp.* FROM crops c JOIN crop_profiles cp ON c.crop_id = cp.crop_id WHERE c.crop_id = ?""",
            (crop_id,),
        ).fetchone()
        if not c:
            raise HTTPException(status_code=404, detail="Crop not found")
        out = dict(c)
        out["sources"] = json.loads(out["sources_json"])
        out["paddy_lamina_params_mm"] = json.loads(out["paddy_lamina_json"]) if out["paddy_lamina_json"] else None
        out["stages"] = [dict(s) for s in conn.execute(
            "SELECT * FROM growth_stages WHERE crop_id = ? ORDER BY stage_order", (crop_id,)
        ).fetchall()]
        out["recent_recommendations"] = [dict(r) for r in conn.execute(
            "SELECT * FROM irrigation_recommendations WHERE crop_id = ? ORDER BY rec_id DESC LIMIT 5", (crop_id,)
        ).fetchall()]
    md_path = os.path.join(KNOWLEDGE_CROPS_DIR, f"{crop_id}.md")
    if os.path.exists(md_path):
        with open(md_path, encoding="utf-8") as f:
            out["scientific_markdown"] = f.read()
    return out


# ---------------------------------------------------------
# ZONES & END-TO-END TINKERCAD INGESTION
# ---------------------------------------------------------
@app.get("/api/zones")
def list_zones():
    with db_session() as conn:
        zones = [dict(r) for r in conn.execute(
            """SELECT z.*, c.common_name as crop_name, c.scientific_name, c.irrigation_regime,
                      cp.optimal_min_vwc_pct, cp.optimal_max_vwc_pct, cp.critical_stress_vwc_pct,
                      cp.excess_moisture_vwc_pct, cp.hysteresis_band_pct, cp.min_cooldown_minutes,
                      cp.max_irrigation_duration_minutes, gs.kc_value
               FROM zones z
               JOIN crops c ON z.crop_id = c.crop_id
               JOIN crop_profiles cp ON z.crop_id = cp.crop_id
               LEFT JOIN growth_stages gs ON z.crop_id = gs.crop_id AND z.active_stage_key = gs.stage_key
               ORDER BY CASE WHEN z.zone_tier='HARDWARE_TINKERCAD' THEN 0 ELSE 1 END, z.zone_id"""
        ).fetchall()]
        for z in zones:
            z["history"] = [dict(h) for h in reversed(conn.execute(
                "SELECT timestamp, soil_moisture_pct, raw_value, irrigation_state, source_type FROM sensor_readings WHERE zone_id = ? ORDER BY reading_id DESC LIMIT 30",
                (z["zone_id"],),
            ).fetchall())]
    return {"zones": zones}


@app.post("/api/zones/{zone_id}/ingest")
def ingest_zone_reading(zone_id: str, req: ZoneIngestRequest):
    global _LAST_INPAGE_BRIDGE_MONO
    if req.inpage_bridge:
        _LAST_INPAGE_BRIDGE_MONO = time.monotonic()
    try:
        result = process_zone_telemetry(
            zone_id=zone_id,
            raw_adc=req.raw_adc,
            measured_vwc_pct=req.measured_vwc_pct,
            air_temp_c=req.air_temp_c,
            soil_temp_c=req.soil_temp_c,
            rh_pct=req.rh_pct,
            pressure_inhg=req.pressure_inhg,
            water_lamina_mm=req.water_lamina_mm,
            source_type=req.source_type,
            simulated_rain_mm=req.simulated_rain_mm,
            simulated_runtime_min=req.simulated_runtime_min,
            tinkercad_pump_active=req.tinkercad_pump_active,
            tinkercad_safety_cutoff=req.tinkercad_safety_cutoff,
            live_ai_loop=req.live_ai_loop,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/zones/{zone_id}/control")
def control_zone(zone_id: str, req: ZoneControlRequest):
    now_iso = datetime.now().isoformat(timespec="seconds")
    with db_session() as conn:
        z = conn.execute("SELECT * FROM zones WHERE zone_id = ?", (zone_id,)).fetchone()
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")
        if req.operating_mode:
            valid_modes = {"MONITORING", "RECOMMENDATION", "AUTO_SIMULATED", "MANUAL_SIMULATED"}
            if req.operating_mode not in valid_modes:
                raise HTTPException(status_code=400, detail="Invalid operating_mode")
            conn.execute("UPDATE zones SET operating_mode = ?, updated_at = ? WHERE zone_id = ?", (req.operating_mode, now_iso, zone_id))
        if req.crop_id:
            crop = conn.execute("SELECT crop_id FROM crops WHERE crop_id = ?", (req.crop_id,)).fetchone()
            if not crop:
                raise HTTPException(status_code=400, detail="Invalid crop_id")
            conn.execute("UPDATE zones SET crop_id = ?, updated_at = ? WHERE zone_id = ?", (req.crop_id, now_iso, zone_id))
        if req.active_stage_key:
            conn.execute("UPDATE zones SET active_stage_key = ?, updated_at = ? WHERE zone_id = ?", (req.active_stage_key, now_iso, zone_id))
        if req.reset_faults:
            conn.execute("UPDATE zones SET sensor_fault = 0, safety_cutoff = 0, updated_at = ? WHERE zone_id = ?", (now_iso, zone_id))
        if req.reset_cooldown:
            conn.execute("UPDATE zones SET pump_active = 0, last_pump_stop_ts = NULL, pump_start_ts = NULL, updated_at = ? WHERE zone_id = ?", (now_iso, zone_id))

    if req.manual_pump_state is not None:
        return process_zone_telemetry(
            zone_id=zone_id,
            raw_adc=z["last_raw_adc"],
            measured_vwc_pct=z["current_moisture_pct"],
            source_type="internal_simulation",
            manual_pump_override=req.manual_pump_state,
        )

    with db_session() as conn:
        updated = dict(conn.execute("SELECT * FROM zones WHERE zone_id = ?", (zone_id,)).fetchone())
    return {"status": "updated", "zone": updated}


@app.post("/api/zones/{zone_id}/config")
def update_zone_crop_config(zone_id: str, req: ZoneConfigRequest):
    with db_session() as conn:
        z = conn.execute("SELECT crop_id FROM zones WHERE zone_id = ?", (zone_id,)).fetchone()
        if not z:
            raise HTTPException(status_code=404, detail="Zone not found")
        cid = z["crop_id"]
        if req.hysteresis_band_pct is not None:
            conn.execute("UPDATE crop_profiles SET hysteresis_band_pct = ? WHERE crop_id = ?", (req.hysteresis_band_pct, cid))
        if req.min_cooldown_minutes is not None:
            conn.execute("UPDATE crop_profiles SET min_cooldown_minutes = ? WHERE crop_id = ?", (req.min_cooldown_minutes, cid))
        if req.max_irrigation_duration_minutes is not None:
            conn.execute("UPDATE crop_profiles SET max_irrigation_duration_minutes = ? WHERE crop_id = ?", (req.max_irrigation_duration_minutes, cid))
        if req.optimal_min_vwc_pct is not None:
            conn.execute("UPDATE crop_profiles SET optimal_min_vwc_pct = ? WHERE crop_id = ?", (req.optimal_min_vwc_pct, cid))
    return {"status": "saved", "zone_id": zone_id, "crop_id": cid}


# ---------------------------------------------------------
# AI MODELS, REAL METRICS & EXPLAINABLE PREDICTION
# ---------------------------------------------------------
@app.get("/api/ai/metrics")
def get_ai_metrics():
    metrics_path = os.path.join(REPORTS_DIR, "metrics.json")
    comp_path = os.path.join(REPORTS_DIR, "model_comparison.csv")
    hist_path = os.path.join(REPORTS_DIR, "training_history.json")
    if not os.path.exists(metrics_path):
        raise HTTPException(status_code=404, detail="metrics.json not generated yet")
    with open(metrics_path, encoding="utf-8") as f:
        metrics = json.load(f)
    comparison = []
    if os.path.exists(comp_path):
        with open(comp_path, encoding="utf-8") as f:
            comparison = list(csv.DictReader(f))
    history = []
    if os.path.exists(hist_path):
        with open(hist_path, encoding="utf-8") as f:
            history = json.load(f)
    return {
        "metrics": metrics,
        "comparison": comparison,
        "history": history,
        "plots": [
            "/ai-reports/horizon_comparison.png",
            "/ai-reports/prediction_vs_actual.png",
            "/ai-reports/feature_importance.png",
            "/ai-reports/residuals_analysis.png",
            "/ai-reports/moisture_evolution.png",
        ],
    }


@app.post("/api/ai/predict")
def preview_ai_prediction(req: PredictPreviewRequest):
    with db_session() as conn:
        crop = conn.execute("SELECT * FROM crops WHERE crop_id = ?", (req.crop_id,)).fetchone()
        profile = conn.execute("SELECT * FROM crop_profiles WHERE crop_id = ?", (req.crop_id,)).fetchone()
        stage = conn.execute("SELECT * FROM growth_stages WHERE crop_id = ? AND stage_key = ?", (req.crop_id, req.stage_key)).fetchone()
        if not crop or not profile:
            raise HTTPException(status_code=404, detail="Crop profile not found")

    ecoirr_vwc, scaled_vwc = calibrate_hw390_adc(req.raw_adc, soil_temp_c=req.soil_temp_c, air_temp_c=req.air_temp_c)
    kc = float(stage["kc_value"]) if stage else 1.0
    etc = round(kc * float(profile["et0_reference_mm_day"]), 2)
    fc = forecast_moisture_horizons(
        current_vwc_pct=scaled_vwc,
        raw_adc=req.raw_adc,
        air_temp_c=req.air_temp_c,
        soil_temp_c=req.soil_temp_c,
        rh_pct=req.rh_pct,
        pressure_inhg=29.92,
        etc_mm_day=etc,
        simulated_rain_mm=req.simulated_rain_mm,
    )
    opt_min = float(profile["optimal_min_vwc_pct"])
    action = "REGAR" if (scaled_vwc < opt_min or fc["predictions"]["6h"] < opt_min) else "MANTENER"
    return {
        "crop_name": crop["common_name"],
        "stage_key": req.stage_key,
        "kc": kc,
        "etc_mm_day": etc,
        "calibrated_ecoirrigate_vwc_pct": ecoirr_vwc,
        "agronomic_scaled_vwc_pct": scaled_vwc,
        "optimal_min_vwc_pct": opt_min,
        "recommended_action": action,
        "forecasts": fc["predictions"],
        "ml_raw_deltas": fc["ml_raw_deltas"],
        "drivers": fc["drivers"],
        "disclaimer": "Predicción híbrida sobre modelos entrenados en EcoIrrigate (CC BY 4.0) combinados con balance FAO-56. No sustituye verificación agronómica en campo.",
    }


# ---------------------------------------------------------
# ALERTS & IRRIGATION HISTORY
# ---------------------------------------------------------
@app.get("/api/alerts")
def list_alerts(
    severity: str = Query(default="all"),
    status: str = Query(default="all"),
    zone_id: str = Query(default="all"),
    origin: str = Query(default="all"),
):
    clauses, params = [], []
    if severity != "all":
        clauses.append("a.severity = ?")
        params.append(severity)
    if status != "all":
        clauses.append("a.status = ?")
        params.append(status)
    if zone_id != "all":
        clauses.append("a.zone_id = ?")
        params.append(zone_id)
    if origin == "real":
        clauses.append("a.is_simulated = 0")
    elif origin == "simulated":
        clauses.append("a.is_simulated = 1")
    w_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    with db_session() as conn:
        rows = [dict(r) for r in conn.execute(
            f"""SELECT a.*, c.common_name as crop_name
                FROM alerts a
                JOIN crops c ON a.crop_id = c.crop_id
                {w_sql}
                ORDER BY a.alert_id DESC LIMIT 100""",
            params,
        ).fetchall()]
    return {"alerts": rows}


@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, resolve: bool = False):
    new_status = "RESOLVED" if resolve else "ACKNOWLEDGED"
    with db_session() as conn:
        cur = conn.execute("UPDATE alerts SET status = ? WHERE alert_id = ?", (new_status, alert_id))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
    return {"alert_id": alert_id, "status": new_status}


@app.get("/api/irrigation/events")
def list_irrigation_events(zone_id: str = Query(default="all")):
    with db_session() as conn:
        if zone_id != "all":
            rows = [dict(r) for r in conn.execute(
                "SELECT e.*, c.common_name as crop_name FROM irrigation_events e JOIN crops c ON e.crop_id = c.crop_id WHERE e.zone_id = ? ORDER BY e.event_id DESC LIMIT 60",
                (zone_id,),
            ).fetchall()]
        else:
            rows = [dict(r) for r in conn.execute(
                "SELECT e.*, c.common_name as crop_name FROM irrigation_events e JOIN crops c ON e.crop_id = c.crop_id ORDER BY e.event_id DESC LIMIT 60"
            ).fetchall()]
        recs = [dict(r) for r in conn.execute(
            "SELECT r.*, c.common_name as crop_name FROM irrigation_recommendations r JOIN crops c ON r.crop_id = c.crop_id ORDER BY r.rec_id DESC LIMIT 30"
        ).fetchall()]
    return {"events": rows, "recommendations": recs}


# ---------------------------------------------------------
# INTERACTIVE SIMULATOR & SCENARIOS
# ---------------------------------------------------------
@app.get("/api/simulator/scenarios")
def list_scenarios():
    with db_session() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM simulation_scenarios").fetchall()]
        for r in rows:
            r["parameters"] = json.loads(r["parameters_json"])
    return {"scenarios": rows}


@app.post("/api/simulator/run")
def run_simulation(req: SimulatorRunRequest):
    if req.crop_id or req.stage_key:
        control_zone(req.zone_id, ZoneControlRequest(crop_id=req.crop_id, active_stage_key=req.stage_key, reset_faults=True))
    return process_zone_telemetry(
        zone_id=req.zone_id,
        raw_adc=req.raw_adc,
        measured_vwc_pct=req.moisture_pct,
        air_temp_c=req.air_temp_c,
        soil_temp_c=req.soil_temp_c,
        rh_pct=req.rh_pct,
        water_lamina_mm=req.water_lamina_mm,
        source_type="internal_simulation",
        simulated_rain_mm=req.rain_mm,
        simulated_runtime_min=req.simulated_runtime_min,
    )


# ---------------------------------------------------------
# REPORTS (SUMMARY, CSV, PDF)
# ---------------------------------------------------------
@app.get("/api/reports/summary")
def get_report_summary(zone_id: str = Query(default="all"), crop_id: str = Query(default="all")):
    return build_report_summary(zone_id=zone_id, crop_id=crop_id)


@app.get("/api/reports/export/csv")
def download_csv(zone_id: str = Query(default="all"), source_type: str = Query(default="all")):
    csv_text = export_readings_csv(zone_id=zone_id, source_type=source_type)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agroriego_telemetry_report.csv"'},
    )


@app.get("/api/reports/export/pdf")
def download_pdf(zone_id: str = Query(default="all"), crop_id: str = Query(default="all")):
    pdf_bytes = export_summary_pdf(zone_id=zone_id, crop_id=crop_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="AgroRiego_AI_Water_Efficiency_Report.pdf"'},
    )


# ---------------------------------------------------------
# DATASETS & APA 7 REFERENCES
# ---------------------------------------------------------
@app.get("/api/datasets")
def get_datasets():
    with db_session() as conn:
        ds = [dict(r) for r in conn.execute("SELECT * FROM datasets").fetchall()]
    sources_detail = {}
    if os.path.exists(SOURCES_PATH):
        with open(SOURCES_PATH, encoding="utf-8") as f:
            sources_detail = json.load(f)
    return {"datasets": ds, "sources_manifest": sources_detail}


@app.get("/api/references")
def get_references():
    apa_path = os.path.join(ROOT, "documentation", "APA_REFERENCES.md")
    bib_path = os.path.join(ROOT, "documentation", "references.bib")
    apa_text = open(apa_path, encoding="utf-8").read() if os.path.exists(apa_path) else ""
    bib_text = open(bib_path, encoding="utf-8").read() if os.path.exists(bib_path) else ""
    return {"apa7": apa_text, "bibtex": bib_text}


# ---------------------------------------------------------
# STATIC ASSETS & DASHBOARD ENTRYPOINT
# ---------------------------------------------------------
if os.path.exists(REPORTS_DIR):
    app.mount("/ai-reports", StaticFiles(directory=REPORTS_DIR), name="ai-reports")
if os.path.exists(os.path.join(DASHBOARD_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(DASHBOARD_DIR, "assets")), name="assets")


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    index_path = os.path.join(DASHBOARD_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>AgroRiego AI Backend Running</h1>")
