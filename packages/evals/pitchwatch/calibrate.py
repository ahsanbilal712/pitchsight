"""Pitch calibration: a homography per frame from the pitch markings.

    python -m evals.pitchwatch.calibrate data/footage/<slug> --shots 61,38 [--key keyframes.json]
    python -m evals.pitchwatch.calibrate data/footage/<slug> --evaluate

No keypoint model: the one the addendum names needs ultralytics, which config/pins.txt excludes (AGPL-3.0). The
markings themselves are the evidence. Each frame's line segments (LSD on a white top-hat of the pitch area) become a
distance transform; the pitch model (every standard line of a 105 x 68 m pitch,
sampled every 0.25 m) is projected through the current camera and the summed, capped distance is minimised.

Camera: the main broadcast camera stands in one place and pans, tilts and zooms, so per clip its position C is fixed
and each frame has four parameters (rotation vector, focal length; principal point at the image centre, square
pixels, no lens distortion). A shot from another camera gets its own keyframe (calib/keyframe_<shot>.json) and its
own position (calib/camera_<shot>.json). C comes from a keyframe: the full camera (rotation, position, focal length) is fitted to
that frame's lines plus a few hand-marked correspondences, starting from a camera behind the near touchline looking at
where the marked points' homography puts the image centre. A new shot starts with a coarse search over pan, tilt and
focal length; each next frame starts from the previous one.

Pitch frame (shared with track B/C, see the shared notes): x in [0, 105] from the left goal line as the main camera
sees it, y in [0, 68] from the far touchline to the near one; right-handed, so z points down (a camera h metres up
has C_z = -h). Output H maps pixels to pitch metres.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

L, WD = 105.0, 68.0
CIRCLE_R, BOX_D, BOX_W, AREA_D, AREA_W, SPOT_D = 9.15, 16.5, 40.32, 5.5, 18.32, 11.0
HALF_LINE = 0.0                # line-centre offset (Laws: 0.06 m); 0 because this fit uses LSD edges, see line_mask
DT_CAP = 25.0                  # px: a model point further than this from any line pixel counts as this far
MIN_VISIBLE = 40               # model points inside the frame needed to trust a fit
OK_RMS_PX = 6.0
F_RANGE = (800.0, 12000.0)     # px: a focal length outside this means the fit has run away


# ---------------------------------------------------------------------------------------------------- pitch model
def _seg(a, b, step=0.25):
    n = max(2, int(np.hypot(b[0] - a[0], b[1] - a[1]) / step) + 1)
    return np.linspace(a, b, n)


def _arc(c, r, a0, a1, step=0.25):
    n = max(2, int(abs(a1 - a0) * r / step) + 1)
    a = np.linspace(a0, a1, n)
    return np.stack([c[0] + r * np.cos(a), c[1] + r * np.sin(a)], axis=1)


def pitch_model(step: float = 0.25, length: float = L, width: float = WD) -> np.ndarray:
    """[N, 2] points along the CENTRE of every painted line of a length x width pitch, metres. Laws dimensions run to
    the outer edge of 12 cm lines and a line belongs to the area it bounds, so each centre sits HALF_LINE inside
    that area (touchlines and goal lines inside the pitch, box lines inside the box, the circle at 9.15 - 0.06)."""
    lx, ly, h = length, width, HALF_LINE
    pts = [_seg((0, h), (lx, h), step), _seg((0, ly - h), (lx, ly - h), step), _seg((h, 0), (h, ly), step),
           _seg((lx - h, 0), (lx - h, ly), step), _seg((lx / 2, 0), (lx / 2, ly), step),
           _arc((lx / 2, ly / 2), CIRCLE_R - h, 0, 2 * np.pi, step)]
    for x0, sgn in ((0.0, 1.0), (lx, -1.0)):
        for d, w in ((BOX_D, BOX_W), (AREA_D, AREA_W)):
            y0, y1 = ly / 2 - w / 2 + h, ly / 2 + w / 2 - h
            xd = x0 + sgn * (d - h)
            pts += [_seg((x0, y0), (xd, y0), step), _seg((xd, y0), (xd, y1), step), _seg((xd, y1), (x0, y1), step)]
        # penalty arc: the part of the 9.15 m circle around the spot outside the box
        spot = (x0 + sgn * SPOT_D, ly / 2)
        r = CIRCLE_R - h
        half = np.arccos(min(1.0, (BOX_D - SPOT_D) / r))
        mid = 0.0 if sgn > 0 else np.pi
        pts.append(_arc(spot, r, mid - half, mid + half, step))
    return np.concatenate(pts)


# ---------------------------------------------------------------------------------------------------- line evidence
def line_mask(bgr: np.ndarray) -> np.ndarray:
    """uint8 mask of pitch-line pixels: line segments (OpenCV LSD) on a white top-hat of the frame, kept when their
    midpoint is on the pitch and they are long, or short but not steep (players' legs and posts are short and
    upright). Far lines are thin and dim; a fixed threshold breaks them into specks, LSD keeps them whole. LSD finds a
    line's two edges, so the fit carries about half a line width of bias (2-3 px); keeping only the paint's centre
    ridge was tried and left too few pixels to follow the camera (23 Oct 2026). calib/<shot>_refined.json (track C,
    demo/refine_calib.py) removes the bias against the paint."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (32, 50, 35), (90, 255, 255))
    pitch = cv2.morphologyEx(green, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    th = cv2.GaussianBlur(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT,
                                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))), (3, 3), 0)
    segs = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD).detect(th)[0]
    out = np.zeros(gray.shape, dtype=np.uint8)
    if segs is None:
        return out
    h, w = gray.shape
    for x1, y1, x2, y2 in np.asarray(segs).reshape(-1, 4):
        length = float(np.hypot(x2 - x1, y2 - y1))
        steep = abs(y2 - y1) > 1.7 * abs(x2 - x1)
        mx, my = int((x1 + x2) / 2), int((y1 + y2) / 2)
        if length < 25 or (steep and length < 60) or not (0 <= mx < w and 0 <= my < h and pitch[my, mx]):
            continue
        cv2.line(out, (int(round(x1)), int(round(y1))), (int(round(x2)), int(round(y2))), 255, 2)
    return out


