// Capsule players in kit colours with shirt-number sprites (no humanoid
// models). Positions interpolate between the two latest 10 Hz frames every render frame. A pale disc under each
// player keeps dark kits (Verdant's green) readable on the grass.
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import { leagueNow, matchKits, type Kit } from "../league";
import type { OverlayState } from "../stream/reducer";
import { world } from "./space";

const FALLBACK: [Kit, Kit] = [
  { primary: "#0e5c36", secondary: "#e3b23c" },
  { primary: "#2b3a55", secondary: "#c9ced6" },
];

function numberTexture(text: string, kit: Kit): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 128;
  c.height = 128;
  const g = c.getContext("2d")!;
  g.fillStyle = kit.primary;
  g.beginPath();
  g.arc(64, 64, 56, 0, Math.PI * 2);
  g.fill();
  g.lineWidth = 10;
  g.strokeStyle = kit.secondary;
  g.stroke();
  g.fillStyle = "#ffffff";
  g.font = "700 64px system-ui, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(text, 64, 68);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export interface FrameRef {
  prev: OverlayState["frame"];
  cur: OverlayState["frame"];
  at: number;
}

export function lerpRow(f: FrameRef, row: number, now: number): [number, number] {
  const cur = f.cur!;
  const prev = f.prev;
  const t = Math.min(1, (now - f.at) / 100);
  if (!prev || prev.t_ms >= cur.t_ms || cur.t_ms - prev.t_ms > 200) return [cur.p[row][0], cur.p[row][1]];
  return [prev.p[row][0] + (cur.p[row][0] - prev.p[row][0]) * t, prev.p[row][1] + (cur.p[row][1] - prev.p[row][1]) * t];
}

export default function Players({ frames, state, focus }: { frames: React.RefObject<FrameRef>; state: OverlayState; focus: string | null }) {
  const groups = useRef<(THREE.Group | null)[]>([]);
  const lg = leagueNow();
  const kits = lg ? matchKits(lg, state.hello) : FALLBACK;
  const ids = state.hello?.player_ids ?? [];
  const sprites = useMemo(
    () =>
      Array.from({ length: 22 }, (_, row) => {
        const shirt = (ids[row] && lg?.players[ids[row]]?.shirt) ?? (row % 11) + 1;
        return numberTexture(String(shirt), kits[row < 11 ? 0 : 1]);
      }),
    [ids.join(","), lg, kits[0].primary, kits[1].primary], // rebuilt when the lineup or the league changes
  );

  useFrame(() => {
    const f = frames.current;
    if (!f?.cur) return;
    const now = performance.now();
    for (let row = 0; row < 22; row++) {
      const g = groups.current[row];
      if (!g) continue;
      const [x, y] = lerpRow(f, row, now);
      const [wx, , wz] = world(x, y);
      g.position.set(wx, 0, wz);
      const [vx, vy] = [f.cur.p[row][2], f.cur.p[row][3]];
      if (Math.hypot(vx, vy) > 0.3) g.rotation.y = Math.atan2(vx, -vy);
    }
  });

  return (
    <group>
      {Array.from({ length: 22 }, (_, row) => {
        const kit = kits[row < 11 ? 0 : 1];
        const isFocus = focus !== null && ids[row] === focus;
        return (
          <group key={row} ref={(g) => void (groups.current[row] = g)} name={`player-${row}`}>
            <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
              <circleGeometry args={[isFocus ? 1.3 : 0.85, 24]} />
              <meshBasicMaterial color={isFocus ? "#ff7a1a" : "#ffffff"} transparent opacity={isFocus ? 0.9 : 0.35} />
            </mesh>
            <mesh position={[0, 0.95, 0]} castShadow>
              <capsuleGeometry args={[0.32, 1.1, 6, 12]} />
              <meshStandardMaterial color={kit.primary} roughness={0.6} />
            </mesh>
            <mesh position={[0, 1.25, 0]}>
              <cylinderGeometry args={[0.335, 0.335, 0.16, 16]} />
              <meshStandardMaterial color={kit.secondary} roughness={0.5} />
            </mesh>
            <sprite position={[0, 2.35, 0]} scale={[0.95, 0.95, 0.95]}>
              <spriteMaterial map={sprites[row]} depthTest={false} />
            </sprite>
          </group>
        );
      })}
    </group>
  );
}
