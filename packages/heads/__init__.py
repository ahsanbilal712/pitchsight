"""heads: LightGBM outcome heads and the moment encoder."""

# torch and LightGBM each ship their own libomp on macOS; they coexist only with torch loaded first and OpenMP
# defaulting to one thread (see packages/policy/__init__.py). LightGBM passes num_threads per call.
import os  # noqa: E402

os.environ.setdefault("OMP_NUM_THREADS", "1")
import torch  # noqa: E402, F401
