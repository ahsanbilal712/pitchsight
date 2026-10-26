"""Video narration: Gemini text-to-speech stems, one per script section (amendment). v9: the intro and the
architecture section; v10: the decision voice-over on the match clips, one stem per cue.

    python -m footage.narration [--script docs/video/narration_v10.md] [--voice NAME] [--dry-run]
    # -> packages/demo/out/narration_vN/ (N from the script's name; default narration_v9.md)
    python -m footage.narration --script docs/video/narration_v10.md --segments packages/demo/voice_v10.yaml
    # -> narration_v10/segments/<segment>.m4a: the cues of one segment in one stem, at their offsets

The sections are the `## <name>` paragraphs of the script; a `Style: ...` line above them replaces STYLE, and a
`Max pause: <s> s` line cuts every pause in a take to that length (the model's own take is kept as <section>.take.wav,
and the check below hears the cut stem). Each is one
live call to MODEL on Vertex AI (the project in .env, ffc-19484) through SpendGuard (role video_narration, match id
video_vN). The model returns
24 kHz 16-bit mono PCM, saved as <section>.wav and converted to <section>.m4a (AAC). timings.json gives each stem's
duration and its sentence starts. CHECK (gemini-3.8-flash, SpendGuard) transcribes the whole stem without the script,
which must match it word for word ("verbatim"; a number is compared as it is spoken, 0.06 as "zero point zero six");
the stem is then cut at its pauses (ffmpeg silencedetect) and each piece's words counted, so each sentence starts where
its first word falls, and each number where its first spoken word falls (`numbers`, for the voice grounding). Media
stay in the git-ignored out/ folder.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from footage.clips import ROOT

MODEL = "gemini-2.5-pro-tts"
VOICE = "Charon"                    # a prebuilt Gemini voice: informative, even
SCRIPT = ROOT / "docs" / "video" / "narration_v9.md"
RATE = 24000
CHECK = "gemini-3.8-flash"           # transcribes each stem: the words, and roughly when each sentence starts
STYLE = ("Read this as the narrator of a short technical product film: natural, confident and warm, at an even, "
         "unhurried pace, with a short pause between sentences:\n\n")


def version(script: Path = SCRIPT) -> str:
    return re.search(r"_(v\d+)$", Path(script).stem).group(1)                  # narration_v10.md -> v10


def out_dir(script: Path = SCRIPT) -> Path:
    return ROOT / "packages" / "demo" / "out" / f"narration_{version(script)}"


def sections(path: Path = SCRIPT) -> dict[str, str]:
    text = Path(path).read_text()
    return {name: " ".join(body.split()) for name, body in
            re.findall(r"^## (\w+)\n\n(.*?)(?=\n## |\Z)", text, re.S | re.M)}


def style(path: Path = SCRIPT) -> str:
    m = re.search(r"^Style: (.+)$", Path(path).read_text(), re.M)
    return m.group(1).strip() + "\n\n" if m else STYLE


def max_pause(path: Path = SCRIPT) -> float | None:
    """`Max pause: <s> s` in the script: every silence inside a take is cut to this (the lead-in to 0.05 s)."""
    m = re.search(r"^Max pause: ([\d.]+) s$", Path(path).read_text(), re.M)
    return float(m.group(1)) if m else None


def cap_pauses(take: Path, wav: Path, cap: float | None) -> None:
    """The stem from the take: as it is, or with each pause longer than `cap` cut to `cap` (ffmpeg silenceremove,
    -40 dB); nothing spoken is touched."""
    if cap is None:
        shutil.copyfile(take, wav)
        return
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(take), "-af",
                    f"silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB:stop_periods=-1:"
                    f"stop_duration={cap}:stop_silence={cap}:stop_threshold=-40dB", "-ar", str(RATE), "-ac", "1",
                    "-c:a", "pcm_s16le", str(wav)], check=True)


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def speak(client, guard, text: str, voice: str, narration_id: str = "video_v9", how: str = STYLE) -> tuple[bytes, dict]:
    from google.genai import types

    guard.check(narration_id)
    config = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))))
    t0 = time.perf_counter()
    resp = client.models.generate_content(model=MODEL, contents=how + text, config=config)
    latency = int((time.perf_counter() - t0) * 1000)
    u = resp.usage_metadata
    tin, tout = int(u.prompt_token_count or 0), int(u.candidates_token_count or 0)
    row = guard.record("video_narration", MODEL, tin, tout, narration_id, "precompute")
    pcm = next(p.inline_data.data for p in resp.candidates[0].content.parts if p.inline_data)
    return pcm, {"tokens_in": tin, "tokens_out": tout, "cost_usd": row["cost_usd"], "latency_ms": latency}


def pauses(wav: Path, min_s: float = 0.25) -> list[tuple[float, float]]:
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(wav), "-af", f"silencedetect=n=-40dB:d={min_s}",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    return list(zip(starts, ends, strict=False))


SPELLING = {"meters": "metres", "meter": "metre",       # the transcriber's spelling, not a different word
            "pitchsite": "pitchsight", "pitchside": "pitchsight",   # the product's name heard as a homophone
            "oh": "zero", "o": "zero", "nought": "zero"}    # 0.06 read as "nought point oh six"
NUM = re.compile(r"\d*\.\d+%?|\d+%?")                  # ".20" is how a transcriber may write 0.20
ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
       "seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def spell(tok: str) -> str:
    """A number as it is spoken: 0.06 -> zero point zero six, 66% -> sixty six percent (0-99 and decimals)."""
    pct = tok.endswith("%")
    whole, _, frac = tok.rstrip("%").partition(".")
    n = int(whole or 0)
    out = ONES[n] if n < 20 else TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10]) if n < 100 else whole
    if frac:
        out += " point " + " ".join(ONES[int(d)] for d in frac)
    return out + (" percent" if pct else "")


def words(text: str) -> list[str]:
    text = re.sub(r"\bx[ -]?g\b|\bex[ -]?gee\b", " xg ", text.lower().replace("per cent", "percent"))   # "xG", "x G"
    text = NUM.sub(lambda m: f" {spell(m.group())} ", text)
    ws = [SPELLING.get(w, w) for w in re.findall(r"[a-z0-9]+", text.replace("-", " "))]
    return [w for i, w in enumerate(ws) if not (w == "zero" and ws[i + 1:i + 2] == ["point"])]   # "point zero six"


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


def _hear(client, guard, audio: bytes, prompt: str, narration_id: str = "video_v9") -> tuple[str, float]:
    from google.genai import types

    schema = {"type": "object", "required": ["transcript"], "properties": {"transcript": {"type": "string"}}}
    cost = 0.0
    for _ in range(3):                                      # an empty reply is asked again
        guard.check(narration_id)
        resp = client.models.generate_content(
            model=CHECK, contents=[types.Part(inline_data=types.Blob(data=audio, mime_type="audio/wav")), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_json_schema=schema,
                                               temperature=0, thinking_config=types.ThinkingConfig(thinking_budget=0)))
        u = resp.usage_metadata
        cost += guard.record("video_narration_check", CHECK, int(u.prompt_token_count or 0),
                             int(u.candidates_token_count or 0), narration_id, "precompute")["cost_usd"]
        if resp.text:
            return json.loads(resp.text)["transcript"], cost
    raise RuntimeError(f"{CHECK} returned no transcript three times")


def check(client, guard, wav: Path, text: str, narration_id: str = "video_v9") -> dict:
    """The whole stem transcribed by CHECK without the script: it must be the script word for word (when it is not, a
    second transcription decides, and the first is kept as "first_transcript"). Then each speech
    chunk is transcribed with the script as context and its words aligned to the script (difflib); a sentence starts
    in the chunk its first word was heard in, at its share of that chunk by word position (exact at a pause,
    interpolated inside a chunk)."""
    ask = "Transcribe this narration verbatim, every word, nothing else."
    heard, cost = _hear(client, guard, wav.read_bytes(), ask, narration_id)
    script = words(text)
    verbatim, misheard = words(heard) == script, None
    if not verbatim:                                         # a second, independent transcription: a slip in the take
        misheard = heard                                     # comes back again, a mishearing does not
        heard, c = _hear(client, guard, wav.read_bytes(), ask, narration_id)
        verbatim, cost = words(heard) == script, cost + c
    spans, heard_at = chunks(wav), []                      # (word, chunk index, position in the chunk, its length)
    for j, (a, b) in enumerate(spans):
        part, c = _hear(client, guard, _slice(wav, a, b), "This clip is one piece of a narration whose script is:\n"
                        f"{text}\nTranscribe exactly the words spoken in this clip, nothing else.", narration_id)
        ws = words(part)
        heard_at += [(w, j, i, len(ws)) for i, w in enumerate(ws)]
        cost += c
    from difflib import SequenceMatcher

    where: dict[int, tuple[int, int, int]] = {}          # script word -> its heard place (a misheard word is skipped)
    for blk in SequenceMatcher(None, script, [h[0] for h in heard_at], autojunk=False).get_matching_blocks():
        for i in range(blk.size):
            where[blk.a + i] = heard_at[blk.b + i][1:]
    def at(k: int) -> float | None:                         # script word k's heard time (None: not matched)
        if k not in where:
            return None
        j, i, n = where[k]
        a, b = spans[j]
        return round(a + i / n * (b - a), 2)

    starts, k = [], 0
    for sent in sentences(text):
        starts.append(at(k))                                 # None: its first word was not matched
        k += len(words(sent))
    numbers = []                                             # each number: its first and last spoken word
    for m in NUM.finditer(text):
        k, n = len(words(text[:m.start()])), len(words(m.group()))
        numbers.append({"text": m.group(), "start_s": at(k), "last_word_s": at(k + n - 1)})
    with wave.open(str(wav)) as w:
        dur = w.getnframes() / w.getframerate()
    return {"duration_s": round(dur, 2), "verbatim": verbatim, "transcript": heard, "first_transcript": misheard,
            "sentences": [{"start_s": t, "text": x} for t, x in zip(starts, sentences(text), strict=False)], "numbers": numbers,
            "check_cost_usd": round(cost + 0.0, 6)}


def run(voice: str = VOICE, dry_run: bool = False, redo: bool = False, script: Path = SCRIPT,
        only: list[str] | None = None) -> dict:
    script = Path(script)
    secs, how, base, nid = sections(script), style(script), out_dir(script), f"video_{version(script)}"
    cap = max_pause(script)
    if dry_run:
        return {k: {"words": len(v.split()), "sentences": len(sentences(v))} for k, v in secs.items()}
    from api.spend import SpendGuard
    from footage.tag import sdk_client

    guard, client = SpendGuard(), sdk_client()
    base.mkdir(parents=True, exist_ok=True)
    out = {"model": MODEL, "voice": voice, "script": str(script.relative_to(ROOT)), "sample_rate": RATE,
           "sections": {}}
    before = json.loads((base / "timings.json").read_text())["sections"] if (base / "timings.json").exists() else {}
    for name, text in secs.items():
        if only and name not in only:
            continue
        folder = base / "short" if name.endswith("_short") else base     # the submit cut's version of a section
        folder.mkdir(parents=True, exist_ok=True)
        stem = name.removesuffix("_short")
        wav, take = folder / f"{stem}.wav", folder / f"{stem}.take.wav"     # the stem, and the model's own take
        kept = before.get(name)
        if wav.exists() and not take.exists() and kept and kept.get("max_pause_s") is None:
            shutil.copyfile(wav, take)                       # a stem from before the cap is its take
        if not (redo or only) and take.exists() and kept and kept.get("text") == text and kept.get("voice") == voice and \
                kept.get("style", STYLE) == how:
            usage = {k: kept[k] for k in ("tokens_in", "tokens_out", "cost_usd", "latency_ms")}   # the same take
        else:
            pcm, usage = speak(client, guard, text, voice, nid, how)
            with wave.open(str(take), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm)
        cap_pauses(take, wav, cap)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "aac", "-b:a", "192k",
                        str(folder / f"{stem}.m4a")], check=True)
        rel = wav.parent.relative_to(base)
        out["sections"][name] = {"wav": str(rel / f"{stem}.wav"), "m4a": str(rel / f"{stem}.m4a"), "text": text,
                                 "voice": voice, **({"style": how} if how != STYLE else {}),
                                 **({"max_pause_s": cap} if cap is not None else {}),
                                 **check(client, guard, wav, text, nid), **usage}
        r = out["sections"][name]
        print(f"{name}: {r['duration_s']} s, verbatim {r['verbatim']}, ${usage['cost_usd'] + r['check_cost_usd']:.4f}")
        (base / "timings.json").write_text(json.dumps({**out, "sections": {**before, **out["sections"]}}, indent=1)
                                          + "\n")                  # after each stem: a paid take is never lost
    return out


def build_segments(plan: Path, script: Path) -> dict:
    """One stem per in-action segment (a placement file such as packages/demo/voice_v10.yaml): its cues' stems at
    their offsets, the stem starting at the first cue; segments.json gives each cue's start in its segment's stem."""
    import numpy as np
    import yaml

    base = out_dir(script)
    folder = base / "segments"
    folder.mkdir(parents=True, exist_ok=True)
    timings = json.loads((base / "timings.json").read_text())["sections"]
    out = {}
    for seg, spec in yaml.safe_load(Path(plan).read_text())["segments"].items():
        cues = sorted(spec["cues"].items(), key=lambda kv: kv[1])
        first = cues[0][1]
        parts = []
        for cue, at in cues:
            with wave.open(str(base / timings[cue]["wav"])) as w:
                parts.append((int(round((at - first) * RATE)), np.frombuffer(w.readframes(w.getnframes()), np.int16)))
        pcm = np.zeros(max(i + len(x) for i, x in parts), np.int32)
        for i, x in parts:
            pcm[i:i + len(x)] += x
        wav = folder / f"{seg}.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(np.clip(pcm, -32768, 32767).astype(np.int16).tobytes())
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-c:a", "aac", "-b:a", "192k",
                        str(folder / f"{seg}.m4a")], check=True)
        out[seg] = {"m4a": f"segments/{seg}.m4a", "clip": spec["clip"], "occurrence": spec.get("occurrence", 1),
                    "starts_at": first, "duration_s": round(len(pcm) / RATE, 2),
                    "cues": [{"cue": c, "at_s": round(at - first, 2)} for c, at in cues]}
    (folder / "segments.json").write_text(json.dumps({"plan": str(Path(plan).resolve().relative_to(ROOT)),
                                                      "segments": out}, indent=1) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--script", type=Path, default=SCRIPT, help="docs/video/narration_vN.md")
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--redo", action="store_true", help="a new take even where the stem's script is unchanged")
    ap.add_argument("--only", nargs="+", help="a new take of these sections only")
    ap.add_argument("--segments", type=Path, help="a placement file: mix the stems into one per segment")
    args = ap.parse_args(argv)
    script = args.script if args.script.is_absolute() else ROOT / args.script
    if args.segments:
        print(json.dumps(build_segments(ROOT / args.segments, script), indent=1))
        return 0
    print(json.dumps(run(args.voice, args.dry_run, args.redo, script, args.only), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "packages"))
    raise SystemExit(main())
