// Player-Cam overlay mode (TECH_PLAN 1.9: player_cam draws the player trail and shows player tags; budgets.yaml
// player_cam.player_trail). The trail is the chosen player's last 8 s of positions, fading out; the tag stays on
// that player while no cue tag is up for them.
import { registerLayer, layerStats, type LayerFn } from "../pitch/layers";
import type { OverlayState } from "../stream/reducer";

const TRAIL_MS = 8000;
const MAX_GAP_MS = 1000; // a jump in time (seek) starts a new trail

/** The player this overlay follows, when it is in player_cam mode. */
export function camPlayer(state: OverlayState): string | null {
  const p = state.profile;
  return p?.mode === "player_cam" && p.player ? p.player : null;
}

let trail: { t: number; x: number; y: number }[] = [];
let trailFor: string | null = null;

export const drawPlayerTrail: LayerFn = (ctx, frame, _cues, _facts, toCanvas, state) => {
  const pid = camPlayer(state);
  const row = pid ? (state.hello?.player_ids ?? []).indexOf(pid) : -1;
  if (!pid || row < 0) {
    trail = [];
    layerStats.player_trail = { points: 0 };
    return;
  }
  const t = frame.t_ms;
  const last = trail[trail.length - 1];
  if (trailFor !== pid || (last && (t < last.t || t - last.t > MAX_GAP_MS))) trail = [];
  trailFor = pid;
  if (!last || t > last.t) trail.push({ t, x: frame.p[row][0], y: frame.p[row][1] });
  trail = trail.filter((p) => t - p.t <= TRAIL_MS);
  ctx.save();
  ctx.lineCap = "round";
  for (let i = 1; i < trail.length; i++) {
    const [ax, ay] = toCanvas(trail[i - 1].x, trail[i - 1].y);
    const [bx, by] = toCanvas(trail[i].x, trail[i].y);
    ctx.globalAlpha = 0.15 + 0.75 * (1 - (t - trail[i].t) / TRAIL_MS);
    ctx.strokeStyle = "#ff7a1a";
    ctx.lineWidth = 6;
    ctx.beginPath();
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
    ctx.stroke();
  }
  ctx.restore();
  layerStats.player_trail = { points: trail.length };
};

registerLayer("player_trail", 40, drawPlayerTrail);
