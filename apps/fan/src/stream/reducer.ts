// Fan state: the latest frame, score, lineup and the cues this profile was sent (the server filters them).
import type { Cue, Hello, Message, TrackingFrame } from "./types";

export interface FanState {
  hello: Hello | null;
  frame: TrackingFrame | null;
  clock: number;
  score: [number, number];
  playerIds: string[];
  cues: Cue[]; // newest first; a feed keeps cues after t_out, a veto (cue_remove) takes them out
  mode: "replay" | "live" | "degraded";
}

export const initialState: FanState = {
  hello: null,
  frame: null,
  clock: 0,
  score: [0, 0],
  playerIds: [],
  cues: [],
  mode: "replay",
};

const MAX_CUES = 60;

export type Action = { kind: "message"; msg: Message } | { kind: "reset" };

export function reducer(state: FanState, action: Action): FanState {
  if (action.kind === "reset") return initialState;
  const msg = action.msg;
  switch (msg.type) {
    case "hello": {
      const h = msg.payload as Hello;
      return {
        ...initialState,
        hello: h,
        mode: h.mode,
        clock: h.t_ms ?? 0,
        score: h.score ? [h.score[0], h.score[1]] : [0, 0],
        playerIds: h.player_ids ?? [],
      };
    }
    case "tracking_frame": {
      const f = msg.payload as TrackingFrame;
      return { ...state, frame: f, clock: f.t_ms };
    }
    case "event": {
      const e = msg.payload as { type: string; team: string };
      if (e.type !== "goal" || (e.team !== "home" && e.team !== "away")) return state;
      const score: [number, number] = [...state.score];
      score[e.team === "home" ? 0 : 1] += 1;
      return { ...state, score };
    }
    case "lineup":
      return { ...state, playerIds: (msg.payload as { player_ids: string[] }).player_ids };
    case "cue": {
      const c = msg.payload as Cue;
      const rest = state.cues.filter((x) => x.cue_id !== c.cue_id);
      return { ...state, cues: [c, ...rest].sort((a, b) => b.t_in_ms - a.t_in_ms).slice(0, MAX_CUES) };
    }
    case "cue_remove": {
      const id = (msg.payload as { cue_id: string }).cue_id;
      return { ...state, cues: state.cues.filter((c) => c.cue_id !== id) };
    }
    case "mode":
      return { ...state, mode: (msg.payload as { mode: FanState["mode"] }).mode };
    default:
      return state;
  }
}
