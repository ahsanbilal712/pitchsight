# WHYLINE — The Whole Idea, Explained Simply

*For the Microsoft × Premier League "Inside the Game" hackathon. Written so that anyone on the team, or any judge, can understand it without reading anything else.*

---

## 1. In one paragraph

WHYLINE is an AI system that watches a football match and explains it, live, to every fan in the way that fan wants. At its centre is a **learned model of football**: a neural network trained on hundreds of matches that predicts what players do next, which we can sample hundreds of times to generate possible futures. That lets us do something no TV broadcaster can do with a real game: **pause the match at any moment, rewind, and let the model play it forward with one thing changed, 200 times, to see what that moment really cost.** We call that feature Sliding Doors, and it is the heart of the product. Around it sit a team of AI agents built on large language models that propose the alternatives, find the moments, explain them, argue about them, check every number, translate them, and decide what goes on screen for each viewer: an analyst, a casual fan, a child, a fan following one player, a producer in the studio.

---

## 2. The problem we are solving

**Fans get numbers without meaning.** Broadcasts now show "expected goals 0.06" on screen with no explanation. Fans and even players call it nonsense. One analytics writer put it well: fans are "drowning in data, starved of wisdom."

**Fans are switching the sound off.** A 2026 survey of 2,000 UK consumers found that half of football fans sometimes mute the commentary, and among 18 to 24 year-olds nearly four in ten do it often. They replace it with fan podcasts, radio or their own music. They do not hate sound. They want sound that is theirs.

**Broadcasters cannot personalise.** One feed goes to hundreds of countries. The analyst in Manchester, the first-time viewer in Jakarta and the ten-year-old in Lagos all get the same lower-third graphic.

**And nobody explains *why*.** A graphic can tell you a shot had a 6% chance of going in. Nothing on television tells you that the pass he didn't make had a 31% chance, or that the decision cost his team nine percent of their chance of winning. That is the question every fan actually argues about in the pub.

---

## 3. The big idea: a match you can rewind and replay

Every other team in this hackathon uses a simulator the same way: to generate fake match data so an AI can write commentary about it. We do something different. We **train a model of how footballers behave**, and then use it as a world you can branch: freeze a moment, change one decision, and sample what the model thinks happens next.

Here is what that means, with one moment from a match.

**31st minute.** Verdant FC are losing 0–1. Okafor gets the ball on the edge of the box. His teammate Reyes is completely unmarked at the far post. Okafor shoots. It goes wide.

**What everyone else would show:** "Okafor shoots. 0.06 xG."

**What WHYLINE does:**

1. Pauses the match at the exact instant Okafor had the ball.
2. Asks a language model what else he could have done. It answers in football terms: square it to Reyes, hold and wait for the overlap, cut inside.
3. Makes 200 copies of the game for each option, and forces the first action to be that option.
4. Lets the **learned behaviour model** play all the copies forward. It predicts, ten times a second, what every player would do: where Reyes runs, how the defenders react, whether the keeper comes out. Physics and the rules of the game are code; the behaviour is the model's.
5. A trained outcome model scores every future: how likely a goal is, and what that does to the chance of winning.
6. Does the same with no change, 200 more copies of what actually happened, and compares.

**What the fan sees:** a ghost trail of the pass he didn't make, 200 translucent futures spreading across the pitch, and a bar reading "Verdant win chance: 42% → 51%. The shot cost 9 points." One line of commentary: "Okafor shoots from a bad angle. Reyes was free at the far post. That decision probably cost them a goal."

The name comes from the film *Sliding Doors*, where one small choice splits the story into two versions.

**Why this is the best idea in the competition:**

- The challenge asks us to "explain why a moment matters rather than only reporting that it happened." *Why* means *compared to what*. Replaying the alternative is the only honest way to answer.
- It is honest because the futures come from a trained model of behaviour, not from rules we wrote. If we had scripted the players, "what he should have done" would just be our own opinion fed back to us.
- No other entry can do it, because none of them built a learned world that can be rewound and branched.
- It is understood in five seconds of video by someone who knows nothing about statistics.
- The same trick, pointed in different directions, gives us three more features for free (see section 5).

---

## 3b. Where the AI actually is

A fair question for any project like this is "where is the machine learning, and where is it just code?" Here is the honest inventory. The detailed design is in `ML_CORE.md`.

**Models we train ourselves**

