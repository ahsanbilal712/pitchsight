// Moment queue (TECH_PLAN 1.9 studio): moments the Scout raised, newest first, with leverage and status.
import { clockText } from "../api";
import { playerName, useLeague } from "../league";
import { useStream } from "../stream/StreamProvider";

export default function MomentQueue() {
  const { state } = useStream();
  const lg = useLeague();
  const moments = Object.values(state.moments).sort((a, b) => b.t_ms - a.t_ms);
  return (
    <section className="panel moments" data-testid="moment-queue">
      <h2>
        Moments <span className="count">{moments.length}</span>
      </h2>
      <ol>
        {moments.map((m) => (
          <li key={m.moment_id} data-moment-id={m.moment_id} data-status={m.status ?? "new"}>
            <span className="t">{m.clock ?? clockText(m.t_ms)}</span>
            <span className="kind">{m.kind.replace(/_/g, " ")}</span>
            {m.fast ? <span className="tag">fast</span> : null}
            <span className="lev">{typeof m.leverage === "number" ? `${Math.round(m.leverage * 100)}%` : ""}</span>
            <span className="who">{(m.players ?? []).slice(0, 2).map((p) => playerName(lg, p)).join(", ")}</span>
            <span className="status">{m.status ?? "new"}</span>
          </li>
        ))}
        {moments.length === 0 && <li className="empty">No moments yet</li>}
      </ol>
    </section>
  );
}
