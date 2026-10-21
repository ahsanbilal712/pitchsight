// Studio state (TECH_PLAN 1.9 studio tree). Unlike the overlay, the studio keeps history across a seek: the
// cue list, moments and trace rows are a log of what the newsroom did; a `hello` only moves the clock.
import type { Cue, Fact, Hello, Message, Mode, Moment, RequestInfo, Spend, Trace } from "./types";

export interface StudioState {
  hello: Hello | null;
  clock: number;
  period: number;
  score: [number, number];
  mode: Mode;
  modeReason: string | null;
  spend: Spend | null;
  cues: Record<string, Cue>;
  removed: Record<string, true>; // cue_remove seen (veto)
  moments: Record<string, Moment>;
  traces: Trace[];
  facts: Record<string, Fact>;
  requests: RequestInfo[];
}

export const initialState: StudioState = {
  hello: null,
  clock: 0,
  period: 1,
  score: [0, 0],
  mode: "replay",
  modeReason: null,
  spend: null,
  cues: {},
  removed: {},
  moments: {},
  traces: [],
  facts: {},
  requests: [],
};

const MAX_TRACES = 400;

export type Action = { kind: "message"; msg: Message } | { kind: "cues"; cues: Cue[] } | { kind: "resolved"; id: string };

function traceKey(t: Trace): string {
  return t.trace_row_id ?? `${t.run_id}/${t.executor}/${t.started_ms}/${t.status}`;
}

export function reducer(state: StudioState, action: Action): StudioState {
  if (action.kind === "cues") {
    const cues = { ...state.cues };
    for (const c of action.cues) cues[c.cue_id] = c;
    return { ...state, cues };
  }
  if (action.kind === "resolved") {
    return { ...state, requests: state.requests.filter((r) => r.request_id !== action.id) };
  }
  const msg = action.msg;
  switch (msg.type) {
    case "hello": {
      const sameMatch = state.hello?.match_id === msg.payload.match_id;
      const base = sameMatch ? state : initialState;
      return {
        ...base,
        hello: msg.payload,
        mode: msg.payload.mode,
        clock: msg.payload.t_ms ?? base.clock,
        score: msg.payload.score ? [msg.payload.score[0], msg.payload.score[1]] : base.score,
      };
    }
    case "tracking_frame":
      return { ...state, clock: msg.payload.t_ms, period: msg.payload.period };
    case "event": {
      const e = msg.payload;
      if (e.type !== "goal" || (e.team !== "home" && e.team !== "away")) return state;
      const score: [number, number] = [...state.score];
      score[e.team === "home" ? 0 : 1] += 1;
      return { ...state, score };
    }
    case "fact":
      return { ...state, facts: { ...state.facts, [msg.payload.name]: msg.payload } };
    case "moment":
      return { ...state, moments: { ...state.moments, [msg.payload.moment_id]: msg.payload } };
    case "cue": {
      const removed = { ...state.removed };
      if (msg.payload.producer_status !== "vetoed") delete removed[msg.payload.cue_id];
      return { ...state, cues: { ...state.cues, [msg.payload.cue_id]: msg.payload }, removed };
    }
    case "cue_remove":
      return { ...state, removed: { ...state.removed, [msg.payload.cue_id]: true } };
    case "trace": {
      const key = traceKey(msg.payload);
      if (state.traces.some((t) => traceKey(t) === key)) return state;
      return { ...state, traces: [...state.traces, msg.payload].slice(-MAX_TRACES) };
    }
    case "request_info":
      if (state.requests.some((r) => r.request_id === msg.payload.request_id)) return state;
      return { ...state, requests: [...state.requests, msg.payload] };
    case "mode":
      return { ...state, mode: msg.payload.mode, modeReason: msg.payload.reason ?? null };
    case "spend":
      return { ...state, spend: msg.payload };
    default:
      return state; // counterfactual, oracle, lineup and unknown types: the studio fetches docs on demand
  }
}

/** A cue's status as the producer sees it. */
export function cueStatus(state: StudioState, cue: Cue): string {
  return state.removed[cue.cue_id] ? "vetoed" : cue.producer_status;
}
