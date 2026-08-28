"""Differential tests for the map, the page ring and the column emitters (src/scroll.c):
map_rle_decompress @ 0x15920, blit_page0_to_playfield @ 0x15d3e,
scroll_page_to_screen_p00..p19 @ 0x15d56..0x16284, scroll_emit_column_shift2 @ 0x169f2 and
scroll_emit_column_shift0 @ 0x16a56.

THE MAP BATTERY RUNS ON THE GAME'S OWN LEVELS. `map_rle_decompress` consumes a token stream, and a
fabricated one would exercise whichever branch the fabricator happened to think of; the twelve
LEV*.MAP files in ../bin/disk are the streams the game really unpacks, so they are what the cases
feed it. What they cannot reach is recorded in STATUS.md rather than manufactured.
"""
import ctypes
import random

import pytest

import abi
import harness
from harness import differential, report

ENTRY_MAP_RLE_DECOMPRESS = 0x15920
ENTRY_BLIT_PAGE0_TO_PLAYFIELD = 0x15d3e
ENTRY_SCROLL_EMIT_COLUMN_SHIFT2 = 0x169f2
ENTRY_SCROLL_EMIT_COLUMN_SHIFT0 = 0x16a56

# The twenty blits, in phase order — the same order as `scroll_blit_jump_table` (0x179aa) and as
# src/scroll.c's own table, which is what the single glue indexes. ENTRY_PROLOGUES pins each one
# individually at the bottom of this file.
ENTRY_SCROLL_PAGE_TO_SCREEN = (
    0x15d56, 0x15d98, 0x15dde, 0x15e24, 0x15e6a, 0x15eb0, 0x15ef6, 0x15f3c, 0x15f82, 0x15fc8,
    0x1600e, 0x16054, 0x1609a, 0x160e0, 0x16126, 0x1616c, 0x161b2, 0x161f8, 0x1623e, 0x16284,
)
# ...and one module-level name per entry, because test_constants.py pins an entry by NAME.
for _phase, _entry in enumerate(ENTRY_SCROLL_PAGE_TO_SCREEN):
    globals()[f"ENTRY_SCROLL_PAGE_TO_SCREEN_P{_phase:02d}"] = _entry

# ---- mirrors of include/scroll.h ----
A_TILE_SET_BASE = 0x4b3be
A_MAP_UNPACKED = 0x478ae
MAP_ROWS = 18
MAP_COLUMNS = 400
MAP_COLUMN_BYTES = 0x24
SCROLL_PHASES = 20
SCROLL_PHASE_STEP = 8
SCROLL_WINDOW_BYTES = 152
A_SCROLL_COL_WORKSPACE = 0x19fae
A_SCROLL_PREFILL_HIDE_SCREEN = 0x19ac1
SCROLL_COLUMN_PASSES = 72
SCROLL_COLUMN_CELL_LONGS = 8
SCROLL_COLUMN_ROW_LONGS = 4

# ---- mirrors of include/video.h ----
A_SCREEN_BACK = 0x1797e
A_BACKDROP_PAGE0 = 0x1a8ae
SCREEN_ROW_BYTES = 160
PLAYFIELD_ROWS = 144
PLAYFIELD_BYTES = 0x5a00

