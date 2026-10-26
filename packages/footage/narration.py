"""Video v9 narration: Gemini text-to-speech stems for the intro and the architecture section (ADR-010, amendment).

    python -m footage.narration [--voice NAME] [--dry-run]    # -> packages/demo/out/narration_v9/

The sections are the `## <name>` paragraphs of docs/video/narration_v9.md. Each is one live call to MODEL on Vertex AI
(the project in .env, ffc-19484) through SpendGuard (role video_narration, match id NARRATION_ID). The model returns
24 kHz 16-bit mono PCM, saved as <section>.wav and converted to <section>.m4a (AAC). timings.json gives each stem's
duration and its sentence starts. CHECK (gemini-3.8-flash, SpendGuard) transcribes the whole stem without the script,
which must match it word for word ("verbatim"); the stem is then cut at its pauses (ffmpeg silencedetect) and each
piece's words counted, so each sentence starts where its first word falls. Media stay in the git-ignored out/ folder.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

from footage.clips import ROOT

MODEL = "gemini-2.5-pro-tts"
VOICE = "Charon"                    # a prebuilt Gemini voice: informative, even
NARRATION_ID = "video_v9"
SCRIPT = ROOT / "docs" / "video" / "narration_v9.md"
OUT = ROOT / "packages" / "demo" / "out" / "narration_v9"
RATE = 24000
CHECK = "gemini-3.8-flash"           # transcribes each stem: the words, and roughly when each sentence starts
STYLE = ("Read this as the narrator of a short technical product film: natural, confident and warm, at an even, "
         "unhurried pace, with a short pause between sentences:\n\n")


def sections(path: Path = SCRIPT) -> dict[str, str]:
    text = path.read_text()
    return {name: " ".join(body.split()) for name, body in
            re.findall(r"^## (\w+)\n\n(.*?)(?=\n## |\Z)", text, re.S | re.M)}


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def speak(client, guard, text: str, voice: str) -> tuple[bytes, dict]:
    from google.genai import types

    guard.check(NARRATION_ID)
    config = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
    t0 = time.perf_counter()
    resp = client.models.generate_content(model=MODEL, contents=STYLE + text, config=config)
    latency = int((time.perf_counter() - t0) * 1000)
    u = resp.usage_metadata
    tin, tout = int(u.prompt_token_count or 0), int(u.candidates_token_count or 0)
    row = guard.record("video_narration", MODEL, tin, tout, NARRATION_ID, "precompute")
    pcm = next(p.inline_data.data for p in resp.candidates[0].content.parts if p.inline_data)
    return pcm, {"tokens_in": tin, "tokens_out": tout, "cost_usd": row["cost_usd"], "latency_ms": latency}


def pauses(wav: Path, min_s: float = 0.25) -> list[tuple[float, float]]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", f"silencedetect=n=-40dB:d={min_s}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends))


SPELLING = {"meters": "metres", "meter": "metre"}       # the transcriber's spelling, not a different word


def words(text: str) -> list[str]:
    return [SPELLING.get(w, w) for w in re.findall(r"[a-z0-9]+", text.lower().replace("-", " "))]


def chunks(wav: Path) -> list[tuple[float, float]]:
    """The speech between the pauses."""
    with wave.open(str(wav)) as w:
        dur = w.getnframes() / w.getframerate()
    out, t = [], 0.0
    for a, b in pauses(wav):
        if a - t > 0.05:
            out.append((t, a))
        t = b
    if dur - t > 0.05:
        out.append((t, dur))
    return out


def _slice(wav: Path, a: float, b: float) -> bytes:
    import io

    with wave.open(str(wav)) as w:
        rate = w.getframerate()
        w.setpos(int(a * rate))
        pcm = w.readframes(int((b - a) * rate))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as o:
            o.setnchannels(w.getnchannels())
            o.setsampwidth(w.getsampwidth())
            o.setframerate(rate)
            o.writeframes(pcm)
    return buf.getvalue()


def _hear(client, guard, audio: bytes, prompt: str) -> tuple[str, float]:
    from google.genai import types

    schema = {"type": "object", "required": ["transcript"], "properties": {"transcript": {"type": "string"}}}
    guard.check(NARRATION_ID)
    resp = client.models.generate_content(
        model=CHECK, contents=[types.Part(inline_data=types.Blob(data=audio, mime_type="audio/wav")), prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema,
                                           temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=0)))
    u = resp.usage_metadata
    row = guard.record("video_narration_check", CHECK, int(u.prompt_token_count or 0),
                       int(u.candidates_token_count or 0), NARRATION_ID, "precompute")
    return json.loads(resp.text)["transcript"], row["cost_usd"]


def check(client, guard, wav: Path, text: str) -> dict:
    """The whole stem transcribed by CHECK without the script: it must be the script word for word. Then each speech
    chunk is transcribed with the script as context, only to count its words; a sentence starts in the chunk its first
    word is in, at its share of that chunk by word position (exact at a pause, interpolated inside a chunk)."""
    heard, cost = _hear(client, guard, wav.read_bytes(), "Transcribe this narration verbatim, every word, nothing else.")
    script = words(text)
    verbatim = words(heard) == script
    spans, counts = chunks(wav), []
    for a, b in spans:
        part, c = _hear(client, guard, _slice(wav, a, b), "This clip is one piece of a narration whose script is:\n"
                        f"{text}\nTranscribe exactly the words spoken in this clip, nothing else.")
        counts.append(len(words(part)))
        cost += c
    aligned = sum(counts) == len(script)
    starts, k = [], 0
    for sent in sentences(text):
        if not aligned:
            starts.append(None)
            continue
        j, first = 0, 0
        while first + counts[j] <= k:
            first += counts[j]
            j += 1
        a, b = spans[j]
        starts.append(round(a + (k - first) / counts[j] * (b - a), 2))
        k += len(words(sent))
    with wave.open(str(wav)) as w:
        dur = w.getnframes() / w.getframerate()
    return {"duration_s": round(dur, 2), "verbatim": verbatim, "transcript": heard,
            "sentences": [{"start_s": t, "text": x} for t, x in zip(starts, sentences(text))],
            "check_cost_usd": round(cost + 0.0, 6)}


def run(voice: str = VOICE, dry_run: bool = False, redo: bool = False) -> dict:
    secs = sections()
    if dry_run:
        return {k: {"words": len(v.split()), "sentences": len(sentences(v))} for k, v in secs.items()}
    from api.spend import SpendGuard
    from footage.tag import sdk_client

    guard, client = SpendGuard(), sdk_client()
    OUT.mkdir(parents=True, exist_ok=True)
    out = {"model": MODEL, "voice": voice, "script": str(SCRIPT.relative_to(ROOT)), "sample_rate": RATE,
           "sections": {}}
    before = json.loads((OUT / "timings.json").read_text())["sections"] if (OUT / "timings.json").exists() else {}
    for name, text in secs.items():
        wav = OUT / f"{name}.wav"
        kept = before.get(name)
        if not redo and wav.exists() and kept and kept.get("text") == text and kept.get("voice") == voice:
            usage = {k: kept[k] for k in ("tokens_in", "tokens_out", "cost_usd", "latency_ms")}   # the same take
        else:
            pcm, usage = speak(client, guard, text, voice)
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "aac", "-b:a", "192k",
                        str(OUT / f"{name}.m4a")], check=True)
        out["sections"][name] = {"wav": wav.name, "m4a": f"{name}.m4a", "text": text, "voice": voice,
                                 **check(client, guard, wav, text), **usage}
        r = out["sections"][name]
        print(f"{name}: {r['duration_s']} s, verbatim {r['verbatim']}, ${usage['cost_usd'] + r['check_cost_usd']:.4f}")
    (OUT / "timings.json").write_text(json.dumps(out, indent=1) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true", help="a new take even where the stem's script is unchanged")
    args = ap.parse_args(argv)
    print(json.dumps(run(args.voice, args.dry_run, args.redo), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