- **The behaviour model.** A transformer that looks at all 22 players and the ball and predicts what each will do in the next second: who the player on the ball passes to, shoots, or carries, and where everyone else runs. Trained by watching hundreds of matches played by pretrained reinforcement-learning football teams inside Google Research Football (teams that learned to play through self-play, so their behaviour is emergent, not scripted), plus matches from our own engine. This model is the world that Sliding Doors, the Oracle and Dugout all run inside.
- **The outcome models.** Small trained models for expected goals, the value of a pass or carry, win probability, pass completion, and "chance of a goal in the next 15 seconds." Every number the system puts on screen comes from one of these.
- **Moment embeddings.** A model that turns any match situation into a vector so similar situations sit close together. Used to recognise tactical phases (high press, low block, transition), to measure chaos, and to find "the last time this happened to your club."
- **A fine-tuned narrator.** A small language model fine-tuned on 20,000 verified commentary lines in six languages, so it writes in our voice, obeys our format and runs cheaply, including offline.

**Pretrained models we use directly**

- Player, ball and pitch detectors (RF-DETR, YOLO, pitch keypoints, ByteTrack) fine-tuned on frames from our 3D renders, so the system can read a match from pixels.
- Google's Gemini 4 Argon for near-line video event tagging as a second opinion.
- Pretrained 11v11 reinforcement-learning football teams as the source of realistic play.
- Speech-to-speech and text-to-speech voice models for commentary and for answering a fan's spoken question.

**Language models doing real work, not just writing**

- Proposing the alternatives for Sliding Doors in football terms ("wait for the overlap"), which the behaviour model then evaluates. The language model steers the simulation.
- The Tactician, which decides which tools to call (run a counterfactual, fetch pitch control, find similar moments) and reasons from the results to a causal explanation.
- Three pundits that argue, a judge that checks their stories, and a showrunner that remembers what each viewer has watched.

The one rule that keeps all of this honest: a language model may reason, propose, argue, remember and speak, but **every number it says must come from a trained model or the event log, and a piece of code checks it before it reaches the screen.**

## 4. How the system works, step by step

The hackathon requires one pipeline with five stages. Here is ours in plain words.

### Stage 1 — Ingest: the match itself

We built a football simulator called **Kickoff**. It moves 22 players and a ball, ten times a second, using team "styles" (how high they press, how fast they play, how direct they are) and simple player decision rules. It produces two streams:

- **Events:** every pass, shot, tackle, interception, pressure, foul, card, substitution, with who, where and when.
- **Tracking:** the position of every player and the ball, ten times a second.

The clubs and players are fictional (the rules forbid real data and real names). An AI writes the league for us: club names, histories, rivalries, 200 players with personalities and backstories, so the commentary has something to talk about.

The simulator also keeps a hidden "truth" (which tactical phase each team is really in, where the momentum really is) that the live system never sees. That lets us measure how often our explanations are right.

We also run a second world, Google Research Football, which has a real 3D game engine and teams controlled by pretrained reinforcement-learning agents. Their play is emergent, not written by us, which makes it the main training data for the behaviour model, a source of realistic video footage, and an independent world to test against.

### Stage 2 — Interpret: turning positions into football

Ten times a second, a mix of physics and trained models:

- **Pitch control** (physics): for every two-metre square on the pitch, which team would get there first. Drawn as a heat map, it shows who owns the space.
- **Tactical phase and chaos** (learned): the moment-embedding model recognises whether a team is pressing high, sitting deep or in transition, and a trained head predicts how likely the ball is to change hands in the next ten seconds. Chaos is that number averaged over the last minute. The system labels the game Settled, Transitional or Chaotic and announces when it changes.
- **Pass quality** (learned): a trained pass-completion model gives every pass a difficulty rating from distance, pressure and the receiver's space.
- **Speeds** (physics): ball speed, shot speed, player sprints with distance covered.
- **Expected goals and expected threat** (learned): trained models for how likely a shot is to score and how much a pass or carry increased the danger, using the full picture of where defenders are.
- **Win probability** (learned): the team's chance of winning right now.

### Stage 3 — Explain: the Sliding Doors engine and the AI newsroom

The behaviour model and the futures it generates live here. On top of it sits a **team of AI agents**, each a language model with one job, built on Microsoft Agent Framework:

| Agent | Job |
|---|---|
| **Scout** | A small classifier over the moment embeddings plus the goal-chance model; flags moments worth talking about. |
| **Proposer** | Reads the frozen moment and suggests, in football language, what else the player could have done. The behaviour model then tests each suggestion. |
| **Tactician** | Decides which tools to call (counterfactual, pitch control, similar past moments, player stats) and reasons from the results to a causal explanation. Every claim tied to a model output or an event. |
| **Narrator** | A small language model we fine-tuned on verified commentary. Writes the words, in the voice of the viewer's chosen mode. |
| **Fact Checker** | Code, not AI. Checks every number, name and minute against the trained models and the event log. Rejects anything it cannot verify and sends it back. Nothing unverified ever reaches a screen. |
| **Judge** | A language model that checks the *story*, not the numbers: does the explanation follow from the tool results? Catches "right numbers, wrong reason." |
| **Localizer** | Translates into six languages with a football glossary, then gets re-checked. |
| **Director** | Decides what goes on screen for each viewer and when. Never during a shot. Never more than one graphic every 45 seconds for a casual fan. Prefers the moments that mattered most. |
| **Recap Editor** | At half time and full time, writes the story of the half: the three sliding-doors moments, the chaos timeline, the player of the match. |

