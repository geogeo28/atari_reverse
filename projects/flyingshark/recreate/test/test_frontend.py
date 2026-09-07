"""Differential tests for src/frontend.c: the asset loader's filename patch, the attract screen's
stage start, level 2's scenery band, the debug key wait and the hall-of-fame name entry.

FOUR SHAPES OF CASE, and each is here because the routine has no simpler one.

* `load_level_assets_patch_filenames` and `title_attract_prescroll` are SLICES with a checkpoint PC:
  the first stops at the `bsr load_file` the `init` subsystem owns, the second starts one
  instruction past a `bsr set_palette_black` it also owns.
* `level2_scenery_effect` writes into the SCREEN RING, which the harness places (`test/abi.py`), so
  every case of it indexes the image with an address the routine computed — the `make guarded`
  half of the suite is what says those indices are in bounds.
* `debug_wait_for_keypad4` writes NOTHING. Its whole content is how many times it reads a byte the
  ACIA interrupt maintains, so it is driven through the kit's scheduled-write model and the case is
  the arrival, not the memory.
* `hiscore_name_entry` NEVER RETURNS — every arm ends `bra.w $10720`, back into the attract loop —
  and calls `check_cheat_name` @ 0x10d92, whose own arm spin reads `key_bits` through the same
  model. So the confirming case carries a schedule for a wait site inside a routine it calls.
"""
import random

import pytest

import abi
import conftest
import emu

# ---- load_level_assets @ 0x10332, SLICE [0x10332, 0x10372) --------------------------------------
ENTRY_PATCH_FILENAMES = 0x10332
STOP_PATCH_FILENAMES = 0x10372

# ---- title_attract_loop @ 0x104f2, SLICE [0x104f6, 0x1054a) -------------------------------------
ENTRY_TITLE_PRESCROLL = 0x104f6
STOP_TITLE_PRESCROLL = 0x1054a

# ---- the whole routines -------------------------------------------------------------------------
ENTRY_LEVEL2_SCENERY = 0x1003c
ENTRY_LEVEL2_SCENERY_GATE = 0x10bc8
ENTRY_DEBUG_WAIT_KEYPAD4 = 0x11ba2

# ---- hiscore_name_entry @ 0x10916, SLICE [0x10916, 0x10720) -------------------------------------
ENTRY_HISCORE_NAME_ENTRY = 0x10916
STOP_HISCORE_NAME_ENTRY = 0x10720

# ---- mirrors of include/frontend.h (MIRROR_HEADER below) ----------------------------------------
A_level_bank_digits = 0x162d4
TITLE_SCROLL_POS_START = 0
LEVEL_BANK_DIGITS = 5
HSC_NAME_DIGIT = 6
MAP_NAME_DIGIT = 7
A_scenery_band_offset = 0x17798
A_scenery_band_rows = 0x1779e
A_scenery_band_partial = 0x177a0
A_charset_order_table = 0x177a6
SCENERY_WINDOW_START = 0x8a2
SCENERY_WINDOW_GROW = 0x96e
SCENERY_WINDOW_END = 0x9c6
SCENERY_BAND_OFFSET_SEED = 0x8100
SCENERY_BAND_ROWS_MAX = 0x20
SCENERY_GROW_OFFSET_STEP = 0xa0
SCENERY_SHRINK_ROW_STEP = 2
SCENERY_COLUMNS = 4
SCENERY_GATE_LEVEL = 2
DEBUG_WAIT_KEY_PC = 0x11ba6
A_name_entry_first_pass = 0x176d6
A_name_entry_cursor = 0x176e2
NAME_ENTRY_LAST_CURSOR = 2
NAME_ENTRY_NEXT_GLYPH_BIT = 3
NAME_ENTRY_PREV_GLYPH_BIT = 2

# ---- mirrors of the headers this subsystem READS ------------------------------------------------
A_file_rec_level_map = 0x16330    # include/globals.h
A_file_rec_hsc_0 = 0x16346        # include/globals.h
A_file_rec_hsc_1 = 0x1635a        # include/globals.h
A_file_rec_hsc_2 = 0x1636e        # include/globals.h
A_file_rec_hsc_3 = 0x16382        # include/globals.h
FILE_REC_NAME = 8                 # include/globals.h
A_hiscore_table = 0x161dd         # include/hud.h
HISCORE_STRIDE = 22               # include/hud.h
HISCORE_NAME = 11                 # include/hud.h
HISCORE_NAME_CHARS = 3            # include/hud.h
GLYPH_A = 0xab                    # include/hud.h
GLYPH_SPACE = 0xcf                # include/hud.h
A_hiscore_rank = 0x176e0          # include/hud.h
A_name_entry_done = 0x176dc       # include/hud.h
A_name_entry_timeout = 0x176de    # include/hud.h
A_new_hiscore_pending = 0x176e8   # include/hud.h
A_const_words_0123 = 0x176ac      # include/hud.h
CONST_WORD_BYTES = 2              # include/hud.h
A_joy1_state = 0x1777f            # include/irq.h
JOY_FIRE_BIT = 7                  # include/hud.h
A_key_bits = 0x17780              # include/irq.h
CHEAT_ARM_KEY_BIT = 0             # include/hud.h
CHEAT_ARM_WAIT_PC = 0x10d9a       # include/hud.h
A_level_number = 0x1642a          # include/player.h
A_level_distance = 0x1779a        # include/scroll.h
A_scroll_pos = 0x17758            # include/scroll.h
A_scroll_fine = 0x16430           # include/scroll.h
A_map_row_ptr = 0x16402           # include/scroll.h
A_prescroll_flag = 0x1642c        # include/scroll.h
A_prescroll_frames = 0x17752      # include/scroll.h

