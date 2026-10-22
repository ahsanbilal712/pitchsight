// Ghost trail layer (TECH_PLAN 1.9, T-024): up to 200 sampled futures of a counterfactual as translucent ball
// paths coloured by branch, plus the cue's chosen alternative (graphics.ghost_trail) as an orange dashed trail.
// Futures are 1 Hz points (TECH_PLAN 1.5 "Returns"), smoothed with Catmull-Rom splines and cached as Path2D
// per counterfactual, so a frame is 200 stroke calls. Everything fades in over 0.8 s of match time.
import type { Counterfactual, Cue } from "../../stream/types";
import { layerStats, registerLayer, type LayerFn } from "../layers";

const FADE_MS = 800;
const SUBDIV = 10; // smoothed points per 1 Hz segment
const MAX_FUTURES = 200;
const COLOURS = { baseline: "rgba(225, 235, 245, 1)", alternative: "rgba(255, 122, 26, 1)", chosen: "#ff7a1a" };

type Pt = [number, number];

/** Uniform Catmull-Rom through every point, `subdiv` samples per segment, endpoints clamped. */
export function catmullRom(points: Pt[], subdiv = SUBDIV): Pt[] {
  if (points.length < 3) return points.slice();
  const out: Pt[] = [];
  const at = (i: number) => points[Math.max(0, Math.min(points.length - 1, i))];
  for (let i = 0; i < points.length - 1; i++) {
    const [p0, p1, p2, p3] = [at(i - 1), at(i), at(i + 1), at(i + 2)];
    for (let k = 0; k < subdiv; k++) {
      const t = k / subdiv;
      const t2 = t * t;
      const t3 = t2 * t;
      const f = (a: number, b: number, c: number, d: number) =>
        0.5 * (2 * b + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3);
      out.push([f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1])]);
    }
  }
  out.push(points[points.length - 1]);
  return out;
}

function toPath(points: Pt[], toCanvas: (x: number, y: number) => Pt): Path2D {
  const path = new Path2D();
  points.forEach(([x, y], i) => {
    const [cx, cy] = toCanvas(x, y);
    if (i === 0) path.moveTo(cx, cy);
    else path.lineTo(cx, cy);
  });
  return path;
}

interface Built {
  baseline: Path2D[];
  alternative: Path2D[];
  pointsPerPath: number;
}

const cache = new Map<string, Built>();

/** Branch split of futures_sample: first half baseline, second half alternative (cue contract gap 7). */
export function splitFutures(cf: Counterfactual): { baseline: Pt[][]; alternative: Pt[][] } {
  const all = (cf.futures_sample ?? []).slice(0, MAX_FUTURES) as Pt[][];
  if (all.length < 2) return { baseline: [], alternative: all };
  const half = Math.floor(all.length / 2);
  return { baseline: all.slice(0, half), alternative: all.slice(half) };
}

function build(cf: Counterfactual, toCanvas: (x: number, y: number) => Pt): Built {
  const hit = cache.get(cf.counterfactual_id);
  if (hit) return hit;
  const { baseline, alternative } = splitFutures(cf);
  const smooth = (paths: Pt[][]) => paths.map((p) => toPath(catmullRom(p), toCanvas));
  const first = baseline[0] ?? alternative[0] ?? [];
  const built = {
    baseline: smooth(baseline),
    alternative: smooth(alternative),
    pointsPerPath: catmullRom(first).length,
  };
  cache.set(cf.counterfactual_id, built);
  return built;
}

/** The visible cue that carries a ghost: a counterfactual we hold, or at least a chosen trail. */
function ghostCue(cues: Cue[], cfs: Record<string, Counterfactual>): { cue: Cue; cf: Counterfactual | null } | null {
  for (const cue of cues) {
    const id = (cue.explain as { counterfactual_id?: string | null } | undefined)?.counterfactual_id;
    const trail = (cue.graphics as { ghost_trail?: Pt[] } | undefined)?.ghost_trail;
    const cf = id ? (cfs[id] ?? null) : null;
    if (cf || (trail && trail.length >= 2)) return { cue, cf };
  }
  return null;
}

function arrowHead(ctx: CanvasRenderingContext2D, from: Pt, to: Pt, size: number): void {
  const a = Math.atan2(to[1] - from[1], to[0] - from[0]);
  ctx.beginPath();
  ctx.moveTo(to[0], to[1]);
  ctx.lineTo(to[0] - size * Math.cos(a - 0.45), to[1] - size * Math.sin(a - 0.45));
  ctx.lineTo(to[0] - size * Math.cos(a + 0.45), to[1] - size * Math.sin(a + 0.45));
  ctx.closePath();
  ctx.fill();
}

export const drawGhostTrail: LayerFn = (ctx, frame, cues, _facts, toCanvas, state) => {
  const found = ghostCue(cues, state.counterfactuals);
  if (!found) {
    layerStats.ghost_trail = { paths: 0, alpha: 0, pointsPerPath: 0, chosen: 0 };
    return;
  }
  const { cue, cf } = found;
  const alpha = Math.max(0, Math.min(1, (frame.t_ms - cue.t_in_ms) / FADE_MS));
  let paths = 0;
  let pointsPerPath = 0;
  ctx.save();
  // futures that leave the pitch (ball out for a throw-in) stop at the lines plus a 2 m run-off, so they never
  // streak across the score bug or the lower-third
  const [lx, ty] = toCanvas(-2, 70);
  const [rx, by] = toCanvas(107, -2);
  ctx.beginPath();
  ctx.rect(lx, ty, rx - lx, by - ty);
  ctx.clip();
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  if (cf && alpha > 0) {
    const built = build(cf, toCanvas);
    pointsPerPath = built.pointsPerPath;
    ctx.lineWidth = 1.6;
    for (const [branch, list] of [
      ["baseline", built.baseline],
      ["alternative", built.alternative],
    ] as const) {
      ctx.strokeStyle = COLOURS[branch];
      ctx.globalAlpha = alpha * (branch === "baseline" ? 0.16 : 0.2);
      for (const p of list) ctx.stroke(p);
      paths += list.length;
    }
  }
  const trail = (cue.graphics as { ghost_trail?: Pt[] } | undefined)?.ghost_trail ?? [];
  if (trail.length >= 2 && alpha > 0) {
    const pts = catmullRom(trail).map(([x, y]) => toCanvas(x, y));
    const line = new Path2D();
    pts.forEach(([x, y], i) => (i === 0 ? line.moveTo(x, y) : line.lineTo(x, y)));
    ctx.globalAlpha = alpha;
    ctx.setLineDash([]);
    ctx.lineWidth = 9;
    ctx.strokeStyle = "rgba(12, 16, 22, 0.55)"; // dark under-stroke keeps the dashes readable on grass
    ctx.stroke(line);
    ctx.setLineDash([16, 11]);
    ctx.lineDashOffset = -frame.t_ms / 40; // dashes march toward the end of the trail
    ctx.lineWidth = 5;
    ctx.strokeStyle = COLOURS.chosen;
    ctx.stroke(line);
    ctx.setLineDash([]);
    ctx.fillStyle = COLOURS.chosen;
    arrowHead(ctx, pts[pts.length - 2], pts[pts.length - 1], 22);
  }
  ctx.restore();
  layerStats.ghost_trail = { paths, alpha, pointsPerPath, chosen: trail.length >= 2 ? 1 : 0 };
};

registerLayer("ghost_trail", 60, drawGhostTrail);
