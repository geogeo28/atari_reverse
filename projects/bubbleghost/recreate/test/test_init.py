"""Differential tests for the boot chain (src/init.c).

WHAT IS HERE. `crt0_start` @ 0x10036, `init_globals` @ 0x16d8e and `main` @ 0x100dc — everything the
program does before its first frame.

NOTHING IN THIS SUBSYSTEM RETURNS, except `init_globals`. So every case but that one is a mid-entry
SLICE with a `stop_pc` (docs/agent-playbook.md §5), and two of the slices are entered at PCs the
composition reaches by a branch rather than by falling through:

* `main`'s WRONG-RESOLUTION arm is unreachable under the model — the kit's XBIOS `Getrez` answers
  low resolution and no case can stage another — so it is entered at its own PC instead of being
  left unrun. What the gate above it decides is checked as the core's ANSWER.
* the crt0 runs on a FILE-LAYOUT image with a fabricated basepage, which is not the image every
  other battery here stages: it is the program as TOS hands it over, BEFORE the segment move this
  slice is. `test_image_model.py` builds the same image for its own end-to-end crt0 pin, and this
  file builds it the same way rather than importing it, because the two ask different questions —
  that one asks whether the fixture is what the startup produces, this one whether the C is what
  the startup's instructions do.

THE POST-INIT FIXTURE IS THIS SUBSYSTEM'S OWN OUTPUT, which is the trap `init_globals`' cases are
written around: `conftest.py` builds the fixture by running the routine under the ORACLE, so a
reconstruction read off the fixture would be green about nothing. `include/init_globals_stream.h` is
generated from the disassembly instead, and `test_init_globals_from_the_bare_image` runs it against
the oracle on `harness.BASE_IMAGE` — the .PRG as loaded, with the BSS still zero — which is the one
image in this project where the routine's whole effect is visible.
"""
import ctypes
import random
import struct

import pytest

import abi
import conftest
import emu
import harness
import loader
from harness import report

# ---- entry addresses (Ghidra == run-time; see README.md, "The image model") --------------------
ENTRY_CRT0 = 0x10036
STOP_CRT0_RELOCATE = 0x100a6            # the `jsr 48(a5)` into init_globals: the slice's end
ENTRY_INIT_GLOBALS = 0x16d8e
ENTRY_MAIN_CHECK_RESOLUTION = 0x100dc
STOP_MAIN_CHECK_RESOLUTION = 0x1010a    # where the LOW-resolution branch lands
ENTRY_MAIN_WRONG_RESOLUTION = 0x100f4   # the `pea 0(a4)` that opens the error arm's c_printf
STOP_MAIN_WRONG_RESOLUTION = 0x100fe    # `move.w #$1,d0 / bne` — a spin with no exit
ENTRY_MAIN_START_GAME = 0x1010a
STOP_MAIN_START_GAME = 0x1010e          # the `jsr game_top_loop`, which never comes back

# ---- mirrors of include/init.h ------------------------------------------------------------------
BASEPAGE_TBASE = 8
BASEPAGE_TLEN = 12
BASEPAGE_DBASE = 16
BASEPAGE_DLEN = 20
BASEPAGE_BBASE = 24
BASEPAGE_BLEN = 28
BASEPAGE_TAIL = 128
MODEL_GETREZ_ANSWER = 0
XBIOS_GETREZ_LOW_RES = 0                # include/frontend.h — what `main` tests Getrez against
BG_CRT0_STACK_SLACK = 0x2100            # include/globals.h — what the Mshrink leaves for the stack
A_rez_message = 0x24f1a
RET_MAIN_GETREZ = 0x100e8

# ---- ...and of the neighbours' headers ----------------------------------------------------------
BG_LOAD_BASE = 0x10000                  # include/globals.h
BG_TEXT_BYTES = 0xe8ca
BG_DATA_BYTES = 0x2f4
BG_BSS_BYTES = 0x6650
BG_BASEPAGE_BYTES = 0x100
A4_BASE = 0x24f1a
BG_PROGRAM_END = 0x2520e
A_trap_saved_ret = 0x1e932              # include/clib.h — the trampoline's three slots
A_trap_saved_a2 = 0x1e936
A_trap_saved_a1 = 0x1e93a
A_screen_phys = 0x23148                 # include/blit.h — what init_gem_and_screens files
A_screen_back = 0x2314c
A_vdi_handle = 0x232ee                  # include/frontend.h
A_vdi_pblock = 0x1e8ca