def distance_map(mask: np.ndarray) -> np.ndarray:
    return np.minimum(cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5), DT_CAP).astype(np.float32)


def sample_dt(dt: np.ndarray, uv: np.ndarray) -> np.ndarray:
    """Bilinear distance at pixel positions; outside the frame -> NaN."""
    h, w = dt.shape
    u, v = uv[:, 0], uv[:, 1]
    inside = (u >= 0) & (u < w - 1) & (v >= 0) & (v < h - 1)
    out = np.full(len(uv), np.nan, dtype=np.float32)
    ui, vi = u[inside], v[inside]
    u0, v0 = np.floor(ui).astype(int), np.floor(vi).astype(int)
    fu, fv = ui - u0, vi - v0
    out[inside] = (dt[v0, u0] * (1 - fu) * (1 - fv) + dt[v0, u0 + 1] * fu * (1 - fv)
                   + dt[v0 + 1, u0] * (1 - fu) * fv + dt[v0 + 1, u0 + 1] * fu * fv)
    return out


# ---------------------------------------------------------------------------------------------------- camera
def K_of(f: float, size: tuple[int, int]) -> np.ndarray:
    return np.array([[f, 0, size[0] / 2], [0, f, size[1] / 2], [0, 0, 1.0]])


def H_pitch_to_img(rvec: np.ndarray, f: float, C: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64))
    t = -R @ C
    return K_of(f, size) @ np.column_stack([R[:, 0], R[:, 1], t])


def project(H: np.ndarray, xy: np.ndarray) -> np.ndarray:
    p = np.column_stack([xy, np.ones(len(xy))]) @ H.T
    with np.errstate(divide="ignore", invalid="ignore"):
        uv = p[:, :2] / p[:, 2:3]
    uv[p[:, 2] <= 0] = np.nan                      # behind the camera
    return uv


