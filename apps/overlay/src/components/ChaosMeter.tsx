// Chaos meter: 0-100 bar plus state label, fed by `fact` messages. `chaos_index` carries the
// value; `chaos_state` (the physics state machine, with hysteresis) carries Settled, Transitional or Chaotic.
// Without a state fact the label falls back to plain thresholds on the value.
import { useStream } from "../stream/StreamProvider";

export type ChaosState = "Settled" | "Transitional" | "Chaotic";
const STATES: ChaosState[] = ["Settled", "Transitional", "Chaotic"];

export function chaosState(value: number | null, stateFact: unknown): ChaosState | null {
  if (typeof stateFact === "string" && (STATES as string[]).includes(stateFact)) return stateFact as ChaosState;
  if (value === null) return null;
  return value > 65 ? "Chaotic" : value < 50 ? "Settled" : "Transitional";
}

export default function ChaosMeter() {
  const { state } = useStream();
  const raw = state.facts["chaos_index"]?.value;
  const value = typeof raw === "number" ? Math.min(100, Math.max(0, raw)) : null;
  const label = chaosState(value, state.facts["chaos_state"]?.value);
  return (
    <div className="chaos-meter" data-testid="chaos-meter" data-state={label ?? "none"} hidden={value === null}>
      <div className="cm-head">
        <span className="cm-title">Chaos</span>
        <span className="cm-value" data-testid="chaos-value">
          {value === null ? "–" : Math.round(value)}
        </span>
      </div>
      <div className="cm-track">
        <div className="cm-fill" style={{ width: `${value ?? 0}%` }} />
        <i className="cm-mark" style={{ left: "50%" }} />
        <i className="cm-mark" style={{ left: "65%" }} />
      </div>
      <div className="cm-state" data-testid="chaos-state">
        {label ?? ""}
      </div>
    </div>
  );
}
