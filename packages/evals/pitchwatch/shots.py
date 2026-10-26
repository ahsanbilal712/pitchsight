"""Shot segmentation with replay detection (FOOTAGE_ADDENDUM §3 step 1, T-103).

    python -m evals.pitchwatch.shots data/footage/<slug>/clip.mp4 [--out data/footage/<slug>]

Samples the clip at 5 fps. A cut is an HSV-histogram correlation below CUT_CORR between samples. A sample is "wide"
when pitch green covers at least WIDE_GREEN of the frame, at least MIN_PLAYERS player-sized blobs are on the pitch,
and no tall blob (a close-up person) is larger than WIDE_BLOB of the frame (tuning history in data/footage/
SHOTS_REVIEW.md). A shot is wide when 70% of its samples are, and is trimmed to its longest run of wide samples (gaps up to 0.6 s
bridged): a fast pan into the stands or the bench changes the colours too gradually to count as a cut.

Replays: Premier League broadcasts keep the score graphic and its running clock through replays, so the graphic
cannot tell live from replay, and a replay is often reframed, so it does not match the live frames it repeats. The
broadcast opens and closes every replay package with a wipe: a full-frame white card with the league lion. A sample
is a wipe when at least WIPE_WHITE of it is bright and unsaturated; consecutive wipe samples are one wipe event, and
events are paired in order (in, out) when the second follows within REPLAY_MAX_S; a lone event is left unpaired (and
listed for review). A shot is a replay when most of it lies inside a pair. Usable = wide, not a replay, >= MIN_WIDE_S.

Other broadcasts (opt-in, defaults unchanged for the Premier League clips): --diff-cut D also cuts where the mean
absolute grey-level change between two samples (64x36 thumbnails, 0-255) exceeds D, which catches a cut between two
green camera angles that the colour histogram misses; --repeats flags a shot as a replay when at least half of its
samples match a sample of an earlier shot (mean absolute grey difference below REPEAT_DIFF after normalising
brightness): a replay without a wipe card that shows the same pictures again; --bug-box x0,y0,x1,y1 (full-frame
pixels of the score graphic's clock) lists, for review, the samples where that box jumps by more than BUG_CUT (mean
grey, 0-255) and is steady again at the next sample: a highlight edit that joins two moments of the same camera view
minutes apart, which neither the colour nor the grey test can see, jumps the clock. It does not cut on its own: a
seconds rollover can change the box as much as a join (measured on barca-madrid-2627), so the reviewer splits with a
"trim" or "drop" override.

Writes <out>/shots.json (every shot) and <out>/shots_review.md (the usable and replay shots with a checkbox each for
the manual review); thumbnails go to <out>/frames/ (git-ignored).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SAMPLE_FPS = 5
W, H = 320, 180
CUT_CORR = 0.55
WIDE_GREEN = 0.42
WIDE_BLOB = 0.025
MIN_PLAYERS = 4
MIN_WIDE_S = 4.0
WIDE_GAP = 3                   # samples (0.6 s) of non-wide bridged inside a wide run
WIPE_WHITE = 0.55             # share of bright (V > 190), unsaturated (S < 50) pixels on a wipe card
REPLAY_MAX_S = 100.0
BUG_CUT = 20.0                 # --bug-box: a jump of the score clock between two samples
REPEAT_DIFF = 12.0             # --repeats: two 64x36 grey thumbnails this close (mean |diff|) show the same picture


def frame_features(bgr: np.ndarray) -> tuple[float, float, int, np.ndarray, np.ndarray, float]:
    small = cv2.resize(bgr, (W, H), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (32, 50, 35), (90, 255, 255))
    green_frac = float(green.mean() / 255)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 16], [0, 180, 0, 256])
    cv2.normalize(hist, hist)
    lower = 255 - green[H // 4:, :]
    lower = cv2.morphologyEx(lower, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(lower, connectivity=8)
    players, blob = 0, 0.0
    if n > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        y, h = stats[1:, cv2.CC_STAT_TOP], stats[1:, cv2.CC_STAT_HEIGHT]
        keep = y > 0
        players = int(((areas >= 8) & (areas <= 700) & keep).sum())
        tall = keep & (h >= 0.3 * lower.shape[0])
        blob = float(areas[tall].max() / (W * H)) if tall.any() else 0.0
    white = float(((hsv[..., 2] > 190) & (hsv[..., 1] < 50)).mean())
    return green_frac, blob, players, hist, small, white


def sample(clip: Path, bug_box: tuple[int, int, int, int] | None = None) -> tuple[list[dict], float, int]:
    cap = cv2.VideoCapture(str(clip))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, round(fps / SAMPLE_FPS))
    samples, prev_hist, idx = [], None, 0
    while cap.grab():
        if idx % step == 0:
            ok, bgr = cap.retrieve()
            if not ok:
                break
            g, b, players, hist, small, white = frame_features(bgr)
            corr = 1.0 if prev_hist is None else float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
            bug = None
            if bug_box:
                x0, y0, x1, y1 = bug_box
                bug = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY).astype(np.float32)
            bug_diff = 0.0 if bug is None or not samples else float(np.abs(bug - samples[-1]["bug"]).mean())
            grey = cv2.resize(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (64, 36), interpolation=cv2.INTER_AREA)
            grey = grey.astype(np.float32)
            diff = 0.0 if not samples else float(np.abs(grey - samples[-1]["grey"]).mean())
            samples.append({"t": idx / fps, "frame": idx, "green": g, "blob": b, "players": players, "corr": corr,
                            "grey": grey, "diff": diff, "bug": bug, "bug_diff": bug_diff,
                            "wide": g >= WIDE_GREEN and b < WIDE_BLOB and players >= MIN_PLAYERS,
                            "img": small, "wipe": white >= WIPE_WHITE})
            prev_hist = hist
        idx += 1
    cap.release()
    return samples, fps, n_frames


def split_shots(samples: list[dict], diff_cut: float | None = None) -> list[list[int]]:
    shots, cur = [], [0]
    for i in range(1, len(samples)):
        if samples[i]["corr"] < CUT_CORR or (diff_cut is not None and samples[i]["diff"] > diff_cut):
            shots.append(cur)
            cur = []
        cur.append(i)
    shots.append(cur)
    return shots


def wipe_events(samples: list[dict]) -> list[tuple[float, float]]:
    """(start, end) seconds of each run of consecutive wipe samples."""
    events, start = [], None
    for k, s in enumerate(samples):
        if s["wipe"] and start is None:
            start = s["t"]
        if not s["wipe"] and start is not None:
            events.append((start, samples[k - 1]["t"] + 1 / SAMPLE_FPS))
            start = None
    if start is not None:
        events.append((start, samples[-1]["t"] + 1 / SAMPLE_FPS))
    return events


def replay_segments(events: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], list[float]]:
    """Pair wipe events in order (in, out) within REPLAY_MAX_S: (replay segments, unpaired event times)."""
    segs, lone, k = [], [], 0
    while k < len(events):
        if k + 1 < len(events) and events[k + 1][0] - events[k][1] <= REPLAY_MAX_S:
            segs.append((events[k][1], events[k + 1][0]))
            k += 2
        else:
            lone.append(events[k][0])
            k += 1
    return segs, lone


def repeats(samples: list[dict], shots: list[list[int]]) -> dict[int, int]:
    """shot index -> the earlier shot it repeats (at least half its samples match one of that shot's samples)."""
    def norm(g):
        return (g - g.mean()) / (g.std() + 1e-6) * 40.0
    out = {}
    for k, sh in enumerate(shots):
        for j in range(k):
            ref = [norm(samples[i]["grey"]) for i in shots[j]]
            hit = sum(1 for i in sh if min(float(np.abs(norm(samples[i]["grey"]) - r).mean()) for r in ref) < REPEAT_DIFF)
            if hit >= 0.5 * len(sh):
                out[k] = j
                break
    return out


def wide_run(samples: list[dict], idx: list[int], gap: int = WIDE_GAP) -> tuple[int, int]:
    """First and last sample index of the longest run of wide samples in a shot, bridging gaps of up to `gap`."""
    best, cur, last_wide = (idx[0], idx[0]), None, None
    for i in idx:
        if samples[i]["wide"]:
            if cur is None or i - last_wide > gap + 1:
                cur = i
            last_wide = i
            if last_wide - cur > best[1] - best[0]:
                best = (cur, last_wide)
    return best


def segment(clip: Path, out_dir: Path, thumbs: bool = True, diff_cut: float | None = None,
            find_repeats: bool = False, bug_box: tuple[int, int, int, int] | None = None) -> dict:
    samples, fps, n_frames = sample(clip, bug_box)
    shots = split_shots(samples, diff_cut)
    repeat_of = repeats(samples, shots) if find_repeats else {}
    events = wipe_events(samples)
    segs, lone = replay_segments(events)
    frames_dir = out_dir / "frames"
    out = []
    for k, sh in enumerate(shots):
        start, end = samples[sh[0]]["t"], samples[sh[-1]]["t"] + 1 / SAMPLE_FPS
        wide_share = sum(samples[i]["wide"] for i in sh) / len(sh)
        inside = sum(1 for i in sh if samples[i]["wipe"] or any(a <= samples[i]["t"] < b for a, b in segs))
        replay = inside / len(sh) > 0.5 or k in repeat_of
        seg = next(((a, b) for a, b in segs if a < end and start < b), None)
        kind = "wide" if wide_share >= 0.7 else "other"
        rec = {"id": k, "start": round(start, 2), "end": round(end, 2), "duration": round(end - start, 2),
               "frame_start": samples[sh[0]]["frame"], "frame_end": samples[sh[-1]]["frame"] + round(fps / SAMPLE_FPS),
               "kind": kind, "wide_share": round(wide_share, 2), "replay": replay,
               "replay_share": round(inside / len(sh), 2), "repeat_of": repeat_of.get(k),
               "replay_segment": [round(seg[0], 2), round(seg[1], 2)] if replay and seg else None,
               "green_mean": round(float(np.mean([samples[i]["green"] for i in sh])), 3)}
        if kind == "wide":            # a pan off the pitch inside one shot (no cut) ends the usable part
            a, b = wide_run(samples, sh)
            if (a, b) != (sh[0], sh[-1]):
                rec["trimmed_from"] = [rec["start"], rec["end"]]
                rec["start"], rec["end"] = round(samples[a]["t"], 2), round(samples[b]["t"] + 1 / SAMPLE_FPS, 2)
                rec["duration"] = round(rec["end"] - rec["start"], 2)
                rec["frame_start"] = samples[a]["frame"]
                rec["frame_end"] = samples[b]["frame"] + round(fps / SAMPLE_FPS)
        rec["usable"] = kind == "wide" and not replay and rec["duration"] >= MIN_WIDE_S
        if thumbs and (rec["usable"] or (replay and kind == "wide")):
            frames_dir.mkdir(parents=True, exist_ok=True)
            tag = "replay" if replay else "shot"
            cv2.imwrite(str(frames_dir / f"{tag}_{k:03d}_{int(start) // 60:02d}m{int(start) % 60:02d}s.jpg"),
                        samples[sh[len(sh) // 2]]["img"])
        out.append(rec)
    apply_overrides(out, out_dir / "shots_overrides.json")
    duration = n_frames / fps
    usable = [s for s in out if s["usable"]]
    summary = {"clip": clip.name, "fps": round(fps, 2), "duration_s": round(duration, 1), "n_shots": len(out),
               "n_usable_wide": len(usable), "n_replays": sum(s["replay"] for s in out),
               "replay_wide_dropped": sum(1 for s in out if s["replay"] and s["kind"] == "wide"
                                          and s["duration"] >= MIN_WIDE_S),
               "usable_wide_s": round(sum(s["duration"] for s in usable), 1),
               "usable_wide_share": round(sum(s["duration"] for s in usable) / duration, 3),
               "longest_wide_s": max((s["duration"] for s in usable), default=0),
               "wipes": [round(a, 2) for a, _ in events],
               "bug_jumps": [round(samples[i]["t"], 2) for i in range(1, len(samples) - 1)
                             if samples[i]["bug_diff"] > BUG_CUT and samples[i + 1]["bug_diff"] < BUG_CUT / 4
                             and samples[i]["diff"] < (diff_cut or 1e9)] if bug_box else None,
               "replay_segments": [[round(a, 2), round(b, 2)] for a, b in segs],
               "unpaired_wipes": [round(t, 2) for t in lone],
               "params": {"sample_fps": SAMPLE_FPS, "cut_corr": CUT_CORR, "wide_green": WIDE_GREEN,
                          "wide_blob": WIDE_BLOB, "min_players": MIN_PLAYERS, "min_wide_s": MIN_WIDE_S,
                          "wipe_white": WIPE_WHITE, "replay_max_s": REPLAY_MAX_S, "diff_cut": diff_cut,
                          "repeats": find_repeats, "repeat_diff": REPEAT_DIFF if find_repeats else None,
                          "bug_box": list(bug_box) if bug_box else None, "bug_cut": BUG_CUT if bug_box else None}}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "shots.json").write_text(json.dumps({"summary": summary, "shots": out}, indent=1) + "\n")
    (out_dir / "shots_review.md").write_text(review_md(out_dir.name, summary, out))
    return summary


def apply_overrides(shots: list[dict], path: Path) -> None:
    """Reviewed corrections: {"live": [[start_s, end_s], ...], "replay": [...], "trim": {shot_id: [start_s, end_s]},
    "fps": clip fps, "drop": {shot_id: reason}}. drop marks a shot unusable after review (e.g. a hidden join leaves
    two pieces shorter than MIN_WIDE_S); trim narrows a shot to a reviewed wide window (a cut the detector missed); a shot whose middle
    falls in a live/replay range takes that label (and is usable again if it is wide and long enough). Highlight packages use the same
    wipe between segments as around replays, so their wipe pairing needs this review."""
    if not path.exists():
        return
    ov = json.loads(path.read_text())
    fps = ov.get("fps")
    for sid, (a, b) in (ov.get("trim") or {}).items():    # a reviewed wide window inside a mixed shot
        s = next(x for x in shots if x["id"] == int(sid))
        s.update({"start": a, "end": b, "duration": round(b - a, 2), "frame_start": round(a * fps),
                  "frame_end": round(b * fps), "kind": "wide", "override": "trim"})
    for s in shots:
        mid = (s["start"] + s["end"]) / 2
        for label in ("live", "replay"):
            if any(a <= mid < b for a, b in ov.get(label, [])):
                s["replay"] = label == "replay"
                s["override"] = label
        s["usable"] = s["kind"] == "wide" and not s["replay"] and s["duration"] >= MIN_WIDE_S
    for sid, why in (ov.get("drop") or {}).items():
        s = next(x for x in shots if x["id"] == int(sid))
        s.update({"usable": False, "override": f"drop: {why}"})


def _mmss(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def review_md(slug: str, summary: dict, shots: list[dict]) -> str:
    lines = [f"# Shot review: {slug}", "",
             f"Generated by `python -m evals.pitchwatch.shots`. {summary['n_usable_wide']} usable wide shots "
             f"({summary['usable_wide_s']:.0f} s), {summary['replay_wide_dropped']} wide replays dropped. Tick a box "
             "when the thumbnail in frames/ confirms the label; write a note when it does not.", "",
             f"Replay segments (between paired wipes): "
             f"{', '.join(f'{_mmss(a)}-{_mmss(b)}' for a, b in summary['replay_segments']) or 'none'}. "
             f"Unpaired wipes (check by hand: a replay may start or end there): "
             f"{', '.join(_mmss(t) for t in summary['unpaired_wipes']) or 'none'}.", "",
             "| ok | shot | start | end | s | label | evidence |", "|---|---|---|---|---|---|---|"]
    for s in shots:
        if s["usable"] or (s["replay"] and s["kind"] == "wide" and s["duration"] >= MIN_WIDE_S):
            label = "replay" if s["replay"] else "wide"
            ev = (f"inside replay {_mmss(s['replay_segment'][0])}-{_mmss(s['replay_segment'][1])}"
                  if s["replay"] and s["replay_segment"] else f"wide {s['wide_share']:.0%}")
            lines.append(f"| [ ] | {s['id']} | {_mmss(s['start'])} | {_mmss(s['end'])} | {s['duration']:.0f} | "
                         f"{label} | {ev} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.pitchwatch.shots")
    ap.add_argument("clip", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="default: the clip's folder")
    ap.add_argument("--no-thumbs", action="store_true")
    ap.add_argument("--diff-cut", type=float, default=None, help="also cut on mean grey change (0-255), e.g. 30")
    ap.add_argument("--repeats", action="store_true", help="flag shots that repeat an earlier shot's pictures")
    ap.add_argument("--bug-box", default=None, help="x0,y0,x1,y1 of the score clock (full-frame px): cut on its jumps")
    args = ap.parse_args(argv)
    box = tuple(int(v) for v in args.bug_box.split(",")) if args.bug_box else None
    print(json.dumps(segment(args.clip, args.out or args.clip.parent, thumbs=not args.no_thumbs,
                             diff_cut=args.diff_cut, find_repeats=args.repeats, bug_box=box), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
