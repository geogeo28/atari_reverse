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
* THE TITLE FLOW is all four at once: five slices whose every exit is a branch, so each is diffed at
  a checkpoint PC; a spin on `joy1_state` that only the scheduled-write model can end; a
  `render_frame` in the middle of it that writes the screen ring through computed addresses; and
  three whole-loop cases that run the ORIGINAL's own loop for several passes against
  `title_attract_loop`'s C, which is where the loop STRUCTURE is verified rather than its pieces.
"""
import ctypes
import functools
import pathlib
import random
import re

import pytest

import abi
import conftest
import emu
import harness    # ...which also puts tools/ on sys.path, for the kit import below
import recreate_kit

# ---- load_level_assets @ 0x10332, whole; its head is the SLICE [0x10332, 0x10372) ---------------
ENTRY_LOAD_LEVEL_ASSETS = 0x10332
STOP_PATCH_FILENAMES = 0x10372

# ---- title_attract_loop @ 0x104f2, SLICE [0x104f2, 0x1054a) -------------------------------------
# Both ends double as checkpoints of the loop's own exits — see "The title flow" below. The far one
# is `conftest.ENTRY_ATTRACT_START_TUNE`: `test_scroll.py` diffs the prescroll at the same address,
# so it is declared and PINNED once, in conftest, rather than under a second name here.
ENTRY_TITLE_PRESCROLL = 0x104f2

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
LEVEL_ASSETS_ORDER_LEVEL_2 = 2
LEVEL_ASSETS_ORDER_LEVEL_3 = 3
DISC_SWAP_ABOVE_LEVEL = 3
A_disc_prompt_message = 0x16022
DISC_PROMPT_WAIT_PC = 0x103d6
A_title_just_entered = 0x17698
A_attract_page_timer = 0x176e6
A_attract_page_reload = 0x1771e
A_text_publisher = 0x160de
A_text_credits = 0x16146
A_text_title_mode = 0x16120
A_title_word_hard = 0x1612e
ATTRACT_TUNE = 4
ATTRACT_END_SCROLL_POS = 0xbb8
ATTRACT_PAGE_HALL_OF_FAME_BELOW = 0xc8
ATTRACT_PAGE_CREDITS_BELOW = 0x226
TITLE_MODE_WORD_OFFSET = 10
TITLE_MODE_WORD_BYTES = 4
TITLE_MODE_EASY_BIT = 2
TITLE_MODE_HARD_BIT = 3
TITLE_HARD_MODE_ON = 1

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
LEVELS = 5                        # include/player.h
A_level_distance = 0x1779a        # include/scroll.h
A_file_rec_sprites_cru = 0x1631a  # include/globals.h
FIRE_RELEASE_WAIT_PC = 0x149f0    # include/hud.h — inside `console_show_message`
A_scroll_pos = 0x17758            # include/scroll.h
A_scroll_fine = 0x16430           # include/scroll.h
A_map_row_ptr = 0x16402           # include/scroll.h
A_prescroll_flag = 0x1642c        # include/scroll.h
A_prescroll_frames = 0x17752      # include/scroll.h
SCC_TRUE = 0xff                   # include/common.h
A_sound_module = 0x58944          # include/globals.h
A_entity_arena = 0x59984          # include/globals.h
SND_MUSIC_ACTIVE = 0x1e           # include/sound.h
A_enemy_bullets = 0x1946e         # include/weapons.h
A_display_list = 0x177ce          # include/display_list.h
A_level0_assets_loaded = 0x176ea  # include/init.h
A_hard_mode = 0x177cc             # include/hud.h
A_title_word_easy = 0x16132       # include/hud.h

WORD = 2
U16 = 0xffff

abi.declare_glue("g_title_attract_prescroll", "g_level2_scenery_effect",
                 "g_level2_scenery_effect_gate", "g_debug_wait_for_keypad4",
                 "g_hiscore_name_entry", "g_title_attract_start_tune", "g_title_attract_loop")
abi.declare_glue("g_load_level_assets_patch_filenames", "g_load_level_assets", args=1)
# The three title-flow cores answer with the branch they took (`include/frontend.h`'s enums), so
# their glue has a RESULT — which ctypes would otherwise read as an `int` it was never told about.
abi.declare_glue("g_enter_title", "g_title_attract_poll", "g_title_frame_step",
                 result=ctypes.c_uint32)

_run = abi.run_case          # the project's one case shape (`test/abi.py`)


# =================================================================================================
# load_level_assets @ 0x10332, head slice [0x10332, 0x10372) — the filename patch
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
    _run(ENTRY_LOAD_LEVEL_ASSETS, lambda lib, buf: lib.g_load_level_assets_patch_filenames(buf, level),
         pokes=pokes, regs={"d0": level}, stop_pc=STOP_PATCH_FILENAMES, poison=poison,
         note=f"level={level}")


@pytest.mark.parametrize("level", range(LEVELS))
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
# load_level_assets @ 0x10332, whole — the level's five files
# =================================================================================================
#
# EVERY FILE IS STAGED WITH CONTENT THE IMAGE DOES NOT ALREADY HOLD, for `test_init.py`'s reason:
# the post-load fixture has level 0's five files at their destinations already, so staging the REAL
# bytes would let a reconstruction that copied nothing agree over every byte. The content is
# pseudo-random and of the file's own on-disc length, which is what makes the `Fread` visible and
# what keeps `A\LEVEL1.MAP`'s short read short (its record asks for more than the file holds —
# ../STATUS.md, init 0x10bfa).
#
# THE PATHS ARE THE PATCHED ONES. The routine rewrites a digit inside each of the five names before
# it opens them, so a case for level 4 must stage "A\HSC_8.DAT" and not "A\HSC_0.DAT" — and staging
# the wrong name is not a soft failure: the model REFUSES an `Fopen` of a path nothing staged, and
# the kit throws the run away by name.

LEVEL_ASSETS_MAX_INSNS = 400_000


def _signed(value):
    """`value` as the 68000 reads a word in a `blt` — the routine's level tests are signed."""
    return value - 0x10000 if value & 0x8000 else value


