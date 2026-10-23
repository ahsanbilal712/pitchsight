"""Pitch geometry on a real broadcast frame (FOOTAGE_ADDENDUM §3 step 7, T-108).

A `Camera` maps pitch metres (event-schema convention: x 0..105 along the pitch, y 0..68 with y = 0 the touchline
nearest the main camera, so y = 68 is the far touchline at the top of the picture) to frame pixels: a homography H
followed by one radial lens term k1 about the picture centre. Broadcast wide shots bend straight lines by several
pixels at the edges of the picture, so H alone cannot hold the far touchline and the penalty box together to 2 px.
Track A's calibration (T-104) publishes H per frame; until then, and for checking, `fit_from_lines` fits a camera
from a handful of hand-picked landmarks and refines it against the frame's own pitch-line pixels.

`drift_px` is the acceptance measure of T-108: the offset, in pixels along the line's normal, from the projected
pitch-model lines to the centre of the painted marking, over the model lines visible in the frame (median and 95th
percentile). Samples with no marking within DETECT_PX (a player standing on the line, a faint stretch) say nothing
about drift; they are left out and reported as coverage.
numpy, scipy and PIL only (no OpenCV in the pins).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.optimize import least_squares

PITCH_L, PITCH_W = 105.0, 68.0
CIRCLE_R = 9.15
DETECT_PX = 8.0
MIN_COVERAGE = 0.5     # drift is pooled over lines found along at least half their visible length
LINE_W = 0.12          # Laws of the Game: lines at most 12 cm wide, part of the areas they bound


# ---------------------------------------------------------------------------------------------- camera
def dlt(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Homography mapping src (N x 2) to dst (N x 2), N >= 4, normalised DLT."""
    def norm(p):
        c = p.mean(0)
        s = np.sqrt(2) / np.mean(np.linalg.norm(p - c, axis=1))
        return np.array([[s, 0, -s * c[0]], [0, s, -s * c[1]], [0, 0, 1]])
    ts, td = norm(src), norm(dst)
    s = (ts @ np.c_[src, np.ones(len(src))].T).T
    d = (td @ np.c_[dst, np.ones(len(dst))].T).T
    rows = []
    for (x, y, _), (u, v, _) in zip(s, d, strict=True):
        rows.append([-x, -y, -1, 0, 0, 0, u * x, u * y, u])
        rows.append([0, 0, 0, -x, -y, -1, v * x, v * y, v])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    h = vt[-1].reshape(3, 3)
    h = np.linalg.inv(td) @ h @ ts
    return h / h[2, 2]


def _apply(h: np.ndarray, pts) -> np.ndarray:
    p = np.asarray(pts, dtype=float).reshape(-1, 2)
    q = (h @ np.c_[p, np.ones(len(p))].T).T
    return q[:, :2] / q[:, 2:3]


@dataclass
class Camera:
    """Pitch metres -> pixels: u = H p, then u' = c + (u - c)(1 + k1 r^2) with r = |u - c| / (width / 2)."""
    h: np.ndarray
    k1: float = 0.0
    size: tuple[int, int] = (1920, 1080)          # width, height

    @property
    def centre(self) -> np.ndarray:
        return np.array(self.size, float) / 2

    def project(self, pts) -> np.ndarray:
        u = _apply(self.h, pts)
        d = (u - self.centre) / (self.size[0] / 2)
        return self.centre + (u - self.centre) * (1 + self.k1 * np.sum(d * d, axis=1, keepdims=True))

    def unproject(self, px) -> np.ndarray:
        """Pixels -> pitch metres (undistort by fixed-point iteration, then H^-1)."""
        v = np.asarray(px, dtype=float).reshape(-1, 2)
        u = v.copy()
        for _ in range(8):
            d = (u - self.centre) / (self.size[0] / 2)
            u = self.centre + (v - self.centre) / (1 + self.k1 * np.sum(d * d, axis=1, keepdims=True))
        return _apply(np.linalg.inv(self.h), u)

    def to_json(self) -> dict:
        return {"h": self.h.tolist(), "k1": self.k1, "size": list(self.size)}

    @classmethod
    def from_json(cls, doc: dict) -> Camera:
        return cls(np.asarray(doc["h"], float), float(doc.get("k1", 0.0)), tuple(doc.get("size", (1920, 1080))))


