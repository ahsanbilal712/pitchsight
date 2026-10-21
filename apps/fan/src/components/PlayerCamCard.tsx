// Player-Cam card (TECH_PLAN 1.9 fan app): distance, top speed, sprints, touches and Decision Index for the
// chosen player, from GET /match/{id}/players/{player_id}/stats (MCP player_stats on the same code), plus the
// latest tag cue about the player (a sprint's km/h, a Decision Index line).
import { useEffect, useState } from "react";
import { useLeague } from "../league";
import { useStream } from "../stream/StreamProvider";

const API = new URLSearchParams(window.location.search).get("api") ?? "localhost:8000";

interface Stats {
  player_id: string;
  name: string;
  touches: number;
  sprints: number;
  top_speed_kmh: number | null;
  distance_m: number | null;
  decision_index: number | null;
}

function fmt(v: number | null | undefined, digits = 0): string {
  return v === null || v === undefined ? "–" : v.toFixed(digits);
}

export default function PlayerCamCard({ player }: { player: string }) {
  const state = useStream();
  const lg = useLeague();
  const matchId = state.hello?.match_id;
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!matchId) return;
    let live = true;
    setStats(null);
    setError(false);
    fetch(`http://${API}/match/${matchId}/players/${player}/stats`)
      .then((r) => (r.ok ? (r.json() as Promise<Stats>) : Promise.reject(new Error(String(r.status)))))
      .then((s) => live && setStats(s))
      .catch(() => live && setError(true));
    return () => {
      live = false;
    };
  }, [matchId, player]);

  const info = lg?.players[player];
  const tag = state.cues.find((c) => c.layer === "player_tag" && (c.targets.players ?? []).includes(player));
  const cells: [string, string, string][] = [
    ["distance", stats?.distance_m != null ? fmt(stats.distance_m / 1000, 1) : "–", "km"],
    ["top speed", fmt(stats?.top_speed_kmh, 1), "km/h"],
    ["sprints", fmt(stats?.sprints), ""],
    ["touches", fmt(stats?.touches), ""],
    ["Decision Index", fmt(stats?.decision_index), ""],
  ];
  return (
    <section className="player-cam" data-testid="player-cam-card" data-player={player} data-loaded={stats !== null}>
      <header>
        <b className="shirt">{info?.shirt ?? ""}</b>
        <div>
          <h2>{info?.name ?? player}</h2>
          <small>{info ? `${lg?.clubs[info.club]?.short_name ?? info.club} · ${info.position}` : ""}</small>
        </div>
      </header>
      <dl>
        {cells.map(([label, value, unit]) => (
          <div key={label} data-stat={label}>
            <dt>{label}</dt>
            <dd>
              {value}
              {unit && value !== "–" ? <small> {unit}</small> : null}
            </dd>
          </div>
        ))}
      </dl>
      {tag && (
        <p className="tag" data-cue-id={tag.cue_id}>
          {tag.text.headline}
        </p>
      )}
      {error && <p className="err">Stats unavailable for this player.</p>}
    </section>
  );
}
