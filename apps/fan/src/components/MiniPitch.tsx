// Mini-pitch: the Pitch2D drawing approach at phone scale (copied, not imported):
// event-schema metres (105 x 68, origin bottom-left) flipped to canvas, kit-coloured discs with a light halo
// when a kit blends into the grass, the ball, and a ring on the Player-Cam player.
import { useEffect, useRef } from "react";
import { contrast, leagueNow, loadLeague, type Kit } from "../league";
import { useStream } from "../stream/StreamProvider";

const W = 358;
const H = Math.round((W * 68) / 105);
const GRASS = "#2f7a3e";
const STRIPE = "#2a6f38";

function drawPitch(ctx: CanvasRenderingContext2D, s: number) {
  ctx.fillStyle = GRASS;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = STRIPE;
  for (let i = 0; i < 14; i += 2) ctx.fillRect((i * W) / 14, 0, W / 14, H);
  ctx.strokeStyle = "rgba(255,255,255,0.8)";
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, W - 1, H - 1);
  ctx.beginPath();
  ctx.moveTo(W / 2, 0);
  ctx.lineTo(W / 2, H);
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(W / 2, H / 2, 9.15 * s, 0, Math.PI * 2);
  ctx.stroke();
  for (const x0 of [0, 105 - 16.5]) ctx.strokeRect(x0 * s, (34 - 20.16) * s, 16.5 * s, 40.32 * s);
  for (const x0 of [0, 105 - 5.5]) ctx.strokeRect(x0 * s, (34 - 9.16) * s, 5.5 * s, 18.32 * s);
}

export default function MiniPitch({ highlight }: { highlight: string | null }) {
  const state = useStream();
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    void loadLeague();
  }, []);

  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    const s = W / 105;
    const to = (x: number, y: number): [number, number] => [x * s, (68 - y) * s];
    drawPitch(ctx, s);
    const f = state.frame;
    if (!f) return;
    const lg = leagueNow();
    const clubs = state.hello?.clubs ?? lg?.golden;
    const kits: [Kit, Kit] =
      lg && clubs
        ? [lg.clubs[clubs.home].home_kit, lg.clubs[clubs.away].away_kit]
        : [
            { primary: "#0e5c36", secondary: "#e3b23c" },
            { primary: "#2b3a55", secondary: "#c9ced6" },
          ];
    const halo = kits.map((k) => !(contrast(k.primary, GRASS) >= 3));
    const row = highlight ? state.playerIds.indexOf(highlight) : -1;
    for (let i = 0; i < 22; i++) {
      const side = i < 11 ? 0 : 1;
      const [x, y] = to(f.p[i][0], f.p[i][1]);
      if (halo[side]) {
        ctx.beginPath();
        ctx.arc(x, y, 6.5, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(255,255,255,0.9)";
        ctx.fill();
      }
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = kits[side].primary;
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = kits[side].secondary;
      ctx.stroke();
      if (i === row) {
        ctx.beginPath();
        ctx.arc(x, y, 10, 0, Math.PI * 2);
        ctx.lineWidth = 2.5;
        ctx.strokeStyle = "#ff7a1a";
        ctx.stroke();
      }
    }
    const [bx, by] = to(f.p[22][0], f.p[22][1]);
    ctx.beginPath();
    ctx.arc(bx, by, 3.2, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = "#0c1016";
    ctx.stroke();
  }, [state.frame, state.hello, state.playerIds, highlight]);

  return <canvas ref={ref} className="mini-pitch" width={W} height={H} data-testid="mini-pitch" />;
}
