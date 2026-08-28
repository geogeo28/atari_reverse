"""Differential tests for the screen buffers, the shifter sink and the block clears (src/video.c):
screen_clear @ 0x1296e, screen_flip_buffers @ 0x1297a, clear_backdrop_page0 @ 0x12fc2,
blit_graphic_block @ 0x134b8, playfield_clear @ 0x1597c, set_palette_title @ 0x153ae.

TWO OF THE SIX END AT THE VIDEO SHIFTER, which is not an image byte, so the memory diff alone would
report a green for a candidate that published nothing at all. Both are given a second witness taken
from the ORACLE'S OWN registers rather than from a Python model of the routine — see
`test_screen_flip_publishes_the_new_front_buffer` and `test_set_palette_title_uploads_the_row`.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, hi_garbage, report

ENTRY_SCREEN_CLEAR = 0x1296e
ENTRY_SCREEN_FLIP_BUFFERS = 0x1297a
ENTRY_CLEAR_BACKDROP_PAGE0 = 0x12fc2
ENTRY_BLIT_GRAPHIC_BLOCK = 0x134b8
ENTRY_PLAYFIELD_CLEAR = 0x1597c
ENTRY_SET_PALETTE_TITLE = 0x153ae

# ---- mirrors of include/video.h ----
A_SCREEN_BACK = 0x1797e
A_SCREEN_FRONT = 0x17982
A_BACKDROP_PAGE0 = 0x1a8ae
A_PALETTE_BOOT = 0x19618
SCREEN_ROW_BYTES = 160
SCREEN_BYTES = 32000
PLAYFIELD_ROWS = 144
PLAYFIELD_BYTES = 0x5a00
GRAPHIC_BLOCK_ROW_BYTES = 32
SHIFTER_PALETTE_PAIRS = 8

# The two rows `_start`'s screen builders pass in D0 (`move.w #$3f,d0` at 0x12a40 and friends,
# `move.w #$17,d0` at 0x12a6a) — a `dbf` count, so 64 and 24 rows.
SHIPPED_BLOCK_LAST_ROWS = (0x3f, 0x17)

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_screen_clear.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_screen_clear.restype = None
harness._lib.g_clear_backdrop_page0.argtypes = [_u8p]
harness._lib.g_clear_backdrop_page0.restype = None
harness._lib.g_playfield_clear.argtypes = [_u8p]
harness._lib.g_playfield_clear.restype = None
harness._lib.g_blit_graphic_block.argtypes = [_u8p] + [ctypes.c_uint32] * 3
harness._lib.g_blit_graphic_block.restype = None
harness._lib.g_screen_flip_buffers.argtypes = [_u8p]
harness._lib.g_screen_flip_buffers.restype = ctypes.c_uint32
harness._lib.g_set_palette_title.argtypes = [_u8p, ctypes.c_uint32]
harness._lib.g_set_palette_title.restype = None


def _noise(seed, spans):
    """Noise over every span a run touches, with `abi.GUARD_BYTES` of margin either side.

    Takes SPANS rather than one base+length, which is not cosmetic: `_block_case` seeds a source
    strip and a destination that OVERLAP in six of its cases, and two pokes over one byte leave the
    second silently winning — the destination's noise swallowing the source strip's and both its
    guard bands. `abi.seed_spans` merges them into one.
    """
    return abi.seed_spans(seed, spans, guard=abi.GUARD_BYTES)


# ===================================================================== screen_clear @ 0x1296e


def _screen_clear_case(buffer, seed, poison=False):
    pokes = _noise(seed, ((buffer, buffer + SCREEN_BYTES),))
    diffs, _ = differential(ENTRY_SCREEN_CLEAR, {"a0": buffer, "_pokes": pokes},
                            lambda lib, buf: lib.g_screen_clear(buf, buffer), poison=poison)
    assert not diffs, f"buffer={buffer:#x}\n{report(diffs)}"


@pytest.mark.parametrize("buffer", (abi.SCRATCH, abi.SCREEN_BACK, abi.SCREEN_FRONT))
def test_screen_clear(buffer):
    """A whole 320x200 four-plane frame, at both of the game's own hard-coded framebuffers and at a
    buffer that is neither — the routine takes its destination in A0 and cares about nothing else."""
    _screen_clear_case(buffer, seed=buffer)


def test_screen_clear_attribution():
    """Poison every byte the oracle wrote: a candidate stopping a longword short stays canary."""
    _screen_clear_case(abi.SCRATCH, seed=0x1296e, poison=True)


# ============================================================ clear_backdrop_page0 @ 0x12fc2


def _backdrop_case(seed, poison=False):
    pokes = _noise(seed, ((A_BACKDROP_PAGE0, A_BACKDROP_PAGE0 + PLAYFIELD_BYTES),))
    diffs, _ = differential(ENTRY_CLEAR_BACKDROP_PAGE0, {"_pokes": pokes},
                            lambda lib, buf: lib.g_clear_backdrop_page0(buf), poison=poison)
    assert not diffs, report(diffs)


def test_clear_backdrop_page0():
    """One playfield's worth at the fixed page. The address is an immediate in the routine, so the
    only thing a case can vary is what was there before — noise, with a guard band."""
    _backdrop_case(seed=0x12fc2)


def test_clear_backdrop_page0_attribution():
    _backdrop_case(seed=0x12fc3, poison=True)


# ================================================================= playfield_clear @ 0x1597c


def _playfield_case(screen_back, seed, poison=False):
    pokes = _noise(seed, ((screen_back, screen_back + PLAYFIELD_BYTES),))
    pokes[A_SCREEN_BACK] = screen_back.to_bytes(4, "big")
    diffs, _ = differential(ENTRY_PLAYFIELD_CLEAR, {"_pokes": pokes},
                            lambda lib, buf: lib.g_playfield_clear(buf), poison=poison)
    assert not diffs, f"screen_back={screen_back:#x}\n{report(diffs)}"


@pytest.mark.parametrize("screen_back", (abi.SCREEN_BACK, abi.SCREEN_FRONT, abi.SCRATCH))
def test_playfield_clear(screen_back):
    """The top 144 rows of whichever buffer `screen_back` names — both of the game's, and a third
    that is neither, which is what says the routine reads the pointer rather than an immediate."""
    _playfield_case(screen_back, seed=screen_back)


def test_playfield_clear_attribution():
    _playfield_case(abi.SCREEN_BACK, seed=0x1597c, poison=True)


# ============================================================== blit_graphic_block @ 0x134b8


def _block_case(src, dst, last_row, seed, poison=False):
    """Call blit_graphic_block(A6 = src, A0 = dst, D0 = last_row) at its own entry.

    Both the source strip and the whole destination extent are seeded, so a candidate that copies
    too few rows — or steps the destination by the wrong stride — leaves bytes that differ.
    """
    rows = (last_row & 0xffff) + 1
    pokes = _noise(seed, ((src, src + rows * GRAPHIC_BLOCK_ROW_BYTES),
                          (dst, dst + rows * SCREEN_ROW_BYTES)))
    regs = {"a6": src, "a0": dst, "d0": last_row, "_pokes": pokes}
    diffs, _ = differential(ENTRY_BLIT_GRAPHIC_BLOCK, regs,
                            lambda lib, buf: lib.g_blit_graphic_block(buf, src, dst, last_row),
                            poison=poison)
    assert not diffs, f"src={src:#x} dst={dst:#x} last_row={last_row:#x}\n{report(diffs)}"


@pytest.mark.parametrize("last_row", SHIPPED_BLOCK_LAST_ROWS + (0, 1, 0x7f))
def test_blit_graphic_block_heights(last_row):
    """Both shipped heights, the one-row minimum, and two more — the count is a `dbf` register, so
    0 must copy ONE row rather than none."""
    _block_case(abi.SCRATCH, abi.SCRATCH + 0x8000, last_row, seed=last_row)


def test_blit_graphic_block_high_half_ignored():
    """D0 is read as a word (`dbf d0`), so junk above it must change neither row count nor output."""
    rng = random.Random(ENTRY_BLIT_GRAPHIC_BLOCK)
    for last_row in SHIPPED_BLOCK_LAST_ROWS:
        _block_case(abi.SCRATCH, abi.SCRATCH + 0x8000, hi_garbage(rng, last_row), seed=last_row)


@pytest.mark.parametrize("delta", (-SCREEN_ROW_BYTES, -GRAPHIC_BLOCK_ROW_BYTES, -2, 2,
                                   GRAPHIC_BLOCK_ROW_BYTES, SCREEN_ROW_BYTES))
def test_blit_graphic_block_overlapping(delta):
    """The source inside the destination, at row and word granularity.

    SYNTHETIC AND JUSTIFIED on the terms STATUS.md already sets out for the sprite batteries: the
    routine takes a bare pointer pair and the inputs are pointers, not invented game records. It is
    what holds the read-before-store ORDER within a row — the source advances 32 bytes a row while
    the destination advances 160, so the two cursors cross whenever they start near each other.
    """
    base = abi.SCRATCH + 0x4000
    _block_case(base, base + delta, SHIPPED_BLOCK_LAST_ROWS[1], seed=0x134b8 + delta)


def test_blit_graphic_block_attribution():
    _block_case(abi.SCRATCH, abi.SCRATCH + 0x8000, SHIPPED_BLOCK_LAST_ROWS[0], seed=7, poison=True)


# =========================================================== screen_flip_buffers @ 0x1297a

# Buffer pairs to flip. The first is what the game ships; the rest exist because the routine never
# DEREFERENCES either pointer — it only swaps them and shifts one — so an arbitrary longword is a
# legal input and is what pins the byte extraction over the whole word.
FLIP_BUFFER_PAIRS = (
    (abi.SCREEN_BACK, abi.SCREEN_FRONT),
    (abi.SCREEN_FRONT, abi.SCREEN_BACK),
    (0xaabbccdd, 0x11223344),
    (0x00000000, 0xffffffff),
)


def test_the_two_framebuffer_pointers_are_adjacent():
    """The flip cases poke both pointers as ONE eight-byte write at `screen_back`, which is only
    the right thing to do while the two longwords are adjacent — and that adjacency is a fact about
    the game's layout, not about this battery."""
    assert A_SCREEN_FRONT == A_SCREEN_BACK + 4


