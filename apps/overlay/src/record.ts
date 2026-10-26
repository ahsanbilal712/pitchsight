// Recording mode: ?record=1 hides the cursor, forces DPR 1 and exposes window.__whyline.

export interface WhylineHandle {
  ready: boolean;
  record: boolean;
  dpr: number;
  seek: (clock: string | number) => void;
  pause: (paused: boolean) => void;
  debug: () => { clock: number; visibleCues: string[]; frames: number };
  inject: (msg: unknown) => void; // dispatch one stream message as if it arrived (tests, scripted shots)
  layerStats?: () => Record<string, Record<string, number>>; // what each Pitch2D layer drew last frame
  gate?: () => boolean; // a route that needs more than a frame (replay3d) holds `ready` until it passes
  camera?: (name: string) => void; // replay3d: "wide" | "player"
  fps?: (windowMs: number) => number; // replay3d: rendered frames per second over the last windowMs
  scene?: () => Record<string, unknown>;
}

declare global {
  interface Window {
    __whyline?: WhylineHandle;
  }
}

const params = new URLSearchParams(window.location.search);
export const RECORD = params.get("record") === "1";
export const FIXTURE = params.get("fixture") === "1";
// the lazily loaded 3D route installs its own gate; until then it is not ready
const REPLAY3D = window.location.pathname.endsWith("/replay3d") || params.get("view") === "replay3d";

/** Device pixel ratio for canvases: 1 while recording so frames are identical across machines. */
export function canvasDpr(): number {
  return RECORD ? 1 : window.devicePixelRatio || 1;
}

/** "mm:ss" or milliseconds to milliseconds of match time. */
export function parseClock(clock: string | number): number {
  if (typeof clock === "number") return clock;
  const m = /^(\d+):(\d{2})$/.exec(clock.trim());
  if (!m) throw new Error(`bad clock ${clock}`);
  return (Number(m[1]) * 60 + Number(m[2])) * 1000;
}

export function installRecordMode(): void {
  if (RECORD) {
    const style = document.createElement("style");
    style.textContent = "*, *::before, *::after { cursor: none !important; }";
    document.head.appendChild(style);
  }
  window.__whyline = {
    ready: false,
    record: RECORD,
    dpr: canvasDpr(),
    seek: () => undefined,
    pause: () => undefined,
    debug: () => ({ clock: 0, visibleCues: [], frames: 0 }),
    inject: () => undefined,
    gate: REPLAY3D ? () => false : undefined,
  };
}
