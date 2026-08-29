"""Differential tests for the map, the page ring, the tile decoder and the column emitters
(src/scroll.c): map_rle_decompress @ 0x15920, blit_page0_to_playfield @ 0x15d3e,
scroll_page_to_screen_p00..p19 @ 0x15d56..0x16284, scroll_emit_tile_column @ 0x162c2,
scroll_emit_column_shift2 @ 0x169f2 and scroll_emit_column_shift0 @ 0x16a56.

THE MAP AND TILE BATTERIES RUN ON THE GAME'S OWN LEVELS. `map_rle_decompress` consumes a token
stream, and a fabricated one would exercise whichever branch the fabricator happened to think of;
the twelve LEV*.MAP files in ../bin/disk are the streams the game really unpacks, so they are what
the cases feed it. `scroll_emit_tile_column` then consumes what that produced, so its cases run the
level through the ORIGINAL'S OWN unpacker and decode the result against the ZYN*.DAT tile set the
level really names — which is also the only way to keep its computed tile addresses inside the
image, a fuzzed index being a 2 MB reach. What neither can reach is recorded in STATUS.md rather
than manufactured.
"""
import ctypes
import functools
import random

import pytest

import abi
import emu
import harness
from harness import differential, report

ENTRY_MAP_RLE_DECOMPRESS = 0x15920
ENTRY_BLIT_PAGE0_TO_PLAYFIELD = 0x15d3e
ENTRY_SCROLL_EMIT_TILE_COLUMN = 0x162c2
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
SCROLL_TILE_BYTES = 64
SCROLL_TILE_PIXEL_ROWS = 8
SCROLL_TILE_FLIP_FLAG = 0x8000
SCROLL_TILE_INDEX_MASK = 0x7fff

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
harness._lib.g_scroll_emit_tile_column.argtypes = [_u8p] + [ctypes.c_uint32] * 3
harness._lib.g_scroll_emit_tile_column.restype = ctypes.c_uint32


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


# ================================================== scroll_emit_tile_column @ 0x162c2

# The three tile sets on the disk. A level names tile indexes up to a maximum, and the smallest of
# these that covers `(max + 1) * SCROLL_TILE_BYTES` is the one the game pairs it with — measured,
# and exact: LEV1 needs 39488 bytes and ZYN1.DAT is 39488, LEV3 needs 35648 and ZYN3.DAT is 35648,
# LEVZ needs 32128 and ZYN8.DAT is 32128. Which set `_start` actually loads is a filename the
# section flow patches (0x1083a), so the pairing is derived here from the data rather than read off
# a table this battery would have to trust.
TILE_SET_FILES = ("ZYN8.DAT", "ZYN3.DAT", "ZYN1.DAT")

MAP_PAGE_BYTES = PLAYFIELD_BYTES              # a page is one playfield (include/scroll.h)
A_MAP_PAGE_TABLE = 0x1798a                    # ../names.txt — eight page pointers
# A framebuffer that is neither of the game's two, clear of every other buffer this file parks in
# scratch (the emitters' SCRATCH_EDGE reaches 0x16a00).
SCRATCH_EDGE_SCREEN = abi.SCRATCH + 0x18000


@functools.lru_cache(maxsize=None)
def _unpacked_map(level):
    """The 14400-byte column-major map the game gets for `level`.

    Produced by running the ORIGINAL'S OWN `map_rle_decompress` over the level file, not by a second
    unpacker written here — so a tile-decoder case cannot be right about a map the game would never
    have produced, and the two batteries in this file stay one chain rather than two guesses.
    """
    image = harness.make_image({A_TILE_SET_BASE: _level_bytes(level)})
    final, _writes, _regs = emu.run(image, ENTRY_MAP_RLE_DECOMPRESS, {})
    return bytes(final[A_MAP_UNPACKED:A_MAP_UNPACKED + MAP_UNPACKED_BYTES])


def _map_word(level, column, row):
    at = column * MAP_COLUMN_BYTES + row * 2
    return int.from_bytes(_unpacked_map(level)[at:at + 2], "big")


