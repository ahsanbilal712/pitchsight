// Why? drawer: the claims behind a cue with their evidence, the pitch-control snapshot
// as a thumbnail and the counterfactual as a mini-chart (baseline vs alternative, with n, horizon and seed).
// Every evidence id is resolved through GET /match/{id}/doc/{doc_id}; unresolved ids are flagged.
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchDoc } from "../api";
import { playerName, useLeague } from "../league";
import { cueStatus } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";

type Doc = Record<string, unknown>;
type Status = "loading" | "ok" | "missing";

interface Outcome {
  p_goal_home: number;
  win_prob_home: number;
  ci95_win_prob_home?: [number, number];
}

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

function PitchThumb({ doc }: { doc: Doc }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const grid = doc.grid as number[][] | undefined;
  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !grid) return;
    const rows = grid.length;
    const cols = grid[0]?.length ?? 0;
    const cw = canvas.width / cols;
    const ch = canvas.height / rows;
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = grid[r][c]; // home share; rows run bottom to top
        const home = [63, 167, 255];
        const away = [255, 61, 90];
        const mix = home.map((h, i) => Math.round(away[i] + (h - away[i]) * v));
        const contested = 1 - Math.abs(v - 0.5) * 2;
        ctx.fillStyle = `rgba(${mix.join(",")}, ${0.35 + 0.65 * (1 - contested)})`;
        ctx.fillRect(c * cw, (rows - 1 - r) * ch, cw + 0.5, ch + 0.5);
      }
    }
    ctx.strokeStyle = "rgba(255,255,255,0.7)";
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, canvas.width - 1, canvas.height - 1);
    ctx.beginPath();
    ctx.moveTo(canvas.width / 2, 0);
    ctx.lineTo(canvas.width / 2, canvas.height);
    ctx.stroke();
  }, [grid]);
  return (
    <figure className="thumb" data-testid="pc-thumb" data-has-grid={Boolean(grid)}>
      {grid ? <canvas ref={ref} width={318} height={204} /> : <div className="empty">no grid</div>}
      <figcaption>
        {String(doc.snapshot_id ?? "")} · home share{" "}
        {typeof doc.home_share === "number" ? pct(doc.home_share) : "–"} · contested{" "}
        {typeof doc.contested_frac === "number" ? pct(doc.contested_frac) : "–"}
      </figcaption>
    </figure>
  );
}

function CfChart({ doc }: { doc: Doc }) {
  const lg = useLeague();
  const { state } = useStream();
  const base = doc.baseline as Outcome;
  const alt = doc.alternative_outcome as Outcome;
  const actual = doc.actual as { kind: string; actor: string; target: string | null };
  const alternative = doc.alternative as { kind: string; actor: string; target: string | null };
  const action = (a: { kind: string; target: string | null }) =>
    `${a.kind}${a.target ? ` to ${a.target.startsWith("p_") ? playerName(lg, a.target, state.hello?.roster) : a.target}` : ""}`;
  const W = 300;
  const rows: [string, number, number, [number, number] | undefined, [number, number] | undefined][] = [
    ["win chance (home)", base.win_prob_home, alt.win_prob_home, base.ci95_win_prob_home, alt.ci95_win_prob_home],
    ["goal in horizon (home)", base.p_goal_home, alt.p_goal_home, undefined, undefined],
  ];
  return (
    <figure className="cf-chart" data-testid="cf-chart">
      <svg width={W + 120} height={rows.length * 56 + 8} role="img" aria-label="counterfactual baseline vs alternative">
        {rows.map(([label, b, a, cb, ca], i) => {
          const y = 8 + i * 56;
          const bar = (v: number, dy: number, cls: string, ci?: [number, number]) => (
            <g className={cls}>
              <rect x={120} y={y + dy} width={Math.max(1, v * W)} height={14} rx={2} />
              {ci && <line x1={120 + ci[0] * W} x2={120 + ci[1] * W} y1={y + dy + 7} y2={y + dy + 7} className="ci" />}
              <text x={126 + Math.max(v, ci ? ci[1] : 0) * W} y={y + dy + 11}>
                {pct(v)}
              </text>
            </g>
          );
          return (
            <g key={label}>
              <text x={0} y={y + 18} className="label">
                {label}
              </text>
              {bar(b, 0, "base", cb)}
              {bar(a, 18, "alt", ca)}
            </g>
          );
        })}
      </svg>
      <figcaption>
        <span className="swatch base" /> actual: {action(actual)} <span className="swatch alt" /> alternative:{" "}
        {action(alternative)}
        <br />
        <span data-testid="cf-provenance">
          n = {String(doc.n)}, {String(doc.horizon_s)} s, seed {String(doc.seed)}
        </span>{" "}
        · {String(doc.engine)} · Δ win {(doc.delta_win_prob_home as number) >= 0 ? "+" : ""}
        {Math.round((doc.delta_win_prob_home as number) * 100)} pts
      </figcaption>
    </figure>
  );
}

