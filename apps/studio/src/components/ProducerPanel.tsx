// Producer panel: pending request_info items (recap cues waiting for
// approval) with Approve / Veto / Hold, and a Veto button on every cue currently on air. Each choice posts
// POST /producer/decision {request_id, decision}; vetoing an on-air cue makes the api broadcast cue_remove.
import { useState } from "react";
import { clockText, post } from "../api";
import { cueStatus } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";

type Decision = "approved" | "vetoed" | "held";

export default function ProducerPanel() {
  const { state, dispatch } = useStream();
  const [held, setHeld] = useState<Record<string, true>>({});
  const [error, setError] = useState<string | null>(null);
  const matchId = state.hello?.match_id;

  const decide = async (requestId: string, decision: Decision) => {
    setError(null);
    const r = await post("/producer/decision", { request_id: requestId, decision, match_id: matchId });
    if (!r.ok) {
      setError(`${requestId}: ${r.status}`);
      return;
    }
    if (decision === "held") setHeld((h) => ({ ...h, [requestId]: true }));
    else dispatch({ kind: "resolved", id: requestId });
  };

  const onAir = Object.values(state.cues)
    .filter((c) => c.t_in_ms <= state.clock && state.clock < c.t_out_ms && cueStatus(state, c) !== "vetoed")
    .sort((a, b) => b.priority - a.priority);

  return (
    <section className="panel producer" data-testid="producer-panel">
      <h2>
        Producer <span className="count">{state.requests.length} pending</span>
      </h2>
      <ol className="requests">
        {state.requests.map((r) => (
          <li key={r.request_id} data-request-id={r.request_id} data-held={Boolean(held[r.request_id])}>
            <div className="req-text">
              <small>
                {r.cue?.clock ?? ""} · {r.cue?.kind?.replace(/_/g, " ") ?? "cue"}
                {held[r.request_id] ? " · held" : ""}
              </small>
              <b>{r.cue?.text?.headline ?? r.request_id}</b>
            </div>
            <div className="buttons">
              <button type="button" className="approve" onClick={() => void decide(r.request_id, "approved")}>
                Approve
              </button>
              <button type="button" className="veto" onClick={() => void decide(r.request_id, "vetoed")}>
                Veto
              </button>
              <button type="button" className="hold" onClick={() => void decide(r.request_id, "held")}>
                Hold
              </button>
            </div>
          </li>
        ))}
        {state.requests.length === 0 && <li className="empty">No approvals waiting</li>}
      </ol>
      <h3>On air</h3>
      <ol className="on-air-list">
        {onAir.map((c) => (
          <li key={c.cue_id} data-on-air-cue={c.cue_id}>
            <div className="req-text">
              <small>
                {clockText(c.t_in_ms)}–{clockText(c.t_out_ms)} · {c.layer.replace(/_/g, " ")}
              </small>
              <b>{c.text.headline}</b>
            </div>
            <button type="button" className="veto" onClick={() => void decide(c.cue_id, "vetoed")}>
              Veto
            </button>
          </li>
        ))}
        {onAir.length === 0 && <li className="empty">Nothing on air</li>}
      </ol>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