def look_at(C: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Rotation vector of an upright camera at C looking at target (world z points down, so image right is
    down x forward; for the main camera behind the near touchline that is pitch +x)."""
    fwd = (target - C) / np.linalg.norm(target - C)
    xc = np.cross(np.array([0.0, 0.0, 1.0]), fwd)
    xc /= np.linalg.norm(xc)
    rvec, _ = cv2.Rodrigues(np.vstack([xc, np.cross(fwd, xc), fwd]))
    return rvec.ravel()


# ---------------------------------------------------------------------------------------------------- fitting
def residuals_H(h8: np.ndarray, model: np.ndarray, dt: np.ndarray) -> np.ndarray:
    H = np.append(h8, 1.0).reshape(3, 3)
    d = sample_dt(dt, project(H, model))
    return np.where(np.isnan(d), 0.0, d)


def refine_free(H0: np.ndarray, model: np.ndarray, dt: np.ndarray) -> np.ndarray:
    h = (H0 / H0[2, 2]).ravel()[:8]
    res = least_squares(residuals_H, h, args=(model, dt), loss="soft_l1", f_scale=3.0, x_scale="jac", max_nfev=200)
    return np.append(res.x, 1.0).reshape(3, 3)


def visible(H: np.ndarray, model: np.ndarray, size, margin: int = 4) -> np.ndarray:
    uv = project(H, model)
    return (uv[:, 0] >= margin) & (uv[:, 0] < size[0] - margin) & (uv[:, 1] >= margin) & (uv[:, 1] < size[1] - margin)


def refine_ptz(p0: np.ndarray, C: np.ndarray, model: np.ndarray, dt: np.ndarray, size, rounds: int = 2) -> np.ndarray:
    """Least-squares on the model points visible at the start of each round; a point that leaves the frame costs
    DT_CAP (otherwise moving every point off-screen would be a perfect, empty fit)."""
    p = np.asarray(p0, dtype=np.float64)
    for _ in range(rounds):
        sub = model[visible(H_pitch_to_img(p[:3], p[3], C, size), model, size)]
        if len(sub) < MIN_VISIBLE:
            return p

        def res(q, sub=sub):
            d = sample_dt(dt, project(H_pitch_to_img(q[:3], q[3], C, size), sub))
            return np.where(np.isnan(d), DT_CAP, d)
        p = least_squares(res, p, loss="soft_l1", f_scale=3.0, x_scale=np.array([0.01, 0.01, 0.01, 50.0]),
                          max_nfev=60).x
    return p


def fit_quality(H: np.ndarray, model: np.ndarray, dt: np.ndarray) -> tuple[float, int]:
    d = sample_dt(dt, project(H, model))
    d = d[~np.isnan(d)]
    if d.size < MIN_VISIBLE:
        return float("inf"), int(d.size)
    near = d[d < DT_CAP]
    return (float(np.sqrt(np.mean(near ** 2))) if near.size else float("inf")), int(d.size)


def search_ptz(C: np.ndarray, model: np.ndarray, mask: np.ndarray, dt: np.ndarray, size,
               ref_rvec: np.ndarray) -> np.ndarray:
    """Coarse pan / tilt / focal search around the keyframe orientation. Score: symmetric chamfer, the mean capped
    distance from visible model points to line pixels plus from line pixels to the projected model, so a view
    that sees almost nothing cannot win."""
    from scipy.spatial import cKDTree

    sub = model[::4]
    ys, xs = np.nonzero(mask[::2, ::2])
    rng = np.random.default_rng(0)
    pick = rng.choice(len(xs), size=min(400, len(xs)), replace=False) if len(xs) else np.array([], dtype=int)
    line_px = np.column_stack([xs[pick] * 2.0, ys[pick] * 2.0])
    R0, _ = cv2.Rodrigues(ref_rvec)
    best, best_p = np.inf, None
    for f in np.geomspace(900, 8000, 22):
        for tilt in np.radians(np.arange(-12, 12.1, 1.0)):
            for pan in np.radians(np.arange(-45, 45.1, 1.0)):
                Rp, _ = cv2.Rodrigues(np.array([0.0, 0.0, pan]))          # about the vertical (camera on a tripod)
                Rt, _ = cv2.Rodrigues(np.array([tilt, 0.0, 0.0]))         # about the camera's x axis
                rv, _ = cv2.Rodrigues(Rt @ R0 @ Rp)
                uv = project(H_pitch_to_img(rv.ravel(), f, C, size), sub)
                vis = ~np.isnan(uv).any(axis=1) & (uv[:, 0] >= 0) & (uv[:, 0] < size[0]) & (uv[:, 1] >= 0) & \
                    (uv[:, 1] < size[1])
                if vis.sum() < 15 or not len(line_px):
                    continue
                a = sample_dt(dt, uv[vis])
                b = np.minimum(cKDTree(uv[vis]).query(line_px)[0], DT_CAP)
                score = float(np.mean(a)) + float(np.mean(b))
                if score < best:
                    best, best_p = score, np.append(rv.ravel(), f)
    return best_p


def refine_camera(C0: np.ndarray, views: list[tuple[np.ndarray, np.ndarray]], model: np.ndarray, size,
                  rounds: int = 3) -> tuple[np.ndarray, list[np.ndarray]]:
    """Joint fit of the camera position (shared) and each view's rotation and focal length. views: [(p0, dt)]."""
    C = np.asarray(C0, dtype=np.float64)
    ps = [np.asarray(p, dtype=np.float64) for p, _ in views]
    for _ in range(rounds):
        subs = [model[visible(H_pitch_to_img(p[:3], p[3], C, size), model, size)] for p in ps]

        def res(x, subs=subs):
            c, out = x[:3], []
            for k, (_, dt) in enumerate(views):
                q = x[3 + 4 * k: 7 + 4 * k]
                d = sample_dt(dt, project(H_pitch_to_img(q[:3], q[3], c, size), subs[k]))
                out.append(np.where(np.isnan(d), DT_CAP, d))
            return np.concatenate(out)
        x0 = np.concatenate([C] + ps)
        scale = np.concatenate([[1.0, 1.0, 1.0]] + [[0.01, 0.01, 0.01, 50.0]] * len(ps))
        x = least_squares(res, x0, loss="soft_l1", f_scale=3.0, x_scale=scale, max_nfev=150).x
        C, ps = x[:3], [x[3 + 4 * k: 7 + 4 * k] for k in range(len(ps))]
    return C, ps


def homography_from_points(points: list[list[float]]) -> np.ndarray:
    """pitch->image H by DLT from [[u, v, x, y], ...] (at least 4, not all collinear)."""
    P = np.asarray(points, dtype=np.float64)
    H, _ = cv2.findHomography(P[:, 2:4], P[:, 0:2], 0)
    return H


# ---------------------------------------------------------------------------------------------------- driver
def read_frame(cap: cv2.VideoCapture, frame: int) -> np.ndarray:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
    ok, bgr = cap.read()
    if not ok:
        raise RuntimeError(f"cannot read frame {frame}")
    return bgr


def camera_from_keyframe(cap, key: dict, model: np.ndarray, point_weight: float = 1.0) -> dict:
    """Fit rotation, position and focal length: first to the marked points alone (plain least squares, several
    starting positions behind the near touchline), then to the keyframe's lines plus the points."""
    bgr = read_frame(cap, key["frame"])
    size = (bgr.shape[1], bgr.shape[0])
    dt = distance_map(line_mask(bgr))
    P = np.asarray(key["points"], dtype=np.float64)
    centre = project(np.linalg.inv(homography_from_points(key["points"])), np.array([[size[0] / 2, size[1] / 2]]))[0]
    scale = np.array([0.01, 0.01, 0.01, 1.0, 1.0, 1.0, 50.0])

    def point_res(x):
        return np.nan_to_num((project(H_pitch_to_img(x[:3], x[6], x[3:6], size), P[:, 2:4]) - P[:, :2]).ravel(),
                             nan=1e4)

    best = None
    if not np.all(np.isfinite(centre)):                   # the image centre is above the horizon
        centre = P[:, 2:4].mean(axis=0)
    starts = [(centre[0], WD + d) for d in (15.0, 30.0, 50.0, 80.0)]          # the main camera: behind the near side
    starts += [(centre[0], -d) for d in (15.0, 30.0, 50.0)]                    # the reverse angle: behind the far side
    starts += [(x, y) for x in (-25.0, L + 25.0) for y in (centre[1], WD + 20.0)]  # behind a goal line, or a corner
    for cx, cy in starts:
        for height in (10.0, 20.0, 35.0):
            C0 = np.array([cx, cy, -height])
            x0 = np.concatenate([look_at(C0, np.array([centre[0], centre[1], 0.0])), C0, [1800.0]])
            r = least_squares(point_res, x0, x_scale=scale, max_nfev=400)
            outside = not (0 <= r.x[3] <= L and 0 <= r.x[4] <= WD)
            if r.x[5] < 0 and outside and (best is None or r.cost < best.cost):    # above the ground, off the pitch
                best = r
    if best is None:
        raise RuntimeError("no camera position above the ground and off the pitch fits the keyframe points")

    def res(x):
        H = H_pitch_to_img(x[:3], x[6], x[3:6], size)
        d = sample_dt(dt, project(H, model))
        return np.concatenate([np.nan_to_num(d, nan=0.0), point_weight * point_res(x) / 3.0])

    x = least_squares(res, best.x, loss="soft_l1", f_scale=3.0, max_nfev=300, x_scale=scale).x
    p = refine_ptz(np.append(x[:3], x[6]), x[3:6], model, dt, size)
    C = x[3:6]
    extra = key.get("refine_frames") or []
    if extra:   # the keyframe alone pins depth weakly: refine C jointly with views at other pans and zooms
        views = [(p, dt)]
        for fr in extra:
            m = line_mask(read_frame(cap, fr))
            d = distance_map(m)
            views.append((refine_ptz(search_ptz(C, model, m, d, size, p[:3]), C, model, d, size), d))
        C, ps = refine_camera(C, views, model, size)
        p = ps[0]
    rms, vis = fit_quality(H_pitch_to_img(p[:3], p[3], C, size), model, dt)
    return {"C": C.tolist(), "rvec": p[:3].tolist(), "f": float(p[3]), "frame": key["frame"], "rms_px": rms,
            "visible": vis, "size": list(size), "refine_frames": extra}


def calibrate_shot(cap, shot: dict, cam: dict, model: np.ndarray, every: int = 1, log=print) -> dict:
    C, size = np.asarray(cam["C"]), tuple(cam["size"])
    frames = {}
    p = None
    for fr in range(shot["frame_start"], shot["frame_end"], every):
        bgr = read_frame(cap, fr) if p is None or every > 1 else _next(cap)
        mask = line_mask(bgr)
        dt = distance_map(mask)
        if p is None:
            p = search_ptz(C, model, mask, dt, size, np.asarray(cam["rvec"]))
            if p is None:                            # no line evidence: start from the keyframe pose
                p = np.append(cam["rvec"], cam["f"])
        p = refine_ptz(p, C, model, dt, size)
        Hp = H_pitch_to_img(p[:3], p[3], C, size)
        rms, vis = fit_quality(Hp, model, dt)
        if not (F_RANGE[0] <= p[3] <= F_RANGE[1]) or rms > 3 * OK_RMS_PX:     # lost: search again from scratch
            found = search_ptz(C, model, mask, dt, size, np.asarray(cam["rvec"]))
            if found is not None:
                p = refine_ptz(found, C, model, dt, size)
                Hp = H_pitch_to_img(p[:3], p[3], C, size)
                rms, vis = fit_quality(Hp, model, dt)
        Hi = np.linalg.inv(Hp)
        Hi /= Hi[2, 2]
        frames[str(fr)] = {"H": np.round(Hi, 9).tolist(), "rms_px": round(rms, 2), "visible": vis,
                           "ok": bool(rms <= OK_RMS_PX), "f": round(float(p[3]), 1)}
        if (fr - shot["frame_start"]) % (every * 250) == 0:
            log(f"shot {shot['id']} frame {fr}: rms {rms:.2f} px, {vis} model points visible, f {p[3]:.0f}")
    return frames


def _next(cap: cv2.VideoCapture) -> np.ndarray:
    ok, bgr = cap.read()
    if not ok:
        raise RuntimeError("clip ended inside a shot")
    return bgr


def pixel_to_pitch(H: list | np.ndarray, uv: tuple[float, float]) -> tuple[float, float]:
    p = np.asarray(H) @ np.array([uv[0], uv[1], 1.0])
    return float(p[0] / p[2]), float(p[1] / p[2])


def evaluate(calib_dir: Path, points: Path | None = None) -> dict:
    """Reprojection error (metres) of the marked points (default <calib_dir>/eval_points.json)."""
    pts = json.loads((points or calib_dir / "eval_points.json").read_text())["points"]
    errs, rows = [], []
    for p in pts:
        cal = json.loads((calib_dir / f"{p['shot']}.json").read_text())["frames"].get(str(p["frame"]))
        if cal is None:
            rows.append({**p, "error_m": None})
            continue
        x, y = pixel_to_pitch(cal["H"], (p["u"], p["v"]))
        e = float(np.hypot(x - p["x"], y - p["y"]))
        errs.append(e)
        rows.append({**p, "pred": [round(x, 3), round(y, 3)], "error_m": round(e, 3)})
    return {"n": len(errs), "mean_m": round(float(np.mean(errs)), 3), "max_m": round(float(np.max(errs)), 3),
            "rms_m": round(float(np.sqrt(np.mean(np.square(errs)))), 3), "threshold_m": 1.5,
            "passed": bool(errs) and max(errs) <= 1.5, "points": rows}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals.pitchwatch.calibrate")
    ap.add_argument("slug_dir", type=Path)
    ap.add_argument("--shots", default="", help="comma list of shot ids (default: the usable shots)")
    ap.add_argument("--evaluate", action="store_true")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None, help="default: <slug_dir>/calib")
    args = ap.parse_args(argv)
    out = args.out or args.slug_dir / "calib"
    if args.evaluate:
        res = evaluate(out, args.slug_dir / "calib" / "eval_points.json")
        (out / "eval.json").write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps({k: res[k] for k in ("n", "mean_m", "max_m", "rms_m", "passed")}))
        return 0 if res["passed"] else 1
    model = pitch_model()
    cap = cv2.VideoCapture(str(args.slug_dir / "clip.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS)
    out.mkdir(parents=True, exist_ok=True)
    cam_path = out / "camera.json"
    if not cam_path.exists():
        cam = camera_from_keyframe(cap, json.loads((args.slug_dir / "calib" / "keyframe.json").read_text()), model)
        cam_path.write_text(json.dumps(cam, indent=1) + "\n")
    cam = json.loads(cam_path.read_text())
    print(f"camera: C = {np.round(cam['C'], 2).tolist()} m, f {cam['f']:.0f} px, keyframe rms {cam['rms_px']:.2f} px")
    shots = json.loads((args.slug_dir / "shots.json").read_text())["shots"]
    wanted = {int(s) for s in args.shots.split(",") if s} or {s["id"] for s in shots if s["usable"]}
    for shot in (s for s in shots if s["id"] in wanted):
        shot_cam = cam
        key_path = args.slug_dir / "calib" / f"keyframe_{shot['id']}.json"
        if key_path.exists():                # a shot from another camera (not the main one) has its own position
            sc_path = out / f"camera_{shot['id']}.json"
            if not sc_path.exists():
                sc = camera_from_keyframe(cap, json.loads(key_path.read_text()), model)
                sc_path.write_text(json.dumps(sc, indent=1) + "\n")
            shot_cam = json.loads(sc_path.read_text())
            print(f"shot {shot['id']}: own camera C = {np.round(shot_cam['C'], 2).tolist()} m, "
                  f"keyframe rms {shot_cam['rms_px']:.2f} px")
        frames = calibrate_shot(cap, shot, shot_cam, model, every=args.every)
        doc = {"slug": args.slug_dir.name, "shot_id": shot["id"], "fps": fps, "image_size": cam["size"],
               "pitch": {"length_m": L, "width_m": WD, "frame": "x from left goal line, y from far touchline"},
               "camera": {"C": cam["C"], "model": "fixed position, rotation + focal length per frame"},
               "frames": frames}
        (out / f"{shot['id']}.json").write_text(json.dumps(doc, separators=(",", ":")) + "\n")
        ok = sum(f["ok"] for f in frames.values())
        print(f"shot {shot['id']}: {len(frames)} frames, {ok} ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
