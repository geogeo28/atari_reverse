"""The POST-INIT IMAGE every differential case stages on, built once per session.

WHY IT EXISTS. `harness.BASE_IMAGE` is `../bin/GHOST_RT.PRG` laid down at load_base: the run-time
layout, with the BSS all zeroes. That is the machine as the crt0 leaves it *before* the last thing
the crt0 does — `init_globals` @ 0x16d8e, reached through `jsr 48(a5)`, which writes every non-zero
BSS initialiser one `move` at a time (it is why `strings` finds "GHOST.LOA" nowhere in the file).
Some 5,900 words of the game's state are established there and nowhere else, so a case staged on
BASE_IMAGE runs against a program whose tables are all zero — green, and about a machine that never
exists at run time.

So the fixture below runs `init_globals` under the ORACLE once and hands back the image it leaves.
That image is what `../notes/anchors.md`'s addresses describe and what `main` @ 0x100dc is entered
on. `test_image_model.py` proves it equal to what the REAL crt0 produces from the file-layout .PRG,
so this is not a convention the suite invented: it is the program's own startup, run.

SESSION-SCOPED AND READ-ONLY. It is INIT_GLOBALS_INSNS instructions — cheap enough to build per
xdist worker and far too expensive per case. It is handed out as `bytes`, not a `bytearray`, so a
case that means to poke it has to say so — `bytearray(post_init_image)`, or `_pokes` in the
differential's `regs`.
"""
import pytest

import harness
import abi
import emu

# `init_globals` @ 0x16d8e, whose `rts` @ 0x1e8c8 is the last instruction of TEXT. Pinned against
# the image's own bytes by test_image_model.py's ENTRY_PROLOGUES.
INIT_GLOBALS = 0x16d8e
# ...AND IT TAKES A5 = p_tbase, which is the whole reason the crt0 pin exists. Its last paragraph
# (0x1e87e..0x1e8aa) fills a seven-entry table with `lea n(a5),a0 / move.l a0,(a1)+` — pointers at
# the jump table's own slots — so a run entered with a5 = 0 writes seven pointers to low memory
# instead. Nothing about the routine's shape says so; the crt0 leaves a5 there
# (`movea.l 8(a5),a5` @ 0x100a2) and test_image_model.py's crt0 equivalence is what found it.
INIT_GLOBALS_A5 = 0x10000        # = include/globals.h's BG_LOAD_BASE = p_tbase
# Its body is one long `move #imm,n(a4)` run over the whole 0x6650-byte BSS, so the instruction
# count is bounded by the BSS size rather than by any loop.
INIT_GLOBALS_INSNS = 7_871       # measured, and asserted by test_image_model.py so it stays so
# ...and the cap the fixture runs under: loose enough not to be a tuning knob, tight enough that a
# runaway is still caught.
INIT_GLOBALS_MAX_INSNS = 50_000


@pytest.fixture(scope="session")
def post_init_image():
    """`harness.BASE_IMAGE` with `init_globals` run over it: the image `main` is entered on."""
    image, _writes, _regs = emu.run(harness.BASE_IMAGE, INIT_GLOBALS,
                                    regs={"a4": abi.A4_BASE, "a5": INIT_GLOBALS_A5},
                                    max_insns=INIT_GLOBALS_MAX_INSNS)
    return bytes(image)


@pytest.fixture(scope="session", autouse=True)
def _differential_base_image(post_init_image):
    """Install the post-init image as the memory EVERY differential starts from.

    `harness.differential()` builds its image from the kit's base rather than from a fixture, so a
    battery cannot hand it one per case — and a per-case argument would be forgettable in exactly
    the way that stays green (`harness.set_base_image`'s own docstring makes that argument). Autouse
    is therefore the mechanism: every case in the session runs on the image `main` @ 0x100dc is
    entered on, and the loader's zeroed bss is never what a case is verified against.

    The previous base is restored on teardown so the session leaves the kit as it found it.
    """
    previous = harness.set_base_image(post_init_image)
    yield
    harness.set_base_image(previous)
