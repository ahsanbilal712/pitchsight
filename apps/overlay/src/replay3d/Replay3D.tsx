// /replay3d?cf=<counterfactual id> (TECH_PLAN 1.9, ADR-008): the Sliding Doors moment as a stylised 3D scene.
// Players and ball follow the stream (fixture or api) at the replay clock; from the branch point the 200 ghost
// futures fan out over the horizon, the chosen alternative is an orange dashed trail and the DOM swing bar moves
// from baseline to alternative. Cameras: ?cam=wide|player, key C, or window.__whyline.camera(name).
// ?ghost=full shows the whole fan at once (stills). Record mode as everywhere: ?record=1, DPR 1, seek(clock).
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import { fetchDoc } from "../api";
import { loadLeague, surname, useLeague } from "../league";
import { canvasDpr, FIXTURE, RECORD } from "../record";
import { useStream } from "../stream/StreamProvider";
import type { Counterfactual } from "../stream/types";
import Ball from "./Ball";
import Cameras, { type CamName } from "./Cameras";
import GhostPaths from "./GhostPaths";
import Players, { type FrameRef } from "./Players";
import Stadium from "./Stadium";
import SwingBarOverlay from "./SwingBarOverlay";
import "./replay3d.css";

const params = new URLSearchParams(window.location.search);
const LEAD_MS = 3000; // the scene opens this long before the branch point
const FADE_MS = 800;

type Pt = [number, number];

