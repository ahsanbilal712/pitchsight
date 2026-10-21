# Where the AI Is — The ML Core of WHYLINE

## 0. The honest diagnosis

In the plan so far, the "brain" of the match is a hand-written rule set, the metrics are formulas, and the language models sit at the edge writing sentences about numbers that code produced. That is a simulation with an LLM narrator. It is what most of the other 433 entries are, and it does not deserve a high score on "Agentic Design and Innovation."

Worse, it makes Sliding Doors circular. If a hand-written rule decides what players do, then "what would have happened if he'd passed" is just our rule's opinion. A sceptical judge will say so.

The fix is a different principle: **the model of football must be learned, not scripted.** Everything that decides what players do, what happens next, and what a situation is worth must be a trained model. Code only enforces physics, rules and verification. Language models reason over the learned model's outputs, propose alternatives, argue, remember and speak. Below is that design, with the specific models, the training data, the sizes, and what breaks if each one is removed.

---

## 1. The three-tier ML stack

```
TIER 3  REASONING & LANGUAGE   frontier LLMs (tool-using Tactician, alternative proposer, Panel debate, LLM judge,
                               memory/RAG Showrunner), a fine-tuned small Narrator model, speech-to-speech voice models
                                        ▲ consumes model outputs, never raw numbers it invented
TIER 2  THE FOOTBALL MODEL     (a) Behaviour policy  (b) Futures generator  (c) Outcome heads  (d) Moment embeddings
        (the core, trained)    "What would these players do next, 200 different ways, and what is each future worth?"
                                        ▲ trained on
TIER 1  PERCEPTION & DATA      pretrained vision (RF-DETR / YOLO26, pitch keypoints, ByteTrack, Gemini 4 Argon video),
                               Google Research Football + pretrained 11v11 RL teams, our Kickoff engine as bootstrap data
```

Remove Tier 2 and there is no Sliding Doors, no Oracle, no Dugout, no Decision Index. Remove Tier 3 and there is no explanation, no alternatives beyond brute-force enumeration, no personalisation, no voice. Remove Tier 1 and there is no realistic data and no path from pixels.

---

## 2. Tier 2: the football model (the heart)

### 2a. Behaviour policy — "what does a player do here?"

**What it is.** A transformer that takes the state of the match (23 entities: 22 players and the ball, each with position, velocity, team, role, fatigue, plus score and clock) and predicts, for the player on the ball, a distribution over actions (pass to each of 10 teammates, carry in 8 directions, shoot, clear, hold) and, for every player, their movement over the next second. Set attention over entities, so it is permutation-invariant, the same architecture family as TacticAI and FootBots.

**Why it must be learned.** This is the thing that makes a counterfactual honest. "If he'd passed to Reyes" is only meaningful if *what Reyes and the defenders do next* comes from a model of how footballers behave, not from an if-statement we wrote.

**Training data.** Behaviour cloning from two synthetic sources, both rules-compliant:
- **Google Research Football with pretrained 11v11 RL teams** (DB-Football / Light-MALib policies, TiZero-class play). These agents learned to play well through self-play; their behaviour is emergent, not scripted by us. 500 full matches = about 1.5 million frames with every position and action.
- **Our Kickoff engine** with randomised style profiles, for coverage of situations the RL agents rarely produce (parked buses, chaos endgames).
- Optional, licence permitting, public open real tracking data (SkillCorner open data, Metrica sample) for a small fine-tune so the movement statistics match real football. The rules require synthetic match data in the product; a licensed public dataset used only to train a model is third-party data we must be authorised to use, so this is a legal check first and a nice-to-have second.

**Size and cost.** 6-layer set transformer, about 10 million parameters. Trains in 3–6 hours on one GPU. Inference for 200 parallel worlds: under 5 ms per step on a GPU, about 40 ms on CPU.

**What breaks without it.** Counterfactuals are circular. The Decision Index ("did he pick the best option?") has no "best" to compare to.

