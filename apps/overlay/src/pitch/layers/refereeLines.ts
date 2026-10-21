// Referee lines layer (TECH_PLAN 1.9, T-045): a `referee_line` cue's graphics.lines ([[x1,y1],[x2,y2]] in
// metres) drawn over 0.6 s of match time from t_in_ms, with the margin between the first two lines labelled
// ("0.4 m"). The cue's text is captioned by the LowerThird.
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
  if (lines.length >= 2 && progress >= 1) {
    m = margin(lines[0], lines[1]);
    const label = `${m.toFixed(1)} m`;
    const mx = (lines[0][0][0] + lines[0][1][0] + lines[1][0][0] + lines[1][1][0]) / 4;
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
