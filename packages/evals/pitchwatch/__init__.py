"""Pitchwatch: real broadcast clips into pitch coordinates (FOOTAGE_ADDENDUM §3, T-103 to T-105).

shots (T-103): steady wide broadcast shots, replays flagged. calibrate (T-104): a pitch homography per frame.
track (T-105): players detected, tracked and projected to pitch metres, with team labels.
Footage and every derived frame stay git-ignored (data/footage/.gitignore); only code, small JSON and reports are
committed.
"""
