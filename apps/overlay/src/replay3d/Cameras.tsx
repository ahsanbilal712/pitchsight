// Two camera rigs: "wide" is the broadcast camera high on the near side, panning with
// the ball; "player" sits behind the counterfactual's actor, looking at the goal they attack. Switching eases
// the camera over about a second.
import { useFrame, useThree } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import { lerpRow, type FrameRef } from "./Players";
import { world } from "./space";

export type CamName = "wide" | "player";

export default function Cameras({ frames, cam, actorRow, attackRight }: { frames: React.RefObject<FrameRef>; cam: CamName; actorRow: number; attackRight: boolean }) {
  const { camera } = useThree();
  const target = useRef(new THREE.Vector3(0, 0, 0));
  const first = useRef(true);
  useFrame((_, dt) => {
    const f = frames.current;
    if (!f?.cur) return;
    const now = performance.now();
    const [bx, by] = lerpRow(f, 22, now);
    const wantPos = new THREE.Vector3();
    const wantLook = new THREE.Vector3();
    if (cam === "player" && actorRow >= 0) {
      const [px, py] = lerpRow(f, actorRow, now);
      const goal = attackRight ? [105, 34] : [0, 34];
      const [ax, , az] = world(px, py);
      const [gx, , gz] = world(goal[0], goal[1]);
      const dir = new THREE.Vector3(gx - ax, 0, gz - az).normalize();
      wantPos.set(ax - dir.x * 12, 6.5, az - dir.z * 12);
      wantLook.set(gx, 0.5, gz);
    } else {
      const [wx] = world(bx, by);
      wantPos.set(wx * 0.5, 40, 78);
      wantLook.set(wx * 0.7, 0, 4);
    }
    const k = first.current ? 1 : 1 - Math.exp(-dt * 2.5);
    first.current = false;
    camera.position.lerp(wantPos, k);
    target.current.lerp(wantLook, k);
    camera.lookAt(target.current);
  });
  return null;
}
