"""policy: Learned on-ball decision policy (decision-only, ADR-002)."""

# LightGBM (outcome heads) and torch each ship their own libomp on macOS; loading torch's first makes LightGBM
# predictions crash the process, so LightGBM is loaded before anything in this package imports torch.
import lightgbm  # noqa: F401