def test_playfield_geometry_agrees_with_its_derivation():
    """`PLAYFIELD_BYTES` is kept as the original's own immediate (`adda.l #$5a00,a6`) so that
    test_constants.py can pin it across the language boundary — its scraper reads literals, not
    expressions — which leaves the product it stands for unpinned in the C. Held here instead."""
    assert PLAYFIELD_BYTES == PLAYFIELD_ROWS * SCREEN_ROW_BYTES


@pytest.mark.parametrize("back,front", FLIP_BUFFER_PAIRS)
def test_screen_flip_publishes_the_new_front_buffer(back, front):
    """The pointer swap is an ordinary image write; the $ff8203/$ff8201 pair is not.

    The publish is held against the ORACLE'S OWN registers rather than against a Python copy of the
    arithmetic: `screen_flip_buffers` leaves A0 holding the buffer it published (`movea.l
    $1797e.l,a0` on entry, never written again) and D0 holding that address shifted down 16 by the
    two `lsr.l #8`s, so each of the two bytes has a witness the oracle produced. What stays unpinned
    is that the bytes reach $ff8203/$ff8201 at all — no image differential can see that, and
    STATUS.md carries the residual.
    """
    pokes = {A_SCREEN_BACK: back.to_bytes(4, "big") + front.to_bytes(4, "big")}
    diffs, info = differential(ENTRY_SCREEN_FLIP_BUFFERS, {"_pokes": pokes},
                               lambda lib, buf: lib.g_screen_flip_buffers(buf))
    assert not diffs, f"back={back:#x} front={front:#x}\n{report(diffs)}"

    published = info["regs"]["a0"]           # the buffer that was the BACK one on entry
    expected = (((published >> 16) & 0xff) << 8) | ((published >> 8) & 0xff)
    assert info["ret"] == expected, (
        f"back={back:#x}: candidate published {info['ret']:#06x}, oracle's A0 {published:#x} "
        f"makes it {expected:#06x} (high byte $ff8201, low byte $ff8203)")
    assert (info["ret"] >> 8) == (info["regs"]["d0"] & 0xff), (
        f"back={back:#x}: the $ff8201 byte {info['ret'] >> 8:#04x} is not the oracle's own "
        f"D0 = {info['regs']['d0']:#x} after its two `lsr.l #8`s")


