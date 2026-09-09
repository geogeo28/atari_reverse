"""Differential tests for src/scroll.c: the frame loop's scroll step, and what a stage start does
to the map cursor and to the screen.

TWO OF THESE CORES ARE VERIFIED AT TWO ADDRESSES EACH, and that is the point rather than an
economy. `title_attract_loop` @ 0x104f2 and `start_level` @ 0x11440 open a stage the same way — seed
the map cursor from the map's own header, then scroll a whole screen in behind a black palette — and
the original carries both blocks TWICE, one copy per site. `src/scroll.c` carries one core for each,
so the claim that the two copies are the same code is something these cases settle: every
`seed_map_row_cursor` and `prescroll_stage` case runs at BOTH entries, and a difference between the
original's two copies would fail at whichever site it is in.

`start_level` itself has no whole-routine case. It ends `bra.w music_play` rather than returning, so
there is no `rts` to stop at, and it is diffed as four slices between the three routines it calls —
`clear_actor_arrays` @ 0x115e2, `set_palette_black` @ 0x111a6 and `set_palette_game` @ 0x111be, all
the `init` subsystem's and all verified now, which makes one whole-routine case stopped at that
`bra` a follow-up rather than something blocked. STATUS.md's rows carry each slice's span.
"""
import functools
import random

import pytest

import abi
import conftest
import emu
import harness

# ---- scroll_advance @ 0x111ee, a whole routine -------------------------------------------------
ENTRY_SCROLL_ADVANCE = 0x111ee

# ---- seed_map_row_cursor, at the title screen's site and at start_level's ----------------------
ENTRY_SEED_CURSOR_TITLE = 0x10508
STOP_SEED_CURSOR_TITLE = 0x1052a
ENTRY_SEED_CURSOR_LEVEL = 0x1151e
STOP_SEED_CURSOR_LEVEL = 0x11540

# ---- prescroll_stage, at the same two sites ----------------------------------------------------
# The title copy's checkpoint is `conftest.ENTRY_ATTRACT_START_TUNE`: `test_frontend.py` ENTERS the
# jingle at the same 0x1054a, so the address is declared and pinned once, in conftest.
ENTRY_PRESCROLL_TITLE = 0x1052a
ENTRY_PRESCROLL_LEVEL = 0x11544
STOP_PRESCROLL_LEVEL = 0x11564

# ---- start_level @ 0x11440's other two slices --------------------------------------------------
ENTRY_START_LEVEL = 0x11440          # [0x11440, 0x1145a): the bomb count and the three resets
STOP_START_LEVEL_RESET = 0x1145a     # the `bsr clear_actor_arrays` the init subsystem owns
ENTRY_START_LEVEL_RECORD = 0x1145e   # [0x1145e, 0x11494): the level record installed
STOP_START_LEVEL_RECORD = 0x11494

# ---- mirrors of include/scroll.h (MIRROR_HEADER below) -----------------------------------------
A_scroll_pos = 0x17758
A_level_distance = 0x1779a
SCROLL_POS_BIAS = 0x30
A_map_row_ptr = 0x16402
A_map_row_ptr_reset = 0x163fe
A_level_map_rows = 0x16434
A_level_map_data = 0x16436
A_prescroll_flag = 0x1642c
A_scroll_fine = 0x16430
SCROLL_FINE_SEED = 0x1e
A_prescroll_frames = 0x17752
A_level_table = 0x15a4c
LEVEL_REC_BYTES = 20
BOMBS_AT_LEVEL_START = 3

# ---- mirrors of the headers this subsystem READS -----------------------------------------------
A_level_map_cols = 0x16432        # include/globals.h — it is also the map file's load address
A_const_words_0123 = 0x176ac      # include/hud.h
CONST_WORD_BYTES = 2              # include/hud.h
A_bombs = 0x17710                 # include/player.h
A_level_number = 0x1642a          # include/player.h
A_level_end_scroll_pos = 0x1771c  # include/player.h
A_boss_scroll_pos = 0x1770a       # include/player.h
A_level_tune_id = 0x1776e         # include/scroll.h
A_spawn_script_ptr = 0x17770      # include/weapons.h

LEVELS = 5                        # include/player.h — the five records in A_level_table
WORD = 2
LONG = 4
U16 = 0xffff

abi.declare_glue("g_scroll_advance", "g_seed_map_row_cursor", "g_prescroll_stage",
                 "g_start_level_reset_actors", "g_start_level_install_record")

_run = abi.run_case          # the project's one case shape (`test/abi.py`)