LOAD_LEVEL_ASSETS_RECORDS = BANK_RECORDS + (A_file_rec_level_map,)

# The two waits the level-4 prompt makes: fire RELEASED inside `console_show_message`, then fire
# PRESSED at the routine's own spin. `probe_disc` after them opens A\SPRITES.cru, which is why that
# record is staged too on this arm alone.
DISC_PROMPT_SITES = [FIRE_RELEASE_WAIT_PC, DISC_PROMPT_WAIT_PC]


STICK_ALL_DIRECTIONS = 0xff & ~(1 << JOY_FIRE_BIT)   # every bit of the byte but the fire button's


def _disc_prompt_schedule(held, released=0, pressed=1 << JOY_FIRE_BIT):
    """The agent that ends both waits, given whether the button is DOWN on entry.

    With it up the release wait ends on its first read and needs no store at all — the site is
    declared and its one arrival is compared against the candidate's one poll. With it down that
    wait has to see it go up first, which is a store of its own and shifts the press by one.

    `released` and `pressed` are the BYTES the two stores land, and they are parameters because both
    waits are BIT tests (`btst #7,$1777f`) on a byte that also carries four directions: with the
    directions always clear, "the fire bit is set" and "the byte is non-zero" are the same predicate
    and a reconstruction spelling either one passes. The two cases below give them a stick.
    """
    schedule = []
    if held:
        schedule.append({"pc": FIRE_RELEASE_WAIT_PC, "nth": 2, "addr": A_joy1_state,
                         "width": 1, "value": released})
    schedule.append({"pc": DISC_PROMPT_WAIT_PC, "nth": 3 if held else 2, "addr": A_joy1_state,
                     "width": 1, "value": pressed})
    return schedule


# How many bytes each record's file is staged with: as many as LEVEL 0's file for that record holds.
# Every HSC bank is one length and every level map another, so this is the right count for any level
# — and it is a COUNT rather than a file because a level's patched name need not name a file on disc
# at all, which is exactly what an out-of-range level produces. Memoised per record, because reading
# the four 32 KB banks off disc once a case is the most expensive thing in this battery.
_level0_file_bytes = {}


def _staged_bytes(post_load_image, record, seed):
    if record not in _level0_file_bytes:
        _dest, record_length, dos_path = conftest.file_record(post_load_image, record)
        _level0_file_bytes[record] = len(
            conftest.disk_bytes(dos_path.rsplit("\\", 1)[-1].upper(), record_length))
    return conftest.seeded_bytes(_level0_file_bytes[record], seed)


def _digit_row(level):
    """Where `muls.w #$5,d0` puts the level's five digits. SIGNED, and with no floor or ceiling."""
    return A_level_bank_digits + _signed(level) * LEVEL_BANK_DIGITS


def _level_assets_pokes(post_load_image, level, extra_records=(), digits=None):
    """The five files `level` names, staged, plus any extra record the case's arm also opens.

    The names come out of `A_level_bank_digits` rather than being spelt, so this says what the
    ROUTINE will do rather than restating the shipped table — which matters for level 3, whose row
    is "013B4" and not five consecutive digits. `digits` replaces the row, which is how a level
    whose row is not five printable bytes (an out-of-range one) can be staged at all.
    """
    image = bytearray(post_load_image)
    row = _digit_row(level)
    if digits is not None:
        image[row:row + LEVEL_BANK_DIGITS] = digits
    patched = bytes(image[row:row + LEVEL_BANK_DIGITS])
    for record, digit in zip(BANK_RECORDS, patched[:len(BANK_RECORDS)]):
        image[record + FILE_REC_NAME + HSC_NAME_DIGIT] = digit
    image[A_file_rec_level_map + FILE_REC_NAME + MAP_NAME_DIGIT] = patched[-1]

    staged = []
    for index, record in enumerate(LOAD_LEVEL_ASSETS_RECORDS + tuple(extra_records)):
        _dest, _record_length, dos_path = conftest.file_record(image, record)
        staged.append((dos_path, _staged_bytes(post_load_image, record, (level << 8) | index)))
    pokes, _handles = harness.stage_files(staged)
    if digits is not None:
        pokes[row] = digits
    # The digits inside the NAMES are poisoned, so a candidate that skipped the patch would ask for
    # the names the .PRG ships and be refused rather than quietly reading level 0's files.
    for address in FILENAME_DIGITS:
        pokes[address] = b"\xde"
    return pokes


def _level_assets_case(post_load_image, level, note, stick=0, digits=None, **arrivals):
    prompts = _signed(level) > DISC_SWAP_ABOVE_LEVEL
    extra = (A_file_rec_sprites_cru,) if prompts else ()
    pokes = _level_assets_pokes(post_load_image, level, extra, digits)
    pokes[A_joy1_state] = bytes([stick])
    held = (stick >> JOY_FIRE_BIT) & 1
    _run(ENTRY_LOAD_LEVEL_ASSETS, lambda lib, buf: lib.g_load_level_assets(buf, level),
         pokes=pokes, regs={"d0": level}, max_insns=LEVEL_ASSETS_MAX_INSNS,
         schedule=_disc_prompt_schedule(held, **arrivals) if prompts else None,
         wait_sites=DISC_PROMPT_SITES if prompts else None, note=note)


@pytest.mark.parametrize("level", range(LEVELS))
def test_load_level_assets_loads_every_levels_five_files(level, post_load_image):
    """All five stages, each through its own arm of the dispatch: levels 0 and 1 share the ordinary
    arm, 2 and 3 have one apiece, and 4 takes the ordinary arm THROUGH the one disc prompt the build
    has left. The two lettered arms are the same five loads in the same order — the original carries
    the block twice — so driving both is what says the copies agree, and both of them RE-READ
    A\\HSC_0.DAT, which the head has already loaded."""
    _level_assets_case(post_load_image, level, f"level {level}")


