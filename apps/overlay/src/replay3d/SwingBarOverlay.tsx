// DOM swing bar over the 3D scene (TECH_PLAN 1.9 /replay3d): home win chance moving from the baseline to the
// alternative as the futures fan out, always with n, horizon and seed (counterfactual schema description).
import { matchClubs, useLeague } from "../league";
import type { Counterfactual, Hello } from "../stream/types";

function pct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

export default function SwingBarOverlay({ cf, hello, progress }: { cf: Counterfactual; hello: Hello | null; progress: number }) {
  const lg = useLeague();
  const home = lg ? lg.clubs[matchClubs(lg, hello).home]?.short_name : null;
  const from = cf.baseline.win_prob_home;
  const to = cf.alternative_outcome.win_prob_home;
  const value = from + (to - from) * progress;
  const delta = Math.round((to - from) * 100);
  return (
    <section className="r3d-swing" data-testid="r3d-swing" data-progress={progress.toFixed(2)}>
      <div className="sw-head">
        <span className="sw-label">{home ? `${home} win chance` : "Home win chance"}</span>
        <span className="sw-number">{pct(value)}</span>
      </div>
      <div className="sw-track">
        <div className="sw-span" style={{ left: `${Math.min(from, value) * 100}%`, width: `${Math.abs(value - from) * 100}%` }} />
        <i className="sw-from" style={{ left: `${from * 100}%` }} />
        <i className="sw-to" style={{ left: `${value * 100}%` }} />
      </div>
      <div className="sw-foot">
        <span className="sw-delta">
          {pct(from)} → {pct(to)} ({delta >= 0 ? "+" : "−"}
          {Math.abs(delta)} pts)
        </span>
        <span className="sw-prov" data-testid="r3d-provenance">
          n = {cf.n}, {cf.horizon_s} s, seed {cf.seed}
        </span>
      </div>
    </section>
  );
}
