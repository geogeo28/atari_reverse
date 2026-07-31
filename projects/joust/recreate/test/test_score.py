"""Differential tests for Joust's HUD layer (src/score.c).

Covered here, leaves first: find_free_message @ 0x1435c, flash_hiscore_color @ 0x144b0,
draw_hiscore_cursor @ 0x14658, draw_hiscore_entry @ 0x146a6, the draw_lives alias family
@ 0x14246/0x1424e/0x14260, draw_messages @ 0x142de and the score_update alias family
@ 0x14160/0x14166/0x14172.

Every routine here takes its arguments in registers or in globals — none builds a stack frame — so
the oracle is entered at the routine itself and its own machine stack stays inside the guard band
the differential drops. The two results an image diff cannot see are compared explicitly:
find_free_message returns its slot in A0 (emu.run reports it), and the colour word
flash_hiscore_color hands XBIOS Setcolor is read back out of the oracle's write set, since the
modeled trap has no image effect of its own.
"""
import ctypes
import random
import struct

import pytest

import harness   # first: binds the kit, which puts oracle/ on sys.path for the next line
import emu
from harness import differential, report
from test_constants import _defines   # the shared `#define` scraper; see the pin tests at the end

# ---- entry points (Ghidra addresses; ../../names.txt) ----
ENTRY_SCORE_UPDATE = 0x14160
ENTRY_SCORE_UPDATE_P2 = 0x14166
ENTRY_SCORE_UPDATE_P1 = 0x14172
ENTRY_DRAW_LIVES = 0x14246
ENTRY_DRAW_LIVES_P1 = 0x1424e
ENTRY_DRAW_LIVES_P2 = 0x14260
ENTRY_DRAW_MESSAGES = 0x142de
ENTRY_FIND_FREE_MESSAGE = 0x1435c
ENTRY_FLASH_HISCORE_COLOR = 0x144b0
ENTRY_DRAW_HISCORE_CURSOR = 0x14658
ENTRY_DRAW_HISCORE_ENTRY = 0x146a6

# ---- globals (mirrors of include/score.h, include/draw.h, include/object.h and addrs.h) ----
A_PLAYERS_ALIVE = 0x10cf2
A_GAME_OVER_FLAG = 0x10d12
A_SCREEN_BASE = 0x10dde
A_HISCORE_FLASH = 0x10dec      # draw_x, borrowed by the entry screen
A_HISCORE_CURSOR = 0x10df4     # draw_shift, likewise
A_HISCORE_LETTER = 0x10df8     # draw_dst_off, likewise
A_TEXT_PTR = 0x10e0a
A_TEXT_SHIFT = 0x10e0e
A_TEXT_COLOR = 0x10e0f
A_TEXT_BG_COLOR = 0x10e10
A_TEXT_FLAGS = 0x10e11
A_MESSAGE_TABLE = 0x10e16
A_OBJECT_TABLE = 0x10f36       # player 1's slot, and the message table's end bound
A_PLAYER2 = 0x10f84
A_HISCORE_NAME = 0x18396
A_SND_PRIORITY = 0x10d4c       # play_sound's gate: a request above this is dropped

# ---- strings ----
STR_LIFE_BLANK = 0x1861b
STR_LIFE_P1 = 0x1861d
STR_LIFE_P2 = 0x18629
STR_GAME_OVER = 0x185c5

# ---- record geometry ----
MSG_RECORD, N_MESSAGES = 0xc, 24
MSG_KIND, MSG_TIMER, MSG_COLOR, MSG_SHIFT, MSG_SCREEN_PTR, MSG_STRING = 0, 1, 2, 3, 4, 8
MSG_KIND_PERSISTENT = 3
OBJ_SCORE_PTR, OBJ_SCORE_SHIFT_LO, OBJ_LIVES = 0x36, 0x3b, 0x4c
OBJ_SCORE_TEXT = 0x3c          # the string draw_string is handed: `02 <colour>`, then the digits
OBJ_SCORE_FIRST_DIGIT = 0x3e
OBJ_SCORE_LIFE_DIGIT = 0x41    # the thousands: a carry OUT of it crosses 10,000
OBJ_SCORE_LAST_DIGIT = 0x44
OBJ_SIZE = 0x4e
CELL_BYTES = 8
SCREEN_ROW_BYTES = 0xa0

# ---- text engine ----
TEXT_FLAG_BACKGROUND = 0x10
TEXT_FLAG_LARGE_FONT = 0x80
UNWRITTEN_W = 0x5a5a       # pre-filled where a routine must overwrite, so a missing write shows
NOISE_ROWS = 9             # scanlines to seed under one drawn character (the large font is 8)

# ---- scratch areas, clear of the program (ends 0x2b7ae), of abi's stub space (0x40000..0x40207),
# of the staged-file table (0xbf000) and of the stack guard. ----
SCORE_SCRATCH = 0x48000   # a third object record, away from BOTH player slots
SCREEN = 0x70000
STRINGS = 0x80000

# Every fuzz below generates its whole corpus and THEN keeps `index % chunks == chunk`, so the
# shards see the same cases however they are scheduled (the recipe in ../../buggyboy/recreate/
# README.md). Each also counts what it ran and asserts it ran something, so a filter that grew to
# reject everything fails instead of going green on an empty shard.
FUZZ_CHUNKS = 2
FIND_FREE_FUZZ_CHUNKS = 4       # cheap cases, so this one shards further

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs, _ret in (("g_score_update", 1, None),
                            ("g_score_update_p1", 0, None),
                            ("g_score_update_p2", 0, None),
                            ("g_find_free_message", 0, ctypes.c_uint32),
                            ("g_draw_messages", 0, None),
                            ("g_draw_lives", 1, None),
                            ("g_draw_lives_p1", 0, None),
                            ("g_draw_lives_p2", 0, None),
                            ("g_flash_hiscore_color", 0, ctypes.c_uint32),
                            ("g_draw_hiscore_cursor", 0, None),
                            ("g_draw_hiscore_entry", 0, None)):
    _fn = getattr(harness._lib, _glue)
    _fn.argtypes = [_U8P] + [ctypes.c_uint32] * _nargs
    _fn.restype = _ret


# ------------------------------------------------------------------ shared staging helpers

def _seed_rows(pokes, rng, first_row, cells, lead_cells=0):
    """Noise over the scanlines a drawn character covers, one poke per row.

    One poke per scanline rather than one block: the rows are SCREEN_ROW_BYTES apart but only a few
    cells wide, and a contiguous block would rewrite the globals between them too — which matters
    because two cases here deliberately aim a row at the program's own data. `lead_cells` starts each
    row that many cells EARLY, so a character drawn to the left of its column lands on noise and
    shows up as a diff.
    """
    for row in range(NOISE_ROWS):
        start = (first_row + row * SCREEN_ROW_BYTES - lead_cells * CELL_BYTES) & 0xffffffff
        pokes[start] = rng.randbytes((cells + lead_cells) * CELL_BYTES)


def _text_engine_pokes(flags, color=1, bg_color=0):
    """text_ptr / shift / color / bg_color / flags are five consecutive fields, with x and y after
    them — one poke for the block. text_ptr and text_shift are staged with a sentinel because every
    routine here must overwrite them before draw_string reads them."""
    return {A_TEXT_PTR: struct.pack(">IBBBBHH", UNWRITTEN_W << 16 | UNWRITTEN_W, UNWRITTEN_W & 0xff,
                                    color, bg_color, flags, UNWRITTEN_W, UNWRITTEN_W)}


def _message_table(slots, seed=None):
    """The whole 24-slot table as one poke. `slots` is a list of per-slot dicts.

    One poke for the entire table, not one per live slot: the base image's own table would
    otherwise show through in the slots a case does not name, and a routine that walks past its
    intended slot would be read as passing.

    A `seed` fills every field the case does not set with noise. For find_free_message that is the
    point — only the kind byte may steer it — and elsewhere it keeps an unset field from reading as
    a plausible zero.
    """
    rng = random.Random(seed)
    table = bytearray(N_MESSAGES * MSG_RECORD)
    for index in range(N_MESSAGES):
        base = index * MSG_RECORD
        slot = slots[index] if index < len(slots) else {}
        if seed is not None:
            table[base:base + MSG_RECORD] = rng.randbytes(MSG_RECORD)
        table[base + MSG_KIND] = slot.get("kind", 0)
        for field, value in (("timer", MSG_TIMER), ("color", MSG_COLOR), ("shift", MSG_SHIFT)):
            if field in slot:
                table[base + value] = slot[field]
        for field, value in (("screen_ptr", MSG_SCREEN_PTR), ("string", MSG_STRING)):
            if field in slot:
                struct.pack_into(">I", table, base + value, slot[field])
    return {A_MESSAGE_TABLE: bytes(table)}


# ------------------------------------------------------------ find_free_message @ 0x1435c

def _find_free_case(slots, expected, seed=None):
    """Run both cores and compare the slot address, which is the routine's ONLY output.

    It writes no memory at all, so the image diff proves nothing here and the register comparison
    is the whole test: the candidate's return against the oracle's A0, and both against the slot
    the staging makes free.
    """
    pokes = _message_table(slots, seed=seed)
    diffs, info = differential(ENTRY_FIND_FREE_MESSAGE, {"_pokes": pokes},
                               lambda lib, buf: lib.g_find_free_message(buf))
    assert not diffs, f"expected={expected:#x}\n{report(diffs)}"
    assert info["regs"]["a0"] == expected, (
        f"oracle returned {info['regs']['a0']:#x} in A0, not the {expected:#x} the staging makes "
        f"free — the test's own model of the table is wrong")
    assert info["ret"] == info["regs"]["a0"], (
        f"candidate returned {info['ret']:#x}, oracle's A0 was {info['regs']['a0']:#x}")
    assert not info["writes"], "find_free_message wrote memory; it is meant to be a pure scan"


