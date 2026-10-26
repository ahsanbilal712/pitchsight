# Nine More Ideas for 45 Days (plain-language edition)

These are new, not extensions of the earlier seven. Each is written so a non-technical reader can picture it: what the fan sees, why nobody has it, how we would build it, and how hard it is in 45 days. "Pairs with Sliding Doors" notes where the rewind-and-replay engine makes the idea stronger, but none of these depend on it.

---

## 1. The Decision Index — rate what players *chose*, not what happened

**What the fan sees.** Next to each player's name, a number from 0 to 100: how often they picked the best available option. After the match: "Reyes made the best choice 81% of the time. Okafor 54%. His worst call: shooting at 31' when Reyes was free."

**Why it is new.** Every football stat rates outcomes: goals, assists, pass completion. Fans argue endlessly about *decision-making* ("he always shoots when he should pass"), and there has never been a number for it. We can produce one because, at every moment a player has the ball, we can replay all the options and see which was best.

**How it is built.** At each on-ball moment, list the options (pass to each teammate, carry, shoot, clear), replay each for a minute, score each by how much it raises the team's chance of scoring. The player's actual choice is compared to the best one. Average over the match and the season.

**Difficulty.** Easy once the replay engine exists (3–4 days). **Pairs with Sliding Doors:** it is the same engine, turned into a player stat. **Prize fit:** Real-World Impact (a brand-new stat broadcasters would license), Personalise (player-focused mode).

---

## 2. The Fourth Official — explains every refereeing call, with the lines drawn

**What the fan sees.** A goal is disallowed. Within three seconds, the overlay draws the offside line, highlights the attacker's shoulder 40 cm past the defender, and says in the fan's language: "Offside. Diallo was 0.4 m beyond the last defender when the pass was played." For a foul: the contact point, the speed of the tackle, and the rule in one sentence. For a penalty: "Inside the box by 1.2 m."

**Why it is new.** "Why was that disallowed?" is the most-asked question in football. Google used it as the showcase prompt for its World Cup assistant. Broadcasters spend minutes on it with a pundit and a freeze-frame. We can do it instantly, for every decision, in every language, because our tracking data knows where every player and the ball were at the exact moment.

