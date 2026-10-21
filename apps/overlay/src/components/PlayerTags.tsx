// Player tags (TECH_PLAN 1.9, cue contract): a `player_tag` cue pins a tag to its player's disc on Pitch2D.
// Position comes from the latest 10 Hz frame; a 100 ms linear transition smooths the hop between frames.
import { surname, useLeague } from "../league";
import { PITCH_T, STAGE_W } from "../pitch/Pitch2D";
import { visibleCues } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";
import { usePresence } from "./motion";

const FLIP_MARGIN = 460; // a tag this close to the right edge opens to the left of its player

export default function PlayerTags() {
  const { state } = useStream();
  const lg = useLeague();
  const ids = state.hello?.player_ids ?? [];
  const tags = visibleCues(state).filter((c) => c.layer === "player_tag");
  const shown = usePresence(tags, (c) => c.cue_id);
  return (
    <div className="player-tags">
      {shown.map(({ key, item: cue, phase }) => {
        const targets = (cue.targets as { players?: string[] } | undefined)?.players ?? [];
        const pid = targets[0];
        const row = pid ? ids.indexOf(pid) : -1;
        if (row < 0 || !state.frame) return null;
        const [x, y] = PITCH_T.toCanvas(state.frame.p[row][0], state.frame.p[row][1]);
        const shirt = lg?.players[pid]?.shirt;
        return (
          <div
            key={key}
            className="player-tag"
            data-cue-id={cue.cue_id}
            data-player={pid}
            data-state={phase}
            data-flip={x > STAGE_W - FLIP_MARGIN}
            style={{ transform: `translate(${Math.round(x)}px, ${Math.round(y)}px)` }}
          >
            <span className="pt-name">
              {shirt !== undefined && <b>{shirt}</b>}
              {surname(lg, pid)}
            </span>
            <span className="pt-metric">{cue.text.headline}</span>
          </div>
        );
      })}
    </div>
  );
}
