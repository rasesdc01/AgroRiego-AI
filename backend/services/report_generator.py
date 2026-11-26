"""
AgroRiego AI — CSV & Academic PDF Report Generator (using reportlab)
Explicitly distinguishes simulated water volume, estimated demand, and real historical measurements.
"""

import csv
import io
import json
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from backend.database.db import db_session


def build_report_summary(zone_id: str = None, crop_id: str = None) -> dict:
    with db_session() as conn:
        where_clauses = []
        params = []
        if zone_id and zone_id != "all":
            where_clauses.append("zone_id = ?")
            params.append(zone_id)
        if crop_id and crop_id != "all":
            where_clauses.append("crop_id = ?")
            params.append(crop_id)
        w_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        events = conn.execute(f"SELECT * FROM irrigation_events{w_sql} ORDER BY event_id DESC LIMIT 200", params).fetchall()
        readings = conn.execute(f"SELECT source_type, COUNT(*) as cnt, AVG(soil_moisture_pct) as avg_vwc FROM sensor_readings{w_sql} GROUP BY source_type", params).fetchall()
        zone_stats = conn.execute(
            """SELECT z.zone_id, z.zone_name, z.zone_tier, c.common_name as crop_name,
                      z.current_moisture_pct, z.current_water_lamina_mm, z.pump_active,
                      COALESCE(SUM(e.water_volume_liters), 0) as total_sim_liters,
                      COUNT(e.event_id) as event_count
               FROM zones z
               JOIN crops c ON z.crop_id = c.crop_id
               LEFT JOIN irrigation_events e ON z.zone_id = e.zone_id
               GROUP BY z.zone_id"""
        ).fetchall()

        total_sim_liters = round(sum(float(e["water_volume_liters"]) for e in events), 2)
        total_events = len(events)
        active_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE status = 'ACTIVE'").fetchone()[0]

        summary = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "filters": {"zone_id": zone_id or "all", "crop_id": crop_id or "all"},
            "kpis": {
                "total_simulated_water_liters": total_sim_liters,
                "total_irrigation_events": total_events,
                "active_alerts": active_alerts,
                "volume_nature_notice": "Los volúmenes de agua corresponden a simulaciones y estimaciones FAO-56; no representan caudalímetros físicos instalados.",
            },
            "readings_by_source": [dict(r) for r in readings],
            "zones": [dict(z) for z in zone_stats],
            "recent_events": [dict(e) for e in events[:30]],
        }
        conn.execute(
            "INSERT INTO reports (generated_at, report_type, period_label, data_source_note, summary_json) VALUES (?, 'WATER_EFFICIENCY', 'Actual acumulado', ?, ?)",
            (summary["generated_at"], summary["kpis"]["volume_nature_notice"], json.dumps(summary)),
        )
        return summary


def export_readings_csv(zone_id: str = None, source_type: str = None) -> str:
    with db_session() as conn:
        clauses, params = [], []
        if zone_id and zone_id != "all":
            clauses.append("zone_id = ?")
            params.append(zone_id)
        if source_type and source_type != "all":
            clauses.append("source_type = ?")
            params.append(source_type)
        w_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"""SELECT reading_id, timestamp, zone_id, crop_id, source_type, sensor_id,
                       raw_value, soil_moisture_pct, soil_temperature_c, air_temperature_c,
                       relative_humidity_pct, water_lamina_mm, irrigation_state, water_volume_liters,
                       dataset_id, calibration_version
                FROM sensor_readings{w_sql} ORDER BY reading_id DESC LIMIT 1000""",
            params,
        ).fetchall()

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "reading_id", "timestamp", "zone_id", "crop_id", "source_type", "sensor_id",
            "raw_value_adc", "soil_moisture_vwc_pct", "soil_temperature_c", "air_temperature_c",
            "relative_humidity_pct", "water_lamina_mm", "irrigation_state", "simulated_water_volume_liters",
            "dataset_id", "calibration_version"
        ])
        for r in rows:
            writer.writerow([r[k] for k in r.keys()])
        return buf.getvalue()


def export_summary_pdf(zone_id: str = None, crop_id: str = None) -> bytes:
    summary = build_report_summary(zone_id=zone_id, crop_id=crop_id)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleAgro", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#0F4C3A"))
    h2_style = ParagraphStyle("H2Agro", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#1E3A5F"))
    body_style = styles["BodyText"]

    story = [
        Paragraph("AgroRiego AI — Reporte de Eficiencia Hídrica y Telemetría", title_style),
        Spacer(1, 6),
        Paragraph(f"Generado: {summary['generated_at']} | Filtros: zona={summary['filters']['zone_id']}, cultivo={summary['filters']['crop_id']}", body_style),
        Spacer(1, 8),
        Paragraph(f"<b>Aviso de Trazabilidad:</b> {summary['kpis']['volume_nature_notice']}", body_style),
        Spacer(1, 14),
        Paragraph("1. Resumen Operativo", h2_style),
        Paragraph(f"Volumen total simulado: <b>{summary['kpis']['total_simulated_water_liters']} L</b> | Eventos de riego registrados: <b>{summary['kpis']['total_irrigation_events']}</b> | Alertas activas: <b>{summary['kpis']['active_alerts']}</b>", body_style),
        Spacer(1, 14),
        Paragraph("2. Estado por Zona (Hardware Tinkercad vs. Perfiles Virtuales)", h2_style),
    ]

    z_data = [["Zona", "Tipo", "Cultivo", "Humedad (% VWC)", "Vol. Sim (L)"]]
    for z in summary["zones"]:
        vwc_str = f"{z['current_moisture_pct']:.1f}%" if z["current_moisture_pct"] is not None else "FAULT/N/A"
        z_data.append([z["zone_id"], "Tinkercad HW" if z["zone_tier"] == "HARDWARE_TINKERCAD" else "Virtual", z["crop_name"], vwc_str, f"{round(float(z['total_sim_liters']), 1)}"])

    t = Table(z_data, colWidths=[95, 85, 95, 100, 95])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0F4C3A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))
    story.append(Paragraph("3. Procedencia de Datos en Base de Datos", h2_style))
    for rs in summary["readings_by_source"]:
        avg_v = f"{rs['avg_vwc']:.2f}%" if rs["avg_vwc"] is not None else "N/A"
        story.append(Paragraph(f"- Origen <b>{rs['source_type']}</b>: {rs['cnt']} registros (promedio VWC: {avg_v})", body_style))

    doc.build(story)
    return buf.getvalue()