WORD = 2
U16 = 0xffff

abi.declare_glue("g_title_attract_prescroll", "g_level2_scenery_effect",
                 "g_level2_scenery_effect_gate", "g_debug_wait_for_keypad4",
                 "g_hiscore_name_entry")
abi.declare_glue("g_load_level_assets_patch_filenames", args=1)

_run = abi.run_case          # the project's one case shape (`test/abi.py`)


# =================================================================================================
# load_level_assets @ 0x10332, slice [0x10332, 0x10372) — the filename patch
# =================================================================================================

# The five bytes the patch overwrites, poisoned so that a candidate which wrote none of them could
# not pass by leaving the digits the .PRG already ships.
BANK_RECORDS = (A_file_rec_hsc_0, A_file_rec_hsc_1, A_file_rec_hsc_2, A_file_rec_hsc_3)
FILENAME_DIGITS = tuple(record + FILE_REC_NAME + HSC_NAME_DIGIT for record in BANK_RECORDS) \
                  + (A_file_rec_level_map + FILE_REC_NAME + MAP_NAME_DIGIT,)


def _patch_case(level, digits=None, poison=True):
    pokes = {address: b"\xde" for address in FILENAME_DIGITS}
    if digits is not None:
        pokes[A_level_bank_digits + (level & U16) * LEVEL_BANK_DIGITS] = digits
    _run(ENTRY_PATCH_FILENAMES, lambda lib, buf: lib.g_load_level_assets_patch_filenames(buf, level),
         pokes=pokes, regs={"d0": level}, stop_pc=STOP_PATCH_FILENAMES, poison=poison,
         note=f"level={level}")


@pytest.mark.parametrize("level", range(5))
def test_patch_filenames_for_every_level(level):
    """The .PRG's own `level_bank_digits`: five bytes a level, four into byte 6 of the "A\\HSC_n.DAT"
    names and the fifth into byte 7 of "A\\LEVEL1.MAP". The fifth is read WITHOUT a post-increment,
    which is what makes a row five bytes long and not four."""
    _patch_case(level)


def test_patch_filenames_from_a_seeded_row():
    """One level's row replaced with five bytes the shipped table does not hold anywhere — so a
    reconstruction that read the wrong row, or the same byte five times, fails by value rather than
    by agreeing with a table of mostly-consecutive digits."""
    _patch_case(2, digits=b"\x11\x22\x33\x44\x55")


@pytest.mark.parametrize("level", (5, 6, 0xffff, 0xfffb))
def test_patch_filenames_indexes_the_digit_table_with_a_signed_multiply(level):
    """`muls.w #$5,d0`, and the routine has neither floor nor ceiling. A level of 5 reads the five
    bytes past the table and -1 the five before it, which an UNSIGNED multiply would put 0x4fffb
    bytes on instead. The arms are latent in the shipped game — nothing writes `level_number` out of
    0..4 — and are reproduced rather than guarded. A level far enough out to leave the image at all
    is not driven: there the original reads memory the model does not have, so a case there would
    verify the reconstruction against nothing."""
    _patch_case(level)


# =================================================================================================
# title_attract_loop @ 0x104f2, slice [0x104f6, 0x1054a)
# =================================================================================================

# 108 frames of `render_frame` under the oracle — the count the .PRG ships in `prescroll_frames`.
TITLE_PRESCROLL_MAX_INSNS = 12_000_000


def _title_prescroll_case(frames=None, scroll_pos_word=None, note=""):
    pokes = {A_scroll_pos: b"\xde\xad", A_scroll_fine: b"\xbe\xef",
             A_map_row_ptr: b"\x00\x00\x00\x00", A_prescroll_flag: b"\xde"}
    if frames is not None:
        pokes[A_prescroll_frames] = frames.to_bytes(WORD, "big")
    if scroll_pos_word is not None:
        pokes[A_const_words_0123 + TITLE_SCROLL_POS_START * CONST_WORD_BYTES] = scroll_pos_word
    _run(ENTRY_TITLE_PRESCROLL, lambda lib, buf: lib.g_title_attract_prescroll(buf),
         pokes=pokes, stop_pc=STOP_TITLE_PRESCROLL, max_insns=TITLE_PRESCROLL_MAX_INSNS,
         note=note or f"frames={frames}")