@pytest.mark.parametrize("free_index", (0, 1, 12, N_MESSAGES - 1))
def test_find_free_message_returns_the_first_free_slot(free_index):
    """Every slot before `free_index` is taken, so the scan must stop exactly there."""
    slots = [{"kind": 1} for _ in range(N_MESSAGES)]
    slots[free_index] = {"kind": 0}
    _find_free_case(slots, A_MESSAGE_TABLE + free_index * MSG_RECORD, seed=free_index + 1)


def test_find_free_message_full_table_returns_zero():
    """`suba.l a0,a0` past the last slot: a full table answers 0, not the table's end."""
    _find_free_case([{"kind": 0xff} for _ in range(N_MESSAGES)], 0, seed=99)


@pytest.mark.parametrize("kind", (1, 2, MSG_KIND_PERSISTENT, 0x7f, 0x80, 0xff))
def test_find_free_message_any_nonzero_kind_is_taken(kind):
    """`tst.b` — every non-zero kind occupies the slot, sign bit included."""
    slots = [{"kind": kind}, {"kind": 0}]
    _find_free_case(slots, A_MESSAGE_TABLE + MSG_RECORD, seed=kind)


def test_find_free_message_ignores_every_other_field():
    """Only the kind byte is read: slot 0 free but noisy everywhere else still wins."""
    slots = [{"kind": 0, "timer": 0xff, "color": 0xff, "shift": 0xff,
              "screen_ptr": 0xdeadbeef, "string": 0xfeedface}]
    _find_free_case(slots, A_MESSAGE_TABLE)


@pytest.mark.parametrize("chunk", range(FIND_FREE_FUZZ_CHUNKS))
def test_find_free_message_fuzz(chunk):
    """Random occupancy patterns, including tables with no free slot at all."""
    rng = random.Random(0x5c04e)
    cases = [[{"kind": rng.randint(0, 3) and rng.randint(1, 0xff)} for _ in range(N_MESSAGES)]
             for _ in range(200)]
    ran = 0
    for index, slots in enumerate(cases):
        if index % FIND_FREE_FUZZ_CHUNKS != chunk:
            continue
        free = next((i for i, slot in enumerate(slots) if slot["kind"] == 0), None)
        expected = 0 if free is None else A_MESSAGE_TABLE + free * MSG_RECORD
        _find_free_case(slots, expected, seed=index)
        ran += 1
    assert ran, "this shard ran no cases"


# ------------------------------------------------------- flash_hiscore_color @ 0x144b0

# What the original pushes for its `trap #14`, deepest word first: the XBIOS function number, then
# Setcolor's two arguments. Entering the routine directly leaves those pushes on the oracle's own
# stack — inside the guard band the diff drops — but emu.run reports every byte the run WROTE, so
# they can still be read back and compared. Nothing else in the run writes there.
XBIOS_SETCOLOR = 0x7


def _pushed_words(writes, count):
    """The `count` words the routine pushed at A7, outermost (highest address) first."""
    return [(writes[emu.STACK_TOP - 2 * (index + 1)] << 8) | writes[emu.STACK_TOP - 2 * index - 1]
            for index in range(count)]


def _flash_case(counter, poison=True):
    pokes = {A_HISCORE_FLASH: struct.pack(">H", counter),
             # A sentinel in the next word: `addq.w` must not carry into it when the counter wraps.
             A_HISCORE_FLASH + 2: b"\x5a\x5a"}
    diffs, info = differential(ENTRY_FLASH_HISCORE_COLOR, {"_pokes": pokes},
                               lambda lib, buf: lib.g_flash_hiscore_color(buf), poison=poison)
    assert not diffs, f"counter={counter:#x}\n{report(diffs)}"

    colour, pen, fn = _pushed_words(info["writes"], 3)
    assert fn == XBIOS_SETCOLOR, f"the original trapped to XBIOS fn {fn:#x}, not Setcolor"
    assert pen == _defines("src/score.c")["HISCORE_FLASH_PEN"], (
        f"the original asked Setcolor for pen {pen}, not HISCORE_FLASH_PEN")
    assert info["ret"] == colour, (
        f"counter={counter:#x}: candidate computed colour {info['ret']:#x}, the original passed "
        f"Setcolor {colour:#x} — the palette write itself is off-image, so this is the only thing "
        f"that can catch it")


@pytest.mark.parametrize("counter", (0, 1, 6, 7, 8, 0x7ffe, 0x7fff, 0x8000, 0xfffe, 0xffff))
def test_flash_hiscore_color_steps_the_cycle(counter):
    """Bump, then `andi.w #7 / ori.w #$400`. 0xffff wraps to 0 within the WORD — a longword
    counter would carry into the next global, which the poked sentinel would catch."""
    _flash_case(counter)


# ------------------------------------------------------ draw_hiscore_cursor @ 0x14658

HISCORE_UNDERLINE_OFF = 0x57b0   # from screen_base (mirror of src/score.c)
HISCORE_UNDERLINE_CELLS = 8
HISCORE_COLUMN_BYTES = 4         # `lsl.w #2`, with the cursor's low bit cleared first
N_HISCORE_COLUMNS = 16           # what hiscore_key_input caps the cursor at


def _sx16(value):
    """A word folded into an address with `adda.w` is SIGN-extended, so 0x8000 means -0x8000."""
    return value - 0x10000 if value & 0x8000 else value


def _column_offset(cursor):
    """The byte offset of `cursor`'s column from the start of its row, as the original computes it."""
    return _sx16(((cursor & ~1) * HISCORE_COLUMN_BYTES) & 0xffff)


def _cursor_case(cursor, screen_base=SCREEN, seed=0, poison=True):
    """Noise over the whole underline AND past its end, so an over-long or short paint both show."""
    rng = random.Random(seed)
    row = screen_base + HISCORE_UNDERLINE_OFF
    bar = (row + _column_offset(cursor)) & 0xffffffff
    pokes = {A_SCREEN_BASE: struct.pack(">I", screen_base),
             A_HISCORE_CURSOR: struct.pack(">H", cursor),
             row: rng.randbytes(2 * HISCORE_UNDERLINE_CELLS * CELL_BYTES)}
    # Only when the bar lands OUTSIDE the rule's noise: at column 0 (and at every cursor whose
    # offset is 0) the two coincide, and a second poke at the same address would replace the
    # rule's 128 bytes with 8 — leaving most of the rule painted over base-image zeros, where a
    # dropped `wr32(cell + 4, 0)` writes nothing visible.
    if not row <= bar < row + 2 * HISCORE_UNDERLINE_CELLS * CELL_BYTES:
        pokes[bar] = rng.randbytes(CELL_BYTES)
    diffs, _ = differential(ENTRY_DRAW_HISCORE_CURSOR, {"_pokes": pokes},
                            lambda lib, buf: lib.g_draw_hiscore_cursor(buf), poison=poison)
    assert not diffs, f"cursor={cursor:#x} screen_base={screen_base:#x}\n{report(diffs)}"


@pytest.mark.parametrize("cursor", range(N_HISCORE_COLUMNS))
def test_draw_hiscore_cursor_every_column(cursor):
    """Both parities of the bar, at each column a name entry can actually reach."""
    _cursor_case(cursor, seed=cursor)


def test_draw_hiscore_cursor_bar_is_written_over_the_rule():
    """The rule is painted first and the bar straight on top, so column 0's cell ends up as the
    bar's pattern, not the rule's — an order this catches only because both land on the same cell."""
    for cursor in (0, 1):
        _cursor_case(cursor, seed=0x60 + cursor)


@pytest.mark.parametrize("cursor", (0x1ffe, 0x1fff, 0x2000, 0x2001, 0x4000, 0x8000, 0xfffe, 0xffff))
def test_draw_hiscore_cursor_column_is_sign_extended(cursor):
    """`lsl.w #2` keeps 16 bits and `adda.w` sign-extends them, so a cursor past 0x1fff paints the
    bar BEFORE the rule's row instead of far past it. Off-screen, and reproduced."""
    _cursor_case(cursor, seed=cursor & 0xff)


@pytest.mark.parametrize("screen_base", (SCREEN, SCREEN + 2, SCREEN + SCREEN_ROW_BYTES, 0x60000))
def test_draw_hiscore_cursor_screen_bases(screen_base):
    """screen_base is re-read from the image, not assumed — including at an odd cell alignment."""
    _cursor_case(5, screen_base=screen_base, seed=screen_base & 0xff)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_draw_hiscore_cursor_fuzz(chunk):
    rng = random.Random(0xc0501)
    cases = [(rng.randint(0, 0xffff), rng.choice((SCREEN, SCREEN + 8, 0x60000)), rng.randint(0, 1))
             for _ in range(200)]
    ran = 0
    for index, (cursor, screen_base, seed) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        _cursor_case(cursor, screen_base=screen_base, seed=seed, poison=False)
        ran += 1
    assert ran, "this shard ran no cases"


# ------------------------------------------------------- draw_hiscore_entry @ 0x146a6

HISCORE_ENTRY_OFF = 0x52b0       # from screen_base (mirror of src/score.c)
ENTRY_ROW_CELLS = 3              # cells one drawn letter can reach


