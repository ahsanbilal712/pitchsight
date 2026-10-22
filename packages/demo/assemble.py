"""Assemble the video from recorded shots and an edit decision list (T-063).

    python packages/demo/assemble.py packages/demo/edit_v1.yaml [--keep]

Reads packages/demo/out/<shot>.webm and <shot>.json (trim marks from the recorder), cuts each clip relative to the
take's play mark, composes split screens and the end card, concatenates, and burns the captions. With
`caption_band: <px>` the picture is scaled (16:9 kept) above a band of that height where the captions sit, so they
never cover the screens (score bug, lower-thirds and studio header fill the frame's edges). Writes the
captions as SubRip (captions_<v>.srt next to the edit list, for upload) and as styled ASS (burned in). Before any
encoding it checks that every number in a caption has an entry in the edit list's `sources`.
ffmpeg is used for cutting, composing and caption burn-in only (no HLS metadata). Prints the duration.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "packages" / "demo" / "out"
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"   # system font; no font files ship in the video
BG = "0x0c1016"
ACCENT = "0xff7a1a"
NUMBER = re.compile(r"[$+\-−]?\d[\d.,]*%?")


class EditError(ValueError):
    pass


def numbers(text: str) -> list[str]:
    return [n.rstrip(".,") for n in NUMBER.findall(text)]


def check_sources(edit: dict) -> None:
    sources = edit.get("sources") or {}
    missing = []
    for clip in edit["clips"]:
        for cap in clip.get("captions", []):
            missing += [(n, cap["text"]) for n in numbers(cap["text"]) if n not in sources]
    if missing:
        raise EditError("caption numbers without a source: " + "; ".join(f"{n!r} in {t!r}" for n, t in missing))


def marks(shot: str) -> dict:
    path = OUT / f"{shot}.json"
    if not path.exists():
        raise EditError(f"{shot}: no {path.relative_to(ROOT)} (record it first, T-062)")
    m = json.loads(path.read_text())
    m["start"] = m.get("play_s", m["ready_s"])
    return m


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:12])} …\n{proc.stderr[-2000:]}")


def encode_args(fps: int) -> list[str]:
    return ["-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-an"]


def cut(shot: str, start: float, dur: float, w: int, h: int, fps: int, dst: Path) -> None:
    m = marks(shot)
    src = OUT / f"{shot}.webm"
    if m["start"] + start + dur > m.get("end_s", 1e9) + 0.05:
        raise EditError(f"{shot}: clip ends {start + dur:.1f} s after play but the take ends at "
                        f"{m['end_s'] - m['start']:.1f} s")
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={BG},"
          f"fps={fps},setsar=1")
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m['start'] + start:.3f}", "-i", str(src), "-t", f"{dur:.3f}",
         "-vf", vf, *encode_args(fps), str(dst)])


def split3(shots: list[str], labels: list[str], start: float, dur: float, w: int, h: int, fps: int,
           dst: Path) -> None:
    """Analyst top-left, casual bottom-left (960x540 each), the phone at full height on the right, labelled."""
    inputs, chains = [], []
    pw = int(round(390 * h / 844))
    boxes = [(960, 540, 60, 0), (960, 540, 60, 540), (pw, h, 1020 + (w - 1020 - pw) // 2, 0)]
    for i, shot in enumerate(shots):
        m = marks(shot)
        inputs += ["-ss", f"{m['start'] + start:.3f}", "-t", f"{dur:.3f}", "-i", str(OUT / f"{shot}.webm")]
        bw, bh, _, _ = boxes[i]
        chains.append(f"[{i}:v]scale={bw}:{bh}:force_original_aspect_ratio=decrease,fps={fps},setsar=1[v{i}]")
    layout = f"color=c={BG}:s={w}x{h}:r={fps}:d={dur:.3f}[bg]"
    over = "[bg]"
    for i, (_, _, x, y) in enumerate(boxes):
        nxt = f"[o{i}]"
        chains.append(f"{over}[v{i}]overlay={x}:{y}:shortest=1{nxt}")
        over = nxt
    text = []
    for i, label in enumerate(labels):
        _, _, x, y = boxes[i]
        text.append(f"drawtext=fontfile='{FONT}':text='{label}':x={x + 16}:y={y + 16}:fontsize=30:"
                    f"fontcolor=white:box=1:boxcolor={ACCENT}@0.9:boxborderw=10")
    graph = ";".join([layout, *chains]) + f";{over}" + ",".join(text) + "[out]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]", "-t", f"{dur:.3f}",
         *encode_args(fps), str(dst)])


def card(title: str, lines: list[str], dur: float, w: int, h: int, fps: int, dst: Path) -> None:
    draws = [f"drawtext=fontfile='{FONT}':text='{title}':x=(w-text_w)/2:y=h/2-170:fontsize=150:fontcolor=white"]
    for i, line in enumerate(lines):
        size, colour = (52, "white") if i == 0 else (30, "0xa9b4c2")
        safe = line.replace(":", r"\:").replace("'", r"\'")
        draws.append(f"drawtext=fontfile='{FONT}':text='{safe}':x=(w-text_w)/2:y=h/2+{40 + 80 * i}:"
                     f"fontsize={size}:fontcolor={colour}")
    draws.append(f"drawbox=x=(iw-360)/2:y=ih/2+10:w=360:h=6:color={ACCENT}:t=fill")
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={BG}:s={w}x{h}:r={fps}:d={dur:.3f}",
         "-vf", ",".join(draws), *encode_args(fps), str(dst)])


def ts(t: float, sep: str = ",") -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d}{sep}{ms % 1000:03d}"


def write_captions(timeline: list[tuple[float, float, str]], srt: Path, ass: Path, w: int, h: int,
                   margin_v: int = 74) -> None:
    srt.write_text("".join(f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n\n" for i, (a, b, text) in enumerate(timeline, 1)))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,40,&H00FFFFFF,&H00FFFFFF,&H00101610,&H00101610,1,0,0,0,100,100,0,0,1,0,0,2,120,120,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def t2(t: float) -> str:
        cs = int(round(t * 100))
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"
    ass.write_text(head + "".join(f"Dialogue: 0,{t2(a)},{t2(b)},Caption,,0,0,0,,{text}\n" for a, b, text in timeline))


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def assemble(edit_path: Path, keep: bool = False) -> Path:
    edit = yaml.safe_load(edit_path.read_text())
    check_sources(edit)
    w, h = edit.get("size", [1920, 1080])
    fps = int(edit.get("fps", 30))
    band = int(edit.get("caption_band", 0))
    out = ROOT / edit["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="assemble_"))
    segments, timeline, at = [], [], 0.0
    for i, clip in enumerate(edit["clips"]):
        seg = tmp / f"seg_{i:02d}.mp4"
        if "card" in clip:
            dur = float(clip["duration"])
            card(clip["title"], clip.get("lines", []), dur, w, h, fps, seg)
        elif clip.get("layout") == "split3":
            dur = float(clip["to"]) - float(clip["from"])
            split3(clip["shots"], clip["labels"], float(clip["from"]), dur, w, h, fps, seg)
        else:
            dur = float(clip["to"]) - float(clip["from"])
            cut(clip["shot"], float(clip["from"]), dur, w, h, fps, seg)
        for cap in clip.get("captions", []):
            if not 0 <= cap["from"] < cap["to"] <= dur + 1e-6:
                raise EditError(f"clip {i}: caption {cap['text']!r} outside the clip (0-{dur:.1f} s)")
            timeline.append((at + cap["from"], at + cap["to"], cap["text"]))
        segments.append(seg)
        at += dur
        print(f"{i:2d} {clip.get('shot') or clip.get('layout') or 'card':<26} {dur:5.1f} s  -> {at:6.1f} s")
    concat = tmp / "concat.txt"
    concat.write_text("".join(f"file '{s}'\n" for s in segments))
    joined = tmp / "joined.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(joined)])
    stem = edit_path.stem.replace("edit_", "captions_")
    srt, ass = edit_path.with_name(f"{stem}.srt"), tmp / f"{stem}.ass"
    vf = f"ass={ass}"
    if band:
        ph = h - band
        pw = int(round(ph * w / h / 2)) * 2
        vf = f"scale={pw}:{ph},pad={w}:{h}:{(w - pw) // 2}:0:color={BG}," + vf
    write_captions(timeline, srt, ass, w, h, margin_v=max(20, band // 2 - 40) if band else 74)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(joined), "-vf", vf, *encode_args(fps),
         "-movflags", "+faststart", str(out)])
    if keep:
        print(f"kept {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("edit", type=Path)
    ap.add_argument("--keep", action="store_true", help="keep the intermediate segments")
    args = ap.parse_args(argv)
    try:
        out = assemble(args.edit if args.edit.is_absolute() else ROOT / args.edit, keep=args.keep)
    except EditError as exc:
        print(f"assemble: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {out.relative_to(ROOT)}: {duration(out):.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
