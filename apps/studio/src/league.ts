// League names for display (public/league.json from scripts/export_league_web.py); ids stay the source of truth.
import { useEffect, useState } from "react";

export interface LeagueWeb {
  golden: { home: string; away: string };
  clubs: Record<string, { name: string; short_name: string }>;
  players: Record<string, { shirt: number; name: string; club: string }>;
}

let pending: Promise<LeagueWeb | null> | null = null;

export function useLeague(): LeagueWeb | null {
  const [league, setLeague] = useState<LeagueWeb | null>(null);
  useEffect(() => {
    pending ??= fetch("league.json")
      .then((r) => r.json() as Promise<LeagueWeb>)
      .catch(() => null);
    let live = true;
    void pending.then((lg) => live && setLeague(lg));
    return () => {
      live = false;
    };
  }, []);
  return league;
}

export function playerName(lg: LeagueWeb | null, id: string, roster?: Record<string, string>): string {
  const p = lg?.players[id];
  if (p) return p.name.split(" ").slice(-1)[0];
  const real = roster?.[id]; // a real-clip match: names from its match metadata
  return real ? real.split(" ").slice(-1)[0] : id;
}