def _entry_case(cursor, letter=0x41, tail=b"\x00", screen_base=SCREEN, flags=TEXT_FLAG_LARGE_FONT,
                seed=0, poison=True):
    rng = random.Random(seed)
    cell = (screen_base + HISCORE_ENTRY_OFF + _column_offset(cursor)) & 0xffffffff
    pokes = {A_SCREEN_BASE: struct.pack(">I", screen_base),
             A_HISCORE_CURSOR: struct.pack(">H", cursor),
             # The string draw_string is handed IS this address: the letter, then whatever follows.
             A_HISCORE_LETTER: bytes([letter]) + tail,
             **_text_engine_pokes(flags, color=6)}
    _seed_rows(pokes, rng, cell, ENTRY_ROW_CELLS, lead_cells=1)
    diffs, _ = differential(ENTRY_DRAW_HISCORE_ENTRY, {"_pokes": pokes},
                            lambda lib, buf: lib.g_draw_hiscore_entry(buf), poison=poison)
    assert not diffs, (f"cursor={cursor:#x} letter={letter:#x} flags={flags:#x} "
                       f"screen_base={screen_base:#x}\n{report(diffs)}")


@pytest.mark.parametrize("cursor", range(N_HISCORE_COLUMNS))
def test_draw_hiscore_entry_every_column(cursor):
    """Each column stores the letter at its own index in the name and paints it at its own cell —
    with text_shift 1 for an even column and 9 for the odd one sharing that cell."""
    _entry_case(cursor, seed=cursor)


@pytest.mark.parametrize("letter", (0x20, 0x41, 0x5a, 0x30, 0xff, 0x00))
def test_draw_hiscore_entry_letters(letter):
    """Whatever byte the entry code left under the cursor is both stored and drawn. 0x00 is the
    string terminator, so that case stores the letter and stages the cursor but paints nothing —
    the one letter value for which the screen stays untouched."""
    _entry_case(2, letter=letter, seed=letter)


def test_draw_hiscore_entry_string_starts_at_the_letter():
    """The string is the ADDRESS of the letter byte, so a non-zero byte after it is a second
    character, not padding. Nothing else in the routine would reveal where the string begins."""
    _entry_case(4, letter=0x41, tail=b"\x42\x00", seed=7)


@pytest.mark.parametrize("flags", (0, TEXT_FLAG_LARGE_FONT,
                                   TEXT_FLAG_LARGE_FONT | TEXT_FLAG_BACKGROUND))
def test_draw_hiscore_entry_font_and_background_are_the_callers(flags):
    """The routine sets text_shift and text_ptr but never the font or the bar — those are left
    exactly as check_highscore staged them."""
    _entry_case(6, flags=flags, seed=flags)


@pytest.mark.parametrize("cursor", (0x1ffe, 0x2000, 0x8000, 0xffff))
def test_draw_hiscore_entry_cursor_is_sign_extended(cursor):
    """Two sign-extensions from one cursor: the name index (`move.b ...,(0,a2,d2.w)`) and the
    screen offset (`adda.w`). Both run backwards from 0x8000, and both are reproduced."""
    _entry_case(cursor, seed=cursor & 0xff)


@pytest.mark.parametrize("screen_base", (SCREEN, SCREEN + 4, 0x60000))
def test_draw_hiscore_entry_screen_bases(screen_base):
    _entry_case(3, screen_base=screen_base, seed=screen_base & 0xff)


# The letter is stored at hiscore_name + sign_extend(cursor), which for a cursor far outside the
# 0..15 the entry code produces can land ANYWHERE — including inside the code this very run is
# executing. That is self-modification: at cursor 0xc355 the store lands on 0x146eb, the last byte
# of the immediate draw_hiscore_entry itself pushes as its string pointer, so the ORACLE goes on to
# draw a different string. No C reconstruction can follow that, and no game state can reach it, so
# the fuzz skips exactly the spans this run executes and covers every other cursor.
EXECUTED_CODE = ((ENTRY_DRAW_HISCORE_ENTRY, 0x146f6),   # draw_hiscore_entry itself
                 (0x10700, 0x1096e),                    # draw_string
                 (0x182a2, 0x182d6))                    # pos_to_screen, via a TEXT_SET_POS byte

# Bytes below 0x0e are draw_string's control codes; several consume the terminator and read on
# through unrelated globals, which is out of contract here — hiscore_key_input only ever leaves a
# space or an upper-case letter under the cursor. The explicit cases above cover 0x00.
FUZZ_LETTER_MIN = 0x0e


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_draw_hiscore_entry_fuzz(chunk):
    rng = random.Random(0xe27a1)
    cases = [(rng.randint(0, 0xffff), rng.randint(FUZZ_LETTER_MIN, 0xff),
              rng.choice((SCREEN, 0x60000)), rng.randint(0, 0xff)) for _ in range(200)]
    ran = 0
    for index, (cursor, letter, screen_base, flags) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        if any(lo <= A_HISCORE_NAME + _sx16(cursor) < hi for lo, hi in EXECUTED_CODE):
            continue
        _entry_case(cursor, letter=letter, screen_base=screen_base, flags=flags,
                    seed=index, poison=False)
        ran += 1
    assert ran, "this shard ran no cases — the EXECUTED_CODE filter rejected every one"


# ------------------- draw_lives @ 0x14246 / draw_lives_p1 @ 0x1424e / draw_lives_p2 @ 0x14260

LIVES_DRAWN = 5              # positions painted per row, whatever the count (mirror of score.c)
LIVES_HUD_ADVANCE = 0x10
LIVES_SHIFT_ADVANCE = 0xa
LIVES_ROW_CELLS = 6          # cells a five-position row can reach, with room to spare


SCORE_SHIFT_HIGH_BYTE = 0xa5   # noise in the half of the .w field draw_lives must NOT read


def _hud_object(score_ptr, shift, lives):
    """The three fields draw_lives reads out of an object record, as one whole-record poke.

    The shift is the LOW byte of a word field, and the high byte is deliberately noise: the routine
    reads `59(a0)`, so a reconstruction that took the field's own address would pick up 0xa5.
    """
    record = bytearray(OBJ_SIZE)
    struct.pack_into(">I", record, OBJ_SCORE_PTR, score_ptr)
    record[OBJ_SCORE_SHIFT_LO - 1] = SCORE_SHIFT_HIGH_BYTE
    record[OBJ_SCORE_SHIFT_LO] = shift
    record[OBJ_LIVES] = lives
    return bytes(record)


def _lives_pokes(lives, shift=0, score_ptr=SCREEN, flags=0, seed=0, other_lives=None):
    """Both player records staged, so a routine reading the WRONG one still reads something known.

    The screen noise goes down FIRST and the records and text globals over it: the re-read pin below
    deliberately aims the row at the record itself, and seeding it afterwards would bury the count
    the case means to stage under noise.
    """
    rng = random.Random(seed)
    pokes = {}
    _seed_rows(pokes, rng, (score_ptr + LIVES_HUD_ADVANCE) & 0xffffffff, LIVES_ROW_CELLS)
    pokes.update({A_OBJECT_TABLE: _hud_object(score_ptr, shift, lives),
                  A_PLAYER2: _hud_object(score_ptr, shift,
                                         lives if other_lives is None else other_lives),
                  **_text_engine_pokes(flags)})
    return pokes


def _lives_case(entry, glue, lives, expect_row_painted=False, poison=True, a0=A_OBJECT_TABLE,
                **staging):
    """`expect_row_painted` asserts the run really reached the row — otherwise a case that staged
    the HUD somewhere the routine never looks would go green on an empty diff."""
    pokes = _lives_pokes(lives, **staging)
    diffs, info = differential(entry, {"a0": a0, "_pokes": pokes}, glue, poison=poison)
    assert not diffs, f"entry={entry:#x} a0={a0:#x} lives={lives:#x} {staging}\n{report(diffs)}"
    if expect_row_painted:
        row = (staging.get("score_ptr", SCREEN) + LIVES_HUD_ADVANCE) & 0xffffffff
        assert any(row <= addr < row + LIVES_ROW_CELLS * CELL_BYTES for addr in info["writes"]), \
            f"lives={lives:#x}: nothing was painted at the row itself ({row:#x})"
    return info


@pytest.mark.parametrize("lives", (0, 1, 2, 4, 5, 6, 0x7f))
def test_draw_lives_p1_counts(lives):
    """`cmp.b lives,d0` + `ble`: position n (5..1) fills in when n <= lives, so a count above 5
    fills every position and one of 0 fills none."""
    _lives_case(ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), lives,
                expect_row_painted=True, seed=lives)


@pytest.mark.parametrize("lives", (0x80, 0xfe, 0xff))
def test_draw_lives_count_is_signed(lives):
    """`ble` is the SIGNED branch, so a count with bit 7 set is negative — every position blanks,
    exactly as a count of 0 does. An unsigned compare would fill all five."""
    _lives_case(ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), lives,
                expect_row_painted=True, seed=lives)


@pytest.mark.parametrize("shift", (0, 1, 5, 6, 0xf6, 0xfb, 0xff))
def test_draw_lives_shift_advance_is_a_byte_add(shift):
    """`addi.b #$a` on text_shift: 0xf6 + 10 wraps to 0 rather than carrying anywhere."""
    _lives_case(ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), 3,
                expect_row_painted=True, shift=shift, seed=shift)


@pytest.mark.parametrize("flags", (0, TEXT_FLAG_LARGE_FONT, TEXT_FLAG_BACKGROUND, 0xff))
def test_draw_lives_sets_both_flags_and_clears_only_one(flags):
    """The row switches the large font AND the background bar on, then clears only the bar — so the
    font selection is left behind for whatever draws next, whatever the caller had staged."""
    _lives_case(ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), 3,
                expect_row_painted=True, flags=flags, seed=flags)


