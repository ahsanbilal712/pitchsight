# Cue contract: renderer sign-off

T-003, 21 Oct 2026. A renderer's review of `schemas/cue.schema.json` 1.0.0 against the screen component trees in
TECH_PLAN 1.9. ADR-007: the Cue Sheet is the editorial boundary; screens render cues and never read the blackboard.
This document maps every `layer` and `kind` to the component that draws it and lists the fields a renderer needs
that the schema lacks. **It changes no schema**: each gap below needs B's agreement and a version bump under the
TECH_PLAN 1.3 rule (optional field: minor bump; consumers ignore unknown fields).

## Stream envelope

Every WebSocket line (and every line of `tests/fixtures/stream/sample_stream.jsonl`) is
`{"type": <message type>, "payload": {...}}`, with the message types of TECH_PLAN 1.9. The type names the schema the
payload follows: `event` → `event.schema.json`, `cue` → `cue.schema.json`, `hello.payload.viewer_profile` →
`viewer_profile.schema.json`; `tracking_frame` follows the JSON shape in TECH_PLAN 1.3; `fact` is the blackboard fact
document. An envelope keeps the event's own `type` field (pass, shot, …) from colliding with the message type.

Screens place a cue when the stream clock reaches `t_in_ms` and remove it at `t_out_ms` or on `cue_remove`,
whichever comes first.

## Components (names from TECH_PLAN 1.9)

| App | Components that render cues |
|---|---|
| Overlay (`apps/overlay`, 1920×1080) | `Pitch2D` layers (heatmap, threat front, ghost trail, referee lines), `ScoreBug`, `ChaosMeter`, `SwingBar`, `LowerThird`, `PlayerTags`, `Ticker`; route `/replay3d` |
| Studio (`apps/studio`) | `CueList` (every cue, with the Why? drawer), `ProducerPanel`, `MomentQueue` |
| Fan (`apps/fan`) | `MiniPitch`, `CueFeed`, `PlayerCamCard`, `MomentCards` |

`ScoreBug` and `ChaosMeter` are fed by the world-state stream (`event`, `fact`), not by cues. Studio's `CueList`
renders every cue of every layer (studio receives all cues regardless of mode), so it is not repeated per row below.

## Layers (all 10)

