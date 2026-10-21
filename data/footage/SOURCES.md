# Footage sources (never commit the media files)

All entries below were confirmed on 21 October 2026 as uploads by the **Premier League** channel (`@premierleague`)
via YouTube's public oEmbed endpoint. Only uploads by this channel fall under the written permission in
`docs/permissions/`. The channel's "Club highlights 2026/27" playlist contains uploads by club channels
(Manchester United, Arsenal, Brighton, Hull, Aston Villa, Liverpool); those are **not** covered and must not be used.

Status: `pending` until the file is in `data/footage/<slug>/clip.mp4`. Durations are from the channel listing.

| slug | official channel URL | title | duration | planned use | status |
|---|---|---|---|---|---|
| liverpool-mancity-2526 | https://www.youtube.com/watch?v=bYcxD-GbJOI | WILD Final 20 Minutes In Full \| Liverpool v Man City 2025/26 | 37 min, continuous play | **Primary.** Sliding Doors moment and the Oracle threat front: long uninterrupted broadcast shots are the best input for tracking | downloaded 21 Oct 2026: 1080p50 H.264, 37:13, 1.5 GB, uploaded 7 Oct 2026 |
| manutd-mancity-2526 | https://www.youtube.com/watch?v=ZewC4N4Z7EI | A Dream Start For Carrick \| Manchester United v Manchester City 2025/26 | 25 min extended | Second Sliding Doors moment; Dugout (a tactical change by a new manager) | downloaded 21 Oct 2026: 1080p25 H.264, 25:32, 645 MB, uploaded 11 Sep 2026 |
| arsenal-chelsea-2526 | https://www.youtube.com/watch?v=HpWBLP-NkfY | David Raya Keeps Chelsea At Bay \| Arsenal v Chelsea 2025/26 | 25 min extended | Big chances and goalkeeper moments: Decision Index and the Panel debate | downloaded 21 Oct 2026: 1080p25 H.264, 25:32, 657 MB, uploaded 4 Sep 2026 |
| manutd-spurs-2425 | https://www.youtube.com/watch?v=nRjuhIa4-YE | Bruno RED \| Van de Ven CRAZY Assist! \| Manchester United v Spurs 2024/25 | 25 min extended | Fourth Official: the red-card foul with contact point and closing speed | downloaded 21 Oct 2026: 1080p30 H.264, 25:33, 657 MB, uploaded 9 Oct 2026 |
| everton-chelsea-classic | https://www.youtube.com/watch?v=VsTj78eKcoA | THRILLER At Goodison! \| Everton v Chelsea \| Classic Premier League Highlights | 25 min extended | Backup; older footage, camera style differs | pending |
| matchweek7-goals-2627 | https://www.youtube.com/watch?v=q8QhLLocpt8 | EVERY Weekend Goal \| Matchweek 7 \| 2026/27 Premier League Highlights | 3 min 24 s, many cuts | Recap cards only; too many cuts for tracking | pending |
| leeds-manutd-2122 | https://www.youtube.com/watch?v=8zSFMqqUwV0 | A WILD Game In The Wind And Rain! \| Leeds v Manchester United 2021/22 | 13 min | Backup | pending |

Selection notes
- Prefer the two 2025/26 extended cuts and the Liverpool v Man City "In Full" segment: current kits, current broadcast
  camera grammar, and long steady wide shots.
- For each featured moment record `wide-shot window (mm:ss–mm:ss)` once the file is in hand (T-103).
- Downloaded with yt-dlp 2026.08.19 under the user's permission and the Premier League written permission; every
  `clip.info.json` confirms channel ID `UCG5qGWdu8nIRZqJ_GgDwQ-w` (Premier League). No clip has chapters.
- Shot analysis: see `SHOTS_REVIEW.md` and each folder's `shots.json`.