@pytest.mark.parametrize("level", (0xffff, 0xfffe))
def test_load_level_assets_reads_the_level_as_a_SIGNED_word(level, post_load_image):
    """A NEGATIVE level takes the ordinary arm and skips the disc prompt, because `cmp.w #$3,d1 /
    blt.w $103f0` @ 0x103c4 is a SIGNED test. Read unsigned, 0x8000 and 0xffff are both "past 3" and
    the routine would stop for a disc swap that never comes — a mutation that spells the compare
    unsigned SURVIVED every other case in this file, because no in-range level is negative.

    The digit row a negative level indexes (five bytes BELOW the table per step, `muls.w #$5` being
    signed) is poked to level 0's, so the five names it patches are ones this case can stage.
    Nothing about the arm depends on which names they are. A level far enough negative to index off
    the image is not driven, for `test_patch_filenames_indexes_the_digit_table_with_a_signed_
    multiply`'s reason: there the original reads memory the model does not have."""
    _level_assets_case(post_load_image, level, f"level {level:#06x}, signed", digits=b"01231")


def test_load_level_assets_waits_out_the_one_disc_prompt_the_build_has_left(post_load_image):
    """Level 4's arm with the stick DOWN on entry, so that both of the prompt's waits really run:
    the release wait inside `console_show_message` takes two reads to see the button go up, and the
    press spin three more to see it come back down. Five of the six prompts in this routine were
    patched out (each `lea <message>,a6` head overwritten with a `bra.s` past the block); this is
    the survivor, and its own retry was patched too, so it asks once and proceeds whatever
    `probe_disc` answers. The message it shows is empty: 0x16022 is the middle of a word table."""
    _level_assets_case(post_load_image, LEVELS - 1, "the disc prompt, button held on entry",
                       stick=1 << JOY_FIRE_BIT)


def test_the_disc_prompts_press_spin_tests_the_FIRE_BIT_and_not_the_whole_byte(post_load_image):
    """The press spin @ 0x103d6 is `btst #7,$1777f`, and every other case reaches it over a byte
    whose four direction bits are clear — so "bit 7 is set" and "the byte is non-zero" agree on all
    of them and a reconstruction spelling the second passes. Here the player is holding a direction
    while the prompt is up: the spin must read 0x7f and go round again, and only the 0xff the agent
    stores may end it. A `!= 0` test ends the wait one poll early, and the poll counts differ."""
    _level_assets_case(post_load_image, LEVELS - 1, "a direction held under the prompt",
                       stick=STICK_ALL_DIRECTIONS, pressed=0xff)


def test_the_disc_prompts_release_wait_tests_the_FIRE_BIT_and_not_the_whole_byte(post_load_image):
    """The other half of the same argument, one wait up: `console_show_message`'s release spin
    @ 0x149f0 must end when the FIRE bit goes clear, not when the byte does. The stick enters with
    everything held, the agent lets go of the button alone (0xff -> 0x7f), and only then does the
    press spin start — which the 0xff at its own third poll ends."""
    _level_assets_case(post_load_image, LEVELS - 1, "everything held, then fire alone released",
                       stick=0xff, released=STICK_ALL_DIRECTIONS, pressed=0xff)


# =================================================================================================
# title_attract_loop @ 0x104f2, slice [0x104f2, 0x1054a)
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
         pokes=pokes, stop_pc=conftest.ENTRY_ATTRACT_START_TUNE, max_insns=TITLE_PRESCROLL_MAX_INSNS,
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
# The title flow: enter_title @ 0x1030e, and title_attract_loop's three slices with title_frame_step
# =================================================================================================
#
# FOUR ADDRESSES, EACH THE ENTRY OF ONE SLICE AND THE CHECKPOINT OF ANOTHER'S EXIT — which is what
# a loop whose every exit is a branch looks like when it is cut into cores. 0x104f2 is the stage
# start's entry and the frame step's "the scroll ran out" checkpoint; 0x1054a is the jingle's entry,
# the stage start's stop and the poll's "the tune ended" checkpoint; 0x10562 is the poll's entry and
# the frame step's "carry on" checkpoint; 0x10594 is the frame step's entry and the poll's "draw the
# next frame" checkpoint. One constant apiece rather than an ENTRY_ and a STOP_ at each address.
#
# THE SPIN IS A WAIT ON THE STICK, so every case that reaches the `btst #7,$1777f` declares
# `conftest.TITLE_FIRE_WAIT_PC` — with a schedule when the button has to come down mid-run, and as
# a bare `wait_sites` when it does not. Declaring it either way is what makes the kit count the oracle's
# arrivals against the candidate's `sched_poll8` calls; a run that reached the site without
# declaring it would have the candidate's poll REFUSED instead of counted.

ENTRY_ENTER_TITLE = 0x1030e
STOP_ENTER_TITLE_LOAD = 0x1032a   # `bsr.w load_level_assets` with D0 = 0 — the arm's exit
ENTRY_TITLE_POLL = 0x10562
ENTRY_TITLE_FRAME_STEP = 0x10594

TITLE_POLL_MAX_INSNS = 400_000
# One attract frame is a whole `render_frame`; the flow cases below draw several and prescroll
# between them.
TITLE_FRAME_MAX_INSNS = 2_000_000
TITLE_FLOW_MAX_INSNS = 40_000_000
# The 108-frame prescroll and the jingle, run by the ORIGINAL to build the machine the frame step
# and the whole-flow cases run on.
ATTRACT_START_MAX_INSNS = 12_000_000

