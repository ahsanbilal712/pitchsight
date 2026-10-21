// Score bug (TECH_PLAN 1.9): short club codes with kit chips, score, match clock and period.
// Fed by the world-state stream: the score follows `goal` events (reducer) and the hello after a seek.
import { matchClubs, matchKits, useLeague } from "../league";
import { useStream } from "../stream/StreamProvider";
import { clockText } from "./motion";

const GOAL_FLASH_MS = 3000; // the score cell flashes for this long of match time after a goal event

function code(name: string | undefined, fallback: string): string {
  return (name ?? fallback).replace(/[^A-Za-z]/g, "").slice(0, 3).toUpperCase();
}

export default function ScoreBug() {
  const { state } = useStream();
  const lg = useLeague();
  const clubs = lg ? matchClubs(lg, state.hello) : null;
  const kits = lg ? matchKits(lg, state.hello) : null;
  const names = clubs && lg ? [lg.clubs[clubs.home]?.short_name, lg.clubs[clubs.away]?.short_name] : [];
  const [home, away] = state.score;
  const period = state.frame?.period ?? 1;
  const lastGoal = [...state.events].reverse().find((e) => e.type === "goal");
  const flash = lastGoal !== undefined && state.clock - lastGoal.t_ms < GOAL_FLASH_MS;
  return (
    <div className="score-bug" data-testid="score-bug">
      {[0, 1].map((side) => (
        <span key={side} className={`sb-team sb-${side === 0 ? "home" : "away"}`} title={names[side]}>
          <i
            className="sb-kit"
            style={kits ? { background: kits[side].primary, borderColor: kits[side].secondary } : undefined}
          />
          <b data-testid={side === 0 ? "sb-home" : "sb-away"}>{code(names[side], side === 0 ? "HOM" : "AWY")}</b>
          {side === 0 && (
            <span className="sb-score" data-testid="score" data-goal={flash}>
              {home}
              <span className="sb-dash">–</span>
              {away}
            </span>
          )}
        </span>
      ))}
      <span className="sb-clock" data-testid="score-clock">
        {state.frame ? clockText(state.clock) : "--:--"}
      </span>
      <span className="sb-period">{period === 1 ? "1H" : "2H"}</span>
    </div>
  );
}