# =================================================================================================
# scroll_advance @ 0x111ee
# =================================================================================================


def _scroll_advance_case(scroll_pos, poison=True):
    _run(ENTRY_SCROLL_ADVANCE, lambda lib, buf: lib.g_scroll_advance(buf),
         pokes={A_scroll_pos: scroll_pos.to_bytes(WORD, "big"),
                A_level_distance: b"\xde\xad"},
         poison=poison, note=f"scroll_pos={scroll_pos:#06x}")


@pytest.mark.parametrize("scroll_pos", (
    0,                       # the title screen's own seed: distance comes back near 0xffff
    SCROLL_POS_BIAS - 4,     # one step below the bias, where the subtraction wraps
    SCROLL_POS_BIAS - 2,     # ...and the last position that wraps at all
    SCROLL_POS_BIAS,         # the first that does not: distance 1
    SCROLL_POS_BIAS + 2,
    0x8a0,                   # the frame before the level-2 scenery window opens
    0x7ffe,                  # the halving's own sign boundary, if the shift were arithmetic
    0x8000,
    0xfffc,
    0xfffe,                  # `addi.w #$2` wraps the position to 0
))
def test_scroll_advance(scroll_pos):
    """Two pixels of scroll, then `level_distance = ((scroll_pos - 0x30) >> 1) + 1` in 16 bits.

    THE SHIFT IS LOGICAL. A position below the bias leaves the subtraction just under 0x10000, and
    `lsr.w` brings that back as a number just under 0x8000 rather than as a small negative — which
    is what the title screen really runs on for its first two dozen frames, `scroll_pos` being
    seeded to 0. An `asr.w` here would agree with every case at or above the bias."""
    _scroll_advance_case(scroll_pos)


@pytest.mark.parametrize("chunk", range(8))
def test_scroll_advance_fuzz(chunk):
    """Every position, sampled — the routine has one input and no branches, so what is left after
    the edges above is the arithmetic over the whole word."""
    rng = random.Random(0x5c201 + chunk)
    for _ in range(40):
        _scroll_advance_case(rng.randrange(0x10000), poison=False)


# =================================================================================================
# seed_map_row_cursor — the title screen's copy @ 0x10508 and start_level's @ 0x1151e
# =================================================================================================

SEED_CURSOR_SITES = (
    pytest.param(ENTRY_SEED_CURSOR_TITLE, STOP_SEED_CURSOR_TITLE, id="title"),
    pytest.param(ENTRY_SEED_CURSOR_LEVEL, STOP_SEED_CURSOR_LEVEL, id="start_level"),
)

# The cursor and its seed, poisoned so a candidate that wrote neither cannot pass by leaving what
# the fixture already held.
CURSOR_POISON = {A_map_row_ptr: b"\xde\xad\xbe\xef", A_map_row_ptr_reset: b"\xfe\xed\xfa\xce"}


def _seed_cursor_case(entry, stop, rows=None, cols=None, poison=True):
    pokes = dict(CURSOR_POISON)
    if rows is not None:
        pokes[A_level_map_rows] = rows.to_bytes(WORD, "big")
    if cols is not None:
        pokes[A_level_map_cols] = cols.to_bytes(WORD, "big")
    _run(entry, stop_pc=stop, glue=lambda lib, buf: lib.g_seed_map_row_cursor(buf),
         pokes=pokes, poison=poison, note=f"rows={rows} cols={cols} entry={entry:#x}")


@pytest.mark.parametrize("entry,stop", SEED_CURSOR_SITES)
def test_seed_map_row_cursor_over_the_shipped_map(entry, stop):
    """A\\LEVEL1.MAP as the post-load fixture holds it: 10 columns and its own row count, read out
    of the header the loader put there rather than poked."""
    _seed_cursor_case(entry, stop)


@pytest.mark.parametrize("entry,stop", SEED_CURSOR_SITES)
@pytest.mark.parametrize("rows,cols", (
    (0, 10),        # an empty map: the cursor lands on the first cell
    (1, 10),
    (231, 10),      # level 5's row count, the longest of the five
    (10, 0),        # no columns at all
    (10, 1),        # an odd width, where the `asl.w #1` is the whole stride
    (0xffff, 10),   # `mulu.w` is 16x16 -> 32, so this is a product no word could hold
    (0xffff, 0xffff),
    (10, 0x8000),   # `asl.w #1` on the column count wraps the STRIDE to zero before the multiply
    (0x1234, 0x4321),
))
def test_seed_map_row_cursor_over_a_poked_header(entry, stop, rows, cols):
    """`A_level_map_data + rows * (cols * 2)`, with the doubling done as a WORD and the multiply as
    an unsigned 16x16 -> 32. The 0x8000 column count is what separates the two widths: a 32-bit
    doubling would put the cursor 0x10000 further on."""
    _seed_cursor_case(entry, stop, rows=rows, cols=cols)