@functools.lru_cache(maxsize=None)
def _tile_set_for(level):
    """The smallest shipped tile set that covers every index `level` names."""
    needed = (max(_map_word(level, c, r) & SCROLL_TILE_INDEX_MASK
                  for c in range(MAP_COLUMNS) for r in range(MAP_ROWS)) + 1) * SCROLL_TILE_BYTES
    for name in TILE_SET_FILES:
        data = (harness.PRG.parent / "disk" / name).read_bytes()
        if len(data) >= needed:
            return data
    raise AssertionError(f"{level} names a tile past every ZYN*.DAT on the disk ({needed} bytes)")


def _column_arms(level, column):
    """Which of the four (near flipped, far flipped) arms this column's eighteen rows reach."""
    return {((_map_word(level, column, row) >> 15) & 1,
             (_map_word(level, column + 1, row) >> 15) & 1) for row in range(MAP_ROWS)}


ALL_TILE_ARMS = {(0, 0), (0, 1), (1, 0), (1, 1)}


def _column_reaching_every_arm(level):
    """The first column of `level` whose eighteen rows reach all four arms in ONE call.

    Such a column exists in every shipped level (measured), which is what makes "all four arms" a
    property of the game's own data rather than of a column this battery picked out.
    """
    for column in range(MAP_COLUMNS - 1):
        if _column_arms(level, column) == ALL_TILE_ARMS:
            return column
    raise AssertionError(f"no column of {level} reaches all four flip arms")


def _tile_column_case(level, column, screen_base, page, hide_screen, seed, poison=False):
    """Call scroll_emit_tile_column(A0 = screen + 152, A5 = the page column, A6 = the map cursor).

    The screen's whole playfield and the page's are seeded, not just the eight bytes a row receives,
    so a candidate writing a fifth plane or stepping by the wrong row stride differs — and so does
    one that writes the screen while `scroll_prefill_hide_screen` says it must not. The map and the
    tile set are the disk's own bytes and are poked over regions no seed covers.
    """
    edge = screen_base + SCROLL_WINDOW_BYTES
    map_cursor = A_MAP_UNPACKED + column * MAP_COLUMN_BYTES
    tile_set = _tile_set_for(level)
    pokes = _noise(seed, ((page, page + MAP_PAGE_BYTES),
                          (screen_base, screen_base + PLAYFIELD_BYTES),
                          (A_SCROLL_COL_WORKSPACE, A_SCROLL_COL_WORKSPACE + WORKSPACE_BYTES)))
    pokes[A_MAP_UNPACKED] = _unpacked_map(level)
    pokes[A_TILE_SET_BASE] = tile_set
    pokes[A_SCROLL_PREFILL_HIDE_SCREEN] = bytes([hide_screen])
    regs = {"a0": edge, "a5": page, "a6": map_cursor, "_pokes": pokes}
    diffs, info = differential(
        ENTRY_SCROLL_EMIT_TILE_COLUMN, regs,
        lambda lib, buf: lib.g_scroll_emit_tile_column(buf, edge, page, map_cursor), poison=poison)
    assert not diffs, (f"{level} column={column} page={page:#x} edge={edge:#x} "
                       f"hide={hide_screen}\n{report(diffs)}")
    # A6 comes back one map column on, and the caller stores it into `map_ptr` — so it is program
    # output even though it never reaches memory here.
    assert info["ret"] == info["regs"]["a6"], (
        f"{level} column={column}: map cursor cand={info['ret']:#x} "
        f"oracle={info['regs']['a6']:#x}")
    assert info["ret"] == map_cursor + MAP_COLUMN_BYTES, (
        f"{level} column={column}: the cursor advanced by {info['ret'] - map_cursor}, not one column")


@pytest.mark.parametrize("level", LEVEL_FILES)
def test_tile_column_every_level(level):
    """Every level the disk ships, decoded against the tile set that level really needs, at a column
    whose own eighteen rows reach all four flip arms.

    Real tiles are what make the arms tell each other apart: a flipped tile is the SAME 64 bytes
    walked backwards, so on symmetric or empty tile data three of the four arms agree and only real
    artwork separates them.
    """
    _tile_column_case(level, _column_reaching_every_arm(level), abi.SCREEN_BACK,
                      SCRATCH_PAGE, 0, seed=LEVEL_FILES.index(level))


# A spread of LEV1 columns: the first, the second, one that reaches all four arms, one whose rows
# are all unflipped, and the last two — 398 being the last whose peek stays inside the map.
TILE_COLUMN_SPREAD = (0, 1, 11, 33, 200, 397, 398)


