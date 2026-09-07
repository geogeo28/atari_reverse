"""Differential tests for the digitised-voice path (src/voice.c).

WHAT IS HERE. `load_voice_player` @ 0x13c6c, run to `rts` on the REAL GHOST.LOA and GHOST.VOI, and a
SLICE of `play_voice` @ 0x13cea that stops at the `jsr` into the loaded LOA image.

WHY `play_voice` STOPS THERE. What it calls is a SECOND PROGRAM — an `ABSFLAG` .PRG read into the
BSS as data — which programs MFP Timer A, installs a handler at $134 and busy-waits on a done flag
(`../notes/loader.md`). The kit models no MFP timer and no interrupt, so there is nothing to enter
that handler from and nothing to end the wait; ../STATUS.md's "Not reconstructed" carries the
routine and what closing it would need. The slice's core ANSWERS the address it would have called,
so the composition is checked rather than a fall-through being silent.

THE REAL FILES ARE STAGED, not synthetic ones. GHOST.LOA is 0xa8f bytes and GHOST.VOI is 0x7594, so
the reads take the whole of one and all but the last byte of the other — and the game's own bytes
are what land in the image, which is what makes a read of the wrong length or into the wrong buffer
a visible difference rather than a plausible one.
"""
import ctypes
import pathlib
import random

import pytest

import abi
import emu
import harness
from harness import report

REC = pathlib.Path(__file__).resolve().parents[1]

# ---- entry addresses (Ghidra == run-time; see README.md, "The image model") --------------------
ENTRY_LOAD_VOICE_PLAYER = 0x13c6c
ENTRY_PLAY_VOICE = 0x13cea
STOP_PLAY_VOICE = 0x13d26               # the `jsr (a0)` into the LOA image, which is not modeled

# ---- mirrors of include/voice.h ----------------------------------------------------------------
A_name_ghost_loa = 0x22f58
A_name_ghost_voi = 0x22f4e
A_mode_ghost_loa = 0x251be
A_mode_ghost_voi = 0x251c2
A_loa_image = 0x237a0
A_voi_buffer = 0x2379c
LOA_FILE_BYTES = 0xa8f
VOI_BUFFER_BYTES = 0x7594
VOI_FILE_BYTES = 0x7593
FREAD_ITEM_BYTES = 1
A_loa_sample_source = 0x23790
A_loa_sample_slot = 0x23794
A_loa_sample_dest = 0x23798
LOA_SAMPLE_POINTER_OFFSET = 0x1e
LOA_ENTRY_OFFSET = 0x1c

# ---- ...and of the neighbours' headers ----------------------------------------------------------
A_trap_saved_ret = 0x1e932              # include/clib.h — the trampoline's three slots
A_trap_saved_a2 = 0x1e936
A_trap_saved_a1 = 0x1e93a
A_c_unbuf_chars = 0x1eabc               # the span iob_poke-style staging covers
A_c_iob = 0x1eb08
C_IOB_SLOTS = 73
C_IOB_STRIDE = 20

# The names `init_globals` builds in the BSS, which is why they carry no "A:" drive prefix — unlike
# the four picture/demo loaders', which are DATA-segment strings.
LOA_NAME = "GHOST.LOA"
VOI_NAME = "GHOST.VOI"

GHOST_LOA = (REC.parent / "bin" / "GHOST.LOA").read_bytes()
GHOST_VOI = (REC.parent / "bin" / "GHOST.VOI").read_bytes()

CALLER_A1 = 0x0001ce01
CALLER_A2 = 0x0001ce02

# `c_fopen` takes a 0x200-byte buffer per stream out of the model's arena, and both reads run
# through it a bufferful at a time — 0x7594 bytes is 60 refills.
VOICE_MAX_INSNS = 4_000_000

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_load_voice_player.argtypes = [_u8p, ctypes.c_uint32, ctypes.c_uint32]
harness._lib.g_load_voice_player.restype = None
harness._lib.g_play_voice_arm.argtypes = [_u8p]
harness._lib.g_play_voice_arm.restype = ctypes.c_uint32


def _trap_slot_noise(rng):
    """`abi.trap_slot_noise` over this battery's own `A_trap_saved_ret`; the adjacency it relies on
    is asserted here, where the three addresses are restated and pinned to `include/clib.h`."""
    assert A_trap_saved_a2 == A_trap_saved_ret + 4 and A_trap_saved_a1 == A_trap_saved_ret + 8
    return abi.trap_slot_noise(rng, A_trap_saved_ret)