**How it is built.** Offside geometry from tracking (last defender, attacker's position, moment of the pass). Foul detection from tackle events plus closing speed. A small rules library (offside, handball zones, penalty area, back-pass) and a Referee agent that writes the one-sentence explanation from the geometry, verified by the fact checker. Drawn as overlay graphics.

**Difficulty.** Medium (5–6 days; most of it is drawing it well). **Prize fit:** Explain, Render, Multi-language. Very legible on video.

---

## 3. The Auto-Telestrator — the pundit's drawings, generated live

**What the fan sees.** Every few minutes, a short animated "chalkboard" clip appears: the pitch freezes, arrows draw the pressing trap, a zone lights up where the space opened, a one-line caption explains it. Exactly what a studio analyst draws at half time with a touchscreen, except it happens during the match, automatically, in the viewer's language and depth.

**Why it is new.** Telestration (drawing on the pitch) is the most-loved analysis format on TV and it is 100% manual. Automated graphics today are score bugs and stat bars. Nobody auto-generates *drawn tactical lessons* from live data.

**How it is built.** The analytics layer already detects patterns (line breaks, overloads, pressing traps, switches of play). A Telestrator agent picks the most teachable one, chooses a template (arrows, zones, player highlights, ghost runs), fills it from tracking data, and the renderer animates it over a freeze-frame. Casual mode gets one simple drawing; analyst mode gets the full sequence.

**Difficulty.** Medium (6–8 days, mostly render templates). **Pairs with Sliding Doors:** the ghost run of the better option is one of the templates. **Prize fit:** Render, UX, Personalise.

---

## 4. The Control Room — one studio watching ten matches at once

**What the fan or producer sees.** A wall of ten live matches from the synthetic league. The AI watches all of them and keeps a ranked list: "Match 7: equaliser likely in the next two minutes. Match 3: red card just shown. Match 1: 0–0, nothing happening." The feed auto-switches to the match where the story is, with a one-line reason. A fan version shows only *your* club's match plus the moments from other matches that affect your table position.

**Why it is new.** Multi-match shows (Soccer Saturday style, goal rushes, final-day coverage) are a huge broadcast format, and the switching decisions are made by a human director listening to ten feeds. The challenge explicitly mentions "studio" scenarios; nobody is building the multi-match case.

**How it is built.** Run ten synthetic matches in parallel (trivial for a simulator). Each produces leverage and threat scores every two seconds. A Switcher agent ranks the matches by "story value now" (threat, scoreline swing, cards, table impact) and produces a cut list with reasons. The render shows a 10-up wall, the main feed, and the reason bar.

**Difficulty.** Medium (one week; needs the season engine). **Pairs with Sliding Doors:** the Oracle's forecast is what tells the Switcher where to look next. **Prize fit:** Real-World Impact (broadcasters), Multi-Agent (one agent per match plus a switcher), Azure (parallel event streams scale nicely).

---

## 5. You Be The Player — the fan replays the moment their way

**What the fan sees.** The match pauses at a big moment. "Okafor shot. What would you do?" The fan drags a pass line to Reyes, or taps "dribble," or "shoot." The engine plays their version forward and shows the result: "Your pass: 31% chance of a goal in the next minute. His shot: 6%. The pundits' pick: your pass." A share button posts a 10-second clip of "my version."

**Why it is new.** Every second-screen app today is read-only (stats, polls). This makes the fan a participant in the analysis, which is what the mute-the-commentary generation says they want: control. It turns explanation into play without becoming gambling.

**How it is built.** The replay engine already accepts an alternative action; here the alternative comes from a touch gesture instead of an algorithm. A small UI for choosing, a rendering of the chosen future, and the clip export. Points-based leaderboard ("best decision-makers tonight"), no money, no odds.

**Difficulty.** Easy-Medium (4–5 days on top of the engine). **Pairs with Sliding Doors:** it *is* Sliding Doors with the fan's hand on the controls. **Prize fit:** UX, Personalise, Real-World Impact (engagement).

---

## 6. Football Teacher — a mode that teaches the game while you watch

**What the fan sees.** A new fan or a child picks "Teach me." The match plays with gentle pauses: "That was a *press*. Watch the three red players run at the ball together. Why? To force a mistake." Two minutes later: "Quiz: which team is pressing now?" Tap the answer, get a star. Vocabulary builds over the match and across the season. Available in every language.

**Why it is new.** The challenge demands that the same match reaches "a casual fan" as a genuinely different experience. "Casual mode" in every other entry means fewer numbers. Teaching is a different experience, and football's growth markets (new fans, kids, new countries) are exactly who the Premier League wants to reach.

**How it is built.** A curriculum of ~40 concepts (offside, press, low block, switch of play, counter-attack, xG in plain words), each with a detector in the analytics layer that fires when a clean example happens. A Teacher agent chooses the next concept the viewer hasn't mastered, writes the explanation at the right reading level, and generates a quiz from the real match state. Progress stored per viewer.

**Difficulty.** Easy-Medium (5 days). **Prize fit:** Personalise, Real-World Impact, Multi-language. Judges with children will remember it.

---

## 7. Catch Me Up — join late, understand everything in 30 seconds

**What the fan sees.** You open the stream in the 63rd minute. Before the live picture, a 30-second personalised catch-up plays: the score, the two moments that decided it, what your player has done, and what to watch for now. Voice in your language, three graphics, then live. Tap "longer" for 90 seconds, or "just the goals."

**Why it is new.** Everyone joins matches late and every app shows them a scoreline and a wall of events. A spoken, personalised, *story-shaped* catch-up is what a friend on the sofa gives you, and no product does it.

**How it is built.** The blackboard already ranks moments by importance. A Catch-Up agent takes the viewer's profile and the match so far, picks the top moments, writes a 30/90-second script, and the renderer stitches graphics and a voice. Done in under five seconds on request.

**Difficulty.** Easy (3 days). **Pairs with Sliding Doors:** "the two moments that decided it" are the top-leverage sliding doors. **Prize fit:** Personalise, UX. Small feature, big demo moment.

---

## 8. Producer Copilot — an assistant for the people making the broadcast

**What the producer sees.** A side panel in the gallery: "Suggested graphic: Diallo's third sprint over 30 km/h, ready to air." "Commentator note: Verdant have not won from behind this season." "Social post drafted in six languages for the goal." "Storyline forming: Okafor's decision-making, three bad choices in 20 minutes." Each with an approve button. Nothing airs without a human.

**Why it is new.** Most entries are fan-facing. The people who decide what goes on air are producers, and their tools are spreadsheets and talkback. An assistant that drafts graphics, notes and posts from verified data, with approval gates, is the fastest path to real adoption and the clearest "enterprise" story in the hackathon.

**How it is built.** The newsroom already produces verified cues. Add a Producer agent that re-targets them for gallery roles (graphics operator, commentator, social desk), ranks by urgency, and routes through an approval UI with an audit trail. Integrates with the broadcast graphics adapter so "approve" really airs it.

**Difficulty.** Medium (5–6 days). **Prize fit:** Best Enterprise Solution (controls, audit, human in the loop), Real-World Impact.

---

## 9. Pattern Hunter — spots the routines teams repeat

**What the fan sees.** "This is the fourth time this season Verdant have used this corner routine: near-post block, late run to the back post. It scored twice." The four clips play side by side. Later: "Harbour FC always switch play after four passes on the left. Watch." And then they do.

**Why it is new.** Analysts find repeated routines by watching hours of video. With tracking data for a whole synthetic season, a machine can find them automatically and, crucially, *predict* when they are about to happen, which makes the broadcast feel clairvoyant.

**How it is built.** Cluster set-piece and open-play sequences across the season by player movement shape. Name the clusters with an LLM. Detect when the opening of a known routine starts in the live match and trigger a "watch for this" cue. Needs the Living Season to have enough matches.

**Difficulty.** Medium-Hard (one week; the clustering needs care). **Prize fit:** Explain, Interpret, Real-World Impact (scouting value).

---

## How I would rank them

| Rank | Idea | Why |
|---|---|---|
| 1 | **Fourth Official** | Answers the most-asked question in football, instantly, in every language. Impossible to misunderstand on video. |
| 2 | **Decision Index** | A genuinely new football statistic. Memorable, arguable, licensable. |
| 3 | **Control Room** | The studio scenario nobody is building; shows scale and multi-agent coordination naturally. |
| 4 | **Auto-Telestrator** | The most-loved TV analysis format, automated. |
| 5 | **You Be The Player** | Turns the viewer into a participant. Strong engagement story. |
| 6 | **Producer Copilot** | The clearest enterprise and adoption story. |
| 7 | **Football Teacher** | The deepest version of "casual mode." |
| 8 | **Catch Me Up** | Small, delightful, three days. |
| 9 | **Pattern Hunter** | Impressive but the hardest to get right. |

**If you want a single platform story for 45 days:** Sliding Doors as the engine; Fourth Official, Decision Index and Auto-Telestrator as the three things fans see every match; Control Room as the studio showcase; Producer Copilot as the enterprise layer; Catch Me Up and Football Teacher as the personalisation proof. That set covers all five pipeline stages, all four category prizes, and every item is buildable in the window.