@pytest.mark.parametrize("column", TILE_COLUMN_SPREAD)
def test_tile_column_walks_the_map(column):
    """Columns across one level, so the 36-byte map stride and the 34-byte peek at the next column
    are exercised at more than one place in the buffer."""
    _tile_column_case(LEVEL_FILES[0], column, abi.SCREEN_BACK, SCRATCH_PAGE, 0, seed=0x900 + column)


def test_tile_column_last_column_peeks_past_the_map():
    """Column 399's peek reads the 36 bytes AFTER the unpacked map, which are neither map nor tile
    set: a 720-byte bss gap between `A_map_unpacked` + 14400 and `A_tile_set_base`.

    Left as the loaded image's own zeroes, so the far tile is index 0 for all eighteen rows — which
    is what makes the case runnable at all (a seeded word there would name a tile up to 2 MB past
    the tile set, off the image entirely). It is the routine's own behaviour at the end of a level
    and it is transcribed, not guarded against; STATUS.md records the reach.
    """
    gap = A_MAP_UNPACKED + MAP_UNPACKED_BYTES
    assert gap + MAP_COLUMN_BYTES <= A_TILE_SET_BASE, (
        "the map no longer abuts a gap wide enough for column 399's peek")
    _tile_column_case(LEVEL_FILES[0], MAP_COLUMNS - 1, abi.SCREEN_BACK, SCRATCH_PAGE, 0, seed=0x9ff)


@pytest.mark.parametrize("hide_screen", (0, 1, 0xff))
def test_tile_column_prefill_redirects_the_screen(hide_screen):
    """Set, the screen destination is redirected onto the page — so the column is written into the
    page twice and the framebuffer is not touched at all. The guard is a `tst.b`, so 0xff is as good
    as 1, and the cases with it clear are what say the screen IS written when it is not set."""
    _tile_column_case(LEVEL_FILES[0], 11, abi.SCREEN_BACK, SCRATCH_PAGE, hide_screen,
                      seed=0xa00 + hide_screen)


@pytest.mark.parametrize("phase", (0, 9, SCROLL_PHASES - 1))
def test_tile_column_at_the_real_destinations(phase):
    """The shape the game runs: A0 is `screen_back` + 152 and A5 is a real page from
    `map_page_table` offset by the column phase, which is `page + phase * 8`."""
    page_base = int.from_bytes(bytes(harness.BASE_IMAGE[A_MAP_PAGE_TABLE + 4:A_MAP_PAGE_TABLE + 8]),
                               "big")
    _tile_column_case(LEVEL_FILES[0], 11, abi.SCREEN_BACK,
                      page_base + phase * SCROLL_PHASE_STEP, 0, seed=0xb00 + phase)


def test_tile_column_at_a_third_screen():
    """A framebuffer that is neither of the game's two, which says A0 is a pointer the caller passes
    and not the `screen_back` the emitters read for themselves."""
    _tile_column_case(LEVEL_FILES[0], 11, SCRATCH_EDGE_SCREEN, SCRATCH_PAGE, 0, seed=0xc00)


def test_tile_column_attribution():
    """Poison every byte the oracle wrote. The workspace is the arm this catches: its longwords pair
    the near tile's word with the far tile's, and a candidate that wrote only the near half — which
    is what the screen and the page already hold — stays canary in the low words."""
    _tile_column_case(LEVEL_FILES[0], 11, abi.SCREEN_BACK, SCRATCH_PAGE, 0,
                      seed=ENTRY_SCROLL_EMIT_TILE_COLUMN, poison=True)


def test_tile_column_arms_are_all_reached_by_the_shipped_levels():
    """The battery's claim to cover all four flip arms, held against the data.

    NOT a re-assertion of `_column_reaching_every_arm`'s own postcondition — that helper raises when
    no such column exists, so asserting its answer would be tautological and would cost twelve oracle
    map unpacks to say nothing. What this checks is the weaker fact the helper's search DEPENDS on:
    that one level's own columns, taken together, use all four (near flipped, far flipped) pairs. A
    level that stopped flipping tiles would fail here with a message about the DATA, where the
    helper's own raise would only say "no column of LEV1 reaches all four flip arms".
    """
    level = LEVEL_FILES[0]
    reached = set()
    for column in range(MAP_COLUMNS - 1):
        reached |= _column_arms(level, column)
    assert reached == ALL_TILE_ARMS, f"{level} uses only {sorted(reached)}"


