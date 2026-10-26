# Video v10 narration: the decisions on the match clips

The owner asked on 26 Oct 2026 for a voice-over on the match clips that explains each decision (ADR-010, amendment).
The broadcast's own sound stays off. The intro and the architecture narration are v9's (`narration_v9.md`); this
file adds one stem per cue on the match clips, in the same voice (Charon, `gemini-2.5-pro-tts`), so it sounds like one
narrator.

`python -m footage.narration --script docs/video/narration_v10.md` writes the stems to
`packages/demo/out/narration_v10/` (git-ignored), with `timings.json`. gemini-3.8-flash transcribes each stem without
the script, and it must match the script word for word, numbers included. The tool also records when each number is
spoken: track C places each stem, and the grounding (`python -m footage.grounding --edit packages/demo/edit_v10.yaml`)
checks every number against the HUD at the moment it is spoken.

The owner's rules for the voice:
- It explains what the player on the ball decides: passes, plays it through, shoots, carries.
- It never names a team or a player. A side is the kit colour on screen: Man Utd, Arsenal and Liverpool all attack in
  red. The player is "the player on the ball", "the receiver", or "they".
- It never says VAR, "ruled out" or "offside". On the stoppage-time move it describes the shot only and never says
  "goal" (nor "expected goals"; the unit is spoken as "xG", as the screen prints it).
- Every pause in a take is cut to 0.25 s (`Max pause`; the model's own take is kept beside it), so each line fits its
  moment. Nothing spoken is cut.
- Every number spoken is the value on screen while it is spoken: a freeze card or tag, the HUD panel (its held value),
  a strike tag, or the burnt-in caption. Where a number would flicker or come too late, the line has none.

| Cue | Clip | Lands on | What is on screen |
|---|---|---|---|
| `mci_live` | `mci_live_v10` | the carry into the box (clip 875.6 s) | ON THE BALL, the carrier's ring |
| `mci_amad` | `mci_amad_v10_v8` (freeze) | the SHOT tag (0.06), then the card (0.06, 0.11) | freeze tag from 2.5 s, card from 3.0 s of the freeze |
| `ars_eze_live` | `ars_eze_live_v10` | "Pass intercepted by" the red player, then the carry | the HUD state, ON THE BALL |
| `ars_eze_decision` | `ars_eze_decision_v9` (freeze) | the shot tag (0.08), then the square pass (0.15 if it arrives) | tag from 0.8 s, pass tag from 1.9 s |
| `ars_eze_save` | `ars_eze_live_v10` (tail) | SHOT, SAVED | the outcome tag |
| `lfc_pass` | `lfc_live_v10` | the pass in flight to the shooter, outside the box | PASS IN FLIGHT |
| `lfc_shot` | `lfc_live_v10` | the strike (0.02) and the block | strike tag, BLOCKED tag |
| `mbeumo_pass` | `mci_mbeumo_live_v10` | the pass to the HUD's best option | Best pass, PASS IN FLIGHT |
| `mbeumo_shot` | `mci_mbeumo_live_v10` | the strike (0.10), after the carry into the box | strike tag, GOAL tag |
| `mount_pass` | `mci_late_live_v10` | the pass to the HUD's best option | Best pass, PASS IN FLIGHT |
| `mount_shot` | `mci_late_live_v10` | the receiver's panel: shot now 0.20 above every pass (best 0.09, not spoken: it would land after the panel fades) | the HUD panel (held 2 s) |

Takes of 26 Oct 2026, voice Charon: each stem matched its script word for word, numbers included (gemini-3.8-flash,
without the script). A number's time is its first spoken word in the stem. The placement in each segment is
`packages/demo/voice_v10.yaml`: each line's last word ends before its segment's cut. `--segments` mixes each
segment's cues into one stem for track C.

| Stem | Length | Numbers (s into the stem) | Segment, starts at |
|---|---|---|---|
| `mci_live` | 2.89 s | – | mci_live, 1.80 s |
| `mci_amad` | 5.75 s | 0.06 at 1.26 · 0.11 at 4.73 | amad_freeze, 0.65 s |
| `ars_eze_live` | 3.06 s | – | eze_live, 0.60 s |
| `ars_eze_decision` | 6.21 s | 0.08 at 1.05 · 0.15 at 4.44 | eze_decision, −0.20 s (the frame before the freeze) |
| `ars_eze_save` | 0.82 s | – | eze_strike, 0.35 s |
| `lfc_pass` | 3.18 s | – | lfc, 2.40 s |
| `lfc_shot` | 3.70 s | 0.02 at 1.49 | lfc, 6.40 s (the segment 2.6 s longer: 10.6 s) |
| `mbeumo_pass` | 2.28 s | – | mbeumo, 0.60 s |
| `mbeumo_shot` | 4.73 s | 0.10 at 2.64 | mbeumo, 2.95 s |
| `mount_pass` | 2.14 s | – | mount, 0.50 s |
| `mount_shot` | 3.63 s | 0.20 at 0.99 | mount, 2.85 s |

Wording changed to fit the takes: "They shoot" at the start of a take was heard as "the shoot" or "per shoot" (twice
each), so the Amad and Mount lines open with "A shot". One take read 0.20 as "point twenty"; it was taken again, and
the kept take says "point two zero".

Max pause: 0.25 s

Style: Read this as the narrator of the same short product film, now calling live match footage: natural, confident and warm, at a brisk pace, with only a brief pause between sentences:

## mci_live

The red team's player on the ball carries it into the box.

## mci_amad

A shot at 0.06 xG. The pass was worth 0.11.

## ars_eze_live

The red team win it back and carry it into the box.

## ars_eze_decision

They shoot at 0.08 xG. The square pass was worth 0.15 if it arrives.

## ars_eze_save

And it's saved.

## lfc_pass

The red team play it to a teammate outside the box.

## lfc_shot

They shoot from distance at 0.02 xG. Blocked.

## mbeumo_pass

The red team pick out the best pass.

## mbeumo_shot

They carry it into the box and shoot at 0.10 xG. Goal.

## mount_pass

The red team find the best pass.

## mount_shot

A shot at 0.20 xG, more than any pass.
