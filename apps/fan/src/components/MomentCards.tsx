// Moment cards (cue contract): recap cards, dugout options and Panel debates (options_card)
// as swipeable cards.
import { useStream } from "../stream/StreamProvider";
import { CARD_LAYERS } from "./CueFeed";

export default function MomentCards() {
  const state = useStream();
  const cards = state.cues.filter((c) => CARD_LAYERS.has(c.layer));
  if (cards.length === 0) return null;
  return (
    <section className="moment-cards" data-testid="moment-cards">
      {cards.map((c) => (
        <article key={c.cue_id} className="moment-card" data-cue-id={c.cue_id} data-kind={c.kind}>
          <small>
            {c.clock} · {c.kind === "dugout" ? "dugout" : c.layer === "recap_card" ? "recap" : "the panel"}
          </small>
          <h3>{c.text.headline}</h3>
          <p>{c.text.body}</p>
        </article>
      ))}
    </section>
  );
}
