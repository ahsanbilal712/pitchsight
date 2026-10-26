// Pitch2D: requestAnimationFrame loop drawing the pitch, players with numbers, the ball
// and the registered layers, interpolating linearly between the two latest 10 Hz tracking frames.
import { useEffect, useRef } from "react";
import { leagueNow, loadLeague, matchKits } from "../league";
import { canvasDpr } from "../record";
import { visibleCues } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";
import type { TrackingFrame } from "../stream/types";
import { drawBall, drawPitch, drawPlayers, type Kit, type Palette } from "./draw";
import { lerp, makeTransform } from "./geometry";
import { layers, layerStats, PLAYERS_ORDER, type DrawFrame } from "./layers";
import "./layers/ghostTrail";
import "./layers/heatmap";
import "./layers/refereeLines";
import "./layers/threatFront";
import "../modes/playerCam";

export const STAGE_W = 1920;
export const STAGE_H = 1080;
const SAFE = { x: 96, y: 54 }; // 5% title-safe insets (tokens.css)
const FRAME_MS = 100;
const MAX_MEASURES = 2000;

/** The pitch transform every overlay component shares (pitch fitted inside the title-safe area). */
export const PITCH_T = makeTransform(SAFE.x, SAFE.y, STAGE_W - 2 * SAFE.x, STAGE_H - 2 * SAFE.y);

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function interpolate(prev: TrackingFrame | null, cur: TrackingFrame, t: number): DrawFrame {
  if (!prev || prev.t_ms >= cur.t_ms || cur.t_ms - prev.t_ms > 2 * FRAME_MS) {
    return { t_ms: cur.t_ms, p: cur.p, ball_z: cur.ball_z, holder: cur.holder, possession: cur.possession };
  }
  const p = cur.p.map((row, i) => [lerp(prev.p[i][0], row[0], t), lerp(prev.p[i][1], row[1], t), row[2], row[3]]);
  return {
    t_ms: lerp(prev.t_ms, cur.t_ms, t),
    p,
    ball_z: lerp(prev.ball_z, cur.ball_z, t),
    holder: cur.holder,
    possession: cur.possession,
  };
}

export default function Pitch2D() {
  const { state } = useStream();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frames = useRef<{ prev: TrackingFrame | null; cur: TrackingFrame | null; at: number }>({
    prev: null,
    cur: null,
    at: 0,
  });
  const live = useRef(state);

  live.current = state;
  if (state.frame && state.frame !== frames.current.cur) {
    frames.current = { prev: state.prevFrame, cur: state.frame, at: performance.now() };
  }

  useEffect(() => {
    void loadLeague();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = canvasDpr();
    canvas.width = STAGE_W * dpr;
    canvas.height = STAGE_H * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const T = PITCH_T;
    const palette: Palette = {
      pitch: cssVar("--c-pitch", "#2f7a3e"),
      stripe: cssVar("--c-pitch-stripe", "#2a6f38"),
      line: cssVar("--c-pitch-line", "rgba(255,255,255,0.85)"),
      ring: cssVar("--c-accent", "#ff7a1a"),
    };
    const fallbackKits: [Kit, Kit] = [
      { primary: cssVar("--c-home", "#0e5c36"), secondary: cssVar("--c-home-trim", "#e3b23c") },
      { primary: cssVar("--c-away", "#8e1b1b"), secondary: cssVar("--c-away-trim", "#1c1c1c") },
    ];
    const cache = document.createElement("canvas");
    cache.width = canvas.width;
    cache.height = canvas.height;
    const cctx = cache.getContext("2d")!;
    cctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawPitch(cctx, T, palette);

    let raf = 0;
    let n = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      const { prev, cur, at } = frames.current;
      if (!cur) return;
      performance.mark("pitch2d-start");
      const s = live.current;
      const t = Math.min(1, (performance.now() - at) / FRAME_MS);
      const frame = interpolate(prev, cur, t);
      const cues = visibleCues(s);
      const lg = leagueNow();
      const kits: [Kit, Kit] = lg ? matchKits(lg, s.hello) : fallbackKits;
      const ids = s.hello?.player_ids;
      const numbers = (row: number) => String((ids && lg?.players[ids[row]]?.shirt) ?? (row % 11) + 1);

      ctx.clearRect(0, 0, STAGE_W, STAGE_H);
      ctx.drawImage(cache, 0, 0, STAGE_W, STAGE_H);
      const all = layers();
      for (const l of all) if (l.order < PLAYERS_ORDER) l.draw(ctx, frame, cues, s.facts, T.toCanvas, s);
      drawPlayers(ctx, T, frame, kits, numbers, palette.ring, palette.pitch);
      drawBall(ctx, T, frame);
      for (const l of all) if (l.order >= PLAYERS_ORDER) l.draw(ctx, frame, cues, s.facts, T.toCanvas, s);
      performance.measure("pitch2d-draw", "pitch2d-start");
      if (++n % MAX_MEASURES === 0) performance.clearMeasures("pitch2d-draw");
    };
    raf = requestAnimationFrame(loop);
    if (window.__whyline) window.__whyline.layerStats = () => JSON.parse(JSON.stringify(layerStats));
    return () => cancelAnimationFrame(raf);
  }, []);

  return <canvas ref={canvasRef} className="pitch2d" style={{ width: STAGE_W, height: STAGE_H }} />;
}
