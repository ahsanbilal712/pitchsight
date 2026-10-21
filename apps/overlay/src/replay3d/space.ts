// Pitch metres (event schema: 105 x 68, origin bottom-left) to three.js world units (1 unit = 1 m): x across,
// y up, z toward the broadcast camera, so the bottom touchline (y = 0) is nearest the wide camera, as in the 2D
// overlay.
export const HALF_L = 52.5;
export const HALF_W = 34;

export function world(x: number, y: number, h = 0): [number, number, number] {
  return [x - HALF_L, h, HALF_W - y];
}