@pytest.mark.parametrize("frames", (0, 1, 16))
def test_title_attract_prescroll(frames):
    """The attract screen's stage start: scroll position back to zero out of `const_words_0123`,
    scroll phase to 0x1e, the map cursor to the end of the map, and the screen scrolled in with
    `prescroll_flag` set. Sixteen frames is a whole tile row, so the phase wraps and the cursor
    steps inside the run."""
    _title_prescroll_case(frames)


def test_title_attract_prescroll_reads_the_start_position_out_of_the_table():
    """`move.w $176ac,$17758` is a READ of `const_words_0123[0]`, not a `clr.w`. With that word poked
    to something else the scroll position follows it — and the prescroll then runs over a different
    stretch of the map, so the whole screen it draws follows too."""
    _title_prescroll_case(frames=1, scroll_pos_word=b"\x01\x00",
                          note="a poked const_words[0]")


def test_title_attract_prescroll_at_the_shipped_frame_count():
    """The whole of it, at the count the binary ships — the machine `test_sprite.py` stages its
    `render_frame` cases on, verified here as the routine that produces it."""
    _title_prescroll_case(note="the shipped prescroll_frames")


# =================================================================================================
# level2_scenery_effect @ 0x1003c and its gate @ 0x10bc8
# =================================================================================================

SCENERY_MAX_INSNS = 2_000_000

def _scenery_pokes(distance, offset=None, rows=0, partial=0, tile_ids=None):
    pokes = {A_level_distance: (distance & U16).to_bytes(WORD, "big"),
             A_scenery_band_rows: (rows & U16).to_bytes(WORD, "big"),
             A_scenery_band_partial: (partial & U16).to_bytes(WORD, "big")}
    if offset is not None:
        pokes[A_scenery_band_offset] = (offset & U16).to_bytes(WORD, "big")
    if tile_ids is not None:
        pokes[A_charset_order_table] = tile_ids
    return pokes


def _scenery_case(distance, note="", poison=False, **kwargs):
    _run(ENTRY_LEVEL2_SCENERY, lambda lib, buf: lib.g_level2_scenery_effect(buf),
         pokes=_scenery_pokes(distance, **kwargs), max_insns=SCENERY_MAX_INSNS, poison=poison,
         note=note or f"distance={distance:#x} {kwargs}")


@pytest.mark.parametrize("distance", (0, 1, SCENERY_WINDOW_START - 1, 0x8000, 0xffff))
def test_scenery_does_nothing_below_the_window(distance):
    """`cmpi.w / blt` is a SIGNED compare, and `level_distance` really is negative for the first two
    dozen frames of every attract loop (`scroll_advance`'s halving). Nothing is written at all —
    not even the counters — which is what the poisoned state above would show."""
    _scenery_case(distance, rows=7, partial=9, offset=0x4000, poison=True)


@pytest.mark.parametrize("distance", (SCENERY_WINDOW_END + 1, 0x1000, 0x7fff))
def test_scenery_does_nothing_above_the_window(distance):
    """Past the far edge the routine returns before touching anything, leaving the band where the
    last frame inside the window left it — it is never cleared, only scrolled off."""
    _scenery_case(distance, rows=7, partial=9, offset=0x4000, poison=True)


def test_scenery_resets_its_counters_on_the_windows_first_frame():
    """`clr.l $1779e` is ONE LONGWORD over TWO adjacent words: it clears the whole-row count and the
    partial-row count together. Both are poked non-zero, so a candidate that cleared only the first
    fails on the second."""
    _scenery_case(SCENERY_WINDOW_START, rows=0x1234, partial=0x11, offset=0x4000,
                  note="the reset frame")


@pytest.mark.parametrize("partial", (0, 1, SCENERY_BAND_ROWS_MAX - 1, SCENERY_BAND_ROWS_MAX))
def test_scenery_grows(partial):
    """Through the growing half the partial row gains a scanline a frame and the band's top rises by
    SCENERY_GROW_OFFSET_STEP. At SCENERY_BAND_ROWS_MAX it carries: the counter is set to 0xffff so
    the `addq #1` that follows lands on 0, and a whole row is added instead."""
    _scenery_case(SCENERY_WINDOW_START + 2, rows=1, partial=partial, offset=SCENERY_BAND_OFFSET_SEED)


@pytest.mark.parametrize("partial", (0, 1, 2, 3, SCENERY_BAND_ROWS_MAX))
def test_scenery_shrinks(partial):
    """Through the shrinking half it loses SCENERY_SHRINK_ROW_STEP scanlines a frame, borrows a
    whole row back when the partial row is empty, and clamps to zero when the subtraction goes
    negative — a `bpl` past a `clr.w`, so the odd counts are what reach it."""
    _scenery_case(SCENERY_WINDOW_GROW + 1, rows=2, partial=partial,
                  offset=SCENERY_BAND_OFFSET_SEED)


@pytest.mark.parametrize("distance", (SCENERY_WINDOW_GROW, SCENERY_WINDOW_GROW + 1,
                                      SCENERY_WINDOW_END))
