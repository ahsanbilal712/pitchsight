// Cue feed (TECH_PLAN 1.9 fan app): the cues the server sent this profile, newest first. Casual shows the one
// sentence (headline); analyst and Player-Cam also show the body. Cards on air are marked live.
import type { ViewerProfile } from "../profile";
import { useStream } from "../stream/StreamProvider";

export const CARD_LAYERS = new Set(["recap_card", "options_card"]); // these go to MomentCards

export default function CueFeed({ profile }: { profile: ViewerProfile }) {
  const state = useStream();
  const cues = state.cues.filter((c) => !CARD_LAYERS.has(c.layer));
  return (
    <section className="feed" data-testid="cue-feed">
      {cues.map((c) => {
        const live = c.t_in_ms <= state.clock && state.clock < c.t_out_ms;
        return (
          <article key={c.cue_id} className="cue-card" data-cue-id={c.cue_id} data-kind={c.kind} data-live={live}>
            <header>
              <span className="kind">{c.kind.replace(/_/g, " ")}</span>
              <span className="clock">{c.clock}</span>
              {live && <span className="live">live</span>}
            </header>
            <h3>{c.text.headline}</h3>
            {profile.mode !== "casual" && c.text.body && <p>{c.text.body}</p>}
            {c.verified && <span className="tick">✓ verified</span>}
          </article>
        );
      })}
      {cues.length === 0 && <p className="empty">The story of the match will appear here.</p>}
    </section>
  );
}
