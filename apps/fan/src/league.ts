// League data for display (public/league.json from scripts/export_league_web.py, copied per app).
import { useEffect, useState } from "react";

export interface Kit {
  primary: string;
  secondary: string;
}

export interface LeagueWeb {
  golden: { home: string; away: string };
  clubs: Record<string, { name: string; short_name: string; home_kit: Kit; away_kit: Kit }>;
  players: Record<string, { shirt: number; name: string; club: string; position: string }>;
}

let pending: Promise<LeagueWeb | null> | null = null;
let loaded: LeagueWeb | null = null;

export function loadLeague(): Promise<LeagueWeb | null> {
  pending ??= fetch("league.json")
    .then((r) => r.json() as Promise<LeagueWeb>)
    .then((lg) => (loaded = lg))
    .catch(() => null);
  return pending;
}

export function leagueNow(): LeagueWeb | null {
  return loaded;
}

export function useLeague(): LeagueWeb | null {
  const [league, setLeague] = useState<LeagueWeb | null>(loaded);
  useEffect(() => {
    let live = true;
    void loadLeague().then((lg) => live && setLeague(lg));
    return () => {
      live = false;
    };
  }, []);
  return league;
}

export function surname(lg: LeagueWeb | null, id: string): string {
  const name = lg?.players[id]?.name;
  return name ? name.split(" ").slice(-1)[0] : id;
}

/** WCAG contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const n = parseInt(hex.replace("#", "").slice(0, 6), 16);
    const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
      const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