def test_scenery_at_the_windows_own_boundaries(distance):
    """The last growing frame, the first shrinking one and the last frame of all — the three the
    two `bgt`s separate, and the only cases that say which side of each the routine takes."""
    _scenery_case(distance, rows=2, partial=4, offset=SCENERY_BAND_OFFSET_SEED)


@pytest.mark.parametrize("rows,partial", ((0, 0), (0, 1), (1, 0), (3, SCENERY_BAND_ROWS_MAX)))
def test_scenery_blits_whole_and_partial_rows(rows, partial):
    """The two loops. Whole rows are four columns of a full 32-row tile; the partial row is four
    columns of the first `partial` scanlines, drawn from where the whole rows left the tile-id
    cursor. Both zero means nothing is drawn at all — which is the state the window opens in."""
    _scenery_case(SCENERY_WINDOW_START + 2, rows=rows, partial=partial,
                  offset=SCENERY_BAND_OFFSET_SEED)


@pytest.mark.parametrize("tile_ids", (
    b"\x00" * 16,                            # tile 0, the top of the bank
    bytes(range(0x30, 0x40)),                # digits, as the shipped table holds them
    b"\x7f" * 16,                            # the last id whose offset still fits a signed word
    b"\x80" * 16,                            # ...and the first that does not: `lsl.w` wraps it to 0
    b"\x40\x41\xc0\xff" * 4,                 # ids whose word offset comes back NEGATIVE
))
def test_scenery_reads_the_tile_bank_with_a_word_shift(tile_ids):
    """`lsl.w #5 / lsl.w #4` is a WORD shift and the `adda.w` that follows SIGN-EXTENDS, so an id of
    0x40 or more addresses a tile BELOW the bank base and 0x80 wraps to the base itself. The shipped
    table is all 0x20..0x3f and never reaches it; these ids are what pin the width."""
    _scenery_case(SCENERY_WINDOW_START + 2, rows=1, partial=4,
                  offset=SCENERY_BAND_OFFSET_SEED, tile_ids=tile_ids)


@pytest.mark.parametrize("offset", (SCENERY_BAND_OFFSET_SEED, 0x8000, 0xff00, 0, 0x100))
def test_scenery_places_the_band_at_a_signed_offset(offset):
    """`adda.w $17798,a5` sign-extends, and the seed the routine itself writes (0x8100) is NEGATIVE
    — the band sits above `screen_draw`, not below it. A zero-extending reconstruction would put it
    32 KB the other way, off the end of the ring, which is what `make guarded` faults on."""
    _scenery_case(SCENERY_WINDOW_START + 2, rows=1, partial=2, offset=offset)


# ---- the band the game itself reaches -----------------------------------------------------------
#
# Every case above pokes the three counters, which reaches each arm one at a time and reaches no
# band bigger than three whole rows. The window the GAME runs is 204 frames long — SCENERY_WINDOW_
# START..SCENERY_WINDOW_GROW, one frame per `level_distance` — and the counters it leaves at the end
# of it are the figures below, MEASURED by replaying the original's own effect over the whole
# growing half (2026-09-07). Two of them are things no poked case chose: six whole tile rows, and an
# offset that has WRAPPED — 0x8100 seeded, 0xa0 subtracted a frame, so the band starts 32,512 bytes
# ABOVE `screen_draw` and is 0x180 BELOW it by the last growing frame.
SCENERY_PEAK_DISTANCE = 0x96e     # == SCENERY_WINDOW_GROW, the last frame of the growing half
SCENERY_PEAK_ROWS = 6
SCENERY_PEAK_PARTIAL = 6
SCENERY_PEAK_OFFSET = 0x180


@pytest.fixture(scope="session")
def scenery_window_pokes(post_load_image):
    """{level_distance: pokes} for the two frames this battery verifies at the game's own height.

    THE STATE IS THE ORIGINAL'S OWN WORK, not a poke: the effect is run under the oracle once per
    `level_distance` from the window's first frame, exactly as the frame loop calls it, so the
    counters, the wrapped offset and the terrain already under the band are all what 204 frames of
    the game produce. `test_the_replayed_window_reaches_the_band_the_measurement_names` is the
    positive control on it.
    """
    image = bytearray(post_load_image)
    staged = {}
    for distance in range(SCENERY_WINDOW_START, SCENERY_PEAK_DISTANCE + 2):
        image[A_level_distance:A_level_distance + WORD] = distance.to_bytes(WORD, "big")
        if distance >= SCENERY_PEAK_DISTANCE:
            staged[distance] = conftest.byte_run_pokes(post_load_image, image)
        image, _writes, _regs = emu.run(image, ENTRY_LEVEL2_SCENERY, max_insns=SCENERY_MAX_INSNS)
        image = bytearray(image)
    return staged