@pytest.mark.parametrize("score_ptr", (SCREEN, SCREEN + 1, SCREEN + 4, SCREEN + SCREEN_ROW_BYTES))
def test_draw_lives_row_follows_the_records_screen_pointer(score_ptr):
    """text_ptr is the record's own pointer plus LIVES_HUD_ADVANCE — nothing here is a constant."""
    _lives_case(ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), 2,
                expect_row_painted=True, score_ptr=score_ptr, seed=score_ptr & 0xff)


# text_shift is the record's shift + LIVES_SHIFT_ADVANCE, and this value makes that sum wrap its
# byte to 1: the background bar then covers bits 1..6 of the cell's first plane word, leaving bit 7
# — the SIGN bit of the byte it lands on — clear. It matters only for the re-read pin below, where
# the byte it lands on IS the count: a bar starting at bit 0 would leave a negative count, which
# blanks the row exactly as the 0 it started from does, and the pin would prove nothing.
LIVES_SHIFT_FOR_POSITIVE_BAR = (1 - LIVES_SHIFT_ADVANCE) & 0xff

# A life glyph string ends with `03 00`, which turns the background bar off; a blank is a bare
# space and leaves it as draw_lives staged it. So a text_bg_color of 0 afterwards means at least
# one GLYPH was drawn, and anything else means the row came out all blanks.


def test_draw_lives_rereads_the_count_every_position():
    """The count is re-read from the record on every pass, so a row painted OVER that record grows
    its own count as it goes: position 5 blanks, the bar it paints lands on the count byte leaving
    it positive, and the remaining positions then see a count above them and fill in. A hoisted
    read would blank all five, which is why the count staged here is 0.
    """
    info = _lives_case(ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), 0,
                       score_ptr=A_OBJECT_TABLE + OBJ_LIVES - LIVES_HUD_ADVANCE,
                       shift=LIVES_SHIFT_FOR_POSITIVE_BAR, poison=False)
    assert info["writes"].get(A_TEXT_BG_COLOR) == 0, (
        "the row drew five blanks, so it never grew its own count — with the count staged at 0 a "
        "reconstruction that read it once would produce exactly this row, and nothing is pinned")


@pytest.mark.parametrize("entry,glue,drawn_object", (
    (ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf), A_OBJECT_TABLE),
    (ENTRY_DRAW_LIVES_P2, lambda lib, buf: lib.g_draw_lives_p2(buf), A_PLAYER2)))
def test_draw_lives_entry_points_ignore_a0(entry, glue, drawn_object):
    """Both bodies reload the object from a constant, so the A0 they were entered with is dead —
    here the two records carry different counts, which a body reading A0 would draw instead."""
    _lives_case(entry, glue, 5, expect_row_painted=True, other_lives=0, a0=0xdeadbee0, seed=1)


@pytest.mark.parametrize("a0", (A_PLAYER2, A_PLAYER2 + 1, A_PLAYER2 - 1, A_OBJECT_TABLE,
                                A_OBJECT_TABLE + 2 * OBJ_SIZE, 0, 0xffffffff))
def test_draw_lives_dispatch_is_a_full_longword_compare(a0):
    """`cmpa.l` against player 2's slot: one byte off — or any other object — draws PLAYER 1's row.
    The two records carry different counts, so picking the wrong one shows as a diff."""
    _lives_case(ENTRY_DRAW_LIVES, lambda lib, buf: lib.g_draw_lives(buf, a0), 5,
                expect_row_painted=True, other_lives=1, a0=a0, seed=a0 & 0xff)


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_draw_lives_fuzz(chunk):
    rng = random.Random(0x11e5)
    entries = ((ENTRY_DRAW_LIVES_P1, lambda lib, buf: lib.g_draw_lives_p1(buf)),
               (ENTRY_DRAW_LIVES_P2, lambda lib, buf: lib.g_draw_lives_p2(buf)))
    cases = [(rng.randrange(len(entries)), rng.randint(0, 0xff), rng.randint(0, 0xff),
              rng.randint(0, 0xff), rng.choice((SCREEN, SCREEN + 3, 0x60000)))
             for _ in range(120)]
    ran = 0
    for index, (which, lives, shift, flags, score_ptr) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        entry, glue = entries[which]
        _lives_case(entry, glue, lives, shift=shift, flags=flags, score_ptr=score_ptr,
                    seed=index, poison=False)
        ran += 1
    assert ran, "this shard ran no cases"


# --------------------------------------------------------------- draw_messages @ 0x142de

STRING_STRIDE = 0x10          # room for one staged message string per slot
MSG_ROW_CELLS = 3             # cells a one-glyph message can reach
MSG_ROW_PITCH = NOISE_ROWS    # scanlines between one slot's noise band and the next's


def _slot_text(index):
    """A DISTINCT glyph per slot, so the pixels say WHICH slot's string pointer was followed. With
    one shared string every live slot paints the same bytes, and a candidate that fetched a
    neighbour's pointer would be invisible."""
    return bytes([ord("A") + index % 26, 0])


def _expires(slot, players_alive):
    """Does this pass retire the slot? (the test's own model of the routine's two timer rules)"""
    if not slot.get("kind"):
        return False
    if not players_alive and slot["kind"] != MSG_KIND_PERSISTENT:
        return True                       # cut short to timer 1, which this same pass decrements
    return ((slot["timer"] - 1) & 0xff) == 0


def _messages_case(slots, players_alive=1, seed=0, poison=True, expect_expired=(),
                   expect_game_over=False, pokes=None):
    """Stage the whole table, run both cores, and check WHICH slots the pass retired.

    The expiry assertions are what keep a case from going green vacuously: the image diff alone
    cannot tell "both cores expired this slot" from "neither did anything".
    """
    rng = random.Random(seed)
    staging, filled = {}, []
    for index, slot in enumerate(slots):
        slot = dict(slot)
        if slot.get("kind"):
            slot.setdefault("screen_ptr", SCREEN + index * MSG_ROW_PITCH * SCREEN_ROW_BYTES)
            if "string" not in slot:
                staging[STRINGS + index * STRING_STRIDE] = _slot_text(index)
                slot["string"] = STRINGS + index * STRING_STRIDE
            _seed_rows(staging, rng, slot["screen_ptr"], MSG_ROW_CELLS)
        filled.append(slot)

    staging.update(_message_table(filled, seed=seed))
    # players_alive is read as a BYTE and tested against 0, so it is staged with counts ABOVE 1 too;
    # the noise beside it is wave_num, which this routine never touches — staged non-zero so that a
    # word-wide read of the flag would change the verdict.
    staging[A_PLAYERS_ALIVE] = bytes([players_alive, 0xa5])
    # A sentinel, not 0: the original only ever WRITES this flag (never clears it), so a candidate
    # that cleared it on a non-game-over expiry would be invisible against a staged 0.
    staging[A_GAME_OVER_FLAG] = bytes([UNWRITTEN_W & 0xff])
    # text_color carries a sentinel too: this routine sets it from the slot (or to 0 on expiry) on
    # every pass, so a missing write would show.
    staging.update(_text_engine_pokes(TEXT_FLAG_LARGE_FONT, color=UNWRITTEN_W & 0xff))
    staging.update(pokes or {})          # the case's own pokes win over the defaults above

    diffs, info = differential(ENTRY_DRAW_MESSAGES, {"_pokes": staging},
                               lambda lib, buf: lib.g_draw_messages(buf), poison=poison)
    assert not diffs, f"players_alive={players_alive} slots={slots}\n{report(diffs)}"

    expired = {index for index in range(N_MESSAGES)
               if info["writes"].get(A_MESSAGE_TABLE + index * MSG_RECORD + MSG_KIND) == 0
               and filled[index].get("kind")}
    assert expired == set(expect_expired), (
        f"the pass retired slots {sorted(expired)}, the case expects {sorted(expect_expired)}")
    assert (info["writes"].get(A_GAME_OVER_FLAG) == 1) == expect_game_over, (
        f"game_over_flag {'was not' if expect_game_over else 'was'} set")
    return info


def test_draw_messages_empty_table_does_nothing():
    """Every kind byte zero: the walk touches nothing at all, in either core."""
    # poison is off deliberately: with an empty oracle write set it re-runs both cores and compares
    # nothing, so it would cost a run and prove nothing. The `writes` assertion below is the check.
    info = _messages_case([{} for _ in range(N_MESSAGES)], seed=1, poison=False)
    assert not info["writes"], "an all-free table still wrote memory"


@pytest.mark.parametrize("index", (0, 1, N_MESSAGES - 1))
def test_draw_messages_draws_one_live_slot(index):
    """Each slot is reached, the last one included — the walk's bound is object_table, so a slot
    short or long would show here."""
    slots = [{} for _ in range(N_MESSAGES)]
    slots[index] = {"kind": 1, "timer": 5, "color": 3, "shift": 2}
    _messages_case(slots, seed=index + 10)


@pytest.mark.parametrize("timer", (2, 3, 0x80, 0xff))
def test_draw_messages_counts_a_live_timer_down(timer):
    """A timer above 1 just decrements, and the slot's own colour goes to the text engine."""
    _messages_case([{"kind": 1, "timer": timer, "color": 7, "shift": 0}], seed=timer)


def test_draw_messages_timer_zero_wraps_to_255():
    """`subq.b`: 0 - 1 = 0xff, i.e. 256 more frames — NOT an expiry."""
    _messages_case([{"kind": 1, "timer": 0, "color": 2, "shift": 4}], seed=20)