### 2b. Futures generator — sampling what happens next

**What it is.** The behaviour policy rolled forward autoregressively: sample an action, apply the physics (ball flight, collisions, offside, fouls are code, because they are rules of the game, not behaviour), sample the next movement, repeat ten times a second. Running 200 copies in one batch on a GPU gives 200 futures of the next 15 seconds in well under a second. This is a **generative model of football**, sampled 200 times. The April 2026 papers GenTac and TacticGen do this with diffusion over whole trajectories; we do the simpler autoregressive version, which is enough for 10–20 second horizons where decisions matter, then hand off to the outcome heads.

**How Sliding Doors uses it.** Freeze the state at the decision. Branch A: let the model continue from what actually happened. Branch B: force the first action to the alternative, then let the model continue. Sample 200 of each. Score every future with the outcome head. The difference is the cost of the decision.

**How the Oracle uses it.** Same call every two seconds from the live state. The distribution of futures *is* the forecast: where the ball is likely to be, who is likely to shoot, how likely a goal is.

**How Dugout uses it.** Condition the policy on a different style vector (press height, line height, tempo) for one team and sample again. The style vector is an input the policy was trained with, so this is a legitimate "what if they changed tactics."

**What breaks without it.** There is no way to produce futures except the scripted engine, which brings back circularity.

### 2c. Outcome heads — what a situation is worth

Small learned models, trained on millions of simulated states with known outcomes:

| Head | Predicts | Model | Why learned |
|---|---|---|---|
| **xG** | P(goal) for a shot from this state | gradient-boosted trees on distance, angle, pressure, body part, goalkeeper position, number of defenders in the cone | Standard, but ours includes defender geometry from tracking, which public xG cannot |
| **xT / possession value** | expected goals added by moving the ball from A to B, or by this pass | neural net over state, trained on "goal within 20 s" labels | Replaces the 12×8 grid with a state-aware value |
| **Win probability** | P(home win, draw, away win) now | small MLP on score, clock, red cards, recent xT, chaos state | Learned calibration beats hand-fitted logistic |
| **Goal-in-horizon** | P(home goal, away goal in next N s) from a state, without rolling out | distilled from millions of rollouts | Lets the Decision Index score every on-ball moment cheaply; the full rollout is reserved for the moments that matter |
| **Pass completion** | P(pass completes) | GBT on distance, angle, pressure, receiver space, pass height | Pass difficulty = 1 − this |

Each head is a trained artefact in the repo with a calibration plot. The Fact Checker uses these heads as the source of truth for any number the LLMs cite.

### 2d. Moment embeddings — "this is like that"

A contrastive encoder that maps any match state to a vector such that similar tactical situations are close. Trained on augmented pairs (same moment, jittered positions) against hard negatives. Uses:

- **Retrieval for narratives.** "This is the fourth time this season Verdant have been caught like this; here are the other three" (Pattern Hunter). The Showrunner agent retrieves similar past moments for the viewer's club.
- **Phase labelling.** Cluster the embeddings; name the clusters with an LLM; the live system reports "high press," "low block," "transition" from the nearest cluster, with an explanation. This replaces the hand-written state machine and is validated against the engine's hidden truth.
- **Chaos as a learned quantity.** Train a head to predict "possession changes hands within 10 s"; chaos is its average over the last minute. Explainable (attention weights show which players drive it) and no longer a formula we invented.

---

## 3. Tier 1: perception and data

| Model | Pretrained source | Role |
|---|---|---|
| **RF-DETR / YOLO26** player, ball, referee detection | Roboflow football datasets (CC BY 4.0), fine-tuned on frames rendered from our 3D scene and from gfootball, where labels are free and perfect | Auto-eventing from pixels (Pitchwatch) |
| **Pitch keypoint model + homography** | Roboflow soccer pitch keypoints; SoccerNet calibration baselines | Maps image coordinates to pitch metres |
| **ByteTrack / re-identification** | SoccerNet game-state-reconstruction baseline (TrackLab) | Keeps player identity across frames |
| **Gemini 4 Argon, agentic video** | Google | Near-line event tagger from a rendered clip with structured output; the second opinion against the detector pipeline, and the evaluator of our own overlay sync |
| **Google Research Football + DB-Football 11v11 policies** | Google / Shanghai Digital Brain Lab (open) | The realistic world: emergent play for training data and for rendered footage |
| **Kickoff engine** | ours | Bootstrap data generator, physics for rollouts, hidden truth for evaluation |