# Pitchwatch (track A, T-104) maps pixels to pitch metres with y from the FAR touchline; this module's y runs from the
# near one (event schema, T-107 moment files). The flip is its own inverse.
FLIP_Y = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, PITCH_W], [0.0, 0.0, 1.0]])


def from_pitchwatch(calib: dict, frame: int, lens: bool = True) -> Camera:
    """The camera for one frame of a Pitchwatch `calib/<shot>.json`, or of the nearest frame whose fit is trusted.
    `H` maps pixels to pitch metres (far-touchline y), no lens term; a refined file (demo.refine_calib) adds `k1` and
    `H_k1`, the homography that applies to pixels once the lens term is taken out, used when `lens`."""
    frames = {int(k): v for k, v in calib["frames"].items() if v.get("ok")}
    if not frames:
        raise ValueError(f"calib shot {calib.get('shot_id')}: no trusted frame")
    entry = frames[min(frames, key=lambda f: abs(f - frame))]
    with_k1 = lens and "H_k1" in entry
    h = np.linalg.inv(np.asarray(entry["H_k1" if with_k1 else "H"], float)) @ FLIP_Y
    return Camera(h / h[2, 2], float(entry["k1"]) if with_k1 else 0.0, tuple(calib.get("image_size", (1920, 1080))))


def to_pitchwatch(cam: Camera) -> list[list[float]]:
    """The camera's homography as Pitchwatch's pixels -> pitch metres (far-touchline y); the lens term is not in it."""
    h = FLIP_Y @ np.linalg.inv(cam.h)
    return (h / h[2, 2]).tolist()


def board_top(cam: Camera, width: int, gap_px: int = 4) -> np.ndarray:
    """Per column, the first row below the far touchline as `cam` sees it: the boards stand on that line and the
    faint paint under them cannot be told from their edge, so the far touchline and everything above it are left out
    (gap_px below the projected line)."""
    edge = cam.project(np.c_[np.linspace(-30, 135, 400), np.full(400, PITCH_W)])
    order = np.argsort(edge[:, 0])
    rows = np.interp(np.arange(width), edge[order, 0], edge[order, 1])
    return np.clip(np.ceil(rows) + gap_px, 0, None).astype(int)


def as_camera(cam) -> Camera:
    return cam if isinstance(cam, Camera) else Camera(np.asarray(cam, float))


# ---------------------------------------------------------------------------------------------- pitch model
def model_lines(step: float = 0.25) -> dict[str, np.ndarray]:
    """Sample points (metres) along the centre of each standard pitch marking, by name. The Laws measure the
    pitch, the areas and the circles to the outer edge of 12 cm lines, so each line's centre sits LINE_W / 2 inside
    the area it bounds: about 2 px at a broadcast camera's zoom on the penalty box."""
    def seg(a, b):
        n = max(2, int(np.hypot(b[0] - a[0], b[1] - a[1]) / step))
        return np.linspace(a, b, n)
    e = LINE_W / 2
    r = CIRCLE_R - e
    t = np.linspace(0, 2 * np.pi, int(2 * np.pi * r / step))
    lines = {
        "touchline_near": seg((0, e), (PITCH_L, e)), "touchline_far": seg((0, PITCH_W - e), (PITCH_L, PITCH_W - e)),
        "goal_line_left": seg((e, 0), (e, PITCH_W)), "goal_line_right": seg((PITCH_L - e, 0), (PITCH_L - e, PITCH_W)),
        "halfway": seg((PITCH_L / 2, 0), (PITCH_L / 2, PITCH_W)),
        "centre_circle": np.c_[PITCH_L / 2 + r * np.cos(t), PITCH_W / 2 + r * np.sin(t)],
    }
    for name, x0, d in (("left", 0.0, 1), ("right", PITCH_L, -1)):
        for box, depth, half in (("penalty", 16.5, 20.16), ("goal", 5.5, 9.16)):
            x1, hw = x0 + d * (depth - e), half - e
            lines[f"{box}_box_{name}"] = np.vstack([seg((x0, 34 - hw), (x1, 34 - hw)),
                                                    seg((x1, 34 - hw), (x1, 34 + hw)),
                                                    seg((x1, 34 + hw), (x0, 34 + hw))])
        arc = np.c_[x0 + d * 11.0 + r * np.cos(t), 34 + r * np.sin(t)]
        lines[f"penalty_arc_{name}"] = arc[d * (arc[:, 0] - (x0 + d * (16.5 + e))) > 0]
    return lines