| `layer` | Overlay | Fan | Fields used |
|---|---|---|---|
| `lower_third` | `LowerThird`; plus `SwingBar` when `graphics.bar` is set | `CueFeed` card | `text.headline`, `text.body`, `graphics.bar`, `verified` badge |
| `pitch_overlay` | `Pitch2D` ghost-trail layer and player highlight rings | `MiniPitch` | `graphics.ghost_trail`, `graphics.players_highlight` |
| `heatmap` | `Pitch2D` heatmap layer (analyst and studio modes only) | none (hidden on phones) | `graphics.pitch_control_snapshot` (see gap 1) |
| `ticker` | `Ticker` (bottom strip, hidden in casual mode) | `CueFeed` (compact line) | `text.headline` |
| `player_tag` | `PlayerTags` (tag pinned to the player's dot) | `PlayerCamCard` | `targets.players[0]`, `text.headline` (see gap 3) |
| `radar` | `LowerThird` (text fallback; no radar component in 1.9) | `PlayerCamCard` | `text`, `targets.players` (see gap 4) |
| `recap_card` | none live; shown on the half-time studio cards (T-076) | `MomentCards` | `text.headline`, `text.body` (see gap 5) |
| `referee_line` | `Pitch2D` referee-lines layer plus a `LowerThird` caption | `MiniPitch` lines plus `CueFeed` | `graphics.lines`, `text` (see gap 6) |
| `threat_front` | `Pitch2D` threat-front layer (geometry from the `oracle` message) plus `LowerThird` caption | `CueFeed` | `text`; zone from `oracle` |
| `options_card` | `LowerThird` (stacked options variant) | `MomentCards` | `text.body` (see gap 2) |

## Kinds (all 14)

| `kind` | Usual layer | Component | Visible in modes (`config/budgets.yaml`) |
|---|---|---|---|
| `sliding_doors` | `lower_third` + `pitch_overlay` | `LowerThird` + `SwingBar` + `Pitch2D` ghost trail; full replay on `/replay3d?cf=…` | analyst, casual (2 per half), player_cam, studio |
| `state_change` | `lower_third` | `LowerThird`; `ChaosMeter` already shows the state | analyst, studio |
| `big_chance` | `lower_third` | `LowerThird` | analyst, casual, studio |
| `goal` | `lower_third` | `LowerThird` (after the 3 s goal hold); `ScoreBug` updates from the `goal` event | all |
| `tempo_shift` | `ticker` | `Ticker` | analyst, studio |
| `player_tag` | `player_tag` | `PlayerTags`; fan `PlayerCamCard` | player_cam, studio |
| `milestone` | `ticker` | `Ticker`; fan `CueFeed` | analyst, casual, player_cam, studio |
| `pressing_trap` | `pitch_overlay` | `Pitch2D` highlight rings + `LowerThird` caption | analyst, studio |
| `fourth_official` | `referee_line` | `Pitch2D` referee lines + `LowerThird` | all |
| `oracle` | `threat_front` | `Pitch2D` threat front + `LowerThird` caption | analyst, studio |
| `dugout` | `options_card` | `LowerThird` options variant; fan `MomentCards` | analyst, studio |
| `decision_index` | `player_tag` or `radar` | `PlayerTags`; fan `PlayerCamCard` | analyst, player_cam, studio |
| `recap` | `recap_card` | half-time studio cards; fan `MomentCards` | analyst, studio |
| `fast_line` | `ticker` or `lower_third` | `Ticker` / `LowerThird` (template or Haiku line, shown while the explained cue is still being written) | studio only (`kinds: [all]`); in no other mode's `kinds` list yet (see gap 9) |

## Fields a renderer needs that the schema lacks (list only; no schema edits)

1. **Heatmap data.** A cue names `pitch_control_snapshot: "pc_000412"` but screens never read the blackboard, so the
   34×53 grid has no route to the overlay. Needs a `pitch_control` stream message (grid as base64 float16 or a URL
   served by `api`), or the grid inline in the cue.
2. **Dugout options.** `options_card` has only free text; a renderer needs `graphics.options[]` of
   `{label, delta_win_prob, chosen}` to draw rows and bars without parsing prose.
3. **Player-tag metric.** `player_tag` and `decision_index` cues carry the number only inside `text.headline`
   ("32 km/h"); the tag needs `graphics.metric {label, value, unit}` and the target player id as a single field.
4. **Radar values.** `radar` has no axes or values; needs `graphics.radar {axes[], values[], reference[]}`, or the
   layer should be dropped until then (no 1.9 component draws it).
5. **Recap structure.** A half-time card shows three moments, a chaos timeline and a player of the half; 60 + 280
   characters of text cannot carry that. Needs `graphics.sections[]` (each `{title, body, moment_id}`).
6. **Referee-line roles and labels.** `graphics.lines` are bare coordinate pairs; the renderer needs a role per line
   (`last_defender`, `attacker`, `box_edge`), a colour hint and a label ("0.4 m").
7. **Ghost futures for `/replay3d`.** The 3D scene draws 200 ball paths; the cue has one `ghost_trail`, and
   `futures_sample` lives in the counterfactual document the screen cannot read. Needs `GET /counterfactual/{id}`
   on `api` or a `counterfactual` stream message. **Interim (T-024):** screens accept a `counterfactual` stream
   message (payload = the counterfactual document, already in `scripts/validate_schemas.py`) and split
   `futures_sample` by convention: first half baseline futures, second half alternative futures. A
   `futures_branch[]` field (minor bump) would replace the convention.
8. **Bar semantics.** `graphics.bar` has no team or unit; the `SwingBar` needs `team` (home or away, for kit colour)
   and a `format` (percent or raw).
9. **Mode budgets for `fast_line`.** `fast_line` is a valid kind but appears in no `kinds` list in
   `config/budgets.yaml` except studio's `all`; Director behaviour for casual and analyst needs deciding.
10. **Row-to-player mapping.** The `tracking_frame` JSON has no player ids (rows 0–21 are positional). The fixture's
    `hello` message carries `player_ids` in row order, mirroring `tracking.npz`; the `hello` row in 1.9 should list it.
11. **`targets.clubs` vocabulary.** Free strings with default `["any"]`, while `viewer_profile.club` is
    `home | away | null`. Renderers will match on `any`, `home` and `away` only; the schema should say so.
12. **Anchor hint.** No placement hint for lower-thirds (left or right, top or bottom). Renderers use a fixed layout
    per layer; a `graphics.anchor` would let the Director avoid covering the ball.

## Sample stream fixture

`python3 scripts/make_sample_stream.py` writes `tests/fixtures/stream/sample_stream.jsonl`: 1 `hello`, 600
`tracking_frame` (30:50–31:50 at 10 Hz, rows 0–10 Verdant, 11–21 Ironvale, 22 ball), 14 `event` (including the
schema examples `e_8809` and `e_8812`), 62 `fact` (`chaos_index` once a second; `chaos_state` Transitional at 30:50 and Chaotic from 31:26, T-023), 1 `counterfactual` (the schema example with 200
`futures_sample` paths, 100 per branch, T-024), 1 `cue` (the `cue.schema.json` example, 31:18–31:26)
and 1 `cue_remove`. Byte-identical on every run; `--check` re-parses and asserts the counts.
