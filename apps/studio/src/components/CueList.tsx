// Cue list: every cue regardless of mode, newest first, with the verified flag and the
// producer status. Clicking a row opens the Why? drawer.
import { clockText } from "../api";
import { cueStatus } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";

export default function CueList({ selected, onSelect }: { selected: string | null; onSelect: (id: string) => void }) {
  const { state } = useStream();
  const cues = Object.values(state.cues).sort((a, b) => b.t_in_ms - a.t_in_ms || b.cue_id.localeCompare(a.cue_id));
  return (
    <section className="panel cues" data-testid="cue-list">
      <h2>
        Cues <span className="count">{cues.length}</span>
      </h2>
      <ol>
        {cues.map((c) => {
          const status = cueStatus(state, c);
          const onAir = c.t_in_ms <= state.clock && state.clock < c.t_out_ms && status !== "vetoed";
          return (
            <li
              key={c.cue_id}
              data-cue-id={c.cue_id}
              data-status={status}
              data-on-air={onAir}
              aria-selected={selected === c.cue_id}
              onClick={() => onSelect(c.cue_id)}
            >
              <span className="t">{c.clock ?? clockText(c.t_in_ms)}</span>
              <span className={c.verified ? "verified" : "unverified"} data-testid="cue-verified">
                {c.verified ? "✓" : "!"}
              </span>
              <span className="headline">{c.text.headline}</span>
              <span className="kind">{c.kind.replace(/_/g, " ")}</span>
              <span className="modes">{c.targets.modes.filter((m) => m !== "studio").join(" ")}</span>
              <span className="status" data-testid="cue-status">
                {status}
              </span>
              {onAir && <span className="on-air">on air</span>}
            </li>
          );
        })}
        {cues.length === 0 && <li className="empty">No cues yet</li>}
      </ol>
    </section>
  );
}
