// Referee lines layer (TECH_PLAN 1.9, T-045): a `referee_line` cue's graphics.lines ([[x1,y1],[x2,y2]] in
// metres) drawn over 0.6 s of match time from t_in_ms, with the margin labelled ("0.4 m"): the gap between the first
// two lines, or, for a single line (an offside line alone), the cue's verified claim in metres. The cue's text is
// captioned by the LowerThird.
import type { Cue } from "../../stream/types";
import { layerStats, registerLayer, type LayerFn } from "../layers";

const DRAW_MS = 600;
const COLOUR = "#ffe600"; // --c-referee-line

type Line = [[number, number], [number, number]];

/** Distance between two (roughly parallel) lines: between their midpoints, across the lines' direction. */
export function margin(a: Line, b: Line): number {
  const [ax, ay] = [(a[0][0] + a[1][0]) / 2, (a[0][1] + a[1][1]) / 2];
  const [bx, by] = [(b[0][0] + b[1][0]) / 2, (b[0][1] + b[1][1]) / 2];
  const [dx, dy] = [a[1][0] - a[0][0], a[1][1] - a[0][1]];
  const len = Math.hypot(dx, dy) || 1;
  return Math.abs(((bx - ax) * -dy + (by - ay) * dx) / len); // component of the gap normal to line a
}

/** The first verified claim in metres on the cue (Fourth Official margins), or null. */
function metresClaim(cue: Cue): number | null {
  const claims = ((cue.explain as { claims?: { unit?: string | null; value?: unknown; verified?: boolean }[] })
    ?.claims ?? []).filter((c) => c.unit === "metres" && c.verified !== false && typeof c.value === "number");
  return claims.length ? (claims[0].value as number) : null;
}

export const drawRefereeLines: LayerFn = (ctx, frame, cues, _facts, toCanvas) => {
  const cue = cues.find((c) => c.layer === "referee_line");
  const lines = ((cue?.graphics as { lines?: Line[] } | undefined)?.lines ?? []).slice(0, 4);
  if (!cue || lines.length === 0) {
    layerStats.referee_lines = { lines: 0, progress: 0 };
    return;
  }
  const progress = Math.max(0, Math.min(1, (frame.t_ms - cue.t_in_ms) / DRAW_MS));
  ctx.save();
  ctx.lineCap = "round";
  for (const [[x1, y1], [x2, y2]] of lines) {
    const [ax, ay] = toCanvas(x1, y1);
    const [bx, by] = toCanvas(x1 + (x2 - x1) * progress, y1 + (y2 - y1) * progress);
    for (const [w, colour] of [
      [7, "rgba(12, 16, 22, 0.6)"],
      [3, COLOUR],
    ] as const) {
      ctx.lineWidth = w;
      ctx.strokeStyle = colour;
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(bx, by);
      ctx.stroke();
    }
  }
  let m = 0;
  const claimed = metresClaim(cue);
  if (progress >= 1 && (lines.length >= 2 || claimed !== null)) {
    m = lines.length >= 2 ? margin(lines[0], lines[1]) : (claimed as number);
    const label = `${m.toFixed(1)} m`;
    const used = lines.slice(0, 2);
    const mx = used.reduce((a, l) => a + l[0][0] + l[1][0], 0) / (2 * used.length);
    const [lx, ly] = toCanvas(mx, 40); // mid-height: clear of the score bug, chaos meter and lower-third
    ctx.font = "700 24px ui-monospace, Menlo, monospace";
    const w = ctx.measureText(label).width + 20;
    ctx.fillStyle = COLOUR;
    ctx.beginPath();
    ctx.roundRect(lx - w / 2, ly - 18, w, 36, 6);
    ctx.fill();
    ctx.fillStyle = "#0c1016";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, lx, ly + 1);
  }
  ctx.restore();
  layerStats.referee_lines = { lines: lines.length, progress, margin_m: Math.round(m * 10) / 10 };
};

registerLayer("referee_lines", 70, drawRefereeLines);
