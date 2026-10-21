// Pitch geometry: event-schema metres (105 x 68, origin bottom-left) to canvas pixels (origin top-left).
export const PITCH_L = 105;
export const PITCH_W = 68;

export interface Transform {
  scale: number; // px per metre
  left: number;
  top: number;
  width: number;
  height: number;
  toCanvas: (x: number, y: number) => [number, number];
}

/** Fit the pitch, aspect preserved, inside a box (the title-safe area by default). */
export function makeTransform(boxLeft: number, boxTop: number, boxWidth: number, boxHeight: number): Transform {
  const scale = Math.min(boxWidth / PITCH_L, boxHeight / PITCH_W);
  const width = PITCH_L * scale;
  const height = PITCH_W * scale;
  const left = boxLeft + (boxWidth - width) / 2;
  const top = boxTop + (boxHeight - height) / 2;
  return {
    scale,
    left,
    top,
    width,
    height,
    // y is flipped: y = 0 (bottom touchline) is the bottom edge of the canvas pitch
    toCanvas: (x, y) => [left + x * scale, top + (PITCH_W - y) * scale],
  };
}

/** Linear interpolation of a value between the two latest frames. */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}
