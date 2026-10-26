// Player tags (cue contract): a `player_tag` cue pins a tag to its player's disc on Pitch2D.
// Position comes from the latest 10 Hz frame; a 100 ms linear transition smooths the hop between frames.
// In player_cam mode the followed player keeps a tag ("Player-Cam") whenever no cue tag is up for them.
import { surname, useLeague } from "../league";
import { PITCH_T, STAGE_W } from "../pitch/Pitch2D";
import { visibleCues } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";
import { camPlayer } from "../modes/playerCam";
import type { Cue } from "../stream/types";
import { usePresence } from "./motion";

const FLIP_MARGIN = 460; // a tag this close to the right edge opens to the left of its player

export default function PlayerTags() {
  const { state } = useStream();
  const lg = useLeague();
  const ids = state.hello?.player_ids ?? [];
  const tags: Cue[] = visibleCues(state).filter((c) => c.layer === "player_tag");
  const cam = camPlayer(state);
  if (cam && !tags.some((c) => ((c.targets as { players?: string[] })?.players ?? [])[0] === cam)) {
    tags.push({
      cue_id: `cam_${cam}`,
      t_in_ms: 0,
      t_out_ms: Number.MAX_SAFE_INTEGER,
      layer: "player_tag",
      kind: "player_tag",
      priority: 0,
      targets: { modes: ["player_cam"], players: [cam] },
      text: { headline: "Player-Cam", body: "" },
    });
  }
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