# The basepage fields TOS fills in that the crt0 never reads, staged so the block is a whole one.
BP_LOWTPA = 0
BP_HITPA = 4

CALLER_A1 = 0x00c0ffee
CALLER_A2 = 0x00badf00

CRT0_MAX_INSNS = 200_000                # the BSS clear alone is 0x6650 passes
# How many bytes of the loaded program `init_globals` leaves DIFFERENT. Measured, and stated so that
# a stream which somehow emptied fails by name: it writes about twice as many, but most of what it
# stores is a zero over the loader's own zero.
INIT_GLOBALS_CHANGED_BYTES = 7056
# The crt0 MOVES THE MACHINE STACK to the top of the block it Mshrinks to, which is outside the band
# `harness.differential` drops — so the twelve bytes the Mshrink call pushes there are the oracle's
# and the candidate (which has no machine stack) never writes them. A generous band around the new
# top is excluded, and `test_crt0_moves_the_stack_where_globals_h_says` is what keeps the exclusion
# honest: it asserts the address rather than letting the band cover anything that drifts into it.
CRT0_STACK_BAND_BYTES = 0x40
INIT_GLOBALS_MAX_INSNS = conftest.INIT_GLOBALS_MAX_INSNS

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_init_globals.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_init_globals.restype = None
harness._lib.g_crt0_relocate_and_clear.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_crt0_relocate_and_clear.restype = ctypes.c_uint32
harness._lib.g_main_check_resolution.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_main_check_resolution.restype = ctypes.c_uint32
harness._lib.g_main_wrong_resolution.argtypes = [_u8p] + [ctypes.c_uint32] * 5
harness._lib.g_main_wrong_resolution.restype = None
harness._lib.g_main_start_game.argtypes = [_u8p] + [ctypes.c_uint32] * 3
harness._lib.g_main_start_game.restype = None


# ================================================================================== init_globals

def test_init_globals_on_the_bare_image():
    """The whole routine, run to `rts` on `harness.BASE_IMAGE` — the .PRG AS LOADED.

    THIS IS THE ONE CASE IN THE PROJECT THAT MUST NOT RUN ON THE POST-INIT FIXTURE, and the reason
    is that the fixture IS this routine's output: staged on it, a reconstruction that wrote nothing
    at all would come back green. `harness.set_base_image` is therefore wound back to the loader's
    image for this case and restored afterwards, so ~15,700 written bytes land on a bss of zeroes
    and every one of them is attributable.
    """
    previous = harness.set_base_image(loader.load_image(harness.PRG))
    try:
        diffs, _info = abi.run_with_a4(
            ENTRY_INIT_GLOBALS,
            lambda lib, buf: lib.g_init_globals(buf, conftest.INIT_GLOBALS_A5),
            regs={"a5": conftest.INIT_GLOBALS_A5}, max_insns=INIT_GLOBALS_MAX_INSNS)
    finally:
        harness.set_base_image(previous)
    assert not diffs, report(diffs)


@pytest.mark.parametrize("a5", (BG_LOAD_BASE, 0, 0x20000, 0xfffe))
def test_init_globals_reads_a5(a5):
    """...and it really depends on A5, which nothing in its shape says: its last paragraph fills a
    seven-entry table with `lea n(a5),a0`.

    A run entered with the wrong A5 puts seven pointers somewhere else, and the four values here are
    what makes that a comparison rather than a claim — `test_image_model.py`'s crt0 pin is what
    found the dependency, and this is what would notice a reconstruction dropping it.
    """
    previous = harness.set_base_image(loader.load_image(harness.PRG))
    try:
        diffs, _info = abi.run_with_a4(ENTRY_INIT_GLOBALS,
                                       lambda lib, buf: lib.g_init_globals(buf, a5),
                                       regs={"a5": a5}, max_insns=INIT_GLOBALS_MAX_INSNS)
    finally:
        harness.set_base_image(previous)
    assert not diffs, f"a5 = {a5:#x}\n{report(diffs)}"