# How much of the model's Malloc arena a case seeds. The VOI buffer is carved out of it, and
# GHOST.VOI has 473 zero bytes in it — so over an untouched (zero) arena a read that stopped short
# would write nothing where it should have written a zero, and the diff would stay empty exactly
# where the file happens to be quiet. Generous: the 0x7594 buffer plus the pool `c_morecore` rounds
# up to, plus the 0x200 buffer each of the two `c_fopen` streams takes.
VOICE_ARENA_SEEDED_BYTES = 0x9000


def _voice_world(seed, loa=None, voi=None):
    """Both files staged under the names `init_globals` builds, and every destination seeded.

    THREE destinations, not one: the LOA image (BSS the loader reads into, which the loaded .PRG
    holds as zeroes), the three scratch longwords, and the ARENA the VOI buffer is malloc'd out of.
    Without the noise a read that stopped short writes nothing where it should have written the
    file's own zero bytes and the diff stays empty.
    """
    rng = random.Random(seed)
    pokes, _handles = harness.stage_files([(LOA_NAME, GHOST_LOA if loa is None else loa),
                                           (VOI_NAME, GHOST_VOI if voi is None else voi)])
    return abi.merge_pokes(
        pokes, _trap_slot_noise(rng),
        abi.seed_spans(seed, ((A_loa_image, A_loa_image + LOA_FILE_BYTES),
                              (A_loa_sample_source, A_voi_buffer + 4),
                              (emu.OS_HEAP_BASE, emu.OS_HEAP_BASE + VOICE_ARENA_SEEDED_BYTES)),
                       guard=abi.GUARD_BYTES))


def test_load_voice_player():
    """Both files read, on the game's own bytes: GHOST.LOA whole into the BSS and GHOST.VOI all but
    its last byte into a buffer `c_malloc` carves out of the arena."""
    diffs, _info = abi.run_with_a4(
        ENTRY_LOAD_VOICE_PLAYER,
        lambda lib, buf: lib.g_load_voice_player(buf, CALLER_A1, CALLER_A2),
        pokes=_voice_world(0x13c6), regs={"a1": CALLER_A1, "a2": CALLER_A2},
        max_insns=VOICE_MAX_INSNS)
    assert not diffs, report(diffs)


def test_load_voice_player_lands_the_files_where_the_player_looks():
    """...and the case is not vacuous: the LOA's own first bytes really are at `A_loa_image`, and
    the VOI buffer holds the sample file.

    Read off the ORACLE, because the byte diff proves the two programs agree and cannot say that
    either of them loaded anything. What pins the read's LENGTH is the diff in the case above, over
    a seeded arena — this only says the files reached their destinations at all.
    """
    pokes = _voice_world(0x13c7)
    staged = harness.make_image(pokes)
    final, _writes, _regs = emu.run(staged, ENTRY_LOAD_VOICE_PLAYER,
                                    regs={"a4": abi.A4_BASE, "a1": CALLER_A1, "a2": CALLER_A2},
                                    max_insns=VOICE_MAX_INSNS)
    assert bytes(final[A_loa_image:A_loa_image + LOA_FILE_BYTES]) == GHOST_LOA
    voi = abi.read_long(final, A_voi_buffer)
    assert voi != 0, "the VOI buffer was never allocated"
    assert bytes(final[voi:voi + VOI_FILE_BYTES]) == GHOST_VOI[:VOI_FILE_BYTES]
    # ...and the buffer's LAST byte is the one the read stops short of, so it still holds the noise
    # the case seeded rather than the file's next byte. Compared against what was STAGED, which is a
    # value that exists whatever GHOST.VOI happens to hold there.
    assert final[voi + VOI_FILE_BYTES] == staged[voi + VOI_FILE_BYTES], (
        "the read filled the whole buffer; the program reads VOI_FILE_BYTES, one byte fewer")


# A VOI buffer address that is distinctive and inside the image, so the three scratch longwords the
# poke is built through are attributable rather than plausible.
STAGED_VOI_BUFFER = abi.SCRATCH + 0x1000


