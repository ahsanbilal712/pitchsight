"""Pitchwatch: real broadcast clips into pitch coordinates.

shots: steady wide broadcast shots, replays flagged. calibrate: a pitch homography per frame.
track: players detected, tracked and projected to pitch metres, with team labels.
Footage and every derived frame stay git-ignored (data/footage/.gitignore); only code, small JSON and reports are
committed.
"""