def test_init_globals_really_writes_the_bss(post_init_image):
    """The case above is not vacuous: the routine changes thousands of bytes of a zeroed bss.

    Read off `conftest.py`'s fixture against the loaded image, which is the same comparison the
    differential makes — stated here as a number so that a stream which somehow emptied would fail
    by name rather than by a green diff over two identical images.
    """
    bare = loader.load_image(harness.PRG)
    changed = sum(1 for at in range(BG_LOAD_BASE, BG_PROGRAM_END)
                  if bare[at] != post_init_image[at])
    assert changed == INIT_GLOBALS_CHANGED_BYTES, (
        f"init_globals changed {changed} bytes of the program, not the "
        f"{INIT_GLOBALS_CHANGED_BYTES} it writes — the stream is not the routine's")


# ========================================================================================= crt0
#
# The crt0 runs BEFORE the segment move, so its image is the FILE layout with a basepage below it —
# not the run-time image every other battery stages.

def _file_layout_image_with_a_basepage(text_bytes=BG_TEXT_BYTES, data_bytes=BG_DATA_BYTES,
                                       bss_bytes=BG_BSS_BYTES):
    """GHOST_PLAIN.PRG as TOS hands it to the crt0: loaded, with a basepage at 4(A7).

    The three lengths are arguments because two cases below vary them — a data segment of one byte
    and of none, which the original's `ble` before the `dbf` treats differently from every other
    size. The bytes of the file are unchanged; only the basepage's claim about them moves, which is
    all the slice reads.
    """
    plain = harness.PRG.parent / "GHOST_PLAIN.PRG"
    image = loader.load_image(plain)
    basepage = BG_LOAD_BASE - BG_BASEPAGE_BYTES
    fields = bytearray(BG_BASEPAGE_BYTES)
    struct.pack_into(">I", fields, BP_LOWTPA, basepage)
    struct.pack_into(">I", fields, BP_HITPA, loader.IMAGE_SIZE)
    struct.pack_into(">I", fields, BASEPAGE_TBASE, BG_LOAD_BASE)
    struct.pack_into(">I", fields, BASEPAGE_TLEN, text_bytes)
    struct.pack_into(">I", fields, BASEPAGE_DBASE, BG_LOAD_BASE + text_bytes)
    struct.pack_into(">I", fields, BASEPAGE_DLEN, data_bytes)
    struct.pack_into(">I", fields, BASEPAGE_BBASE, BG_LOAD_BASE + text_bytes + data_bytes)
    struct.pack_into(">I", fields, BASEPAGE_BLEN, bss_bytes)
    image[basepage:basepage + BG_BASEPAGE_BYTES] = fields
    struct.pack_into(">I", image, abi.FIRST_ARG, basepage)
    return bytes(image), basepage


@pytest.fixture(autouse=True)
def _leave_the_loader_bound_to_the_run_time_prg():
    """`loader.load_image` REBINDS the module-level geometry, and half the cases here load the
    file-layout .PRG. `test_image_model.py` restores it for the same reason; so does this."""
    yield
    loader.load_image(harness.PRG)


def _crt0_noise(seed, text_bytes, data_bytes, bss_bytes):
    """Noise over everything the slice writes, so that every store is attributable.

    IT IS NOT TIDINESS. The loaded file-layout image holds its BSS as zeroes, and most of what the
    crt0 does is clear bytes that are already zero — so a BSS clear one byte short writes nothing
    where it should have written a zero, and the diff stays empty. Measured: that mutant passed the
    whole suite before this span existed.

    The span starts AT the data base and not a guard below it, because below it is the program's own
    TEXT — including the instructions the oracle is executing. A store one byte short of the region
    lands on real code, which differs by itself.
    """
    data_base = BG_LOAD_BASE + text_bytes
    end = data_base + data_bytes + bss_bytes
    return abi.seed_spans(seed, ((data_base, end + abi.GUARD_BYTES),), guard=0)


def _crt0_stack_top(basepage, text_bytes, data_bytes, bss_bytes):
    """Where the crt0 puts A7: the top of the block it Mshrinks to, word-aligned DOWN.

    `add.l #$2100,d0 / add.l a5,d1 / and.l #$fffffffe,d1 / movea.l d1,a7` — derived here rather than
    written down, so a case that varies the segment lengths gets the band that goes with them.
    """
    return (basepage + text_bytes + data_bytes + bss_bytes + BG_CRT0_STACK_SLACK) & ~1


