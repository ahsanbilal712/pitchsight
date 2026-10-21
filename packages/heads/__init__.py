"""heads: LightGBM outcome heads and the moment encoder."""

# torch and LightGBM each ship their own libomp on macOS. Prediction works next to torch only when torch loads first
# and OpenMP defaults to one thread; LightGBM training crashes with torch loaded at all. So heads sets the one-thread
# default (LightGBM passes num_threads per call) but does not import torch; rollout and policy import torch first.
import os  # noqa: E402

os.environ.setdefault("OMP_NUM_THREADS", "1")
