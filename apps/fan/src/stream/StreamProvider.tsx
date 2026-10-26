// Fan stream (pattern copied from apps/overlay; apps do not import each other). Subscribes with
// WS /ws?viewer_id&mode&club&player for the current profile; the api filters cues by targets and mode kinds
//, so a profile change reconnects and the feed starts again from the server's snapshot.
import { createContext, useContext, useEffect, useReducer, useRef, type ReactNode } from "react";
import type { ViewerProfile } from "../profile";
import { initialState, reducer, type FanState } from "./reducer";
import type { Message } from "./types";

const API = new URLSearchParams(window.location.search).get("api") ?? "localhost:8000";

const StreamContext = createContext<FanState>(initialState);

export function useStream(): FanState {
  return useContext(StreamContext);
}

declare global {
  interface Window {
    __whyline?: { ready: boolean; debug: () => Record<string, unknown> };
  }
}

export function StreamProvider({ profile, children }: { profile: ViewerProfile; children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const received = useRef<{ cue_id: string; kind: string }[]>([]);
  const { viewer_id, mode, club, player } = profile;

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;
    let backoff = 500;
    dispatch({ kind: "reset" });
    received.current = [];
    const q = new URLSearchParams({ viewer_id, mode, club: club ?? "", player: player ?? "" });
    const connect = () => {
      ws = new WebSocket(`ws://${API}/ws?${q.toString()}`);
      ws.onopen = () => {
        backoff = 500;
      };
      ws.onmessage = (ev) => {
        for (const line of String(ev.data).split("\n")) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line) as Message;
          if (msg.type === "cue") {
            const c = msg.payload as { cue_id: string; kind: string };
            received.current.push({ cue_id: c.cue_id, kind: c.kind });
          }
          dispatch({ kind: "message", msg });
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
  }, [viewer_id, mode, club, player]);

  useEffect(() => {
    window.__whyline = {
      ready: state.hello !== null && state.frame !== null,
      debug: () => ({
        clock: state.clock,
        mode,
        kinds: [...new Set(received.current.map((r) => r.kind))].sort(),
        received: received.current.map((r) => r.cue_id),
        feed: state.cues.map((c) => c.cue_id),
      }),
    };
  }, [state, mode]);

  return <StreamContext.Provider value={state}>{children}</StreamContext.Provider>;
}