def test_the_replayed_window_reaches_the_band_the_measurement_names(post_load_image,
                                                                    scenery_window_pokes):
    """A replay that quietly stopped growing would make the two cases below small-band duplicates.

    The three counters are read back out of the staged image rather than trusted, and the offset is
    asserted POSITIVE — which is the wrap: the seed is 0x8100 and every frame subtracts, so a band
    that had not wrapped would still be sitting above `screen_draw` with a negative offset.
    """
    image = bytearray(post_load_image)
    for address, data in scenery_window_pokes[SCENERY_PEAK_DISTANCE].items():
        image[address:address + len(data)] = data
    read = lambda at: int.from_bytes(bytes(image[at:at + WORD]), "big")
    assert (read(A_scenery_band_rows), read(A_scenery_band_partial),
            read(A_scenery_band_offset)) == (SCENERY_PEAK_ROWS, SCENERY_PEAK_PARTIAL,
                                             SCENERY_PEAK_OFFSET), (
        f"204 frames of the window left rows={read(A_scenery_band_rows)} "
        f"partial={read(A_scenery_band_partial)} offset={read(A_scenery_band_offset):#06x}, not the "
        f"measurement this file states")
    assert read(A_scenery_band_offset) < 0x8000, "the band's offset has not wrapped positive"


@pytest.mark.parametrize("distance", (SCENERY_PEAK_DISTANCE, SCENERY_PEAK_DISTANCE + 1))
def test_scenery_at_the_band_height_the_game_reaches(scenery_window_pokes, distance):
    """The last GROWING frame and the first SHRINKING one, at six whole rows and a wrapped offset.

    What this adds to the poked cases is scale and placement together: 24 columns of whole tile row
    and four of partial, 30,912 bytes of screen written through an address the routine computed
    from a sign-extended word — which is why `make guarded` is the bound on it rather than a
    comment. It is also the only case in the file whose band spans a screen-ring wrap.
    """
    _run(ENTRY_LEVEL2_SCENERY, lambda lib, buf: lib.g_level2_scenery_effect(buf),
         pokes=scenery_window_pokes[distance], max_insns=SCENERY_MAX_INSNS,
         note=f"the game's own band at level_distance {distance:#x}")


@pytest.mark.parametrize("chunk", range(6))
def test_scenery_fuzz(chunk):
    """The window, the counters and the tile ids together — the arms above one at a time, and the
    combinations the game's own frame sequence would take days to reach."""
    rng = random.Random(0x5cede + chunk)
    for _ in range(12):
        _scenery_case(rng.randrange(SCENERY_WINDOW_START - 4, SCENERY_WINDOW_END + 4),
                      rows=rng.randrange(4), partial=rng.randrange(SCENERY_BAND_ROWS_MAX + 1),
                      offset=rng.choice((SCENERY_BAND_OFFSET_SEED, 0x8400, 0xfe00, 0x200)),
                      tile_ids=bytes(rng.randrange(0x20, 0x40) for _ in range(24)))


@pytest.mark.parametrize("level", (0, SCENERY_GATE_LEVEL, 3, 0xffff))
def test_the_scenery_gate_is_level_2_alone(level):
    """The frame loop's call. Level 2 runs the effect, every other level returns having done
    nothing — including the levels whose `level_distance` is inside the window, which is why the
    gate is a routine of its own rather than a test inside the effect."""
    pokes = _scenery_pokes(SCENERY_WINDOW_START + 2, offset=SCENERY_BAND_OFFSET_SEED,
                           rows=1, partial=2)
    pokes[A_level_number] = (level & U16).to_bytes(WORD, "big")
    _run(ENTRY_LEVEL2_SCENERY_GATE, lambda lib, buf: lib.g_level2_scenery_effect_gate(buf),
         pokes=pokes, max_insns=SCENERY_MAX_INSNS, note=f"gate at level {level}")


# =================================================================================================
# debug_wait_for_keypad4 @ 0x11ba2
# =================================================================================================


@pytest.mark.parametrize("arrival", (1, 2, 5, 40))
def test_debug_wait_for_keypad4(arrival):
    """It writes nothing at all, so the ONLY thing this case can compare is how many times it read
    the byte — which the kit does by counting the oracle's scheduled arrivals at the wait PC against
    the candidate's `sched_poll8` calls at the same one. `arrival = 1` is "the key is already down",
    expressed as a store that lands before the first read so that both sides count it."""
    _run(ENTRY_DEBUG_WAIT_KEYPAD4, lambda lib, buf: lib.g_debug_wait_for_keypad4(buf),
         pokes={A_key_bits: b"\x00"},
         schedule=[{"pc": DEBUG_WAIT_KEY_PC, "nth": arrival, "addr": A_key_bits,
                    "width": 1, "value": 1 << CHEAT_ARM_KEY_BIT}],
         note=f"keypad '4' down at read {arrival}")


def test_debug_wait_for_keypad4_ignores_the_other_key_bits():
    """Bit 0 and nothing else: the byte carries pause, abort and the bomb key too, and a wait that
    tested the whole byte would end on any of them."""
    _run(ENTRY_DEBUG_WAIT_KEYPAD4, lambda lib, buf: lib.g_debug_wait_for_keypad4(buf),
         pokes={A_key_bits: b"\xfe"},
         schedule=[{"pc": DEBUG_WAIT_KEY_PC, "nth": 3, "addr": A_key_bits, "width": 1,
                    "value": 0xff}],
         note="every bit but 0 held on entry")


