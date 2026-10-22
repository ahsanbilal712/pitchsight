# Shot segmentation: first pass (T-103 exploration, 21 Oct 2026)

Script: `scripts/shots_firstpass.py <clip.mp4> <out_dir>` (needs numpy and opencv-python-headless). It samples at
5 fps, finds cuts by HSV-histogram correlation, and calls a sample "wide" when pitch green covers at least 42% of the
frame, there are at least 4 player-sized blobs, and no tall blob (a close-up person) is larger than 2.5% of the frame.
A shot is usable when at least 70% of its samples are wide and it lasts 4 s or more.
Output: `<slug>/shots.json` (all shots) and `<slug>/frames/` (one thumbnail per usable shot plus `contact_sheet.jpg`;
git-ignored).

## Results

| clip | length | shots | usable wide shots | usable wide time | longest wide windows (mm:ss) |
|---|---|---|---|---|---|
| liverpool-mancity-2526 | 37:13 | 214 | 34 | 17:07 (46%) | 13:22–14:51 (88 s), 07:15–08:41 (87 s), 10:35–11:59 (85 s), 09:18–10:35 (77 s), 26:34–27:41 (67 s) |
| manutd-mancity-2526 | 25:32 | 183 | 27 | 8:47 (34%) | 14:54–16:12 (78 s), 03:02–04:02 (60 s), 21:33–22:19 (45 s) |
| arsenal-chelsea-2526 | 25:32 | 213 | 36 | 11:09 (44%) | 04:50–05:42 (52 s), 15:31–16:16 (45 s), 21:04–21:47 (43 s) |
| manutd-spurs-2425 | 25:33 | 193 | 32 | 10:56 (43%) | 11:02–11:54 (52 s), 05:35–06:22 (47 s), 02:54–03:37 (43 s), 16:00–16:43 (43 s) |

The Liverpool v Man City clip is the strongest tracking input: five unbroken wide shots over a minute long, all from
the main broadcast camera. That confirms it as the primary clip.

## Known false positives (from the contact sheets; correct by hand before T-104)

- liverpool-mancity-2526: 06:49 (fan's-eye view through a crowd), 18:45 (keeper close-up), 34:37 (full-time
  celebration), 36:59 (empty stadium). Medium goalmouth shots at 02:14 and 04:12 are usable for set pieces only.
- arsenal-chelsea-2526: 00:00 (line-ups), 06:55, 09:04, 09:30 and 11:4x (goalmouth scrambles and Raya close-ups),
  12:35 (score graphic over the pitch), 16:21 and 21:51 (reverse and behind-goal replay angles).
- All clips: replays and slow motion are not detected yet. A replay of the main camera angle will pass as wide;
  check for the replay wipe before choosing a featured moment.

## Tuning history

1. Area-only blob filter that ignored blobs on the frame border: 63 usable shots in the Liverpool clip, about a
   quarter of them player close-ups (a close-up always touches the bottom edge).
2. Border blobs counted, at least 6 players required: 24 usable shots, high precision, but long wide shots were lost
   because stands and benches along the bottom edge formed one large blob.
3. Only tall blobs count as close-ups, at least 4 players: the version above.

## T-103: `python -m evals.pitchwatch.shots` (23 Oct 2026)

Same wide-shot rules, plus replay detection. The score graphic and its clock stay on screen through replays, and a
replay is often reframed, so neither the graphic nor matching against earlier frames finds them (tried both). Every
replay package opens and closes with a full-frame white wipe card with the league lion: wipe samples are paired in
order (in, out) within 100 s, and shots inside a pair are replays. Per-clip review files: `<slug>/shots_review.md`.

| clip | usable wide shots | usable wide time | wide replays dropped | replay segments | unpaired wipes |
|---|---|---|---|---|---|
| liverpool-mancity-2526 | 27 | 15:42 | 7 | 12 | 29:29 |
| manutd-mancity-2526 | 15 | 6:00 | 12 | 14 | 02:49, 20:46, 22:45 |
| arsenal-chelsea-2526 | 18 | 6:09 | 18 | 17 | 19:14, 23:59 |
| manutd-spurs-2425 | 19 | 6:27 | 13 | 14 | 02:47, 15:15, 24:23 |

The five long Liverpool windows (13:22, 07:15, 10:35, 09:18, 26:34) contain no replay. The seven dropped Liverpool
shots were checked on thumbnails: all replay angles (free-kick re-runs, reverse and high cameras).
