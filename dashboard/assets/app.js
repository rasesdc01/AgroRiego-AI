/* AgroRiego AI — Dashboard Client Controller */

const STATE = {
  overview: null,
  crops: [],
  zones: [],
  activeCropId: 'tomate',
  activeView: 'overview',
  activeSubTabs: {
    irrigation: 'sub-irrigation-control',
    ai: 'sub-ai-predict',
    alerts: 'sub-alerts-list'
  },
  visibleAlertIds: [],
  lastTinkercadCount: null,
  lastLiveSig: null,
  charts: {},
  serialLog: []
};

const VIEW_META = {
  overview: ['Resumen en Vivo', 'Estado actual de tus 2 zonas conectadas a Tinkercad y la IA'],
  tinkercad: ['Tinkercad en Vivo', 'Circuito Arduino Dual-Zone, control de sensores A0/A1 y pruebas rápidas'],
  crops: ['Cultivos (7 Perfiles)', 'Parámetros agronómicos FAO-56, INEC e INTA para cada cultivo'],
  irrigation: ['Riego y Simulador', 'Control de bombas, simulador de escenarios y configuración por zona'],
  ai: ['Inteligencia Artificial', 'Entrenamiento reproducible sobre EcoIrrigate (DOI: 10.17632/8x4v7yy3ds.1)'],
  alerts: ['Alertas y Reportes', 'Avisos activos deduplicados y descarga de reportes CSV / PDF'],
  datasets: ['Datasets, SHA-256 y Referencias APA 7', 'Trazabilidad bibliográfica completa para trabajo académico UIA']
};

const LEGACY_VIEW_MAP = {
  simulator: ['irrigation', 'sub-irrigation-sim'],
  settings: ['irrigation', 'sub-irrigation-settings'],
  reports: ['alerts', 'sub-alerts-reports']
};

async function api(url, opts = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...opts
  });
  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`HTTP ${res.status}: ${errText}`);
  }
  return res.json();
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

/* ==================== PLAIN SPANISH HELPERS ==================== */
function formatDecision(code) {
  const map = {
    IRRIGATE: 'Regar ahora',
    HOLD: 'Sin riego necesario',
    SAFE_SHUTOFF: 'Apagado por seguridad',
    WAIT_COOLDOWN: 'En pausa (enfriamiento)',
    DRAINAGE_PHASE: 'Fase de drenaje'
  };
  return map[code] || code || 'En espera';
}

function formatMode(mode) {
  const map = {
    AUTO_SIMULATED: 'Automático',
    MANUAL_SIMULATED: 'Manual',
    MONITORING: 'Solo lectura',
    RECOMMENDATION: 'Solo sugerencias'
  };
  return map[mode] || mode || 'Automático';
}

function getZoneStatus(z) {
  if (z.sensor_fault === 1 || z.safety_cutoff === 1) {
    return { label: 'Fallo de sensor', cls: 'danger' };
  }
  if (z.pump_active === 1) {
    return { label: 'Regando ahora', cls: 'water' };
  }
  const vwc = z.current_moisture_pct;
  if (vwc != null && vwc < z.optimal_min_vwc_pct) {
    return { label: 'Suelo seco', cls: 'warn' };
  }
  if (vwc != null && z.excess_moisture_vwc_pct != null && vwc >= z.excess_moisture_vwc_pct) {
    return { label: 'Mucha humedad', cls: 'warn' };
  }
  return { label: 'Humedad óptima', cls: 'ok' };
}

function deduplicateAlerts(alerts) {
  const grouped = new Map();
  for (const a of alerts || []) {
    const key = `${a.zone_id}::${a.alert_type}`;
    if (!grouped.has(key)) {
      grouped.set(key, { ...a, _count: 1 });
    } else {
      grouped.get(key)._count += 1;
    }
  }
  return Array.from(grouped.values());
}

/* ==================== NAVIGATION & SUB-TABS ==================== */
function switchView(viewId) {
  if (LEGACY_VIEW_MAP[viewId]) {
    const [parent, sub] = LEGACY_VIEW_MAP[viewId];
    STATE.activeSubTabs[parent] = sub;
    viewId = parent;
  }

  STATE.activeView = viewId;
  document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => {
    const isMatch = b.dataset.view === viewId;
    b.classList.toggle('active', isMatch);
    if (isMatch) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });

  const target = document.getElementById(`view-${viewId}`);
  if (target) target.classList.add('active');

  const [t, sub] = VIEW_META[viewId] || ['AgroRiego AI', ''];
  document.getElementById('viewTitle').textContent = t;
  document.getElementById('viewSubtitle').textContent = sub;
  document.getElementById('sidebar').classList.remove('open');

  if (viewId === 'irrigation' || viewId === 'ai' || viewId === 'alerts') {
    switchSubTab(viewId, STATE.activeSubTabs[viewId]);
  } else if (viewId === 'overview') {
    loadOverview();
  } else if (viewId === 'crops') {
    loadCrops();
  } else if (viewId === 'tinkercad') {
    loadTinkercad();
  } else if (viewId === 'datasets') {
    loadDatasets();
  }
}

function switchSubTab(viewId, subId) {
  STATE.activeSubTabs[viewId] = subId;
  const panel = document.getElementById(`view-${viewId}`);
  if (!panel) return;

  panel.querySelectorAll('.sub-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.sub === subId);
  });
  panel.querySelectorAll('.sub-panel').forEach(sp => {
    sp.classList.toggle('active', sp.id === subId);
  });

  if (subId === 'sub-irrigation-control') loadIrrigation();
  else if (subId === 'sub-irrigation-sim') loadSimulatorOptions();
  else if (subId === 'sub-irrigation-settings') loadSettingsOptions();
  else if (subId === 'sub-ai-predict' || subId === 'sub-ai-metrics') loadAiLab();
  else if (subId === 'sub-alerts-list') loadAlerts();
  else if (subId === 'sub-alerts-reports') loadReports();
}

function refreshActiveView() {
  switchView(STATE.activeView);
}

function renderChart(canvasId, config) {
  const el = document.getElementById(canvasId);
  if (!el || typeof Chart === 'undefined') return;
  if (STATE.charts[canvasId]) STATE.charts[canvasId].destroy();
  STATE.charts[canvasId] = new Chart(el.getContext('2d'), config);
}