# =================================================================================================
# hiscore_name_entry @ 0x10916, slice [0x10916, 0x10720)
# =================================================================================================

NAME_ENTRY_MAX_INSNS = 400_000
# `check_cheat_name`'s arm spin, which the confirming case runs through. Its schedule is what makes
# that spin end; without one the oracle would run 5001 passes and the candidate's polls would be
# compared against no arrivals at all (STATUS.md, "Follow-ups the kit should absorb").
CHEAT_ARM_SCHEDULE = [{"pc": CHEAT_ARM_WAIT_PC, "nth": 1, "addr": A_key_bits, "width": 1,
                       "value": 0}]


def _name_address(rank, cursor=0):
    return A_hiscore_table + rank * HISCORE_STRIDE + HISCORE_NAME + cursor


def _name_entry_case(stick=0, done=0, first_pass=0, cursor=0, rank=0, timeout=1, name=None,
                     const_word_zero=None, note="", **kwargs):
    pokes = {A_joy1_state: bytes([stick]),
             A_name_entry_done: done.to_bytes(WORD, "big"),
             A_name_entry_first_pass: first_pass.to_bytes(WORD, "big"),
             A_name_entry_cursor: (cursor & U16).to_bytes(WORD, "big"),
             A_hiscore_rank: (rank & U16).to_bytes(WORD, "big"),
             A_name_entry_timeout: (timeout & U16).to_bytes(WORD, "big"),
             A_new_hiscore_pending: b"\xde\xad"}
    if name is not None:
        pokes[_name_address(rank & U16)] = name
    if const_word_zero is not None:
        pokes[A_const_words_0123] = const_word_zero.to_bytes(WORD, "big")
    _run(ENTRY_HISCORE_NAME_ENTRY, lambda lib, buf: lib.g_hiscore_name_entry(buf),
         pokes=pokes, stop_pc=STOP_HISCORE_NAME_ENTRY, max_insns=NAME_ENTRY_MAX_INSNS,
         note=note or f"stick={stick:#04x} done={done} first={first_pass} cursor={cursor}",
         **kwargs)


STICK_NEXT = 1 << NAME_ENTRY_NEXT_GLYPH_BIT
STICK_PREV = 1 << NAME_ENTRY_PREV_GLYPH_BIT
STICK_FIRE = 1 << JOY_FIRE_BIT


def test_name_entry_fills_the_name_with_spaces_once():
    """`first_pass` clear: the three glyphs are set to SPACE and the flag is `st` — a BYTE store into
    a word the `tst.w` reads, so it leaves 0xff00 and not 0xffff. The name is poked to three other
    glyphs so the fill is visible."""
    _name_entry_case(name=b"\x11\x22\x33", note="the first pass")


def test_name_entry_does_not_refill_on_later_frames():
    """With the flag already set the glyphs are left alone, which is what makes the name survive
    between frames at all."""
    _name_entry_case(first_pass=0xff00, name=b"\x11\x22\x33", note="a later pass")


@pytest.mark.parametrize("glyph", (GLYPH_A, GLYPH_A + 1, GLYPH_SPACE - 1, GLYPH_SPACE))
@pytest.mark.parametrize("cursor", range(HISCORE_NAME_CHARS))
def test_name_entry_steps_the_glyph_forward(glyph, cursor):
    """Stick right: +1, and SPACE wraps to 'A' rather than stepping past it. Driven at every cursor
    position, because the cursor is added to the name address with a sign-extending `adda.w`."""
    name = bytearray(b"\x00" * HISCORE_NAME_CHARS)
    name[cursor] = glyph
    _name_entry_case(stick=STICK_NEXT, first_pass=0xff00, cursor=cursor, name=bytes(name),
                     note=f"right from {glyph:#04x} at cursor {cursor}")


@pytest.mark.parametrize("glyph", (GLYPH_A, GLYPH_A + 1, GLYPH_SPACE))
def test_name_entry_steps_the_glyph_back(glyph):
    """Stick left: -1, and 'A' wraps to SPACE. Right is tested BEFORE left in the original, so a
    stick holding both moves forward — the case below."""
    name = bytes([glyph, 0, 0])
    _name_entry_case(stick=STICK_PREV, first_pass=0xff00, name=name,
                     note=f"left from {glyph:#04x}")


def test_name_entry_takes_right_over_left():
    """Both directions held. The arms are an if/else chain in the original's order, so right wins
    and left is never reached — and the sound is played once, not twice."""
    _name_entry_case(stick=STICK_NEXT | STICK_PREV, first_pass=0xff00, name=b"\xb0\x00\x00",
                     note="right and left together")


def test_name_entry_takes_a_direction_over_fire():
    """Fire is tested LAST, so a stick pushed and pressed at once steps the glyph and does not
    advance the cursor."""
    _name_entry_case(stick=STICK_NEXT | STICK_FIRE, first_pass=0xff00, name=b"\xb0\x00\x00",
                     note="right and fire together")


