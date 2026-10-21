// Overlay state (TECH_PLAN 1.9): {frame, cues[], facts, oracle, profile} plus the bits the score bug and badges need.
import { modeAllows } from "../modes/config";
import type {
  Counterfactual,
  Cue,
  Fact,
  Hello,
  MatchEvent,
  Message,
  Oracle,
  TrackingFrame,
  ViewerProfile,
} from "./types";

export interface OverlayState {
  hello: Hello | null;
  frame: TrackingFrame | null;
  prevFrame: TrackingFrame | null;
  clock: number; // stream clock, ms of match time
  cues: Cue[]; // every cue not yet removed; visibility is decided against the clock
  facts: Record<string, Fact>; // latest fact per name
  counterfactuals: Record<string, Counterfactual>; // by counterfactual_id, for ghost trails and swing bars
  oracle: Oracle | null;
  profile: ViewerProfile | null;
  events: MatchEvent[]; // recent events, newest last (bounded)
  score: [number, number];
  mode: "replay" | "live" | "degraded";
  spend: { match_usd: number; day_usd: number } | null;
  pendingRequests: string[];
}

export const initialState: OverlayState = {
  hello: null,
  frame: null,
  prevFrame: null,
  clock: 0,
  cues: [],
  facts: {},
  counterfactuals: {},
  oracle: null,
  profile: null,
  events: [],
  score: [0, 0],
  mode: "replay",
  spend: null,
  pendingRequests: [],
};

const MAX_EVENTS = 200;

export type Action = { kind: "message"; msg: Message } | { kind: "reset" };

export function reducer(state: OverlayState, action: Action): OverlayState {
  if (action.kind === "reset") return initialState;
  const msg = action.msg;
  switch (msg.type) {
    case "hello": // a hello resets the screen: the API sends one on connect and after every seek
      return {
        ...initialState,
        hello: msg.payload,
        mode: msg.payload.mode,
        profile: msg.payload.viewer_profile ?? null,
        clock: msg.payload.t_ms ?? 0,
        score: msg.payload.score ? [msg.payload.score[0], msg.payload.score[1]] : [0, 0],
      };
    case "lineup":
      return state.hello ? { ...state, hello: { ...state.hello, player_ids: msg.payload.player_ids } } : state;
    case "tracking_frame": {
      const cues = state.cues.filter((c) => c.t_out_ms > msg.payload.t_ms);
      return { ...state, prevFrame: state.frame, frame: msg.payload, clock: msg.payload.t_ms, cues };
    }
    case "event": {
      const e = msg.payload;
      const score: [number, number] = [...state.score];
      if (e.type === "goal" && (e.team === "home" || e.team === "away")) score[e.team === "home" ? 0 : 1] += 1;
      const events = [...state.events, e].slice(-MAX_EVENTS);
      return { ...state, events, score };
    }
    case "fact":
      return { ...state, facts: { ...state.facts, [msg.payload.name]: msg.payload } };
    case "cue":
      return { ...state, cues: [...state.cues.filter((c) => c.cue_id !== msg.payload.cue_id), msg.payload] };
    case "counterfactual":
      return {
        ...state,
        counterfactuals: { ...state.counterfactuals, [msg.payload.counterfactual_id]: msg.payload },
      };
    case "cue_remove":
      return { ...state, cues: state.cues.filter((c) => c.cue_id !== msg.payload.cue_id) };
    case "oracle":
      return { ...state, oracle: msg.payload };
    case "mode":
      return { ...state, mode: msg.payload.mode };
    case "spend":
      return { ...state, spend: { match_usd: msg.payload.match_usd, day_usd: msg.payload.day_usd } };
    case "request_info":
      return { ...state, pendingRequests: [...state.pendingRequests, msg.payload.request_id] };
    case "moment":
    case "trace":
      return state; // studio-only messages
    default:
      return state; // unknown types are ignored
  }
}

/** Cues on screen at the current stream clock, for this overlay's viewer mode. */
export function visibleCues(state: OverlayState): Cue[] {
  return state.cues
    .filter((c) => c.t_in_ms <= state.clock && state.clock < c.t_out_ms && modeAllows(state, c))
    .sort((a, b) => b.priority - a.priority);
}

/** Match time a message belongs to, or null for untimed messages. */
export function messageTime(msg: Message): number | null {
  switch (msg.type) {
    case "tracking_frame":
    case "event":
    case "fact":
    case "oracle":
      return msg.payload.t_ms;
    case "cue":
      return msg.payload.t_in_ms;
    default:
      return null;
  }
}
