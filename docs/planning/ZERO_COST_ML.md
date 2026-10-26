# WHYLINE at $0 Training Spend — Deep Research

Date: 21 October 2026. Constraint from the user: **no money spent on training.** This document works out how to keep genuine machine learning at the centre of WHYLINE while spending nothing on training, and close to nothing on inference. Every claim is labelled VERIFIED (read in a primary source or measured on this Mac today) or INFERRED (secondary source or reasoning).

---

## 1. The short answer

Training costs money only when it happens on rented GPUs. Three free sources cover everything the ML core needs:

1. **Your laptop's GPU.** Measured today: the 5M-parameter behaviour policy trains at 2,474 samples per second on this Mac's GPU, so one epoch over 6 million samples takes 0.7 hours. Ten epochs is one night. Cost: electricity. (VERIFIED, measured)
2. **Pretrained weights that already exist.** Vision detectors (RF-DETR, Apache-2.0), the RL football teams (GRF_MARL, Apache-2.0), open text-to-speech (Kokoro, Apache-2.0), and the frontier LLMs' free tiers (Gemini 3.8 Flash and 3.8 Live are free; Argon is not). (VERIFIED)
3. **A pre-recorded Google Research Football tracking dataset.** 3,000 simulated games as CSV, 23 rows per timestep (22 players plus ball: position, velocity, role, possession), published with an AAMAS 2025 demo paper. The gfootball engine does not need to be installed to train on it. (VERIFIED, repo and Drive listing)

What changes versus the audit's minimum viable version: nothing in ambition. Training moves from Azure GPUs to the laptop and free quotas; LLM calls move to free tiers with a local model as fallback; the fine-tuned narrator is dropped or done with a free local LoRA. The demo can run on Azure's $200 trial credit or on free tiers.

---

## 2. The unlock: pre-recorded GRF tracking data

**What it is.** `github.com/Dtradke/grf_tracking_data`, companion to "Simulating Tracking Data to Advance Sports Analytics Research" (Radke & Tilbury, AAMAS 2025, arXiv 2503.19809). The README describes 3,000 pre-recorded simulated games from the Google Research Football environment, in subsets from `tiny_set` (12 games, ~100 MB) to `full_set` (3,000 games, ~25 GB), three games per CSV. Schema: `GAME_ID, TIMESTEP, TEAM_0_SCORE, TEAM_1_SCORE, PLAYER_ID, TEAM_ID, PLAYER_ROLE, LOCATION_X/Y/Z, VELOCITY_X/Y/Z, ON_BALL`. Player IDs 0–10 and 100–110, ball = −1. Includes `make_events.py` (rule-based event extraction), `expected_goals.py` (logistic xG), a Spearman pitch-control implementation and a demo. (VERIFIED, README)

**What I saw in the Drive folder.** 50 CSV files, `gfootball_results_games_0-2.csv` to `games_147-149.csv`, ~25 MB each, so 150 games (~1.25 GB) are directly visible; the README's downloader script fetches the larger subsets. (VERIFIED, folder listing)

**Why it matters.** 150 games × 3,000 timesteps × 22 players is roughly 10 million player-timesteps and about 450,000 on-ball decisions, which is more than enough to train the on-ball decision policy. The gfootball engine, which failed to install here three times, is no longer on the training path at all.

**Caveats.** (1) The repository has no LICENSE file; the arXiv listing shows a CC0 badge, which covers the paper, not necessarily the data. Email the authors before shipping; cite them regardless. (INFERRED risk) (2) The README does not say which agents played the games; the demo paper does not either. The play is most likely the built-in AI at some difficulty (INFERRED), which is less "emergent" than the RL teams but perfectly adequate for a behaviour prior. (3) Frame rate is not stated; gfootball's engine is 10 steps per second and 3,000 steps per match, so 10 Hz (INFERRED from the gfootball docs verified in the audit).

---

## 3. Free compute, verified where possible

