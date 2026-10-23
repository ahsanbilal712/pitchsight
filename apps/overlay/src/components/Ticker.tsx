// Ticker (TECH_PLAN 1.9, cue contract): bottom strip with the headline of one visible `ticker` cue at a time,
// newest first, rotating every 4 s of match time when several are up. One 60-character headline always fits.
// Hidden in modes without a ticker (casual).
import { modeConfig } from "../modes/config";
import { visibleCues } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";
import { usePresence } from "./motion";

const ROTATE_MS = 4000;

export default function Ticker() {
  const { state } = useStream();
  const items = visibleCues(state)
    .filter((c) => c.layer === "ticker")
    .sort((a, b) => b.t_in_ms - a.t_in_ms || a.cue_id.localeCompare(b.cue_id));
  const current = items.length ? [items[Math.floor(state.clock / ROTATE_MS) % items.length]] : [];
  const shown = usePresence(current, (c) => c.cue_id);
  if (!modeConfig(state).ticker) return null; // casual hides the ticker (TECH_PLAN 1.9)
  return (
    <div className="ticker" data-testid="ticker" data-empty={items.length === 0} data-count={items.length}>
      <span className="tk-label">PITCHSIGHT</span>
      <ul className="tk-items">
        {shown.map(({ key, item, phase }) => (
          <li key={key} data-cue-id={item.cue_id} data-state={phase} data-kind={item.kind}>
            {item.text.headline}
          </li>
        ))}
      </ul>
    </div>
  );
}
