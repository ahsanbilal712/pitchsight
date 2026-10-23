"""Oracle threat front on real tracks (video v2): the zone summary and the ball filter. The tracks themselves are
git-ignored, so the window is exercised by `python -m footage.threat`, not here."""

import numpy as np

from footage.from_tracks import _good_ball
from footage.threat import ellipse


def test_ellipse_follows_the_spread_of_shot_origins():
    rng = np.random.default_rng(0)
    pts = np.c_[rng.normal(95, 4, 400), rng.normal(34, 1, 400)]
    z = ellipse(pts)
    assert abs(z["cx"] - 95) < 0.6 and abs(z["cy"] - 34) < 0.3
    assert z["rx"] > 3 * z["ry"] and abs(z["angle_deg"]) < 10 or abs(abs(z["angle_deg"]) - 180) < 10
    assert ellipse(pts[:2]) is None


def test_ball_filter_drops_off_pitch_and_weak_detections():
    assert _good_ball({"xy": [52.0, 30.0], "conf": 0.6})
    assert not _good_ball({"xy": [106.3, 53.1], "conf": 0.6})       # off the pitch
    assert not _good_ball({"xy": [52.0, 30.0], "conf": 0.2})        # a low-confidence blob
    assert not _good_ball(None) and not _good_ball({"xy": None})
