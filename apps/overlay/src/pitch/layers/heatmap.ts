// Heatmap layer (TECH_PLAN 1.9, T-045): the pitch-control snapshot named by a visible cue
// (graphics.pitch_control_snapshot) as a [34, 53] home-share grid (2 m cells, rows bottom to top) in a diverging
// palette at 35% opacity. The grid becomes a 53 x 34 image once per snapshot; each frame is one drawImage.
import { fetchDoc } from "../../api";
import { modeConfig } from "../../modes/config";
import type { Cue } from "../../stream/types";
import { PITCH_L, PITCH_W } from "../geometry";
import { layerStats, registerLayer, type LayerFn } from "../layers";

const OPACITY = 0.35;
const HOME = [63, 167, 255]; // --c-chaos-settled blue: home control
const AWAY = [255, 61, 90]; // --c-chaos-chaotic red: away control
const MID = [245, 247, 250]; // contested

let wanted: string | null = null;
let image: { id: string; canvas: HTMLCanvasElement; build_ms: number } | null = null;

export function gridImage(grid: number[][]): HTMLCanvasElement {
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  const canvas = document.createElement("canvas");
  canvas.width = cols;
  canvas.height = rows;
  const ctx = canvas.getContext("2d")!;
  const img = ctx.createImageData(cols, rows);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const v = Math.min(1, Math.max(0, grid[r][c]));
      const [to, k] = v >= 0.5 ? [HOME, (v - 0.5) * 2] : [AWAY, (0.5 - v) * 2];
      const i = ((rows - 1 - r) * cols + c) * 4; // row 0 is the bottom touchline
      for (let ch = 0; ch < 3; ch++) img.data[i + ch] = Math.round(MID[ch] + (to[ch] - MID[ch]) * k);
      img.data[i + 3] = Math.round(255 * (0.25 + 0.75 * k));
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

function snapshotOf(cues: Cue[]): string | null {
  for (const c of cues) {
    const id = (c.graphics as { pitch_control_snapshot?: string | null } | undefined)?.pitch_control_snapshot;
    if (id) return id;
  }
  return null;
}

export const drawHeatmap: LayerFn = (ctx, _frame, cues, _facts, toCanvas, state) => {
  const id = modeConfig(state).heatmap ? snapshotOf(cues) : null;
  if (id && id !== wanted && state.hello) {
    wanted = id;
    void fetchDoc(state.hello.match_id, id).then((doc) => {
      const grid = doc?.grid as number[][] | undefined;
      if (wanted !== id || !grid) return;
      const started = performance.now();
      const canvas = gridImage(grid);
      image = { id, canvas, build_ms: performance.now() - started };
    });
  }
  if (!id || !image || image.id !== id) {
    layerStats.heatmap = { drawn: 0 };
    return;
  }
  const [x0, y0] = toCanvas(0, PITCH_W);
  const [x1, y1] = toCanvas(PITCH_L, 0);
  ctx.save();
  ctx.globalAlpha = OPACITY;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(image.canvas, x0, y0, x1 - x0, y1 - y0);
  ctx.restore();
  layerStats.heatmap = { drawn: 1, build_ms: image.build_ms };
};

registerLayer("heatmap", 10, drawHeatmap);
