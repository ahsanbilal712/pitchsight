// Demo controls (TECH_PLAN 1.9 studio, 1.8 demo script): kill the newsroom worker, replay speed x1/x2/x5/x10,
// play/pause and seek to a clock (mm:ss). Kill posts POST /demo/kill {target: "newsroom"}; the rest post
// /replay/control.
import { useState } from "react";
import { post } from "../api";
import { useStream } from "../stream/StreamProvider";

const SPEEDS = [1, 2, 5, 10];

export default function DemoControls() {
  const { state } = useStream();
  const [seekTo, setSeekTo] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [speed, setSpeed] = useState<number | null>(null);

  const control = async (body: Record<string, unknown>) => {
    const r = await post("/replay/control", body);
    setNote(r.ok ? null : `replay/control ${r.status}`);
    return r.ok;
  };

  const kill = async () => {
    const r = await post("/demo/kill", { target: "newsroom" });
    setNote(r.ok ? "kill sent: newsroom" : `kill failed ${r.status}`);
  };

  const seek = async () => {
    if (!/^\d{1,3}:\d{2}$/.test(seekTo.trim())) {
      setNote("seek wants mm:ss");
      return;
    }
    await control({ action: "seek", value: seekTo.trim() });
  };

  const current = speed ?? state.hello?.replay_speed ?? 1;
  return (
    <section className="panel demo" data-testid="demo-controls">
      <h2>Demo controls</h2>
      <div className="row">
        <button type="button" className="kill" data-testid="kill" onClick={() => void kill()}>
          Kill newsroom
        </button>
        <button type="button" onClick={() => void control({ action: "pause" })} data-testid="pause">
          Pause
        </button>
        <button type="button" onClick={() => void control({ action: "play" })} data-testid="play">
          Play
        </button>
      </div>
      <div className="row speeds">
        {SPEEDS.map((s) => (
          <button
            key={s}
            type="button"
            data-testid={`speed-${s}`}
            aria-pressed={current === s}
            onClick={() => void control({ action: "speed", value: s }).then((ok) => ok && setSpeed(s))}
          >
            x{s}
          </button>
        ))}
      </div>
      <form
        className="row"
        onSubmit={(e) => {
          e.preventDefault();
          void seek();
        }}
      >
        <input
          data-testid="seek-input"
          value={seekTo}
          placeholder="mm:ss"
          onChange={(e) => setSeekTo(e.target.value)}
          aria-label="Seek to clock"
        />
        <button type="submit" data-testid="seek">
          Seek
        </button>
      </form>
      {note && (
        <p className="note" data-testid="demo-note">
          {note}
        </p>
      )}
    </section>
  );
}
