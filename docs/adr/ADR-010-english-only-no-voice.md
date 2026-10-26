# ADR-010: English only, no voice

## Status

Accepted, 2026-10-21. Amended 2026-10-26: the demo video (v9) has narration (see "Amendment" below). The product
decision is unchanged.

## Context

- This is a user decision in the frozen scope: on-screen text only, English only. Unmute, the Localizer agent and all TTS are removed (`DEMO_MASTERPLAN_50USD.md`, header and section 1). The reasons given are cost, latency and a class of demo failures.
- The audit's minimum viable version (E.3) included a Localizer, ElevenLabs Starter and Unmute voices. This ADR removes them.
- Voice facts from the audit: ElevenLabs Free is non-commercial and requires attribution, so Starter at $6/month is the floor for a public demo (A.1 row 33). Azure Speech neural TTS is $15 per 1M characters (HD $22) with 0.5M free characters per month (row 34). The Gemini Live API has a 1 frame-per-second cap and a 2-minute cap on audio-plus-video sessions, and language counts differ across Google's pages (row 32).
- A Localizer call for six languages adds 2 to 4 s to the serial cue path (audit C.1). Multilingual quality would need a native-speaker rating sheet as proof (C.6).
- The video's voice-over is separate: a team member records it, or captions only (`DEMO_MASTERPLAN_50USD.md` section 7).
- `config/pins.txt` excludes `elevenlabs` and any TTS.

## Decision

There is no Localizer agent, no TTS and no audio in cues. `cue.text` is one English `headline` (at most 60 characters) and one English `body` (at most 280). `schemas/cue.schema.json` states "English only. No audio." `schemas/viewer_profile.schema.json` has no language or voice field; its fields are mode, club, player, metric, `high_contrast` and `show_heatmap`.

The Fact Checker's number-binding and banned-content rules (TECH_PLAN 1.7) are written for English. The README states that the challenge's multi-language bullet is not addressed. The video voice-over, if any, is human or captions and is not a product feature.

## Alternatives rejected

- ElevenLabs voices: the free tier is non-commercial; Starter costs $6/month and adds a licence to track.
- Azure Speech TTS or Voice Live: GA and cheap, but adds latency and more demo failure modes, which the user cut.
- A Localizer agent: 2 to 4 s of serial latency for six languages (audit C.1) and a rating study for fidelity (C.6).
- Gemini Live for commentary: 1 fps cap and a 2-minute session cap.

## Consequences

- Positive: lower latency, no TTS licence, and a simpler cue schema. Fewer places for a take to fail.
- Positive: the Fact Checker has one language to cover.
- Negative: the challenge's multi-language bullet is not addressed, and the README says so. There is no audio description for viewers who cannot read the overlay; the viewer profile offers high contrast only.
- Negative: adding languages later is additive for the schema (optional fields are a minor bump, TECH_PLAN 1.3). It is not additive for the Fact Checker: rule 6 (regex for digits, percent and decimals) and the banned-name list need work per language.
- Negative: the audit's multilingual and voice evidence items (C.6) are not produced.

## Amendment, 2026-10-26: narration in the demo video

- The owner approved narration for video v9 on 26 Oct 2026. It covers the intro and the architecture section only;
  the match clips carry no voice ("no need for the commentary on the broadcasts").
- The voice is Gemini text-to-speech on Vertex AI (`gemini-2.5-pro-tts`, prebuilt voice Charon), called live on
  project ffc-19484 through SpendGuard (role `video_narration`, priced in `config/budgets.yaml`). No new cloud
  resource. A premium macOS voice is the fallback.
- The script is `docs/video/narration_v9.md`. `python -m footage.narration` turns it into one stem per section and
  checks each stem: gemini-3.8-flash transcribes it without the script, and the transcript must match the script word
  for word. No number is spoken.
- This does not change the decision above. It is a property of the video, not of the product: there is still no
  Localizer, no TTS and no audio in cues, `cue.text` stays English text, and `config/pins.txt` adds nothing (the
  google-genai SDK already pinned makes the call). The section 7 line "a team member records it, or captions only"
  is superseded for v9 only.

## Related

- TECH_PLAN 1.3, 1.7 (agents table has no Localizer; Fact Checker rules), 1.12, 1.14.
- ADR-004, ADR-007, ADR-011.
- Schemas: `schemas/cue.schema.json`, `schemas/viewer_profile.schema.json`. Config: `config/pins.txt`.
- Audit: A.1 rows 32 to 34, C.1, C.6, E.3.
