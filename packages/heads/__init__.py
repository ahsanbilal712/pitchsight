"""heads: LightGBM outcome heads and the moment encoder."""

# Load LightGBM before torch can be (the moment encoder uses torch): with torch's libomp loaded first, LightGBM
# predictions crash the process on macOS.
import lightgbm  # noqa: E402, F401