# =================================================================================================
# prescroll_stage — the title screen's copy @ 0x1052a and start_level's @ 0x11544
# =================================================================================================

PRESCROLL_SITES = (
    pytest.param(ENTRY_PRESCROLL_TITLE, conftest.ENTRY_ATTRACT_START_TUNE, id="title"),
    pytest.param(ENTRY_PRESCROLL_LEVEL, STOP_PRESCROLL_LEVEL, id="start_level"),
)

# One `render_frame` with `prescroll_flag` set is a seam copy, a scroll step and a tile band; the
# shipped frame count is 108 of them. Loose enough for that, tight enough to catch a runaway.
PRESCROLL_MAX_INSNS = 12_000_000
SEED_SLICE_MAX_INSNS = 100_000
# The band the seed slice is allowed to have written: the map cursor and its saved copy, which are
# adjacent longwords. `test_the_seed_staging_is_the_originals_own_work` refuses anything else.
SEEDED_CURSOR_BAND = (A_map_row_ptr_reset, A_map_row_ptr + LONG)


@functools.lru_cache(maxsize=None)
def _cursor_seeded(post_load_bytes):
    """The post-load image with the map cursor seeded BY THE ORIGINAL, at the title screen's site.

    A prescroll on a null cursor would read its tiles from the front of DATA, which is a machine the
    game never has: `render_frame` steps the cursor backwards from the end of the map. Cached on the
    fixture's bytes, so the slice runs once per session however many cases ask.
    """
    final, _writes, _regs = emu.run(bytearray(post_load_bytes), ENTRY_SEED_CURSOR_TITLE,
                                    stop_pc=STOP_SEED_CURSOR_TITLE, max_insns=SEED_SLICE_MAX_INSNS)
    return bytes(final)


def _prescroll_pokes(post_load_image, frames, scroll_fine=SCROLL_FINE_SEED):
    staged = _cursor_seeded(bytes(post_load_image))
    lo, hi = SEEDED_CURSOR_BAND
    return {lo: staged[lo:hi],
            A_scroll_fine: scroll_fine.to_bytes(WORD, "big"),
            A_prescroll_frames: frames.to_bytes(WORD, "big"),
            A_prescroll_flag: b"\xde"}


def _prescroll_case(post_load_image, entry, stop, frames, scroll_fine=SCROLL_FINE_SEED):
    _run(entry, stop_pc=stop, glue=lambda lib, buf: lib.g_prescroll_stage(buf),
         pokes=_prescroll_pokes(post_load_image, frames, scroll_fine),
         max_insns=PRESCROLL_MAX_INSNS,
         note=f"frames={frames} scroll_fine={scroll_fine:#x} entry={entry:#x}")


@pytest.mark.parametrize("entry,stop", PRESCROLL_SITES)
@pytest.mark.parametrize("frames", (0, 1, 2, 5))
def test_prescroll_stage(post_load_image, entry, stop, frames):
    """`move.w $17752,d0` then `dbf d0`, so a stored count of 0 still draws ONE frame — which is the
    off-by-one every `dbf` in this program carries and the reason `frames = 0` is a case rather than
    a degenerate one. `prescroll_flag` is poked to a value that is neither the 1 the routine writes
    nor the 0 it clears, so both stores have to happen."""
    _prescroll_case(post_load_image, entry, stop, frames)


@pytest.mark.parametrize("entry,stop", PRESCROLL_SITES)
def test_prescroll_stage_crosses_a_tile_row(post_load_image, entry, stop):
    """Sixteen frames is a whole 32-pixel tile row of scroll: `scroll_fine` wraps to 0, the map
    cursor steps back one 20-byte row, and every screen base in the ring has moved. Seeded at the
    phase the two callers really seed, so the wrap lands inside the run."""
    _prescroll_case(post_load_image, entry, stop, 16)