# ================================================================ set_palette_title @ 0x153ae

# The routine writes NO memory — its whole effect is sixteen colour registers at $ff8240 — so the
# oracle enters at a stub that stores the eight longwords it loaded (d0-d7) where the image diff can
# see them, exactly as test_sound.py does for a register-only answer. The candidate's glue publishes
# what its SINK recorded at the same address, so the two uploads are compared byte for byte.
_PALETTE_STORES = tuple(f"d{n}" for n in range(SHIFTER_PALETTE_PAIRS))
PALETTE_BYTES = 4 * SHIFTER_PALETTE_PAIRS


def _palette_case(palette, poison=False):
    pokes = abi.register_call_pokes(ENTRY_SET_PALETTE_TITLE, _PALETTE_STORES)
    pokes[abi.RESULT] = bytes(range(0x41, 0x41 + PALETTE_BYTES))   # neither answer, so silence shows
    pokes[A_PALETTE_BOOT] = palette
    regs = {"a0": abi.RESULT, "_pokes": pokes}
    diffs, _ = differential(abi.STUB, regs,
                            lambda lib, buf: lib.g_set_palette_title(buf, abi.RESULT), poison=poison)
    assert not diffs, f"palette={palette.hex()}\n{report(diffs)}"


def test_set_palette_title_uploads_the_row():
    """The palette the binary ships with, unchanged — the row `_start` actually puts up."""
    _palette_case(bytes(harness.BASE_IMAGE[A_PALETTE_BOOT:A_PALETTE_BOOT + PALETTE_BYTES]))