# ---------------------------------------------------------------------------------------------- line pixels
def _grass(f: np.ndarray) -> np.ndarray:
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    return (g > r + 5) & (g > b + 20)


def line_response(frame: np.ndarray, top=0) -> np.ndarray:
    """Per-pixel pitch-marking response: a white top-hat on the blue channel (grass has almost none) inside the
    grass region, 0 above `top` (stands and advertising boards): a row, or one row per column when the boards slope
    across the picture."""
    f = frame.astype(float)
    grass = ndi.binary_closing(ndi.binary_opening(_grass(f), iterations=2), iterations=8)
    resp = ndi.white_tophat(ndi.gaussian_filter(f[..., 2], 0.7), size=(9, 9)) * ndi.binary_dilation(grass, iterations=6)
    resp[np.arange(len(resp))[:, None] < np.broadcast_to(np.asarray(top), resp.shape[1:])[None, :]] = 0
    return resp


def occluders(frame: np.ndarray) -> np.ndarray:
    """Pixels where something stands on the pitch (players, referee, ball): not grass and not white line paint,
    grown by DETECT_PX so a sample near a player is not measured against his kit."""
    f = frame.astype(float)
    paint = (f.min(2) > 120) & ((f.max(2) - f.min(2)) < 70)
    occ = ndi.binary_opening(~_grass(f) & ~paint, iterations=1)
    return ndi.binary_dilation(occ, iterations=int(DETECT_PX))


def _normals(px: np.ndarray) -> np.ndarray:
    tang = np.gradient(px, axis=0)
    tang /= np.linalg.norm(tang, axis=1, keepdims=True) + 1e-9
    return np.c_[-tang[:, 1], tang[:, 0]]


def _targets(cam: Camera, resp, pts, step=0.25, min_peak=18.0, occ=None, search=DETECT_PX):
    """For each projected sample: the centre of the marking along the normal within +-search pixels (sub-sample
    peak), or NaN where none is found or a player stands on it; the normals; and which samples are in the frame."""
    px = cam.project(pts)
    nrm = _normals(px)
    ks = np.arange(-search, search + step / 2, step)
    tgt = np.full_like(px, np.nan)
    inside = ((px[:, 0] > search + 2) & (px[:, 0] < resp.shape[1] - search - 2) &
              (px[:, 1] > search + 2) & (px[:, 1] < resp.shape[0] - search - 2))
    idx = np.nonzero(inside)[0]
    if occ is not None:
        idx = idx[~occ[px[idx, 1].astype(int), px[idx, 0].astype(int)]]
    if not len(idx):
        return tgt, nrm, inside
    q = px[idx, None, :] + ks[None, :, None] * nrm[idx, None, :]           # samples x profile x 2
    prof = ndi.map_coordinates(resp, [q[..., 1].ravel(), q[..., 0].ravel()], order=1).reshape(len(idx), len(ks))
    j = np.argmax(prof, axis=1)
    rows = np.arange(len(idx))
    good = (prof[rows, j] >= min_peak) & (j > 0) & (j < len(ks) - 1)
    jj = np.clip(j, 1, len(ks) - 2)
    a, b, c = prof[rows, jj - 1], prof[rows, jj], prof[rows, jj + 1]
    den = a - 2 * b + c
    frac = np.where(den != 0, 0.5 * (a - c) / np.where(den != 0, den, 1), 0.0)
    off = ks[j] + frac * step
    tgt[idx[good]] = px[idx[good]] + off[good, None] * nrm[idx[good]]
    return tgt, nrm, inside


def line_offsets(cam, frame: np.ndarray, names: list[str] | None = None, top=0, min_peak: float = 18.0
                 ) -> dict[str, np.ndarray]:
    """Per named line, the signed offset in pixels along the normal from each projected sample inside the frame to
    the marking's centre (NaN where not found or occluded)."""
    cam = as_camera(cam)
    resp, occ = line_response(frame, top=top), occluders(frame)
    lines = model_lines(step=0.2)
    out = {}
    for name in names or list(lines):
        tgt, nrm, inside = _targets(cam, resp, lines[name], min_peak=min_peak, occ=occ)
        px = cam.project(lines[name])
        out[name] = np.sum((tgt - px) * nrm, axis=1)[inside]
    return out