TILE_FUZZ_CHUNKS = 4
TILE_FUZZ_CASES = 48


def _tile_fuzz_cases():
    rng = random.Random(ENTRY_SCROLL_EMIT_TILE_COLUMN)   # seeded ONCE — every chunk replays it
    for i in range(TILE_FUZZ_CASES):
        yield (i,
               LEVEL_FILES[rng.randrange(len(LEVEL_FILES))],
               rng.randrange(MAP_COLUMNS - 1),     # the peek stays inside the map
               rng.randrange(2) == 0,              # the real framebuffer, or a third one?
               rng.randrange(1 << 30))


@pytest.mark.parametrize("chunk", range(TILE_FUZZ_CHUNKS))
def test_tile_column_fuzz(chunk):
    """Columns drawn from every level against fresh noise, so no column's output is ever compared
    against a destination whose bytes happen to repeat with the tile stride.

    THE COLUMN IS THE ONLY THING FUZZED, and that is a measurement rather than a shortcut: the map
    word is a tile INDEX scaled by 64 into an absolute address, so a random word reaches up to 2 MB
    past `A_tile_set_base` and off the 1 MB image — where the oracle drops the read and a
    reconstruction indexing `image + addr` would read host memory. The game's own maps are what keep
    every index inside the set the level loaded; STATUS.md records that as the residual it is.
    """
    # SHARDED BY LEVEL and not by case index: a case's cost is dominated by unpacking its level's
    # map, which is cached per worker, so splitting by `i % chunks` would have every worker unpack
    # most of the twelve. Sharding by level gives each worker ~3 maps and the same 48 cases.
    for i, level, column, real_screen, seed in _tile_fuzz_cases():
        if LEVEL_FILES.index(level) % TILE_FUZZ_CHUNKS != chunk:
            continue
        _tile_column_case(level, column,
                          abi.SCREEN_BACK if real_screen else SCRATCH_EDGE_SCREEN,
                          SCRATCH_PAGE, 0, seed)


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
    ("SCROLL_TILE_BYTES", "include/scroll.h", "SCROLL_TILE_BYTES"),
    ("SCROLL_TILE_PIXEL_ROWS", "include/scroll.h", "SCROLL_TILE_PIXEL_ROWS"),
    ("SCROLL_TILE_FLIP_FLAG", "include/scroll.h", "SCROLL_TILE_FLIP_FLAG"),
    ("SCROLL_TILE_INDEX_MASK", "include/scroll.h", "SCROLL_TILE_INDEX_MASK"),
    # The page pointer table's C home is include/init.h, which is where the section pre-fill reads
    # it; this battery reads the same table to pick a real page, so it is pinned there and not left
    # as this file's own copy of 0x1798a.
    ("A_MAP_PAGE_TABLE", "include/init.h", "A_map_page_table"),
    ("PLAYFIELD_ROWS", "include/video.h", "PLAYFIELD_ROWS"),
)
ENTRY_PROLOGUES = {
    "ENTRY_MAP_RLE_DECOMPRESS": "41f90004b3be43f90004",
    "ENTRY_BLIT_PAGE0_TO_PLAYFIELD": "20790001797e43f90001",
    # TWENTY-TWO BYTES for the two emitters, not the usual ten: they are the same routine but for
    # one step, and their first TWENTY bytes are byte-identical (`tst.b`/`beq`/`movea.l a1,a2`/
    # `moveq #$47,d0`/`movea.l d0,a4`/`movem.l (a0),#$00ff`). They separate at the `lsl.l` one has
    # and the other's `lea`, so a shorter pin would let either address stand for the other.
    # TWENTY BYTES for the tile decoder, for a weaker version of the same reason: its first TEN are
    # the two emitters' as well (`tst.b scroll_prefill_hide_screen / beq`), so a ten-byte pin would
    # not tell the three apart. It separates at byte 10 — `movea.l a5,a0` against their
    # `movea.l a1,a2` — so twelve would in fact do; twenty is carried because the four bytes after
    # that are the `lea` of the workspace address, which is the fact that says this is the decoder
    # and not some other routine that happens to test the same flag.
    "ENTRY_SCROLL_EMIT_TILE_COLUMN": "4a3900019ac167000004204d47f900019fae7011",
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
