"""Project-local harness: binds the shared kit (tools/recreate_kit) to this game.

Everything below re-exports the kit's differential driver unchanged, so every
`from harness import differential, report` in test/ keeps working.
"""
import sys
from pathlib import Path

_KIT = Path(__file__).resolve().parents[4] / "tools"      # .../reverse/tools
sys.path.insert(0, str(_KIT))

from recreate_kit import project                          # noqa: E402
project.load(Path(__file__).resolve().parents[1])         # the recreate/ dir

from recreate_kit.harness import *                        # noqa: E402,F401,F403
from recreate_kit.harness import _lib                     # noqa: E402,F401  (tests poke this)

# ---- the shifter registers this reconstruction does not write (kit TRAP_MODEL.md, "Phase 10") ----
# The kit compares every store to a memory-mapped I/O register against the candidate's, for every
# case, by default. Three routines here make such stores and their reconstructions do not: the
# palette upload (`set_palette` @ 0xf944, the eight `movem.l`s over the sixteen colour registers),
# the single-pen write `clear_palette` @ 0xe7f4 leaves behind, and `flip_screen` @ 0x694's publish
# of the buffer address in the shifter's two screen-base bytes. The hole is this project's oldest —
# ../names.txt's plate at 0xe562 has recorded "$ff8254 ... is OFF the loaded image, so no memory
# differential can see it (the same hole set_palette has carried since batch 12)" since batch 44 —
# and it is a RECONSTRUCTION job, not a harness one: each of the three now has a kit door to write
# through (`hw_write32`/`hw_write16`/`hw_write8`, tools/recreate_kit/include/hw.h), and until one of
# them uses it the cases that reach it declare the addresses here and compare the rest of the run.
#
# Every case that passes this is listed by `leaf.HW_UNPINNED_ROUTINES` plus the boot-chain slices;
# each application is recorded, with its reason, in `harness.HW_WAIVERS`.
SHIFTER_PALETTE_BASE = 0xFF8240      # the sixteen colour registers, sixteen bytes of them
SHIFTER_PALETTE_REGS = 16
_PALETTE_REASON = ("the shifter's colour registers are uploaded by set_palette @ 0xf944 / "
                   "clear_palette @ 0xe7f4, whose reconstructions write no hardware — this "
                   "project's oldest unpinned half (see ../names.txt, cmt 0xe562)")
SHIFTER_UNPINNED = {
    0xFF8201: "the shifter's screen-base HIGH byte is published by flip_screen @ 0x694, whose "
              "reconstruction swaps the two in-image pointers and makes no hardware store",
    0xFF8203: "...and its MID byte, from the same instruction pair",
}
# One entry per colour register rather than a range, because the waiver is keyed by address and the
# original writes the row as eight longwords, one word and (in the credits slice) one word alone —
# three different address sets over the same sixteen registers.
SHIFTER_UNPINNED.update({SHIFTER_PALETTE_BASE + 2 * pen: _PALETTE_REASON
                         for pen in range(SHIFTER_PALETTE_REGS)})
