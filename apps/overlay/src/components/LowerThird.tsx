// Lower-third (TECH_PLAN 1.9, docs/cue_contract.md): the highest-priority visible cue on a caption layer.
// Headline up to 60 characters, body up to 280, verified tick, 300 ms slide in and out. Text is fitted to the
// box (font steps down) so the schema maximum lengths never overflow.
import { useRef } from "react";
import { visibleCues } from "../stream/reducer";
import { useStream } from "../stream/StreamProvider";
import type { Cue } from "../stream/types";
import { useFitText, usePresence } from "./motion";

/** Layers whose text is shown as a lower-third caption (cue contract, "Layers"). */
export const CAPTION_LAYERS = new Set(["lower_third", "radar", "referee_line", "threat_front", "options_card"]);

function Card({ cue, phase }: { cue: Cue; phase: "in" | "out" }) {
  const head = useRef<HTMLDivElement>(null);
  const body = useRef<HTMLParagraphElement>(null);
  useFitText(head, [cue.text.headline], 31, 22);
  useFitText(body, [cue.text.body], 20, 15);
  const verified = cue.verified === true;
  return (
    <section
      className="lower-third"
      data-cue-id={cue.cue_id}
      data-state={phase}
      data-kind={cue.kind}
      data-testid="lower-third"
    >
      <div className="lt-bar" />
      <div className="lt-content">
        <div className="lt-headline" ref={head}>
          {cue.text.headline}
        </div>
        <p className="lt-body" ref={body}>
          {cue.text.body}
        </p>
        <div className="lt-foot">
          <span className={verified ? "lt-verified" : "lt-unverified"} data-testid="lt-verified">
            {verified ? "✓ Verified" : "Unverified"}
          </span>
          <span className="lt-clock">{String(cue.clock ?? "")}</span>
        </div>
      </div>
    </section>
  );
}

export default function LowerThird() {
  const { state } = useStream();
  const top = visibleCues(state).find((c) => CAPTION_LAYERS.has(c.layer));
  const shown = usePresence(top ? [top] : [], (c) => c.cue_id);
  return (
    <div className="lower-third-slot">
      {shown.map((p) => (
        <Card key={p.key} cue={p.item} phase={p.phase} />
      ))}
    </div>
  );
}
