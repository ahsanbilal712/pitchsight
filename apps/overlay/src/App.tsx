// Overlay root (TECH_PLAN 1.9): a fixed 1920x1080 transparent stage with Pitch2D underneath.
// Lower-third components arrive in T-023; until then the shell shows the stream clock and visible cues.
import Pitch2D from "./pitch/Pitch2D";
import { visibleCues } from "./stream/reducer";
import { useStream } from "./stream/StreamProvider";

function clockText(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export default function App() {
  const { state } = useStream();
  const cues = visibleCues(state);
  return (
    <div className="stage" data-mode={state.profile?.mode ?? "analyst"}>
      <Pitch2D />
      <div className="safe-area">
        <div className="shell-clock" data-testid="clock">
          {state.frame ? clockText(state.clock) : "--:--"} · {state.score[0]}-{state.score[1]}
        </div>
        <ul className="shell-cues" data-testid="cues">
          {cues.map((c) => (
            <li key={c.cue_id} data-cue-id={c.cue_id}>
              {c.text.headline}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