@pytest.mark.parametrize("seed", (1, 2, 3))
def test_set_palette_title_reads_the_whole_row(seed):
    """Noise in place of the shipped colours: every one of the eight longwords must come from its
    own slot, so a transposed or short read differs rather than agreeing by symmetry."""
    _palette_case(random.Random(seed).randbytes(PALETTE_BYTES))


def test_set_palette_title_attribution():
    """Poison the stub's result slots: a candidate that publishes nothing stays canary in all
    eight, which is the only thing standing between an unwritten sink and a green."""
    _palette_case(bytes(range(0x80, 0x80 + PALETTE_BYTES)), poison=True)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_SCREEN_FRONT", "include/video.h", "A_screen_front"),
    ("A_BACKDROP_PAGE0", "include/video.h", "A_backdrop_page0"),
    ("A_PALETTE_BOOT", "include/video.h", "A_palette_boot"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
    ("SCREEN_BYTES", "include/video.h", "SCREEN_BYTES"),
    ("PLAYFIELD_ROWS", "include/video.h", "PLAYFIELD_ROWS"),
    ("PLAYFIELD_BYTES", "include/video.h", "PLAYFIELD_BYTES"),
    ("GRAPHIC_BLOCK_ROW_BYTES", "include/video.h", "GRAPHIC_BLOCK_ROW_BYTES"),
    ("SHIFTER_PALETTE_PAIRS", "include/video.h", "SHIFTER_PALETTE_PAIRS"),
)
ENTRY_PROLOGUES = {
    "ENTRY_SCREEN_CLEAR": "303c1f3f429851c8fffc",
    "ENTRY_SCREEN_FLIP_BUFFERS": "20790001797e22790001",
    "ENTRY_CLEAR_BACKDROP_PAGE0": "207c0001a8ae3e3c167f",
    "ENTRY_BLIT_GRAPHIC_BLOCK": "4cde02fe48d002fe41e8",
    "ENTRY_PLAYFIELD_CLEAR": "72007400760078007a00",
    "ENTRY_SET_PALETTE_TITLE": "4cf900ff0001961848f9",
}