# The three exits `title_attract_poll` answers with, and the two `title_frame_step` does —
# `include/frontend.h`'s enums, in declaration order.
TITLE_POLL_NEXT_FRAME, TITLE_POLL_START_GAME, TITLE_POLL_TUNE_ENDED = 0, 1, 2
TITLE_FRAME_POLL_AGAIN, TITLE_FRAME_ATTRACT_OVER = 0, 1
ENTER_TITLE_LOAD_LEVEL0, ENTER_TITLE_ATTRACT = 0, 1

STICK_EASY = 1 << TITLE_MODE_EASY_BIT
STICK_HARD = 1 << TITLE_MODE_HARD_BIT

A_title_mode_word = A_text_title_mode + TITLE_MODE_WORD_OFFSET


def word(value):
    return (value & U16).to_bytes(WORD, "big")


# ---- enter_title @ 0x1030e ----------------------------------------------------------------------

def _enter_title_case(assets_loaded=None, stop_pc=ENTRY_TITLE_PRESCROLL, note=""):
    """`title_just_entered` is poked clear first, so the `st` that opens the routine is visible over
    a fixture in which the flag could otherwise already be set."""
    pokes = {A_title_just_entered: word(0)}
    if assets_loaded is not None:
        pokes[A_level0_assets_loaded] = assets_loaded
    return _run(ENTRY_ENTER_TITLE, lambda lib, buf: lib.g_enter_title(buf),
                pokes=pokes, stop_pc=stop_pc, poison=True, note=note)


def test_enter_title_falls_into_the_attract_loop_when_level_0_is_loaded():
    """The arm the game itself always takes: the boot chain has already `st`ed
    `A_level0_assets_loaded`, so the routine raises its own flag, blacks the palette and branches
    on. The palette call writes no image byte — the ordered OS event is the whole of it."""
    info = _enter_title_case(note="the flag the boot chain left set")
    assert info["ret"] == ENTER_TITLE_ATTRACT


def test_enter_title_loads_level_0_when_the_flag_is_clear():
    """The other arm, unreachable in an ordinary boot and reached here by poking the word clear: the
    routine `st`s the flag itself and answers with the `bsr load_level_assets` it makes next."""
    info = _enter_title_case(assets_loaded=word(0), stop_pc=STOP_ENTER_TITLE_LOAD,
                             note="level 0's assets not loaded yet")
    assert info["ret"] == ENTER_TITLE_LOAD_LEVEL0


def test_enter_title_tests_the_whole_word_and_not_the_st_byte():
    """`st $176ea` is a BYTE store and `tst.w $176ea` a WORD read, so the flag's LOW byte is part of
    the answer even though nothing ever writes it. With only that byte set the routine takes the
    "already loaded" arm, and a reconstruction that read the `st`'s own byte would load again."""
    info = _enter_title_case(assets_loaded=b"\x00\x01", note="only the low byte set")
    assert info["ret"] == ENTER_TITLE_ATTRACT


# ---- title_attract_loop @ 0x1054a, slice [0x1054a, 0x10562) --------------------------------------

def test_the_attract_start_plays_the_jingle_and_clears_the_three_lists():
    """The tune, the display list, the entity arena and the enemy-bullet array, then the game
    palette. Everything it clears is poked dirty first and the module's "still playing" byte is
    poked clear, so the jingle's own effect on it is visible rather than already there."""
    _run(conftest.ENTRY_ATTRACT_START_TUNE, lambda lib, buf: lib.g_title_attract_start_tune(buf),
         pokes={A_sound_module + SND_MUSIC_ACTIVE: b"\x00",
                A_display_list: b"\xa5" * 0x40,
                A_entity_arena: b"\x5a" * 0x40,
                A_enemy_bullets: b"\x3c" * 0x20},
         stop_pc=ENTRY_TITLE_POLL, max_insns=TITLE_POLL_MAX_INSNS,
         note="the jingle and the three lists")


# ---- title_attract_loop @ 0x10562, slice [0x10562, 0x10594) --------------------------------------

# `hard_mode` poked to a byte NEITHER toggle arm writes (easy writes `const_words_0123`'s high byte,
# hard writes 1), so a pass that took no arm is separable from one that took the wrong one.
HARD_MODE_POISON = 0x5a


def _poll_pokes(pending=0, stick=0, music=SCC_TRUE, timer=None, just_entered=0,
                const_word_zero=None):
    pokes = {A_new_hiscore_pending: word(pending),
             A_joy1_state: bytes([stick]),
             A_sound_module + SND_MUSIC_ACTIVE: bytes([music]),
             A_title_just_entered: word(just_entered),
             A_hard_mode: bytes([HARD_MODE_POISON]),
             A_title_mode_word: b"\xde\xad\xbe\xef"}
    if timer is not None:
        pokes[A_attract_page_timer] = word(timer)
    if const_word_zero is not None:
        pokes[A_const_words_0123] = word(const_word_zero)
    return pokes


def _poll_case(stop_pc=ENTRY_TITLE_FRAME_STEP, note="", schedule=None, **kwargs):
    return _run(ENTRY_TITLE_POLL, lambda lib, buf: lib.g_title_attract_poll(buf),
                pokes=_poll_pokes(**kwargs), stop_pc=stop_pc, max_insns=TITLE_POLL_MAX_INSNS,
                schedule=schedule, wait_sites=[conftest.TITLE_FIRE_WAIT_PC], note=note)


def test_the_poll_starts_a_game_when_fire_is_already_down():
    """The loop's only `rts`. The stick is read through the kit's scheduled-write model with an
    EMPTY schedule — "the button is already down", stated as itself — so the one arrival the
    original makes at the `btst` is compared against the candidate's one poll."""
    info = _poll_case(stick=1 << JOY_FIRE_BIT, stop_pc=0, note="fire held on entry")
    assert info["ret"] == TITLE_POLL_START_GAME


