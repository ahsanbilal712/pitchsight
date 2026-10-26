// Message shapes the studio reads (copied from the overlay, studio fields added).
export interface ViewerProfile {
  schema_version: string;
  viewer_id: string;
  mode: string;
  [key: string]: unknown;
}

export interface Hello {
  match_id: string;
  mode: Mode;
  replay_speed: number;
  viewer_profile?: ViewerProfile;
  t_ms?: number;
  score?: [number, number];
  clubs?: { home: string; away: string } | null;
  /** {player_id: name} for a real-clip match, whose players are not in the league file. */
  roster?: Record<string, string>;
}

export type Mode = "replay" | "live" | "degraded";

export interface TrackingFrame {
  t_ms: number;
  period: number;
}

export interface MatchEvent {
  id: string;
  t_ms: number;
  type: string;
  team: string;
  player: string | null;
  [key: string]: unknown;
}

export interface Claim {
  text: string;
  kind: string;
  value: number | string | null;
  unit: string | null;
  evidence_ids: string[];
  verified: boolean;
  reject_reason?: string | null;
}

export interface Cue {
  cue_id: string;
  match_id: string;
  moment_id?: string | null;
  t_in_ms: number;
  t_out_ms: number;
  clock: string;
  layer: string;
  kind: string;
  priority: number;
  targets: { modes: string[]; clubs?: string[]; players?: string[] };
  text: { headline: string; body: string };
  graphics?: { pitch_control_snapshot?: string | null; bar?: { label?: string; from?: number; to?: number } | null };
  explain: {
    why: string;
    claims: Claim[];
    counterfactual_id?: string | null;
    explanation_id?: string | null;
  };
  verified: boolean;
  producer_status: "auto" | "approved" | "vetoed" | "held";
  provenance: { mode: string; agent_path: string[]; model?: string | null; resumed_from_checkpoint?: string | null };
  [key: string]: unknown;
}

export interface Fact {
  fact_id?: string;
  id?: string;
  t_ms: number;
  kind?: string;
  name: string;
  value: number | string;
  unit?: string | null;
  [key: string]: unknown;
}

export interface Moment {
  moment_id: string;
  t_ms: number;
  clock?: string;
  kind: string;
  leverage?: number | null;
  players?: string[];
  team?: string | null;
  status?: string;
  fast?: boolean;
  [key: string]: unknown;
}

export interface Trace {
  trace_row_id?: string;
  run_id?: string;
  moment_id?: string;
  executor: string;
  branch?: string | null;
  started_ms?: number;
  latency_ms?: number;
  model?: string | null;
  tokens_in?: number;
  tokens_out?: number;
  cost_usd?: number;
  cache_hit?: boolean | null;
  status: string;
  [key: string]: unknown;
}

export interface Spend {
  match_usd: number | null;
  day_usd: number;
  project_usd?: number;
  caps: { match: number; day: number; project?: number };
}

export interface RequestInfo {
  request_id: string;
  cue?: Cue;
  /** Set when the request was decided (approved or vetoed), by any producer or the demo runner. */
  decision?: "approved" | "vetoed";
}

export type Message =
  | { type: "hello"; payload: Hello }
  | { type: "tracking_frame"; payload: TrackingFrame }
  | { type: "event"; payload: MatchEvent }
  | { type: "fact"; payload: Fact }
  | { type: "moment"; payload: Moment }
  | { type: "cue"; payload: Cue }
  | { type: "cue_remove"; payload: { cue_id: string } }
  | { type: "trace"; payload: Trace }
  | { type: "request_info"; payload: RequestInfo }
  | { type: "mode"; payload: { mode: Mode; reason?: string | null } }
  | { type: "spend"; payload: Spend }
  | { type: "counterfactual"; payload: { counterfactual_id: string; [key: string]: unknown } }
  | { type: "oracle"; payload: Record<string, unknown> }
  | { type: "lineup"; payload: Record<string, unknown> };