They share one notebook (a database we call the blackboard) and reach the match data only through a small set of tools, which is also the audit boundary. If one agent crashes mid-moment, the system resumes from a saved checkpoint. We demonstrate that live by killing an agent during the demo.

### Stage 4 — Render: putting it on screen

Every decision becomes a **cue**: a small machine-readable message saying what to show, when to show it (to the millisecond), on which layer, for which viewers, in which languages, with the evidence attached. Cues are delivered three ways:

- **Broadcast overlay:** a transparent graphics layer that drops straight into broadcast software (OBS, CasparCG, Singular.live), carried inside the video stream so it stays in sync.
- **Studio console:** for the producer. The live blackboard, the queue of moments, which agent did what, a "Why?" button on every line that opens the evidence, and a veto button.
- **Fan app:** a second screen on your phone.

The match itself is drawn from the tracking data, in 2D for the light live overlays and in **stylised 3D** for the replays: a stadium, a broadcast camera, players as figures in kits, 200 ghost futures fanning out across the pitch. Same data, two renderers. Since the rules forbid real footage, every team's video is synthetic; a good 3D render is the best picture anyone can legally show.

### Stage 5 — Personalise: made for every fan

The fan picks a mode, a club, a player, a favourite stat, a language and accessibility needs. Personalisation happens at three levels:

- **What is chosen:** the analyst gets state changes and counterfactuals; the casual fan gets goals, big chances and one "did you know" every ten minutes; the kid gets celebrations and simple cause and effect; the player-cam fan gets everything their player does.
- **How it is said:** same fact, four different sentences. "Shot from a tight angle: 0.06 xG" for the analyst. "He should have passed" for the casual fan. "Oh no, Okafor! Reyes was all alone!" for the kid.
- **Which language and voice:** six languages on day one, spoken by a chosen commentator voice, with a mode for blind and low-vision fans that describes where the ball and the danger are.

---

## 5. The features that fall out of the same engine

The rewind-and-replay trick, pointed in different directions:

| Feature | Point it at… | What the fan sees |
|---|---|---|
| **Sliding Doors** | the past | "That shot cost nine points. Reyes was free." |
| **The Oracle** | the future | A danger "front" rising on the pitch and a bar reading "Shot in the next 10 seconds: 34%", a few seconds before the cross comes. |
| **Dugout** | the manager's options | "Three options at 60 minutes: press higher, +6 pts. Bring on Diallo, +3 pts. Go direct, +1 pt." Ten minutes later: "Dugout called it." |
| **The Decision Index** | each player | A new stat: how often a player chose the best available option. "Reyes 81%. Okafor 54%." |
| **You Be The Player** | the fan | The match pauses. "What would you do?" Drag a pass. See your future play out. |

And a few that stand on their own:

- **The Fourth Official:** every refereeing call explained in three seconds with the lines drawn. "Offside. Diallo was 0.4 m beyond the last defender." The most-asked question in football, answered in every language.
- **Unmute:** a commentator that is yours. Pick the voice, the language, the intensity, the amount of numbers. Interrupt it with a question and it answers from the match data.
- **The Panel:** three AI pundits with different football philosophies who argue about each moment, and must cite a Sliding Doors number to make a claim. The fan picks which one to follow.
- **The Control Room:** ten matches at once. The AI watches all of them and switches to where the story is, with a reason.
- **Catch Me Up:** join in the 63rd minute and get a 30-second spoken summary of what you missed, personalised.
- **Producer Copilot:** for the people making the broadcast. Suggested graphics, commentator notes and social posts, each needing a human click before it airs.

Not everything ships at once. Sliding Doors, the Fourth Official and the newsroom are the core. The rest are added in order of how much they add to the demo.

---

## 6. The technology, in plain terms