function updateLivePill(isPulse = false) {
  const pill = document.getElementById('liveStatusPill');
  if (!pill) return;
  const now = new Date().toLocaleTimeString('es-CR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  pill.innerHTML = `<span class="dot"></span>En vivo · Tinkercad (${now})`;
  if (isPulse) {
    pill.classList.remove('hydro');
    pill.classList.add('botanical');
    setTimeout(() => {
      pill.classList.remove('botanical');
      pill.classList.add('hydro');
    }, 1200);
  }
}

/* ==================== 1. OVERVIEW (RESUMEN) ==================== */
async function loadOverview() {
  const data = await api('/api/overview');
  STATE.overview = data;
  STATE.zones = data.zones;
  const k = data.kpis;
  const uniqueAlerts = deduplicateAlerts(data.active_alerts);
  document.getElementById('navAlertBadge').textContent = uniqueAlerts.length;

  const hwZones = data.zones.filter(z => z.zone_tier === 'HARDWARE_TINKERCAD');
  const virtZones = data.zones.filter(z => z.zone_tier !== 'HARDWARE_TINKERCAD');

  const latestRecByZone = {};
  for (const r of data.recent_recommendations || []) {
    if (!latestRecByZone[r.zone_id]) latestRecByZone[r.zone_id] = r;
  }

  document.getElementById('overviewHwZones').innerHTML = hwZones
    .map((z, idx) => renderLiveZoneCard(z, latestRecByZone[z.zone_id], idx))
    .join('');

  document.getElementById('overviewVirtZones').innerHTML = virtZones
    .map(z => renderCompactVirtualCard(z))
    .join('');

  document.getElementById('overviewKpis').innerHTML = `
    <div class="kpi-cell">
      <div class="kpi-label">Bombas Encendidas</div>
      <div class="kpi-value mono" style="color:${k.active_pumps_count > 0 ? 'var(--accent-hydro)' : 'var(--text-primary)'};">${k.active_pumps_count} / ${k.hardware_zones_count}</div>
      <div class="kpi-meta">${k.active_pumps_count > 0 ? 'Riego activo en simulación' : 'Todas las bombas en reposo'}</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Avisos Activos</div>
      <div class="kpi-value mono" style="color:${uniqueAlerts.length > 0 ? 'var(--accent-amber)' : 'var(--accent-botanical)'};">${uniqueAlerts.length}</div>
      <div class="kpi-meta">${uniqueAlerts.length > 0 ? `${data.active_alerts.length} eventos registrados` : 'Todo operando en rango normal'}</div>
    </div>
    <div class="kpi-cell">
      <div class="kpi-label">Agua Estimada</div>
      <div class="kpi-value mono">${k.simulated_water_liters} L</div>
      <div class="kpi-meta">${k.tinkercad_serial_readings} lecturas desde Tinkercad</div>
    </div>
  `;

  document.getElementById('overviewAlertsList').innerHTML = uniqueAlerts.length
    ? uniqueAlerts.slice(0, 3).map(a => `
        <div class="alert-row ${escapeHtml(a.severity)}">
          <div style="min-width:0;">
            <strong style="font-size:0.84rem; display:block;">${escapeHtml(a.title)}</strong>
            <span style="font-size:0.78rem; color:var(--text-muted);">${escapeHtml(a.description)}</span>
          </div>
          ${a._count > 1 ? `<span class="pill amber mono">×${a._count}</span>` : `<span class="pill">${a.is_simulated ? 'Simulado' : 'Real'}</span>`}
        </div>
      `).join('')
    : '<div class="panel-elevated" style="color:var(--text-muted); font-size:0.84rem;">Sin avisos activos en este momento.</div>';

  document.getElementById('overviewRecsList').innerHTML = (data.recent_recommendations || []).slice(0, 2).map(r => {
    const decisionText = formatDecision(r.decision);
    const decColor = r.decision === 'IRRIGATE'
      ? 'var(--accent-hydro)'
      : (r.decision === 'SAFE_SHUTOFF' ? 'var(--accent-crimson)' : 'var(--accent-botanical)');
    return `
      <div style="padding:0.55rem 0; border-bottom:1px solid var(--border-subtle); font-size:0.82rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
          <strong>${escapeHtml(r.crop_name)} (${r.zone_id === 'zone_01' ? 'Zona 1' : (r.zone_id === 'zone_02' ? 'Zona 2' : escapeHtml(r.zone_id))})</strong>
          <span style="font-weight:600; color:${decColor};">${escapeHtml(decisionText)}</span>
        </div>
        <div style="color:var(--text-muted); font-size:0.78rem; margin-top:2px;">
          Pronóstico +6h: <span class="mono">${r.predicted_6h_pct != null ? r.predicted_6h_pct + '%' : 'N/A'}</span> · ${escapeHtml((r.explanation || '').slice(0, 95))}${(r.explanation || '').length > 95 ? '...' : ''}
        </div>
      </div>
    `;
  }).join('');

  // Minimal clean time-series chart
  const pts = data.recent_timeseries.slice(-48);
  renderChart('overviewChart', {
    type: 'line',
    data: {
      labels: pts.map(p => p.timestamp.slice(11, 16) || p.timestamp.slice(5, 16).replace('T', ' ')),
      datasets: [{
        label: 'Humedad del suelo (%)',
        data: pts.map(p => p.soil_moisture_pct),
        borderColor: '#0ea5e9',
        backgroundColor: 'rgba(14, 165, 233, 0.12)',
        fill: true,
        tension: 0.3,
        pointRadius: 1.5
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#cbd5e1' } } },
      scales: {
        x: { ticks: { color: '#7f9488', maxTicksLimit: 7 }, grid: { color: 'rgba(255,255,255,0.03)' } },
        y: { ticks: { color: '#cbd5e1' }, grid: { color: 'rgba(255,255,255,0.05)' }, title: { display: true, text: '% Humedad', color: '#94a89c' } }
      }
    }
  });

  if (STATE.lastTinkercadCount === null) {
    STATE.lastTinkercadCount = k.tinkercad_serial_readings;
  }
  updateLivePill(false);
}

function renderLiveZoneCard(z, rec, idx) {
  const vwc = z.current_moisture_pct;
  const fault = z.sensor_fault === 1 || z.safety_cutoff === 1;
  const pump = z.pump_active === 1;
  const status = getZoneStatus(z);
  const pctWidth = !fault && vwc != null ? Math.min(100, Math.max(4, (vwc / 55) * 100)) : 0;

  let barClass = '';
  if (fault) barClass = 'critical';
  else if (z.crop_id === 'arroz') barClass = 'hydro';
  else if (vwc != null && vwc < z.optimal_min_vwc_pct) barClass = 'low';

  const zoneNum = z.zone_id === 'zone_01' ? 'Zona 1' : (z.zone_id === 'zone_02' ? 'Zona 2' : `Zona ${idx + 1}`);
  const mainPin = (z.hardware_pins || '').split(',')[0] || 'A0';
  const aiLine = rec
    ? `IA (+6h): ${rec.predicted_6h_pct != null ? rec.predicted_6h_pct + '%' : '--'} · ${formatDecision(rec.decision)}`
    : `Modo ${formatMode(z.operating_mode)} listo`;

  return `
    <div class="live-zone-card ${pump ? 'pump-on' : ''} ${fault ? 'fault' : ''}">
      <div class="zone-top-row">
        <div class="zone-title">${escapeHtml(zoneNum)} · ${escapeHtml(z.crop_name)}</div>
        <span class="status-badge ${status.cls}">${escapeHtml(status.label)}</span>
      </div>

      <div class="zone-metric-row">
        <div class="zone-vwc-big mono">${fault ? 'Fallo' : (vwc != null ? `${vwc.toFixed(1)}%` : '--')}</div>
        <div class="zone-ideal-range">Ideal: ${z.optimal_min_vwc_pct}% – ${z.optimal_max_vwc_pct}%</div>
      </div>

      <div class="moisture-bar-track"><div class="moisture-bar-fill ${barClass}" style="width:${pctWidth}%"></div></div>

      <div style="display:flex; justify-content:space-between; align-items:center; font-size:0.83rem;">
        <span style="color:${pump ? 'var(--accent-hydro)' : 'var(--text-secondary)'}; font-weight:600;">
          ${pump ? 'Bomba encendida' : 'Bomba apagada'}
        </span>
        <span style="color:var(--text-muted);">${escapeHtml(formatMode(z.operating_mode))}</span>
      </div>

      <div class="zone-ai-note">${escapeHtml(aiLine)}</div>

      <div class="zone-foot mono">
        <span>Pin ${escapeHtml(mainPin)} · ADC ${z.last_raw_adc ?? '--'}</span>
        <span>Kc ${z.kc_value ?? '-'}</span>
      </div>
    </div>
  `;
}

function renderCompactVirtualCard(z) {
  const vwc = z.current_moisture_pct;
  const pctWidth = vwc != null ? Math.min(100, Math.max(4, (vwc / 55) * 100)) : 0;
  let barClass = '';
  if (z.crop_id === 'arroz') barClass = 'hydro';
  else if (vwc != null && vwc < z.optimal_min_vwc_pct) barClass = 'low';

  return `
    <div class="sector-card">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:6px;">
        <strong style="font-size:0.86rem;">${escapeHtml(z.crop_name)}</strong>
        <span style="font-size:0.72rem; color:var(--text-muted);">Referencia</span>
      </div>
      <div class="mono" style="font-size:1.15rem; font-weight:700; margin-top:4px;">
        ${vwc != null ? `${vwc.toFixed(1)}%` : 'N/A'}
      </div>
      <div class="moisture-bar-track" style="margin:0.45rem 0;"><div class="moisture-bar-fill ${barClass}" style="width:${pctWidth}%"></div></div>
      <div style="font-size:0.74rem; color:var(--text-muted); display:flex; justify-content:space-between;">
        <span>Óptimo ≥ ${z.optimal_min_vwc_pct}%</span>
        <span>${z.crop_id === 'arroz' && z.current_water_lamina_mm != null ? `Lámina ${z.current_water_lamina_mm} mm` : `Kc ${z.kc_value ?? '-'}`}</span>
      </div>
    </div>
  `;
}

/* ==================== 2. CROPS (7 PROFILES) ==================== */
async function loadCrops() {
  if (!STATE.crops.length) {
    const res = await api('/api/crops');
    STATE.crops = res.crops;
  }
  const tabsEl = document.getElementById('cropTabs');
  tabsEl.innerHTML = STATE.crops.map(c => `
    <button class="crop-tab ${c.crop_id === STATE.activeCropId ? 'active' : ''}" onclick="selectCrop('${c.crop_id}')">
      ${escapeHtml(c.common_name)}
    </button>
  `).join('');
  renderCropDetail(STATE.activeCropId);
}

async function selectCrop(cropId) {
  STATE.activeCropId = cropId;
  loadCrops();
}

async function renderCropDetail(cropId) {
  const detail = await api(`/api/crops/${cropId}`);
  const isRice = detail.crop_id === 'arroz';
  const paddy = detail.paddy_lamina_params_mm;

  document.getElementById('cropDetailContainer').innerHTML = `
    <div class="grid-2" style="margin-bottom:0.5rem;">
      <div class="panel-elevated">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
          <div>
            <h3 style="font-size:1.25rem;">${escapeHtml(detail.common_name)} — <em>${escapeHtml(detail.scientific_name)}</em></h3>
            <p class="panel-sub">Familia ${escapeHtml(detail.family)} · Régimen: ${escapeHtml(detail.irrigation_regime)}</p>
          </div>
          <span class="pill botanical">FAO-56</span>
        </div>
        <p style="font-size:0.85rem; color:var(--text-secondary); margin:0.75rem 0;"><strong>Suelo recomendado:</strong> ${escapeHtml(detail.soil_texture_recommended)}</p>

        <div class="grid-3" style="margin-top:0.8rem;">
          <div class="kpi-cell" style="padding:0.8rem;">
            <div class="kpi-label">Humedad del Suelo Ideal</div>
            <div class="kpi-value mono" style="font-size:1.25rem; color:var(--accent-botanical);">${detail.optimal_min_vwc_pct}% – ${detail.optimal_max_vwc_pct}%</div>
            <div class="kpi-meta">Cap. campo ${detail.field_capacity_vwc_pct}% · Crítico ${detail.critical_stress_vwc_pct}%</div>
          </div>
          <div class="kpi-cell" style="padding:0.8rem;">
            <div class="kpi-label">Clima Recomendado</div>
            <div class="kpi-value mono" style="font-size:1.25rem;">${detail.optimal_air_temp_min_c}–${detail.optimal_air_temp_max_c} °C</div>
            <div class="kpi-meta">Humedad aire ${detail.optimal_rh_min_pct}–${detail.optimal_rh_max_pct}%</div>
          </div>
          <div class="kpi-cell" style="padding:0.8rem;">
            <div class="kpi-label">Protecciones de Riego</div>
            <div class="kpi-value mono" style="font-size:1.25rem;">Máx ${detail.max_irrigation_duration_minutes} min</div>
            <div class="kpi-meta">Pausa ${detail.min_cooldown_minutes}m · Margen +${detail.hysteresis_band_pct}%</div>
          </div>
        </div>

        ${isRice && paddy ? `
          <div class="panel-elevated" style="margin-top:0.9rem; border-color:var(--accent-hydro); background:var(--accent-hydro-soft);">
            <h4 style="color:#7dd3fc;">Manejo Especial de Arroz Inundado (Lámina de agua en mm)</h4>
            <p style="font-size:0.82rem; margin:0.3rem 0;">A diferencia de cultivos en tierra firme, el arroz opera bajo lámina de agua en crecimiento y se drena antes de cosechar:</p>
            <div style="display:grid; grid-template-columns:repeat(4,1fr); gap:6px; font-size:0.78rem; margin-top:6px;">
              ${Object.entries(paddy).map(([st, pv]) => `
                <div style="background:var(--bg-surface); padding:6px; border-radius:6px;">
                  <strong>${st}</strong><br/>Meta: <span class="mono">${pv.target_water_lamina_mm} mm</span><br/>${pv.drainage_required ? '<span style="color:var(--accent-amber);">Drenaje final</span>' : `Mín ${pv.min_water_lamina_mm} mm`}
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>

      <div class="panel-elevated">
        <h3>Consumo por Etapa (Kc) y Profundidad de Raíz</h3>
        <div class="chart-box" style="height:230px;"><canvas id="cropKcChart"></canvas></div>
        <h4 style="margin-top:0.85rem; font-size:0.84rem; color:var(--text-secondary);">Fuentes Científicas</h4>
        <ul style="font-size:0.78rem; color:var(--text-muted); padding-left:1.15rem; margin:0.35rem 0;">
          ${detail.sources.map(s => `<li>${escapeHtml(s)}</li>`).join('')}
        </ul>
      </div>
    </div>
  `;

  renderChart('cropKcChart', {
    type: 'bar',
    data: {
      labels: detail.stages.map(s => `${s.stage_key} (${s.duration_days}d)`),
      datasets: [
        { label: 'Coeficiente Kc (FAO-56)', data: detail.stages.map(s => s.kc_value), backgroundColor: '#2e9f68', yAxisID: 'y' },
        { label: 'Profundidad Radicular (m)', data: detail.stages.map(s => s.root_depth_m), type: 'line', borderColor: '#0ea5e9', tension: 0.25, yAxisID: 'y1' }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#cbd5e1' } } },
      scales: {
        x: { ticks: { color: '#cbd5e1' } },
        y: { position: 'left', min: 0, max: 1.4, ticks: { color: '#cbd5e1' }, title: { display: true, text: 'Kc', color: '#2e9f68' } },
        y1: { position: 'right', min: 0, max: 1.5, grid: { drawOnChartArea: false }, ticks: { color: '#7dd3fc' }, title: { display: true, text: 'Zr (m)', color: '#0ea5e9' } }
      }
    }
  });
}

/* ==================== 3. TINKERCAD DUAL-ZONE TWIN ==================== */
async function loadTinkercad() {
  const res = await api('/api/zones');
  STATE.zones = res.zones;
  const z1 = res.zones.find(z => z.zone_id === 'zone_01');
  const z2 = res.zones.find(z => z.zone_id === 'zone_02');
  if (z1?.last_raw_adc != null) {
    document.getElementById('z1AdcRange').value = z1.last_raw_adc;
    document.getElementById('z1AdcVal').textContent = String(z1.last_raw_adc);
  }
  if (z2?.last_raw_adc != null) {
    document.getElementById('z2AdcRange').value = z2.last_raw_adc;
    document.getElementById('z2AdcVal').textContent = String(z2.last_raw_adc);
  }
  renderTinkercadSvg(z1, z2);
}

function renderTinkercadSvg(z1, z2) {
  const z1Pump = z1?.pump_active === 1;
  const z1Fault = z1?.sensor_fault === 1 || z1?.safety_cutoff === 1;
  const z2Pump = z2?.pump_active === 1;
  const z2Fault = z2?.sensor_fault === 1 || z2?.safety_cutoff === 1;

  document.getElementById('tinkercadSvgHost').innerHTML = `
    <svg viewBox="0 0 760 320" width="100%" style="background:#08100d; border-radius:10px; border:1px solid var(--border-strong);">
      <rect x="240" y="35" width="280" height="250" rx="10" fill="#0d313f" stroke="#38bdf8" stroke-width="2"/>
      <text x="380" y="65" text-anchor="middle" fill="#f8fafc" font-family="Space Grotesk, sans-serif" font-size="16" font-weight="700">ARDUINO UNO R3 (SIMULADO)</text>
      <text x="380" y="84" text-anchor="middle" fill="#7dd3fc" font-family="JetBrains Mono, monospace" font-size="11">ATmega328P · UART 9600 bps</text>

      <rect x="18" y="45" width="175" height="95" rx="8" fill="#12211a" stroke="${z1Fault ? '#ef4444' : '#2e9f68'}" stroke-width="2"/>
      <text x="105" y="70" text-anchor="middle" fill="#f1f5f2" font-size="12" font-weight="700">SENSOR SUELO Z1 (A0)</text>
      <text x="105" y="92" text-anchor="middle" fill="#fcd34d" font-family="JetBrains Mono, monospace" font-size="13">ADC: ${z1?.last_raw_adc ?? 560}</text>
      <text x="105" y="114" text-anchor="middle" fill="#94a89c" font-family="JetBrains Mono, monospace" font-size="12">${z1?.current_moisture_pct != null ? z1.current_moisture_pct.toFixed(1) + '% Humedad' : 'FALLO'}</text>
      <line x1="193" y1="92" x2="240" y2="92" stroke="#f59e0b" stroke-width="2.5"/>

      <rect x="567" y="45" width="175" height="95" rx="8" fill="#12211a" stroke="${z1Pump ? '#0ea5e9' : (z1Fault ? '#ef4444' : '#2d4a3b')}" stroke-width="2"/>
      <text x="654" y="68" text-anchor="middle" fill="#f1f5f2" font-size="12" font-weight="700">BOMBA Z1 (D8)</text>
      <circle cx="605" cy="95" r="10" fill="${z1Pump ? '#22c55e' : '#1e293b'}" stroke="#22c55e"/>
      <text x="622" y="99" fill="#cbd5e1" font-family="JetBrains Mono, monospace" font-size="11">D4 Riego: ${z1Pump ? 'ON' : 'OFF'}</text>
      <circle cx="605" cy="122" r="10" fill="${z1Fault ? '#ef4444' : '#1e293b'}" stroke="#ef4444"/>
      <text x="622" y="126" fill="#cbd5e1" font-family="JetBrains Mono, monospace" font-size="11">D5 Fallo: ${z1Fault ? 'ALERTA' : 'OK'}</text>
      <line x1="520" y1="92" x2="567" y2="92" stroke="${z1Pump ? '#0ea5e9' : '#475569'}" stroke-width="2.5"/>

      <rect x="18" y="175" width="175" height="95" rx="8" fill="#12211a" stroke="${z2Fault ? '#ef4444' : '#2e9f68'}" stroke-width="2"/>
      <text x="105" y="200" text-anchor="middle" fill="#f1f5f2" font-size="12" font-weight="700">SENSOR SUELO Z2 (A1)</text>
      <text x="105" y="222" text-anchor="middle" fill="#fcd34d" font-family="JetBrains Mono, monospace" font-size="13">ADC: ${z2?.last_raw_adc ?? 600}</text>
      <text x="105" y="244" text-anchor="middle" fill="#94a89c" font-family="JetBrains Mono, monospace" font-size="12">${z2?.current_moisture_pct != null ? z2.current_moisture_pct.toFixed(1) + '% Humedad' : 'FALLO'}</text>
      <line x1="193" y1="222" x2="240" y2="222" stroke="#f59e0b" stroke-width="2.5"/>

      <rect x="567" y="175" width="175" height="95" rx="8" fill="#12211a" stroke="${z2Pump ? '#0ea5e9' : (z2Fault ? '#ef4444' : '#2d4a3b')}" stroke-width="2"/>
      <text x="654" y="198" text-anchor="middle" fill="#f1f5f2" font-size="12" font-weight="700">BOMBA Z2 (D9)</text>
      <circle cx="605" cy="225" r="10" fill="${z2Pump ? '#22c55e' : '#1e293b'}" stroke="#22c55e"/>
      <text x="622" y="229" fill="#cbd5e1" font-family="JetBrains Mono, monospace" font-size="11">D6 Riego: ${z2Pump ? 'ON' : 'OFF'}</text>
      <circle cx="605" cy="252" r="10" fill="${z2Fault ? '#ef4444' : '#1e293b'}" stroke="#ef4444"/>
      <text x="622" y="256" fill="#cbd5e1" font-family="JetBrains Mono, monospace" font-size="11">D7 Fallo: ${z2Fault ? 'ALERTA' : 'OK'}</text>
      <line x1="520" y1="222" x2="567" y2="222" stroke="${z2Pump ? '#0ea5e9' : '#475569'}" stroke-width="2.5"/>

      <rect x="275" y="140" width="210" height="115" rx="6" fill="#09110e" stroke="#1f3329"/>
      <text x="380" y="165" text-anchor="middle" fill="#6ee7b7" font-family="JetBrains Mono, monospace" font-size="11">PROTECCIÓN 1N4007 ACTIVA</text>
      <text x="380" y="188" text-anchor="middle" fill="#94a89c" font-family="JetBrains Mono, monospace" font-size="10">Z1: ${escapeHtml(formatMode(z1?.operating_mode))}</text>
      <text x="380" y="206" text-anchor="middle" fill="#94a89c" font-family="JetBrains Mono, monospace" font-size="10">Z2: ${escapeHtml(formatMode(z2?.operating_mode))}</text>
      <text x="380" y="232" text-anchor="middle" fill="#38bdf8" font-family="JetBrains Mono, monospace" font-size="10">TX/RX JSON ↔ IA</text>
    </svg>
  `;
}

function appendSerial(msg, cls = '') {
  const host = document.getElementById('serialConsole');
  if (!host) return;
  const div = document.createElement('div');
  div.className = `serial-line ${cls}`;
  div.textContent = msg;
  host.prepend(div);
}

async function sendTinkercadFrame(zoneId, extra = {}) {
  const isZ1 = zoneId === 'zone_01';
  const raw = extra.raw_adc !== undefined ? extra.raw_adc : parseInt(document.getElementById(isZ1 ? 'z1AdcRange' : 'z2AdcRange').value, 10);
  const temp = parseFloat(document.getElementById(isZ1 ? 'z1Temp' : 'z2Temp').value || 25.5);

  if (extra.resetFaults || extra.resetCooldown) {
    await api(`/api/zones/${zoneId}/control`, {
      method: 'POST',
      body: JSON.stringify({
        reset_faults: Boolean(extra.resetFaults),
        reset_cooldown: Boolean(extra.resetCooldown),
        operating_mode: 'AUTO_SIMULATED'
      })
    });
  }
  const txJson = JSON.stringify({ zone: zoneId, raw, air_temp_c: temp, source: 'tinkercad_serial' });
  appendSerial(`TX Arduino → IA: ${txJson}`);

  const res = await api(`/api/zones/${zoneId}/ingest`, {
    method: 'POST',
    body: JSON.stringify({
      raw_adc: raw,
      air_temp_c: temp,
      soil_temp_c: temp - 1.5,
      rh_pct: 64.0,
      source_type: 'tinkercad_serial',
      simulated_runtime_min: extra.runtime || 0
    })
  });
  appendSerial(`RX IA → Arduino: ${res.arduino_command} | Humedad=${res.soil_moisture_pct ?? 'FALLO'}% | ${formatDecision(res.decision)} | Bomba=${res.pump_active ? 'ON' : 'OFF'}`, res.sensor_fault || res.safety_cutoff ? 'err' : 'rx');
  await loadTinkercad();
}

async function resetZoneGuards(zoneId) {
  await api(`/api/zones/${zoneId}/control`, { method: 'POST', body: JSON.stringify({ reset_faults: true, reset_cooldown: true, operating_mode: 'AUTO_SIMULATED' }) });
  appendSerial(`SYS: Protecciones reiniciadas en ${zoneId}.`, 'rx');
  await loadTinkercad();
}

async function runCircuitPreset(preset) {
  if (preset === 'adequate') {
    document.getElementById('z1AdcRange').value = 560;
    document.getElementById('z1AdcVal').textContent = '560';
    await sendTinkercadFrame('zone_01', { raw_adc: 560, resetFaults: true, resetCooldown: true });
  } else if (preset === 'dry') {
    document.getElementById('z1AdcRange').value = 180;
    document.getElementById('z1AdcVal').textContent = '180';
    await sendTinkercadFrame('zone_01', { raw_adc: 180, resetFaults: true, resetCooldown: true });
  } else if (preset === 'independent') {
    document.getElementById('z1AdcRange').value = 180;
    document.getElementById('z1AdcVal').textContent = '180';
    document.getElementById('z2AdcRange').value = 600;
    document.getElementById('z2AdcVal').textContent = '600';
    await sendTinkercadFrame('zone_01', { raw_adc: 180, resetFaults: true, resetCooldown: true });
    await sendTinkercadFrame('zone_02', { raw_adc: 600, resetFaults: true, resetCooldown: true });
  } else if (preset === 'recovery') {
    document.getElementById('z1AdcRange').value = 580;
    document.getElementById('z1AdcVal').textContent = '580';
    await sendTinkercadFrame('zone_01', { raw_adc: 580, resetFaults: true });
  } else if (preset === 'fault') {
    document.getElementById('z1AdcRange').value = 1023;
    document.getElementById('z1AdcVal').textContent = '1023';
    await sendTinkercadFrame('zone_01', { raw_adc: 1023 });
  } else if (preset === 'timeout') {
    document.getElementById('z1AdcRange').value = 180;
    document.getElementById('z1AdcVal').textContent = '180';
    await sendTinkercadFrame('zone_01', { raw_adc: 180, runtime: 32, resetFaults: true, resetCooldown: true });
  }
}

/* ==================== 4. AI LAB ==================== */
async function loadAiLab() {
  const [aiRes, cropsRes] = await Promise.all([api('/api/ai/metrics'), api('/api/crops')]);
  const best = aiRes.metrics.best_models;
  document.querySelector('#aiBestModelsTable tbody').innerHTML = Object.entries(best).map(([task, m]) => `
    <tr>
      <td class="mono">${escapeHtml(task)}</td>
      <td><strong>${escapeHtml(m.algorithm)}</strong></td>
      <td class="mono">${m.metrics.val_rmse}</td>
      <td class="mono">${m.metrics.test_mae}</td>
      <td class="mono">${m.metrics.test_rmse}</td>
      <td class="mono" style="color:var(--accent-botanical);">${m.metrics.test_r2}</td>
    </tr>
  `).join('');

  const fcRows = aiRes.comparison.filter(r => r.task.startsWith('forecast_'));
  const horizons = ['1h', '6h', '12h', '24h'];
  const algs = ['PersistenceBaseline', 'LinearRegression', 'GradientBoosting', 'HistGradientBoosting', 'ExtraTrees', 'MLP_NeuralNet'];
  const palette = ['#94a3b8', '#2e9f68', '#0ea5e9', '#f59e0b', '#14b8a6', '#f43f5e'];

  renderChart('aiComparisonChart', {
    type: 'bar',
    data: {
      labels: horizons,
      datasets: algs.map((alg, idx) => ({
        label: alg,
        backgroundColor: palette[idx],
        data: horizons.map(h => {
          const found = fcRows.find(r => r.horizon === h && r.algorithm === alg);
          return found ? parseFloat(found.test_rmse) : null;
        })
      }))
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#cbd5e1', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#cbd5e1' } },
        y: { ticks: { color: '#cbd5e1' }, title: { display: true, text: 'Test RMSE (% VWC)', color: '#94a89c' } }
      }
    }
  });

  const sel = document.getElementById('aiPredCrop');
  if (!sel.options.length) {
    sel.innerHTML = cropsRes.crops.map(c => `<option value="${c.crop_id}">${escapeHtml(c.common_name)}</option>`).join('');
  }
}

async function runAiPreview() {
  const res = await api('/api/ai/predict', {
    method: 'POST',
    body: JSON.stringify({
      crop_id: document.getElementById('aiPredCrop').value,
      stage_key: document.getElementById('aiPredStage').value,
      raw_adc: parseInt(document.getElementById('aiPredAdc').value, 10),
      air_temp_c: parseFloat(document.getElementById('aiPredTemp').value),
      soil_temp_c: parseFloat(document.getElementById('aiPredTemp').value) - 1.8,
      rh_pct: 62.0
    })
  });
  document.getElementById('aiPredOutput').innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <strong>${escapeHtml(res.crop_name)} (${escapeHtml(res.stage_key)}) · Kc=${res.kc}</strong>
      <span class="pill ${res.recommended_action === 'REGAR' ? 'amber' : 'botanical'}">${escapeHtml(res.recommended_action)}</span>
    </div>
    <div class="mono" style="font-size:0.84rem; margin-bottom:8px;">
      Humedad estimada hoy: ${res.agronomic_scaled_vwc_pct}% (Óptimo ≥ ${res.optimal_min_vwc_pct}%)<br/>
      Pronóstico → +1h: ${res.forecasts['1h']}% | +6h: ${res.forecasts['6h']}% | +12h: ${res.forecasts['12h']}% | +24h: ${res.forecasts['24h']}%
    </div>
    <div style="color:var(--text-secondary);"><strong>Factores:</strong> ${res.drivers.map(escapeHtml).join(' · ')}</div>
    <div style="color:var(--text-muted); font-size:0.76rem; margin-top:4px;">${escapeHtml(res.disclaimer)}</div>
  `;
}

/* ==================== 5. ALERTS ==================== */
async function loadAlerts() {
  const sev = document.getElementById('alertFilterSev').value;
  const org = document.getElementById('alertFilterOrigin').value;
  const st = document.getElementById('alertFilterStatus').value;
  const res = await api(`/api/alerts?severity=${sev}&origin=${org}&status=${st}`);
  const alerts = res.alerts || [];
  STATE.visibleAlertIds = alerts.filter(a => a.status === 'ACTIVE').map(a => a.alert_id);

  // Sync badge when viewing active/all alerts
  if (st === 'ACTIVE' || st === 'all') {
    const activeOnly = alerts.filter(a => a.status === 'ACTIVE');
    if (sev === 'all' && org === 'all') {
      document.getElementById('navAlertBadge').textContent = deduplicateAlerts(activeOnly).length;
    }
  }

  const host = document.getElementById('alertsListHost');
  host.innerHTML = alerts.length ? alerts.map(a => `
    <div class="alert-card ${escapeHtml(a.severity)}">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap;">
        <div>
          <strong>[${escapeHtml(a.severity)}] ${escapeHtml(a.title)}</strong>
          <span class="mono" style="font-size:0.75rem; color:var(--text-muted); margin-left:8px;">${escapeHtml(a.created_at)} · ${escapeHtml(a.zone_id)}</span>
        </div>
        <div style="display:flex; gap:6px; align-items:center;">
          <span class="pill ${a.is_simulated ? 'amber' : 'botanical'}">${a.is_simulated ? 'Simulada' : 'Datos Reales'}</span>
          <span class="pill">${escapeHtml(a.status)}</span>
          ${a.status === 'ACTIVE' ? `<button class="btn btn-sm" onclick="ackAlert(${a.alert_id}, false)">Vista</button><button class="btn btn-primary btn-sm" onclick="ackAlert(${a.alert_id}, true)">Resolver</button>` : ''}
        </div>
      </div>
      <div style="font-size:0.84rem; color:var(--text-secondary); margin-top:6px;">${escapeHtml(a.description)}</div>
      <div style="font-size:0.78rem; color:var(--text-muted); margin-top:4px;"><strong>Causa:</strong> ${escapeHtml(a.cause)} · <strong>Acción:</strong> ${escapeHtml(a.recommendation)}</div>
    </div>
  `).join('') : '<div class="panel-elevated" style="color:var(--text-muted);">No hay alertas con los filtros seleccionados.</div>';
}

async function ackAlert(id, resolve) {
  await api(`/api/alerts/${id}/acknowledge?resolve=${resolve}`, { method: 'POST' });
  await loadAlerts();
}

async function resolveAllVisibleAlerts() {
  if (!STATE.visibleAlertIds.length) return;
  await Promise.all(
    STATE.visibleAlertIds.map(id => api(`/api/alerts/${id}/acknowledge?resolve=true`, { method: 'POST' }))
  );
  await loadAlerts();
}

/* ==================== 6. IRRIGATION CONTROL ==================== */
async function loadIrrigation() {
  const [zRes, eRes] = await Promise.all([api('/api/zones'), api('/api/irrigation/events')]);
  document.querySelector('#irrigationZonesTable tbody').innerHTML = zRes.zones.map(z => `
    <tr>
      <td><strong>${escapeHtml(z.zone_id)}</strong><div style="font-size:0.74rem; color:var(--text-muted);">${z.zone_tier === 'HARDWARE_TINKERCAD' ? 'Tinkercad' : 'Virtual'}</div></td>
      <td>${escapeHtml(z.crop_name)} (${escapeHtml(z.active_stage_key)})</td>
      <td class="mono">${z.current_moisture_pct != null ? z.current_moisture_pct.toFixed(1) + '%' : 'FALLO'} ${z.current_water_lamina_mm != null ? `· ${z.current_water_lamina_mm}mm` : ''}</td>
      <td>
        <select onchange="changeZoneMode('${z.zone_id}', this.value)">
          ${['MONITORING', 'RECOMMENDATION', 'AUTO_SIMULATED', 'MANUAL_SIMULATED'].map(m => `<option value="${m}" ${z.operating_mode === m ? 'selected' : ''}>${escapeHtml(formatMode(m))}</option>`).join('')}
        </select>
      </td>
      <td><span class="pill ${z.pump_active ? 'hydro' : ''}">${z.pump_active ? 'Encendida' : 'Apagada'}</span></td>
      <td style="display:flex; gap:5px;">
        <button class="btn btn-sm" onclick="manualPump('${z.zone_id}', true)">Encender</button>
        <button class="btn btn-danger btn-sm" onclick="manualPump('${z.zone_id}', false)">Apagar</button>
      </td>
    </tr>
  `).join('');

  document.querySelector('#irrigationEventsTable tbody').innerHTML = eRes.events.map(e => `
    <tr>
      <td class="mono">${escapeHtml(e.timestamp)}</td>
      <td class="mono">${escapeHtml(e.zone_id)}</td>
      <td>${escapeHtml(e.crop_name)}</td>
      <td><strong>${escapeHtml(e.action)}</strong></td>
      <td class="mono">${escapeHtml(e.trigger_mode)}</td>
      <td class="mono">${e.duration_minutes}</td>
      <td class="mono">${e.water_volume_liters} L</td>
      <td class="mono">${escapeHtml(e.arduino_command || '-')}</td>
      <td style="font-size:0.78rem;">${escapeHtml(e.reason)}</td>
    </tr>
  `).join('');
}

async function changeZoneMode(zoneId, mode) {
  await api(`/api/zones/${zoneId}/control`, { method: 'POST', body: JSON.stringify({ operating_mode: mode }) });
  loadIrrigation();
}

async function manualPump(zoneId, on) {
  await api(`/api/zones/${zoneId}/control`, { method: 'POST', body: JSON.stringify({ operating_mode: 'MANUAL_SIMULATED', manual_pump_state: on, reset_faults: !on }) });
  loadIrrigation();
}

/* ==================== 7. SIMULATOR ==================== */
async function loadSimulatorOptions() {
  const [zRes, cRes] = await Promise.all([api('/api/zones'), api('/api/crops')]);
  const zSel = document.getElementById('simZone');
  const cSel = document.getElementById('simCrop');
  if (!zSel.options.length) {
    zSel.innerHTML = zRes.zones.map(z => `<option value="${z.zone_id}">${escapeHtml(z.zone_name)}</option>`).join('');
  }
  if (!cSel.options.length) {
    cSel.innerHTML = cRes.crops.map(c => `<option value="${c.crop_id}">${escapeHtml(c.common_name)}</option>`).join('');
  }
}

function applySimPreset(kind) {
  if (kind === 'drought') {
    document.getElementById('simMoisture').value = 17.5;
    document.getElementById('simTemp').value = 33.0;
    document.getElementById('simRh').value = 42;
    document.getElementById('simRain').value = 0;
  } else if (kind === 'rain') {
    document.getElementById('simMoisture').value = 34.0;
    document.getElementById('simTemp').value = 21.0;
    document.getElementById('simRh').value = 88;
    document.getElementById('simRain').value = 28;
  } else if (kind === 'heatwave') {
    document.getElementById('simMoisture').value = 23.0;
    document.getElementById('simTemp').value = 37.5;
    document.getElementById('simRh').value = 35;
    document.getElementById('simRain').value = 0;
  } else if (kind === 'rice') {
    document.getElementById('simZone').value = 'vzone_arroz';
    document.getElementById('simCrop').value = 'arroz';
    document.getElementById('simStage').value = 'medio';
    document.getElementById('simMoisture').value = 41.0;
    document.getElementById('simLamina').value = 18;
  } else if (kind === 'fault') {
    executeSimulation(1023);
    return;
  }
  document.getElementById('simMoistVal').textContent = document.getElementById('simMoisture').value;
  document.getElementById('simTempVal').textContent = document.getElementById('simTemp').value;
  document.getElementById('simRhVal').textContent = document.getElementById('simRh').value;
}

async function executeSimulation(overrideAdc = null) {
  const body = {
    zone_id: document.getElementById('simZone').value,
    crop_id: document.getElementById('simCrop').value,
    stage_key: document.getElementById('simStage').value,
    air_temp_c: parseFloat(document.getElementById('simTemp').value),
    soil_temp_c: parseFloat(document.getElementById('simTemp').value) - 1.8,
    rh_pct: parseFloat(document.getElementById('simRh').value),
    rain_mm: parseFloat(document.getElementById('simRain').value || 0),
    water_lamina_mm: parseFloat(document.getElementById('simLamina').value || 0),
    raw_adc: overrideAdc,
    moisture_pct: overrideAdc === null ? parseFloat(document.getElementById('simMoisture').value) : null
  };
  const res = await api('/api/simulator/run', { method: 'POST', body: JSON.stringify(body) });
  document.getElementById('simResultBox').innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
      <strong>Decisión: <span style="color:var(--accent-hydro);">${escapeHtml(formatDecision(res.decision))}</span></strong>
      <span class="pill ${res.pump_active ? 'hydro' : (res.sensor_fault ? 'crimson' : 'botanical')}">Bomba: ${res.pump_active ? 'Encendida' : 'Apagada'}</span>
    </div>
    <div style="font-size:0.84rem; color:var(--text-secondary);">${escapeHtml(res.explanation)}</div>
    <div class="mono" style="font-size:0.78rem; color:var(--text-muted); margin-top:6px;">Comando: ${escapeHtml(res.arduino_command)} · ETc: ${res.etc_mm_day} mm/día</div>
  `;

  if (res.predictions) {
    renderChart('simForecastChart', {
      type: 'line',
      data: {
        labels: ['Actual', '+1h', '+6h', '+12h', '+24h'],
        datasets: [{
          label: 'Humedad proyectada (%)',
          data: [res.soil_moisture_pct, res.predictions['1h'], res.predictions['6h'], res.predictions['12h'], res.predictions['24h']],
          borderColor: '#2e9f68',
          backgroundColor: 'rgba(46, 159, 104, 0.16)',
          fill: true,
          tension: 0.25
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#cbd5e1' } } },
        scales: { x: { ticks: { color: '#cbd5e1' } }, y: { ticks: { color: '#cbd5e1' } } }
      }
    });
  }
}

/* ==================== 8. REPORTS ==================== */
async function loadReports() {
  const rep = await api('/api/reports/summary');
  document.getElementById('reportsSummaryHost').innerHTML = `
    <div class="kpi-strip">
      <div class="kpi-cell"><div class="kpi-label">Agua Simulada Acumulada</div><div class="kpi-value mono">${rep.kpis.total_simulated_water_liters} L</div><div class="kpi-meta">${escapeHtml(rep.kpis.volume_nature_notice)}</div></div>
      <div class="kpi-cell"><div class="kpi-label">Eventos de Riego</div><div class="kpi-value mono">${rep.kpis.total_irrigation_events}</div><div class="kpi-meta">Registrados en SQLite</div></div>
      <div class="kpi-cell"><div class="kpi-label">Fuentes de Datos</div><div class="kpi-value mono">${rep.readings_by_source.length}</div><div class="kpi-meta">${rep.readings_by_source.map(s => `${s.source_type}: ${s.cnt}`).join(' · ')}</div></div>
    </div>
  `;
  renderChart('reportsChart', {
    type: 'bar',
    data: {
      labels: rep.zones.map(z => z.zone_id),
      datasets: [{
        label: 'Volumen Simulado (Litros)',
        data: rep.zones.map(z => z.total_sim_liters),
        backgroundColor: '#0ea5e9'
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#cbd5e1' } } },
      scales: { x: { ticks: { color: '#cbd5e1' } }, y: { ticks: { color: '#cbd5e1' } } }
    }
  });
}

/* ==================== 9. DATASETS & REFERENCES ==================== */
async function loadDatasets() {
  const [dRes, rRes] = await Promise.all([api('/api/datasets'), api('/api/references')]);
  document.querySelector('#datasetsTable tbody').innerHTML = dRes.datasets.map(d => `
    <tr>
      <td class="mono">${escapeHtml(d.dataset_id)}</td>
      <td><strong>${escapeHtml(d.title)}</strong></td>
      <td style="font-size:0.78rem;">${escapeHtml(d.authors)}</td>
      <td class="mono"><a href="${escapeHtml(d.url)}" target="_blank" rel="noopener" style="color:var(--accent-hydro);">${escapeHtml(d.doi)}</a></td>
      <td>${escapeHtml(d.license)}</td>
      <td class="mono">${d.total_records ?? 'Ref'}</td>
      <td class="mono" style="font-size:0.72rem;">${d.sha256_primary ? d.sha256_primary.slice(0, 18) + '...' : escapeHtml(d.status)}</td>
    </tr>
  `).join('');
  document.getElementById('apaBox').textContent = rRes.apa7;
  document.getElementById('bibBox').textContent = rRes.bibtex;
}

/* ==================== 10. SETTINGS ==================== */
async function loadSettingsOptions() {
  const res = await api('/api/zones');
  const sel = document.getElementById('cfgZone');
  if (!sel.options.length) {
    sel.innerHTML = res.zones.map(z => `<option value="${z.zone_id}">${escapeHtml(z.zone_name)}</option>`).join('');
  }
}

async function saveZoneSettings() {
  const zid = document.getElementById('cfgZone').value;
  const res = await api(`/api/zones/${zid}/config`, {
    method: 'POST',
    body: JSON.stringify({
      optimal_min_vwc_pct: parseFloat(document.getElementById('cfgOptMin').value),
      hysteresis_band_pct: parseFloat(document.getElementById('cfgHyst').value),
      min_cooldown_minutes: parseInt(document.getElementById('cfgCooldown').value, 10),
      max_irrigation_duration_minutes: parseInt(document.getElementById('cfgMaxDur').value, 10)
    })
  });
  document.getElementById('cfgFeedback').textContent = `Cambios guardados en SQLite para ${res.zone_id} (${res.crop_id}).`;
}

/* ==================== INIT ==================== */
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });
  document.getElementById('mobileMenuBtn').addEventListener('click', (e) => {
    e.stopPropagation();
    document.getElementById('sidebar').classList.toggle('open');
  });
  document.addEventListener('click', (e) => {
    const sb = document.getElementById('sidebar');
    if (sb.classList.contains('open') && !sb.contains(e.target) && e.target.id !== 'mobileMenuBtn') {
      sb.classList.remove('open');
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') document.getElementById('sidebar').classList.remove('open');
  });

  loadOverview();

  // Auto-refresh active view every 1.0s whenever telemetry, pump, or safety state changes
  setInterval(async () => {
    try {
      const ov = await api('/api/overview');
      const tcCount = ov.kpis.tinkercad_serial_readings;
      const z1 = (ov.zones || []).find(z => z.zone_id === 'zone_01');
      const z2 = (ov.zones || []).find(z => z.zone_id === 'zone_02');
      const sig = `${tcCount}|${z1?.last_raw_adc}:${z1?.pump_active}:${z1?.safety_cutoff}|${z2?.last_raw_adc}:${z2?.pump_active}:${z2?.safety_cutoff}`;
      if (STATE.lastLiveSig !== null && sig !== STATE.lastLiveSig) {
        updateLivePill(true);
        if (STATE.activeView === 'overview') {
          await loadOverview();
        } else if (STATE.activeView === 'tinkercad') {
          await loadTinkercad();
          appendSerial(`TINKERCAD EN VIVO → Z1: ADC=${z1?.last_raw_adc} (${z1?.current_moisture_pct ?? 'FALLO'}%, Bomba=${z1?.pump_active ? 'ON' : 'OFF'}) | Z2: ADC=${z2?.last_raw_adc} (${z2?.current_moisture_pct ?? 'FALLO'}%, Bomba=${z2?.pump_active ? 'ON' : 'OFF'})`, 'rx');
        } else if (STATE.activeView === 'alerts' && STATE.activeSubTabs.alerts === 'sub-alerts-list') {
          await loadAlerts();
        } else if (STATE.activeView === 'irrigation' && STATE.activeSubTabs.irrigation === 'sub-irrigation-control') {
          await loadIrrigation();
        }
      }
      STATE.lastTinkercadCount = tcCount;
      STATE.lastLiveSig = sig;
    } catch {}
  }, 1000);
});