def test_the_poll_starts_a_game_when_fire_arrives():
    """The same exit with the button coming down while the run is in flight rather than held on
    entry. ONE pass of the poll makes ONE read, so an arrival of 2 here would be a store that never
    came due — which is the kit refusing the case, and is why the multi-pass arrivals are the
    whole-loop cases at the foot of this section."""
    info = _poll_case(stop_pc=0, note="fire on the poll's own read",
                      schedule=[{"pc": conftest.TITLE_FIRE_WAIT_PC, "nth": 1, "addr": A_joy1_state,
                                 "width": 1, "value": 1 << JOY_FIRE_BIT}])
    assert info["ret"] == TITLE_POLL_START_GAME


def test_the_poll_ignores_fire_while_a_high_score_is_waiting():
    """`tst.w new_hiscore_pending / bne` skips the `btst` entirely, so the stick is not read at all
    on that arm — zero arrivals against zero polls — and the button cannot start a game over a name
    that has not been entered. The run goes on to the name-entry screen instead."""
    info = _poll_case(pending=1, stick=1 << JOY_FIRE_BIT, note="fire held, a name still to enter")
    assert info["ret"] == TITLE_POLL_NEXT_FRAME


def test_the_poll_restarts_the_jingle_when_the_module_says_it_has_finished():
    """`tst.b 30(a0)` on the sound module — its ONLY "tune finished" signal — and the branch back to
    0x1054a. Nothing is drawn on this pass: the test is made before the scroll step."""
    info = _poll_case(music=0, stop_pc=conftest.ENTRY_ATTRACT_START_TUNE, note="the tune has ended")
    assert info["ret"] == TITLE_POLL_TUNE_ENDED


@pytest.mark.parametrize("timer,page", (
    (1, "hall of fame"),                             # steps to 0, below both thresholds
    (ATTRACT_PAGE_HALL_OF_FAME_BELOW, "hall of fame"),   # steps to 0xc7, the last of that page
    (ATTRACT_PAGE_HALL_OF_FAME_BELOW + 1, "credits"),    # steps to 0xc8, the first of the next
    (ATTRACT_PAGE_CREDITS_BELOW, "credits"),             # steps to 0x225, the last of it
    (ATTRACT_PAGE_CREDITS_BELOW + 1, "publisher"),       # steps to 0x226, the first publisher frame
    (0x8000, "publisher"),   # steps to 0x7fff, which is below NEITHER threshold — the third arm
))
def test_the_poll_publishes_the_page_its_timer_names(timer, page):
    """The page cycle at 0x105a8: the timer down one, then two SIGNED tests on what is left. Both
    thresholds are driven from either side, which is the only thing that separates the three
    scripts — they compile into the same display list from its head. The publisher page also runs
    the mode toggle, which is why `title_just_entered` is poked clear on every one of these."""
    info = _poll_case(timer=timer, note=f"timer {timer:#x} -> {page}")
    assert info["ret"] == TITLE_POLL_NEXT_FRAME


def test_the_page_timer_reloads_when_it_goes_negative():
    """A timer of 0 steps to 0xffff, which is NEGATIVE, so the `bpl` falls through to the reload —
    and the page then chosen is the RELOADED value's, not the 0xffff one's. The shipped reload is
    0x2ee, which is the publisher page."""
    _poll_case(timer=0, note="the timer reloads")


def test_the_page_timer_reload_is_read_and_not_an_immediate():
    """The same arm with `attract_page_reload` poked, so the value the timer comes back with follows
    it and the page the reload lands on changes with it."""
    pokes = _poll_pokes(timer=0)
    pokes[A_attract_page_reload] = word(0x40)
    _run(ENTRY_TITLE_POLL, lambda lib, buf: lib.g_title_attract_poll(buf),
         pokes=pokes, stop_pc=ENTRY_TITLE_FRAME_STEP, max_insns=TITLE_POLL_MAX_INSNS,
         wait_sites=[conftest.TITLE_FIRE_WAIT_PC], note="a poked reload, into the hall of fame")


# The publisher page is the only one the toggle runs on, so every toggle case names its timer.
PUBLISHER_TIMER = ATTRACT_PAGE_CREDITS_BELOW + 1


@pytest.mark.parametrize("stick,note", (
    (0, "the stick centred"),
    (STICK_EASY, "stick left"),
    (STICK_HARD, "stick right"),
    (STICK_EASY | STICK_HARD, "both directions at once"),
))
def test_the_mode_toggle_arms(stick, note):
    """Left copies `title_word_easy` over the mode word and clears `hard_mode`, right copies
    `title_word_hard` and writes a literal 1, and both play the same effect. The ARMS' ORDER is what
    the fourth case pins: left is tested first and wins, which an if/else chain has and two
    independent tests would not. The mode word and `hard_mode` are poked to values neither arm
    writes, so a pass that took no arm is separable from one that took the wrong one."""
    _poll_case(stick=stick, timer=PUBLISHER_TIMER, note=note)


def test_the_mode_toggle_resets_to_easy_silently_when_the_title_was_just_entered():
    """`title_just_entered` takes the EASY arm without the stick, SUPPRESSES its sound effect, and
    then clears itself — so entering the title screen resets the difficulty in silence where the
    stick does it audibly. The sound is an ordered OS event on the module, so the two are separable
    even though the bytes the arm writes are the same."""
    _poll_case(just_entered=0xff00, timer=PUBLISHER_TIMER, note="just entered, stick centred")


def test_the_just_entered_flag_is_a_WHOLE_WORD_on_both_the_test_and_the_clear():
    """`st $17698` is a BYTE store into a word that `tst.w` @ 0x105ee and @ 0x10624 READ WHOLE and
    `clr.w` @ 0x10632 WRITES WHOLE — so the flag's LOW byte is part of both answers even though
    nothing in the program ever sets it. Entered with only that byte up, the toggle must still take
    the silent easy arm and must still leave the word 0x0000: a reconstruction testing the `st`'s
    own byte plays the sound effect instead, and one clearing only that byte leaves 0x00ff behind.
    The sibling `test_enter_title_tests_the_whole_word_and_not_the_st_byte` is the same shape one
    routine up."""
    _poll_case(just_entered=0x00ff, timer=PUBLISHER_TIMER, note="only the flag's low byte set")


