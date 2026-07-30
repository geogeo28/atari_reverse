"""Differential tests for Joust's HUD layer (src/score.c).

Covered here, leaves first: find_free_message @ 0x1435c, flash_hiscore_color @ 0x144b0,
draw_hiscore_cursor @ 0x14658, draw_hiscore_entry @ 0x146a6, the draw_lives alias family
@ 0x14246/0x1424e/0x14260 and draw_messages @ 0x142de.

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
SCREEN = 0x70000
STRINGS = 0x80000

# Every fuzz below generates its whole corpus and THEN keeps `index % chunks == chunk`, so the
# shards see the same cases however they are scheduled (the recipe in ../../buggyboy/recreate/
# README.md). Each also counts what it ran and asserts it ran something, so a filter that grew to
# reject everything fails instead of going green on an empty shard.
FUZZ_CHUNKS = 2
FIND_FREE_FUZZ_CHUNKS = 4       # cheap cases, so this one shards further

_U8P = ctypes.POINTER(ctypes.c_uint8)
for _glue, _nargs, _ret in (("g_find_free_message", 0, ctypes.c_uint32),
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
    for addr, name in ((ENTRY_DRAW_LIVES, "draw_lives"),
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
    })


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
