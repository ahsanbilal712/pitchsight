// Blackboard panel (TECH_PLAN 1.9 studio): the latest fact per name (indices every 1 s, state changes).
import { clockText } from "../api";
import { useStream } from "../stream/StreamProvider";

function show(v: number | string): string {
  return typeof v === "number" ? (Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(3)) : v;
}

export default function Blackboard() {
  const { state } = useStream();
  const facts = Object.values(state.facts).sort((a, b) => a.name.localeCompare(b.name));
  return (
    <section className="panel blackboard" data-testid="blackboard">
      <h2>Blackboard</h2>
      <table>
        <tbody>
          {facts.map((f) => (
            <tr key={f.name} data-fact={f.name}>
              <td>{f.name.replace(/_/g, " ")}</td>
              <td className="num">{show(f.value)}</td>
              <td className="muted">{f.unit ?? f.kind ?? ""}</td>
              <td className="muted num">{clockText(f.t_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {facts.length === 0 && <p className="empty">No facts yet</p>}
    </section>
  );
}
