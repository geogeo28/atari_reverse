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

# ---- the hardware this project's candidate models as NO-OPS (kit TRAP_MODEL.md, "Phase 10") ----
# The kit compares both off-image hardware streams — the modeled reads and every store to an I/O
# register — for every case by default. Three addresses in this game are answered by src/os.c stubs
# instead of being reproduced, and each stub says why in its own header: the PRG build (game_main.c)
# excludes src/os.c and issues the real trap or poke, so the seam is deliberate and predates the
# ledger. A case that drives one of them passes this dict as `differential(hw_waiver=...)`, which
# drops THAT ADDRESS from both streams on both sides and compares the whole rest of the run as
# usual. Every waiver is recorded in harness.HW_WAIVERS with its reason.
#
# Closing one means giving the stub a real body through the kit's hw_read8 / hw_write8 —
# reconstruction work, not harness work, and it is what these entries are a standing note of. The
# waiver RETIRES ITSELF: a candidate that accesses a waived address fails the case, so a stub that
# grows a body cannot leave these rows quietly hiding it. STATUS.md's "Deferred: the hardware half of
# three routines" is the same list in prose, plus the one address deliberately NOT here.
HW_STUBBED_BY_OS_C = {
    0xFFFC00: "read_joystick @ 0x12110 is g_read_joystick, a no-op in src/os.c: the joystick reply "
              "arrives on an interrupt the harness does not run, so the candidate makes neither the "
              "ACIA status poll the original spins on...",
    0xFFFC02: "...nor the 0x16 interrogate byte it then sends to the ACIA's data port",
    0xFF8200: "the shifter's screen-base register is written by g_flip_screen's hardware half, a "
              "no-op in src/os.c that game_main.c's PRG build overrides with the real store",
}
