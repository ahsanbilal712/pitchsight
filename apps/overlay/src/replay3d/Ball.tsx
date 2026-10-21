// The ball at its tracked height (ball_z), with a soft shadow disc on the grass.
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { lerpRow, type FrameRef } from "./Players";
import { world } from "./space";

export default function Ball({ frames }: { frames: React.RefObject<FrameRef> }) {
  const ball = useRef<THREE.Mesh>(null);
  const shadow = useRef<THREE.Mesh>(null);
  useFrame(() => {
    const f = frames.current;
    if (!f?.cur || !ball.current || !shadow.current) return;
    const now = performance.now();
    const [x, y] = lerpRow(f, 22, now);
    const t = Math.min(1, (now - f.at) / 100);
    const z = f.prev ? f.prev.ball_z + (f.cur.ball_z - f.prev.ball_z) * t : f.cur.ball_z;
    const [wx, , wz] = world(x, y);
    ball.current.position.set(wx, Math.max(0.11, z), wz);
    shadow.current.position.set(wx, 0.03, wz);
    shadow.current.scale.setScalar(1 + 0.15 * z);
  });
  return (
    <group>
      <mesh ref={ball} castShadow>
        <sphereGeometry args={[0.22, 20, 16]} />
        <meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.25} />
      </mesh>
      <mesh ref={shadow} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[0.32, 20]} />
        <meshBasicMaterial color="#000000" transparent opacity={0.35} />
      </mesh>
    </group>
  );
}