function clockText(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Counts rendered frames, for the record-mode fps check. */
function FrameMeter({ stamps, onFirst }: { stamps: React.RefObject<number[]>; onFirst: () => void }) {
  const fired = useRef(false);
  useFrame(() => {
    const s = stamps.current!;
    s.push(performance.now());
    if (s.length > 4000) s.splice(0, s.length - 4000);
    if (!fired.current) {
      fired.current = true;
      onFirst();
    }
  });
  return null;
}

function meanPath(paths: Pt[][]): Pt[] {
  if (!paths.length) return [];
  const n = Math.min(...paths.map((p) => p.length));
  return Array.from({ length: n }, (_, i) => [
    paths.reduce((a, p) => a + p[i][0], 0) / paths.length,
    paths.reduce((a, p) => a + p[i][1], 0) / paths.length,
  ]);
}

export default function Replay3D() {
  const { state, seek } = useStream();
  const lg = useLeague();
  const cfId = params.get("cf") ?? Object.keys(state.counterfactuals)[0] ?? null;
  const [cf, setCf] = useState<Counterfactual | null>(null);
  const [cam, setCam] = useState<CamName>(params.get("cam") === "player" ? "player" : "wide");
  const [rendered, setRendered] = useState(false);
  const seeked = useRef(false);
  const stamps = useRef<number[]>([]);
  const frames = useRef<FrameRef>({ prev: null, cur: null, at: 0 });
  if (state.frame && state.frame !== frames.current.cur) {
    frames.current = { prev: state.prevFrame, cur: state.frame, at: performance.now() };
  }

  useEffect(() => {
    void loadLeague();
  }, []);

  // the counterfactual: from the stream if it already came with a cue, else by id from the doc endpoint (the
  // fixture serves the same document under fixtures/docs/)
  const matchId = state.hello?.match_id;
  useEffect(() => {
    if (!cfId || cf) return;
    const streamed = state.counterfactuals[cfId];
    if (streamed) setCf(streamed);
    else if (matchId) void fetchDoc(matchId, cfId).then((d) => d && setCf(d as unknown as Counterfactual));
  }, [cfId, cf, state.counterfactuals, matchId]);

  // fixture playback opens a few seconds before the branch point; against the api the seek moves every screen's
  // clock, so it happens only when asked (?autoseek=1) and the recorder normally seeks itself
  useEffect(() => {
    if (!cf || seeked.current || !state.frame || !(FIXTURE || params.get("autoseek") === "1")) return;
    seeked.current = true;
    seek(Math.max(0, cf.t_ms - LEAD_MS));
  }, [cf, state.frame, seek]);

  // record-mode handle: camera switch, fps, and "ready" only once the scene has drawn a frame
  useEffect(() => {
    const h = window.__whyline;
    if (!h) return;
    h.gate = () => cf !== null && rendered;
    h.camera = (name: string) => setCam(name === "player" ? "player" : "wide");
    h.fps = (windowMs: number) => {
      const s = stamps.current;
      const now = performance.now();
      const inWindow = s.filter((t) => now - t <= windowMs);
      return inWindow.length / (windowMs / 1000);
    };
    h.scene = () => ({ cam, cf: cf?.counterfactual_id ?? null, rendered });
  }, [cf, rendered, cam]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "c" || e.key === "C") setCam((c) => (c === "wide" ? "player" : "wide"));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const clock = state.clock;
  const full = params.get("ghost") === "full";
  const progress = cf ? (full ? 1 : Math.max(0, Math.min(1, (clock - cf.t_ms) / (cf.horizon_s * 1000)))) : 0;
  const fade = cf ? (full ? 1 : Math.max(0, Math.min(1, (clock - cf.t_ms) / FADE_MS))) : 0;

  const trail = useMemo<Pt[]>(() => {
    if (!cf) return [];
    const cue = state.cues.find((c) => (c.explain as { counterfactual_id?: string } | undefined)?.counterfactual_id === cf.counterfactual_id);
    const t = (cue?.graphics as { ghost_trail?: Pt[] } | undefined)?.ghost_trail;
    if (t && t.length >= 2) return t;
    const half = Math.floor((cf.futures_sample?.length ?? 0) / 2);
    return meanPath(((cf.futures_sample ?? []) as Pt[][]).slice(half));
  }, [cf, state.cues]);

  const actor = (cf?.actual as { actor?: string } | undefined)?.actor ?? null;
  const alt = cf?.alternative as { kind?: string; target?: string | null } | undefined;
  const ids = state.hello?.player_ids ?? [];
  const actorRow = actor ? ids.indexOf(actor) : -1;
  const attackRight = actorRow >= 0 && state.frame ? state.frame.p[actorRow][0] > 52.5 : true;

  return (
    <div className="r3d-stage" data-cam={cam}>
      <Canvas
        className="r3d-canvas"
        dpr={canvasDpr()}
        shadows
        gl={{ antialias: true, preserveDrawingBuffer: RECORD }}
        camera={{ fov: 34, near: 0.5, far: 600, position: [0, 40, 78] }}
      >
        <Stadium />
        <Players frames={frames} state={state} focus={actor} />
        <Ball frames={frames} />
        {cf && <GhostPaths cf={cf} trail={trail} progress={progress} fade={fade} />}
        <Cameras frames={frames} cam={cam} actorRow={actorRow} attackRight={attackRight} />
        <FrameMeter stamps={stamps} onFirst={() => setRendered(true)} />
      </Canvas>
      <div className="safe-area r3d-dom">
        <header className="r3d-caption" data-testid="r3d-caption">
          <span className="r3d-kicker">Sliding Doors · {cf ? clockText(cf.t_ms) : "--:--"}</span>
          {cf && actor && (
            <span className="r3d-what">
              {surname(lg, actor)}: {String((cf.actual as { kind?: string }).kind ?? "")} · alternative:{" "}
              {alt?.kind}
              {alt?.target ? ` to ${alt.target.startsWith("p_") ? surname(lg, alt.target) : alt.target}` : ""}
            </span>
          )}
          <span className="r3d-clock" data-testid="r3d-clock">
            {clockText(clock)} · {cam === "wide" ? "wide" : "behind the player"}
          </span>
        </header>
        {cf && progress > 0 && <SwingBarOverlay cf={cf} hello={state.hello} progress={progress} />}
        {!cfId && <p className="r3d-empty">No counterfactual: open /replay3d?cf=cf_000077</p>}
      </div>
    </div>
  );
}
