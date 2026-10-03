"""Project-local harness: binds the shared kit (tools/recreate_kit) to the TOS 1.02 US ROM.

Everything below re-exports the kit's differential driver unchanged, plus this project's address
map — `include/addrs.h` as Python, parsed rather than re-typed (see tools/addrs.py).
"""
import sys
from pathlib import Path

_RECREATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_RECREATE.parents[2] / "tools"))   # .../reverse/tools
sys.path.insert(0, str(_RECREATE / "tools"))              # this project's own tools

from recreate_kit import project                          # noqa: E402
project.load(_RECREATE)

from recreate_kit.harness import *                        # noqa: E402,F401,F403
from recreate_kit.harness import _lib                     # noqa: E402,F401  (tests poke this)
import addrs                                              # noqa: E402,F401

# TIER 3's MODULE, `bench/tier3.py`: the one place a test puts its directory on the path. A battery imports it where a
# case asks (`bench_tier3`), never at its own import — tier3 imports every battery through `test_boot_snapshot`.
BENCH_DIR = _RECREATE / "bench"


def bench_tier3():
    """`bench/tier3.py`, imported (the first call) or already imported."""
    if str(BENCH_DIR) not in sys.path:
        sys.path.insert(0, str(BENCH_DIR))
    import tier3
    return tier3