def test_the_easy_arm_writes_hard_mode_out_of_the_const_word_table():
    """`move.b $176ac,$177cc` is a READ of `A_const_words_0123`'s HIGH byte, not a `clr.b`. With that
    byte poked non-zero `hard_mode` follows it — and the game would then be in hard mode having been
    told to go easy, which is the original's spelling and not a repair."""
    _poll_case(stick=STICK_EASY, timer=PUBLISHER_TIMER, const_word_zero=0x7700,
               note="const_words_0123[0] high byte poked")


@pytest.mark.parametrize("done", (0, 0xff00))
def test_the_poll_runs_the_name_entry_screen_while_a_high_score_is_pending(done):
    """`bra.w $106f2` @ 0x10590 leaves the loop for `hiscore_show_entry_screen`, which falls into
    `hiscore_name_entry`, whose every arm branches to 0x10594 — the frame step this pass was going
    to reach anyway. So the arm is a CALL of two verified cores and not a fourth exit, and the whole
    hall-of-fame page plus one pass of the name entry is inside this one slice. Both of the name
    entry's halves are driven: the glyph walk (`done` clear) and the countdown (`done` set)."""
    pokes = _poll_pokes(pending=1)
    pokes[A_name_entry_done] = word(done)
    pokes[A_name_entry_first_pass] = word(0xff00)
    pokes[A_name_entry_timeout] = word(4)
    pokes[A_hiscore_rank] = word(2)
    info = _run(ENTRY_TITLE_POLL, lambda lib, buf: lib.g_title_attract_poll(buf),
                pokes=pokes, stop_pc=ENTRY_TITLE_FRAME_STEP, max_insns=TITLE_POLL_MAX_INSNS,
                wait_sites=[conftest.TITLE_FIRE_WAIT_PC], note=f"name entry, done={done:#x}")
    assert info["ret"] == TITLE_POLL_NEXT_FRAME


@pytest.mark.parametrize("chunk", range(4))
def test_the_poll_fuzz(chunk):
    """The three exits, the three pages, the reload and both toggle arms together — every state the
    poll reads, drawn at random, which is how the arms' combinations are covered rather than one at
    a time."""
    rng = random.Random(0x104f2 + chunk)
    for _ in range(8):
        pending = rng.choice((0, 0, 1))
        music = rng.choice((0, SCC_TRUE, SCC_TRUE, SCC_TRUE))
        stick = rng.randrange(0x100) & ~(1 << JOY_FIRE_BIT)
        # The module test is made on BOTH arms of the high-score branch, so a silent tune ends the
        # pass whatever `new_hiscore_pending` says.
        stop = conftest.ENTRY_ATTRACT_START_TUNE if music == 0 else ENTRY_TITLE_FRAME_STEP
        _poll_case(pending=pending, music=music, stick=stick,
                   timer=rng.randrange(0x10000), just_entered=rng.choice((0, 0xff00)),
                   stop_pc=stop, note=f"chunk={chunk} pending={pending} music={music:#x} "
                                      f"stick={stick:#04x}")


# ---- title_frame_step @ 0x10594, slice [0x10594, 0x10562) ----------------------------------------

@functools.lru_cache(maxsize=None)
def _attract_started(post_load_bytes):
    """The machine the attract frame really runs on, built by the ORIGINAL: its own
    [0x104f2, 0x10562) — the black palette, the 108-frame prescroll and the jingle — replayed from
    the post-load fixture. That leaves real terrain in all four screens and the module playing.

    Cached on the fixture's bytes, so the prescroll runs once per session however many cases ask.
    """
    final, _writes, _regs = emu.run(bytearray(post_load_bytes), ENTRY_TITLE_PRESCROLL,
                                    stop_pc=ENTRY_TITLE_POLL, max_insns=ATTRACT_START_MAX_INSNS)
    return bytes(final)


@pytest.fixture(scope="session")
def attract_started_pokes(post_load_image):
    return conftest.byte_run_pokes(post_load_image, _attract_started(bytes(post_load_image)))


def _frame_step_case(attract_started_pokes, scroll_pos, over, note=""):
    pokes = dict(attract_started_pokes)
    pokes[A_scroll_pos] = word(scroll_pos)
    # The budget already spent, so `render_frame` takes its Vsync arm and makes no scheduled wait —
    # the wait itself is `test_sprite.py`'s, and what this slice is about is the compare below it.
    pokes[conftest.A_vbl_tick] = conftest.RENDER_FRAME_VBL_BUDGET.to_bytes(4, "big")
    info = _run(ENTRY_TITLE_FRAME_STEP, lambda lib, buf: lib.g_title_frame_step(buf),
                pokes=pokes,
                stop_pc=ENTRY_TITLE_PRESCROLL if over else ENTRY_TITLE_POLL,
                max_insns=TITLE_FRAME_MAX_INSNS, note=note or f"scroll_pos={scroll_pos:#06x}")
    assert info["ret"] == (TITLE_FRAME_ATTRACT_OVER if over else TITLE_FRAME_POLL_AGAIN)