def test_draw_messages_expiry_frees_the_slot_and_still_draws_it():
    """The last frame forces text_color to 0 and frees the slot, then draws the string ANYWAY —
    in colour 0, which is how the message rubs itself out."""
    info = _messages_case([{"kind": 1, "timer": 1, "color": 7, "shift": 0}], seed=21,
                          expect_expired=(0,))
    assert any(addr >= SCREEN for addr in info["writes"]), (
        "the expiring message painted nothing — the erase pass is what frees the pixels")
    assert info["writes"].get(A_TEXT_COLOR) == 0, "text_color was not forced to 0 on expiry"


@pytest.mark.parametrize("kind", (1, 2, 4, 0xff))
def test_draw_messages_no_players_cuts_a_message_short(kind):
    """With players_alive == 0 the timer is forced to 1, which this same pass decrements to 0 —
    so every kind but MSG_KIND_PERSISTENT retires in one frame however long it had left."""
    _messages_case([{"kind": kind, "timer": 0x40, "color": 5, "shift": 0}], players_alive=0,
                   seed=kind, expect_expired=(0,))


@pytest.mark.parametrize("players_alive", (1, 2, 0x7f, 0x80, 0xff))
def test_draw_messages_any_live_player_leaves_the_timer_alone(players_alive):
    """The test is `tst.b`/== 0, not "== 1": with two players up (or any other non-zero count) the
    cut-short must not fire, which a `!= 1` or `& 1` reading of the flag would get wrong."""
    _messages_case([{"kind": 1, "timer": 0x40, "color": 5, "shift": 0}],
                   players_alive=players_alive, seed=players_alive)


def test_draw_messages_persistent_kind_survives_with_no_players():
    """Kind 3 is exempt from the cut-short, so it ages one frame like any other."""
    _messages_case([{"kind": MSG_KIND_PERSISTENT, "timer": 0x40, "color": 5, "shift": 0}],
                   players_alive=0, seed=30)


def test_draw_messages_no_players_still_expires_a_persistent_slot_on_its_own_timer():
    """...and when kind 3's own timer runs out it retires normally."""
    _messages_case([{"kind": MSG_KIND_PERSISTENT, "timer": 1, "color": 5, "shift": 0}],
                   players_alive=0, seed=31, expect_expired=(0,))


def test_draw_messages_game_over_string_sets_the_flag():
    """The end of the game is the expiry of ONE string: "THY GAME IS OVER" at 0x185c5."""
    _messages_case([{"kind": 1, "timer": 1, "color": 1, "shift": 0, "string": STR_GAME_OVER}],
                   seed=40, expect_expired=(0,), expect_game_over=True)


def test_draw_messages_game_over_string_that_has_not_expired_sets_nothing():
    """The flag rides on the expiry, not on the string being present."""
    _messages_case([{"kind": 1, "timer": 4, "color": 1, "shift": 0, "string": STR_GAME_OVER}],
                   seed=41)


# The pointer compare is `cmpi.l`. Its top byte cannot be probed — a pointer differing there would
# be >= 0x1000000, outside the 1 MiB image both cores address — so these three cover the bytes that
# a game pointer can actually differ in. Each probe address is poked with a bare terminator so the
# case exercises the comparison and nothing else.
@pytest.mark.parametrize("string", (STR_GAME_OVER ^ 1, STR_GAME_OVER ^ 0x100,
                                    STR_GAME_OVER ^ 0x10000))
def test_draw_messages_game_over_compare_is_a_full_pointer(string):
    """A string one byte away from the game-over one must NOT end the game."""
    slots = [{"kind": 1, "timer": 1, "color": 1, "shift": 0, "string": string}]
    _messages_case(slots, seed=50, expect_expired=(0,), pokes={string: b"\x00"})


def test_draw_messages_walks_every_slot_in_one_pass():
    """A full table of live slots at different timers: one pass ages all 24, retiring only those
    that reach 0. Nothing about a slot's state stops the walk."""
    slots = [{"kind": 1 + (index % 3), "timer": 1 if index % 4 == 0 else 2 + index,
              "color": index & 0xf, "shift": index % 3} for index in range(N_MESSAGES)]
    _messages_case(slots, seed=60, poison=False,
                   expect_expired=tuple(range(0, N_MESSAGES, 4)))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_draw_messages_fuzz(chunk):
    rng = random.Random(0x5e33)
    cases = []
    for _ in range(60):
        slots = [{} if rng.randint(0, 2) else
                 {"kind": rng.randint(1, 5), "timer": rng.choice((0, 1, 1, 2, 0x7f, 0xff)),
                  "color": rng.randint(0, 0xf), "shift": rng.randint(0, 0x1f)}
                 for _ in range(N_MESSAGES)]
        cases.append((slots, rng.choice((0, 1, 2, 0xff))))   # 0 is the only special count
    ran = 0
    for index, (slots, players_alive) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        expired = tuple(i for i, slot in enumerate(slots) if _expires(slot, players_alive))
        _messages_case(slots, players_alive=players_alive, seed=index, poison=False,
                       expect_expired=expired)
        ran += 1
    assert ran, "this shard ran no cases"


# ------------- score_update @ 0x14160 / _p2 @ 0x14166 / _p1 @ 0x14172 — one alias family
#
# The family adds NOTHING. A caller has already added its points into one of the object's ASCII
# score digits, and these three repair the string: promote a bumped blank to the digit it means,
# carry the decimal columns, hand out the extra lives those carries earn, and repaint the row.

SND_PRIORITY_IDLE = 0x10       # nothing playing; any request outranks it (mirror of include/sound.h)
SND_EXTRA_LIFE = 1             # what the extra life asks play_sound for

N_SCORE_DIGITS = OBJ_SCORE_LAST_DIGIT - OBJ_SCORE_FIRST_DIGIT + 1
SCORE_COLOR_BYTE = OBJ_SCORE_TEXT + 1   # the `02 <colour>` pair's colour — what a carry overflows into
TEXT_SET_COLOR = 2                      # draw_string's set-colour control byte...
TEXT_SET_POS = 1                        # ...and the one that moves text_ptr (mirrors of src/draw.c)
SCORE_COLOR = 7                         # the colour the shipped records carry

BLANK = ord(" ")               # a digit position the score has not reached yet
DIGIT_0, DIGIT_9 = ord("0"), ord("9")
BLANK_TO_DIGIT = 0x10          # `addi.b #$10`: ' ' + n becomes '0' + n
SCORE_CARRY = 0xa

# Where the model's index sits relative to the digits: index 0 is the string's COLOUR byte (the
# carry out of the leftmost digit lands there), so digit n is index n + 1.
MODEL_LIFE_INDEX = OBJ_SCORE_LIFE_DIGIT - SCORE_COLOR_BYTE

SCORE_ROW_CELLS = 9            # cells the digit row and the lives row beside it can reach
SCORE_ROW_PITCH = 12           # scanlines between the three staged HUD bands

# The three records every case stages. A routine that read the wrong one still reads something
# known, and each has its OWN screen band, so painting the wrong row shows up as pixels.
HUD_SLOTS = (A_OBJECT_TABLE, A_PLAYER2, SCORE_SCRATCH)
HUD_FILLER = (b"  12340", b"  56780", b"  90120")   # a settled string per slot, all distinct


def _hud_row(object_addr):
    return SCREEN + HUD_SLOTS.index(object_addr) * SCORE_ROW_PITCH * SCREEN_ROW_BYTES


def _score_record(digits, score_ptr, shift, lives, colour):
    """One whole object record: the score string, the HUD cursor and the life count.

    The shift is the LOW byte of a word field whose high byte is noise, as for draw_lives — and the
    byte after the last digit stays 0, which is the string's terminator.
    """
    assert len(digits) == N_SCORE_DIGITS, "the score string is seven digits"
    record = bytearray(OBJ_SIZE)
    struct.pack_into(">I", record, OBJ_SCORE_PTR, score_ptr)
    record[OBJ_SCORE_SHIFT_LO - 1] = SCORE_SHIFT_HIGH_BYTE
    record[OBJ_SCORE_SHIFT_LO] = shift
    record[OBJ_LIVES] = lives
    record[OBJ_SCORE_TEXT] = TEXT_SET_COLOR
    record[SCORE_COLOR_BYTE] = colour
    record[OBJ_SCORE_FIRST_DIGIT:OBJ_SCORE_LAST_DIGIT + 1] = bytes(digits)
    return bytes(record)


def _score_pokes(digits, object_addr, shift=0, lives=0, colour=SCORE_COLOR,
                 priority=SND_PRIORITY_IDLE, flags=0, score_ptr=None, seed=0):
    """Stage all three HUD records plus the noise under their rows, then the case's own record."""
    rng = random.Random(seed)
    pokes = {}
    for index, slot in enumerate(HUD_SLOTS):
        row = SCREEN + index * SCORE_ROW_PITCH * SCREEN_ROW_BYTES
        _seed_rows(pokes, rng, row, SCORE_ROW_CELLS)
        pokes[slot] = _score_record(HUD_FILLER[index], row, index, index, index + 1)

    row = _hud_row(object_addr) if score_ptr is None else score_ptr
    if score_ptr is not None:
        _seed_rows(pokes, rng, score_ptr & 0xffffffff, SCORE_ROW_CELLS)
    pokes[object_addr] = _score_record(digits, row, shift, lives, colour)
    pokes[A_SND_PRIORITY] = struct.pack(">H", priority)
    pokes.update(_text_engine_pokes(flags))
    return pokes, row


