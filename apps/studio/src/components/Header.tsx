// Header (TECH_PLAN 1.9 studio): match, clock, score, mode badge and spend against the caps.
import { clockText } from "../api";
import { useLeague } from "../league";
import { useStream } from "../stream/StreamProvider";

function usd(v: number | null | undefined): string {
  return v === null || v === undefined ? "–" : `$${v.toFixed(2)}`;
}

export default function Header() {
  const { state } = useStream();
  const lg = useLeague();
  const clubs = state.hello?.clubs ?? lg?.golden;
  const name = (id: string | undefined) => (id && lg?.clubs[id]?.short_name) || id || "–";
  const s = state.spend;
  return (
    <header className="header" data-testid="header">
      <div className="brand">
        PITCHSIGHT <span>studio</span>
      </div>
      <div className="match" data-testid="match">
        <span className="match-id">{state.hello?.match_id ?? "connecting…"}</span>
        <span>
          {name(clubs?.home)} <b data-testid="studio-score">{state.score[0]}–{state.score[1]}</b> {name(clubs?.away)}
        </span>
        <span className="clock" data-testid="studio-clock">
          {clockText(state.clock)}
        </span>
      </div>
      <div className="mode-badge" data-mode={state.mode} data-testid="mode-badge" title={state.modeReason ?? ""}>
        {state.mode}
        {state.modeReason ? <small> · {state.modeReason}</small> : null}
      </div>
      <div className="spend" data-testid="spend">
        <span>
          match {usd(s?.match_usd)} / {usd(s?.caps.match)}
        </span>
        <span>
          day {usd(s?.day_usd)} / {usd(s?.caps.day)}
        </span>
      </div>
    </header>
  );
}
