# Video v9 narration

The owner approved narration for video v9 on 26 Oct 2026 (ADR-010, amendment). The voice covers the intro and the
architecture section only. There is no voice over the match clips ("no need for the commentary on the broadcasts").

- Voice: Gemini text-to-speech on Vertex AI (`gemini-2.5-pro-tts`, prebuilt voice below), project ffc-19484, live calls
  through SpendGuard. `python -m footage.narration` reads the sections from this file and writes one WAV and one M4A
  stem per section to `packages/demo/out/narration_v9/` (git-ignored), with `timings.json`.
- Every claim is true of the code: RF-DETR and ByteTrack (`packages/evals/pitchwatch/track.py`); the camera fitted per
  frame to the painted lines with a lens term (`packages/demo/refine_calib.py`); the pass model and the published xG
  model (`packages/footage/v5_lines.py`); the newsroom on Microsoft Agent Framework (`packages/newsroom/graph.py`),
  Gemini through `agent_framework.gemini` (`packages/newsroom/llm.py`); the Fact Checker binding every number
  (`packages/newsroom/executors/factcheck.py`). The script says nothing about training, gives no training figures, and
  names no YOLO and no Azure Foundry.
- No number is spoken, so the narration adds nothing to the on-screen grounding count.

Take of 26 Oct 2026: voice Charon. gemini-3.8-flash transcribed each stem without the script, and each matched it word
for word. The sentence starts come from the stems' pauses (`timings.json`).

| Stem | Length | Sentence starts (s) |
|---|---|---|
| `intro.wav` / `.m4a` | 19.29 s | 0.00 · 5.56 · 7.18 · 9.86 |
| `architecture.wav` / `.m4a` | 51.05 s | 0.29 · 2.17 · 11.74 · 23.17 · 30.64 · 38.49 · 45.75 |
| `short/architecture.wav` / `.m4a` | 27.89 s | 0.29 · 10.54 · 16.61 |

The script follows (each `##` section is one stem). `architecture_short` is the submit cut's version (2:00 or under):
the same claims in fewer words, the same voice and settings, written to `short/architecture.wav` / `.m4a`. The submit
cut plays `intro` and then `architecture_short`.

## intro

Built for Inside the Game: the Premier League and Microsoft developer hackathon. This is Pitchsight. A broadcast
shows you what happened. Pitchsight shows you why it mattered: the pass that was on, the shot worth taking, drawn on
the real pitch, with every number checked.

## architecture

Here is how it works. Computer vision finds every player: RF-DETR detects them, and ByteTrack follows them from frame
to frame. Each frame's camera is calibrated against the painted pitch lines, so every player has a position in metres
and every graphic sits on the grass. A pass model prices each option, and a published Expected Goals model prices
each shot. Then an agent newsroom, built on Microsoft Agent Framework with Google Gemini, takes over. The scout spots
the moment, the tactician weighs the options, and the narrator drafts the line. Before anything goes to air, a fact
checker ties every number to the data.

## architecture_short

RF-DETR detects every player, ByteTrack follows them, and each frame's camera is calibrated to the painted pitch
lines. A pass model and a published Expected Goals model price every option. Then an agent newsroom, built on
Microsoft Agent Framework with Google Gemini, writes the line, and a fact checker ties every number to the data.
