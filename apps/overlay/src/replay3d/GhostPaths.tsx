// Ghost futures: up to 200 sampled ball paths of the counterfactual as translucent
// lines coloured by branch (first half baseline, second half alternative; cue contract gap 7), Catmull-Rom
// smoothed from 1 Hz points. They fan out over the horizon as the replay clock passes the branch point. The
// chosen alternative is a thick orange dashed trail.
import { Line } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import { catmullRom, splitFutures } from "../pitch/layers/ghostTrail";
import type { Counterfactual } from "../stream/types";
import { world } from "./space";

const LIFT = 0.25;
const SUB = 10;

type Pt = [number, number];

/** All paths' segments ordered by time step, so a draw range reveals every path up to the same time. */
function segmentsByStep(paths: Pt[][]): { geometry: THREE.BufferGeometry; steps: number } {
  const smooth = paths.map((p) => catmullRom(p, SUB));
  const steps = Math.max(0, ...smooth.map((p) => p.length - 1));
  const pos: number[] = [];
  for (let s = 0; s < steps; s++) {
    for (const p of smooth) {
      const a = p[Math.min(s, p.length - 1)];
      const b = p[Math.min(s + 1, p.length - 1)];
      pos.push(...world(a[0], a[1], LIFT), ...world(b[0], b[1], LIFT));
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  return { geometry, steps };
}

export default function GhostPaths({ cf, trail, progress, fade }: { cf: Counterfactual; trail: Pt[]; progress: number; fade: number }) {
  const branches = useMemo(() => {
    const { baseline, alternative } = splitFutures(cf);
    return {
      baseline: { ...segmentsByStep(baseline), n: baseline.length },
      alternative: { ...segmentsByStep(alternative), n: alternative.length },
    };
  }, [cf]);
  const chosen = useMemo(
    () => catmullRom(trail, SUB).map(([x, y]) => new THREE.Vector3(...world(x, y, LIFT + 0.05))),
    [trail],
  );
  const shownSteps = (steps: number) => Math.floor(progress * steps);
  return (
    <group name="ghosts">
      {(
        [
          ["baseline", "#e1ebf5", 0.22],
          ["alternative", "#ff7a1a", 0.28],
        ] as const
      ).map(([name, colour, opacity]) => {
        const b = branches[name];
        b.geometry.setDrawRange(0, shownSteps(b.steps) * b.n * 2);
        return (
          <lineSegments key={name} geometry={b.geometry} name={`ghost-${name}`}>
            <lineBasicMaterial color={colour} transparent opacity={opacity * fade} depthWrite={false} />
          </lineSegments>
        );
      })}
      {chosen.length >= 2 && progress > 0 && (
        <Line
          points={chosen.slice(0, Math.max(2, Math.ceil(chosen.length * Math.min(1, progress * 1.6))))}
          color="#ff7a1a"
          lineWidth={6}
          dashed
          dashSize={1.6}
          gapSize={1.1}
          transparent
          opacity={fade}
          name="chosen-trail"
        />
      )}
    </group>
  );
}