def test_prescroll_stage_at_the_shipped_frame_count(post_load_image):
    """The whole of the title screen's own prescroll — the count the .PRG ships, read out of the
    image rather than poked. ONE SITE ONLY: it is 108 frames of `render_frame` under the oracle, and
    what the second site would add over the shorter counts above is the run time."""
    staged = _cursor_seeded(bytes(post_load_image))
    lo, hi = SEEDED_CURSOR_BAND
    _run(ENTRY_PRESCROLL_TITLE, stop_pc=conftest.ENTRY_ATTRACT_START_TUNE,
         glue=lambda lib, buf: lib.g_prescroll_stage(buf),
         pokes={lo: staged[lo:hi], A_scroll_fine: SCROLL_FINE_SEED.to_bytes(WORD, "big")},
         max_insns=PRESCROLL_MAX_INSNS, note="the shipped prescroll_frames")


def test_the_seed_staging_is_the_originals_own_work(post_load_image):
    """The prescroll cases stage on a slice of the ORIGINAL, and this is what says it stages only
    what it claims: outside the two adjacent cursor longwords the seeded image must equal the
    fixture, so a slice that ran too far — into the prescroll it is supposed to precede — would
    fail here rather than quietly become the thing under test."""
    staged = _cursor_seeded(bytes(post_load_image))
    lo, hi = SEEDED_CURSOR_BAND
    # `byte_run_pokes` is the project's one difference scan (`conftest.py`) — block-compared, where
    # the byte-at-a-time loop this used to be was the slowest thing in the battery.
    runs = conftest.byte_run_pokes(bytes(post_load_image), staged)
    # The oracle's own stack band, which `differential` drops from every diff for the same reason:
    # the slice runs on `emu.STACK_TOP` and its return frame is the harness's, not the game's.
    stray = sorted(start for start, run in runs.items()
                   if not (lo <= start and start + len(run) <= hi)
                   and not emu.STACK_GUARD_LO <= start < harness.OS_IMAGE_SIZE)
    assert not stray, (f"the seed slice changed {len(stray)} runs of bytes outside the cursor "
                       f"band, the first at {stray[0]:#x}")
    assert any(lo <= start < hi for start in runs), "the seed slice wrote no cursor at all"


# =================================================================================================
# start_level @ 0x11440 — slice [0x11440, 0x1145a)
# =================================================================================================

START_LEVEL_MAX_INSNS = 400_000


def test_start_level_reset_actors(post_load_image, new_game_pokes):
    """The bomb count out of `const_words_0123[3]`, then the player, the take-off and landing
    scripts and the display list all reset — four routines this slice CALLS rather than restates,
    and the last instruction before the `bsr clear_actor_arrays` the init subsystem owns.

    Run on a started game with the bomb count dirtied, so the store is visible."""
    pokes = dict(new_game_pokes)
    pokes[A_bombs] = b"\xde\xad"
    _run(ENTRY_START_LEVEL, stop_pc=STOP_START_LEVEL_RESET,
         glue=lambda lib, buf: lib.g_start_level_reset_actors(buf), pokes=pokes,
         max_insns=START_LEVEL_MAX_INSNS, note="start_level's actor reset")


def test_start_level_reset_actors_reads_the_bomb_count_out_of_the_table(post_load_image,
                                                                       new_game_pokes):
    """`move.w $176b2,$17710` is a READ of `const_words_0123[3]`, not an immediate 3. With the
    table's fourth word poked to something else the bomb count follows it — which is what separates
    the reconstruction from one that compiled the 3 in."""
    pokes = dict(new_game_pokes)
    pokes[A_bombs] = b"\xde\xad"
    pokes[A_const_words_0123 + BOMBS_AT_LEVEL_START * CONST_WORD_BYTES] = b"\x12\x34"
    _run(ENTRY_START_LEVEL, stop_pc=STOP_START_LEVEL_RESET,
         glue=lambda lib, buf: lib.g_start_level_reset_actors(buf), pokes=pokes,
         max_insns=START_LEVEL_MAX_INSNS, note="a poked const_words[3]")


# =================================================================================================
# start_level @ 0x11440 — slice [0x1145e, 0x11494)
# =================================================================================================

# The four parameters the record is copied into, poisoned so that a candidate which wrote none of
# them could not pass by leaving what was already there.
RECORD_POISON = {A_level_end_scroll_pos: b"\xde\xad", A_boss_scroll_pos: b"\xbe\xef",
                 A_level_tune_id: b"\xfe\xed", A_spawn_script_ptr: b"\xfa\xce\xb0\x0c"}