CRT0_SEGMENTS = (
    (BG_TEXT_BYTES, BG_DATA_BYTES, BG_BSS_BYTES),   # the program's own
    (BG_TEXT_BYTES, BG_DATA_BYTES, 0x10),           # a tiny bss
    (BG_TEXT_BYTES, 0x100, BG_BSS_BYTES),           # ...and a smaller data segment
    (BG_TEXT_BYTES, 2, 0x40),                       # the smallest data segment that MOVES
    (BG_TEXT_BYTES, 1, 0x40),                       # `dlen - 1 <= 0`: nothing moves at all
    (BG_TEXT_BYTES, 0, 0x40),                       # ...and neither here
    # THE `ble` IS A LONG TEST AND THE `dbf` UNDER IT A WORD ONE, which is two instructions and not
    # one idiom: 0x10001 passes the test with `d0.w` = 0 and then moves exactly ONE byte. The
    # program's own 0x2f4 can never separate the two readings; this row is the only thing that does.
    (BG_TEXT_BYTES, 0x10001, 0x40),
)


@pytest.mark.parametrize("text_bytes,data_bytes,bss_bytes", CRT0_SEGMENTS)
def test_crt0_relocate_and_clear(text_bytes, data_bytes, bss_bytes):
    """The segment move, the BSS clear and the basepage pointer, over six segment layouts.

    The last two rows are the original's own quirk: the counter is `dlen - 1` tested `<= 0` before
    the `dbf`, so a one-byte data segment moves NOTHING while a two-byte one moves both bytes.
    """
    image, basepage = _file_layout_image_with_a_basepage(text_bytes, data_bytes, bss_bytes)
    top = _crt0_stack_top(basepage, text_bytes, data_bytes, bss_bytes)
    previous = harness.set_base_image(image)
    try:
        diffs, info = abi.run_with_a4(
            ENTRY_CRT0,
            lambda lib, buf: lib.g_crt0_relocate_and_clear(buf, basepage),
            pokes=_crt0_noise(data_bytes + bss_bytes, text_bytes, data_bytes, bss_bytes),
            regs={}, stop_pc=STOP_CRT0_RELOCATE, max_insns=CRT0_MAX_INSNS,
            exclude=[(top - CRT0_STACK_BAND_BYTES, top)])
    finally:
        harness.set_base_image(previous)
    assert not diffs, f"text {text_bytes:#x} data {data_bytes:#x} bss {bss_bytes:#x}\n{report(diffs)}"
    assert info["ret"] == info["regs"]["a4"], (
        f"the reconstruction answered a4 = {info['ret']:#x}, the oracle established "
        f"{info['regs']['a4']:#x}")


def test_crt0_establishes_the_projects_a4():
    """...and for the program's OWN segments that A4 is `abi.A4_BASE`, which every other case in
    this project is entered with."""
    image, basepage = _file_layout_image_with_a_basepage()
    top = _crt0_stack_top(basepage, BG_TEXT_BYTES, BG_DATA_BYTES, BG_BSS_BYTES)
    previous = harness.set_base_image(image)
    try:
        _diffs, info = abi.run_with_a4(
            ENTRY_CRT0, lambda lib, buf: lib.g_crt0_relocate_and_clear(buf, basepage),
            pokes=_crt0_noise(0xc7, BG_TEXT_BYTES, BG_DATA_BYTES, BG_BSS_BYTES),
            regs={}, stop_pc=STOP_CRT0_RELOCATE, max_insns=CRT0_MAX_INSNS,
            exclude=[(top - CRT0_STACK_BAND_BYTES, top)])
    finally:
        harness.set_base_image(previous)
    assert info["ret"] == A4_BASE
    assert info["regs"]["a5"] == BG_LOAD_BASE, (
        "the slice ends with a5 = p_tbase, which is the A5 init_globals reads")
    # THE EXCLUDED BAND IS NOT A LICENCE: it must be the stack the crt0 really moved to, and the
    # deepest A7 the run reached is what says so. Anything else in it would be program output
    # dropped from the diff (docs/agent-playbook.md §5, "vet every shortcut").
    assert top - CRT0_STACK_BAND_BYTES <= info["regs"]["min_a7"] < top, (
        f"the run's deepest A7 was {info['regs']['min_a7']:#x}, which is not inside the "
        f"{CRT0_STACK_BAND_BYTES}-byte band below {top:#x} that the diff drops")


