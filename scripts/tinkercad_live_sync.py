"""
AgroRiego AI — Native Headless Windows Tinkercad Serial Bridge
Reads live JSON telemetry from Tinkercad's Monitor en Serie in Google Chrome without
stealing window focus or mouse cursor, runs real ML + FAO-56 + Safety decisioning in
FastAPI, and keeps 1:1 closed-loop pump telemetry synchronized with the Dashboard.
"""

import json
import shutil
import subprocess
import time
from typing import Any, Dict, Optional

import requests

API_BASE = "http://127.0.0.1:8000"


def find_tinkercad_window_id() -> Optional[str]:
    """Return the window ID of a visible Chrome window currently showing Tinkercad."""
    if not shutil.which("agent-desktop"):
        return None
    proc = subprocess.run(
        ["agent-desktop", "list-windows"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None

    for win in payload.get("data", []):
        if (win.get("app_name") or "").lower() != "chrome.exe":
            continue
        title = (win.get("title") or "").lower()
        if "tinkercad" in title or "agroriego-ai-dualzone" in title:
            return win.get("id")
    return None


def poll_tinkercad_once(
    last_sent_by_zone: Dict[str, Any],
    last_cmd_ts_by_zone: Optional[Dict[str, float]] = None,
    last_ai_res_by_zone: Optional[Dict[str, Dict[str, Any]]] = None,
    bridge_state: Optional[Dict[str, Any]] = None,
) -> int:
    """Query Tinkercad's Serial Monitor headlessly and ingest frames into FastAPI."""
    del last_cmd_ts_by_zone  # Command actuation runs via inpage DOM bridge when active
    try:
        h = requests.get(f"{API_BASE}/api/health", timeout=1.5).json()
        if h.get("inpage_bridge_active"):
            return 0
    except Exception:
        pass
    if last_ai_res_by_zone is None:
        last_ai_res_by_zone = {}
    if bridge_state is None:
        bridge_state = {}

    wid = bridge_state.get("wid")
    if not wid:
        wid = find_tinkercad_window_id()
        if not wid:
            return 0
        bridge_state["wid"] = wid

    proc = subprocess.run(
        [
            "agent-desktop",
            "find",
            "--window-id",
            wid,
            "--role",
            "statictext",
            "--text",
            "timestamp_ms",
            "--timeout-ms",
            "4000",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    if proc.returncode != 0:
        bridge_state["wid"] = None
        return 0
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        bridge_state["wid"] = None
        return 0

    matches = data.get("data", {}).get("matches", [])
    if not matches:
        bridge_state["empty_polls"] = int(bridge_state.get("empty_polls", 0)) + 1
        if bridge_state["empty_polls"] >= 4:
            bridge_state["wid"] = None
            bridge_state["empty_polls"] = 0
        return 0
    bridge_state["empty_polls"] = 0

    latest_by_zone: Dict[str, Dict[str, Any]] = {}
    for m in matches:
        txt = m.get("name") or ""
        if "timestamp_ms" not in txt:
            continue
        for raw_line in txt.splitlines():
            line = raw_line.strip()
            start = line.find("{")
            end = line.rfind("}")
            if start == -1 or end <= start:
                continue
            try:
                frame = json.loads(line[start : end + 1])
            except json.JSONDecodeError:
                continue
            zone = frame.get("zone")
            raw = frame.get("raw")
            ts = frame.get("timestamp_ms")
            if zone in ("zone_01", "zone_02") and isinstance(raw, (int, float)):
                ts_num = int(ts) if isinstance(ts, (int, float)) else 0
                prev_best = latest_by_zone.get(zone)
                if prev_best is None or ts_num >= prev_best["_ts_num"]:
                    frame_copy = dict(frame)
                    frame_copy["_ts_num"] = ts_num
                    latest_by_zone[zone] = frame_copy

    sent = 0
    for zone, frame in latest_by_zone.items():
        raw_val = int(frame["raw"])
        pump_val = bool(frame.get("pump"))
        fault_val = bool(frame.get("fault"))
        cutoff_val = bool(frame.get("safety_cutoff"))
        moisture_val = frame.get("moisture_pct")
        sig = (frame.get("timestamp_ms"), raw_val, pump_val, fault_val, cutoff_val)

        if last_sent_by_zone.get(zone) != sig:
            last_sent_by_zone[zone] = sig
            ingest_payload: Dict[str, Any] = {
                "raw_adc": raw_val,
                "air_temp_c": 27.5,
                "soil_temp_c": 24.8,
                "rh_pct": 62.0,
                "source_type": "tinkercad_serial",
                "tinkercad_pump_active": pump_val,
                "tinkercad_safety_cutoff": cutoff_val,
                "live_ai_loop": True,
            }
            if isinstance(moisture_val, (int, float)) and moisture_val >= 0:
                ingest_payload["measured_vwc_pct"] = float(moisture_val)
            r = requests.post(
                f"{API_BASE}/api/zones/{zone}/ingest",
                json=ingest_payload,
                timeout=5,
            )
            res = r.json()
            last_ai_res_by_zone[zone] = res
            print(
                f"[Tinkercad->AI] {zone} raw={raw_val} -> {res.get('soil_moisture_pct')}% | "
                f"{res.get('decision')} | pump={res.get('pump_active')} | cmd={res.get('arduino_command')}"
            )
            sent += 1

    return sent


def run_sync_loop(stop_event=None, poll_interval_s: float = 0.6) -> None:
    """Poll Chrome Tinkercad Serial Monitor headlessly and ingest telemetry."""
    if not shutil.which("agent-desktop"):
        print(
            "AgroRiego AI: usa arduino/circuit/tinkercad_live_bridge.js en la consola "
            "del navegador de Tinkercad para sincronización bidireccional 100% IA."
        )
        return
    last_sent_by_zone: Dict[str, Any] = {}
    last_cmd_ts_by_zone: Dict[str, float] = {}
    last_ai_res_by_zone: Dict[str, Dict[str, Any]] = {}
    bridge_state: Dict[str, Any] = {}
    print("AgroRiego AI Headless Tinkercad Bridge listening (Ctrl+C to stop)...")
    while stop_event is None or not stop_event.is_set():
        try:
            poll_tinkercad_once(
                last_sent_by_zone,
                last_cmd_ts_by_zone,
                last_ai_res_by_zone,
                bridge_state=bridge_state,
            )
        except KeyboardInterrupt:
            break
        except Exception as exc:
            bridge_state["wid"] = None
            print("Bridge warning:", exc)
        if stop_event is not None:
            if stop_event.wait(poll_interval_s):
                break
        else:
            time.sleep(poll_interval_s)


if __name__ == "__main__":
    run_sync_loop()
