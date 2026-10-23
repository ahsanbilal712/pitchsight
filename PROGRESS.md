# WHYLINE progress log

Newest entry first. Each session appends one entry when it finishes a piece of work: date, ticket, what was done,
files touched, verification run, open issues. Keep entries short; details live in the files they point to.

---

## 2026-10-23 · Video v7 draft 2: the Eze caption source; one caption flagged (track B)

- v7 caption source added: "Eze from 16 m: 0.08 xG. Saved." (shots_0 e_0046, as in v5).
  `python -m footage.grounding` on edit_v7 draft 2 (6516439): see v7_grounding.json.
- Checked the two new number-less captions against the data: "Arsenal's share ... climbs" holds (1% at 1297.0 s
  to 23% at 1301.0 s), but **"Eze wins it back" is wrong**: Arsenal regain the ball through an unnamed player
  (t46, 1296.2-1296.4 s), Saka carries (1298.1 s) and passes to Eze (1299.4 s; tagged event e_0045). Track C asked
  to reword ("Arsenal win it back, Saka finds Eze, ..."). City's "creeps up" holds (1% to a 22% peak, 14% at the
  end): fine without numbers.
- No model call. Verification: `pytest tests/footage` (exit 0).

---

## 2026-10-23 · Video v7 grounding: 969 of 969 on draft 1b (track B)

- `python -m footage.grounding` on track C's committed edit_v7.yaml (a055dcb, with the dangerous-space caption on
  lfc_live_v7): **969 of 969 on-screen numbers bound to verified evidence (965 of 965 claims verified)**;
  data/footage/v7_grounding.json regenerated (it said 937 from the earlier edit).
- No model call, no code change.

---

## 2026-10-23 · Video v7 grounding on edit_v7.yaml: 937 of 937 (track B)

- `python -m footage.grounding` on track C's edit_v7.yaml (draft 1, working tree): **937 of 937 on-screen numbers
  bound to verified evidence (933 of 933 claims verified)**: the always_on beats' v6 ball layer (747 with the v6
  freezes, shot map, strip, pipeline), the always-on layer 156 (danger sentence = share, attacking team; shape
  width/depth/gap = their lines), lines 17, captions 17. New caption source: "Seconds later, 0.32 xG: saved."
  (shots_0 e_0038, as in v5).
- No model call. Verification: `pytest tests/footage` (exit 0).

---

## 2026-10-23 · Video v7: the "dangerous space in view" caption; v7 grounding ready (track B)

- **Caption** (`footage.v7_caption`, `cache/v7/caption_danger.json`, Man Utd v City manifest): "Dangerous space in
  view: spots in front of goal worth 0.05 xG or more, weighted by xG; the share the attacking team would reach
  first." From track A's final definition (ee20aa4: one number for the team attacking the goal in view; zone =
  cells worth >= 0.05 xG, the v5/v6 reference model; share = control x xG / xG; printed from 50% of the zone in
  view). gemini-4-argon (`insight_footage@9`), Fact Checker (the "0.05" bound to danger_def), hand review: the
  draft pinned one frame's 28% (the overlay prints the live share) and the first draft (@8, on the superseded
  two-team definition) said "worth 0.05 xG" instead of "at least"; both kept as records.
- **v7 grounding** (`python -m footage.grounding --edit packages/demo/edit_v7.yaml`, once the edit exists): the v6
  checks plus `v7_always` over each always_on beat's window: the danger sentence must print the share and name the
  attacking team; the shape panel's width, depth and line gap (whole metres) must equal what their definitions say
  of the file's lines (width = y_max - y_min, depth = front - back line x, gap = midfield - back line x), and only
  with 9+ outfielders seen; v7 captions = v6's + this caption. On a preview edit of track C's seven v7 beats:
  857 of 857.
- **Spend:** 2 Argon calls, $0.0096; project $4.2247 of $50.
- Verification: `pytest tests/footage` 61 passed (exit 0); a test shows a wrong share and a wrong depth caught.

---

## 2026-10-23 · Video v6 grounding: the pipeline's compact phrases (track B)

- `footage.grounding.v6_pipeline` now also reads the beat's `compact` phrases (track C, footage_moments
  mci_pipeline_v6, fef7d20): every number in them must be one of the pipeline view's facts ("18 m", "4", "56:43",
  "8 s"); the Fact Checker card's "<n> claims checked" is bound to the count of its own claims (not to the
  options' "4").
- `python -m footage.grounding` on edit_v6: **941 of 941 on-screen numbers bound to verified evidence (937 of 937
  claims verified)**. A test shows a wrong number in a compact phrase is caught.
- No model call. Verification: `pytest tests/footage` (exit 0).

---

## 2026-10-23 · Video v6: names for the late Man Utd passage (track B)

- Track C's new live beat (mci_late_live_v6, live_1390000 1409.5-1415.0 s) added to `footage.shirts.PASSAGES`;
  only its 8 tracks read (the other passages' reads stand on their windows; track A's re-cut windows differ
  by a few hundred ms). Named: **Mason Mount** (#7, 7 of 7 crops), **Matheus Cunha** (#10, 3 crops); 6 tracks no
  consistent number, no label.
- Mount is now verified as a player on the pitch (shirt), not for his disallowed "3-0": the event-level
  rejection is kept in names_verified.json (rejections tied to an event or a label are never dropped), and the
  shot e_0070 stays unnamed.
- Amad's opening beat: t19 is named 875.5-878.5 s from his hand label (3ff919c); t16 stays unnamed (its reads
  disagree).
- **Spend:** 8 Flash calls, $0.0762; project $4.2152 of $50. Grounding on edit_v6: 935 of 935.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 233 passed, 4 skipped (exit 0); ruff clean.

---

## 2026-10-23 · Video v6: hand-label windows in the live name lists (track B)

- Track A asked for Amad (t19) and Casemiro (t16) in Amad's passage. `footage.shirts.hand_windows`: a freeze's
  hand-labelled, named player gets a live window on his track, +-1.5 s around the freeze (the same window the
  freeze reads use), on the live file of the same camera shot, only when no crop of that track over the window
  shows another number. Amad: t19 875.5-878.5 s, shirt 16 (his hand label), no crop shows any number. Casemiro:
  no window (t16 reads 18 at the freeze but 19 five times over the passage: the track may have switched), so the
  follow-up shot at 879.5-880.1 s stays unlabelled. Also: Bruno, Szoboszlai, Salah, Eze, Saka, Werner around their
  freezes (each agrees with its own shirt read where one exists).