# ========================================================================================= main

def _trap_slot_noise(seed=0x100d):
    """`abi.trap_slot_noise` over this battery's own `A_trap_saved_ret`; the adjacency it relies on
    is asserted here, where the three addresses are restated and pinned to `include/clib.h`.

    NOISE, not fixed bytes: a slice that stored a constant of its own into a slot would match a
    hand-written pattern by coincidence, and this battery is the one whose slices write only those
    three longwords."""
    assert A_trap_saved_a2 == A_trap_saved_ret + 4 and A_trap_saved_a1 == A_trap_saved_ret + 8
    return abi.trap_slot_noise(random.Random(seed), A_trap_saved_ret)


def test_main_check_resolution():
    """XBIOS `Getrez`, and the branch on its answer.

    The trap is a no-op in the model, so the three save slots are the whole of what the slice
    writes; the ANSWER is the rest, and a reconstruction that took the other arm would compose the
    error path into a low-resolution boot. Both are checked.
    """
    diffs, info = abi.run_with_a4(
        ENTRY_MAIN_CHECK_RESOLUTION,
        lambda lib, buf: lib.g_main_check_resolution(buf, CALLER_A1, CALLER_A2),
        pokes=_trap_slot_noise(), regs={"a1": CALLER_A1, "a2": CALLER_A2},
        stop_pc=STOP_MAIN_CHECK_RESOLUTION)
    assert not diffs, report(diffs)
    assert info["ret"] & 0xffff == 1, (
        "the reconstruction did not answer \"low resolution\", but the run reached the low-"
        "resolution branch — the two would compose into different programs")


def test_main_check_resolution_files_the_trampolines_slots():
    """...and which trap site ran, which is the only thing a modeled-as-no-op call leaves behind."""
    image = harness.make_image(_trap_slot_noise())
    final, _writes, _regs = emu.run(image, ENTRY_MAIN_CHECK_RESOLUTION,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2},
                                    stop_pc=STOP_MAIN_CHECK_RESOLUTION)
    assert abi.read_long(final, A_trap_saved_ret) == RET_MAIN_GETREZ
    assert abi.read_long(final, A_trap_saved_a1) == CALLER_A1
    assert abi.read_long(final, A_trap_saved_a2) == CALLER_A2


# The printf engine's two threaded machine-state values (`include/clib.h`): the conversion character
# D7 held on entry and the status register above the condition codes. Neither is derivable inside the
# routine that reads it, and the message this arm prints has no conversion in it — so the values are
# arbitrary, and being arbitrary is the point: they are handed to both sides.
PRINTF_INHERITED_CONVERSION = 0x0064     # 'd', a plausible leftover
PRINTF_STATUS_HIGH = 0x2000              # supervisor bit set, as the oracle runs

# Where `main` pushes the format string, which is what `c_printf`'s own `pea 8(a6)` then points at.
# `emu.run` forces A7 to `emu.STACK_TOP`, and the arm's first instruction is the `pea` — so the slot
# is one longword below the top. Inside the band the differential drops, which is why the core takes
# it as an argument rather than having a stack of its own.
MAIN_PRINTF_ARGUMENT_SLOT = emu.STACK_TOP - 4


def test_main_wrong_resolution():
    """The error arm's `c_printf`, entered at its own PC because the gate above can never choose it.

    `Getrez` answers low resolution in the model and nothing can stage another value, so this is
    what "run it anyway" looks like: the arm's own instructions against the oracle's, with the
    branch that reaches them read-verified (../STATUS.md).
    """
    diffs, _info = abi.run_with_a4(
        ENTRY_MAIN_WRONG_RESOLUTION,
        lambda lib, buf: lib.g_main_wrong_resolution(buf, MAIN_PRINTF_ARGUMENT_SLOT,
                                                     PRINTF_INHERITED_CONVERSION,
                                                     PRINTF_STATUS_HIGH, CALLER_A1, CALLER_A2),
        pokes=_trap_slot_noise(), regs={"a1": CALLER_A1, "a2": CALLER_A2,
                                        "d7": PRINTF_INHERITED_CONVERSION},
        stop_pc=STOP_MAIN_WRONG_RESOLUTION)
    assert not diffs, report(diffs)