def _model_score(digits, colour):
    """The test's own model of the two sweeps: (final digits, final colour byte, lives awarded).

    It exists to keep a case from passing vacuously: the image diff alone cannot tell "both cores
    carried this column" from "neither core did anything at all".
    """
    string = [colour] + list(digits)          # index 0 = the colour byte, 1..7 = the digits

    at = 1                                    # the promotion sweep stops one short of the last digit
    while at < N_SCORE_DIGITS and string[at] == BLANK:
        at += 1
    while at < N_SCORE_DIGITS:
        if ((string[at] ^ 0x80) - 0x80) < DIGIT_0:      # a SIGNED byte compare
            string[at] = (string[at] + BLANK_TO_DIGIT) & 0xff
        at += 1

    lives = 0
    for at in range(N_SCORE_DIGITS, 0, -1):
        while string[at] > DIGIT_9:                     # ...and this one is UNSIGNED
            if string[at - 1] == BLANK:
                string[at - 1] = DIGIT_0
            string[at - 1] = (string[at - 1] + 1) & 0xff
            string[at] = (string[at] - SCORE_CARRY) & 0xff
            if at == MODEL_LIFE_INDEX and not string[at - 1] & 1:
                lives += 1
    return bytes(string[1:]), string[0], lives


def _poison_is_safe(final_digits):
    """Would the attribution pass stay inside the image on this case? (see `poison` below)

    Poison re-runs both cores on an image whose every WRITTEN byte is inverted — which here means
    inverted score digits, i.e. a second, arbitrary run of the same two sweeps over ~digit. That is
    only safe while the sweeps cannot land on draw_string's 0x01 set-position byte, which would aim
    text_ptr through pos_to_screen at an address outside the 1 MiB buffer the candidate is handed.

    A string that settles at '0'..'9' (or an untouched leading blank, which is never written and so
    never poisoned) inverts to 0xc6..0xcf, which the promotion lifts to 0xd6..0xdf and the carries
    then bring back down ten at a time — at most 17 of them, so the running total tops out at 0xf0
    and can never wrap into the control range. Any other settled string can, so it is left alone.
    """
    return all(byte == BLANK or DIGIT_0 <= byte <= DIGIT_9 for byte in final_digits)


def _score_case(entry, glue, digits, object_addr=A_OBJECT_TABLE, lives=0, colour=SCORE_COLOR,
                expect_lives=None, poison=None, note="", **staging):
    """Run both cores, then check the run was not vacuous against the model above.

    `poison` defaults to whatever `_poison_is_safe` allows for this string, so a case does not have
    to reason about the attribution pass itself; pass False to skip it outright.
    """
    if poison is None:
        poison = _poison_is_safe(_model_score(digits, colour)[0])
    pokes, row = _score_pokes(digits, object_addr, lives=lives, colour=colour, **staging)
    diffs, info = differential(entry, {"a0": object_addr, "_pokes": pokes}, glue, poison=poison)
    assert not diffs, (f"entry={entry:#x} object={object_addr:#x} digits={bytes(digits)!r} "
                       f"lives={lives:#x} colour={colour:#x} {staging} {note}\n{report(diffs)}")

    final_digits, final_colour, awarded = _model_score(digits, colour)
    if expect_lives is not None:
        assert awarded == expect_lives, (
            f"the test's own model awards {awarded} extra lives, the case says {expect_lives} — "
            f"the staging does not mean what the case claims")
    for index in range(N_SCORE_DIGITS):
        if final_digits[index] == digits[index]:
            continue
        addr = object_addr + OBJ_SCORE_FIRST_DIGIT + index
        assert info["writes"].get(addr) == final_digits[index], (
            f"digit {index}: the original left {info['writes'].get(addr)}, the model says "
            f"{final_digits[index]:#x}")
    if final_colour != colour:
        assert info["writes"].get(object_addr + SCORE_COLOR_BYTE) == final_colour, (
            "the carry out of the leftmost digit did not reach the string's colour byte")
    if awarded:
        assert info["writes"].get(object_addr + OBJ_LIVES) == (lives + awarded) & 0xff, (
            "the extra lives did not reach the record's life count")
    assert any(row <= addr < row + SCORE_ROW_CELLS * CELL_BYTES for addr in info["writes"]), (
        f"nothing was painted at the score row itself ({row:#x}) — the case staged the HUD "
        f"somewhere the routine never looks")
    return info


SCORE_ENTRIES = ((ENTRY_SCORE_UPDATE, A_OBJECT_TABLE),
                 (ENTRY_SCORE_UPDATE_P2, A_PLAYER2),
                 (ENTRY_SCORE_UPDATE_P1, A_OBJECT_TABLE))


def _score_glue(entry, object_addr):
    if entry == ENTRY_SCORE_UPDATE_P1:
        return lambda lib, buf: lib.g_score_update_p1(buf)
    if entry == ENTRY_SCORE_UPDATE_P2:
        return lambda lib, buf: lib.g_score_update_p2(buf)
    return lambda lib, buf: lib.g_score_update(buf, object_addr)


def _update(digits, object_addr=A_OBJECT_TABLE, **kwargs):
    """The A0 entry — what every case below uses unless it is about the aliases themselves."""
    return _score_case(ENTRY_SCORE_UPDATE,
                       lambda lib, buf: lib.g_score_update(buf, object_addr),
                       digits, object_addr=object_addr, **kwargs)


# ---- the three entry points ----

@pytest.mark.parametrize("object_addr", HUD_SLOTS)
def test_score_update_takes_its_object_from_a0(object_addr):
    """0x14160 falls straight into the shared body with whatever A0 holds — including a record
    that is neither player's, which the two aliases below can never reach."""
    _update(b"  1239:", object_addr=object_addr, expect_lives=0)


@pytest.mark.parametrize("entry,object_addr,other", ((ENTRY_SCORE_UPDATE_P1, A_OBJECT_TABLE,
                                                      A_PLAYER2),
                                                     (ENTRY_SCORE_UPDATE_P2, A_PLAYER2,
                                                      A_OBJECT_TABLE)))
def test_score_update_aliases_load_their_own_player_and_ignore_a0(entry, object_addr, other):
    """Each alias is `movem` + `movea.l #<slot>,a0` + a branch into the body, so the A0 it was
    entered with is dead. The other player's record carries its own settled string and its own
    screen band, so working on the wrong one shows as both digits and pixels."""
    _score_case(entry, _score_glue(entry, object_addr), b"  1239:", object_addr=object_addr,
                expect_lives=0, note=f"other={other:#x}")


# ---- the promotion sweep (0x1417c..0x141a8) ----

def test_score_update_leading_blanks_stay_blank():
    """The sweep skips over the blanks BEFORE the first real character rather than filling them
    with zeroes, which is what keeps the row right-aligned."""
    for digits in (b"      0", b"     10", b"  12340", b"1234560"):
        _update(digits, expect_lives=0, note=repr(digits))


def test_score_update_promotes_a_bumped_blank():
    """The live case: a caller adds 5 into a position still holding ' ', leaving 0x25, and this is
    what turns it into '5'. Nothing else in the routine would."""
    _update(b"     %0", expect_lives=0)


@pytest.mark.parametrize("digits", (b"    12%", b"      %"))
def test_score_update_never_promotes_the_last_digit(digits):
    """The sweep stops one short of the units position, so a bump landing THERE is never repaired.

    Unreachable in the game — every reset writes '0' into that byte (`move.b #$30,68(a0)`) and no
    caller adds to it — but it is the sweep's bound. The first string RUNS the promotion up to that
    bound (a reconstruction that went one place further turns the '%' into a '5'); the second is all
    blanks, so the skip loop hits the same bound and returns without promoting anything at all.
    """
    info = _update(digits, expect_lives=0, note=repr(digits))
    assert A_OBJECT_TABLE + OBJ_SCORE_LAST_DIGIT not in info["writes"], (
        "the units digit was rewritten — the promotion sweep ran one position too far")


@pytest.mark.parametrize("byte", (0x00, 0x1f, 0x21, 0x2f, 0x30, 0x31, 0x7f, 0x80, 0xef, 0xff))
def test_score_update_promotion_is_a_signed_compare(byte):
    """`cmpi.b #$30 ; bge` — bytes 0x80..0xff are NEGATIVE, so they are promoted just as 0x00..0x2f
    are, while 0x30..0x7f are left alone. An unsigned reading gets the whole top half backwards."""
    _update(b"  0" + bytes([byte]) + b"000")


def test_score_update_promotes_every_position_after_the_first_non_blank():
    """One blank per position, each preceded by a real digit, so the promotion has to reach it."""
    for index in range(1, N_SCORE_DIGITS - 1):
        digits = bytearray(b"0000000")
        digits[index] = BLANK
        _update(bytes(digits), expect_lives=0, note=f"blank at {index}")


# ---- the carry sweep (0x141b8..0x14200) ----

@pytest.mark.parametrize("index", range(N_SCORE_DIGITS))
def test_score_update_carries_every_column(index):
    """':' is '9' + 1. Every position carries, the units included — which is the one the promotion
    sweep above never reaches, so only the carry sweep can be reading it."""
    digits = bytearray(b"0000000")
    digits[index] = DIGIT_9 + 1
    _update(bytes(digits), note=f"carry at {index}")


def test_score_update_carry_cascades_the_whole_string():
    """A string of nines carries all the way up, one column at a time."""
    _update(b"099999:")


def test_score_update_carry_promotes_a_blank_column():
    """A carry arriving at a still-blank column makes it '0' first, which is how the number grows
    a digit to the left. Without that step the ' ' would be incremented to '!'."""
    _update(b"    :00", expect_lives=0)