- `python -m footage.grounding` (track C's current edit_v6): 935 of 935 on-screen numbers bound (931 of 931 claims).
- No model call. Verification: `pytest tests/footage` 59 passed (exit 0).

---

## 2026-10-23 · Video v6 grounding back to 541 of 541 (track B)

- Track C reworded the Arsenal caption to "the top pass option climbs to 0.19 xG" (7ccdce4); its source entry in
  `footage.grounding.v6_caption_sources` is re-keyed to the new text (same number, same source: live_823600 frame
  834800, best xg_after_pass). `python -m footage.grounding` on the committed edit_v6: **541 of 541 on-screen numbers
  bound to verified evidence (537 of 537 claims verified)** (was 540 of 541 in track C's re-run).
- No model call. Verification: `pytest tests/footage/test_grounding.py` 6 passed (exit 0).

---

## 2026-10-23 · Video v6 grounding: 541 of 541 (track B)

- `python -m footage.grounding` (latest edit, edit_v6.yaml draft 1, f667c65): **541 of 541 on-screen numbers bound
  to verified evidence (537 of 537 claims verified)**. Beats are read from the edit (each shot's footage_moments
  beat):
  - v6 lines 17/17: the reviewed lines the freezes show (line_v5: Amad, Szoboszlai, Mbeumo, Dorgu);
  - freeze cards: shot (freeze value on a decision freeze, else the strike), the pass and its arrival chance,
    each against the line's display;
  - live HUD (5 passages, their on-screen windows): every distinct tag printed (p_pass, xG after the pass, shot
    now): each must be the product it claims (p_pass x xG at the receiver, to the two decimals shown), and a
    name or shirt only inside a verified live read's window;
  - shot beats and the shot map (names only where the shot is verified), the score strip (xg_running_0) adding up
    to the shot map;
  - the pipeline view (every number in what the agents say is one of the view's facts; no latency printed where
    the source is "not recorded");
  - captions 16/16 with declared sources (v5's where unchanged; the Arsenal "0.19" is live_823600 frame 834800's
    best xG after the pass).
- v3 73 of 73, v4 121 of 121, v5 115 of 115 unchanged. No model call: the v6 freezes reuse the v5 lines (Argon,
  Fact Checker, hand review).
- Verification: `pytest tests/footage tests/newsroom tests/cache` 232 passed, 4 skipped (exit 0); a test shows the
  live product check catching a wrong tag.

---

## 2026-10-23 · Video v6: names for track A's live passages, the pipeline view in track C's format (track B)

- **Live names** (`cache/v6/names_live_0.json` per clip, for track A to attach to its live frames): every track
  that carries the ball or is a pass option inside track C's five v6 passages, shirt read on 8 crops spread over
  its window there, plus two new checks: the crop's torso colour must be the track's own team kit (teams.json),
  and an outfield track never maps to a goalkeeper's number. One number per team per passage. Each name holds
  only from_clip_ms..to_clip_ms on that camera shot's track (Liverpool t69 is Wirtz at 867.2-870.9 s and a City
  player at the freeze). Named: Man Utd v City 6 of 11 (Mbeumo, Bruno, Dorgu, Casemiro), Liverpool 6 of 11
  (Salah, Szoboszlai, Kerkez, Mac Allister, Gravenberch, Wirtz), Chelsea 3 of 9 (Palmer, Neto, Enzo Fernández),
  Spurs 1 of 4 (Werner). Rejected: a second #19 in the Amad passage, a 28 read (a goalkeeper's number).
- `footage.names`: live links (track, window); `name_at` gives a player's verified name at a moment (hand, a read
  at that moment, or his track's live read in the same camera shot covering it); `short` keeps surname particles
  ("Mac Allister", "van de Ven"). Squad files now list their goalkeepers.
- **Pipeline view** (`cache/v6/pipeline_<slug>_<clip_ms>.json`, track C's format): agents scout, proposer
  (options named by name_at, else "Pass"), rollout, tactician (the verdict and Argon's draft), factcheck (each
  claim, ok, evidence), director ("On air 56:43, lower third, 8 s"), cuebus (the line); latency_ms with its
  source; every number in a `says` listed in `facts`. Both v6 pipeline files and the live name lists are in the
  clips' cache manifests (validate_schemas sees them).
- **Spend:** 35 Flash calls, $0.2875; project $4.139 of $50.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 231 passed, 4 skipped (exit 0); ruff clean;
  validate_schemas OK (5501 documents).

---

## 2026-10-23 · Video v6: shirt-number names, agent-pipeline records (track B)

- **Shirt numbers -> names** (`footage.shirts`, `data/footage/<slug>/shirts.json`): for the attacking team's labelled
  players at the featured freezes and the montage shooters without a name, 8 crops of the tracked box within 1.5 s
  of the moment the label applies to (1080p; crops in the git-ignored frames/), one gemini-3.8-flash call each
  (SpendGuard). A number counts only with 3+ agreeing crops, two thirds of the crops with a number, no rival read
  twice; it is mapped to the season's squad list (`data/footage/squads/<club>_<season>.json`: the season's
  Wikipedia squad table, URL and retrieval date; the clubs' own sites now list 2026/27).
  - Controls read right: Szoboszlai 8/8, Salah 8/8, Bruno 8/8, Saka 8/8, Eze 7/8, Werner 7/8.
  - New names: Amad's pass target **#19 = Bryan Mbeumo** (8/8), U5 = Casemiro (6/6), #13 = Dorgu (8/8), Arsenal
    #12 Timber, #16 Nørgaard, #29 Havertz (8/8); shooters e_0065 = Ekitike (6/8; the tagger said Mac Allister),
    e_0058 = Aït-Nouri, Spurs e_0057 = Casemiro. Unread (no consistent number): L4-L8, A7, e_0038 (18 twice).
  - Arsenal A6 also read 29 (6/8): rejected, Havertz's number belongs to #29 (8/8) in that frame.
  - First Man Utd v City pass took crops across the whole shot and read #19's track as City's #45 (an identity
    switch after the freeze): discarded, crops now come from the label's moment.
- `footage.names`: a fourth source "shirt" (one number per team per moment; never against a hand label); shots
  named by shirt. Lines use names verified for a label at a moment (Amad's pass now "to Mbeumo").
- **Pipeline records** (`footage.pipeline`, `cache/v6/pipeline_<clip_ms>.json`, Amad and Liverpool): Freeze,
  Scout, Proposer, Model, Tactician, Fact Checker (each claim and its evidence), Producer review (draft against
  final), Director, On air. Timings by source: recorded live (Argon 13,819 ms for Amad), measured re-run (model
  49 ms, reproduces the stored numbers; Fact Checker 5.6 ms), replay (cache-served, whole ms), not recorded.
- **Spend:** 35 Flash calls, $0.2947; project $3.8515 of $50.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 229 passed, 4 skipped (exit 0); ruff clean.

---

## 2026-10-23 · Video v5 grounding: 115 of 115, "from here" binds the freeze (track B)

- Lead's ruling as a checker rule (`footage.grounding.v5_caption_sources.shot_xg`): a shot number said "from here"
  binds to the freeze value (xg_decision, frame_role freeze; Amad 0.06), any other to the reviewed strike (shots_0,
  frame_role strike; Eze 0.08). The decision card follows the same split ("Shot from here" on decision freezes).
- The ghost future footer ("the most typical of 2,000 simulated futures, seed 4242") is counted for every ghost
  beat in the edit, from its data file.
- `python -m footage.grounding` on track C's v5 draft 2 (066f06f): **115 of 115 on-screen numbers bound to verified
  evidence (105 of 105 claims verified)**: studio cues 18/18 (Liverpool shot-only, Amad), v5 lines 25/25, overlays
  52/52, captions 20/20. v3 73 of 73, v4 121 of 121 (Spurs pass X-ray withdrawn).
- Already in 528ac3f: Amad's studio cue on the v5 line (t_in_ms 3,403,700), the Liverpool and Eze strike lines.
- No model call. Verification: `pytest tests/footage tests/newsroom tests/cache` 225 passed, 4 skipped (exit 0).

---

## 2026-10-23 · Video v5: Amad compared at the freeze, Amad studio, grounding 113 of 113 (track B)

- **Amad 56:41** (track C's point, lead's rule 3): a decision freeze compares the shot and the pass at the same
  instant, so the line gives the freeze value labelled "from here", as the card's "Shot from here" row does:
  "Amad: shot from here 0.06 xG, pass 0.11 xG" (gap 0.05, #19 0.75 m onside). Argon re-draft, Fact Checker, hand
  review. Shot-only and goal beats stay at the reviewed strike.
- **Studio:** Man Utd v City recorded on Amad's v5 line (the studio beat track C waits for): sliding_doors cue,
  bar "Man Utd xG, shot v pass" 0.06 -> 0.11; Liverpool re-recorded (shot-only); trace notes now name which shot
  value is shown (freeze or strike).
- **Grounding** on edit_v5.yaml (track C's draft 2, working tree): **113 of 113** (103 of 103 claims). Decision
  overlays are counted only for beats in the edit (footage_moments `xg` of each edit shot; Werner is montage only);
  both v5 studios counted; the ghost future's "2,000" bound to ghost_future_877000 n. v3 73 of 73, v4 121 of 121.
- **Fixed:** the Amad re-run under the same prompt version overwrote the earlier @7 record at the same cache path
  (that call's $0.0064 stays in the ledger). Caption records are now keyed and named by a hash of the payload, so a
  different answer can never overwrite another.
- **Spend:** 1 Argon call, $0.0065; project $3.5568 of $50.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 224 passed, 4 skipped (exit 0); ruff clean.

---

## 2026-10-23 · Video v5 on the lead's rules; Spurs pass X-ray withdrawn from v3, v4, v5 (track B)

- **Lines** (prompt `insight_footage@7`; Argon, Fact Checker, gates, hand review): every shot at its reviewed
  strike (track A's shots_0); a pass only when worth >= 0.04 xG more and the receiver > 0.5 m onside, else the
  beat is shot-only. "Szoboszlai from 29 m: 0.02 xG, blocked"; "Amad: shot 0.07 xG, pass 0.11 xG";
  "Eze from 16 m: 0.08 xG, saved"; "Werner from 16 m: 0.08 xG, saved"; "Mbeumo scores from 15 m: 0.10 xG";
  "Dorgu scores from 4.5 m: 0.48 xG". Strike distances in the lines (one decimal under 10 m).
- **Studio:** Liverpool airs the shot-only cue (big_chance, no bar); the trace says why no pass is shown.
- **Withdrawn:** the Man Utd v Spurs pass X-ray (track A 115f6a0: attack directions were reversed; a clearance
  valued as an attack): v3 28% / 3.2%, v4 11% -> 21% and its tags, v5 0.32. Not counted; listed in
  `result.withdrawn` of every vN_grounding.json. **v3 73 of 73** (was 75), **v4 121 of 121** (was 170).
- **v5 grounding 107 of 108**: Amad's caption gives the freeze value 0.06; the strike (and the card) is 0.07
  (track C, listed in `result.unbound`).
- **Spend:** 6 Argon calls, $0.0331; project $3.5503 of $50.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 224 passed, 4 skipped (exit 0); ruff clean.

---

## 2026-10-23 · Video v5: real-data xG lines, studio, grounding 100 of 103 (track B)

- **Lines** `data/footage/<slug>/cache/v5/lines_<clip_ms>.json` (`footage.v5_lines`, prompt `insight_footage@6`;
  the writer is shared with v4 since 948ade2): gemini-4-argon, Fact Checker, gates, hand review.
  - Szoboszlai 86:23 "shot 0.02 xG, pass 0.03 xG, a close call" (L5 left out: 0.43 m beyond City's second-last);
  - Amad 56:41 "shot 0.06 xG, pass 0.11 xG" (arrives 84% of the time);
  - Eze 79:10 "shot 0.05 xG, pass 0.06 xG, a close call";
  - Mbeumo "scores from a 0.10 xG chance"; Dorgu "scores from a 0.48 xG chance"; Werner "shot: 0.08 xG, saved".
  Rule: deterministic numbers, compared as shown (two decimals); "higher" only at 0.02 xG or more, else a close
  call (track A's comparison_rule agrees). Comparisons use the shot "from where he stands" at the freeze; goals and
  shot-only beats use the reviewed strike's xG (Dorgu 0.48 at 4.5 m, not 0.30 at the freeze; Werner 0.08).
- **Studio:** Liverpool re-recorded on the v5 line: bar "Liverpool xG, shot v pass" 0.02 -> 0.03; the moment
  carries `xg_decision` (renamed from `xg`: synthetic moments already use `xg` for a float); the sqlite loads only
  the aired line's facts (v4 and v5 fact ids overlap).
- **Grounding** `python -m footage.grounding --edit packages/demo/edit_v5.yaml` -> `data/footage/v5_grounding.json`:
  **100 of 103** (97 of 99 claims). Unbound, each listed under `result.unbound` with its owner: Dorgu's goal
  flash prints the freeze xG 0.30 (line 0.48), Werner's card prints 0.04 (line 0.08), and the Spurs X-ray caption
  "climbs to 0.32" has no source since track A found the clip's directions reversed (115f6a0: it was a clearance).
  v4 reads its studio from 6920af1 (170 of 170), v3 from 14d7679 (75 of 75).
- **Spend:** 8 Argon calls, $0.0369; project $3.5172 of $50. No new GCP resource; quota project ffc-19484.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 224 passed, 4 skipped (exit 0); ruff clean;
  validate_schemas OK (5437 documents); check_spend OK.

---

## 2026-10-23 · Video v4 grounding: 170 of 170 (track B)

- `python -m footage.grounding` on edit_v4.yaml (track C's draft 2, b90a302): **170 of 170 on-screen numbers bound
  to verified evidence (159 of 159 claims verified)**. The decision cards now print "n = 2,000" (track C), and the
  check reads it as one number; new: the Liverpool Oracle card (each sample's goal chance as demo.live.pct prints
  it, "n = 2,000 per 0.5 s, 10 s, seed 4242") and the ghost future's footer ("2,000 simulated futures, seed 4242").
- No model call. Verification: `pytest tests/footage/test_grounding.py` 3 passed.

---

## 2026-10-23 · Video v4: finishing lines for the two goals; grounding takes the edit file (track B)

- **Mbeumo 64:27 and Dorgu 75:28 (both scored):** lead ruling, a goal never implies a better option. New verdict
  `finishing` (prompt `insight_footage@5`): the line gives the goal chance from here and that he scored, and the
  gate refuses any other option. Argon, Fact Checker, hand review: "Mbeumo scores from a 3.8% chance (goal in
  10 s)", "Dorgu scores from a 17% chance (goal in 10 s)". These replace the close-call / carry-on lines in
  `lines_1079360.json` / `lines_1189840.json` (`lower_third`, `why`; no alternative facts, overlay label
  "From here").
- **Liverpool 86:23** stays on track A's final decision (16141fe, after the L3/L4 fix): pass 3.3% v shot 1.1%;
  L3 has no readable shirt number in the nearby frames, so he stays unnamed ("the team-mate at the edge of the box").
- **Grounding:** `python -m footage.grounding [--edit packages/demo/edit_vN.yaml]`, default the latest edit;
  version from the file name. v4 now **143 of 149** (the six decision cards print "n = 2000" against the caption's
  "2,000"; track C is changing the card); v3 unchanged at 75 of 75 (adds the `edit` field).
- Facts carry a `role` (actual, alternative, horizon, n, interval ends, seed).
- **Spend:** 2 Argon calls, $0.0115; v4 total $0.0732; project $3.4759 of $50.
- Verification: `pytest tests/footage tests/newsroom/test_director.py` 66 passed; ruff clean.

---

## 2026-10-23 · Video v4: the six goal-in-10s lines, studio re-recorded, v4 grounding (track B)

- **Lines** `data/footage/<slug>/cache/v4/lines_<clip_ms>.json` for Liverpool 86:23, Arsenal 79:10, Man Utd v City
  56:41 / 64:27 (Mbeumo) / 75:28 (Dorgu), Spurs 38:02 (Werner): gemini-4-argon (`insight_footage@4`, with the real
  outcome in the payload), Fact Checker, gates, hand review (one format: "Name: shot X%, alternative Y%"; keepers
  unnamed). Verdicts from the 95% intervals: alternative better at 86:23 (pass 3.3% v shot 1.1%), 79:10 (5.7% v
  2.6%), 56:41 (4.5% v 2.5%), 75:28 (carry 32% v 17%, he scored); close call at 64:27 (3.8% v 4.5%, he scored) and
  38:02 (1.4% v 0.6%). Each file carries `display` (one string per number, track C's fmt_pct rule, halves up),
  `overlay_labels` (verified names only) and the facts for the card's small print.
- **Names:** `names_verified.json` now has `shots`: a shooter is named only where that shot is verified (score-bug
  goal, or a hand-marked frame whose named holder shoots): 14 of 56.
- **Studio:** Liverpool re-recorded on the v4 line: sliding_doors cue, bar "Liverpool goal chance, next 10 s"
  0.011 -> 0.033, ghost trail from track A's ghost future, no win chance in the moment's stream (Director reads
  `goal_in_10s` on the moment; Narrator treats it as a Sliding Doors comparison). Recap unchanged.
- **Grounding:** `python -m footage.grounding v4` -> `data/footage/v4_grounding.json`: studio cue, v4 lines,
  every decision-card number as track C's fmt_pct prints it, the pass X-ray tags, the burnt-in captions of
  edit_v4.yaml (declared sources, verified names). Now **152 of 158**: the six cards print "n = 2000" while the
  caption says "2,000" (asked track C). v3 grounding reads the studio as the v3 final recorded it (git 14d7679):
  still 75 of 75.
- **Fixed on the way:** @4 runs wrote to the same cache path as @3, overwriting four @3 records; caption records are
  now versioned by prompt, the four @3 manifest entries were dropped (their $0.0240 stays in the ledger).
- **Spend:** 10 Argon calls, **$0.0616** (m_9001 $0.0065, m_9002 $0.0368, m_9003 $0.0063, m_9004 $0.0121);
  project $3.4643 of $50. No new GCP resource; quota project ffc-19484.
- Verification: `pytest tests/footage tests/newsroom tests/cache` 220 passed, 4 skipped; ruff clean;
  validate_schemas OK (5408 documents); check_spend OK.

---

## 2026-10-23 · Video v4: line writer on goal-in-10s, Director bar, studio v4 path (track B, code)

- `footage.v4_lines` (+ prompt `insight_footage@3`): lower-third (<= 60 chars) and one-sentence explanation per
  goal-in-10s decision (track A's `cache/v4/goal10_decision_<clip_ms>.json`), gemini-4-argon, then the Fact
  Checker, then gates: every number claim prints its fact's single `display` string ("3.3%", one decimal), every
  name verified (`footage.names`), wording follows the verdict, length. The verdict is computed, not written by the
  model: "better" only when the alternative's 95% interval is clear of the actual choice's; overlap = close call;
  all clear below = the choice was the best found. Unnamed players are described by position from their team's
  attacking direction. Review in `review/footage/v4_*.md`; `import` writes `cache/v4/lines_<clip_ms>.json`.
- Director: a moment carrying `goal_in_10s` gets the bar "<club> goal chance, next 10 s" (and the ghost future's
  ball path) instead of win chance, even with a counterfactual on the draft.
- `footage.studio`: a featured moment with a reviewed v4 line runs the same executors on goal-in-10s (no
  counterfactual, the line's facts on the blackboard); v3 moments unchanged.
- Validated with one live call (Man Utd v City 56:41, $0.0061; Fact Checker verified, gates pass).
- Verification: `pytest tests/footage/test_v4_lines.py tests/newsroom/test_director.py tests/footage/test_studio.py`
  26 passed; ruff clean.

---

## 2026-10-23 · Video v4: verified names, and two moment-file fixes under track A's goal-in-10s (track B)

- **Verified names** `footage.names` -> `data/footage/<slug>/names_verified.json`. A name reaches the screen only
  with a source: hand label (moments/hand), the clip's published description (frozen in `description.json`: goal
  lines and mentions; clip.info.json stays ignored), or a tagger goal the **score bug** confirms (`score_bug.json`,
  read by hand 8 s before and 40 s after every tagged goal). `unverified_in(slug, text)` flags any other name.
  Result: 24 verified across the four clips; rejected include Bruno Fernandes's "goal" at 40:06 v City (bug stays
  0-0), Mason Mount's 3-0 (the description lists two goals, 2-0), the duplicate Kulusevski at 47:49 (bug stays 0-2),
  and every tagger-only name (e.g. Van Dijk, Maddison).
- **Liverpool 86:23 moment:** L3 and L4 stand in one merged tracking box (track 68); the hand-mark-order matching
  gave the track to L3 (1.9 m) instead of L4 (0.5 m), so L3 sat on L4's spot with the box's velocity, and track A's
  "pass to L3, 4.2%" rested on it. `from_tracks.inherit_labels` now matches closest pairs first; a different player
  standing close (City's t69, 32 px from L3's feet) is no longer a team conflict (`CONFLICT_IMAGE_PX` 12).
  Frame-checked: two Liverpool players overlap at the D. Re-runs start from moments/hand.
- **Arsenal 79:10 moment:** the ball was a stale tracking detection at x 106.66 (behind the goal line); re-derived,
  it is the hand-marked ball at (88.78, 23.39) beside Eze.
- Track A re-runs goal10_decision for 875000 and 1300500 on the fixed files. No model call; spend unchanged.
- Verification: `pytest tests/footage` 39 passed; ruff clean; validate_schemas OK (5389 documents).

---

## 2026-10-23 · Working-tree tidy after the v3 final: ledger, eval table, footage tests (track B)

- **Ledger:** two smoke rows of 23 Oct 08:30 UTC (Flash $0.000009, Argon $0.000126) committed; the ledger stays the
  spend proof. Project spend **$3.40 over 691 calls** (cap $50).
- **Eval table** `packages/evals/results.{md,json}`, `out/groundedness.json`: regenerated with
  `evals.run_evals --seeds 1..50` (no model call). Project spend now matches the ledger; groundedness
  **150/150 = 1.000** (was 141/141: the Fact Checker's number handling from T-109 and 6a6c2b9 now counts 9 more
  numbers in the golden Sliding Doors cues, all bound).
- **Studio cache restored:** the Liverpool studio `stream.jsonl`, `blackboard.sqlite` and two manifest timestamps
  differed from 14d7679 only in run timings (`started_ms`, `latency_ms`, `created_at`), rewritten by
  `tests/footage/test_studio.py` and `test_river.py` during a test run. Restored to what the video recorded.
- **Fix:** `tests/footage/conftest.py` `restore_clip_cache` puts the clip cache back byte for byte after those two
  tests, so `make ci` leaves the tree clean.
- Verification: `make ci`: lint, schemas (5376 documents) and spend OK; unit **486 passed, 2 failed**: track A's
  wall-clock budgets `tests/rollout/test_perf.py` (cpu p90 1.71 s vs 1.3 s) and `test_policy_perf.py` (0.36-0.42 s
  vs 0.30 s), also failing when run alone, with the machine under system load (kdc, StorageManagement; load average
  11-50). No rollout code changed; thresholds untouched. The clip caches stayed clean through the run.

---

## 2026-10-23 · T-110 video v3 (real footage only) and T-111 README and JUDGES (track C)

- **Video v3 final cut** `packages/demo/out/final_v3.mp4` (git-ignored), **116.3 s**, captions only, real Premier
  League footage and names only (owner direction): Liverpool Sliding Doors freeze; Man Utd v Spurs pass X-ray into
  Van de Ven's speed gun (37.0 km/h, at least 91 m); Arsenal freeze; Fourth Official; Raya keeper cone; Dorgu ghost
  defender; the studio and a veto on track B's recorded real-clip run; viewer modes; the measured card; the
  win-probability river. Edit `packages/demo/edit_v3.yaml`, captions `captions_v3.srt`, every number sourced;
  `footage.grounding` 75 of 75 on-screen numbers bound. v2 draft 3 (edit_v2.yaml) and v1 kept as fallbacks.
- Built for it: `demo.live` (overlays on the playing clip through each frame's camera, across camera cuts; freeze
  beats pick their camera by measured paint drift), `demo.v3_data` (track A insight adapters), `demo.refine_calib`
  on every featured shot, `api.replay --match` (a recorded real-clip run on the clock, real clubs and roster),
  studio fixes for real-clip facts and names, `scripts/record_v3_studio.sh`.
- **T-111:** `README.md` (pitch, the video, permission and sources, what never enters the repository, the footage
  pipeline with its measures, limits, how to run) and `docs/JUDGES.md` (watch first, the footage note, local replay in
  three commands, the real-clip studio). T-067/T-068 (track B) can extend both with the evidence table and
  architecture. The permission `.eml` is not committed yet (held by the owner).
- **Not done:** docs/video/VERSION stays until the owner approves; the upload is a human step.
  Verification: `pytest tests/demo tests/api` 59 passed; studio tests 8 passed; README/JUDGES relative links resolve.

---

## 2026-10-23 · Video v3 metrics card: grounded on-screen numbers (track B)

- `python -m footage.grounding` -> `data/footage/v3_grounding.json` (`result.card_line`): every number that reaches
  the screen in video v3, checked by the Fact Checker (`verify_claims`, rules 1-8) against its evidence:
  **75 of 75 on-screen numbers bound to verified evidence (81 of 81 claims verified)**. Groups: studio replay cues and
  the held recap, against their own sqlite (35/35 numbers, 33/33 claims); the six reviewed beat captions, against
  the beat facts and clip evidence (23/23, 31/31); the video's burnt-in captions (edit_v3.yaml), each number a claim
  on a fact built from its source file: counterfactual, pass X-ray, speed gun, keeper, ghost, Fourth Official,
  pitchwatch results (17/17). Overlay graphics are drawn from the same beat fields and not counted separately.
- Fact Checker gains a `px` unit (tolerance 0.05) for graphics drift. Tests: all bound, and a number off by more
  than the tolerance or without a claim is caught. No model call.

---

## 2026-10-23 · Video v3 item 5, option (c): real newsroom executors over the real-clip moments, cached (track B)

- `python -m footage.studio`: per clip, the real Tactician, Narrator, Fact Checker, Director and CueBus executors run
  in-process over the featured moment (and Spurs' Fourth Official cue through Director and CueBus), against the
  clip's evidence; model calls answered from the cache by the reviewed gemini-4-argon outputs (no spend); the
  precomputed steps (ingest, scout, proposer, rollout) are trace rows saying so. Output per clip:
  `data/footage/<slug>/cache/studio/stream.jsonl` ({seq, clip_ms, t_ms, collection, doc}: moments, counterfactuals,
  traces, explanations, cues) for track C's studio replay. 4 verified Sliding Doors cues + the Fourth Official cue;
  no synthetic league name in any cue, why or explanation; bar labels from the real clubs.
- Product changes: the Director shows a producer-selected moment (`selected_by: "producer"`) below the Sliding
  Doors leverage floor and records `floor_waived` in its trace (test); its swing-bar label uses a real clip's clubs;
  the Tactician's prompt version can be set per run (`deps.state["tactician_prompt"]`) so a replay records the
  prompt that really wrote the text. Leverage is the Scout's measure on the real tracked frames (Liverpool 0.003,
  Man Utd v City 0.012, Spurs 0.021: waived; Arsenal 0.052: above the floor).
- Kill-resume stays a golden-match feature (lead's decision for v3).
- Track C's container: one blackboard sqlite per clip, `data/footage/<slug>/cache/studio/blackboard.sqlite`
  (api shapes: events with match_metadata incl. real clubs and kits, facts, pitch_control, moments,
  counterfactuals, traces, explanations, cues, requests), timed on the match clock: moment at its t_ms, traces
  0.3 s apart after it, the cue after the last trace. Every cue verifies inside its own sqlite.
- Veto: a full-time recap of Liverpool v Man City (`footage.recap_beat` from the tagged goals and red card;
  Argon caption "Manchester City rally past Liverpool", $0.0062; review added the count and scorer claims) goes
  through the Director, which holds it: `requests` doc req_m_9001_recap_0 at t_ms 6,281,900 (104:41.9).
  Goal scorers named outside the moment files are kept in roster.json `named` (ids frozen; overflow ids p_98x).
- Keeper beat: the coverage assumptions are in its source line and a `small_print` field (lead's request).
- Cached caption answers moved from `insights/` (git-ignored by track A's rule) to `captions/`, so a clean
  checkout never pays twice. Red-card cost: dropped from v3 (lead), kept as an honest negative result.

---

## 2026-10-23 · Video v3 item 2: ghost defender on Mbeumo's and Dorgu's goals (track B)

- `python -m footage.ghost_beat`: shot frames from track A's tracks (127: Mbeumo, track 25, clip 1079.36 s; 137:
  Dorgu, track 6, clip 1189.84 s; the tags put both goals at 64:27 and 75:30), City positions one second earlier,
  `footage.ghost` (the defender with least ground into the shooting cone at 7 m/s) and 200 forced-shot rollouts.
- **Dorgu (75:28):** a City defender (track 1, shirt not readable) needed **6.5 m**, within the 7 m he could cover
  in the second: the engine's goal chance falls from **26% to 19%** with him there (formula 15.6% -> 10.5%).
- **Mbeumo (64:27):** the closest City defender (track 28) needed **10.7 m** in that second, beyond 7 m: no City
  defender could have got into the shooting lane; with one there 5% -> 4%.
- Captions on gemini-4-argon (insight_footage@2, $0.0152), both verified first time; review: Mbeumo's headline leads
  with the finding, "7.0" -> "7". Beats `manutd-mancity-2526/cache/v3/ghost_defender_{1078360,1188840}.json`
  (freeze one second before the shot, homography included).

---

## 2026-10-23 · Video v3 item 1: what Bruno's red card cost, engine estimate: no clear cost (track B)

- `python -m footage.redcard run 11v11|11v10` + `combine`: from the frozen 40:57 state (Man Utd 0-1 Spurs) the
  engine plays to full time twice, same seeds per world, n=400 each, scripted_v1, seed 9004; 11 v 10 sends off
  Bruno's role (slot 6, CM) with track A's `Override(sent_off=...)` (583039d).
- Result: Man Utd win 7.3% -> 10.3% (gap CI -0.8..+7.0 points), draw 21.5% -> 15.3% (-11.8..-0.8), loss 71.3% ->
  74.5% (-2.8..+9.5); goals conceded 0.70 -> 0.83; expected points 0.43 -> 0.46. **No clear cost in the engine**
  (only the draw gap is outside noise). Not captioned: a "cost" caption would overstate it. First run (slot 3, a
  centre-back from the role prior) even had United scoring more with ten; the engine's 10 v 11 keeps the ten in
  their slots (no reshuffle). Beat `manutd-spurs-2425/cache/v3/red_card_cost_772400.json` with `gap_significant`.
- CPU only, $0.

---

## 2026-10-23 · Video v3 item 3: keeper positioning, David Raya at 92:15 (track B)

- Track A's tracks for shots 113/190 put the keeper far from his goal (calibration near the goalmouth), so the save
  frame was hand-marked: Chelsea's close-range chance at 92:15 (clip 1382.65 s, saved at 1383.3 s); goal-area
  homography from posts, six-yard box and the D's junctions (8 points, RMS 0.1 m, leave-one-out <= 0.54 m).
- `footage.keeper` geometry (the engine's shot model ignores the keeper): from where he stood (1.2 m off his
  line) Raya covers **39%** of the goal mouth against a shot from 4.5 m; the best point on the bisector, 1.8 m
  further out, covers **100%**. Assumptions (shot 26 m/s, reaction 0.25 s, dive 3.5 m/s, reach 1.0-2.6 m) in the
  beat. Beat `arsenal-chelsea-2526/cache/v3/keeper_cone_1382650.json` (coverage_* fields, save_* null).
- Caption on gemini-4-argon (insight_footage@2, $0.0073), verified first time, accepted in review: "David Raya covers
  39% of the goal mouth".

---

## 2026-10-23 · Video v3: Argon captions and explanations after the ADC refresh (track B)

- ADC quota project set to ffc-19484 (owner: "no other"); WHYLINE calls go to ffc-19484 only.
- Win-probability river caption (gemini-4-argon, insight_footage@1, $0.0096): "Liverpool reach 91% win chance
  before Man City rally"; hand review added the "9%" claim (f_800006); in the beat's `caption`.
- The four Sliding Doors explanations regenerated on Argon from the current (tracked) counterfactuals ($0.031);
  Liverpool and Spurs verified as written, Man Utd v City ("the number 19", unbound) and Arsenal (Sánchez not in
  the cited evidence) fixed in review; lines condensed from the reviewed why. The hand-written Fourth Official text
  is gone: the cue now takes its text from the reviewed Argon caption of the new `fourth_official` beat
  (insight_footage@2 adds km/h and "assessment, not a ruling"; $0.0049): "Bruno Fernandes red card: closing in at
  about 15 km/h" ("15.3" -> "about 15" in review: other windows give 15-25 km/h).
- Model answers are cached per beat (a re-run never pays twice); a beat keeps its reviewed caption while its data
  is unchanged. Real-clip spend this round $0.0558; footage total so far $0.69.

---

## 2026-10-23 · Video v3 item 4: win-probability river, Liverpool v Man City final 20 minutes (track B)

- `python -m footage.river`: the engine's win-probability head on the real score (from the T-106 tagged goals) and
  clock every 15 s, 72:00-104:45 (132 samples; the score bug runs past 99:59 in stoppage time), clock mapped to the
  video through the score-bug readings. Context features the head also takes (xT/xG difference, chaos) are not
  measured on real footage and are held neutral; stoppage time is valued as minute 90 (the head's training range).
- Markers: Szoboszlai FK 1-0 at 73:26 (Liverpool 15% -> 78%), Silva 1-1 at 83:37 (91% -> 9%), the Oracle window at
  86:15 (peak p(shot in 10 s) 60%), the Sliding Doors moment at 86:23 (+2 points), Alisson's penalty foul at 90:15,
  Haaland's penalty 1-2 at 92:43 (City 2% -> 96%), Cherki 1-3, Szoboszlai's red card. No model call, $0.
- Cache: data/footage/liverpool-mancity-2526/cache/river/wp_river.json (`result.samples`, `result.markers`).
  `pytest tests/footage` 28 passed.
- v3 items 1-3 found two engine limits: no sending-off (asked track A for one) and a shot model that ignores the
  keeper's position (keeper item to be a geometric goal-coverage measure, said so on screen).

---


## 2026-10-23 · T-065 Day-7 bug bash (track A) — not closed

- Every Verification command of T-001..T-064 run in order (adapted where it would spend money, rewrite the frozen
  cache, re-run hour-long jobs or need Azure): **52 pass, 2 fail on machine load, 2 not built (Azure T-058/T-059)**.
  Table, adaptations and P1 list: `docs/evidence/bugbash_v0.1.md`. No P0.
- `make ci`: 465 passed; 3 timing budgets fail under load (load avg 25-160, not project jobs; passed idle) and 3
  test_batch errors (asyncio.run after Playwright; filed to track B with the fix). Clean replay --runs 1: PASS, same
  hash as T-064.
- Also today (footage, owner priority): T-103 replay/trim/overrides, T-105 recall 0.993, tracks for the four
  featured frames and the Bruno Fernandes foul (contact frame 23172) handed to track B; T-104 gate still open
  (refined max 2.21 m vs 1.5 m).

---

## 2026-10-23 · Video v2: Fourth Official on Bruno Fernandes' red-card foul (track B)

- Contact found in the live wide shot (shot 90, clip 772.4 s, 40:57; the score bug confirms it): track 3 (Spurs,
  ball at his feet) is James Maddison, track 22 (Man Utd) closes in and meets him at frame 23172, so track 22 is
  Bruno Fernandes (track A's first reading, t19/t12 at 41:01, was the aftermath).
- `python -m footage.fourth`: moment `moments/772400.json` from tracks/90.json; the Fourth Official's measures:
  contact point (69.8, 53.5) in midfield near the far touchline, **outside the penalty area**; closing speed
  **4.25 m/s (15 km/h)** over the 0.5 s before contact (other windows 5.4 and 7.1 m/s, all above the 3 m/s "at
  speed" line; positions are 0.5-1 m here); referee's decision reported as what happened (straight red at 41:04).
- Text hand-written in review (`review/footage/fo_manutd-spurs-2425_772400.md`, no model call: ADC still expired),
  always "assessment, not a ruling"; Fact Checker gate passed against the tagged foul and card events (linked to
  the players) and a closing-speed fact. Cache: `fourth_official/c_907724.json` (cue.schema.json), `ruling_772400.json`
  (contact point, speeds, Bruno's run for the line), `evidence_772400.jsonl`.
- Player ids are now frozen per clip in `data/footage/<slug>/roster.json` (cached explanations cite them); new
  labels get the next free id (Maddison p_965, Bruno p_966). Spend $0. `pytest tests/footage` 26 passed.

---

## 2026-10-23 · Video v2: Oracle threat front on Liverpool v Man City (track B)

- `python -m footage.threat <slug> <start_ms> <end_ms> [--step-ms] [--n]`: the Oracle (rollout.oracle) on every
  sample of a tracked window: moment from track A's tracks, 100 unforced worlds x 8 s, p(shot in 10 s) per team
  (Oracle's 8-10 s estimate), the attacking team's shot origins and their mean + 2-sigma ellipse (the threat zone)
  in the moment file's pitch metres, plus that frame's homography; smoothed p for drawing. No model call, $0.
- Window: clip 14:27-14:35 (86:15-86:23, shot 62, paint-refined calibration), 17 samples at 0.5 s. Liverpool's
  smoothed p(shot in 10 s) builds from ~10% to 60% as Szoboszlai carries; the zone moves from left of centre
  (97, 38.7) to central (96.4, 32.7) in front of goal. Cache: data/footage/liverpool-mancity-2526/cache/oracle/
  window_867000.json (`result.samples[]`).
- Converter fixes found on real tracks: ball detections off the pitch or under 0.3 confidence are ignored (a
  fixed false ball at (106.3, 53.1)); a missing ball is taken from the nearest sample within 0.5 s; the window
  keeps the last holder when no trustworthy ball is near. `pytest tests/footage` 25 passed.

---

## 2026-10-23 · T-107/T-109: all four featured moments from tracking (track B)

- Track A's tracks for Man Utd v Man City (shot 104), Arsenal v Chelsea (177) and Man Utd v Spurs (84) converted
  with `footage.from_tracks --write`; every hand label matched a same-team track (12/12 median 0.57 m, 15/15
  median 1.16 m, 5/5 median 0.34 m). Label fixes per frame in `moments/overrides.json` (applied by the converter):
  referees t11 (MUN v MCI) and t38 (ARS v CHE), t15 = Chelsea, keepers t47 (CHE), t20 = **City's** Donnarumma
  (the goal Man Utd attack) and t37 = **Man Utd's** Onana (the goal Werner attacks); the hand marks and the frames
  decide the two keepers where the suggested labels had them the other way round. Hand files kept in moments/hand/.
- Counterfactuals recomputed (200 x 8 s): Man Utd v Man City shot 2.8% vs pass to #19 1.7% (shot right);
  Arsenal v Chelsea shot 3.3% vs back to Saka **19.6%**, +2.1 points (was 12.2%, +1.3); Man Utd v Spurs shot 2.7%
  vs round the keeper 1.7% (shot right). Reviews updated to the new numbers by hand (no model call; ADC expired),
  Fact Checker gate passed for all four. `roster`/`clip_moments` skip overrides.json.
- Verification: `pytest tests/footage` 23 passed; validate_schemas OK.

---

## 2026-10-23 · T-107/T-109: Liverpool 86:23 moment from tracking (track B)

- Track A's tracks/62.json (re-tracked, through track C's calib/62_refined.json) converted with
  `footage.from_tracks --write`: 18 tracked players; 17 of 19 hand labels matched a same-team track (median 0.44 m,
  max 2.16 m); L4 (one of a close pair at the D) has no track and keeps its hand mark; the occluded C2 is the
  unlabelled track t69. Velocities are the tracks' 1 s differences (common mode +0.6, -1.8 m/s: both teams shifting
  to the ball side, per track A/C, ~1.5 px calibration drift). Hand marks kept in moments/hand/875000.json.
- Counterfactual from tracked positions: shot 3.1% (was 3.0%), pass to Salah **5.3%** (was 7.7%), **+2.0 points**
  (was +4.2). The reviewed explanation failed its own check (test caught it); a fresh Argon call failed on expired
  gcloud ADC (no spend), so the cached model explanation was re-reviewed by hand to the new evidence
  (32 metres, 3%, 5%, 2 points), Fact Checker gate passed.
- Converter: an untracked hand-marked player is kept only while his team has fewer than 11 (else an unlabelled
  track is him). Verification: `pytest tests/footage` 21 passed; validate_schemas OK.

---

## 2026-10-23 · T-107 part 2: Pitchwatch tracking -> moment files; licence scan fix (track B)

- `python -m footage.from_tracks <slug> <clip_ms> [--write]` reads track A's Pitchwatch format v1 (shots.json,
  calib/<shot>.json, tracks/<shot>.json): the usable shot containing the frame, the nearest trusted homography,
  players and ball at the nearest tracking sample, velocities from the 1 s difference, y flipped to the near-side
  origin (homography composed with the flip). Labels, names, clock, score and the real action come from the
  hand-marked moment (nearest track of the same team within 2.5 m); it reports how far tracking and hand marks
  disagree, and with --write keeps the hand file in moments/hand/. Waiting for tracks/62.json (Liverpool 13:22-14:51,
  which holds the 86:23 featured frame) to run it for real.
- T-066 follow-up (73d7e40): the licence scan stripped the closing parenthesis of "ISC License (ISCL)" and did not
  know "Apache 2.0 License" (track A, T-105 stack); fixed, track A's two exceptions removed, 219 entries 0 offenders.
- Verification: `pytest tests/footage tests/tooling/test_licence_scan.py`.

---

## 2026-10-23 · T-109 Featured real-clip moments: select and precompute (track B)

- Four Sliding Doors moments, one per clip, each frozen from a 1080p frame inside a steady wide shot and
  hand-marked (homography from box/goal landmarks, RMS 0.19-0.21 m; missing players by role prior). Tracking (T-105)
  can replace the hand marks later through the same moment files.
- `python -m footage.featured`: 200 rollouts x 8 s of the real action and the alternative from the same state and
  seeds (scripted_v1), pitch-control snapshot, evidence (tagged events with the real action as anchor, facts,
  match_metadata with the clip's roster and clubs), gemini-4-argon explanation (prompts/tactician_footage@1.md,
  live, SpendGuard per clip match id, $0.10 per moment limit), Fact Checker; cache per clip in
  `data/footage/<slug>/cache/` (manifest + evidence.jsonl). `python -m footage.review export|import`: hand review
  gated by the Fact Checker; 4 imported, 0 refused (explanation@reviewed + footage_line@1, hand_reviewed).

  | clip, clock | real action | alternative | goal chance real -> alt | win chance |
  |---|---|---|---|---|
  | Liverpool v Man City 86:23 | Szoboszlai shoots, 31 m, blocked | pass to Salah | 3% -> 8% | +4 points |
  | Man Utd v Man City 56:41 | Amad shoots, 18 m, saved | pass to #19 in the box | 2% -> 2% | shot was right |
  | Arsenal v Chelsea 79:10 | Eze shoots, 19 m, saved | back to Saka | 2% -> 12% | +1 point |
  | Man Utd v Spurs 38:02 | Werner shoots, 21 m, saved | round the keeper | 3% -> 1% | shot was right |

- Fact Checker: a footage match lists its real players and clubs in match_metadata (`roster`, `clubs`); exactly
  those names pass rules 3 and 7 for that match, any other real name is still banned; synthetic matches unchanged
  (golden replay 55/55 verified, 0 misses). 3 of 4 model explanations verified first time; Man Utd v Man City
  said "the number 19" (an unbound number), fixed in review.
- **Spend: $0.0294** (4 Argon calls, ~$0.007 each). Footage total so far $0.6367.
- Engine caveat for the README (T-111): outcomes come from the synthetic engine replaying a frozen frame; e.g.
  Werner's one-on-one is a 3% goal chance there, far below what a real 1v1 is worth.
- Also: `to_state` refuses a label used twice (Eze and Chelsea's #10 collided); validate_schemas covers
  data/footage (5357 documents OK). Verification: `pytest tests/footage tests/newsroom/test_factcheck.py` 77 passed.

---


## 2026-10-23 · T-064 Clean-machine replay test and one-command demo (track A)

- `scripts/replay_headless.py` (mcp, newsroom supervisor and api replay on free ports, loopback-only network guard,
  stall detection with stack dumps), `scripts/clean_machine_replay.sh`, `docker-compose.yml` +
  `docker/python.Dockerfile` + `.dockerignore`, `make demo` / `make clean-replay`.
- **3/3 fresh-clone runs: identical cue-stream sha256 `b90e1e03...`**, 55 cues all verified, 125/125 moments, 0
  refused connections, ~9 min each at x10. Evidence: `docs/evidence/clean_replay_v0.1.md`.
- Not verified: `make demo` itself (Docker daemon not running here; compose file validated). One earlier run stalled
  after mo_00020 and has not recurred; the harness now diagnoses a stall instead of waiting an hour.
- Verification: `bash scripts/clean_machine_replay.sh --runs 3` -> PASS.

---

## 2026-10-23 · T-108 Real-frame compositing, part 1 (track C)

- `demo.footage`: broadcast camera = homography + one radial lens term k1, fitted from >= 4 hand landmarks and
  refined ICP-style against the frame's own paint (white top-hat on blue, players masked, boards cut by a sloped
  `top`); the pitch model draws line centres (Laws dimensions are to the outer edge of 12 cm lines, ~2 px here).
  `drift_px` = offset along the normal from projected model line to marking centre, pooled over lines found along
  >= 50% of their visible length; every line's figure kept.
- `python -m demo.composite <moment> [--png] [--clip] [--standin]` (moments in `packages/demo/footage_moments.yaml`,
  players from T-107's moment file): freeze grade with the two players lit, ground rings and tags, 200 ghost futures
  (baseline white, alternative orange, Catmull-Rom, clamped to pitch + 2 m), dashed alternative pass, referee lines,
  swing card with n/horizon/seed; PNG and a 14 s clip (4 s real, 7 s freeze, 3 s resume). Outputs git-ignored in
  `packages/demo/out/footage/`.
- **Measured, Liverpool v Man City 86:23 (clip 875 s):** k1 +0.039; drift **median 0.65 px, p95 1.76 px** (675
  samples: penalty box, goal box, goal line, penalty arc); far touchline left out (found on 3% of it under the
  boards). A referee line drawn along the box edge through the painter lands on the paint at median 0.77 px, p95
  2.19 px (a smooth S along that 40 m line; no lens model does better). H alone: p95 2.20; k1+k2: 1.90. Synthetic
  frame from a known camera: k1 recovered 0.0346 of 0.035, drift p95 0.38 px.
- **Pending:** T-109's counterfactual for the moment (until then `--standin` re-anchors cf_000070, watermarked,
  never in the video); T-104's per-frame camera when it lands. Verification: `pytest tests/demo/test_footage.py`
  8 passed (2 need the clip on this machine).

---

## 2026-10-23 · T-107 Moment freeze and hand-correction, part 1 (track B)

- `footage.freeze`: a moment file `data/footage/<slug>/moments/<clip_ms>.json` (players and ball in pitch metres,
  homography, home direction, clock, score) becomes a branchable engine `State`: `fill` assigns every observed player
  an engine slot (4-3-3 role prior shifted to the team's observed line, Hungarian matching) and adds the missing ones
  at their role position, pushed off camera when the homography says they would be visible; `to_state` builds a
  neutral synthetic fixture (league-average styles), mirrors the frame into the engine's period convention, sets
  positions, velocities, ball, score and the holder in control, and returns `snapshot_state()`.
- `python -m footage.editor <slug> <clip_ms>`: local page (127.0.0.1) with the frozen frame and a top-down pitch;
  drag a dot in either view, the other follows through the homography; "Fill missing" and "Save". Checked in the
  browser pane: dots sit on the players' feet; image and pitch drags update the file model; prior dots draggable.
- Starter frame without tracking: Liverpool v Man City 86:23 (clip 14:35), hand-marked from the 1080p frame,
  homography from 8 box/goal landmarks (**RMS 0.19 m**, leave-one-out <= 0.8 m); 19 players seen, 3 by role prior.
  Szoboszlai shoots from 31 m (blocked) with Salah free wide right. 200 rollouts x 8 s from the frozen state: forced
  shot p_goal 3.2%, pass to Salah 4.6%, engine's own choice 11.6% (1.5 s CPU).
- **Pending:** reading track A's tracking output (T-105; format not published yet) into moment files with 1 s
  velocities. Verification: `pytest tests/footage` 10 passed.

---

## 2026-10-23 · T-106 Gemini event tagging of the real clips (track B)

- `python -m footage.tag [slug...]` (packages/footage/tag.py, config/footage.yaml): each clip is cut by ffmpeg into
  180 s, 360p, 5 fps segments (git-ignored media) sent **inline** to gemini-3.8-flash on Vertex AI (no bucket, no
  Files API, no new GCP resource: owner rule) at low media resolution and 1 frame/s, thinking off, with a JSON schema.
  Every call goes through SpendGuard under the clip's own match id; a clip stops at $0.40.
- Output: `data/footage/<slug>/events.jsonl` in event.schema.json form (players have no p_ ids: `player` null,
  `attrs.player_name`; `attrs.clip_ms` links back to the video; replays dropped; clock read off the score bug or
  carried between reads); raw answers in `tags/` (re-runs cost nothing).
- **Spend: $0.6072 for 40 segments, 113 min of video** (m_9001 Liverpool v Man City $0.1893, m_9002 Man Utd v Man
  City $0.1384, m_9003 Arsenal v Chelsea $0.1365, m_9004 Man Utd v Spurs $0.1431); ~17k tokens in per 3 min.
- 284 live events (169 replay tags dropped), 0 schema errors. Spot check against the broadcasts: the goals
  (Szoboszlai FK, Silva, Haaland pen, Cherki; Mbeumo, Dorgu, Mount; Saliba, Timber; Johnson, Kulusevski, Solanke),
  Bruno Fernandes' straight red at 41:04, Neto's second yellow, the Raya saves are all tagged with the right clock.
- **Agreement with tracking-derived events: pending** (T-105, track A, not landed); to be measured when it lands.
- Verification: `pytest tests/footage/test_tag.py` (conversion, replays, clock carry, boundary dedupe) 4 passed.

---

## 2026-10-22 · T-069 part 1 Video v1 final pass (track C) — waiting for the human steps

- Manifest unchanged since the takes → no re-record. Machine frame review: no real marks or names; Dugout clip cut (no
  dugout cue in the golden cue stream). Captions: 0 banned hits. **final_v1.mp4 104.37 s**
  (`packages/demo/out/final_v1.mp4`, sha256 98a21523…).
- `docs/video/VERSION` = 1; `docs/video/v1.md` with manifest_sha256 48fed423…, caption → source table. Verification
  command passes.
- **Human steps open:** a person watches it frame by frame and signs `docs/video/v1.md`, then uploads (YouTube unlisted or
  a GitHub release asset) and pastes the link. Provisional until the T-057 regeneration decision.

---

## 2026-10-22 · T-063 Video v1 edit (track C) — provisional

- `packages/demo/{edit_v1.yaml,assemble.py,captions_v1.srt}`, `docs/video/architecture.html`. 12 clips, captions in a
  band below the picture, no music, no voice. Every caption number has a source in the edit list (results.md, the
  Sliding Doors counterfactual and its verified cue); unmeasured storyboard lines dropped (trained policy, Azure,
  Foundry, latency seconds, vendor names, oracle %).
- Verification: `python packages/demo/assemble.py packages/demo/edit_v1.yaml && ffprobe …` → **110.33 s** (limit 120).
  `tests/demo`: 12 passed. Video: `packages/demo/out/final_v1.mp4` (git-ignored, 21 MB).
- Provisional with T-062: recorded on the cache at 405fd91, before the T-057 regeneration.

---

## 2026-10-22 · T-062 Rehearsal and v1 recording (track C) — provisional

- **Provisional** (coordinator's call, option a): recorded on the golden cache at 405fd91, before the T-057 prompt
  bump/regeneration that waits on the owner's per-match cap decision; if approved, re-record only shots whose cue text
  changed.
- Rehearsal, whole golden match at x10 with the demo script: **0 cache_miss, 0 error**, 55/55 cues verified, one
  scripted `interrupted` row; kill on mo_00060 with the four TECH_PLAN 1.7 lines; half-time recap vetoed.
- **13 shots** in `packages/demo/out/` (git-ignored) plus 16 keyframes; kill and veto takes on a fresh blackboard with
  the demo script armed. Fixed on the way: /replay3d ready while paused, offside margin label from the claim, ghost
  clip, Player-Cam Decision Index (T-048 cache) and actor, Panel card label.
- Verification: `check_cue_evidence` OK (57 cues, 201 claims), `scan_banned` 0 hits, `ls packages/demo/out/*.webm`
  13 files: exit 0. Evidence: `docs/evidence/rehearsal_day6.md`.

---

## 2026-10-22 · T-057 follow-up: banned word in a cached Panel chair line (track B)

- Track C's T-062 scan (`scan_banned.py data/matches/4242/cache apps/*/src`) found betting 'Odds' in mo_00104's
  cached chair headline. New `review/chair_<moment>.md` import (gated by the rule-7 matcher): headline now
  "Passing Over Shooting: the Better Chance"; consensus and dissent unchanged.
- Visible change: the chair line now passes the Fact Checker, so c_001042 shows the chair's debate instead of the
  Narrator's rewrite. Replay 55/55 verified, 0 templates; scan **0 hits**; check_cue_evidence OK. No model call.

---

## 2026-10-22 · T-057 follow-up: seven cue lines the T-056 judge flagged, hand-reviewed (track B)

- The judge (31344a9) flagged factual swaps of actual and alternative: c_000201 (the alternative's 7% credited to
  the pass to Okafor), c_001181 (Ainsley named as shooter; Tolliver shot), c_000911 (the alternative's 1% to 9%
  credited to the clearance), c_000132 (a shot called "turning back"). Also rewritten: c_000612, c_001142 (vague
  Panel cards) and c_000261 (my own mo_00026 line, now with the clearance as the alternative). c_000552 and c_000302
  are vague but not false, so they stay as they are.
- `cache.review.export_lines` / `line_<moment>_a<n>.md` replaces the rewrite-only path: it records the claims the
  Narrator actually received in replay (for a Panel moment the Panel's, not the Tactician's), and the import gates
  each edit on exactly those through the Fact Checker. 10 lines imported, 0 refused; 54 entries `hand_reviewed`.
- Golden replay: 55 cues + 2 held, 55/55 verified, 0 templates, 0 `error`/`cache_miss` rows. No model call.
- Verification: `python scripts/import_review.py review/ && python scripts/check_cue_evidence.py --seed 4242 &&
  python scripts/validate_schemas.py && python scripts/check_spend.py` exits 0; track B suites 245 passed.

---

## 2026-10-22 · T-057 follow-up: three broken cached rewrites hand-reviewed, golden replay has no red rows (track B)

- Track C's x10 rehearsal showed 4 red `error` trace rows: the golden run cached three Narrator rewrites
  (narrator@2.a2) as broken output (mo_00026 a truncated `{"`, mo_00034 prose around a code fence, mo_00040 a
  failed call); the Director's row for mo_00026 followed from the first.
- `cache.review.export_rewrites` / import of `review/rewrite_<moment>_a<n>.md`: each line uses only the claims that
  pass the Fact Checker and is gated by it. All 3 imported (48 entries `hand_reviewed`). mo_00026's first line had
  the pass backwards ("Grabowski finds Fennimore"); the rewrite follows the evidence (Fennimore to Silva under
  Grabowski's pressure). No model call; spend unchanged by this.
- Golden replay: **0 `error` / `cache_miss` rows**, 55 cues + 2 held, 55 verified, **0 templates** (was 1).
  Test `tests/cache/test_review.py` fails if a broken cached rewrite comes back.
- Verification: `python scripts/import_review.py review/ && python scripts/check_cue_evidence.py --seed 4242 &&
  python scripts/validate_schemas.py && python scripts/check_spend.py` exits 0. Spend total $2.6815: the $0.36
  since the last entry is track A's T-056 judge evals.

---


## 2026-10-22 · T-056 Evals: latency, groundedness, cost; run_evals and results.md; evals-gate (track A)

- `packages/evals/{run_evals,latency,groundedness,cost,gate,judge}.py`, `newsroom/prompts/judge@1.md`,
  `packages/evals/results.{md,json}`, `tests/evals/test_gate.py`; CI `evals-gate` now runs the stdlib-only gate.
- results.md has every 1.11 row. Measured and passing: state F1 0.772, Brier 0.0629, placebo 0.987, planted errors
  500/500, false rejects 0/500, **groundedness 141/141 = 1.000** (55 golden cues from a replay of the committed
  cache), golden match $2.31 of $2.50, project $2.32 + judge. Cut line: policy metrics (top-3 0.505 vs 0.80, T-037,
  scripted_v1 ships). Pending with owner: live latency and cost per match (T-080; interim explained p95 12.9 s from
  the T-032 probe), realism (T-073), resume 20 runs (T-091).
- Groundedness first found 37 ungrounded numbers, all in my Fourth Official cues (closing speed in m/s, contact
  coordinates); fixed in 3193723 (T-049), stage re-run with track B's agreement.
- CI judge (gemini-4-argon via SpendGuard, no match id): **76% plausible** of 25 judged explained cues (1 timeout,
  4 no verdict); judge spend **$0.37** in total (<= $0.50). Its rejections include cues that swap the actual and the
  alternative action (c_000201, c_001181): reported to track B with the rule-2 finding.
- Verification: `python -m evals.run_evals --seeds 1..50 --out packages/evals/results.md && python -m evals.gate
  packages/evals/results.json` exits 0 (PYTHONPATH=packages).

---

## 2026-10-22 · T-038 follow-up: replay latency follows the live replay clock; error trace reasons (track B)

- Track C's x10 rehearsal fell ~20 min behind: CacheClient divided simulated latency by WHYLINE_REPLAY_SPEED read
  once at start. It now reads the api's clock `replay/<match_id>` {speed, playing} (9e14a91, track C) at most every
  0.5 s and sleeps in 0.25 s slices, so a speed change or a pause also applies to a wait already in progress; the
  env var stays the fallback. The worker passes its blackboard (`CacheClient(clock_bb=bb)`).
- Trace rows with a non-ok status now carry `reason` (narrator, fast line, Director red rows, Tactician, Proposer;
  `Draft.reason`): golden replay has 30 such rows, 0 without a reason. Replay output unchanged (55 cues + 2 held,
  55 verified, 0 misses).
- Verification: `pytest tests/newsroom tests/cache tests/chaos tests/mcp_server tests/blackboard tests/tooling`
  244 passed, 4 skipped.

---

## 2026-10-22 · T-057 Hand-review export/import, few-shots and cue stream (track B) — partial, no regeneration

- `--hand-review 20` exports the 20 highest-leverage moments (`review/mo_*.md`) and the 5 cached fast lines for
  goals and big chances (`review/fast_*.md`). All 25 edited in this session and imported: **45 cache entries
  `hand_reviewed: true`** (20 Tactician, 20 Narrator, 5 fast lines), **0 refused** by the Fact Checker;
  20 few-shots each in `fewshot/{narrator,tactician}.jsonl`. Re-import is idempotent.
- Review found two bugs, both fixed with tests: goal fast lines credited the passer ("Fennimore strikes" for
  Sandoval's goal), so `claims_from_moment` now names only the scorer or shooter; and the Director's 90 s dedupe hid
  explained lower-thirds behind the Panel's options card of the same kind, so it now compares kind and layer.
  Factcheck reads "1 point" as 0.01 win probability.
- Cue stream cached (`cue_stream` stage, kind `cue`): **55 cues delivered + 2 recaps held, 55/55 verified,
  21 explanations**, was 46 before the dedupe fix. replay_check clean (0 model misses, 0 counterfactual misses).
- **Not done:** prompt bump (tactician@4, narrator@3) and regeneration. m_4242 has spent $2.32 of its $2.50
  per-match cap, so regeneration can't run; the owner's call is pending. Regeneration spend so far $0.00.
- Verification: `python scripts/import_review.py review/ && python scripts/check_cue_evidence.py --seed 4242 &&
  python scripts/validate_schemas.py && python scripts/check_spend.py` exits 0 (57 cues, 201 claims, 0 problems;
  5053 documents; total spend $2.3191).

---


## 2026-10-22 · T-055 Evals: state detection and planted-error suite (track A)

- State detection (part 1, d8f4db8) re-run: macro **F1 0.772** (>= 0.75), accuracy 0.778, seeds 1-50.
- `packages/evals/planted_errors.py`: copies of the golden match's verified Tactician explanations (T-042, 0f62f8c;
  only **40** exist, 38 with a `why` that also passes, so outputs are **sampled with replacement**, said in the JSON),
  one injected error each, checked against the evidence replay preloads. **500 planted, 100% caught**, each type by
  its own rule: wrong number +-10% (rule 2), wrong player (3), wrong minute (4), unbound number (6), banned word (7).
  **False rejects 0 / 500** (0 / 40 unique) with the golden verdict's call.
- Finding for track B (reported, not gated): where +-10% is inside the tolerance and the number is pushed to the
  smallest visible change, **94 / 100** are caught. Rule 2 accepts any same-unit value of the cited evidence, so a
  number swapped for another of the same counterfactual (the alternative's 2% for the shot's 4%) passes.
  2 of 40 explanations have a `why` with an unbound number (rule 6 rejects it; the Narrator drops that why).
- Same numbers with track B's uncommitted factcheck.py edit and with the committed one.
- Verification: `python -m evals.state_detection --seeds 1..50 && python -m evals.planted_errors --n 500` exits 0.

---

## 2026-10-22 · T-042 Golden precompute, part 2: model calls (track B) — live, owner decisions

- Owner decisions: no new GCP resources, so no Vertex batch bucket; the golden precompute ran live with
  gemini-4-argon for the Tactician and pundits; T-042 limit raised from $1.50 to **$2.00** (TASKS.md).
  `--mode batch` without a bucket now runs live and says so.
- Golden run: 125 moments, 8 rounds, **302 requests** (1 failed at the provider), 21 extra counterfactuals for
  model-proposed alternatives, 133 tool results, evidence.jsonl (83 documents), batches.json with the custom_id map.
  Fact Checker: 113 of 154 lines verified first time; rejected ones were rewritten (max two rewrites).
  Spend **$1.42** (limit $2.00): $1.11 reported usage and $0.30 worst-case rows for abandoned hedge duplicates
  (hedging is now off in the precompute). Match m_4242 now at $2.31 of its $2.50 cap.
- New `replay_check` stage replays every moment from the cache with no model call: first pass 27 counterfactual and
  3 model misses (alternatives the engine cannot play, and one failed Narrator call, both unrecorded); `--repair`
  caches the engine's errors and the failed call as failed, so replay takes the golden run's own fallbacks. Now
  **0 misses, 46 cues, all verified**, 1 template (the failed call). The precompute ran its moments concurrently,
  so its Director let more cues through (59); the sequential replay's 46 are the real count.
- `schemas/model_cache.schema.json` (cached model results, tool results, batches.json) so `validate_schemas.py`
  covers every cache file: OK, 8 schemas, 4,975 documents. `simulated_latency_ms` is the measured live latency of
  each live role (proposer 2.3 s, Tactician 3.7 s, Narrator 2.1 s, pundit 3.8 s, chair 2.0 s, recap 20 s).
- `pytest tests/cache/test_batch.py -q`: 4 passed; my suites 204 passed. Correction to the T-050 entry: recap
  spend is $0.135, not $0.16.

---

## 2026-10-22 · T-050 Recap with producer approval; top_moments and timeline (track B)

- `executors/recap.py` (role `recap_live`, golden `recap`, both gemini-4-argon; inputs from MCP `top_moments`,
  `timeline` and `player_stats`, resolved before one structured call; template on failure),
  `prompts/recap@2.md`, `mcp_server/tools_recap.py` (both tools registered on the MCP server), Director
  `handle_recap` with `ctx.request_info` and `@response_handler on_decision` (TECH_PLAN 1.7, a veto never reaches the
  CueBus), worker publishing `{request_id, cue}` to blackboard `requests` and resuming from the pause checkpoint
  with `responses=` when `POST /producer/decision` writes the decision, without blocking other moments.
- `recap` and `recap_live` thinking low: at high the golden full-time recap spent all 6,000 output tokens on
  thinking and returned no text. Recap inputs now name scorers and clubs (the first run wrote "p_046" on screen).
- Golden recaps (via `--stages recap`): half-time "Okafor cancels out Sandoval's early opener", full-time
  "Tolliver hits late double for Verdant"; both pass the Fact Checker. Recap spend **$0.16** (limit $0.30): $0.12
  for the first attempt (high thinking, one empty, one rejected), $0.014 for the kept run.
- `pytest tests/newsroom/test_recap_veto.py -q`: 4 passed (veto never reaches the CueBus; approval delivers with
  `producer_status: approved`; resume uses `workflow.run(stream=True, responses=..., checkpoint_id=...,
  checkpoint_storage=storage)`; worker round trip; both tools).

---


## 2026-10-22 · T-036 policy_v1 decision-only rollout path and MPS performance test (track A)

- Code was in 0562d76 (policy_engine, loader guard, tests); budgets were missed by ~9% after T-014's per-player
  speeds. Now met by value-preserving engine speed-ups (`kickoff/engine.py`, `kickoff/rules.py`): per-team
  frame flips instead of `np.where` over a constant mask, `np.partition` for the second-deepest opponent, per-axis
  position clamp and steering scales instead of broadcasting a two-element array, the heading written in place,
  kick-off and dead-ball branches only when some world needs them. Golden 4242 regenerates byte-identical
  (events, tracking, truth) and a B=200 x 60 s branch hashes the same.
- Measured (load avg 5-30 from macOS storage services): policy_v1 200 x 8 s **0.281-0.287 s on MPS** (<= 0.30),
  **0.42-0.43 s on CPU** (<= 1.2); scripted 200 x 90 s **1.254-1.263 s** CPU (<= 1.3), 200 x 60 s 0.84 s (<= 1.2).
- Verification: `pytest tests/rollout/test_policy_perf.py tests/rollout/test_policy_determinism.py -q` 4 passed
  three times; `tests/rollout/test_perf.py` passes; tests/kickoff and tests/rollout green.

---

## 2026-10-22 · T-048 Decision Index precompute (track A)

- `packages/rollout/decision_index.py`: value = p_goal(actual) - max p_goal(engine's top-3 other options), n = 50,
  8 s, scripted_v1; per-player index = percentile of the mean value (>= 5 decisions). A pass to an offside team-mate
  (the engine will not force one) is valued from the realised state after the whistle (the 66:05 offside, e_2661).
- Golden match: **1,385 / 1,385** decisions valued, 27 players indexed, **1.7 min** with 8 workers (< 30 min).
- Live approximation: the goal-in-8-s head swing t - 100 ms -> t + 1 s, **net of the opponent**. Spearman with the
  rollout index **0.645** (gate >= 0.5). The team-only swing gave 0.417; checked on held-out seeds 1 and 2 (rollout
  index run for each): net 0.529 / 0.534, team-only 0.451 / 0.664, so net is the one that holds on all three.
- Cache: `analytics/decision_index.json` (producer decision_index, `$schema` analytics) + manifest entry.
- Verification: `pytest tests/rollout/test_decision_index.py -q` 4 passed; `python scripts/precompute.py --seed 4242
  --mode batch --stages decision_index` exits 0; `validate_schemas` OK.

---

## 2026-10-22 · T-040 Counterfactual calibration plot and placebo test (track A)

- `packages/evals/calibration.py`: every explained moment of the 300 held-out matches (seeds 51-350), re-simulated
  to the branch state, unforced branch n=200, 8 s with the goal-in-8-s hand-off, vs the realised outcome.
- Measured: **Brier 0.0629** (gate <= 0.18), log-loss 0.213, base rate 0.090, mean forecast 0.099, ECE 0.0117,
  9,226 moments; **placebo pass rate 0.987** (gate >= 0.95) on 8,420 testable moments. Engine scripted_v1 (from
  `packages/policy/artifacts/gate.json`, T-037). 39.2 min on CPU, 8 workers.
- Outputs: `packages/evals/out/{calibration.json,calibration.png,calibration_moments.jsonl}`.
- Verification: `python -m evals.calibration --seeds 51..350 --engine-from packages/policy/artifacts/gate.json
  --out packages/evals/out` exits 0.

---

## 2026-10-22 · T-070 Front-end bug bash and clean-load check (track C)

- Clean `npm ci` + build of all three apps; `pytest tests/apps -q` **41 passed**. New `scripts/frontend_sweep.py`:
  10 pages against a local replay + newsroom at every golden_moments beat: **0 page errors, 0 console errors, 0 failed
  requests, 0 phone overflow** (360/390/430 px). Fixed: replay docs from the golden cache (71a20ce), fan frame fills
  phones, PCF shadows in /replay3d. Open P1/P2 with owners in `docs/evidence/frontend_bugbash_v0.1.md`.
- Not done: the hosted Static Web Apps check; Azure is deferred by owner direction.
- Also: T-061 finished (74317bf) with the golden_moments clocks (kill 41:54, speed 1 76:52, speed 10 77:10).

---

## 2026-10-22 · T-042 part 1: batched golden precompute of model calls, code and tests (track B)

- `packages/cache/batch.py` (BatchingClient, RecordingTools, VertexBatchRunner / LiveRunner / FakeRunner,
  custom_id = hash of the cache key), `packages/cache/precompute_models.py` (the stages fast_lines, tactician,
  narrator, panel, factcheck in one pass), three lines in `scripts/precompute.py` to register them.
- Design: the real newsroom graph runs every golden moment; each model call parks until every workflow waits on
  one, then all parked calls leave as one batch per model (a round) and come back matched by custom_id. The Fact
  Checker and its rewrites run in the graph, so every line is cached with its verdict, under exactly the key
  replay looks up. Tool results and any counterfactual outside proposer_rule are recorded too; the evidence the
  Fact Checker saw goes to `evidence.jsonl`, which the replay worker now preloads (same verdicts, same rewrites).
  Golden roles: Tactician and pundits on gemini-4-argon (`tactician_golden`, `panel_pundit_golden`).
- `pytest tests/cache/test_batch.py -q`: 4 passed. On four golden moments with a fake model (answers returned in
  reverse order): 8 rounds, 18 requests, every line verified 7/7, and a replay of the same moments through
  CacheClient has zero cache misses and identical cues.
- Waiting: the real golden run (`python scripts/precompute.py --seed 4242 --mode batch --bucket gs://...`) needs a
  Cloud Storage bucket for Vertex batch I/O; asked the owner (only buckets of other workloads exist in ffc-19484).

---

## 2026-10-22 · T-037, T-039, T-046, T-047 done; heads, encoder and policy rebuilt (track A)

- T-037 gate (`gate.json`): **scripted_v1**. top-1 kind 0.810 (pass), **top-3 kind+target 0.505 vs 0.80 (fail)**,
  4 s FDE 21.4 m vs 31.8 m baseline, teleports 0, shape collapse 0.2%, offsides 0.001. The rule's own probabilities
  reach only ~0.44 top-3, so the gate is unreachable for an imitation of this engine. Evidence:
  `docs/evidence/policy_gate_day4.md`, 20 clip strips.
- Rebuilt on the regenerated corpus: heads v1 (all gates pass: xG ECE 0.0088, pass 0.0044, win prob 0.0262,
  goal-8 s 0.0001, chaos AUC 0.764), MomentEncoder (purity **0.715**; names from one Gemini call, $0.0014; naming is
  now its own step after an expired credential lost a run), policy_v1 (8 epochs, val loss 2.753, kind acc 0.815).
- Found: LightGBM *training* segfaults with torch loaded; `heads` no longer imports torch, `rollout` imports
  `policy` (torch) first.
- T-039: golden cache (analytics for 54,001 frames, 125 moments / 60 explained with pitch-control snapshots,
  82 counterfactuals, scripted_v1) and `packages/demo/golden_moments.yaml`: Sliding Doors **76:56** (p_020 shoots,
  pass to p_023 was on: win chance 17.2% -> 20.9%), offside 66:05, cards 60:50 and 75:04, Oracle 83:30 (59%,
  confirmed), Dugout 60:00, kill 41:54. Track C to move `demo_script.yaml` clocks (76:52, 41:54).
- T-046 Oracle: 2,700 forecasts every 2 s at n = 200; `api/oracle.py` feeds C's replay feed. T-047 Dugout at
  90 s scripted: Verdant "keep the ball" +0.46 pts, matched 60:00-70:00 (caption allowed); Ironvale tie, no call.
- T-036: determinism passes (MPS twice, MPS vs CPU). Budgets **missed by ~9%**: policy 200x8 s 0.31-0.33 s on MPS
  (0.30; the GPU forward alone is 23 ms x 16 calls), scripted 200x90 s 1.42 s (1.3). Policy path is unused
  (gate = scripted_v1). 200x60 s 0.92 s and policy on CPU 0.46-0.51 s pass.
- Running: T-040 calibration (seeds 51-350), then T-048 Decision Index.

---

## 2026-10-22 · T-061 Demo script runner, shot list and Playwright recorder (track C)

- Finished on top of part 1 (963361d) once `golden_moments.yaml` landed (T-039, dd6f339). `demo_script.yaml`: the four
  1.8 actions at the golden beats: kill 41:54 (`@kill`), veto 45:00+15s (half-time recap), speed 1 at 76:52
  (`@sliding_doors-4s`), speed 10 at 77:10 (`@sliding_doors+14s`). TECH_PLAN's 44:10/31:10/33:00 were the draft match's.
- Verification: `pytest tests/demo/test_demo_script.py -q` **9 passed** (clocks agree with golden_moments to the second;
  runner fires each action once, waits for a late recap request, re-arms on seek back); `python -m demo.record_demo
  --shots packages/demo/shot_list.yaml --dry-run` exits 0 with **14 shots** over the 8 beats (architecture page comes
  with T-063). A real 2.5 s GPU recording writes `.webm` + keyframe PNG.

---

## 2026-10-22 · T-029 follow-up 2: contested passages on the regenerated golden match (track B)

- Track A's regenerated golden 4242 (movement realism, 0353e09; heads v1 498119e) gave 136 moments, **69 explained**
  (limit 60). Besides 28 chaos-state changes, many play moments were the same ball state counted per touch: shot,
  block or clearance, rebound within a second, by both sides, each carrying the same goal-in-8-s swing.
- The Merger now treats touches of both sides within SAME_INSTANT_MS (1 s, the existing constant) as one contested
  passage, named by the side with the larger swing; a goal or whistle absorbs either side's touch in the second
  before it. Moments whose auto-event names no event (an overload seen in tracking only) cite the last event before.
  The 0.04 threshold is unchanged.
- Golden 4242 now: **125 moments, 60 explained** (28 state changes, 23 decisions, 4 goals, 5 others), 20 referee,
  5 fast, 2 recap. 60 is exactly the upper limit; nearly half the explained moments are chaos-state changes from the
  T-013 state machine (two chaotic spells and twelve Settled/Transitional flips), flagged to track A.
- `pytest tests/newsroom/test_scout.py -q`: 23 passed. My suites on the new golden: newsroom, mcp_server, cache,
  chaos, blackboard all pass (two Proposer tests now pick a team-mate other than the pass actually played).

---

## 2026-10-22 · Movement realism fix (T-014) and full rebuild (track A)

- Track C found 10.5 km in 60 min and every top speed exactly 28.0 km/h. Cause: one sprint speed for all players
  (7.8 m/s) and constant jogging to formation spots (13.5 km per 90). Fix: per-player top speed from position, pace
  traits and age (25-35 km/h, no random draw); formation movement eases to a stop within 3 m (keepers, ball carrier,
  pressers, runners exempt); offsides and goals re-balanced. Seeds 1-50: completion **0.804**, shots **13.8**,
  goals **1.58**, offsides 0.64; outfield **11.6 km/90**, keepers **5.7 km**, fastest per match median **34.1 km/h**.
  State detection macro F1 0.773 (seeds 1-30). `tests/kickoff/test_realism.py` now checks distance and top speeds.
- Golden 4242 regenerated: **Verdant 3-1 Ironvale** (goals 08:18 away; 23:29, 83:37, 85:49 home), 1 offside,
  2 cards. Fourth Official cache rebuilt (20 cues). Tracks B and C told; B asked to hold T-042 until A commits the
  regenerated `cache/moments.jsonl`.
- Rebuilding everything trained on the old engine: corpus (2,350 matches), heads v1, policy dataset, policy_v1
  training (restarted; the old-engine run was stopped after epoch 2), moment encoder, auto-events report, golden
  caches. Chain: `data/runtime/rebuild_chain.sh`.
- Also fixed: ruff B905 in `tests/kickoff/test_no_truth_leak.py`.

---

## 2026-10-22 · T-041 follow-up: live Panel on Flash pundits, 20.6 s (track B) — cut line lifted

- Owner decision: Flash for live pundits if it brings the Panel within budget. `panel_pundit` is gemini-3.8-flash
  (thinking off, 4 s hedge); a new `panel_pundit_golden` role keeps Argon for the golden precompute (T-042).
- Live run (golden 45:15, Okafor shot vs carry): **20.6 s** of the 25 s budget (evidence 3.6 s, three pundits
  14.9 s at 3.8 / 7.5 / 3.5 s, chair ~2 s), $0.009. `WHYLINE_LIVE_TESTS=1 pytest tests/newsroom/test_panel.py -m
  live`: passed. The day-4 cut line is lifted: `panel_enabled` defaults on (`WHYLINE_PANEL=0` turns it off).
- The live test's warm-up now advances the engine explicitly (it re-simulated 45 minutes before, 29.7 s).
  Pundit rules ask for whole percentages on screen (the run wrote raw fractions like 0.152).

---

## 2026-10-22 · T-032 follow-up: Flash live Tactician, explained cue p95 12.9 s (track B)

- Owner decision: pick the live Tactician model by measurement, Argon stays for the golden batch. `tactician_live`
  is gemini-3.8-flash, thinking off (4.4–5.3 s, $0.003 on the Tactician prompt vs 9–14 s on Argon); Proposer
  thinking off. The Tactician gets the last 15 s of events up front (no `query_events` round), the Proposer starts
  the rule alternatives' rollouts while it runs, and `LiveClient` hedges slow calls (`hedge_after_s` per role: a
  second identical request, first answer wins, the loser gets a worst-case ledger row).
- Probes over six golden decision moments (load average 200–340): 15.9 → 15.7 → 16.2 → **12.9 s p95**, p50 10.4 s,
  5/6 delivered (the sixth had no plausible alternative), every cue verified. T-032's live test passes on Flash.
  Details: `docs/evidence/latency_probe_day3.md`.
- Bugs fixed: the worker died on its first idle second (a `wait_for` around the watcher closed the async
  generator; regression test added); the MCP counterfactual tool re-checks its store inside the engine lock.
- Spend since the decision: $0.10 ($0.088 reported, $0.012 worst-case rows). T-032 total on the ledger is now about
  $0.68 against its $0.50 dev budget (most of it worst-case rows from the Argon timeouts this morning).
- Note: uncommitted engine edits in the shared checkout (track A, 02:15) made re-simulation diverge from the golden
  events, so rollout-dependent tests fail in the working tree; my tests pass on committed code plus my changes in a
  detached scratch worktree (192 passed).

---

## 2026-10-22 · T-029 follow-up: one moment per event (track B)

- After track A's heads v1 (T-025) the golden match gave 61 explained moments (limit 60). Six were the same event
  counted twice: a pass that ended offside was both a "decision" and an "offside" moment, and a shot or big chance
  followed by its goal was two moments, each taking the explained branch. The Merger now lets a goal or referee
  event absorb the same team's detection from the same instant (≤ 1 s): one moment, all its branches (TECH_PLAN 1.7
  "a moment can take several branches"). Team-less detections (chaos-state changes) no longer split a possession.
  The 0.04 leverage threshold is unchanged.
- Golden 4242 now: **119 moments, 55 explained**, 28 referee, 5 fast (two big chances became their goals' moments),
  2 recap. `pytest tests/newsroom/test_scout.py -q`: 22 passed (CPU p99 10 ms per event).

---

## 2026-10-22 · Track C: replay feed, end-to-end dry run, fixes

- Owner direction: local demo first, Azure later. While T-039/T-057 are pending:
- **Replay feed** (44f0136, `packages/api/replay_feed.py`): plays the golden cache on the replay clock: analytics as facts
  (chaos meter, studio blackboard), cached oracle converted to the 1.9 shape, moments written to the blackboard when
  the clock reaches them so the worker runs each in time. `python -m api.replay --feed`.
- **End-to-end dry run** 30:00 → 46:00 on the current golden match: `docs/evidence/e2e_dryrun_day2.md`. Moments flow,
  13 cues reach all screens, demo script fires all four actions, no console errors. Found: the newsroom worker exits
  after 0.5 s idle (track B, reported with fix); a cross-thread sqlite error in the api kill path (fixed 13f5c02).
- `tests/apps` + `tests/api`: 70 passed (one wall-clock flake under load average 313, clean on rerun).

---

## 2026-10-22 · T-025 and T-054 done; T-028 training; T-037 outlook (track A)

- T-025 heads v1 on 2,000 matches, test split (200 matches): xG ECE **0.0102**, pass **0.0045**, win probability
  **0.0257**, goal-in-8-s **0.0001** (PR-AUC 0.286), chaos AUC **0.765**. All gates pass (`python -m heads.gates`).
- T-054 MomentEncoder: purity vs the hidden regime **0.695** (gate 0.6; majority 0.39) after weighting the 60 s
  features 4x; clusters named by one gemini-3.8-flash call, **$0.0014** (line in `data/spend/ledger.jsonl`, which
  also holds track B's uncommitted lines, so A did not commit the ledger). `similar_moments` MCP tool registered.
- T-028: epoch 1 val loss printed as Infinity: a passer who regains his own pass was labelled as the recipient
  (2 samples). Fixed in the dataset and the loss; `python -m policy.train --revalidate` re-scores epochs after the
  run (epoch 1: val loss 2.910, kind accuracy 0.809). Training continues; ~38 min per epoch, done about 06:30.
- T-037 outlook (dry run on epoch 1): top-1 kind 0.809 (gate 0.45, pass), **top-3 kind+target 0.502 (gate 0.80,
  fail)**, 4 s FDE 18.8 m vs 28.7 m velocity baseline (pass), teleports 0, shape collapse 0, offsides 0. The
  scripted rule's own probabilities reach only about 0.44 top-3 (near-uniform choice among good passes), so the
  0.80 gate looks unreachable for any model imitating this engine; expect `gate.json` = scripted_v1 (an accepted
  M1 outcome). Threshold unchanged.
- Dugout at 60:00 with a 90 s scripted horizon moves the trailing home side's win probability by at most +0.0008;
  honest but small (style changes act over minutes, win probability at 0-2 down is 2.4%).

---

## 2026-10-22 · T-061 part 1 (track C): demo runner, shot list and recorder — waiting for T-039

- `packages/api/demo_runner.py` (demo script on the replay clock: speed, kill via T-051, veto of the pending recap
  request), `packages/demo/{clocks.py,demo_script.yaml,shot_list.yaml,record_demo.py,__main__.py}`,
  `scripts/record_demo.sh`, `tests/demo/test_demo_script.py`. Shot clocks are references into
  `golden_moments.yaml` (`@sliding_doors-6s`); 14 shots cover the 8 storyboard beats; the recorder uses GPU Chromium.
- `pytest tests/demo -q`: 8 passed, 1 failing by design (`golden_moments.yaml` does not exist; T-039, track A,
  writes it). A real 2.5 s recording works: `smoke.webm` 1.1 MB plus keyframe PNG, ready 1.6 s after load.
  `--dry-run` with the sample moments file prints all 14 shots. Key list for track A in the shared notes folder.
- Not committed as `T-061:` until the clock check passes against the real file.

---

## 2026-10-22 · T-053 /replay3d React-Three-Fiber Sliding Doors scene (track C)

- `apps/overlay/src/replay3d/{Replay3D,Stadium,Players,Ball,GhostPaths,Cameras,SwingBarOverlay}.tsx`, `space.ts`,
  `replay3d.css`, `src/routes.tsx` (lazy route; `?view=replay3d` works on static hosting). Procedural only: no
  model, texture or HDR files are fetched (test checks requests). Ghosts fan out over the 8 s horizon as the clock
  passes the branch point; `?ghost=full` for stills.
- Headless Chromium uses SwiftShader (CPU) for WebGL by default; with `--use-angle=metal --ignore-gpu-blocklist` it
  renders on the M3 Pro. Tests use a `gpu_browser` fixture with those flags; **the T-061 recorder must too.**
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_replay3d.py -q` 2 passed: frame
  renders, seek and both cameras work, swing bar "n = 200, 8 s, seed 4242"; **60.0 fps over 20 s** at 1920×1080
  DPR 1 with 200 ghost paths (limit 30). TECH_PLAN 1.13 trigger (frame by end of day 5) met on day 2.
  `tests/apps` + `tests/api`: 66 passed.
- Polish left for T-083: slight moiré in the crowd texture on the behind-the-player camera.

---

## 2026-10-22 · T-060 Freeze rule and frozen-cache-guard CI job (track B)

- `scripts/frozen_cache_guard.py --base REF`: if the base manifest is frozen, any change at HEAD (entry added,
  removed or re-hashed, match hashes, the frozen flag) fails unless `docs/video/VERSION` went up in the same diff;
  not frozen or absent at the base passes. `docs/video/VERSION` = 0. CI passes the PR base sha or HEAD^.
- Verification `pytest tests/tooling/test_frozen_guard.py -q`: 6 passed (unchanged, changed without bump fails,
  changed with bump passes, unfreezing fails, not frozen / absent pass, this repository passes).

---

## 2026-10-22 · T-051 Supervisor, kill switch and checkpoint resume (track B)

- `newsroom/{supervisor,resume}.py`, `api/control.py` (`POST /demo/kill` + `kill_when_ready`), worker run tracking
  (blackboard `runs` running → done, moments marked running/done), Director/trace rows stamp
  `resumed_from_checkpoint`, `tests/chaos/test_resume.py`, `docs/evidence/kill_resume.log`.
- The kill waits for a running run with a Tactician trace row and no Narrator row, then SIGKILLs the pid the
  supervisor wrote; the supervisor restarts the worker; on start the worker restores each `running` run from its
  newest checkpoint holding that run's messages. Executors hold no in-flight data (messages carry everything), so
  `on_checkpoint_save/restore` save nothing.
- Measured (replay mode, cached outputs): restart **0.05 s** after the kill, resume 0.9 s later, resumed cue
  `c_000011` 3.1 s after that (the cached Narrator latency), same cue id and text as the uninterrupted run.
  Verification `pytest tests/chaos/test_resume.py -q`: 2 passed. The CI chaos-resume job already runs this file.
- The demo-script run at 44:10 (`packages/demo/golden_moments.yaml`) does not exist yet; the evidence log comes
  from the chaos test's moment (00:00 state change) and should be re-recorded on the golden cache after T-039/T-062.
- Note: track C's `tests/api/test_fanout_perf.py` failed here (88 ms > 50 ms) at load average 265; unrelated.

---

## 2026-10-22 · T-041 Panel via GroupChatBuilder (track B) — live budget not met, day-4 cut line applied

- `executors/panel.py`, `prompts/{pundit_press,pundit_possession,pundit_sceptic,chair}@1.md` (+ shared
  `pundit_rules.md`). `GroupChatBuilder` sub-workflow inside `PanelExecutor`: three pundit participant executors
  (gemini-4-argon, tools simulate_counterfactual / get_pitch_control, max_tool_rounds 1) speak in a fixed order,
  `max_rounds=3`; the chair (gemini-3.8-flash) writes {consensus, dissent, headline}. Pundit claims without a cf_/pc_
  id or failing the Fact Checker are dropped. 25 s budget; on timeout the cue is dropped, no retry.
- Deviation: the speaking order is a selection function, not the agent-based manager, because that orchestrator
  makes a structured next-speaker call every round (three more model calls inside 25 s); the chair still decides
  what goes on screen. The orchestrator's output is a closing notice, not the conversation, so pundits record takes.
- `panel_pundit.effort` low (medium maps to thinking high on Argon: 37 s per call, T-032).
- **Live: 25 s budget exceeded.** Each pundit call takes 9–10 s, sequential, after ~4 s of evidence; two live runs
  were both cut at 25.0 s (machine load average ~380). Cut line day 4, first drop: the Panel is near-line
  (golden precompute T-042 and recaps), off on the live path (`panel_enabled` false by default). The live test
  is kept as written and fails; offline `pytest tests/newsroom/test_panel.py -q`: 5 passed.
- `LiveClient` also records a worst-case ledger row when a call is cancelled from outside (the panel budget).
  T-041 dev spend **$0.08** (limit $0.50), $0.04 of it worst-case rows for cancelled calls.

---

## 2026-10-22 · T-045 Overlay viewer modes, heatmap, threat front and referee lines (track C)

- `apps/overlay/src/modes/{analyst,casual,playerCamConfig,config}.ts` (mirror `budgets.yaml`, checked by a test),
  `pitch/layers/{heatmap,threatFront,refereeLines}.ts`, `api.ts` (doc fetch: api or fixture files). Fixture now
  has 30 oracle messages, referee cue `c_000913` (onside by 0.4 m) and `apps/overlay/public/fixtures/docs/
  pc_000412.json` (outside `tests/fixtures`, which needs a schema per file).
- Oracle zone format chosen here (T-046 should emit it): `zone: {x, y, r}` in metres.
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_viewer_modes.py -q` 5 passed. Modes
  differ in exactly the 1.9 layers (analyst vs casual: heatmap, threat front, ticker; analyst vs player_cam:
  heatmap, threat front, player trail, player tag); referee lines yellow at x = 88.2 and 88.6 m, margin label
  0.4 m, half drawn at 0.3 s; **frame with heatmap + threat front + 200 ghosts p95 0.40 ms**, grid image built in
  0.90 ms (limit 8 ms). `tests/apps` + `tests/api`: 64 passed twice.
- Also: T-044's player_stats dump moved to `tests/apps/data/` (2390155) — under `tests/fixtures` it broke
  `make schemas`.

---

## 2026-10-22 · T-026, T-027, T-049 done; T-025, T-028 running (track A)

- T-026 auto-events (`physics/auto_events.py`): six detectors, facts not events; golden counts pressing_trap 13,
  line_break 3, switch_of_play 19 (35 m, not the brief's example 30 m: 51 at 30 m), overload 4, counter_attack 3,
  big_chance 4; p95 0.6 ms on a 15 s window.
- T-027: user approved the GRF download; 150 games (1.3 GB, git-ignored) check out (10.21 Hz, mapping holds).
  Dataset 2.76M / 345k / 345k samples (2,000 Kickoff + 150 GRF games), split by game. F = 16: TECH_PLAN's list
  has 17 entries, stamina dropped. The repo downloader hung once (no timeout); re-run with a 60 s socket timeout.
- T-049: Fourth Official geometry re-derives all 5 golden offsides exactly; 28 cached verified referee_line cues
  (`scripts/precompute.py --stages fourth_official`); executor registered in `newsroom/graph.py` (only A's two lines
  committed; track B's Panel edits left in the working copy, see the shared notes).
- T-028 launched: `policy_v1`, 8 epochs on MPS, about 1,300 samples/s while the corpus and heads jobs share the CPU
  (spec measured 2,474), so about 36 min per epoch. Log: `packages/policy/artifacts/train_log.jsonl`.
- Found: importing torch before LightGBM crashes LightGBM predictions on macOS (two libomp copies). `heads`,
  `policy` and `tests/conftest.py` now import LightGBM first.
- Dugout at 8 s moves win probability by 0.0000 for every style option; T-047 will use a longer scripted horizon
  (the schema allows up to 90 s for scripted_v1).

---

## 2026-10-22 · T-038 CacheManifest and CacheClient (track B)

- `packages/cache/{manifest,client,errors}.py`. Keys as TECH_PLAN 1.8 (the two schema-example keys reproduce
  exactly); saves validate against the schema; `verify_hashes()` catches one flipped byte in an entry or in
  events.jsonl. `CacheClient` serves model calls and tool calls after `simulated_latency_ms / WHYLINE_REPLAY_SPEED`;
  a model miss raises `CacheMiss` (template + red `cache_miss` trace row from the executors), a counterfactual miss
  returns `{error, code: cache_miss}` and the Rollout trace row turns red.
- Injection: worker replay mode → CacheClient (LLM and tools); MCP server with `WHYLINE_MODE=replay` → cached
  `simulate_counterfactual` (`cf_000077` from the schema example in the test), misses refused.
- Executors now pass `producer` (narrator / fast_line / proposer / tactician) so a moment's fast line and its
  explained line have separate keys.
- Verification `pytest tests/cache -q`: 15 passed.

---

## 2026-10-22 · T-032 Tactician with MCP tools and first live latency probe (track B)

- `executors/tactician.py` (gemini-4-argon, tools query_events / get_pitch_control / simulate_counterfactual /
  player_stats through the newsroom tool client, structured output → explanation.schema.json, 12 s timeout, one
  retry, then `tactician_degraded`), `prompts/tactician@3.md` (stable league block first for implicit prefix
  caching), `templates.tactician_template`, `scripts/latency_probe.py`, `docs/evidence/latency_probe_day3.md`.
- Live probe (MCP server + worker as processes, golden 23:39, Okafor shot vs pass to Novacek, goal chance
  3.4% → 20.7%): **run 1 18.6 s** moment→cue, verified Sliding Doors cue with model text, $0.013 (Proposer 3.7 s,
  Rollout 2.3 s, Tactician 9.3 s, Narrator 3.1 s). > 15 s, so `max_tool_rounds` 1 (TECH_PLAN 1.13): **run 2
  37.5 s**, Tactician timed out twice and Narrator once → template cue (verified). 15 s target not met; carried
  to T-080/T-081 with the levers listed in the evidence file.
- Config from measurements: `tactician_live.effort` low (thinking high: 37 s, all 3,000 tokens on thinking, JSON
  cut off), `max_tool_rounds` 1; worker warms both models.
- Fixes found by the probe: Agent Framework 1.22.0 `MCPStreamableHTTPTool` cannot initialise against mcp 2.3.0
  (`protocolVersion` → `protocol_version`), so `McpTools` uses `mcp.Client` (regression test added). The 5% policy
  guard dropped every rule alternative because the rule ignored policy probabilities: MCP `get_state` now returns
  the engine's option probabilities, the rule picks plausible options (17 of 27 golden decision moments get a
  plausible alternative), and the Proposer sees them.
- **Spend over budget:** T-032 ledger $0.59 against $0.50: $0.064 reported usage plus $0.529 worst-case estimates
  for ten timed-out calls. Live calls stopped there; the `-m live` Tactician test is written but not run.
- Verification `pytest tests/newsroom/test_tactician.py -q`: 9 passed (+1 live not run). Scout timing test now
  measures process CPU time (load average 283 from another track's job made wall time meaningless): CPU p99
  14 ms, max 26 ms per event.

---

## 2026-10-22 · T-044 Player-Cam card and player_cam overlay mode (track C)

- `packages/api/players.py`: `GET /match/{id}/players/{player_id}/stats` = MCP `player_stats` (same code) +
  `distance_m` from tracking + Decision Index from a blackboard fact until T-048 (README lists the addition).
  `apps/fan/src/components/PlayerCamCard.tsx`; `apps/overlay/src/modes/playerCam.ts` (8 s trail layer, persistent
  Player-Cam tag). api filter applies `only_player_involved`.
- Verification: `npm --prefix apps/fan run build && npm --prefix apps/overlay run build && pytest
  tests/apps/test_player_cam.py -q` 4 passed: endpoint equals the MCP dump (`tests/fixtures/player_stats/
  m_4242.json`) for p_017, p_031, p_045; the card shows touches 95, sprints 38, top speed 28.0, DI 71 (fixture fact)
  for Okafor; a player_cam viewer gets only cues listing the player; overlay trail ≥ 20 points and tag on Okafor.
  `tests/apps` + `tests/api`: 59 passed.
- Open: stats cover the whole recorded match (MCP semantics), not "so far" at the replay clock. Engine
  observation for track A in the shared notes: distances high (Okafor 10.5 km in 60 min), every top speed 28.0.

---

## 2026-10-22 · T-043 Fan app: modes, mini-pitch, cue feed, moment cards (track C)

- `apps/fan/src/{App,main,profile,league}.tsx|ts`, `stream/{StreamProvider.tsx,reducer.ts,types.ts}`,
  `components/{ProfilePicker,MiniPitch,CueFeed,MomentCards}.tsx`, `styles/{tokens,fan}.css`,
  `public/league.json`. Profile validated against the viewer_profile schema rules, stored with try/catch (app works
  when storage throws). api `messages.cue_matches` now also enforces `budgets.yaml` mode kinds server side.
- Verification: `npm --prefix apps/fan run build && pytest tests/apps/test_fan.py -q` 4 passed. With one cue of
  every kind on air, **casual receives exactly its 5 kinds, analyst its 12** (switching back and forth); stored
  profile passes `jsonschema` against `viewer_profile.schema.json` and survives a reload; **veto → fan card gone
  in 3–5 ms** (closes the fan half of T-035). Fixed an order-dependent wait in the score-bug test (shared api
  left at 70:00 by another test). `tests/apps` + `tests/api`: 55 passed, twice.

---

## 2026-10-22 · T-035 Studio producer panel and demo controls (track C)

- `apps/studio/src/components/{ProducerPanel,DemoControls}.tsx`: Approve / Veto / Hold on `request_info`, Veto on
  any on-air cue, Kill newsroom, Pause/Play, x1/x2/x5/x10, seek mm:ss. Held requests stay pending (the api's studio
  snapshot now drops only approved/vetoed requests).
- Verification: `npm --prefix apps/studio run build && pytest tests/apps/test_studio_controls.py -q` 3 passed.
  **Veto click → overlay lower-third leaving: 7 ms** (limit 200 ms, two pages, both stamped with Date.now()).
  Decisions land in blackboard `decisions` (approved / vetoed / held); kill posts `{target: "newsroom"}`; x5 and
  seek 52:30 reach the replay clock. The fan half of "overlay and fan" is checked when the fan app exists (T-043).
  `tests/apps` + `tests/api`: 51 passed.

---

## 2026-10-22 · T-034 Studio console core (track C)

- `apps/studio/src/{App,api,league,main}.tsx|ts`, `stream/{StreamProvider.tsx,reducer.ts,types.ts}`,
  `components/{Header,MomentQueue,AgentTrace,CueList,WhyDrawer,Blackboard}.tsx`, `styles/{tokens,studio}.css`,
  `public/league.json` (export script output). The studio keeps a cue/trace/moment log across seeks and reloads
  the full cue list over REST on each hello.
- api: the doc endpoint inlines the pitch-control grid from the MCP server's `grid_path` .npz; the studio's
  reset snapshot also carries the last 60 trace rows and undecided `requests`.
- Verification: `npm --prefix apps/studio run build && pytest tests/apps/test_studio.py -q` 4 passed: trace rows
  show all six fields, cache_miss and interrupted rows red; the fixture cue's evidence (e_8812, cf_000077) resolves
  2/2 through `/match/{id}/doc/{id}`; an unknown id is flagged missing; thumbnail and "n = 200, 8 s, seed 4242".
  `tests/apps` + `tests/api`: 48 passed.
- Seen, not mine: ruff flags `tests/kickoff/test_no_truth_leak.py:43` (B905) and `tests/policy/test_data.py` (I001).

---

## 2026-10-22 · T-033 API cue fan-out, ingest and control endpoints (track C)

- `packages/api/{cues,control,docs,ingest,messages}.py`, `ws.py` reworked: blackboard watcher forwards every 1.9
  message type; timed docs (cues, facts, moments, oracle) released on the stream clock; target filtering server side;
  seek snapshot (cues on screen, latest facts); counterfactual sent before its first cue. Doc endpoint (addition to
  the 1.4 list, in `packages/api/README.md`), `/producer/decision` (+ veto of a shown cue → `cue_remove`),
  `/demo/kill` 202 stub, `/spend`, `/ingest/*` (live mode), `python -m kickoff play --target api`
  (`packages/kickoff/stream.py`; small CLI edit in `kickoff/__main__.py`).
- Contract for track B (collections `requests`, `decisions`) in the shared notes folder.
- Verification: `pytest tests/api/test_cues.py tests/api/test_fanout_perf.py -q` 9 passed. **Fan-out to 20 clients
  (blackboard write → 20th client): max 23.7–29.6 ms, p95 23–27 ms** over three runs (limit 50 ms). Veto →
  `cue_remove` on two screens in 4–8 ms. CLI streamed m_7 into a running api (31 frames, 7 events).
  `tests/api` + `tests/apps` + `tests/kickoff`: 58 passed.

---

## 2026-10-22 · T-031 Proposer and RolloutExecutor (track B)

- `newsroom/decision.py` (decision point: last pass/carry/shot/clearance of the moment, branch at event − 100 ms,
  team-mates with xT gain; `proposer_rule`; `valid_alternatives`), `executors/{proposer,rollout}.py`,
  `prompts/proposer@1.md`, `newsroom/tools.py` (`McpTools` over `MCPStreamableHTTPTool`, `LocalTools` in-process;
  the worker uses MCP when `WHYLINE_MCP_URL` is set).
- Proposer: gemini-3.8-flash (`proposer` role), 6 s timeout, one retry, then the rule (top-3 team-mates by xT
  gain); model output is validated (actor forced, targets on the pitch, never the actual action). Rollout: n 200
  under 2 s (5 s with `WHYLINE_CLOUD`), then n 50; errors (invalid alternatives) skipped; keeps the largest
  |Δ win prob| with policy_prob ≥ 0.05.
- Gemini's schema converter rejects `["string","null"]` types, so `target` is a string ("" for none).
- Live proposer on a golden decision: 3 valid alternatives, $0.0013; the cold first call timed out at 6 s and
  the retry succeeded (9.9 s total). `LiveClient` now records a worst-case ledger row (`<role>:timeout`, input
  ≈ chars/4, output = max_tokens) for every timed-out call; two earlier unrecorded timeouts (T-020, T-031) were
  added the same way ($0.0045). Dev spend for T-031: $0.0044 (limit $0.20).
- Verification `pytest tests/newsroom/test_proposer.py -q`: 9 passed (+1 live). In-graph run on the golden
  match: proposer + 2 rollouts 2.8 s.

---

## 2026-10-22 · T-030 MCP server: core tools (track B)

- `packages/mcp_server/{__main__,server,tools_core,errors}.py`. mcp 2.3.0 has no FastMCP: it is `MCPServer` now
  (same decorator API); Streamable HTTP on :8080 `/mcp`. Seven tools with the 1.7 signatures; every failure returns
  `{error, code}`.
- `simulate_counterfactual` wraps T-016 `sliding_doors` (n 200, horizon 8 by default), stores `cf_` and its `pc_`
  snapshot; golden minute 2: **2.9 s** cold (the match re-simulates from kick-off; later calls move forward).
- Verification `pytest tests/mcp_server/test_tools.py -q`: 20 passed (each tool on the golden match, 9 error cases,
  one Streamable HTTP round trip).
- Open: `player_stats` counts the whole match file, so in replay it can see past the replay clock (T-033/T-039).

---

## 2026-10-22 · T-029 Scout executor and classification predicates (track B)

- `newsroom/scout_rules.py` (predicates exactly as TECH_PLAN 1.7; batch `detect_match` and live `ScoutStream`;
  `Merger`), `executors/scout.py` (one Routed per branch, none → drop), wired into the graph.
- Leverage = max |ΔP| of GoalIn8sHead (home or away scores in 8 s) between the frames before and after the event
  (t ± 100 ms). Sources: goals, fouls/cards/offsides, period ends, auto-events (T-026), on-ball decisions (pass,
  carry, shot, clearance: the actions a counterfactual can replace), chaos-state changes at 1 Hz, sprints ≥ 34 km/h.
  Consecutive same-team detections within 5 s merge into one moment.
- Golden 4242: **120 moments, 58 explained** (27 decisions, 16 state changes, 4 big chances, 3 goals, 3 offsides,
  5 auto-event moments), 28 referee, 7 fast, 2 recap. Above the $50 plan's 40-Tactician-call assumption; the
  Director's budgets drop some, T-042 will show the real count. First reading (+1 s after the event, every on-ball
  event type, merging across possessions) gave 86; adjacent frames plus the two rules above are the plan's wording.
- Per event (live path, 1,499 golden events): p50 **3.7 ms**, p95 12.2 ms, p99 18.5 ms; max 28.6–72.8 ms across
  runs while the machine load average was ~40 (the slowest event profiles at 12 ms alone). The test asserts
  p99 < 50 ms; the limit is "< 50 ms per event", so the max is recorded here, not hidden.
- Verification `pytest tests/newsroom/test_scout.py -q`: 20 passed. Routing tests in test_graph now use the stub
  Scout explicitly.

---

## 2026-10-22 · T-015 Outcome heads v0, T-016 rollout primitive (track A)

- T-015 `packages/heads`: five heads on the first 200 training matches, split by match seed (rng 4242), test split:
  xG ECE 0.040 / AUC 0.81, pass ECE 0.009, goal-in-8-s ECE 0.0004 / PR-AUC 0.24, win probability ECE 0.106
  (only 20 test matches, one label each), chaos AUC 0.758. Reports only; T-025 gates on 2,000. Artefacts committed
  (`*.txt`, `*.metrics.json`, `*.calibration.png`); missing artefacts raise at start-up.
- T-016: engine tick vectorised (B=200: 13 → 1.4 ms per tick; golden hashes unchanged), `Engine.branch`,
  `Override`, `rollout` → `Futures`, `sliding_doors` → schema-valid `CounterfactualResult`, `placebo`, `MatchRef`.
  Idle Mac: B=200 × 90 s **1.265 s CPU** (≤ 1.3), × 60 s **0.845 s** (≤ 1.2). The perf test fails while the corpus
  runs in the background (CPU contention); run it on an idle machine.
- Placebo: forced actual action vs baseline worlds whose own first choice was that action, two-sample 95% interval
  floored at ±0.005 (8-s futures barely move win probability, so raw intervals are ~1e-4). 7/7 golden moments pass;
  without the floor 18/21 passed in a wider sample.
- For track B (MCP, day 3): `from rollout import MatchRef, rollout, sliding_doors, option_probs` (see
  `packages/rollout/README.md`). Run CLIs with `PYTHONPATH=packages`.

---

## 2026-10-21 · T-013 Physics core, and hidden match regimes for T-014 (track A)

- T-013 `packages/physics`: Spearman-style pitch control [34,53] (shares sum to 1, mirror test), indices, chaos
  index, speeds, `StateMachine`, `TrackingWindow`. Per frame (pitch control + 60 s indices + chaos + speeds + state):
  p50 0.8 ms, p95 3.4 ms CPU (budget 15 ms). `pytest tests/physics -q` passes.
- The engine's tactical phases barely moved anything observable, so state detection (T-055, F1 ≥ 0.75) could not
  pass. Added a hidden match regime to `truth.json` (t2, phases with side `M`: settled / transitional / chaotic,
  10–18 min) that drives tempo, press and duel intensity. Chaos now comes from the open-play turnover rate
  (EWMA, tau 60 s). **State-detection macro F1 0.771 on seeds 1–50** (Settled 0.84, Transitional 0.68, Chaotic 0.79).
- Realism after the change, seeds 1–50 per team: completion **0.801**, shots **13.2**, goals **1.52**, offsides 1.17.
- Golden 4242 regenerated again: **Verdant 1–2 Ironvale**, goals 11:50, 16:55, 67:42; 5 offsides, 2 cards; regimes
  chaotic 0–17 and 57–75 min. Corpus restarted from scratch (1001–3000, 51–350) in the background.

---

## 2026-10-21 · T-014 Training corpus generator and realism ranges (track A)

- Engine tuned (`packages/kickoff`): seeds 1–50 per team per match now completion **0.834**, shots **14.6**, goals
  **1.59**, offsides **1.01**, fouls 5.1, cards 0.54 (was 0.823 / 21.0 / 2.17 / 0.06; Ironvale 37.9 → 15.4 shots).
  Knobs are named constants at the top of `engine.py`, `rules.py`, `physics_prior.py`.
- Golden 4242 regenerated: **Verdant 2–2 Ironvale**, goals 00:53, 10:28, 23:10, 68:09; 4 offsides, 2 cards; new
  `SHA256SUMS`. Three tests that hard-coded the old 0–4 score (`tests/api/test_replay.py`,
  `tests/apps/test_overlay_components.py`, `tests/apps/test_overlay_ws.py`) now read goals from `events.jsonl`.
- `scripts/generate_corpus.py` (resumable, `progress.json`, behavioural engine hash), `League.fixture(seed)`,
  `tests/kickoff/test_realism.py`. Seeds 1–50 done; 1001–3000 and 51–350 running in the background (~30
  matches/min, about 80 min). Verification: `pytest tests/kickoff/test_realism.py -q && python scripts/generate_corpus.py --status` pass.

---

## 2026-10-21 · T-066 Licence scan job and asset list (track B, built early: only needs T-005)

- `scripts/licence_scan.py`, `config/licence_allowlist.txt`, `LICENSES.md`, `tests/tooling/test_licence_scan.py`.
  Python via `pip-licenses`, npm production deps from the three lockfiles (works without node_modules), assets from
  `data/league/assets.json` once T-077 creates it. GPL/AGPL/LGPL/non-commercial always fail.
- `python scripts/licence_scan.py`: **202 entries (131 pip, 71 npm), 0 offenders**, 3 named exceptions for the
  owner to confirm: `certifi` and `tqdm` (MPL-2.0, unmodified dependencies) and `webgl-constants` (no licence field,
  MIT LICENSE file). The `licence-scan` CI job already runs the script once it exists; `ci.yml` unchanged.
- Open: the repo has no top-level `LICENSE` file (pyproject says MIT); needed before the repo goes public.

---

## 2026-10-21 · T-021 Director with budgets (track B)

- `executors/director.py`, `cuebus.py`. Hard rules: a cue waits out a shot sequence (to the next possession change,
  goal, restart, foul or period end, max 6 s) and the 3 s after a goal; same kind within 90 s, unshown after 45 s
  (`deps.state["match_clock_ms"]` when the clock is known), Sliding Doors below leverage 0.04 and Oracle below
  p_shot 0.30 are dropped. Per viewer mode: kinds, min gap between lower-thirds, max per 10 min, casual Sliding
  Doors per half; history is read from blackboard `cues`, so it survives restarts. Studio gets every cue that
  reaches any viewer mode; a cue no viewer mode accepts is suppressed with a trace row.
- `cue_id` = `c_` + moment number × 10 + branch index (mo_00077 explained → `c_000771`): independent of process
  state and processing order. SpendCapReached → `degraded` mode, one `modes` document; model error, timeout, cache
  miss or third rejection → template from verified claims and a red trace row (status `error`/`cache_miss`/…).
- Verification `pytest tests/newsroom/test_director.py -q`: 17 passed (every produced cue validates against
  `cue.schema.json`). Graph-routing tests now use the stub Director/CueBus so they test routing only.

---

## 2026-10-21 · T-024 Ghost trail and swing bar (track C)

- `apps/overlay/src/pitch/layers/ghostTrail.ts`: 200 futures, Catmull-Rom (81 points per 8 s path), Path2D cache,
  branch colours, 0.8 s fade, orange dashed chosen trail. `components/SwingBar.tsx`: from → to animation,
  "n = 200, 8 s, seed 4242" always printed; no counterfactual document → no bar.
- Interim contract: `counterfactual` stream message; `futures_sample` first half baseline, second half alternative
  (cue contract gap 7; note for track A's T-016 in the shared notes folder). Fixture has 200 deterministic futures.
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_ghost_trail.py -q` 5 passed.
  **200 paths: p95 0.20 ms** CPU-side draw (limit 8 ms), rAF interval p95 16.7 ms (no dropped frames).
  `tests/apps` + `tests/api`: 35 passed.

---

## 2026-10-21 · T-020 Narrator and fast-line executors (track B)

- `executors/{narrator,fast_line}.py`, `templates.py`, `prompts/narrator@2.md`, empty `prompts/fewshot/narrator.jsonl`.
  The Narrator re-verifies the Tactician's claims and sends only verified ones to the model; output is clipped to
  60/280 chars; rewrites get the Fact Checker diff and the previous draft. Fast line builds player/xG/team claims
  from the moment's evidence events.
- Gemini adaptation of "Anthropic error → Gemini fallback": `narrator_fast` is already gemini-3.8-flash, so a
  provider error retries once (or uses a role's `provider_fallback` if one is configured), then the template;
  timeout, cache miss and SpendCapReached go straight to the template (cap also sets degraded).
- Latency (measured, Vertex AI global): Flash with thinking `low` 2.5–5.1 s per call, thinking off 1.3–1.8 s, so
  `config/models.yaml` `narrator_fast.effort` is now `none` (thinking_budget 0). A cold first call took 4.8–5.4 s,
  so `LiveClient.warm()` runs at worker start. Live narrator call with 483 input tokens: **3.4 s**, $0.000726; the
  fast-cue SLO of 3 s will need the template or a shorter prompt live (T-032 probe).
- Verification: `pytest tests/newsroom/test_narrator.py -q` 11 passed; live test passed (output verified-claim
  numbers only). Dev spend for T-020 **$0.0007** (limit $0.10). A call cut off by the timeout is not in the ledger
  (no usage returned); at most one such call happened here.

---

## 2026-10-21 · T-023 Lower-thirds, score bug, chaos meter, player tags, ticker (track C)

- `apps/overlay/src/components/{ScoreBug,ChaosMeter,LowerThird,PlayerTags,Ticker}.tsx`, `motion.ts`
  (presence + text fitting), `styles/broadcast.css`, shared `league.ts`. Chaos meter reads facts `chaos_index` and
  `chaos_state` (note for track A in the shared notes folder).
- **Kit contrast fix:** kits under 3:1 WCAG contrast with the grass get a light halo (Verdant #0E5C36 is 1.6:1,
  Ironvale's navy away kit too); score-bug kit chips get a light edge.
- Fixture: 62 facts (chaos_index every 1 s, chaos_state Transitional → Chaotic at 31:26). Fixed a T-010 fold bug:
  untimed messages took the previous frame's time, so `cue_remove` fired 100 ms early.
- Verification: `npm --prefix apps/overlay run build && pytest tests/apps/test_overlay_components.py -q`
  7 passed (all of `tests/apps` + `tests/api`: 30 passed). Schema-max text (60/280 wide chars) fits at full size
  (headline 31 px, body 20 px), nothing overflows; cue appears at 31:18.2 and is gone at 31:26.2; score bug goes
  0–0 → 0–1 on the 39:05 goal event over the WebSocket. Pitch2D p95 still 0.20–0.30 ms.

---

## 2026-10-21 · T-018 newsroom graph and T-019 Fact Checker (track B)

- T-018: `packages/newsroom/{messages,graph,llm,worker,config}.py`, `executors/{base,ingest,stubs,drop}.py`. The full
  1.7 graph with the verbatim builder calls; stubs keep the real executor ids so checkpoints survive swaps. Messages
  are pydantic and registered for checkpoint restore. `LiveClient` = Gemini on Vertex AI via
  `agent_framework.gemini.GeminiChatClient`, SpendGuard on every call, thinking tokens as output.
  `pytest tests/newsroom/test_graph.py -q`: 7 passed (goal → cue via fast branch; rejecting stub stops at attempt 3;
  a checkpoint per superstep; resume from a mid-run checkpoint).
- T-019: `packages/newsroom/factcheck.py` (eight rules, verbatim tolerances; xT ±0.005 and seconds ±0.5 are my
  choice, the plan names none), `executors/factcheck.py`, `scripts/scan_banned.py`. Verification: 56 passed;
  `scan_banned.py data/league` 0 hits. Example check **1.1 ms** (limit 50 ms).
- Decisions: the counterfactual schema has no field for the alternative's xG ("0.31 xG" cites `cf_000077`), so
  derived numbers are facts carrying `counterfactual_id` and citing the cf covers them (no schema change). Rule 7
  matches speculation and accusation phrases (e.g. "looks injured", "biased referee"), not topic nouns, so
  `lore.md`'s "no injuries, no referee-bias talk" line passes. Rule 3 accepts a player from a cited event, a cited
  counterfactual's actor/target, or one hop of `related_event_ids` (the cue example's "Reyes" cites the shot).
- Note: the cue schema example's body ("In 200 replays … within 8 seconds") fails rule 6 as written; the Narrator
  must bind those numbers to `count`/`seconds` claims on the counterfactual.

---

## 2026-10-21 · T-022 API replay server and tracking stream (track C)

- `packages/api/{main,replay,ws,models,__main__}.py`: `/health`, `/match/{id}/events?from&to` (ms or mm:ss),
  `/replay/control` (play, pause, seek by `value` or `t_ms`, speed x1–x10), `WS /ws`. One ticker, per-client
  queues (ready for T-033 cue fan-out). `hello` also carries `t_ms`, `score`, `player_ids` (subs applied) and is
  re-sent after every seek; new `lineup` message on substitutions. CORS open (screens run on other ports).
- Overlay: `?api=host:port`, hello resets the reducer, lineup updates row mapping.
- Verification: `pytest tests/api/test_replay.py -q` 8 passed; **13–14 frames in 1.2 s at x1**, x10 moves
  10.2 s of match time per second. `tests/apps/test_overlay_ws.py`: overlay plays 4242 over WS, 15 frames/1.5 s,
  seek to 39:10 shows 0-1.

---

## 2026-10-21 · T-017 SqliteBlackboard (track B)

- `packages/blackboard/{protocol,sqlite,ids}.py`: one table per collection, JSON column, WAL, cross-process
  `watch` by sequence polling; ids per TECH_PLAN 1.3, monotonic per match. Verification `pytest tests/blackboard -q`:
  15 passed. `put` p50 **0.06 ms**, p95 0.10 ms (limit 2 ms).

---

## 2026-10-21 · Day 1 backlog: T-001 to T-012

**Done** (one commit per ticket, `git log --oneline`)
- T-001 repo bootstrap: git repo, Python 3.12.12 `.venv` with every pin exact (`requirements.lock`, 130 packages),
  13 package skeletons, three Vite + React 19.3.1 apps, `scripts/check_pins.py`, Playwright Chromium. Changes to the
  plan: `azure-ai-projects` 2.9.0 → **2.7.0** (agent-framework-foundry 1.15.0 needs <2.8); React 19 (fiber 9.8.2 peer
  range); apps resolve dependencies with **Node 22.23.3** (`.nvmrc`; npm 10.8.2 on Node 20 crashes resolving Vite 8
  peers, `npm ci` works on both); Haiku 5.5 cache read **$0.01**/M and Sonnet 5.5 **$0.10**/M (pricing page).
  ADRs were already in `docs/adr/` with descriptive file names; kept.
- T-002 league: 8 clubs, 200 players, styles, lore, 396-phrase banned list. **Deviation:** Okafor p_017, Silva
  p_022 and Reyes p_031 all play for Verdant (the brief put Reyes on the other side, but the schema examples have
  Okafor's alternative pass going to Reyes).
- T-012 GRF tiny_set (12 games, 102 MB, git-ignored): 23 rows per step, mapping holds (99.997% inside), frame rate
  derived from ball gravity **10.2 Hz**; a 3,001-step game is about 300 s of play, not 90 min. `docs/DATA.md` has
  the attribution and a drafted email to the authors.
- T-003 `docs/cue_contract.md` (10 layers, 14 kinds mapped; 12 renderer gaps listed, no schema edits), byte-identical
  60 s sample stream, `tokens.css`.
- T-004 pre-commit secret guard, installed in `.git/hooks`.
- T-005 CI with the nine jobs (five skip until their tickets), `validate_schemas.py`, `check_spend.py`, `make ci`.
- T-006 Kickoff engine: 18 event types, 10 Hz tracking, hidden truth, CLI. 90-minute match in **10.4 s** (limit 60 s).
- T-007 golden match `data/matches/4242` + `SHA256SUMS`; two runs byte-identical. tracking.npz is 25 MB.
- T-008 SpendGuard + ledger; Agent Framework import test (RequestInfoExecutor absent; Case/Default in
  `agent_framework._workflows._edge`). Gemini smoke via Vertex AI on project ffc-19484 (gcloud ADC) ok.
- T-009 `azure.yaml` (six services), `infra/main.bicep`, `infra/README.md`.
- T-010 overlay shell: fixture playback, reducer, record mode (`window.__whyline.ready/seek/pause/debug`).
- T-011 Pitch2D: cached pitch, players, ball shadow, layer registry; p95 draw **0.30 ms** (CPU-side canvas time).

**Verification** (each ticket's own command, re-run at the end)
- Pass: T-001, T-002, T-003, T-004, T-005 (`make ci`: 34 tests), T-006, T-007, T-010, T-011, T-012.
- T-008: tests pass; `smoke_models.py` exits 2: Gemini ok ($0.000009 × 2 in the ledger), **Claude blocked, no
  ANTHROPIC_API_KEY in `.env`**.
- T-009: blocked, `az`/`azd` not installed (owner sets up Azure).
- CI has never run on GitHub: no remote yet.

**Open**
- Human steps: paste `ANTHROPIC_API_KEY` into `.env` and re-run `python scripts/smoke_models.py`; create the public
  GitHub repo and add it as `origin`; Azure account + `az`/`azd` 1.36.0 + logins, then fill in `infra/README.md`;
  send the GRF licence email in `docs/DATA.md`.
- Before pushing public: the committed planning docs name the Premier League contact and real clubs
  (`docs/permissions/README.md`, `data/footage/SOURCES.md`, `data/footage/*/shots.json`, proposal files). Decide
  what stays. `clip.info.json` files are git-ignored (they carry signed stream URLs).
- Engine realism is a first read, not tuned (T-014): completion 76–81% (in range), Verdant ≈13 shots and 1.2
  goals, high-press Ironvale too strong (≈37 shots, 2.7 goals), offsides ≈0.2 per match (forced-offside test
  covers the geometry). Golden 4242 is currently 0–4 and must be regenerated after T-014 tuning.
- Verdant's dark-green kit is hard to see on the green pitch (T-023/T-077).
- Planned 23.5 person-hours for day 1; this session took about 1 h 45 min wall clock.

---

## 2026-10-21 · Footage: downloads and first-pass shot analysis (T-102 partial, T-103 exploration)

**Done**
- Shortlisted seven clips uploaded by the Premier League channel itself (verified via oEmbed and `clip.info.json`,
  channel ID `UCG5qGWdu8nIRZqJ_GgDwQ-w`). Table in `data/footage/SOURCES.md`. Club-channel uploads in the
  "Club highlights 2026/27" playlist are outside the permission and excluded.
- Downloaded the four primary clips with yt-dlp 2026.08.19 (user's explicit go-ahead plus the Premier League written
  permission): `liverpool-mancity-2526`, `manutd-mancity-2526`, `arsenal-chelsea-2526`, `manutd-spurs-2425`, each
  `data/footage/<slug>/clip.mp4` at 1080p H.264 with `clip.info.json`. 3.5 GB total. Media is git-ignored by
  `data/footage/.gitignore`.
- Wrote a heuristic shot segmenter (`scripts/shots_firstpass.py`, contact sheets via
  `scripts/shots_contact_sheet.py`), tuned it three times against contact sheets. Results in
  `data/footage/SHOTS_REVIEW.md`; per-clip `shots.json` and `frames/` (git-ignored).
- Liverpool v Man City confirmed as primary tracking clip: 34 usable wide shots, 46% wide time, five unbroken wide
  shots of 67–88 s (13:22, 07:15, 10:35, 09:18, 26:34).

**Verification**
- `ffprobe` on all four clips: h264 1920x1080, durations 37:13 / 25:32 / 25:32 / 25:33.
- Contact sheets reviewed by eye; remaining false positives listed in `SHOTS_REVIEW.md`.

**Open**
- Original permission email as `.eml` with headers not yet in `docs/permissions/` (user action).
- Decision on real club and player names in overlays (user).
- Replays and slow motion are not detected; the first pass will mark a main-camera replay as wide.
- T-001 repo bootstrap not done: no git repo, no `packages/`, no `.venv`. The analysis ran in a throwaway venv.
- Three backup clips not downloaded.