Perception is where "pretrained" is literally true: these are published weights we fine-tune, not things we invent.

---

## 4. Tier 3: language models doing work, not decoration

Each use below is one where the LLM *changes what the system does*, not just how it is phrased.

| Use | Model | What it does that code cannot |
|---|---|---|
| **Alternative proposer** | frontier model (Claude Opus 5.5 / Gemini 4 Argon / GPT-6.1) | Sliding Doors needs candidate alternatives. Enumerating "pass to each teammate" misses the ones humans argue about: "delay and wait for the overlap," "switch play," "take the foul," "recycle and reset." The LLM proposes semantic alternatives from the state description; the futures generator evaluates them. This is the LLM steering the simulation. |
| **Tool-using Tactician** | frontier model with tools | Decides *which* model calls to make: run a counterfactual, fetch pitch control, retrieve similar moments, query a player's season stats; synthesises a causal explanation ("the press broke the line, which left Reyes free, which is why the pass was worth 0.31"). Multi-step reasoning with tools is the "agentic" criterion. |
| **The Panel** | three frontier models, one each | Structured disagreement. Each pundit must ground every claim in a model output; the chair adjudicates. Multi-agent debate improves explanation quality and surfaces uncertainty honestly. |
| **LLM judge** | frontier model | Rates tactical plausibility of explanations against the Tactician's tool trace; catches reasoning errors the numeric Fact Checker cannot (right numbers, wrong story). Runs in CI as an evaluation gate (Foundry Evaluations with a custom evaluator). |
| **Showrunner with memory** | frontier model + retrieval over the season blackboard and moment embeddings | Plans the story for *this* viewer: what they watched, who they follow, what happened in the reverse fixture. Retrieval-augmented, so claims are grounded. |
| **Fine-tuned Narrator** | small model (Phi-4-mini or GPT-4o-mini class) fine-tuned in Foundry on 20,000 verified, human-rated lines in six languages | A model that writes in our voice, obeys the structured-claims format 99% of the time, and runs at a fraction of the cost and latency of a frontier model. This is a trained artefact we ship, and it runs on Foundry Local for the offline judge demo. |
| **Speech-to-speech** | Gemini 3.8 Live or Azure Voice Live | Barge-in questions ("why was that offside?") answered from the blackboard with tools, in the fan's language, in under two seconds. Native audio models, not text-to-speech bolted on. |
| **League and narrative author** | frontier model | Generates the fictional league, players, histories and rivalries, conditioned on the season simulator's actual results so stories are true. |
| **Cluster namer** | frontier model | Names the tactical-phase clusters from the moment embeddings and writes their one-line definitions. |

The rule that keeps this honest: **every number an LLM says must come from a Tier 2 model or the event log, and the Fact Checker (code) verifies it.** LLMs reason, propose, argue, remember and speak. They never invent a statistic.

---

## 5. Sliding Doors, restated with the ML in it

1. The **Scout** (a small classifier over moment embeddings plus the goal-in-horizon head) flags a moment with high leverage.
2. The **alternative proposer** (LLM) reads the state and suggests three alternatives in football language.
3. The **futures generator** (behaviour policy + physics) samples 200 futures for the actual action and for each alternative, on a GPU, in under a second.
4. The **outcome heads** score each future; the **win-probability head** turns goals into a win-chance swing.
5. The **Tactician** (LLM with tools) calls pitch control and retrieval, and writes a causal explanation with claims bound to model outputs.
6. The **Fact Checker** (code) verifies every number against the heads and the log; the **LLM judge** checks the story.
7. The **fine-tuned Narrator** writes the line per mode; the **Localizer** translates; the **Director** schedules it; the voice model speaks it.