| Source | What you get | Status | Good for |
|---|---|---|---|
| **This Mac (Apple Silicon, 11 cores, 18 GB)** | PyTorch 2.14 with MPS; 5M-param policy: 2,474 train samples/s, 20 ms inference per batch of 200 | VERIFIED, measured | All policy and head training; rollouts for the demo |
| **Hugging Face ZeroGPU** | Free accounts: 5 minutes of GPU per day on half an RTX Pro 6000; can host 2 ZeroGPU Spaces; Gradio only | VERIFIED, docs | Hosting a free public demo of one model call, not training |
| **Modal** | "$30 / month free credits" on Starter; T4 ≈ $0.59/h, A10 ≈ $1.10/h, A100 ≈ $2.50/h | VERIFIED, pricing page (card requirement not stated) | ~50 T4-hours or ~12 A100-hours per month at $0 |
| **Kaggle notebooks** | ~30 GPU-hours/week on T4 ×2 or P100; 12-hour sessions | INFERRED (community figure; docs page did not render) | Overnight training runs with a free A100-class fallback |
| **Google Colab free** | T4 when available; ~12-hour cap; GPU not guaranteed at peak hours | INFERRED (third-party guides) | Ad-hoc experiments |
| **Lightning AI free** | Reported ~80 GPU-hours/month on spot T4/A10, no card; older listing says 22 h | INFERRED (pricing page returned 403) | Possible second source; verify in-app |
| **Azure free account** | $200 credit for 30 days; always-free: Functions 1M requests, Cosmos DB 1,000 RU/s + 25 GB, Speech 0.5M neural characters/month; card required, "won't be charged" | VERIFIED, Azure page | Hosting the demo, not training (GPU quota needs pay-as-you-go) |
| **GitHub Models** | **Retired 30 July 2026** | VERIFIED, GitHub docs | Nothing; remove from any plan |

Training budget at $0, measured and estimated:

| Model | Where | Time | Confidence |
|---|---|---|---|
| On-ball decision policy, 5M params, 10 epochs over ~6M samples | Mac GPU | ~7 h (one night) | VERIFIED rate, INFERRED epochs |
| Outcome heads (xG, pass completion, win prob, goal-in-8 s) | Mac CPU, gradient-boosted trees | minutes | INFERRED |
| Moment embeddings (autoencoder) + chaos head | Mac GPU/CPU | < 1 h | INFERRED |
| RF-DETR Nano fine-tune on 2,000 rendered frames (optional) | Mac GPU or Kaggle | 1–3 h | INFERRED |
| Narrator LoRA on a 4B local model (optional, replaces the paid Foundry fine-tune) | Mac GPU with MLX or Unsloth | 2–4 h | INFERRED |

---

## 4. Free inference, verified where possible

### LLMs

| Provider | Free terms | Status | Use in WHYLINE |
|---|---|---|---|
| **Gemini 3.8 Flash** | Free tier: input and output "free of charge"; data used to improve products; **rate limits not published**, shown per project in AI Studio | VERIFIED (pricing page); limits INFERRED unknown | Tactician, Proposer, Localizer; video tagging of rendered clips |
| **Gemini 3.8 Live** | Free tier for input and output | VERIFIED | Barge-in voice Q&A (Unmute) |
| **Gemma 4** | Free input/output/caching | VERIFIED | Volume lines if limits bite |
| **Gemini 4 Argon** | **No free tier** | VERIFIED | Do not plan on it |
| **Groq** | Developer plan shown: 30 RPM, 1K RPD, 8K TPM for gpt-oss-120b/20b and Qwen3.8-27b; free-plan numbers not on the public page | VERIFIED (Developer figures); free INFERRED | Fast cheap pundits if a free plan exists for your account |
| **OpenRouter `:free` models** | 20 RPM; **50 requests/day** with no purchase history, 1,000/day after $10 lifetime purchase | VERIFIED (docs) | Backup only; 50/day is too small for a match |
| **Cerebras** | Redirected to a marketing page; not verified | Unknown | — |
| **Local: Qwen3-8B / Phi-4-mini / gpt-oss-20b via Ollama or Foundry Local** | Free; Foundry Local catalogue lists GPT OSS, Qwen, DeepSeek, Mistral, Phi, Whisper; macOS Apple Silicon supported; OpenAI-compatible server | VERIFIED (Foundry Local README); speeds INFERRED (~30–60 tok/s for 4–8B on this class of Mac) | Narrator for high-volume lines; offline judge demo; Foundry Local is also a Microsoft hero technology |
| **Azure Foundry on the $200 trial** | Tier 0 quota exposes gpt-4.1-mini and gpt-5-mini; no GPT-6, no Claude on trial | VERIFIED (audit) | Agent Framework demo path on Azure within the credit |

