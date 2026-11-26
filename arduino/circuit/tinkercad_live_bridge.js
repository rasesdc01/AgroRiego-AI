// AgroRiego AI — In-Page Bidirectional Tinkercad Serial Bridge (100% AI-Commanded Motor Control)
// Reads live JSON telemetry from Tinkercad's Monitor en Serie DOM, queries FastAPI AI Engine,
// and sends Z1:PUMP=1/0 & Z2:PUMP=1/0 commands directly via DOM without moving mouse or stealing focus.
(function initAgroRiegoLiveBridge() {
  if (window.__AGRORIEGO_BRIDGE_TIMER) {
    clearInterval(window.__AGRORIEGO_BRIDGE_TIMER);
  }
  if (window.__AGRORIEGO_QUEUE_TIMER) {
    clearInterval(window.__AGRORIEGO_QUEUE_TIMER);
  }

  const API_BASE = "http://127.0.0.1:8000";
  const STATE = {
    lastSigByZone: {},
    lastCmdAtByZone: {},
    lastCmdSentByZone: {},
    zoneStatus: { zone_01: null, zone_02: null },
    frameByZone: { zone_01: null, zone_02: null },
    cmdQueue: [],
    sendingNow: false,
    connected: false,
    sentCount: 0,
    cmdCount: 0,
    lastError: null,
  };

  let hud = document.getElementById("agroriego-live-hud");
  if (!hud) {
    hud = document.createElement("div");
    hud.id = "agroriego-live-hud";
    hud.style.cssText = [
      "position:fixed", "bottom:14px", "left:14px", "z-index:99999",
      "background:#0b1310", "color:#f1f5f2", "border:1px solid #2e9f68",
      "border-radius:10px", "padding:10px 14px", "width:470px",
      "font-family:Consolas, monospace", "font-size:11.5px",
      "box-shadow:0 8px 24px rgba(0,0,0,0.45)", "pointer-events:auto"
    ].join(";");
    document.body.appendChild(hud);
  }

  function renderHud() {
    const z1 = STATE.zoneStatus.zone_01;
    const z2 = STATE.zoneStatus.zone_02;
    const f1 = STATE.frameByZone.zone_01;
    const f2 = STATE.frameByZone.zone_02;
    const badge = STATE.connected
      ? `<span style="color:#4ade80;font-weight:bold;">● CONTROL IA ACTIVO (${STATE.cmdCount} cmds)</span>`
      : `<span style="color:#f59e0b;font-weight:bold;">○ ESPERANDO SERIAL / SIMULACIÓN</span>`;
    const fmt = (z, f, label, zKey) => {
      if (!z) return `<div style="color:#94a89c">${label}: esperando trama JSON del Arduino...</div>`;
      const pumpStr = f && f.pump ? '<span style="color:#4ade80">ON</span>' : '<span style="color:#94a3b8">OFF</span>';
      const cmdStr = STATE.lastCmdSentByZone[zKey] || z.arduino_command || "-";
      const p6 = z.predictions ? `${z.predictions["6h"]}%` : "N/A";
      return `<div><b>${label}:</b> ADC=${z.raw_adc} → ${z.soil_moisture_pct ?? "FAULT"}% | IA+6h=${p6} | <span style="color:#38bdf8">${z.decision}</span> | Motor=${pumpStr} | Cmd: <b>${cmdStr}</b></div>`;
    };
    hud.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <strong style="color:#6ee7b7;">AgroRiego AI → Tinkercad (Control 100% IA)</strong>
        ${badge}
      </div>
      ${fmt(z1, f1, "Z1 (A0)", "zone_01")}
      ${fmt(z2, f2, "Z2 (A1)", "zone_02")}
      <div style="color:#94a3b8;font-size:10.5px;margin-top:4px;">Tramas procesadas: ${STATE.sentCount}</div>
      ${STATE.lastError ? `<div style="color:#fca5a5;margin-top:4px;">Error: ${STATE.lastError}</div>` : ""}
    `;
  }

  function findSerialText() {
    const direct = document.querySelector("div.js-code_panel__serial__text, .js-code_panel__serial__text");
    if (direct && (direct.textContent || "").includes("timestamp_ms")) {
      return direct.textContent || "";
    }
    const candidates = document.querySelectorAll('[class*="serial__text"], [class*="serial-monitor__content"], pre');
    for (const el of candidates) {
      const txt = el.textContent || el.innerText || "";
      if (txt.includes('"timestamp_ms"') && txt.includes('"zone"')) {
        return txt;
      }
    }
    return "";
  }

  function findSerialControls() {
    const inp = document.querySelector("input.js-code_panel__serial__input, [class*='serial'] input[type='text']");
    const btn = document.querySelector("a.js-code_panel__serial__send, [class*='serial__send'], [class*='serial'] button");
    return { inp, btn };
  }

  function writeSerialCommandDom(cmd) {
    const { inp, btn } = findSerialControls();
    if (!inp) {
      STATE.lastError = "Abre Monitor en Serie para que la IA envíe comandos.";
      renderHud();
      return false;
    }
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")?.set;
    if (nativeSetter) {
      nativeSetter.call(inp, cmd);
    } else {
      inp.value = cmd;
    }
    inp.dispatchEvent(new Event("input", { bubbles: true }));
    inp.dispatchEvent(new Event("change", { bubbles: true }));
    if (btn) {
      btn.click();
    } else {
      inp.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", keyCode: 13, which: 13, bubbles: true }));
    }
    return true;
  }

  function enqueueCommand(zone, cmd) {
    STATE.cmdQueue = STATE.cmdQueue.filter((item) => item.zone !== zone);
    STATE.cmdQueue.push({ zone, cmd });
  }

  function processCommandQueue() {
    if (STATE.sendingNow || STATE.cmdQueue.length === 0) return;
    const item = STATE.cmdQueue.shift();
    STATE.sendingNow = true;
    try {
      if (writeSerialCommandDom(item.cmd)) {
        STATE.lastCmdSentByZone[item.zone] = item.cmd;
        STATE.lastCmdAtByZone[item.zone] = Date.now();
        STATE.cmdCount += 1;
        STATE.lastError = null;
        console.log(`[AI->Tinkercad] ${item.zone}: ${item.cmd}`);
        renderHud();
      }
    } catch (err) {
      STATE.lastError = String(err?.message || err);
    } finally {
      setTimeout(() => {
        STATE.sendingNow = false;
      }, 350);
    }
  }

  async function forwardLatestFrame(zone, frame) {
    try {
      const resp = await fetch(`${API_BASE}/api/zones/${zone}/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          raw_adc: Number(frame.raw),
          measured_vwc_pct: (typeof frame.moisture_pct === "number" && frame.moisture_pct >= 0) ? Number(frame.moisture_pct) : null,
          air_temp_c: 27.5,
          soil_temp_c: 24.8,
          rh_pct: 62.0,
          source_type: "tinkercad_serial",
          tinkercad_pump_active: Boolean(frame.pump),
          tinkercad_safety_cutoff: Boolean(frame.safety_cutoff),
          live_ai_loop: true,
          inpage_bridge: true,
        }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const res = await resp.json();
      STATE.connected = true;
      STATE.sentCount += 1;
      STATE.lastError = null;
      STATE.zoneStatus[zone] = res;
      STATE.frameByZone[zone] = frame;

      const aiWantsPump = Boolean(res.pump_active);
      const arduinoPump = Boolean(frame.pump);
      const now = Date.now();
      const lastCmdMs = STATE.lastCmdAtByZone[zone] || 0;
      if (!frame.fault && !frame.safety_cutoff && aiWantsPump !== arduinoPump && (now - lastCmdMs) >= 2000) {
        const wireCmd = `${res.arduino_command};`;
        enqueueCommand(zone, wireCmd);
      }
      renderHud();
    } catch (err) {
      STATE.lastError = String(err?.message || err);
      renderHud();
    }
  }

  async function tick() {
    const rawText = findSerialText();
    if (!rawText) return;
    const latestByZone = {};
    const lines = rawText.split(/\r?\n/);
    for (const rawLine of lines) {
      const line = rawLine.trim();
      const s = line.indexOf("{");
      const e = line.lastIndexOf("}");
      if (s === -1 || e <= s) continue;
      try {
        const parsed = JSON.parse(line.slice(s, e + 1));
        if (parsed && (parsed.zone === "zone_01" || parsed.zone === "zone_02") && typeof parsed.raw === "number") {
          const ts = typeof parsed.timestamp_ms === "number" ? parsed.timestamp_ms : 0;
          if (!latestByZone[parsed.zone] || ts >= (latestByZone[parsed.zone].timestamp_ms || 0)) {
            latestByZone[parsed.zone] = parsed;
          }
        }
      } catch {
        // Ignore truncated trailing serial line
      }
    }

    for (const zone of ["zone_01", "zone_02"]) {
      const frame = latestByZone[zone];
      if (!frame) continue;
      const sig = `${frame.timestamp_ms}_${frame.raw}_${Boolean(frame.pump)}_${Boolean(frame.fault)}_${Boolean(frame.safety_cutoff)}`;
      if (STATE.lastSigByZone[zone] !== sig) {
        STATE.lastSigByZone[zone] = sig;
        await forwardLatestFrame(zone, frame);
      }
    }
  }

  renderHud();
  tick();
  window.__AGRORIEGO_BRIDGE_TIMER = setInterval(tick, 700);
  window.__AGRORIEGO_QUEUE_TIMER = setInterval(processCommandQueue, 120);
  console.log("AGRORIEGO_INPAGE_AI_BRIDGE_V3_ACTIVE");
})();