@pytest.mark.parametrize("byte", (DIGIT_9 + 1, 0x44, 0x50, 0x7f, 0x80, 0xff))
def test_score_update_carry_repeats_until_the_digit_is_a_digit_again(byte):
    """`bls` is UNSIGNED, so anything above '9' — 0x80 and 0xff included — is carried ten at a time
    until it lands back in range. The column above therefore gains several units in one call."""
    _update(b"00" + bytes([byte]) + b"0000", note=f"units {byte:#x}")


def test_score_update_carries_out_of_the_leftmost_digit_into_the_colour_byte():
    """Every column's carry lands one byte to its LEFT, and the leftmost digit's neighbour is the
    string's `02 <colour>` pair — so an eight-digit score recolours its own row instead of
    overflowing cleanly. Unreachable in a real game; reproduced, not fixed."""
    info = _update(b":000000", expect_lives=0)
    assert info["writes"].get(A_OBJECT_TABLE + SCORE_COLOR_BYTE) == SCORE_COLOR + 1


@pytest.mark.parametrize("colour", (0, 1, SCORE_COLOR, 0xf))
def test_score_update_draws_the_string_from_its_control_pair(colour):
    """draw_string is handed OBJ_SCORE_TEXT, not the first digit, so the `02 <colour>` pair really
    is part of the string — a different colour paints different pixels."""
    _update(b"  12340", colour=colour, expect_lives=0)


# ---- the extra life ----

@pytest.mark.parametrize("ten_thousands", tuple(b"0123456789") + (BLANK,))
def test_score_update_extra_life_when_the_ten_thousands_turns_even(ten_thousands):
    """One carry out of the thousands column, i.e. one 10,000 crossed. The life is paid only when
    the digit it lands on comes out EVEN (`btst #0`), which is one life per 20,000 points."""
    digits = b"00" + bytes([ten_thousands]) + b":000"
    expected = DIGIT_0 + 1 if ten_thousands == BLANK else ten_thousands + 1
    _update(digits, lives=2, expect_lives=0 if expected & 1 else 1)


@pytest.mark.parametrize("index", (0, 1, 2, 4, 5, 6))
def test_score_update_no_extra_life_from_any_other_column(index):
    """`cmp.b #$41,d0` — only the thousands column is checked, whatever the digit above it ends up
    being. Every one of these carries leaves an EVEN digit behind and still pays nothing."""
    digits = bytearray(b"1111111")
    digits[index] = DIGIT_9 + 1
    _update(bytes(digits), expect_lives=0, note=f"carry at {index}")


def test_score_update_pays_several_lives_in_one_call():
    """A digit far above '9' carries repeatedly, and each carry re-tests the column above — so one
    call can cross several 20,000 boundaries. The five carries here step it 1..5, even twice."""
    _update(b"000" + bytes([DIGIT_9 + 50]) + b"000", lives=1, expect_lives=2)


@pytest.mark.parametrize("lives", (0, 1, 4, 0x7f, 0x80, 0xfe, 0xff))
def test_score_update_extra_life_is_a_byte_increment(lives):
    """`addq.b #1,76(a0)` wraps inside the byte, and draw_lives reads the result as SIGNED — so a
    count of 0x7f becomes 0x80 and the row it repaints comes out empty."""
    _update(b"001:000", lives=lives, expect_lives=1)


def test_score_update_extra_life_redraws_player_1s_row_for_any_other_object():
    """The life is added to the object A0 named, but draw_lives dispatches on that pointer and both
    of its bodies then reload the object from a CONSTANT — so a scratch record's extra life bumps
    its own count and repaints PLAYER 1's lives row."""
    info = _update(b"001:000", object_addr=SCORE_SCRATCH, lives=0, expect_lives=1)
    p1_row = _hud_row(A_OBJECT_TABLE) + LIVES_HUD_ADVANCE
    assert any(p1_row <= addr < p1_row + LIVES_ROW_CELLS * CELL_BYTES for addr in info["writes"]), (
        "player 1's lives row was not repainted")


@pytest.mark.parametrize("priority,plays", ((SND_PRIORITY_IDLE, True), (SND_EXTRA_LIFE, True),
                                            (SND_EXTRA_LIFE - 1, False), (0x8000, False)))
def test_score_update_extra_life_sound_goes_through_play_sound(priority, plays):
    """The sound is off-image (XBIOS Dosound), so only the kit's ledger sees it — and it is issued
    through play_sound, which drops a request that does not outrank what is already playing. The
    signed gate is what makes 0x8000 refuse where 0x10 admits."""
    info = _update(b"001:000", lives=0, expect_lives=1, priority=priority)
    assert bool(info["regs"]["dosound"]) == plays, (
        f"priority={priority:#x}: the original {'played no' if plays else 'played a'} sound")
    if plays:
        assert info["writes"].get(A_SND_PRIORITY + 1) == SND_EXTRA_LIFE, (
            "play_sound did not latch the extra-life index as the sound now playing")


# ---- the redraw ----

@pytest.mark.parametrize("shift", (0, 1, 5, 8, 0xf6, 0xff))
def test_score_update_row_shift_is_the_records_low_byte(shift):
    """text_shift comes from `move.w 58(a0),d0 ; move.b d0,...` — the LOW byte of the word field,
    with noise staged in the high byte a reconstruction reading the field's own address would take."""
    _update(b"  12340", shift=shift, expect_lives=0, seed=shift)


@pytest.mark.parametrize("score_ptr", (SCREEN + 0x2000, SCREEN + 0x2001, SCREEN + 0x2004,
                                       SCREEN + 0x2000 + SCREEN_ROW_BYTES))
def test_score_update_row_follows_the_records_screen_pointer(score_ptr):
    """text_ptr is the record's own pointer — nothing here is a constant, and the pointer is not
    even cell-aligned in one of these."""
    _update(b"  12340", expect_lives=0, score_ptr=score_ptr, seed=score_ptr & 0xff)


@pytest.mark.parametrize("flags", (0, TEXT_FLAG_LARGE_FONT, TEXT_FLAG_BACKGROUND,
                                   TEXT_FLAG_LARGE_FONT | TEXT_FLAG_BACKGROUND, 0xff))
def test_score_update_sets_the_font_and_the_bar_then_clears_only_the_bar(flags):
    """`bset #7` before the carries and `bset #4` / `bclr #4` around the draw: the large font is
    left switched on for whatever draws next, the background bar is not."""
    info = _update(b"  12340", flags=flags, expect_lives=0, seed=flags)
    assert info["writes"].get(A_TEXT_FLAGS) == ((flags | TEXT_FLAG_LARGE_FONT)
                                                & ~TEXT_FLAG_BACKGROUND)
    assert info["writes"].get(A_TEXT_BG_COLOR) == _defines("src/score.c")["HUD_BG_COLOR"]


# ---- fuzz ----

# Weighted so most strings look like a real record's — digits and blanks — while the whole byte
# range still turns up, which is where the signed promotion and the unsigned carry are separated.
SCORE_FUZZ_BYTES = tuple(b"0123456789") * 4 + (BLANK,) * 8 + tuple(range(0x100))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_score_update_fuzz(chunk):
    rng = random.Random(0x5c02e)               # seeded ONCE — every chunk replays this stream
    cases = [(rng.randrange(len(SCORE_ENTRIES)),
              bytes(rng.choice(SCORE_FUZZ_BYTES) for _ in range(N_SCORE_DIGITS)),
              rng.randint(0, 0xff), rng.randint(0, 0xff), rng.randint(0, 0xf),
              rng.choice((0, 1, SND_PRIORITY_IDLE, 0x7fff)), rng.randint(0, 0xff))
             for _ in range(200)]
    ran = 0
    for index, (which, digits, shift, lives, colour, priority, flags) in enumerate(cases):
        if index % FUZZ_CHUNKS != chunk:
            continue
        # A string that SETTLES on draw_string's set-position byte aims text_ptr through
        # pos_to_screen at an address outside the 1 MiB buffer the candidate is handed. No caller
        # can produce one (they add a small number to a digit or a blank), and the crash it causes
        # is the harness's limit rather than a divergence, so those cases are dropped.
        if TEXT_SET_POS in _model_score(digits, colour)[0]:
            continue
        entry, object_addr = SCORE_ENTRIES[which]
        _score_case(entry, _score_glue(entry, object_addr), digits, object_addr=object_addr,
                    shift=shift, lives=lives, colour=colour, priority=priority, flags=flags,
                    seed=index, poison=False, note=f"case {index}")
        ran += 1
    assert ran, "this shard ran no cases"


# ------------------------------------------------------------------ mirrored-constant pins
#
# Everything above restates addresses and offsets that really live in ../names.txt and in the C.
# Drift in a mirrored address is INVISIBLE to the differential — a staged input would land in dead
# memory, both cores would agree about the game's own untouched data, and the case would go green
# proving nothing. So each mirror is pinned to its single source of truth here.

def _pin(defines, origin, mirrored):
    """Pin {C name: the value this file restates} against the `#define`s scraped from `origin`."""
    for name, value in mirrored.items():
        got = defines.get(name)
        assert got == value, (f"{name}: {origin} has "
                              f"{'no such #define' if got is None else hex(got)}, "
                              f"test has {value:#x}")