def _install_record_case(level, extra=None, poison=True):
    pokes = dict(RECORD_POISON)
    pokes[A_level_number] = (level & U16).to_bytes(WORD, "big")
    pokes.update(extra or {})
    _run(ENTRY_START_LEVEL_RECORD, stop_pc=STOP_START_LEVEL_RECORD,
         glue=lambda lib, buf: lib.g_start_level_install_record(buf), pokes=pokes,
         poison=poison, note=f"level={level}")


@pytest.mark.parametrize("level", range(LEVELS))
def test_start_level_installs_each_levels_record(level):
    """All five records, out of the .PRG's own `level_table`: two scroll triggers, a tune number and
    a relocated pointer to the stage's spawn script. The object list is cleared first, which is the
    `bsr clear_object_list` this slice opens with."""
    _install_record_case(level)


def test_start_level_installs_a_seeded_record():
    """One record replaced whole, so every field is a value the shipped table does not carry — the
    only thing that separates a copy of the record from four constants that happen to match it."""
    record = bytes(range(0x11, 0x11 + LEVEL_REC_BYTES))
    _install_record_case(1, extra={A_level_table + LEVEL_REC_BYTES: record})


@pytest.mark.parametrize("level", (LEVELS, LEVELS + 1, 0xffff, 0xfffb))
def test_start_level_indexes_the_table_with_a_signed_multiply(level):
    """`muls.w #$14,d0` on a level number the game keeps in 0..4, and the routine has no floor and
    no ceiling. A level of 5 reads the longword table above `level_table`, and -1 reads twenty bytes
    BELOW it — where an UNSIGNED multiply would read 0xffffec bytes on. Both are latent arms, both
    inside DATA so the read is well defined, and both are reproduced rather than guarded. A level
    far enough out to leave the image is not driven: the original would read memory the model does
    not have, so the case would verify the reconstruction against nothing."""
    _install_record_case(level)


# =================================================================================================
# The pins
# =================================================================================================

MIRROR_HEADER = "include/scroll.h"
MIRRORS = (
    "A_scroll_pos", "A_level_distance", "SCROLL_POS_BIAS",
    "A_map_row_ptr", "A_map_row_ptr_reset", "A_level_map_rows", "A_level_map_data",
    "A_prescroll_flag", "A_scroll_fine",
    "SCROLL_FINE_SEED", "A_prescroll_frames",
    "A_level_table", "LEVEL_REC_BYTES",
    "BOMBS_AT_LEVEL_START",
    ("A_level_map_cols", "include/globals.h", "A_level_map_cols"),
    ("A_const_words_0123", "include/hud.h", "A_const_words_0123"),
    ("CONST_WORD_BYTES", "include/hud.h", "CONST_WORD_BYTES"),
    ("A_bombs", "include/player.h", "A_bombs"),
    ("A_level_number", "include/player.h", "A_level_number"),
    ("A_level_end_scroll_pos", "include/player.h", "A_level_end_scroll_pos"),
    ("A_boss_scroll_pos", "include/player.h", "A_boss_scroll_pos"),
    ("LEVELS", "include/player.h", "LEVELS"),
    "A_level_tune_id",
    ("A_spawn_script_ptr", "include/weapons.h", "A_spawn_script_ptr"),
)

# TEN BYTES, which is what it takes here: this program's routines open on a `lea` or a `move` of an
# absolute long, so a two-byte pin would match dozens of addresses. Note that the two
# `seed_map_row_cursor` sites hold the SAME ten bytes — the original really does carry that block
# twice, which is the premise `src/scroll.c` folds into one core.
ENTRY_PROLOGUES = {
    "ENTRY_SCROLL_ADVANCE": "06790002000177583039",
    "ENTRY_SEED_CURSOR_TITLE": "32390001643430390001",
    "ENTRY_SEED_CURSOR_LEVEL": "32390001643430390001",
    "ENTRY_PRESCROLL_TITLE": "13fc00010001642c3039",
    "ENTRY_PRESCROLL_LEVEL": "13fc00010001642c3039",
    "ENTRY_START_LEVEL": "33f9000176b200017710",
    "ENTRY_START_LEVEL_RECORD": "6100019c428030390001",
}
STOP_PROLOGUES = {
    "STOP_SEED_CURSOR_TITLE": "13fc00010001642c3039",
    "STOP_SEED_CURSOR_LEVEL": "6100fc6413fc00010001",
    "STOP_PRESCROLL_LEVEL": "6100fc5842406000101c",
    "STOP_START_LEVEL_RESET": "610001866100019c4280",
    "STOP_START_LEVEL_RECORD": "4a790001642a67220c79",
}