Every step from 1 to 7 is a model except the physics and the verifier, and those are code on purpose.

---

## 6. Training plan inside 45 days

| Week | Train | Data | Deliverable |
|---|---|---|---|
| 1 | Outcome heads (xG, xT, pass completion, win prob) | 2,000 Kickoff matches | Calibration plots; Fact Checker uses the heads |
| 2 | gfootball data generation with pretrained 11v11 teams; behaviour policy v1 | 500 gfootball matches + 2,000 Kickoff | Policy beats a velocity-extrapolation baseline on 4-second movement prediction (FDE); action top-3 accuracy reported |
| 3 | Futures generator (policy + physics) on GPU; goal-in-horizon head distilled from rollouts | 1 million rollouts | 200 × 15 s futures in < 1 s; Brier score of P(goal) published |
| 4 | Moment embeddings; phase clusters; chaos head; anticipation evaluation | all of the above | Phase labels validated against hidden truth; retrieval demo |
| 5 | Vision fine-tune (RF-DETR on rendered frames), Argon tagger comparison; Narrator fine-tune on verified lines | 2,000 labelled frames; 20,000 lines | Pitchwatch accuracy table; fine-tuned Narrator deployed |
| 6 | LLM judge calibration against human ratings; Foundry Evaluations gates in CI | 500 rated explanations | Evaluation dashboard |

Compute: roughly 40 GPU-hours total on one Azure NC-series VM or a rented consumer GPU. All training runs are scripts in the repo with fixed seeds.

---

## 7. What a judge sees

A one-slide "AI inventory" in the README and the video:

| Component | Type | Trained by us? | Pretrained source |
|---|---|---|---|
| Behaviour policy | set transformer, ~10M params | yes | — |
| Futures generator | autoregressive sampling from the policy | yes | — |
| xG, xT, pass, win-prob, goal-in-horizon heads | GBT / MLP | yes | — |
| Moment embeddings + phase clusters + chaos head | contrastive encoder | yes | — |
| Player/ball detector | RF-DETR / YOLO26 | fine-tuned | Roboflow |
| Pitch keypoints, tracking, re-ID | CNN / ByteTrack | fine-tuned | Roboflow, SoccerNet |
| Video event tagger | Gemini 4 Argon | no | Google |
| RL football teams (data source) | 11v11 MARL policies | no | DB-Football on gfootball |
| Narrator | fine-tuned small LLM | yes (fine-tune) | Microsoft Phi / OpenAI |
| Tactician, proposer, Panel, judge, Showrunner | frontier LLMs with tools | no | Anthropic / Google / OpenAI via Foundry |
| Voice | speech-to-speech and TTS | no | Google / Microsoft / ElevenLabs |

Eleven models, seven trained or fine-tuned by us, every one with a published evaluation. That is a defensible answer to "where is the AI."

---

## 8. Risks specific to the ML core

| Risk | Mitigation |
|---|---|
| Behaviour policy produces implausible play (players drift, no shape) | Train with a shape-preserving auxiliary loss; keep role targets as a prior; fall back to the Kickoff rules for off-ball movement and learn only on-ball decisions in v1 |
| Rollouts diverge after 15 s | Hand off to the goal-in-horizon head after 15 s; most decisions resolve inside that window |
| gfootball install or policy loading fails | Day-4 spike; fallback is behaviour cloning from Kickoff alone, which is still a learned model, just a less interesting one |
| Fine-tuning data for the Narrator is too small | 20,000 lines is enough for format and voice; fall back to a frontier model with few-shot prompting |
| Judges distrust synthetic-only training | Publish cross-world validation (Kickoff vs gfootball) and the licence-checked real-data fine-tune if permitted |
