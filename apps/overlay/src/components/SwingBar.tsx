// Swing bar: a cue's graphics.bar {label, from, to} animated from -> to, with the
// counterfactual's n, horizon and seed printed beside the number. The counterfactual schema says numbers are
// shown on screen only with n, horizon_s and seed, so without the counterfactual document the bar stays hidden.
import { useEffect, useState } from "react";
import { visibleCues } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";
import type { Counterfactual, Cue } from "../stream/types";
import { usePresence } from "./motion";

const DELAY_MS = 300; // after the lower-third has slid in
const RUN_MS = 1200;

interface Bar {
  label?: string;
  from?: number;
  to?: number;
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

/** "n = 200, 8 s, seed 4242" (counterfactual schema description). */
export function provenanceLine(cf: Counterfactual): string {
  return `n = ${cf.n}, ${cf.horizon_s} s, seed ${cf.seed}`;
}

function useProgress(): number {
  const [p, setP] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf = 0;
    const step = () => {
      const t = Math.max(0, Math.min(1, (performance.now() - start - DELAY_MS) / RUN_MS));
      setP(1 - (1 - t) ** 3); // ease-out cubic
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, []);
  return p;
}

function Card({ cue, cf, bar, phase }: { cue: Cue; cf: Counterfactual; bar: Required<Bar>; phase: "in" | "out" }) {
  const p = useProgress();
  const value = bar.from + (bar.to - bar.from) * p;
  const delta = Math.round((bar.to - bar.from) * 100);
  const lo = Math.min(bar.from, value);
  const hi = Math.max(bar.from, value);
  return (
    <section className="swing-bar" data-cue-id={cue.cue_id} data-state={phase} data-testid="swing-bar">
      <div className="sw-head">
        <span className="sw-label">{bar.label}</span>
        <span className="sw-number" data-testid="swing-number">
          {pct(value)}
        </span>
      </div>
      <div className="sw-track">
        <div className="sw-span" style={{ left: `${lo * 100}%`, width: `${(hi - lo) * 100}%` }} />
        <i className="sw-from" style={{ left: `${bar.from * 100}%` }} />
        <i className="sw-to" style={{ left: `${value * 100}%` }} />
      </div>
      <div className="sw-foot">
        <span className="sw-delta" data-testid="swing-delta">
          {pct(bar.from)} → {pct(bar.to)} ({delta >= 0 ? "+" : "−"}
          {Math.abs(delta)} pts)
        </span>
        <span className="sw-prov" data-testid="swing-provenance">
          {provenanceLine(cf)}
        </span>
      </div>
    </section>
  );
}

export default function SwingBar() {
  const { state } = useStream();
  const found = visibleCues(state)
    .map((cue) => {
      const bar = (cue.graphics as { bar?: Bar | null } | undefined)?.bar;
      const id = (cue.explain as { counterfactual_id?: string | null } | undefined)?.counterfactual_id;
      const cf = id ? state.counterfactuals[id] : undefined;
      return bar && typeof bar.from === "number" && typeof bar.to === "number" && cf
        ? { cue, cf, bar: { label: bar.label ?? "", from: bar.from, to: bar.to } }
        : null;
    })
    .find((x) => x !== null);
  const shown = usePresence(found ? [found] : [], (f) => f.cue.cue_id);
  return (
    <div className="swing-bar-slot">
      {shown.map(({ key, item, phase }) => (
        <Card key={key} cue={item.cue} cf={item.cf} bar={item.bar} phase={phase} />
      ))}
    </div>
  );
}
