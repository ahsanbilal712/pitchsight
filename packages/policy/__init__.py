"""policy: Learned on-ball decision policy (decision-only)."""

# torch and LightGBM (outcome heads) each ship their own libomp on macOS. Two OpenMP runtimes in one process are only
# stable when torch loads first and OpenMP defaults to one thread (measured 22 Oct: LightGBM first crashes torch,
# torch first with the default crashes LightGBM). LightGBM sets its own thread count per call; policy.loader restores
# torch's CPU threads.
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
import torch  # noqa: E402, F401