| Need | What we use | Why |
|---|---|---|
| The behaviour model | A transformer we train (about 10 million parameters) on matches played by pretrained reinforcement-learning teams in Google Research Football, plus our own engine | It is the world Sliding Doors runs inside. 200 futures of 15 seconds in under a second on a GPU. |
| The outcome models | Trained models for expected goals, pass value, win probability, goal-in-the-next-15-seconds | Every number on screen comes from one of these. |
| The physics and rules | Our own code | Ball flight, collisions, offside, fouls are rules of the game, not behaviour, so they stay as code. |
| Reading the match from video | Pretrained detectors (RF-DETR, YOLO, pitch keypoints, ByteTrack) fine-tuned on our renders; Gemini 4 Argon for video tagging | Shows the system can start from pixels, as the rules ask. |
| The AI agents' brains | Frontier models (Claude, Gemini, GPT) for proposing alternatives, tool-using explanation, debate and judging; a small fine-tuned model for the thousands of commentary lines | Cents per match; the fine-tuned narrator also runs offline. |
| Coordinating the agents | Microsoft Agent Framework | Provider-independent, with built-in checkpoints, handoffs and tracing. This is the "multi-agent" the judges score. |
| Hosting, evaluation, tracing | Microsoft Foundry | Hosts the agents, measures how grounded their output is, records every decision. |
| Running it in the cloud | Azure Container Apps, Event Hubs, Cosmos DB, Web PubSub, Functions | Event-driven and scales to zero when idle, which is what the cloud-native prize asks for. |
| Voices | ElevenLabs or Azure Speech | Real-time, 30+ languages. |
| 3D picture | Three.js in the browser | Stylised but believable, any camera angle. |
| Broadcast graphics | OBS, CasparCG, Singular.live | Real production tools, so the cue format is proven, not theoretical. |

The rule we follow everywhere: **trained models predict and value; code enforces physics, rules and verification; language models reason, propose, argue and speak.** A language model never invents a number. Every number must come from a trained model or the event log, and the Fact Checker enforces it.

---

## 7. How we prove it works

Because the simulator keeps a hidden truth, we can measure ourselves honestly and publish the numbers:

- How often the system correctly spots a change from settled to chaotic play.
- How well calibrated the Sliding Doors predictions are (if we say 27%, does it happen 27% of the time?).
- How many planted false claims the Fact Checker catches (target: all of them).
- How fast a moment reaches the screen (target: under five seconds).
- What a full match costs to run in six languages (target: about a dollar).

With time, we also run a study with around 40 real fans: the same match passages shown plain, with standard stats, with Sliding Doors, and personalised. We measure whether they understood more, enjoyed it more, trusted it more, and whether they would turn the sound back on.

---

## 8. Why judges will score it highly

The five judging criteria carry equal weight.

- **Technology:** a real simulator with hidden truth, published calibration, every Microsoft "hero" technology used structurally rather than decoratively, clean code, tests, infrastructure as code.
- **Agentic design:** distinct agents with real handoffs, a fact checker that is a separate party from the writer, a director that makes editorial decisions, recovery from a killed agent, tools as the only path to data. Counterfactual tool use is genuinely new.
- **Real-world impact:** solves the broadcaster's trust-and-timing problem and the fan's data-without-meaning problem at once. Producer veto, audit trail, content safety, cost guard. A clear path to a production studio.
- **User experience:** three surfaces, a 3D replay that sells the idea in five seconds, a video built around moments nobody has seen before.
- **Category fit:** we enter as Best Multi-Agent System, and the architecture is that category's description almost word for word. It also satisfies the Azure cloud-native and Foundry category text.

---

## 9. The two-minute video, in one breath

A fan mutes the TV. A new voice starts, in her language. A shot goes wide; the screen rewinds, 200 futures fan out across a 3D pitch, a bar drops nine points: "Reyes was free." Danger rises on the pitch before the next cross comes. Three AI pundits argue about it, each citing a number. An agent is killed on screen and the system carries on. At the hour, the studio is told what the manager should do, and ten minutes later he does it. Half time: an analyst's breakdown, a kid's version, one player's story, and a description a blind fan can follow, all from the same engine. Numbers on screen: 97% grounded, under five seconds, cents per match. "WHYLINE. Every line on screen has a why."

---

## 10. What is already done, and what is next

Done: the research, the competitive analysis of other entries, the full architecture, the seven-day and 45-day plans, the list of ideas, and an interactive 2D mock-up of the Sliding Doors moment.

Next: build the Kickoff engine, because every feature stands on it. Then the Sliding Doors replay. Then the newsroom. Then the screens. Everything after that is adding features in the order that makes the demo stronger.

*Other documents in this folder: `ML_CORE.md` (the trained models, training data and plan), `WHYLINE_PROPOSAL.md` (full 7-day plan), `WHYLINE_45DAY_MASTERPLAN.md` (full 45-day plan), `TOP7_IDEAS.md` and `NEW_IDEAS_45DAYS.md` (all ideas considered).*