def test_name_entry_does_nothing_with_the_stick_centred():
    """No direction, no button: the routine falls through every arm and branches back into the
    attract loop having written only the first-pass fill."""
    _name_entry_case(first_pass=0xff00, name=b"\xb0\xb1\xb2", note="stick centred")


@pytest.mark.parametrize("cursor", (0, 1))
def test_name_entry_confirms_a_glyph_and_carries_it_forward(cursor):
    """Fire below the last position: the glyph just entered is COPIED INTO THE NEXT one, so the
    following initial starts as this one rather than as a space — the space fill happens once per
    name, not once per glyph — and the cursor advances."""
    name = bytes([0xb0 + i for i in range(HISCORE_NAME_CHARS)])
    _name_entry_case(stick=STICK_FIRE, first_pass=0xff00, cursor=cursor, name=name,
                     note=f"fire at cursor {cursor}")


def test_name_entry_confirms_the_last_glyph():
    """The third fire runs `check_cheat_name` over the three initials — with the arm key UP, so the
    cheat spin runs its full 5001 passes and matches nothing — and sets `name_entry_done`, another
    `st` into a word. The schedule is what lets that spin end on both sides."""
    _name_entry_case(stick=STICK_FIRE, first_pass=0xff00, cursor=NAME_ENTRY_LAST_CURSOR,
                     name=b"\xb0\xb1\xb2", schedule=CHEAT_ARM_SCHEDULE,
                     note="the confirming fire")


def test_name_entry_confirms_a_cheat_name():
    """The same fire with the arm key DOWN and "HSC" in the three initials: `check_cheat_name`
    matches, sets its flag and runs the invulnerability handler. The whole of that is the hud
    subsystem's core, called from here — this case is what says this routine really calls it."""
    _name_entry_case(stick=STICK_FIRE, first_pass=0xff00, cursor=NAME_ENTRY_LAST_CURSOR,
                     name=b"\xb7\xbd\xad",
                     schedule=[{"pc": CHEAT_ARM_WAIT_PC, "nth": 1, "addr": A_key_bits,
                                "width": 1, "value": 1 << CHEAT_ARM_KEY_BIT}],
                     note="the cheat name HSC")


@pytest.mark.parametrize("rank", (0, 1, 5))
def test_name_entry_writes_into_the_rank_it_is_given(rank):
    """`muls.w #$16,d0` on `hiscore_rank`, so the name goes into that row of the table and no
    other. Rank 5 is the lowest row, which is where a score that only just beat the table lands."""
    _name_entry_case(stick=STICK_NEXT, first_pass=0xff00, rank=rank, name=b"\xb0\x00\x00",
                     note=f"rank {rank}")


@pytest.mark.parametrize("timeout", (2, 1, 0, 0x8000))
def test_name_entry_counts_the_finished_name_down(timeout):
    """With `name_entry_done` set the routine only decrements. At -1 — and the test is a SIGN test,
    so 0x8000 steps to 0x7fff and is still positive — it resets `new_hiscore_pending` out of
    `const_words_0123`, the cursor, the done flag and the timeout, and the attract loop resumes."""
    _name_entry_case(done=0xff00, timeout=timeout, note=f"timeout {timeout:#x}")


def test_name_entry_resets_the_pending_flag_out_of_the_const_word_table():
    """`move.w $176ac,$176e8` @ 0x10a04 is a READ of `const_words_0123[0]`, not a `clr.w`.

    The table's first word is 0 in the shipped .PRG, so the reset writes 0 over the poisoned
    `new_hiscore_pending` whether the candidate reads the table or spells a literal — the two are
    indistinguishable on every other case in this file. Poking the table entry to something else is
    what separates them, and the routine then writes THAT: an immediate 0 would fail here, and so
    would a read of the wrong table slot.
    """
    _name_entry_case(done=0xff00, timeout=0, const_word_zero=0x1234,
                     note="const_words_0123[0] rewritten")


@pytest.mark.parametrize("chunk", range(6))
def test_name_entry_fuzz(chunk):
    """Every combination of the stick, the two flags, the cursor and the rank, over glyphs the
    shipped table does not hold. The confirming arm is excluded: it calls into `check_cheat_name`,
    whose own wait needs a schedule, and the cases above drive it deliberately."""
    rng = random.Random(0x1105c + chunk)
    for _ in range(14):
        cursor = rng.randrange(NAME_ENTRY_LAST_CURSOR)
        stick = rng.choice((0, STICK_NEXT, STICK_PREV, STICK_FIRE, STICK_NEXT | STICK_PREV,
                            STICK_NEXT | STICK_FIRE, 0xff, 0x33))
        _name_entry_case(stick=stick, done=rng.choice((0, 0xff00)),
                         first_pass=rng.choice((0, 0xff00)), cursor=cursor,
                         rank=rng.randrange(6), timeout=rng.randrange(0x10000),
                         name=bytes(rng.randrange(0xab, 0xd0) for _ in range(HISCORE_NAME_CHARS)))