@pytest.mark.parametrize("scroll_pos,over", (
    (0, False),
    (ATTRACT_END_SCROLL_POS - 1, False),
    (ATTRACT_END_SCROLL_POS, True),
    (ATTRACT_END_SCROLL_POS + 1, True),
    (0x7fff, True),
    (0x8000, False),   # the most negative word: an UNSIGNED compare would restart here
    (0xffff, False),   # ...and so would -1, the other end of the same half of the number line
))
def test_the_frame_step_restarts_the_attract_at_its_own_scroll_position(attract_started_pokes,
                                                                        scroll_pos, over):
    """One whole attract frame, then `cmpi.w #$bb8,$17758 / blt` — a SIGNED compare.

    THE TWO NEGATIVE POSITIONS ARE CONTRACT COVERAGE, and are named as such rather than claimed to
    be the game's own state: `scroll_pos` is seeded 0 by the stage start and `scroll_advance` only
    ever adds 2, so the attract's own run climbs to 0xbb8 and never reaches the far half of the
    number line. (The word that DOES go negative in the first two dozen frames is `level_distance`,
    which this compare does not read — see `test_scenery_does_nothing_below_the_window`, where the
    same shape IS reached by the game.) Poked here because the instruction is signed, and an
    unsigned reading would restart the attract on a position the original carries on from.

    The frame is drawn either way, into the screen ring through addresses the routine computed,
    which is why `make guarded` is the bound here."""
    _frame_step_case(attract_started_pokes, scroll_pos, over)


# ---- the whole loop: title_attract_loop @ 0x104f2 to its `rts` ------------------------------------
#
# THE INTEGRATION PIN, and the shape `test_init.py`'s frame-loop windows have: the cores above are
# each diffed over one pass, and these run the ORIGINAL's own loop for several passes and let the
# reconstruction's loop structure be what agrees or does not. Every one of them ends at the `rts`,
# with the fire button arriving on a poll the case chose.
#
# The prescroll is shortened by poking `A_prescroll_frames`: 108 frames of `render_frame` is what
# `test_title_attract_prescroll_at_the_shipped_frame_count` above already verifies, and paying for
# it again here would buy nothing but minutes.


def _flow_pokes(prescroll_frames=1, scroll_seed=None):
    pokes = {A_joy1_state: b"\x00", A_new_hiscore_pending: word(0),
             conftest.A_vbl_tick: (0).to_bytes(4, "big"),
             A_prescroll_frames: word(prescroll_frames),
             A_attract_page_timer: word(PUBLISHER_TIMER)}
    if scroll_seed is not None:
        pokes[A_const_words_0123] = word(scroll_seed)
    return pokes


def _flow_case(entry, glue, pokes, fire_at, frames, note):
    _run(entry, glue, pokes=pokes, max_insns=TITLE_FLOW_MAX_INSNS,
         schedule=conftest.attract_schedule(fire_at, frames), note=note)


def test_the_whole_attract_loop_from_its_stage_start_to_the_fire_button():
    """The loop the four cores make: the palette blacked, the map rewound and prescrolled, the
    jingle started, three attract frames drawn, and the button on the fourth poll. Nothing in the
    case says where one core ends and the next begins — the oracle runs the original's branches and
    the candidate runs `title_attract_loop`'s C, and the whole image is compared."""
    _flow_case(ENTRY_TITLE_PRESCROLL, lambda lib, buf: lib.g_title_attract_loop(buf),
               _flow_pokes(), fire_at=4, frames=3, note="three attract frames, then fire")


def test_the_whole_flow_from_enter_title():
    """The same with `enter_title` in front of it, which is how the game reaches the title screen:
    `init_new_game` ends `bra.w enter_title`, and the attract loop runs off that call's frame. The
    candidate is the two cores in the order the exit code puts them in."""
    def candidate(lib, buf):
        assert lib.g_enter_title(buf) == ENTER_TITLE_ATTRACT
        lib.g_title_attract_loop(buf)

    _flow_case(ENTRY_ENTER_TITLE, candidate, _flow_pokes(), fire_at=3, frames=2,
               note="enter_title, two attract frames, then fire")


def test_the_tune_ending_restarts_the_jingle_without_leaving_the_loop():
    """The `beq.s $1054a` exit, driven inside a running loop: the module's "still playing" byte is
    stored clear by the same agent that works the stick, on the second poll. That pass draws NO
    frame — the test is made before the scroll step — and the loop goes back to 0x1054a, where
    `music_play` sets the byte again and the attract carries on."""
    schedule = conftest.attract_schedule(fire_at=5, frames=3)
    schedule.append({"pc": conftest.TITLE_FIRE_WAIT_PC, "nth": 2, "width": 1, "value": 0,
                     "addr": A_sound_module + SND_MUSIC_ACTIVE})
    _run(ENTRY_TITLE_PRESCROLL, lambda lib, buf: lib.g_title_attract_loop(buf),
         pokes=_flow_pokes(), max_insns=TITLE_FLOW_MAX_INSNS, schedule=schedule,
         note="the tune ends on the second poll")


def test_the_attract_scroll_running_out_restarts_the_stage_start():
    """The `bra.w $104f2` exit, twice, inside one run. `const_words_0123[0]` — the word the stage
    start seeds `scroll_pos` from — is poked four short of the end of the attract's window, so two
    frames of scroll reach it and the whole stage start runs again. It is also the case that says
    the seed is a table READ: an immediate 0 there would never reach the end at all."""
    _flow_case(ENTRY_TITLE_PRESCROLL, lambda lib, buf: lib.g_title_attract_loop(buf),
               _flow_pokes(prescroll_frames=0, scroll_seed=ATTRACT_END_SCROLL_POS - 4),
               fire_at=5, frames=4, note="the attract restarts twice, then fire")


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


# The kit's give-up, READ OUT OF ITS HEADER rather than restated — `include/common.h`'s
# `wait_may_go_round_again` counts against this same constant, and a case that spelt its own copy
# would stop driving the seam the day the kit moved it (CLAUDE.md §5).
KIT_OS_H = pathlib.Path(recreate_kit.__file__).parent / "include" / "os.h"
OS_SCHED_POLL_MAX = int(re.search(r"^#define\s+OS_SCHED_POLL_MAX\s+(\d+)u?\s*$",
                                  KIT_OS_H.read_text(), re.M).group(1))
