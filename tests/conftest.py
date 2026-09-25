"""Test configuration.

Thread caps are set FIRST, before any import that might pull in numpy or scipy.
BLAS backends size their thread pool when the shared library loads, so setting
these afterwards has no effect.

Why it matters: the cluster's login node reports 128 CPUs. OpenBLAS and MKL
default to one thread per core, and that initialisation stalled the suite at the
first `import scipy.stats`. Nothing here is numerically parallel enough to lose
anything by capping it.
"""

import os

for _var in (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
):
    os.environ.setdefault(_var, "4")

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
