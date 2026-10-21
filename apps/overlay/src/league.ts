// League data for rendering (public/league.json, written by scripts/export_league_web.py). The stream carries
// ids only; names, shirt numbers and kit colours are resolved here, at render time.
import { useEffect, useState } from "react";
import type { Hello } from "./stream/types";

export interface Kit {
  primary: string;
  secondary: string;
}

export interface ClubWeb {
  name: string;
  short_name: string;
  home_kit: Kit;
  away_kit: Kit;
}

export interface PlayerWeb {
  shirt: number;
  name: string;
  club: string;
  position: string;
}

export interface LeagueWeb {
  golden: { home: string; away: string };
  clubs: Record<string, ClubWeb>;
  players: Record<string, PlayerWeb>;
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

/** Club ids of the match: from the API hello when it says, else the golden pairing. */
export function matchClubs(lg: LeagueWeb, hello: Hello | null): { home: string; away: string } {
  return hello?.clubs ?? lg.golden;
}

/** Home side wears its home kit, away side its away kit. */
export function matchKits(lg: LeagueWeb, hello: Hello | null): [Kit, Kit] {
  const { home, away } = matchClubs(lg, hello);
  return [lg.clubs[home].home_kit, lg.clubs[away].away_kit];
}

/** "Zoltan Fennimore" -> "Fennimore"; unknown ids fall back to the id itself. */
export function surname(lg: LeagueWeb | null, playerId: string): string {
  const name = lg?.players[playerId]?.name;
  return name ? name.split(" ").slice(-1)[0] : playerId;
}

/** WCAG relative luminance of a #rrggbb colour. */
export function luminance(hex: string): number {
  const n = parseInt(hex.replace("#", "").slice(0, 6), 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}

/** WCAG contrast ratio between two #rrggbb colours (1 to 21). */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