@dataclass
class Drift:
    median: float
    p95: float
    samples: int
    coverage: float
    lines: list[str] = field(default_factory=list)            # the lines pooled into median and p95
    per_line: dict[str, dict] = field(default_factory=dict)


def drift_px(cam, frame: np.ndarray, names: list[str] | None = None, top=0, min_coverage: float = MIN_COVERAGE
             ) -> Drift:
    """Median and 95th percentile of |offset| from the projected model lines to the markings' centres, over samples
    where the marking is found, pooled over the lines found along at least `min_coverage` of their visible length
    (a faint stretch of touchline under the boards, found at a few points, measures the detector, not the camera).
    Every line's own figures are kept in per_line, the left-out ones included."""
    offs = line_offsets(cam, frame, names, top=top)

    def stats(off):
        found = ~np.isnan(off)
        if not found.any():
            return {"median": float("inf"), "p95": float("inf"), "samples": 0, "coverage": 0.0}
        a = np.abs(off[found])
        return {"median": round(float(np.median(a)), 2), "p95": round(float(np.percentile(a, 95)), 2),
                "samples": int(found.sum()), "coverage": round(float(found.mean()), 2)}
    per_line = {n: stats(o) for n, o in offs.items() if len(o)}
    pooled = [n for n, v in per_line.items() if v["coverage"] >= min_coverage]
    every = stats(np.concatenate([offs[n] for n in pooled]) if pooled else np.array([]))
    return Drift(every["median"], every["p95"], every["samples"], every["coverage"], pooled, per_line)


@dataclass
class Fit:
    camera: Camera
    drift: Drift
    lines: list[str]


def fit_from_lines(frame: np.ndarray, pitch_pts, pixel_pts, names: list[str], top=0,
                   search=(24, 16, 8, 8, 8, 8), min_peak: float = 10.0, lens: bool | float = True,
                   seed: Camera | None = None, prior=None) -> Fit:
    """DLT from hand landmarks (pitch metres <-> pixels), then refine H (8 parameters) and k1 ICP-style: find the
    centre of each named marking along the normal of its projection, fit the camera to those centres (robust loss,
    so players and noise do not pull the fit), repeat. The search window narrows over the iterations, so a line the
    landmarks leave loose (a far touchline) is still caught by the first ones. `seed` (a camera from elsewhere, e.g.
    track A's per-frame calibration) replaces the landmarks. `lens`: True fits k1, False leaves it out, a number
    holds it fixed (a per-clip value). `prior` = (pitch points, pixel targets, weight): soft residuals holding those
    points near where another camera put them, for a side of the picture no visible line constrains."""
    size = (frame.shape[1], frame.shape[0])
    resp, occ = line_response(frame, top=top), occluders(frame)
    free = lens is True
    fixed = 0.0 if lens is False or lens is True else float(lens)
    cam = seed if seed is not None else Camera(dlt(np.asarray(pitch_pts, float), np.asarray(pixel_pts, float)),
                                               size=size)
    cam = Camera(cam.h, cam.k1 if free else fixed, size)
    lines = model_lines(step=0.2)
    pts = np.vstack([lines[n] for n in names])

    def unpack(x):
        return Camera(np.append(x[:8], 1.0).reshape(3, 3), float(x[8]) if free else fixed, size)

    for win in search:
        tgt, nrm, _ = _targets(cam, resp, pts, occ=occ, search=win, min_peak=min_peak)
        keep = ~np.isnan(tgt[:, 0])
        p, t, n = pts[keep], tgt[keep], nrm[keep]

        def resid(x, p=p, t=t, n=n):
            c = unpack(x)
            r = np.sum((c.project(p) - t) * n, axis=1)
            if prior is not None and len(prior[0]):
                r = np.concatenate([r, prior[2] * (c.project(prior[0]) - prior[1]).ravel()])
            return r

        x0 = np.append((cam.h / cam.h[2, 2]).ravel()[:8], [cam.k1] if free else [])
        cam = unpack(least_squares(resid, x0, loss="soft_l1", f_scale=1.0, x_scale="jac").x)
    return Fit(camera=cam, drift=drift_px(cam, frame, names, top=top), lines=names)


def load_frame(path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))