@pytest.mark.parametrize("voi_buffer", (STAGED_VOI_BUFFER, 0, 0xfffffffe))
def test_play_voice_arm(voi_buffer):
    """The sample pointer poked into the loaded LOA image at +0x1e, through three scratch globals.

    Three buffer addresses, including a zero (which is what the field holds if `load_voice_player`
    never ran) and one that wraps: the poke's own address arithmetic is a 32-bit `addi.l`, and a
    reconstruction that truncated it anywhere would differ on the last row.
    """
    rng = random.Random(voi_buffer & 0xffff)
    pokes = abi.merge_pokes(
        abi.seed_spans(0x13ce, ((A_loa_sample_source, A_loa_image + LOA_FILE_BYTES),),
                       guard=abi.GUARD_BYTES),
        {A_voi_buffer: abi.long(voi_buffer)}, _trap_slot_noise(rng), allow_overlap=True)
    diffs, info = abi.run_with_a4(ENTRY_PLAY_VOICE,
                                  lambda lib, buf: lib.g_play_voice_arm(buf),
                                  pokes=pokes, stop_pc=STOP_PLAY_VOICE)
    assert not diffs, f"voi buffer {voi_buffer:#x}\n{report(diffs)}"
    assert info["ret"] == info["regs"]["a0"], (
        f"the reconstruction would have called {info['ret']:#x} and the oracle's A0 holds "
        f"{info['regs']['a0']:#x} — the two would enter the LOA at different addresses")
    assert info["ret"] == A_loa_image + LOA_ENTRY_OFFSET


def test_play_voice_arm_writes_the_pointer_into_the_loa_image():
    """...and where it lands: `A_loa_image + LOA_SAMPLE_POINTER_OFFSET`, which is the one thing the
    LOA player reads out of its own image."""
    pokes = abi.merge_pokes(
        abi.seed_spans(0x13cf, ((A_loa_sample_source, A_loa_image + LOA_FILE_BYTES),),
                       guard=abi.GUARD_BYTES),
        {A_voi_buffer: abi.long(STAGED_VOI_BUFFER)}, allow_overlap=True)
    image = harness.make_image(pokes)
    final, _writes, _regs = emu.run(image, ENTRY_PLAY_VOICE, regs={"a4": abi.A4_BASE},
                                    stop_pc=STOP_PLAY_VOICE)
    assert abi.read_long(final, A_loa_image + LOA_SAMPLE_POINTER_OFFSET) == STAGED_VOI_BUFFER


# ================================================================================================
# The pins `test/test_constants.py` collects.
# ================================================================================================

MIRRORS = (
    ("A_name_ghost_loa", "include/voice.h", "A_name_ghost_loa"),
    ("A_name_ghost_voi", "include/voice.h", "A_name_ghost_voi"),
    ("A_mode_ghost_loa", "include/voice.h", "A_mode_ghost_loa"),
    ("A_mode_ghost_voi", "include/voice.h", "A_mode_ghost_voi"),
    ("A_loa_image", "include/voice.h", "A_loa_image"),
    ("A_voi_buffer", "include/voice.h", "A_voi_buffer"),
    ("LOA_FILE_BYTES", "include/voice.h", "LOA_FILE_BYTES"),
    ("VOI_BUFFER_BYTES", "include/voice.h", "VOI_BUFFER_BYTES"),
    ("VOI_FILE_BYTES", "include/voice.h", "VOI_FILE_BYTES"),
    ("FREAD_ITEM_BYTES", "include/voice.h", "FREAD_ITEM_BYTES"),
    ("A_loa_sample_source", "include/voice.h", "A_loa_sample_source"),
    ("A_loa_sample_slot", "include/voice.h", "A_loa_sample_slot"),
    ("A_loa_sample_dest", "include/voice.h", "A_loa_sample_dest"),
    ("LOA_SAMPLE_POINTER_OFFSET", "include/voice.h", "LOA_SAMPLE_POINTER_OFFSET"),
    ("LOA_ENTRY_OFFSET", "include/voice.h", "LOA_ENTRY_OFFSET"),
    # ...and the neighbour's header this battery reads through rather than restates.
    ("A_trap_saved_ret", "include/clib.h", "A_trap_saved_ret"),
    ("A_trap_saved_a2", "include/clib.h", "A_trap_saved_a2"),
    ("A_trap_saved_a1", "include/clib.h", "A_trap_saved_a1"),
    ("A_c_unbuf_chars", "include/clib.h", "A_c_unbuf_chars"),
    ("A_c_iob", "include/clib.h", "A_c_iob"),
    ("C_IOB_SLOTS", "include/clib.h", "C_IOB_SLOTS"),
    ("C_IOB_STRIDE", "include/clib.h", "C_IOB_STRIDE"),
)

ENTRY_PROLOGUES = {
    "ENTRY_LOAD_VOICE_PLAYER": "4e56fffc486c02a4486ce03e",
    "ENTRY_PLAY_VOICE": "4e56fffc41ece8862008",
}

STOP_PROLOGUES = {
    "STOP_PLAY_VOICE": "4e904e5e4e754e560000",
}