MAP_UNPACKED_BYTES = MAP_COLUMNS * MAP_COLUMN_BYTES
WORKSPACE_BYTES = SCROLL_COLUMN_PASSES * SCROLL_COLUMN_CELL_LONGS * 4
EMIT_ROWS = SCROLL_COLUMN_PASSES * (SCROLL_COLUMN_CELL_LONGS // SCROLL_COLUMN_ROW_LONGS)

# Where a case's own page/screen/workspace buffers go, inside abi's scratch window. Two playfields
# and a workspace, none overlapping, all longword-aligned (a `movem.l` faults otherwise).
SCRATCH_PAGE = abi.SCRATCH
SCRATCH_SCREEN = abi.SCRATCH + 0x8000
SCRATCH_WORKSPACE = abi.SCRATCH + 0x10000
SCRATCH_EDGE = abi.SCRATCH + 0x11000

# NO `max_insns` OVERRIDE, and that is a measurement rather than an oversight: decoding all twelve
# shipped streams puts the unpacker at 33,482-39,300 oracle instructions, comfortably inside
# `differential`'s 200,000 default. An earlier revision passed a "raised" cap of 115,200 that in
# fact LOWERED it, on a rationale that was wrong twice over — `emu.run` RAISES on the cap, it does
# not truncate a run into a half-finished map. A synthetic stream would need its own cap: a token
# with a zero low-15-bit length runs 65,536 cells (~262k instructions) all by itself.

_u8p = ctypes.POINTER(ctypes.c_uint8)
harness._lib.g_map_rle_decompress.argtypes = [_u8p]
harness._lib.g_map_rle_decompress.restype = None
harness._lib.g_blit_page0_to_playfield.argtypes = [_u8p]
harness._lib.g_blit_page0_to_playfield.restype = None
harness._lib.g_scroll_page_to_screen.argtypes = [_u8p] + [ctypes.c_uint32] * 3
harness._lib.g_scroll_page_to_screen.restype = None
for _sym in ("g_scroll_emit_column_shift2", "g_scroll_emit_column_shift0"):
    getattr(harness._lib, _sym).argtypes = [_u8p] + [ctypes.c_uint32] * 3
    getattr(harness._lib, _sym).restype = None


def _noise(seed, spans):
    """Noise over every span a run touches, with `abi.GUARD_BYTES` of margin either side.

    A one-line wrapper so the guard is not restated at eight call sites; the merging and the reason
    for it live in `abi.seed_spans`.
    """
    return abi.seed_spans(seed, spans, guard=abi.GUARD_BYTES)


# ==================================================================== map_rle_decompress @ 0x15920

LEVEL_FILES = tuple(f"LEV{stage}.MAP" for stage in "123456789XYZ")


def _level_bytes(name):
    return (harness.PRG.parent / "disk" / name).read_bytes()


def _map_case(stream, seed, poison=False):
    """Unpack `stream` from A_tile_set_base and diff the whole 14400-byte column-major map."""
    pokes = _noise(seed, ((A_MAP_UNPACKED, A_MAP_UNPACKED + MAP_UNPACKED_BYTES),))
    pokes[A_TILE_SET_BASE] = stream
    diffs, _ = differential(ENTRY_MAP_RLE_DECOMPRESS, {"_pokes": pokes},
                            lambda lib, buf: lib.g_map_rle_decompress(buf), poison=poison)
    assert not diffs, f"{len(stream)}-byte stream\n{report(diffs)}"


@pytest.mark.parametrize("level", LEVEL_FILES)
def test_map_rle_decompress_every_level(level):
    """Every level the disk ships, unpacked from its own bytes.

    Twelve independent streams is what makes the two token kinds and their lengths real coverage:
    the alternation, the run lengths and the literal spans are the level designers', not a test
    author's guess at what a token stream looks like.
    """
    _map_case(_level_bytes(level), seed=LEVEL_FILES.index(level))


def test_map_rle_decompress_attribution():
    """Poison every byte the oracle wrote: a candidate that stops a column short stays canary."""
    _map_case(_level_bytes(LEVEL_FILES[0]), seed=0x15920, poison=True)


# =============================================================== blit_page0_to_playfield @ 0x15d3e


def _page0_case(screen_back, seed, poison=False):
    pokes = _noise(seed, ((A_BACKDROP_PAGE0, A_BACKDROP_PAGE0 + PLAYFIELD_BYTES),
                          (screen_back, screen_back + PLAYFIELD_BYTES)))
    pokes[A_SCREEN_BACK] = screen_back.to_bytes(4, "big")
    diffs, _ = differential(ENTRY_BLIT_PAGE0_TO_PLAYFIELD, {"_pokes": pokes},
                            lambda lib, buf: lib.g_blit_page0_to_playfield(buf), poison=poison)
    assert not diffs, f"screen_back={screen_back:#x}\n{report(diffs)}"


@pytest.mark.parametrize("screen_back", (abi.SCREEN_BACK, abi.SCREEN_FRONT, SCRATCH_SCREEN))
def test_blit_page0_to_playfield(screen_back):
    """One playfield from the fixed backdrop page onto whichever buffer `screen_back` names."""
    _page0_case(screen_back, seed=screen_back)


def test_blit_page0_to_playfield_attribution():
    _page0_case(abi.SCREEN_BACK, seed=0x15d3e, poison=True)


# ============================================ scroll_page_to_screen_p00..p19 @ 0x15d56..0x16284


def _blit_case(phase, page, screen, seed, poison=False):
    """Call one phase's entry (A5 = page, A6 = screen) at ITS OWN address, not through a table.

    Both buffers are seeded over a whole playfield, so a candidate that copies too few rows, starts
    the ring window in the wrong place, or writes into the screen's right-edge cell — which this
    routine must leave alone — differs.
    """
    pokes = _noise(seed, ((page, page + PLAYFIELD_BYTES), (screen, screen + PLAYFIELD_BYTES)))
    regs = {"a5": page, "a6": screen, "_pokes": pokes}
    diffs, _ = differential(ENTRY_SCROLL_PAGE_TO_SCREEN[phase], regs,
                            lambda lib, buf: lib.g_scroll_page_to_screen(buf, phase, page, screen),
                            poison=poison)
    assert not diffs, f"phase={phase} page={page:#x} screen={screen:#x}\n{report(diffs)}"


@pytest.mark.parametrize("phase", range(SCROLL_PHASES))
def test_scroll_page_to_screen_every_phase(phase):
    """All twenty entry points. Each starts its 152-byte ring window 8 bytes further into the page
    row than the last, so nineteen of them wrap and phase 19 does not — and getting the wrap point
    wrong by one cell moves 8 bytes of every one of the 144 rows."""
    _blit_case(phase, SCRATCH_PAGE, SCRATCH_SCREEN, seed=phase)


@pytest.mark.parametrize("phase", (0, SCROLL_PHASES // 2, SCROLL_PHASES - 1))
def test_scroll_page_to_screen_at_the_real_framebuffer(phase):
    """The shape the game runs: A6 is `screen_back`, one of the two hard-coded framebuffers."""
    _blit_case(phase, SCRATCH_PAGE, abi.SCREEN_BACK, seed=0x5c000 + phase)


def test_scroll_page_to_screen_attribution():
    """Poison both wrapping and non-wrapping phases: a candidate that emits the head but not the
    tail stays canary in the tail."""
    _blit_case(1, SCRATCH_PAGE, SCRATCH_SCREEN, seed=0x15d98, poison=True)
    _blit_case(SCROLL_PHASES - 1, SCRATCH_PAGE, SCRATCH_SCREEN, seed=0x16284, poison=True)


# ================================= scroll_emit_column_shift2 @ 0x169f2 / _shift0 @ 0x16a56

_EMIT_ENTRIES = {
    "shift2": (ENTRY_SCROLL_EMIT_COLUMN_SHIFT2, "g_scroll_emit_column_shift2"),
    "shift0": (ENTRY_SCROLL_EMIT_COLUMN_SHIFT0, "g_scroll_emit_column_shift0"),
}


def _emit_case(variant, workspace, page, edge, hide_screen, seed, poison=False):
    """Call one emitter (A0 = workspace, A1 = page column, A2 = edge column) at its own entry.

    The two destinations are seeded over a whole playfield each rather than over the 8 bytes a row
    receives, so a candidate writing a fifth plane or stepping by the wrong row stride differs.
    """
    pokes = _noise(seed, ((workspace, workspace + WORKSPACE_BYTES),
                          (page, page + EMIT_ROWS * SCREEN_ROW_BYTES),
                          (edge, edge + EMIT_ROWS * SCREEN_ROW_BYTES)))
    pokes[A_SCROLL_PREFILL_HIDE_SCREEN] = bytes([hide_screen])
    regs = {"a0": workspace, "a1": page, "a2": edge, "_pokes": pokes}
    entry, glue_name = _EMIT_ENTRIES[variant]
    diffs, _ = differential(entry, regs,
                            lambda lib, buf: getattr(lib, glue_name)(buf, workspace, page, edge),
                            poison=poison)
    assert not diffs, (f"{variant} workspace={workspace:#x} page={page:#x} edge={edge:#x} "
                       f"hide={hide_screen}\n{report(diffs)}")


@pytest.mark.parametrize("variant", sorted(_EMIT_ENTRIES))
@pytest.mark.parametrize("hide_screen", (0, 1, 0xff))
def test_scroll_emit_column(variant, hide_screen):
    """Both emitters, with the prefill flag clear and set.

    Set, the edge destination is redirected onto the page destination — so the case with the flag
    set is what says the redirect happens at all, and the cases with it clear are what say the edge
    column is written when it is not.
    """
    _emit_case(variant, SCRATCH_WORKSPACE, SCRATCH_PAGE, SCRATCH_EDGE, hide_screen,
               seed=_EMIT_ENTRIES[variant][0] + hide_screen)


@pytest.mark.parametrize("variant", sorted(_EMIT_ENTRIES))
def test_scroll_emit_column_at_the_real_workspace(variant):
    """The shape the game runs: A0 is `scroll_col_workspace` and A2 is the screen's own right-edge
    column, 152 bytes into the framebuffer.

    NOTE THE UPPER GUARD BAND: the workspace is exactly WORKSPACE_BYTES long and ends at
    `A_backdrop_page0`, so this case's 16-byte margin lands on the first bytes of the backdrop page.
    Harmless while no case in this battery uses page 0 as a destination — one that did would find
    the head of its own seed overwritten before either core ran.
    """
    assert A_SCROLL_COL_WORKSPACE + WORKSPACE_BYTES == A_BACKDROP_PAGE0, (
        "the workspace no longer abuts the backdrop page — re-check the guard band this case writes")
    _emit_case(variant, A_SCROLL_COL_WORKSPACE, SCRATCH_PAGE,
               abi.SCREEN_BACK + SCROLL_WINDOW_BYTES, 0, seed=_EMIT_ENTRIES[variant][0])


@pytest.mark.parametrize("variant", sorted(_EMIT_ENTRIES))
def test_scroll_emit_column_attribution(variant):
    _emit_case(variant, SCRATCH_WORKSPACE, SCRATCH_PAGE, SCRATCH_EDGE, 0, seed=0x169f2,
               poison=True)


# ============================================================================== sharded fuzz

FUZZ_CHUNKS = 4
FUZZ_CASES = 120


def _fuzz_cases():
    rng = random.Random(0x15d56)                 # seeded ONCE — every chunk replays this stream
    for i in range(FUZZ_CASES):
        yield (i,
               rng.randrange(SCROLL_PHASES),
               rng.randrange(2) == 0,            # screen at the real framebuffer, or in scratch?
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_scroll_page_to_screen_fuzz(chunk):
    """Every phase against fresh noise, so no phase's window is ever compared against a page whose
    bytes happen to repeat with the ring's own period."""
    for i, phase, real_screen, seed in _fuzz_cases():
        if i % FUZZ_CHUNKS != chunk:
            continue
        _blit_case(phase, SCRATCH_PAGE, abi.SCREEN_BACK if real_screen else SCRATCH_SCREEN, seed)


# --- test_constants.py collects these; see README.md, "Adding a function" ---
MIRRORS = (
    ("A_SCREEN_BACK", "include/video.h", "A_screen_back"),
    ("A_BACKDROP_PAGE0", "include/video.h", "A_backdrop_page0"),
    ("SCREEN_ROW_BYTES", "include/video.h", "SCREEN_ROW_BYTES"),
    ("PLAYFIELD_BYTES", "include/video.h", "PLAYFIELD_BYTES"),
    ("A_TILE_SET_BASE", "include/scroll.h", "A_tile_set_base"),
    ("A_MAP_UNPACKED", "include/scroll.h", "A_map_unpacked"),
    ("MAP_ROWS", "include/scroll.h", "MAP_ROWS"),
    ("MAP_COLUMNS", "include/scroll.h", "MAP_COLUMNS"),
    ("MAP_COLUMN_BYTES", "include/scroll.h", "MAP_COLUMN_BYTES"),
    ("SCROLL_PHASES", "include/scroll.h", "SCROLL_PHASES"),
    ("SCROLL_PHASE_STEP", "include/scroll.h", "SCROLL_PHASE_STEP"),
    ("SCROLL_WINDOW_BYTES", "include/scroll.h", "SCROLL_WINDOW_BYTES"),
    ("A_SCROLL_COL_WORKSPACE", "include/scroll.h", "A_scroll_col_workspace"),
    ("A_SCROLL_PREFILL_HIDE_SCREEN", "include/scroll.h", "A_scroll_prefill_hide_screen"),
    ("SCROLL_COLUMN_PASSES", "include/scroll.h", "SCROLL_COLUMN_PASSES"),
    ("SCROLL_COLUMN_CELL_LONGS", "include/scroll.h", "SCROLL_COLUMN_CELL_LONGS"),
    ("SCROLL_COLUMN_ROW_LONGS", "include/scroll.h", "SCROLL_COLUMN_ROW_LONGS"),
    ("PLAYFIELD_ROWS", "include/video.h", "PLAYFIELD_ROWS"),
)
ENTRY_PROLOGUES = {
    "ENTRY_MAP_RLE_DECOMPRESS": "41f90004b3be43f90004",
    "ENTRY_BLIT_PAGE0_TO_PLAYFIELD": "20790001797e43f90001",
    # TWENTY-TWO BYTES for the two emitters, not the usual ten: they are the same routine but for
    # one step, and their first TWENTY bytes are byte-identical (`tst.b`/`beq`/`movea.l a1,a2`/
    # `moveq #$47,d0`/`movea.l d0,a4`/`movem.l (a0),#$00ff`). They separate at the `lsl.l` one has
    # and the other's `lea`, so a shorter pin would let either address stand for the other.
    "ENTRY_SCROLL_EMIT_COLUMN_SHIFT2": "4a3900019ac1670000042449704728404cd000ffe588",
    "ENTRY_SCROLL_EMIT_COLUMN_SHIFT0": "4a3900019ac1670000042449704728404cd000ff41e8",
    # The twenty blits, pinned by a FORMULA rather than by twenty transcribed strings — and the
    # formula is the stronger pin: each entry opens by stepping A5 to its own window start
    # (`lea 8*(phase+1)(a5),a5`, opcode 4bed) and then `move.w #$8f,d0 / movem.l (a5)+,...`. So a
    # mistyped address fails on the DISPLACEMENT, which is exactly what distinguishes one phase's
    # entry from another's. Phase 19's start is 160 = 0 bytes in, so it has no `lea` at all and is
    # the one entry written out.
    **{f"ENTRY_SCROLL_PAGE_TO_SCREEN_P{phase:02d}":
       f"4bed{SCROLL_PHASE_STEP * (phase + 1):04x}303c008f4cdd"
       for phase in range(SCROLL_PHASES - 1)},
    "ENTRY_SCROLL_PAGE_TO_SCREEN_P19": "303c008f4cdd1ffe48d6",
}
