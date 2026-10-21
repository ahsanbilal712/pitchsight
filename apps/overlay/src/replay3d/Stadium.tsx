// Stadium bowl, pitch and lights, all procedural (no external 3D assets; FEASIBILITY_AUDIT A rows 61-62).
// The pitch texture is drawn on a canvas at 10 px per metre: stripes and the full set of markings.
import { useMemo } from "react";
import * as THREE from "three";

const PX = 10; // canvas pixels per metre
const RUN_OFF = 5; // metres of grass around the lines

function pitchTexture(): THREE.CanvasTexture {
  const W = (105 + 2 * RUN_OFF) * PX;
  const H = (68 + 2 * RUN_OFF) * PX;
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d")!;
  g.fillStyle = "#2f7a3e";
  g.fillRect(0, 0, W, H);
  g.fillStyle = "#2a6f38";
  for (let i = 0; i < 18; i += 2) g.fillRect((i * W) / 18, 0, W / 18, H);
  g.strokeStyle = "rgba(255,255,255,0.9)";
  g.lineWidth = 0.12 * PX;
  const X = (m: number) => (m + RUN_OFF) * PX;
  const Y = (m: number) => (68 - m + RUN_OFF) * PX;
  const rect = (x0: number, y0: number, x1: number, y1: number) => g.strokeRect(X(x0), Y(y1), (x1 - x0) * PX, (y1 - y0) * PX);
  rect(0, 0, 105, 68);
  g.beginPath();
  g.moveTo(X(52.5), Y(0));
  g.lineTo(X(52.5), Y(68));
  g.stroke();
  g.beginPath();
  g.arc(X(52.5), Y(34), 9.15 * PX, 0, Math.PI * 2);
  g.stroke();
  for (const [end, dir] of [
    [0, 1],
    [105, -1],
  ]) {
    rect(Math.min(end, end + dir * 16.5), 34 - 20.16, Math.max(end, end + dir * 16.5), 34 + 20.16);
    rect(Math.min(end, end + dir * 5.5), 34 - 9.16, Math.max(end, end + dir * 5.5), 34 + 9.16);
    const a = Math.acos(5.5 / 9.15);
    g.beginPath();
    if (dir === 1) g.arc(X(11), Y(34), 9.15 * PX, -a, a);
    else g.arc(X(94), Y(34), 9.15 * PX, Math.PI - a, Math.PI + a);
    g.stroke();
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function crowdTexture(): THREE.CanvasTexture {
  // tiny coloured dots read as a crowd from broadcast distance; deterministic hash, no randomness
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 256;
  const g = c.getContext("2d")!;
  g.fillStyle = "#121722";
  g.fillRect(0, 0, c.width, c.height);
  const palette = ["#2d3a52", "#3a3f4b", "#0e5c36", "#e3b23c", "#8e1b1b", "#c9ced6", "#1f2633"];
  for (let i = 0; i < 14000; i++) {
    const h = Math.sin(i * 12.9898) * 43758.5453;
    const f = h - Math.floor(h);
    const k = Math.sin(i * 78.233) * 12345.678;
    const f2 = k - Math.floor(k);
    g.fillStyle = palette[Math.floor(f * f2 * 997) % palette.length];
    g.fillRect(Math.floor(f * c.width), Math.floor(f2 * c.height), 2, 2);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(24, 3); // the lathe's u runs round the bowl, v up the stand: keep the dots square-ish
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

/** Goal frame: posts 7.32 m apart, crossbar at 2.44 m, a translucent net 2 m deep. */
function Goal({ end }: { end: 0 | 105 }) {
  const dir = end === 0 ? -1 : 1;
  const x = end - 52.5;
  const white = <meshStandardMaterial color="#f5f7fa" roughness={0.4} />;
  return (
    <group position={[x, 0, 0]}>
      {[-3.66, 3.66].map((z) => (
        <mesh key={z} position={[0, 1.22, z]}>
          <cylinderGeometry args={[0.06, 0.06, 2.44, 10]} />
          {white}
        </mesh>
      ))}
      <mesh position={[0, 2.44, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.06, 0.06, 7.32, 10]} />
        {white}
      </mesh>
      <mesh position={[dir * 1, 1.22, 0]}>
        <boxGeometry args={[2, 2.44, 7.32]} />
        <meshStandardMaterial color="#ffffff" transparent opacity={0.12} depthWrite={false} />
      </mesh>
    </group>
  );
}

function Floodlight({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      <mesh position={[0, -14, 0]}>
        <cylinderGeometry args={[0.4, 0.6, 28, 8]} />
        <meshStandardMaterial color="#2a2f38" />
      </mesh>
      <mesh>
        <boxGeometry args={[6, 3, 0.6]} />
        <meshStandardMaterial color="#ffffff" emissive="#fff6dd" emissiveIntensity={3} />
      </mesh>
    </group>
  );
}

export default function Stadium() {
  const pitch = useMemo(pitchTexture, []);
  const crowd = useMemo(crowdTexture, []);
  const bowl = useMemo(() => {
    // lathe profile (radius, height) of the stands, then squashed into an oval around the pitch
    const profile = [
      new THREE.Vector2(72, 0),
      new THREE.Vector2(74, 1.5),
      new THREE.Vector2(96, 20),
      new THREE.Vector2(98, 26),
      new THREE.Vector2(99, 26),
    ];
    const geo = new THREE.LatheGeometry(profile, 96);
    geo.scale(1, 1, 0.72);
    return geo;
  }, []);
  return (
    <group>
      <color attach="background" args={["#060a12"]} />
      <fog attach="fog" args={["#060a12", 140, 320]} />
      <hemisphereLight args={["#b9c8ff", "#1b2a1f", 0.55]} />
      <directionalLight
        position={[30, 60, 25]}
        intensity={1.6}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-60}
        shadow-camera-right={60}
        shadow-camera-top={40}
        shadow-camera-bottom={-40}
      />
      <directionalLight position={[-40, 50, -30]} intensity={0.6} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.02, 0]} receiveShadow>
        <planeGeometry args={[105 + 2 * RUN_OFF, 68 + 2 * RUN_OFF]} />
        <meshStandardMaterial map={pitch} roughness={0.95} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.05, 0]}>
        <planeGeometry args={[220, 170]} />
        <meshStandardMaterial color="#1b2b20" roughness={1} />
      </mesh>
      <Goal end={0} />
      <Goal end={105} />
      <mesh geometry={bowl}>
        <meshStandardMaterial map={crowd} side={THREE.DoubleSide} roughness={1} />
      </mesh>
      {(
        [
          [-75, 40, -50],
          [75, 40, -50],
          [-75, 40, 50],
          [75, 40, 50],
        ] as [number, number, number][]
      ).map((p) => (
        <Floodlight key={p.join(",")} position={p} />
      ))}
    </group>
  );
}
