// Ordered layer registry for Pitch2D. Each layer draws with (ctx, frame, cues, facts, toCanvas).
// Layers with order < PLAYERS_ORDER draw under the players, the rest above them.
// T-011 registers the four hooks empty; T-024 (ghost trail) and T-045 (heatmap, threat front,
// referee lines) fill them in.
import type { Cue, Fact } from "../stream/types";

export interface DrawFrame {
  t_ms: number;
  p: number[][]; // interpolated rows [x, y, vx, vy]
  ball_z: number;
  holder: number;
  possession: number;
}

export type LayerFn = (
  ctx: CanvasRenderingContext2D,
  frame: DrawFrame,
  cues: Cue[],
  facts: Record<string, Fact>,
  toCanvas: (x: number, y: number) => [number, number],
) => void;

export interface Layer {
  name: string;
  order: number;
  draw: LayerFn;
}

export const PLAYERS_ORDER = 50;
const registry: Layer[] = [];

export function registerLayer(name: string, order: number, draw: LayerFn): void {
  const i = registry.findIndex((l) => l.name === name);
  if (i >= 0) registry.splice(i, 1);
  registry.push({ name, order, draw });
  registry.sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
}

export function layers(): readonly Layer[] {
  return registry;
}

const empty: LayerFn = () => undefined;
registerLayer("heatmap", 10, empty);
registerLayer("threat_front", 20, empty);
registerLayer("ghost_trail", 60, empty);
registerLayer("referee_lines", 70, empty);
