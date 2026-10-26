// Threat front layer: from the latest `oracle` message {t_ms, p_shot_home, p_shot_away,
// zone {x, y, r}, shooter}. A glow where the attacking side's shot threat is concentrated with a dashed front
// line around it; alpha follows p_shot. Stale oracles (more than two refresh periods old) are not drawn.
import { modeConfig } from "../../modes/config";
import { layerStats, registerLayer, type LayerFn } from "../layers";

const STALE_MS = 4000; // oracle refresh is 2 s (budgets.yaml hard_rules.oracle_refresh_s)
const MIN_P = 0.1;

interface Zone {
  x: number;
  y: number;
  r?: number;
}

export const drawThreatFront: LayerFn = (ctx, frame, _cues, _facts, toCanvas, state) => {
  const o = state.oracle;
  const zone = (o?.zone ?? null) as Zone | null;
  const p = o ? Math.max(o.p_shot_home, o.p_shot_away) : 0;
  if (!modeConfig(state).threatFront || !o || !zone || frame.t_ms - o.t_ms > STALE_MS || p < MIN_P) {
    layerStats.threat_front = { drawn: 0, p: 0 };
    return;
  }
  const [cx, cy] = toCanvas(zone.x, zone.y);
  const [ex] = toCanvas(zone.x + (zone.r ?? 10), zone.y);
  const r = Math.abs(ex - cx);
  const alpha = Math.min(1, 0.25 + p * 1.5);
  ctx.save();
  const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
  glow.addColorStop(0, `rgba(255, 61, 90, ${0.55 * alpha})`);
  glow.addColorStop(0.7, `rgba(255, 61, 90, ${0.25 * alpha})`);
  glow.addColorStop(1, "rgba(255, 61, 90, 0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = "#ff3d5a";
  ctx.lineWidth = 3;
  ctx.setLineDash([10, 8]);
  ctx.lineDashOffset = -frame.t_ms / 60;
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.8, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
  layerStats.threat_front = { drawn: 1, p };
};

registerLayer("threat_front", 20, drawThreatFront);
