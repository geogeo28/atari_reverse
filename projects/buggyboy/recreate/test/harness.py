"""Project-local harness: binds the shared kit (tools/recreate_kit) to this game.

Everything below re-exports the kit's differential driver unchanged, so every
`from harness import differential, report` in test/ keeps working as before.
"""
import sys
from pathlib import Path

_KIT = Path(__file__).resolve().parents[4] / "tools"      # .../reverse/tools
sys.path.insert(0, str(_KIT))

from recreate_kit import project                          # noqa: E402
project.load(Path(__file__).resolve().parents[1])         # the recreate/ dir

from recreate_kit.harness import *                        # noqa: E402,F401,F403
from recreate_kit.harness import _lib, _vet_exclude_bands  # noqa: E402,F401  (tests poke these)
