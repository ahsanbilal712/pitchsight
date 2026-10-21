// Recording mode (TECH_PLAN 1.9): ?record=1 hides the cursor, forces DPR 1 and exposes window.__whyline.

export interface WhylineHandle {
  ready: boolean;
  record: boolean;
  dpr: number;
  seek: (clock: string | number) => void;
  debug: () => { clock: number; visibleCues: string[]; frames: number };
}

declare global {
  interface Window {
    __whyline?: WhylineHandle;
  }
}

const params = new URLSearchParams(window.location.search);
export const RECORD = params.get("record") === "1";
export const FIXTURE = params.get("fixture") === "1";

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
    debug: () => ({ clock: 0, visibleCues: [], frames: 0 }),
  };
}