def test_main_wrong_resolution_really_prints_the_message():
    """...and what it prints is the program's own string, out of the console ledger.

    The message is the FIRST bytes of the DATA segment — `pea 0(a4)` — which is a fact about this
    program's link order rather than about `main`, and nothing else in the suite reads it.
    """
    image = harness.make_image(_trap_slot_noise())
    _final, _writes, regs = emu.run(image, ENTRY_MAIN_WRONG_RESOLUTION,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2,
                                          "d7": PRINTF_INHERITED_CONVERSION},
                                    stop_pc=STOP_MAIN_WRONG_RESOLUTION)
    printed = bytes(value for kind, value in regs["events"]
                    if kind == harness.OS_EVENT_CONOUT)
    assert b"LOW" in printed.upper(), (
        f"the error arm printed {printed!r}, which does not look like the resolution message")


# `main`'s own A6, and the frame `init_gem_and_screens` runs on when it is called from there.
# `main` opens `link a6,#$0`, so its A7 equals its A6 and both are `emu.STACK_TOP` for a run entered
# at the game arm; the `jsr` then pushes a return address and `link a6,#$fffa` the saved A6.
MAIN_FRAME_A6 = emu.STACK_TOP
INIT_GEM_FRAME_A6 = emu.STACK_TOP - 2 * 4


def test_main_start_game():
    """The game arm's first call: the AES connection, the VDI workstation and both screen bases.

    It composes ONE already-verified routine and stops at the `jsr game_top_loop` that follows,
    which never returns — so what this pins is the composition, not `init_gem_and_screens` itself.
    """
    diffs, _info = abi.run_with_a4(
        ENTRY_MAIN_START_GAME,
        lambda lib, buf: lib.g_main_start_game(buf, INIT_GEM_FRAME_A6, CALLER_A1, CALLER_A2),
        pokes=_trap_slot_noise(), regs={"a1": CALLER_A1, "a2": CALLER_A2},
        stop_pc=STOP_MAIN_START_GAME)
    assert not diffs, report(diffs)


def test_main_start_game_opens_the_workstation():
    """...and the case is not vacuous: the two screen pointers and the handle really appear."""
    image = harness.make_image(_trap_slot_noise())
    final, _writes, _regs = emu.run(image, ENTRY_MAIN_START_GAME,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2},
                                    stop_pc=STOP_MAIN_START_GAME)
    assert abi.read_long(final, A_screen_phys) != 0
    assert abi.read_long(final, A_screen_phys) - abi.read_long(final, A_screen_back) == 32000
    assert abi.read_long(final, A_vdi_pblock) != 0, "v_opnvwk left the parameter block unfilled"


def test_the_basepage_offsets_have_one_meaning_across_both_files():
    """`test_image_model.py` stages the SAME basepage under a SECOND set of names (`BP_TBASE` and
    friends), and nothing in the suite would notice the two drifting apart.

    `test_constants.py` keys its duplicate check on the constant NAME and its value check on the
    `A_*` family only, so `BP_DBASE = 16` here and `BASEPAGE_DBASE = 16u` in `include/init.h` are
    invisible to both. That matters because the two files build the same image for different
    questions — that one asks whether the post-init fixture is what the startup produces, this one
    whether the C is what the startup's INSTRUCTIONS do — and a mis-transcribed field would leave
    them staging two different machines while both stayed green.

    The `include/init.h` side is already pinned by MIRRORS below; this pins the other spelling to
    it, which is the whole of what the duplication costs.
    """
    import test_image_model as model

    for ours, theirs in ((BASEPAGE_TBASE, model.BP_TBASE), (BASEPAGE_TLEN, model.BP_TLEN),
                         (BASEPAGE_DBASE, model.BP_DBASE), (BASEPAGE_DLEN, model.BP_DLEN),
                         (BASEPAGE_BBASE, model.BP_BBASE), (BASEPAGE_BLEN, model.BP_BLEN)):
        assert ours == theirs, (
            f"this file stages basepage offset {ours} where test_image_model.py stages {theirs} — "
            f"the two are the same GEMDOS field under two names and have drifted")
    assert (BG_LOAD_BASE, BG_TEXT_BYTES, BG_DATA_BYTES, BG_BSS_BYTES, BG_BASEPAGE_BYTES) == (
        model.BG_LOAD_BASE, model.BG_TEXT_BYTES, model.BG_DATA_BYTES, model.BG_BSS_BYTES,
        model.BG_BASEPAGE_BYTES), (
        "the two files describe the program's segments differently, so they fabricate two "
        "different basepages for the same .PRG")


