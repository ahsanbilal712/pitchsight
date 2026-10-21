// Stream messages the fan app reads (TECH_PLAN 1.3, 1.9; copied from the overlay, trimmed).
export interface TrackingFrame {
  t_ms: number;
  period: number;
  p: number[][];
  ball_z: number;
  holder: number;
  possession: number;
}

export interface Hello {
  match_id: string;
  mode: "replay" | "live" | "degraded";
  replay_speed: number;
  t_ms?: number;
  score?: [number, number];
  player_ids?: string[];
  clubs?: { home: string; away: string } | null;
}

export interface Cue {
  cue_id: string;
  t_in_ms: number;
  t_out_ms: number;
  clock: string;
  layer: string;
  kind: string;
  priority: number;
  targets: { modes: string[]; clubs?: string[]; players?: string[] };
  text: { headline: string; body: string };
  verified: boolean;
  [key: string]: unknown;
}

export interface MatchEvent {
  id: string;
  t_ms: number;
  type: string;
  team: string;
  [key: string]: unknown;
}

export type Message =
  | { type: "hello"; payload: Hello }
  | { type: "tracking_frame"; payload: TrackingFrame }
  | { type: "event"; payload: MatchEvent }
  | { type: "cue"; payload: Cue }
  | { type: "cue_remove"; payload: { cue_id: string } }
  | { type: "lineup"; payload: { t_ms: number; player_ids: string[] } }
  | { type: "mode"; payload: { mode: "replay" | "live" | "degraded" } }
  | { type: string; payload: unknown };
