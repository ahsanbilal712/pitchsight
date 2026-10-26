# The Meridian League

A fictional eight-club top flight, written for WHYLINE. Every club, player, ground and town here is
invented. Club and player data live in `clubs.json`, `players.json` and `styles.json`; this file is the shared
background the agents may draw colour from. Facts on screen still come only from the match data, never from lore.

## The league

The Meridian League was founded in 1921 when eight clubs from the river towns of the Meridian valley broke away
from their county associations to play a double round-robin of their own. It has kept the same eight clubs ever
since, and promotion and relegation run through a play-off against the winners of the second division.

Seasons run from late summer to early spring. A match is ninety minutes in two halves; there is no extra time in
the league. The trophy is the Meridian Shield, a silver plate engraved with the founding year and the eight crests.

## Clubs at a glance

| Club | Town | Ground | Identity |
|---|---|---|---|
| Verdant Athletic | Larkhaven | The Glasshouse | Patient possession, a youth-led revival, three titles in the 1960s |
| Ironvale Forge | Ironvale | Anvil Road | High press, direct, the most feared away side |
| Saltmarsh Mariners | Saltmarsh | Quayside Park | Width and crossing; a factory of full-backs |
| Northmoor Wanderers | Northmoor | Heathfield | The oldest club; compact mid-block and quick counters |
| Copperdene Rangers | Copperdene | The Kiln | Set-piece specialists, deep and patient |
| Westhollow Harriers | Westhollow | Lantern Lane | The fastest tempo in the league, and the most counters conceded |
| Granite Hill | Granite Hill | Quarry End | Newly promoted; the tallest back line, aerial strength |
| Brackenford Town | Brackenford | Millrace Ground | Expansive 4-3-3, inverted full-backs, a prolific academy |

## Rivalries

- **Glass and Iron (Verdant v Ironvale).** Born in the cup finals of 1974 and 1975, both won in extra time, one
  by each side. The fixture is the league's biggest crowd every season and the golden match of this project.
- **The Coast Road (Verdant v Saltmarsh).** A friendlier rivalry along the estuary road; away fans walk.
- **The Moor and the Harbour (Saltmarsh v Northmoor).** Fishing town against hill town; the bugle call at
  Heathfield is aimed squarely at the visiting Mariners.
- **The Furnace Derby (Ironvale v Copperdene).** Foundry against pottery, eleven miles apart.
- **The Quarry Derby (Copperdene v Granite Hill).** Renewed this season after Granite Hill's promotion.
- **The Millrace (Westhollow v Brackenford).** Two young clubs, two fast styles, the league's highest-scoring fixture.

## The golden match: Verdant Athletic v Ironvale Forge

Verdant (home, deep green with gold) like to keep the ball and build through their midfield metronome
**Lauro Silva** (p_022, No. 8). Their forwards are **Tobi Okafor** (p_017, No. 9), who shoots early and from tight
angles, and **Teo Reyes** (p_031, No. 11), who arrives late at the far post. Ironvale (away, red with black) press
high and go direct; their pressing is the reason Verdant's patience gets tested.

The storyboard moment: Silva finds Okafor, Okafor shoots from a tight angle, and Reyes was free at the far post.

## Style profiles

`styles.json` gives each club five dials between 0 and 1: `press_height` (how high the first line presses),
`tempo` (speed of ball circulation), `width` (how wide the team spreads in possession), `directness` (share of
forward, line-skipping passes) and `line_height` (depth of the defensive line). The Kickoff engine reads them as
its style priors; hidden match truth may drift from them during a match.

## Writing rules for agents

- Use player names only as they appear in `players.json`; the engine emits ids, names are resolved at render time.
- No injuries, no referee-bias talk, no betting language, and no real club, league, player or broadcaster names
  (`banned_names.txt`).