def test_entry_addresses_match_names_txt():
    """Every address this file enters the oracle at is the address names.txt gives that function."""
    for addr, name in ((ENTRY_SCORE_UPDATE, "score_update"),
                       (ENTRY_SCORE_UPDATE_P1, "score_update_p1"),
                       (ENTRY_SCORE_UPDATE_P2, "score_update_p2"),
                       (ENTRY_DRAW_LIVES, "draw_lives"),
                       (ENTRY_DRAW_LIVES_P1, "draw_lives_p1"),
                       (ENTRY_DRAW_LIVES_P2, "draw_lives_p2"),
                       (ENTRY_DRAW_MESSAGES, "draw_messages"),
                       (ENTRY_FIND_FREE_MESSAGE, "find_free_message"),
                       (ENTRY_FLASH_HISCORE_COLOR, "flash_hiscore_color"),
                       (ENTRY_DRAW_HISCORE_CURSOR, "draw_hiscore_cursor"),
                       (ENTRY_DRAW_HISCORE_ENTRY, "draw_hiscore_entry")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_executed_code_spans_match_names_txt():
    """The spans test_draw_hiscore_entry_fuzz refuses to write into are [routine, next routine).

    They are hand-copied addresses steering a `continue`, so a drifted one would silently narrow or
    widen the fuzz instead of failing — the one filter in this file that can quietly shrink a
    battery. Both ends of each span are named in ../names.txt.
    """
    for (start, end), (start_name, end_name) in zip(EXECUTED_CODE,
                                                    (("draw_hiscore_entry", "lava_troll"),
                                                     ("draw_string", "snd_tone_sweep"),
                                                     ("pos_to_screen", "screen_to_pos"))):
        assert harness.NAME_MAP.get(start) == start_name, f"no `{start_name}` at {start:#x}"
        assert harness.NAME_MAP.get(end) == end_name, f"no `{end_name}` at {end:#x}"


def test_mirrored_constants_match_score_h():
    """The globals, record fields and string addresses this layer owns."""
    _pin(_defines("include/score.h"), "score.h", {
        "A_players_alive": A_PLAYERS_ALIVE, "A_game_over_flag": A_GAME_OVER_FLAG,
        "A_hiscore_name": A_HISCORE_NAME,
        "OBJ_SCORE_PTR": OBJ_SCORE_PTR, "OBJ_LIVES": OBJ_LIVES,
        "OBJ_SCORE_TEXT": OBJ_SCORE_TEXT, "OBJ_SCORE_FIRST_DIGIT": OBJ_SCORE_FIRST_DIGIT,
        "OBJ_SCORE_LIFE_DIGIT": OBJ_SCORE_LIFE_DIGIT,
        "OBJ_SCORE_LAST_DIGIT": OBJ_SCORE_LAST_DIGIT,
        "MSG_TIMER": MSG_TIMER, "MSG_COLOR": MSG_COLOR, "MSG_SHIFT": MSG_SHIFT,
        "MSG_STRING": MSG_STRING, "MSG_KIND_PERSISTENT": MSG_KIND_PERSISTENT,
        "STR_LIFE_BLANK": STR_LIFE_BLANK, "STR_LIFE_P1": STR_LIFE_P1,
        "STR_LIFE_P2": STR_LIFE_P2, "STR_GAME_OVER": STR_GAME_OVER,
    })
    # OBJ_SCORE_SHIFT_LO is spelled as an expression in the header (the low byte of the .w field),
    # so it is not scraped: pin it against the word offset it is derived from instead.
    assert _defines("include/score.h")["OBJ_SCORE_SHIFT"] + 1 == OBJ_SCORE_SHIFT_LO


def test_mirrored_constants_match_score_c():
    """...and the values that live in the reconstruction's body rather than in its header."""
    _pin(_defines("src/score.c"), "score.c", {
        "LIVES_DRAWN": LIVES_DRAWN, "LIVES_HUD_ADVANCE": LIVES_HUD_ADVANCE,
        "LIVES_SHIFT_ADVANCE": LIVES_SHIFT_ADVANCE,
        "HISCORE_UNDERLINE_OFF": HISCORE_UNDERLINE_OFF,
        "HISCORE_UNDERLINE_CELLS": HISCORE_UNDERLINE_CELLS,
        "HISCORE_COLUMN_BYTES": HISCORE_COLUMN_BYTES,
        "HISCORE_ENTRY_OFF": HISCORE_ENTRY_OFF,
        "SCORE_BLANK": BLANK, "SCORE_DIGIT_0": DIGIT_0, "SCORE_DIGIT_9": DIGIT_9,
        "SCORE_BLANK_TO_DIGIT": BLANK_TO_DIGIT, "SCORE_CARRY": SCORE_CARRY,
        "SND_EXTRA_LIFE": SND_EXTRA_LIFE,
    })


def test_mirrored_constants_match_the_sound_layer():
    """score_update's extra life leaves through play_sound, so this file restates two of the sound
    layer's own constants — the priority global it is gated on and the idle value that admits it."""
    _pin(_defines("include/sound.h"), "sound.h", {"A_snd_priority": A_SND_PRIORITY,
                                                  "SND_PRIORITY_IDLE": SND_PRIORITY_IDLE})
    assert harness.NAME_MAP.get(A_SND_PRIORITY) == "snd_priority", \
        "names.txt has no `snd_priority` at that address"


def test_mirrored_constants_match_the_shared_headers():
    """The message table, the text engine and the geometry — all owned by other layers' headers.

    The three high-score globals are the interesting ones: score.h reaches them through ALIASES
    (A_hiscore_cursor = A_draw_shift, ...) rather than fresh `#define`s, precisely so there is one
    address per name, which also means `_defines` never sees the alias. Pinning the addresses they
    alias is what keeps this file's mirrors honest.
    """
    _pin(_defines("include/object.h"), "object.h", {
        "A_message_table": A_MESSAGE_TABLE, "A_message_table_END": A_OBJECT_TABLE,
        "MSG_KIND": MSG_KIND, "MSG_SCREEN_PTR": MSG_SCREEN_PTR, "MSG_RECORD": MSG_RECORD,
        "A_draw_x": A_HISCORE_FLASH,
    })
    draw_h = _defines("include/draw.h")
    _pin(draw_h, "draw.h", {
        "A_player2": A_PLAYER2, "A_draw_dst_off": A_HISCORE_LETTER,
        "A_text_ptr": A_TEXT_PTR, "A_text_shift": A_TEXT_SHIFT, "A_text_color": A_TEXT_COLOR,
        "A_text_bg_color": A_TEXT_BG_COLOR, "A_text_flags": A_TEXT_FLAGS,
        "TEXT_FLAG_BACKGROUND": TEXT_FLAG_BACKGROUND,
        "TEXT_FLAG_LARGE_FONT": TEXT_FLAG_LARGE_FONT,
    })
    # _text_engine_pokes stages the whole block as ONE `>IBBBBHH` poke, which only reaches the right
    # fields while they are consecutive in this order.
    assert [draw_h[name] - A_TEXT_PTR for name in ("A_text_shift", "A_text_color",
                                                   "A_text_bg_color", "A_text_flags",
                                                   "A_text_x", "A_text_y")] == [4, 5, 6, 7, 8, 10], \
        "the text-engine globals are no longer the consecutive block _text_engine_pokes packs"
    _pin(_defines("include/addrs.h"), "addrs.h", {
        "A_screen_base": A_SCREEN_BASE, "A_object_table": A_OBJECT_TABLE,
        "A_draw_shift": A_HISCORE_CURSOR,
    })
    _pin(_defines("include/joust.h"), "joust.h", {
        "OBJ_SIZE": OBJ_SIZE, "CELL_BYTES": CELL_BYTES, "SCREEN_ROW_BYTES": SCREEN_ROW_BYTES,
    })
    assert N_MESSAGES * MSG_RECORD == A_OBJECT_TABLE - A_MESSAGE_TABLE, (
        "the table is not 24 slots long — _message_table would stage past its end, or short of it")


def test_global_names_match_names_txt():
    """...and every one of those addresses is the global names.txt says it is."""
    for addr, name in ((A_PLAYERS_ALIVE, "players_alive"), (A_GAME_OVER_FLAG, "game_over_flag"),
                       (A_SCREEN_BASE, "screen_base"), (A_HISCORE_FLASH, "draw_x"),
                       (A_HISCORE_CURSOR, "draw_shift"), (A_HISCORE_LETTER, "draw_dst_off"),
                       (A_TEXT_PTR, "text_ptr"), (A_TEXT_SHIFT, "text_shift"),
                       (A_TEXT_COLOR, "text_color"), (A_TEXT_BG_COLOR, "text_bg_color"),
                       (A_TEXT_FLAGS, "text_flags"), (A_MESSAGE_TABLE, "message_table"),
                       (A_OBJECT_TABLE, "object_table"), (A_PLAYER2, "player2"),
                       (A_HISCORE_NAME, "hiscore_name")):
        assert harness.NAME_MAP.get(addr) == name, f"names.txt has no `{name}` at {addr:#x}"


def test_staged_strings_are_the_ones_the_image_carries():
    """The four string addresses are not just consistent, they are the strings they claim to be.

    A mirror can agree with the C and still be wrong about the binary; this reads the bytes. The
    life glyph is '$' over '%' (a backspace between them), and the game-over banner is the one whose
    expiry ends the game.
    """
    image = bytes(harness.BASE_IMAGE)
    assert image[STR_LIFE_BLANK:STR_LIFE_BLANK + 2] == b" \x00"
    for glyph in (STR_LIFE_P1, STR_LIFE_P2):
        assert image[glyph + 4:glyph + 10] == b"$\x08\x02\x01\x03\x00", "not the life glyph string"
        assert image[glyph + 10:glyph + 12] == b"%\x00"
    assert image[STR_GAME_OVER:STR_GAME_OVER + 19] == b"\x09\x01THY GAME IS OVER\x00"
