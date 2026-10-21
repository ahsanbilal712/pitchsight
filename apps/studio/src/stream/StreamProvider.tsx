// Studio stream (pattern copied from apps/overlay; apps do not import each other). Connects as mode=studio, so
// the api sends every cue and the studio-only messages. On each hello it also loads the match's full cue list
// and the spend totals over REST, so the cue log survives seeks and late connects.
import { createContext, useContext, useEffect, useReducer, type ReactNode } from "react";
import { API, http } from "../api";
import { initialState, reducer, type Action, type StudioState } from "./reducer";
import type { Cue, Message, Spend } from "./types";

interface StreamApi {
  state: StudioState;
  dispatch: (a: Action) => void;
}

const StreamContext = createContext<StreamApi>({ state: initialState, dispatch: () => undefined });

export function useStream(): StreamApi {
  return useContext(StreamContext);
}

declare global {
  interface Window {
    __whyline?: { ready: boolean; debug: () => Record<string, unknown> };
  }
}

export function StreamProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;
    let backoff = 500;
    const connect = () => {
      ws = new WebSocket(`ws://${API}/ws?viewer_id=studio&mode=studio`);
      ws.onopen = () => {
        backoff = 500;
      };
      ws.onmessage = (ev) => {
        for (const line of String(ev.data).split("\n")) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line) as Message;
          dispatch({ kind: "message", msg });
          if (msg.type === "hello") {
            void fetch(http(`/match/${msg.payload.match_id}/cues?viewer=studio`))
              .then((r) => (r.ok ? (r.json() as Promise<Cue[]>) : []))
              .then((cues) => dispatch({ kind: "cues", cues }))
              .catch(() => undefined);
            void fetch(http("/spend"))
              .then((r) => (r.ok ? (r.json() as Promise<Spend>) : null))
              .then((spend) => spend && dispatch({ kind: "message", msg: { type: "spend", payload: spend } }))
              .catch(() => undefined);
          }
        }
      };
      ws.onclose = () => {
        if (closed) return;
        retry = window.setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 8000);
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) window.clearTimeout(retry);
      ws?.close();
    };
  }, []);

  useEffect(() => {
    window.__whyline = {
      ready: state.hello !== null,
      debug: () => ({
        clock: state.clock,
        mode: state.mode,
        cues: Object.keys(state.cues).length,
        traces: state.traces.length,
        requests: state.requests.map((r) => r.request_id),
      }),
    };
  }, [state]);

  return <StreamContext.Provider value={{ state, dispatch }}>{children}</StreamContext.Provider>;
}