export default function WhyDrawer({ cueId, onClose }: { cueId: string; onClose: () => void }) {
  const { state } = useStream();
  const cue = state.cues[cueId];
  const [docs, setDocs] = useState<Record<string, Doc | null>>({});
  const [open, setOpen] = useState<string | null>(null);

  const ids = useMemo(() => {
    if (!cue) return [];
    const set = new Set<string>();
    for (const c of cue.explain.claims) for (const e of c.evidence_ids) set.add(e);
    for (const extra of [cue.explain.counterfactual_id, cue.explain.explanation_id, cue.graphics?.pitch_control_snapshot])
      if (extra) set.add(extra);
    return [...set];
  }, [cue]);

  useEffect(() => {
    if (!cue) return;
    let live = true;
    setDocs({});
    for (const id of ids) {
      void fetchDoc(cue.match_id, id).then((doc) => live && setDocs((d) => ({ ...d, [id]: doc })));
    }
    return () => {
      live = false;
    };
  }, [cue, ids]);

  if (!cue) return null;
  const status = (id: string): Status => (id in docs ? (docs[id] ? "ok" : "missing") : "loading");
  const pcId = cue.graphics?.pitch_control_snapshot ?? ids.find((i) => i.startsWith("pc_"));
  const cfId = cue.explain.counterfactual_id ?? ids.find((i) => i.startsWith("cf_"));
  const ex = cue.explain.explanation_id ? docs[cue.explain.explanation_id] : null;
  const evidence = cue.explain.claims.flatMap((c) => c.evidence_ids);
  const resolved = new Set(evidence.filter((e) => status(e) === "ok")).size;
  const total = new Set(evidence).size;

  return (
    <aside className="drawer" data-testid="why-drawer" data-cue-id={cue.cue_id}>
      <header>
        <div>
          <small>
            {cue.clock} · {cue.kind.replace(/_/g, " ")} · {cueStatus(state, cue)}
          </small>
          <h2>{cue.text.headline}</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="Close" data-testid="drawer-close">
          ×
        </button>
      </header>
      <p className="body">{cue.text.body}</p>
      <h3>Why</h3>
      <p className="why">{cue.explain.why || String(ex?.why ?? "–")}</p>
      {ex && (
        <p className="muted">
          {String(ex.model)} · {String(ex.prompt_version)} · attempt {String(ex.attempt ?? 1)} · confidence{" "}
          {typeof ex.confidence === "number" ? ex.confidence.toFixed(2) : "–"}
        </p>
      )}
      <h3>
        Claims{" "}
        <span className="count" data-testid="evidence-resolved">
          {resolved}/{total} evidence resolved
        </span>
      </h3>
      <table className="claims">
        <thead>
          <tr>
            <th>claim</th>
            <th>kind</th>
            <th>value</th>
            <th>unit</th>
            <th>evidence</th>
          </tr>
        </thead>
        <tbody>
          {cue.explain.claims.map((c, i) => (
            <tr key={i} data-verified={c.verified}>
              <td>
                <span className={c.verified ? "verified" : "unverified"}>{c.verified ? "✓" : "✗"}</span> {c.text}
                {c.reject_reason ? <small className="reject"> {c.reject_reason}</small> : null}
              </td>
              <td>{c.kind}</td>
              <td className="num">{c.value === null ? "–" : String(c.value)}</td>
              <td>{c.unit ?? "–"}</td>
              <td>
                {c.evidence_ids.map((e) => (
                  <a
                    key={e}
                    href={`#${e}`}
                    className="evidence"
                    data-evidence={e}
                    data-status={status(e)}
                    onClick={(ev) => {
                      ev.preventDefault();
                      setOpen(open === e ? null : e);
                    }}
                  >
                    {e}
                  </a>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {open && (
        <pre className="doc" data-testid="evidence-doc" data-doc-id={open}>
          {docs[open] ? JSON.stringify(docs[open], null, 1).slice(0, 2000) : `${open}: not found`}
        </pre>
      )}
      <div className="figures">
        {pcId && docs[pcId] && <PitchThumb doc={docs[pcId]!} />}
        {cfId && docs[cfId] && <CfChart doc={docs[cfId]!} />}
      </div>
      <p className="muted provenance">
        {cue.provenance.agent_path.join(" → ")} · {cue.provenance.model ?? "template"}
        {cue.provenance.resumed_from_checkpoint ? ` · resumed from ${cue.provenance.resumed_from_checkpoint}` : ""}
      </p>
    </aside>
  );
}
