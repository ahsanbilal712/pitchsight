// Feeds the overlay reducer from the API WebSocket, or with ?fixture=1 from the T-003 sample stream
// replayed on the same 10 Hz clock. Exposes seek() for the recorder through window.__whyline.
import { createContext, useCallback, useContext, useEffect, useReducer, useRef, type ReactNode } from "react";
import { API } from "../api";
import { FIXTURE, parseClock } from "../record";
import { initialState, messageTime, reducer, visibleCues, type OverlayState } from "./reducer";
import type { Message } from "./types";

const TICK_MS = 100;
const FIXTURE_URL = "fixtures/sample_stream.jsonl";

interface StreamApi {
  state: OverlayState;
  seek: (clock: string | number) => void;
}

const StreamContext = createContext<StreamApi>({ state: initialState, seek: () => undefined });

export function useStream(): StreamApi {
  return useContext(StreamContext);
}

type Act = Parameters<typeof reducer>[1] | { kind: "replace"; state: OverlayState };

function rootReducer(state: OverlayState, action: Act): OverlayState {
  return action.kind === "replace" ? action.state : reducer(state, action);
}

function wsUrl(): string {
  const page = new URLSearchParams(window.location.search);
  const q = new URLSearchParams();
  for (const key of ["viewer_id", "mode", "club", "player"]) q.set(key, page.get(key) ?? "");
  if (!q.get("viewer_id")) q.set("viewer_id", "overlay");
  if (!q.get("mode")) q.set("mode", "analyst");
  return `ws://${API}/ws?${q.toString()}`;
}

export function StreamProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(rootReducer, initialState);
  const messages = useRef<Message[]>([]);
  const times = useRef<number[]>([]); // match time per message; untimed ones take the next timed message's time
  const cursor = useRef(0);
  const clock = useRef(0);
  const speed = useRef(1);
  const framesSeen = useRef(0);
  const paused = useRef(false);

  // fixture playback: everything up to `clock` has been dispatched
  const fold = useCallback((until: number) => {
    let s = initialState;
    let i = 0;
    for (; i < messages.current.length; i++) {
      if (times.current[i] > until) break;
      s = reducer(s, { kind: "message", msg: messages.current[i] });
    }
    cursor.current = i;
    clock.current = until;
    dispatch({ kind: "replace", state: s });
  }, []);

  useEffect(() => {
    if (!FIXTURE) return;
    let timer: number | undefined;
    let cancelled = false;
    fetch(FIXTURE_URL)
      .then((r) => r.text())
      .then((text) => {
        if (cancelled) return;
        messages.current = text
          .split("\n")
          .filter((l) => l.trim())
          .map((l) => JSON.parse(l) as Message);
        // a cue_remove sits just before the frame it belongs to, so it must not fire with the frame before it
        let next = Infinity;
        times.current = new Array<number>(messages.current.length);
        for (let i = messages.current.length - 1; i >= 0; i--) {
          next = messageTime(messages.current[i]) ?? next;
          times.current[i] = next;
        }
        const hello = messages.current.find((m) => m.type === "hello");
        if (hello && hello.type === "hello" && hello.payload.viewer_profile) {
          // ?mode=&player=&club= pick the viewer in fixture mode, as the query string does for the api
          const page = new URLSearchParams(window.location.search);
          const vp = { ...hello.payload.viewer_profile };
          const mode = page.get("mode");
          if (mode === "analyst" || mode === "casual" || mode === "player_cam" || mode === "studio") vp.mode = mode;
          if (page.get("player")) vp.player = page.get("player");
          const club = page.get("club");
          if (club === "home" || club === "away") vp.club = club;
          vp.show_heatmap = vp.mode === "analyst" || vp.mode === "studio";
          hello.payload = { ...hello.payload, viewer_profile: vp };
        }
        if (hello && hello.type === "hello") speed.current = hello.payload.replay_speed || 1;
        const first = messages.current.find((m) => m.type === "tracking_frame");
        fold(first ? (messageTime(first) ?? 0) : 0);
        timer = window.setInterval(() => {
          if (paused.current) return;
          const next = clock.current + TICK_MS * speed.current;
          const batch: Message[] = [];
          while (cursor.current < messages.current.length && times.current[cursor.current] <= next) {
            batch.push(messages.current[cursor.current]);
            cursor.current += 1;
          }
          clock.current = next;
          for (const msg of batch) {
            if (msg.type === "tracking_frame") framesSeen.current += 1;
            dispatch({ kind: "message", msg });
          }
        }, TICK_MS);
      });
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [fold]);

  useEffect(() => {
    if (FIXTURE) return;
    let ws: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;
    let backoff = 500;
    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => {
        backoff = 500;
      };
      ws.onmessage = (ev) => {
        for (const line of String(ev.data).split("\n")) {
          if (!line.trim()) continue;
          const msg = JSON.parse(line) as Message;
          if (msg.type === "tracking_frame") framesSeen.current += 1;
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
  }, []);

  const seek = useCallback(
    (c: string | number) => {
      const ms = parseClock(c);
      if (FIXTURE) {
        fold(ms);
        return;
      }
      void fetch(`http://${API}/replay/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "seek", t_ms: ms }),
      });
    },
    [fold],
  );

  // record-mode handle for the Playwright recorder
  useEffect(() => {
    const handle = window.__whyline;
    if (!handle) return;
    handle.seek = seek;
    handle.pause = (on: boolean) => {
      paused.current = on;
    };
    handle.inject = (msg: unknown) => dispatch({ kind: "message", msg: msg as Message });
    handle.debug = () => ({
      clock: clock.current || state.clock,
      visibleCues: visibleCues(state).map((c) => c.cue_id),
      frames: framesSeen.current,
    });
    handle.ready = Boolean(state.frame && state.hello && (handle.gate ? handle.gate() : true));
  }, [seek, state]);

  return <StreamContext.Provider value={{ state, seek }}>{children}</StreamContext.Provider>;
}