A match's language workload (roughly 150 moments × 3 calls × 6 languages batched into one Localizer call each) is about 600 requests. That is fine for Gemini's free tier if its per-day limit is in the hundreds or above (unknown until you look in AI Studio), and it is comfortably within a local model's capacity. The design rule that makes this safe: **cache every LLM output for the golden match and run the demo from the cache.** Live calls are for the judges' own matches, throttled.

### Voice

| Option | Free terms | Languages | Status |
|---|---|---|---|
| **Gemini 3.8 Flash TTS** (`gemini-3.8-flash-tts`, `-lite-tts`) | Free input and output on the free tier; streaming PCM supported | "over 130 languages" (Flash), "over 100" (Lite); 30 studio voices plus a library | VERIFIED (pricing and speech pages) |
| **Kokoro** (open weights, Apache-2.0, 82M params) | Free, runs locally; MPS on Mac | English (US/UK), Spanish, French, Hindi, Italian, Japanese, Brazilian Portuguese, Mandarin; **no Arabic, no Swahili** | VERIFIED (repo) |
| **Azure Speech** | 0.5M neural characters/month free, always | 100+ locales incl. Arabic and Swahili | VERIFIED (Azure free page, audit) |
| ElevenLabs Free | Non-commercial, attribution required | — | VERIFIED; **do not use** for the public demo |

Recommendation: Gemini Flash TTS for everything in development; Azure Speech's free half-million characters for the final demo's six languages (a full match of commentary is roughly 60–100k characters per language); Kokoro as the fully offline fallback for the judge's laptop.

### Vision

| Option | Free terms | Status |
|---|---|---|
| RF-DETR Nano/Small/Medium, COCO-pretrained, Apache-2.0, auto-download | Free | VERIFIED (audit) |
| Roboflow football detector and pitch keypoints, CC BY 4.0 datasets; 10 free hosted credits/month | Free with account | VERIFIED (audit) |
| Gemini 3.8 Flash agentic video on rendered clips | Free tier | VERIFIED (pricing) |

### Hosting the demo at $0

- Replay mode on a laptop: free.
- Public web demo: Azure Static Web Apps free plan for the three front-ends; Azure Functions free grant for the API; Cosmos DB free tier for the blackboard; Container Apps free grant (180k vCPU-seconds/month) for the newsroom; Web PubSub free tier for up to 20 concurrent viewers, which is enough for judges. All VERIFIED in the audit. The $200 trial credit covers anything above the grants for 30 days; after that, scale-to-zero keeps it near $0.
- Alternative public demo of a single model call: a Hugging Face ZeroGPU Space (free, Gradio).

---

## 5. The zero-cost ML stack, component by component

| Component | In `ML_CORE.md` | At $0 |
|---|---|---|
| Behaviour policy (on-ball decisions) | Train on A10 in Azure | Train on the Mac GPU overnight from `grf_tracking_data` (150–3,000 games) plus the Kickoff engine's own matches. Same architecture, same evaluation. |
| Futures generator | GPU rollouts on Container Apps | Decision-only rollouts on the Mac GPU (0.3 s per 200 futures measured) for the recorded demo; for the live cloud demo, precompute counterfactuals for the golden season and serve from Cosmos; live judge matches get CPU rollouts (1.2 s) with n=100 |
| Outcome heads | Trained in cloud | Trained on CPU in minutes |
| Moment embeddings, chaos head | Trained in cloud | Trained locally in under an hour |
| Vision detectors | Fine-tune on A10 | Use COCO-pretrained RF-DETR as-is on the 3D render (players are "person" class); fine-tune on the Mac only if accuracy is poor |
| Video tagger | Gemini 4 Argon | Gemini 3.8 Flash (free) |
| Tactician, Proposer, Panel | Claude Opus 5.5 / Argon via Foundry | Gemini 3.8 Flash free tier, with Groq's free plan or a local Qwen3-8B as fallback; on Azure, gpt-4.1-mini within the trial credit |
| Narrator, Localizer | GPT-6 Luna via Foundry | Local Qwen3-8B via Foundry Local (free, offline, Microsoft-branded) or Gemini 3.8 Flash |
| Fine-tuned narrator | gpt-4.1-mini SFT (~$45) | Drop, or a free LoRA on Qwen3-4B with MLX on the Mac if a shipped artefact is wanted |
| Voice | ElevenLabs Starter | Gemini Flash TTS (free) in dev; Azure Speech free tier for the final six-language demo; Kokoro offline |
| RL teams as data source | gfootball + GRF_MARL policies | Not needed for training; the pre-recorded dataset replaces them. gfootball branching stays an optional Docker experiment |
| Evaluation | Foundry Evaluations | Own evaluators (free) plus Foundry Evaluations within the trial credit for the judge-visible table |