# ================================================================================================
# The pins `test/test_constants.py` collects.
# ================================================================================================

MIRRORS = (
    ("BASEPAGE_TBASE", "include/init.h", "BASEPAGE_TBASE"),
    ("BASEPAGE_TLEN", "include/init.h", "BASEPAGE_TLEN"),
    ("BASEPAGE_DBASE", "include/init.h", "BASEPAGE_DBASE"),
    ("BASEPAGE_DLEN", "include/init.h", "BASEPAGE_DLEN"),
    ("BASEPAGE_BBASE", "include/init.h", "BASEPAGE_BBASE"),
    ("BASEPAGE_BLEN", "include/init.h", "BASEPAGE_BLEN"),
    ("BASEPAGE_TAIL", "include/init.h", "BASEPAGE_TAIL"),
    ("MODEL_GETREZ_ANSWER", "include/init.h", "MODEL_GETREZ_ANSWER"),
    ("XBIOS_GETREZ_LOW_RES", "include/frontend.h", "XBIOS_GETREZ_LOW_RES"),
    ("BG_CRT0_STACK_SLACK", "include/globals.h", "BG_CRT0_STACK_SLACK"),
    ("A_rez_message", "include/init.h", "A_rez_message"),
    ("RET_MAIN_GETREZ", "include/init.h", "RET_MAIN_GETREZ"),
    # ...and the neighbours' headers this battery reads through rather than restates.
    ("BG_LOAD_BASE", "include/globals.h", "BG_LOAD_BASE"),
    ("BG_TEXT_BYTES", "include/globals.h", "BG_TEXT_BYTES"),
    ("BG_DATA_BYTES", "include/globals.h", "BG_DATA_BYTES"),
    ("BG_BSS_BYTES", "include/globals.h", "BG_BSS_BYTES"),
    ("BG_BASEPAGE_BYTES", "include/globals.h", "BG_BASEPAGE_BYTES"),
    ("A4_BASE", "include/globals.h", "A4_BASE"),
    ("BG_PROGRAM_END", "include/globals.h", "BG_PROGRAM_END"),
    ("A_trap_saved_ret", "include/clib.h", "A_trap_saved_ret"),
    ("A_trap_saved_a2", "include/clib.h", "A_trap_saved_a2"),
    ("A_trap_saved_a1", "include/clib.h", "A_trap_saved_a1"),
    ("A_screen_phys", "include/blit.h", "A_screen_phys"),
    ("A_screen_back", "include/blit.h", "A_screen_back"),
    ("A_vdi_handle", "include/frontend.h", "A_vdi_handle"),
    ("A_vdi_pblock", "include/frontend.h", "A_vdi_pblock"),
)

ENTRY_PROLOGUES = {
    "ENTRY_CRT0": "2a4f2a6d0004202d000c",
    "ENTRY_INIT_GLOBALS": "43ece37432fc001e32fc001f",
    "ENTRY_MAIN_CHECK_RESOLUTION": "4e5600003f3c00044eba5d56",
    "ENTRY_MAIN_WRONG_RESOLUTION": "486c00004eba63c8588f303c",
    "ENTRY_MAIN_START_GAME": "4eba000c4eba00d64e5e4e75",
}

STOP_PROLOGUES = {
    "STOP_CRT0_RELOCATE": "4ead0030206cfffc48680080",
    "STOP_MAIN_CHECK_RESOLUTION": "4eba000c4eba00d64e5e4e75",
    "STOP_MAIN_WRONG_RESOLUTION": "303c000166fa6004600260ea",
    "STOP_MAIN_START_GAME": "4eba00d64e5e4e754e754e56",
}
