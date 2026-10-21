// Agent trace (TECH_PLAN 1.9 studio): one row per executor step: executor, model, latency, tokens, cache hit,
// status. Rows are red for a cache miss, an interrupted run or an error (TECH_PLAN 1.8: a miss is visible, never
// silent; a failed step, such as a Panel cache miss reported as an error, must not look clean either).
import { useStream } from "../stream/StreamProvider";
import type { Trace } from "../stream/types";

const RED = new Set(["cache_miss", "interrupted", "error"]);
const SHOWN = 80;

export function isRed(t: Trace): boolean {
  return RED.has(t.status);
}

function hit(v: boolean | null | undefined): string {
  return v === true ? "hit" : v === false ? "miss" : "–";
}

export default function AgentTrace() {
  const { state } = useStream();
  const rows = state.traces.slice(-SHOWN).reverse();
  return (
    <section className="panel trace" data-testid="agent-trace">
      <h2>
        Agent trace <span className="count">{state.traces.length}</span>
      </h2>
      <div className="scroll">
        <table>
          <thead>
            <tr>
              <th>moment</th>
              <th>executor</th>
              <th>model</th>
              <th className="num">latency</th>
              <th className="num">tokens in/out</th>
              <th>cache</th>
              <th>status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr
                key={t.trace_row_id ?? `${t.run_id}-${t.executor}-${i}`}
                className={isRed(t) ? "red" : undefined}
                data-status={t.status}
                data-executor={t.executor}
              >
                <td>{t.moment_id ?? "–"}</td>
                <td>{t.executor}</td>
                <td>{t.model ?? "–"}</td>
                <td className="num">{t.latency_ms !== undefined ? `${t.latency_ms} ms` : "–"}</td>
                <td className="num">
                  {t.tokens_in ?? 0} / {t.tokens_out ?? 0}
                </td>
                <td>{hit(t.cache_hit)}</td>
                <td className="status">{t.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="empty">No runs yet</p>}
      </div>
    </section>
  );
}