# =================================================================================================
# The pins
# =================================================================================================

MIRROR_HEADER = "include/frontend.h"
MIRRORS = (
    "A_level_bank_digits", "LEVEL_BANK_DIGITS", "HSC_NAME_DIGIT", "MAP_NAME_DIGIT",
    "TITLE_SCROLL_POS_START",
    "A_scenery_band_offset", "A_scenery_band_rows", "A_scenery_band_partial",
    "A_charset_order_table", "SCENERY_WINDOW_START", "SCENERY_WINDOW_GROW", "SCENERY_WINDOW_END",
    "SCENERY_BAND_OFFSET_SEED", "SCENERY_BAND_ROWS_MAX", "SCENERY_GROW_OFFSET_STEP",
    "SCENERY_SHRINK_ROW_STEP", "SCENERY_COLUMNS",
    "SCENERY_GATE_LEVEL", "DEBUG_WAIT_KEY_PC",
    "A_name_entry_first_pass", "A_name_entry_cursor", "NAME_ENTRY_LAST_CURSOR",
    "NAME_ENTRY_NEXT_GLYPH_BIT", "NAME_ENTRY_PREV_GLYPH_BIT",
    ("A_file_rec_level_map", "include/globals.h", "A_file_rec_level_map"),
    ("A_file_rec_hsc_0", "include/globals.h", "A_file_rec_hsc_0"),
    ("A_file_rec_hsc_1", "include/globals.h", "A_file_rec_hsc_1"),
    ("A_file_rec_hsc_2", "include/globals.h", "A_file_rec_hsc_2"),
    ("A_file_rec_hsc_3", "include/globals.h", "A_file_rec_hsc_3"),
    ("FILE_REC_NAME", "include/globals.h", "FILE_REC_NAME"),
    ("A_hiscore_table", "include/hud.h", "A_hiscore_table"),
    ("HISCORE_STRIDE", "include/hud.h", "HISCORE_STRIDE"),
    ("HISCORE_NAME", "include/hud.h", "HISCORE_NAME"),
    ("HISCORE_NAME_CHARS", "include/hud.h", "HISCORE_NAME_CHARS"),
    ("GLYPH_A", "include/hud.h", "GLYPH_A"),
    ("GLYPH_SPACE", "include/hud.h", "GLYPH_SPACE"),
    ("A_hiscore_rank", "include/hud.h", "A_hiscore_rank"),
    ("A_name_entry_done", "include/hud.h", "A_name_entry_done"),
    ("A_name_entry_timeout", "include/hud.h", "A_name_entry_timeout"),
    ("A_new_hiscore_pending", "include/hud.h", "A_new_hiscore_pending"),
    ("A_joy1_state", "include/irq.h", "A_joy1_state"),
    ("JOY_FIRE_BIT", "include/hud.h", "JOY_FIRE_BIT"),
    ("A_key_bits", "include/irq.h", "A_key_bits"),
    ("CHEAT_ARM_KEY_BIT", "include/hud.h", "CHEAT_ARM_KEY_BIT"),
    ("CHEAT_ARM_WAIT_PC", "include/hud.h", "CHEAT_ARM_WAIT_PC"),
    ("A_const_words_0123", "include/hud.h", "A_const_words_0123"),
    ("CONST_WORD_BYTES", "include/hud.h", "CONST_WORD_BYTES"),
    ("A_level_number", "include/player.h", "A_level_number"),
    ("A_level_distance", "include/scroll.h", "A_level_distance"),
    ("A_scroll_pos", "include/scroll.h", "A_scroll_pos"),
    ("A_scroll_fine", "include/scroll.h", "A_scroll_fine"),
    ("A_map_row_ptr", "include/scroll.h", "A_map_row_ptr"),
    ("A_prescroll_flag", "include/scroll.h", "A_prescroll_flag"),
    ("A_prescroll_frames", "include/scroll.h", "A_prescroll_frames"),
)

# TEN BYTES, for the reason `test_sprite.py` gives: this program's routines open on a `lea` or a
# `move` of an absolute long, and a shorter pin would match dozens of addresses.
ENTRY_PROLOGUES = {
    "ENTRY_PATCH_FILENAMES": "41f9000162d43200c1fc",
    "ENTRY_TITLE_PRESCROLL": "33f9000176ac00017758",
    "ENTRY_LEVEL2_SCENERY": "0c7908a20001779a6d00",
    "ENTRY_LEVEL2_SCENERY_GATE": "0c7900020001642a6604",
    "ENTRY_DEBUG_WAIT_KEYPAD4": "48e7fffe083900000001",
    "ENTRY_HISCORE_NAME_ENTRY": "4a79000176dc660000b4",
}
STOP_PROLOGUES = {
    "STOP_PATCH_FILENAMES": "41f90001634661000880",
    "STOP_TITLE_PRESCROLL": "303c0004610020386100",
    "STOP_HISCORE_NAME_ENTRY": "6000fe724239000177cc",
}
