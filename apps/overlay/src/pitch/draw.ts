// Canvas 2D drawing for the pitch, players and ball (ADR-008: 2.5D canvas for live overlays).
import { contrast, type Kit } from "../league";
import { PITCH_L, PITCH_W, type Transform } from "./geometry";
import type { DrawFrame } from "./layers";

export type { Kit };

export interface Palette {
  pitch: string;
  stripe: string;
  line: string;
  ring: string;
}

/** Static pitch: stripes and markings. Drawn once into an offscreen canvas and blitted every frame. */
export function drawPitch(ctx: CanvasRenderingContext2D, T: Transform, c: Palette): void {
  const { toCanvas, scale } = T;
  ctx.fillStyle = c.pitch;
  ctx.fillRect(T.left, T.top, T.width, T.height);
  ctx.fillStyle = c.stripe;
  const stripes = 14;
  for (let i = 0; i < stripes; i += 2) {
    ctx.fillRect(T.left + (i * T.width) / stripes, T.top, T.width / stripes, T.height);
  }
  ctx.strokeStyle = c.line;
  ctx.lineWidth = Math.max(2, 0.12 * scale);
  const rect = (x0: number, y0: number, x1: number, y1: number) => {
    const [ax, ay] = toCanvas(x0, y1);
    const [bx, by] = toCanvas(x1, y0);
    ctx.strokeRect(ax, ay, bx - ax, by - ay);
  };
  rect(0, 0, PITCH_L, PITCH_W);
  const [mx, top] = toCanvas(PITCH_L / 2, PITCH_W);
  const [, bottom] = toCanvas(PITCH_L / 2, 0);
  ctx.beginPath();
  ctx.moveTo(mx, top);
  ctx.lineTo(mx, bottom);
  ctx.stroke();
  const [cx, cy] = toCanvas(PITCH_L / 2, PITCH_W / 2);
  ctx.beginPath();
  ctx.arc(cx, cy, 9.15 * scale, 0, Math.PI * 2);
  ctx.stroke();
  for (const end of [0, PITCH_L]) {
    const dir = end === 0 ? 1 : -1;
    rect(Math.min(end, end + dir * 16.5), PITCH_W / 2 - 20.16, Math.max(end, end + dir * 16.5), PITCH_W / 2 + 20.16);
    rect(Math.min(end, end + dir * 5.5), PITCH_W / 2 - 9.16, Math.max(end, end + dir * 5.5), PITCH_W / 2 + 9.16);
    const [sx, sy] = toCanvas(end + dir * 11, PITCH_W / 2);
    ctx.fillStyle = c.line;
    ctx.beginPath();
    ctx.arc(sx, sy, Math.max(2, 0.2 * scale), 0, Math.PI * 2);
    ctx.fill();
    // penalty arc: the part of the 9.15 m circle outside the box
    const a = Math.acos(5.5 / 9.15);
    ctx.beginPath();
    if (dir === 1) ctx.arc(sx, sy, 9.15 * scale, -a, a);
    else ctx.arc(sx, sy, 9.15 * scale, Math.PI - a, Math.PI + a);
    ctx.stroke();
    rect(Math.min(end, end - dir * 1.5), PITCH_W / 2 - 3.66, Math.max(end, end - dir * 1.5), PITCH_W / 2 + 3.66);
  }
  ctx.beginPath();
  ctx.arc(cx, cy, Math.max(2, 0.2 * scale), 0, Math.PI * 2);
  ctx.fillStyle = c.line;
  ctx.fill();
}

function textColour(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const lum = 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
  return lum > 150 ? "#0c1016" : "#ffffff";
}

/** Below this WCAG contrast against the grass a kit gets a light halo (Verdant's #0E5C36 is 1.6). */
export const MIN_KIT_CONTRAST = 3;

/** Players as kit-coloured discs with shirt numbers; a ring marks the ball holder. Kits that blend into the
 * grass get a light outer halo so every disc stays readable on the green pitch. */
export function drawPlayers(
  ctx: CanvasRenderingContext2D,
  T: Transform,
  frame: DrawFrame,
  kits: [Kit, Kit],
  numbers: (row: number) => string,
  ringColour: string,
  grass = "#2f7a3e",
): void {
  const r = 0.95 * T.scale;
  const halo = kits.map((k) => !(contrast(k.primary, grass) >= MIN_KIT_CONTRAST));
  ctx.font = `700 ${Math.round(r * 1.05)}px system-ui, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  for (let row = 0; row < 22; row++) {
    const [px, py] = T.toCanvas(frame.p[row][0], frame.p[row][1]);
    const kit = kits[row < 11 ? 0 : 1];
    if (halo[row < 11 ? 0 : 1]) {
      ctx.beginPath();
      ctx.arc(px, py, r + Math.max(2.5, 0.2 * T.scale), 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
      ctx.fill();
    }
    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fillStyle = kit.primary;
    ctx.fill();
    ctx.lineWidth = Math.max(2, 0.14 * T.scale);
    ctx.strokeStyle = kit.secondary;
    ctx.stroke();
    if (row === frame.holder) {
      ctx.beginPath();
      ctx.arc(px, py, r * 1.55, 0, Math.PI * 2);
      ctx.lineWidth = Math.max(2, 0.16 * T.scale);
      ctx.strokeStyle = ringColour;
      ctx.stroke();
    }
    ctx.fillStyle = textColour(kit.primary);
    ctx.fillText(numbers(row), px, py + 1);
  }
}

/** Ball with a ground shadow that drifts and grows with height. */
export function drawBall(ctx: CanvasRenderingContext2D, T: Transform, frame: DrawFrame): void {
  const [x, y] = [frame.p[22][0], frame.p[22][1]];
  const z = Math.max(0, frame.ball_z - 0.11);
  const [gx, gy] = T.toCanvas(x, y);
  const shadowR = (0.45 + 0.12 * z) * T.scale;
  ctx.beginPath();
  ctx.ellipse(gx + 0.25 * z * T.scale, gy + 0.18 * z * T.scale, shadowR, shadowR * 0.6, 0, 0, Math.PI * 2);
  ctx.fillStyle = `rgba(0, 0, 0, ${Math.max(0.12, 0.4 - 0.03 * z)})`;
  ctx.fill();
  const [bx, by] = T.toCanvas(x, y + 0.6 * z); // lifted toward the camera with height
  const r = (0.38 + 0.03 * z) * T.scale;
  ctx.beginPath();
  ctx.arc(bx, by, r, 0, Math.PI * 2);
  ctx.fillStyle = "#ffffff";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#0c1016";
  ctx.stroke();
}