Net training spend: **$0.** Net inference spend for development and the demo: **$0 to ~$20**, the upper end only if Gemini free limits are exhausted and you choose to top up rather than fall back to the local model.

---

## 6. What the laptop-first path costs you, honestly

- **Time instead of money.** Training runs overnight rather than in an hour. Plan the policy run for the end of week one so it is ready at the start of week two.
- **Free-tier uncertainty.** Gemini does not publish free limits; Groq's free plan figures are not on the public page; OpenRouter's 50/day is too small. The cache-first design and the local model fallback remove the dependency; check your actual limits in AI Studio on day one.
- **Weaker frontier reasoning for the Tactician.** Gemini 3.8 Flash is capable but not Opus or Argon class. For the demo this is invisible; for the Panel's debate quality it is a small loss. The $200 Azure credit or a $10 Gemini top-up buys frontier calls for the recorded demo if wanted, which is inference, not training.
- **No Azure GPU.** The cloud path serves precomputed counterfactuals and CPU rollouts. Judges running a live match get n=100 futures in about a second on CPU, which is acceptable.
- **Dataset licence.** `grf_tracking_data` has no LICENSE file. One email to the authors resolves it; until then, treat it as "cite and ask."

---

## 7. Day-one setup, all free

```bash
# 1. Data: the tiny set first (12 games, ~100 MB), then more
git clone https://github.com/Dtradke/grf_tracking_data
python3 grf_tracking_data/scripts/download_game_data.py tiny_set

# 2. Local training environment (already verified on this Mac: torch 2.14.1, MPS available)
python3 -m venv .venv && . .venv/bin/activate
pip install torch numpy pandas scikit-learn lightgbm

# 3. Local LLM for high-volume lines (Microsoft hero tech, free, offline)
#    Foundry Local CLI from github.com/microsoft/Foundry-Local, then:
foundry model run qwen2.5-7b-instruct      # or a Phi / gpt-oss variant from `foundry model list`

# 4. Gemini free key from AI Studio; check your project's rate limits there before relying on them
export GOOGLE_API_KEY=...

# 5. Local TTS fallback
pip install "kokoro>=0.9.4" soundfile && brew install espeak-ng

# 6. Azure free account ($200 / 30 days) only when the cloud demo is needed
```

---

## 8. Verified versus inferred, for the record

**VERIFIED today:** Mac training and inference rates; `grf_tracking_data` README schema, subsets and the 50-file Drive listing; HF ZeroGPU quotas; Modal free credits and GPU prices; Gemini free-tier model list (3.8 Flash, 3.8 Live, Flash TTS free; Argon not); Gemini TTS languages and streaming; Kokoro licence, size and languages; Azure free account terms; GitHub Models retirement; OpenRouter `:free` limits; Groq Developer-plan limits; Foundry Local catalogue families and platforms.

**INFERRED or unverified:** Kaggle weekly quota (community figure); Colab free limits (third-party); Lightning AI free hours (pricing page blocked); Groq and Cerebras free-plan numbers; Gemini free-tier RPM/RPD (deliberately unpublished by Google); which agents generated the GRF dataset and its frame rate; local LLM token rates on this Mac; `grf_tracking_data` licence.