# One arrival past it, so the ORACLE still finishes (its loop is two instructions) while the
# CANDIDATE runs out of polls first — which is the only way to drive the give-up from a case.
UNRELEASED_WAIT_ARRIVAL = OS_SCHED_POLL_MAX + 1
UNRELEASED_WAIT_MAX_INSNS = 100_000


def test_a_wait_the_schedule_never_releases_is_REFUSED_and_not_quietly_abandoned():
    """THE POSITIVE CONTROL ON `include/common.h`'s BUSY-WAIT SEAM, and the only case that reaches
    its give-up.

    Every wait in this reconstruction is bounded off target, because a wait a case never releases is
    an infinite loop in the candidate and a hung suite decides nothing. The bound is worth having
    only if EXHAUSTING it is loud: a give-up that merely returned would let the routine carry on
    down a path the original never took and let the case come back green or red about that. So
    `wait_may_go_round_again` tallies through `os_refused` exactly as `sched_wait8` does
    (`tools/recreate_kit/include/sched.h`, "WHY A CAP AT ALL"), and `harness.differential` throws
    the run away with a name on it.

    This drives it at the simplest wait in the project — `debug_wait_for_keypad4`, which writes
    nothing at all — by putting the key's arrival one poll BEYOND the cap. Delete the tally from the
    helper and this case stops raising, which is what it is here to say.
    """
    with pytest.raises(AssertionError, match=r"os_\* call"):
        _run(ENTRY_DEBUG_WAIT_KEYPAD4, lambda lib, buf: lib.g_debug_wait_for_keypad4(buf),
             pokes={A_key_bits: b"\x00"}, max_insns=UNRELEASED_WAIT_MAX_INSNS,
             schedule=[{"pc": DEBUG_WAIT_KEY_PC, "nth": UNRELEASED_WAIT_ARRIVAL,
                        "addr": A_key_bits, "width": 1, "value": 1 << CHEAT_ARM_KEY_BIT}],
             note="a key that arrives one poll past the cap")


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
        pokes[A_const_words_0123] = word(const_word_zero)
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
    "LEVEL_ASSETS_ORDER_LEVEL_2", "LEVEL_ASSETS_ORDER_LEVEL_3", "DISC_SWAP_ABOVE_LEVEL",
    "A_disc_prompt_message",
    "DISC_PROMPT_WAIT_PC",
    "TITLE_SCROLL_POS_START",
    "A_title_just_entered", "A_attract_page_timer", "A_attract_page_reload",
    "A_text_publisher", "A_text_credits", "A_text_title_mode", "A_title_word_hard",
    "ATTRACT_TUNE", "ATTRACT_END_SCROLL_POS",
    "ATTRACT_PAGE_HALL_OF_FAME_BELOW", "ATTRACT_PAGE_CREDITS_BELOW",
    "TITLE_MODE_WORD_OFFSET", "TITLE_MODE_WORD_BYTES", "TITLE_MODE_EASY_BIT",
    "TITLE_MODE_HARD_BIT", "TITLE_HARD_MODE_ON",
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
    ("A_file_rec_sprites_cru", "include/globals.h", "A_file_rec_sprites_cru"),
    ("FIRE_RELEASE_WAIT_PC", "include/hud.h", "FIRE_RELEASE_WAIT_PC"),
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
    ("LEVELS", "include/player.h", "LEVELS"),
    ("A_level_distance", "include/scroll.h", "A_level_distance"),
    ("A_scroll_pos", "include/scroll.h", "A_scroll_pos"),
    ("A_scroll_fine", "include/scroll.h", "A_scroll_fine"),
    ("A_map_row_ptr", "include/scroll.h", "A_map_row_ptr"),
    ("A_prescroll_flag", "include/scroll.h", "A_prescroll_flag"),
    ("A_prescroll_frames", "include/scroll.h", "A_prescroll_frames"),
    ("SCC_TRUE", "include/common.h", "SCC_TRUE"),
    ("A_sound_module", "include/globals.h", "A_sound_module"),
    ("A_entity_arena", "include/globals.h", "A_entity_arena"),
    ("SND_MUSIC_ACTIVE", "include/sound.h", "SND_MUSIC_ACTIVE"),
    ("A_enemy_bullets", "include/weapons.h", "A_enemy_bullets"),
    ("A_display_list", "include/display_list.h", "A_display_list"),
    ("A_level0_assets_loaded", "include/init.h", "A_level0_assets_loaded"),
    ("A_hard_mode", "include/hud.h", "A_hard_mode"),
    ("A_title_word_easy", "include/hud.h", "A_title_word_easy"),
)

# TEN BYTES, for the reason `test_sprite.py` gives: this program's routines open on a `lea` or a
# `move` of an absolute long, and a shorter pin would match dozens of addresses.
ENTRY_PROLOGUES = {
    "ENTRY_LOAD_LEVEL_ASSETS": "41f9000162d43200c1fc",
    "ENTRY_ENTER_TITLE": "50f90001769861000e90",
    "ENTRY_TITLE_PRESCROLL": "61000cb233f9000176ac",
    "ENTRY_TITLE_POLL": "4a79000176e8660a0839",
    "ENTRY_TITLE_FRAME_STEP": "61003eb00c790bb80001",
    "ENTRY_LEVEL2_SCENERY": "0c7908a20001779a6d00",
    "ENTRY_LEVEL2_SCENERY_GATE": "0c7900020001642a6604",
    "ENTRY_DEBUG_WAIT_KEYPAD4": "48e7fffe083900000001",
    "ENTRY_HISCORE_NAME_ENTRY": "4a79000176dc660000b4",
}
STOP_PROLOGUES = {
    "STOP_PATCH_FILENAMES": "41f90001634661000880",
    "STOP_ENTER_TITLE_LOAD": "61000006600001c241f9",
    "STOP_HISCORE_NAME_ENTRY": "6000fe724239000177cc",
}
