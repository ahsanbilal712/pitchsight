// Message shapes of the WHYLINE stream. Envelope: {type, payload}.

export interface TrackingFrame {
  t_ms: number;
  period: number;
  p: number[][]; // 23 rows of [x, y, vx, vy]: 0-10 home, 11-21 away, 22 ball
  ball_z: number;
  holder: number;
  possession: number;
}

export interface ViewerProfile {
  schema_version: string;
  viewer_id: string;
  mode: "analyst" | "casual" | "player_cam" | "studio";
  club?: "home" | "away" | null;
  player?: string | null;
  metric?: string | null;
  high_contrast?: boolean;
  show_heatmap?: boolean;
}

export interface Hello {
  match_id: string;
  mode: "replay" | "live" | "degraded";
  replay_speed: number;
  viewer_profile?: ViewerProfile;
  player_ids?: string[]; // row order, substitutions applied
  t_ms?: number; // API: clock this hello resets the screen to (sent on connect and after every seek)
  score?: [number, number];
  clubs?: { home: string; away: string }; // club ids, from the match_metadata event
}

export interface MatchEvent {
  id: string;
  t_ms: number;
  type: string;
  team: "home" | "away" | "none";
  player: string | null;
  [key: string]: unknown;
}

export interface Cue {
  cue_id: string;
  t_in_ms: number;
  t_out_ms: number;
  layer: string;
  kind: string;
  priority: number;
  text: { headline: string; body: string };
  [key: string]: unknown;
}

export interface Fact {
  id: string;
  t_ms: number;
  name: string;
  value: number | string; // indices are numbers; state facts (chaos_state) carry a label
  [key: string]: unknown;
}

export interface CfOutcome {
  p_goal_home: number;
  p_goal_away: number;
  win_prob_home: number;
  ci95_win_prob_home?: [number, number];
  [key: string]: unknown;
}

/** schemas/counterfactual.schema.json (fields the screens use). */
export interface Counterfactual {
  counterfactual_id: string;
  t_ms: number;
  engine: string;
  n: number;
  horizon_s: number;
  seed: number;
  baseline: CfOutcome;
  alternative_outcome: CfOutcome;
  delta_win_prob_home: number;
  futures_sample?: number[][][]; // first half baseline futures, second half alternative (cue contract gap 7)
  [key: string]: unknown;
}

export interface Oracle {
  t_ms: number;
  p_shot_home: number;
  p_shot_away: number;
  zone?: unknown;
  shooter?: string | null;
}

export type Message =
  | { type: "hello"; payload: Hello }
  | { type: "tracking_frame"; payload: TrackingFrame }
  | { type: "event"; payload: MatchEvent }
  | { type: "fact"; payload: Fact }
  | { type: "moment"; payload: Record<string, unknown> }
  | { type: "cue"; payload: Cue }
  | { type: "cue_remove"; payload: { cue_id: string } }
  | { type: "trace"; payload: Record<string, unknown> }
  | { type: "request_info"; payload: { request_id: string; cue: Cue } }
  | { type: "mode"; payload: { mode: "replay" | "live" | "degraded"; reason?: string } }
  | { type: "spend"; payload: { match_usd: number; day_usd: number; caps: Record<string, number> } }
  | { type: "oracle"; payload: Oracle }
  | { type: "lineup"; payload: { t_ms: number; player_ids: string[] } }
  | { type: "counterfactual"; payload: Counterfactual };
