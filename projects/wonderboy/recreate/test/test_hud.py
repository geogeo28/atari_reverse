"""Differential test for the eleven status-panel leaves of src/hud.c.

Every case runs the ORIGINAL routine under the Musashi oracle and the reconstruction on the same
image, requires the two to agree byte for byte over the whole image, and bounds the original's write
set to the bytes the case says it may touch. Where a routine returns a register a caller reads back
(`hud_blit_meter_cell`'s cursor) the case compares that too.

These are not the effect handlers' shape, and three things follow from that:

  * MOST OF THEM TAKE REGISTERS. Ghidra recovered `void FUN(void)` for all eleven; the register
    interfaces are read off the disassembly, `../names.txt` carries a `proto` line for each one it
    can express, and the C takes a `uint32_t` per register so that the operand size the original
    applies (`move.w d0,...` on a longword, `adda.w` on a 32-bit product) happens where a case can
    pin it. Several cases feed a register whose high half must NOT reach the result.
  * FIVE OF THEM DRAW, three of them through `screen_back` — a longword IN MEMORY, so a case has to
    seed it, and the seeds below are the game's own back AND front buffers, since nothing may be
    hardcoded. (The other two, `hud_blit_cell_copy` and `hud_blit_cell_or`, are handed a destination
    their caller already resolved.) Each blit's expected bytes come from the game's own source data
    in the loaded image rather than from the reconstruction, so a case says WHICH bytes moved and not
    only that both sides agree.
  * FOUR OF THEM ARE PACKED-BCD ACCUMULATORS. Their expected value is stated in DECIMAL — the
    reading "packed BCD" means — and converted back, which is a different statement from
    src/hud.c's nibble arithmetic rather than a copy of it.

KNOWINGLY NOT PINNED
  * THE X FLAG THE BCD ROUTINES ARE ENTERED WITH. `abcd`/`sbcd` fold in the 68000 extend bit, and
    the caller's X reaches the first digit pair (src/hud.c has the argument). The oracle FORCES the
    entry SR to `$2700` after its reset — a 68000 reset does not clear the condition codes, so
    without the force a run would inherit the previous one's — and `emu.run` has no entry-CCR
    parameter, so X = 0 is the only entry condition expressible here and
    `test_a_bcd_add_of_zero_pins_the_entry_extend_bit` is the whole of what these cases hold. The
    game does reach them with X = 1.
  * `hud_meter_add_clamped`'s comparison STRICTNESS, for the reason batch 1 registered the effect
    handlers': at a raise landing exactly on the maximum both arms store the same word, so `<=` and
    `<` are indistinguishable from outside. What the sweep pins is the comparison's POSITION.
  * THE REGISTERS THE BLITS LEAVE BEHIND, except `hud_blit_meter_cell`'s cursor. The kit's oracle
    reports d0/d1/a0/a1 only, and every call site in the game reloads them (`../names.txt`), so a
    case would be pinning a value nothing reads.
  * WHAT ANY OF IT MEANS. `../names.txt` names these for their mechanism; a green suite would not
    make a meaning-level name true.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (MOVE_W_ABS_L_ABS_L, MOVE_W_ABS_L_D0, MOVE_W_D0_ABS_L, RTS, longword, word)
from layout import wb

import emu   # noqa: E402  (harness puts the kit's oracle on sys.path)

# --- the globals and the geometry, from the header both languages read ---------------------------
SCREEN_BACK = wb("SCREEN_BACK")
SCREEN_LINE = wb("SCREEN_LINE")
PLANE_STRIDE = wb("PLANE_STRIDE")
PLANES = wb("PLANES")

STATE_FLAG_A32 = wb("STATE_FLAG_A32")
TABLE_PTR = wb("TABLE_PTR_21E8C")
TABLE_PTR_LEN = wb("TABLE_PTR_LEN")
TABLE_A32_CLEAR = wb("TABLE_A32_CLEAR")
TABLE_A32_SET = wb("TABLE_A32_SET")
FRAME_TICK = wb("FRAME_TICK_B39A")

RECORD_BITMAP_TABLE = wb("RECORD_BITMAP_TABLE")
RECORD_BITMAP_LEN = wb("RECORD_BITMAP_LEN")
RECORD_BITMAP_ORIGIN = wb("RECORD_BITMAP_ORIGIN")
RECORD_BITMAP_BYTES = wb("RECORD_BITMAP_BYTES")
RECORD_BITMAP_ROWS = wb("RECORD_BITMAP_ROWS")

BCD_COUNTER = wb("BCD_COUNTER")
BCD_COUNTER_LEN = wb("BCD_COUNTER_LEN")
BCD_SCORE = wb("BCD_SCORE")
BCD_SCORE_LEN = wb("BCD_SCORE_LEN")
BCD_HISCORE = wb("BCD_HISCORE")
BCD_ADDEND = wb("BCD_ADDEND")

METER_CELL_TABLE = wb("METER_CELL_TABLE")
METER_CELL_ENTRIES = wb("METER_CELL_ENTRIES")
METER_CELL_OFFSET_LEN = wb("METER_CELL_OFFSET_LEN")
METER_CELL_ROWS = wb("METER_CELL_ROWS")

HUD_CELL_BYTES = wb("HUD_CELL_BYTES")
HUD_CELL_ROWS = wb("HUD_CELL_ROWS")

PANEL_FRAME_INDEX = wb("PANEL_FRAME_INDEX")
PANEL_FRAME_TABLE = wb("PANEL_FRAME_TABLE")
PANEL_FRAME_LEN = wb("PANEL_FRAME_LEN")
PANEL_FRAME_ORIGIN = wb("PANEL_FRAME_ORIGIN")
PANEL_FRAME_BYTES = wb("PANEL_FRAME_BYTES")
PANEL_FRAME_ROWS = wb("PANEL_FRAME_ROWS")

METER_VALUE = wb("HUD_METER_VALUE")
METER_MAX = wb("HUD_METER_MAX")
WORD_LEN = wb("STATE_WORD_LEN")
RECORD_LIST = leaf.entry_of("effect_record_list")

WORD_MASK = leaf.WORD_MASK

# The panel blits LOOP, so leaf.py's default cap (LEAF_INSN_CAP = 64, sized for the straight-line
# leaves, whose runs are at most six instructions) does not fit them. Stated from the widest one's
# own geometry rather than guessed: the record bitmap runs 32 rows of eight moves, a lea and a dbf,
# which is 327 instructions with its prologue — so 400 still leaves no room for a second pass.
PANEL_BLIT_INSN_CAP = 400

# The game's own screen buffers (../names.txt: screen_back starts at $70000, screen_front $78000).
# Both are used, because a blit's destination comes out of MEMORY and nothing may be hardcoded.
SCREEN_BUFFERS = (0x70000, 0x78000)


# --- the shared reading helpers ------------------------------------------------------------------
# The operand encoders (`word`/`longword`), the entry-pin asserts and the write-set readers
# (`leaf.read_int`, `leaf.assert_rows`) come from leaf.py, which test_effects.py shares.

def _signed_word(value):
    return value - 0x10000 if value & 0x8000 else value


def _indexed_bitmap(table, index, stride):
    """Where `mulu.w #stride,d0` and the `adda.w` / `lea (0,An,d0.w)` after it land: the 32-bit
    product is truncated to its LOW WORD, sign-extended, and added to the table in 32 bits — so an
    index whose product overflows a word loses the overflow, and one with bit 15 set goes BELOW the
    table. Python has neither of those two wraps by default, which is the whole reason this exists."""
    low_word = (index * stride) & WORD_MASK
    return (table + _signed_word(low_word)) & 0xffffffff


def _rows(base, length, rows):
    """The (address, length) of each row of a blit — its allowed write set, and a stride pin: rows
    landing 158 bytes apart instead of 160 would show up here as stray writes, not only as a diff."""
    return [(base + row * SCREEN_LINE, length) for row in range(rows)]


def _source_rows(source, length, rows):
    """The game's own bytes at ``source``, row by row, out of the loaded image."""
    return [bytes(harness.BASE_IMAGE[source + row * length:source + (row + 1) * length])
            for row in range(rows)]


def _filler(length, salt):
    """Deterministic filler for a destination the routine must overwrite (or, for the OR blit, must
    combine with). Not random: a case that fails should fail the same way twice."""
    return bytes(((index * 7 + salt * 31 + 1) & 0xff) for index in range(length))


def _seeded_rows(rows):
    return {addr: _filler(length, row) for row, (addr, length) in enumerate(rows)}


# --- the encodings each entry is pinned against --------------------------------------------------
# Named so the builders below read as instructions. Every operand is one of the constants above, so
# a wrong address, immediate, row count or stride fails at its own entry point rather than surfacing
# as a puzzling diff somewhere in a 1 MiB image. The four test_effects.py also spells (RTS and the
# three `move.w` forms) are imported from leaf.py instead, so the two batteries cannot disagree.
TST_W_ABS_W = b"\x4a\x78"           # tst.w <abs>.w
BNE_W = b"\x66\x00"
BRA_W = b"\x60\x00"
BLE_W = b"\x6f\x00"
MOVE_L_IMM_ABS_L = b"\x23\xfc"      # move.l #imm,<abs>.l
ADDQ_W_1_ABS_L = b"\x52\x79"        # addq.w #1,<abs>.l
MOVE_B_A0_D0 = b"\x10\x10"          # move.b (a0),d0   — leaves d0's high byte alive
MULU_W_IMM_D0 = b"\xc0\xfc"         # mulu.w #imm,d0   — 16 x 16 -> 32
LEA_ABS_L_A0 = b"\x41\xf9"          # lea <abs>.l,a0
LEA_ABS_L_A1 = b"\x43\xf9"          # lea <abs>.l,a1
LEA_A0_D0_W_A0 = b"\x41\xf0\x00\x00"  # lea (0,a0,d0.w),a0
ADDA_W_D0_A0 = b"\xd0\xc0"          # adda.w d0,a0
ADDA_W_A1_INC_A0 = b"\xd0\xd9"      # adda.w (a1)+,a0
MOVEA_L_ABS_W_A0 = b"\x20\x78"      # movea.l <abs>.w,a0
MOVEA_L_ABS_W_A1 = b"\x22\x78"      # movea.l <abs>.w,a1
ADDA_W_IMM_A1 = b"\xd2\xfc"         # adda.w #imm,a1
MOVE_W_IMM_D0 = b"\x30\x3c"
MOVE_W_IMM_D7 = b"\x3e\x3c"
MOVE_L_A0_INC_A1_INC = b"\x22\xd8"  # move.l (a0)+,(a1)+
MOVE_L_A0_INC_D1 = b"\x22\x18"      # move.l (a0)+,d1
OR_L_D1_A1_INC = b"\x83\x99"        # or.l d1,(a1)+    — so the OR blit READS the destination
MOVE_B_A2_INC_A0 = b"\x10\x9a"      # move.b (a2)+,(a0)
MOVE_B_A2_INC_D16_A0 = b"\x11\x5a"  # move.b (a2)+,d16(a0)
LEA_D16_A0_A0 = b"\x41\xe8"         # lea d16(a0),a0
LEA_D16_A1_A1 = b"\x43\xe9"         # lea d16(a1),a1
DBF_D0 = b"\x51\xc8"
DBF_D7 = b"\x51\xcf"
MOVEM_L_SAVE_A0_A1 = b"\x48\xe7\x00\xc0"     # movem.l a0/a1,-(a7)   (pre-decrement mask order)
MOVEM_L_RESTORE_A0_A1 = b"\x4c\xdf\x03\x00"  # movem.l (a7)+,a0/a1
MOVE_L_D0_ABS_L = b"\x23\xc0"
ABCD_PREDEC = b"\xc3\x08"           # abcd -(a0),-(a1)  — NOT the `and.b` the linear listing prints
SBCD_PREDEC = b"\x83\x08"           # sbcd -(a0),-(a1)  — nor the `or.b`
ADD_W_D0_ABS_L = b"\xd1\x79"        # add.w d0,<abs>.l  — a read-modify-write ON MEMORY
MOVE_W_ABS_L_D1 = b"\x32\x39"
CMP_W_ABS_L_D1 = b"\xb2\x79"
MOVEM_L_A0_INC_D0_D5 = b"\x4c\xd8\x00\x3f"   # movem.l (a0)+,d0-d5   (six longwords = 24 bytes)
MOVEM_L_D0_D5_A1 = b"\x48\xd1\x00\x3f"       # movem.l d0-d5,(a1)
MOVEM_L_D0_D5_D16_A1 = b"\x48\xe9\x00\x3f"   # movem.l d0-d5,d16(a1)

# A 68000 branch counts from the word AFTER its opcode, so every displacement below is the bytes it
# spans plus the 2 its own extension word occupies. Spelling that once is what lets the entry pins
# be built out of the geometry constants instead of out of transcribed hex.
BRANCH_EXTENSION = 2

# The four `movem` stores $bcd6 makes between two `lea 640(a1)`.
PANEL_FRAME_ROWS_PER_PASS = 4


def _dbf(loop_body_bytes):
    return word(-(loop_body_bytes + BRANCH_EXTENSION))


def _forward_branch(spanned_bytes):
    return word(spanned_bytes + BRANCH_EXTENSION)


def _longword_blit_tail(moves, move_bytes, row_bytes):
    """`lea (line - row_bytes)(a1),a1 / dbf d0` — the tail the three longword blits share."""
    lea = LEA_D16_A1_A1 + word(SCREEN_LINE - row_bytes)
    return lea + DBF_D0 + _dbf(moves * move_bytes + len(lea))


def _select_table_entry():
    store = MOVE_L_IMM_ABS_L + longword(TABLE_A32_CLEAR) + longword(TABLE_PTR)
    bra = BRA_W + _forward_branch(len(store))
    return (TST_W_ABS_W + word(STATE_FLAG_A32)
            + BNE_W + _forward_branch(len(store) + len(bra))
            + store + bra
            + MOVE_L_IMM_ABS_L + longword(TABLE_A32_SET) + longword(TABLE_PTR)
            + ADDQ_W_1_ABS_L + longword(FRAME_TICK) + RTS)


def _record_bitmap_entry():
    moves = RECORD_BITMAP_BYTES // 4
    return (MOVE_B_A0_D0
            + MULU_W_IMM_D0 + word(RECORD_BITMAP_LEN)
            + LEA_ABS_L_A0 + longword(RECORD_BITMAP_TABLE)
            + ADDA_W_D0_A0
            + MOVEA_L_ABS_W_A1 + word(SCREEN_BACK)
            + ADDA_W_IMM_A1 + word(RECORD_BITMAP_ORIGIN)
            + MOVE_W_IMM_D0 + word(RECORD_BITMAP_ROWS - 1)
            + MOVE_L_A0_INC_A1_INC * moves
            + _longword_blit_tail(moves, len(MOVE_L_A0_INC_A1_INC), RECORD_BITMAP_BYTES)
            + RTS)


def _bcd_entry(operation, staging, accumulator, length):
    """`movem save / move.<n> d0,addend / lea past-addend,a0 / lea past-accumulator,a1 /
    length x abcd|sbcd -(a0),-(a1) / movem restore / rts` — all four accumulators, whose only
    differences are the staging width, the accumulator and the digit count."""
    return (MOVEM_L_SAVE_A0_A1
            + staging + longword(BCD_ADDEND)
            + LEA_ABS_L_A0 + longword(BCD_ADDEND + length)
            + LEA_ABS_L_A1 + longword(accumulator + length)
            + operation * length
            + MOVEM_L_RESTORE_A0_A1 + RTS)


def _meter_cell_entry():
    plotted = MOVE_B_A2_INC_A0 + b"".join(
        MOVE_B_A2_INC_D16_A0 + word(plane * PLANE_STRIDE) for plane in range(1, PLANES))
    lea = LEA_D16_A0_A0 + word(SCREEN_LINE)
    return (MOVEA_L_ABS_W_A0 + word(SCREEN_BACK)
            + ADDA_W_A1_INC_A0
            + MOVE_W_IMM_D0 + word(METER_CELL_ROWS - 1)
            + plotted + lea
            + DBF_D0 + _dbf(len(plotted) + len(lea))
            + RTS)


def _meter_add_entry():
    return (ADD_W_D0_ABS_L + longword(METER_VALUE)
            + MOVE_W_ABS_L_D1 + longword(METER_MAX)
            + CMP_W_ABS_L_D1 + longword(METER_VALUE)
            + BLE_W + _forward_branch(len(RTS))
            + RTS
            + MOVE_W_ABS_L_ABS_L + longword(METER_MAX) + longword(METER_VALUE) + RTS)


def _cell_blit_entry(move):
    moves = HUD_CELL_BYTES // 4
    return (MOVE_W_IMM_D0 + word(HUD_CELL_ROWS - 1)
            + move * moves
            + _longword_blit_tail(moves, len(move), HUD_CELL_BYTES)
            + RTS)


def _panel_frame_entry():
    stores = MOVEM_L_D0_D5_A1 + b"".join(
        MOVEM_L_A0_INC_D0_D5 + MOVEM_L_D0_D5_D16_A1 + word(row * SCREEN_LINE)
        for row in range(1, PANEL_FRAME_ROWS_PER_PASS))
    lea = LEA_D16_A1_A1 + word(PANEL_FRAME_ROWS_PER_PASS * SCREEN_LINE)
    body = MOVEM_L_A0_INC_D0_D5 + stores + lea
    return (MOVE_W_ABS_L_D0 + longword(PANEL_FRAME_INDEX)
            + MULU_W_IMM_D0 + word(PANEL_FRAME_LEN)
            + LEA_ABS_L_A0 + longword(PANEL_FRAME_TABLE)
            + LEA_A0_D0_W_A0
            + MOVEA_L_ABS_W_A1 + word(SCREEN_BACK)
            + ADDA_W_IMM_A1 + word(PANEL_FRAME_ORIGIN)
            + MOVE_W_IMM_D7 + word(PANEL_FRAME_ROWS // PANEL_FRAME_ROWS_PER_PASS - 1)
            + body
            + DBF_D7 + _dbf(len(body))
            + RTS)


ENTRY_BYTES = {
    "select_table_21e8c_and_tick_b39a": _select_table_entry(),
    "hud_blit_record_bitmap": _record_bitmap_entry(),
    "bcd_add_counter_bd6e": _bcd_entry(ABCD_PREDEC, MOVE_W_D0_ABS_L, BCD_COUNTER, BCD_COUNTER_LEN),
    "bcd_sub_counter_bd6e": _bcd_entry(SBCD_PREDEC, MOVE_W_D0_ABS_L, BCD_COUNTER, BCD_COUNTER_LEN),
    "bcd_add_score_bd70": _bcd_entry(ABCD_PREDEC, MOVE_L_D0_ABS_L, BCD_SCORE, BCD_SCORE_LEN),
    "bcd_sub_score_bd70": _bcd_entry(SBCD_PREDEC, MOVE_L_D0_ABS_L, BCD_SCORE, BCD_SCORE_LEN),
    "hud_blit_meter_cell": _meter_cell_entry(),
    "hud_meter_add_clamped": _meter_add_entry(),
    "hud_blit_cell_copy": _cell_blit_entry(MOVE_L_A0_INC_A1_INC),
    "hud_blit_cell_or": _cell_blit_entry(MOVE_L_A0_INC_D1 + OR_L_D1_A1_INC),
    "hud_blit_panel_frame": _panel_frame_entry(),
}

# The batch this file was written for. Recorded rather than derived from ENTRY_BYTES, so a routine
# dropped from a table shrinks the battery loudly instead of silently.
HUD_LEAF_COUNT = 11

# --- the glue ------------------------------------------------------------------------------------
_select_table = leaf.image_glue("select_table_21e8c_and_tick_b39a")
_panel_frame = leaf.image_glue("hud_blit_panel_frame")
_record_bitmap = leaf.register_glue("hud_blit_record_bitmap", [ctypes.c_uint32])
_meter_add = leaf.register_glue("hud_meter_add_clamped", [ctypes.c_uint32])
_meter_cell = leaf.register_glue("hud_blit_meter_cell", [ctypes.c_uint32] * 2, ctypes.c_uint32)
_cell_blit = {name: leaf.register_glue(name, [ctypes.c_uint32] * 2)
              for name in ("hud_blit_cell_copy", "hud_blit_cell_or")}
_bcd = {name: leaf.register_glue(name, [ctypes.c_uint32])
        for name in ("bcd_add_counter_bd6e", "bcd_sub_counter_bd6e",
                     "bcd_add_score_bd70", "bcd_sub_score_bd70")}


def test_this_file_covers_the_whole_batch():
    leaf.assert_batch_is_complete(ENTRY_BYTES, HUD_LEAF_COUNT)


def test_the_bcd_fields_are_adjacent_in_the_order_the_accumulators_assume():
    """The accumulators reach their field by pre-decrementing from the field ABOVE it, so the
    `lea $bd70,a1` / `lea $bd74,a1` in the entry pins are the NEXT field's address doing double
    duty. If those constants ever disagreed the pins would still pass, on the wrong field."""
    assert BCD_COUNTER + BCD_COUNTER_LEN == BCD_SCORE
    assert BCD_SCORE + BCD_SCORE_LEN == BCD_HISCORE


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_an_entry_is_the_instruction_this_battery_reconstructs(name):
    """One assert per routine covering the address ../names.txt gives it, every global
    include/wonderboy.h gives that routine, and every immediate, row count and stride at once."""
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


# --- $b372: publish a table, tick the counter ----------------------------------------------------

# (the flag, the table it selects). $ffff is the value $1f2a writes; the other two non-zero seeds
# are there because the original tests the whole WORD, so a port that read one byte of it fails on
# exactly one of them.
TABLE_CASES = ((0x0000, TABLE_A32_CLEAR), (0xffff, TABLE_A32_SET),
               (0x0001, TABLE_A32_SET), (0xff00, TABLE_A32_SET))
# The tick is a bare `addq.w #1` with no bound, so its wrap is part of the routine.
TICK_SEEDS = (0x0000, 0x1234, 0xffff)


@pytest.mark.parametrize("tick", TICK_SEEDS, ids=[f"tick_{t:04x}" for t in TICK_SEEDS])
@pytest.mark.parametrize("flag,expected_table", TABLE_CASES,
                         ids=[f"flag_{c[0]:04x}" for c in TABLE_CASES])
def test_the_table_select_publishes_a_pointer_and_ticks_the_counter(flag, expected_table, tick):
    what = f"select_table with the flag {flag:#06x} and the tick at {tick:#06x}"
    # The pointer is seeded to the OTHER table, so a routine that wrote the wrong one is caught by
    # the value assert and one that wrote nothing by the attribution pass.
    other = TABLE_A32_SET if expected_table == TABLE_A32_CLEAR else TABLE_A32_CLEAR
    pokes = {STATE_FLAG_A32: word(flag), TABLE_PTR: longword(other), FRAME_TICK: word(tick)}
    info = leaf.run("select_table_21e8c_and_tick_b39a", _select_table,
                    [(TABLE_PTR, TABLE_PTR_LEN), (FRAME_TICK, WORD_LEN)], what,
                    regs={"_pokes": pokes})
    assert leaf.read_int(info, TABLE_PTR, TABLE_PTR_LEN, what) == expected_table, (
        f"{what}: wrong table")
    assert leaf.read_int(info, FRAME_TICK, WORD_LEN, what) == (tick + 1) & WORD_MASK, (
        f"{what}: wrong tick")


# --- $b410: the record list's bitmap -------------------------------------------------------------

# The bitmap selector, i.e. a record's high byte. 5..8 are the four `effect_push_record_*` handlers'
# own values; the other four are what makes the operand sizes observable, and every one of them
# lands the 1 KiB source inside the loaded program (which ends at 0x218d0):
#   $00  the first entry
#   $20  bit 5 set, so the product's low word is $8000 and `adda.w` SIGN-EXTENDS it — the source
#        moves BELOW the table, to $879c
#   $3f  the largest selector whose product still fits in a word
#   $40  the first selector whose product overflows the word entirely, so it addresses entry 0
#        again: the case that pins the truncation rather than only the sign extension
RECORD_SELECTORS = (0x05, 0x06, 0x07, 0x08, 0x00, 0x20, 0x3f, 0x40)

# `move.b (a0),d0` leaves d0's own high byte alive into the `mulu.w`, where it cannot reach the
# result (src/hud.c has the algebra). These pin that instead of arguing it. The record addresses do
# the same job for a0: the routine has no business knowing where the list is.
RECORD_ENTRY_D0 = (0x00000000, 0xdeadbe00, 0xffffff00)
RECORD_ADDRESSES = (RECORD_LIST, RECORD_LIST + 0x40)


def _run_record_bitmap(selector, screen, record, entry_d0, what):
    destination = screen + RECORD_BITMAP_ORIGIN
    rows = _rows(destination, RECORD_BITMAP_BYTES, RECORD_BITMAP_ROWS)
    pokes = {SCREEN_BACK: longword(screen), record: bytes([selector])}
    pokes.update(_seeded_rows(rows))
    info = leaf.run("hud_blit_record_bitmap", _record_bitmap(record), rows, what,
                    regs={"d0": entry_d0, "a0": record, "_pokes": pokes},
                    max_insns=PANEL_BLIT_INSN_CAP)
    source = _indexed_bitmap(RECORD_BITMAP_TABLE, selector, RECORD_BITMAP_LEN)
    expected = _source_rows(source, RECORD_BITMAP_BYTES, RECORD_BITMAP_ROWS)
    leaf.assert_rows(info, rows, expected, f"{what}: not the {source:#x} bitmap")


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
@pytest.mark.parametrize("selector", RECORD_SELECTORS,
                         ids=[f"sel_{s:02x}" for s in RECORD_SELECTORS])
def test_the_record_bitmap_lands_where_screen_back_points(selector, screen):
    _run_record_bitmap(selector, screen, RECORD_LIST, 0,
                       f"record bitmap {selector:#04x} into screen_back {screen:#x}")


@pytest.mark.parametrize("record", RECORD_ADDRESSES, ids=[f"a0_{r:05x}" for r in RECORD_ADDRESSES])
@pytest.mark.parametrize("entry_d0", RECORD_ENTRY_D0, ids=[f"d0_{d:08x}" for d in RECORD_ENTRY_D0])
def test_the_record_bitmap_reads_only_the_byte_a0_points_at(entry_d0, record):
    """d0's high byte survives `move.b` into the `mulu.w`, and a0 is the only thing that says where
    the record is — so the same selector must produce the same 1 KiB whatever either of them is."""
    _run_record_bitmap(0x06, SCREEN_BUFFERS[0], record, entry_d0,
                       f"record bitmap $06 at a0 = {record:#x} with d0 = {entry_d0:#010x}")


# --- the packed-BCD accumulators -----------------------------------------------------------------

def _packed_to_decimal(value, length):
    """The decimal number a packed-BCD field reads as, or None if a nibble is not a digit."""
    text = f"{value:0{length * 2}x}"
    return int(text) if text.isdigit() else None


def _decimal_to_packed(value, length):
    return int(f"{value % 10 ** (length * 2):0{length * 2}d}", 16)


def _bcd_expected(accumulated, operand, length, subtract):
    """The result stated in DECIMAL — the reading "packed BCD" means — rather than as src/hud.c's
    nibble arithmetic, so the two are independent statements. None where a nibble is not a digit."""
    left = _packed_to_decimal(accumulated, length)
    right = _packed_to_decimal(operand & (2 ** (length * 8) - 1), length)
    if left is None or right is None:
        return None
    return _decimal_to_packed(left - right if subtract else left + right, length)


# (accumulator, operand, why this case exists). The operand is a full longword everywhere, so that
# the WORD accumulators' `move.w d0,$bd78` always has a high half to discard.
COUNTER_ADD_CASES = (
    (0x0000, 0x00000000, "0 + 0 — the case that pins the entry extend bit at 0"),
    (0x0000, 0x12340005, "the $4e56 call site's +5, with a high word the .w staging must drop"),
    (0x0009, 0x00000001, "a carry out of the low nibble"),
    (0x0099, 0x00000001, "a carry cascading through both digits of the low byte"),
    (0x9999, 0x00000001, "the full four-digit wrap"),
    (0x1234, 0x00005678, "two multi-digit operands, no wrap"),
)
COUNTER_SUB_CASES = (
    (0x0000, 0x00000000, "0 - 0 — the entry extend bit again, on the borrow path"),
    (0x0010, 0x00000001, "a borrow out of the low nibble"),
    (0x0100, 0x00000001, "a borrow cascading through both digits of the low byte"),
    (0x0000, 0xffff0001, "the full four-digit wrap, with a high word the staging must drop"),
    (0x5000, 0x00001234, "two multi-digit operands, no wrap"),
    (0x9999, 0x00009999, "back to zero"),
)
SCORE_ADD_CASES = (
    (0x00000000, 0x00000000, "0 + 0 — the entry extend bit, eight digits wide"),
    (0x00000000, 0x00000020, "the $4e5e call site's own addend"),
    (0x00012345, 0x00000410, "the $e05e call site's addend, over a non-zero score"),
    (0x00999999, 0x00000001, "a carry cascading across three bytes"),
    (0x99999999, 0x00000001, "the full eight-digit wrap"),
    (0x12345678, 0x87654321, "every digit pair carrying at once"),
)
SCORE_SUB_CASES = (
    (0x00000000, 0x00000000, "0 - 0"),
    (0x00000000, 0x00000001, "the full eight-digit wrap"),
    (0x10000000, 0x00000001, "a borrow cascading across all four bytes"),
    (0x00012345, 0x00000045, "an ordinary subtraction"),
)

# Nibbles above 9 are not BCD, so the decimal model declines to predict them and the DIFFERENTIAL is
# the whole pin. That is worth having and worth stating: the 68000's manual leaves `abcd` on such an
# operand UNDEFINED, so these cases hold the port to the ORACLE's model of it, not to hardware. The
# game cannot reach them — both accumulators start cleared and only ever see BCD constants.
#
# They are crossed with all four routines because each is a SEPARATE INSTANCE of the same opcode, and
# the undefined behaviour is the opcode's: 12 cases is four instructions x three seeds, not one
# instruction tested twelve ways. Do not read "3 invalid seeds x every routine" as a house pattern
# for a table with more entries — there the seeds belong to the table, not to each row.
INVALID_NIBBLE_CASES = ((0x000a, 0x00000001), (0x00ff, 0x00000011), (0xaaaa, 0x00005555))

BCD_ROUTINES = (
    ("bcd_add_counter_bd6e", BCD_COUNTER, BCD_COUNTER_LEN, False, COUNTER_ADD_CASES),
    ("bcd_sub_counter_bd6e", BCD_COUNTER, BCD_COUNTER_LEN, True, COUNTER_SUB_CASES),
    ("bcd_add_score_bd70", BCD_SCORE, BCD_SCORE_LEN, False, SCORE_ADD_CASES),
    ("bcd_sub_score_bd70", BCD_SCORE, BCD_SCORE_LEN, True, SCORE_SUB_CASES),
)

# Flattened so every case is its own test rather than a loop inside one — a failure then names the
# case, and the battery shards across xdist workers.
BCD_VALID_CASES = tuple(
    (name, accumulator, length, accumulated, operand,
     _bcd_expected(accumulated, operand, length, subtract), why)
    for name, accumulator, length, subtract, cases in BCD_ROUTINES
    for accumulated, operand, why in cases)


def _run_bcd(name, accumulator, length, accumulated, operand, what, expected):
    # The neighbours on both sides are seeded, so a port that walked one byte too far shows up as a
    # diff as well as a stray write: the word below the counter, and the high score above the score.
    pokes = {accumulator: accumulated.to_bytes(length, "big"),
             BCD_ADDEND: _filler(BCD_SCORE_LEN, 3),
             BCD_HISCORE: _filler(BCD_SCORE_LEN, 5),
             BCD_COUNTER - WORD_LEN: _filler(WORD_LEN, 7)}
    info = leaf.run(name, _bcd[name](operand), [(BCD_ADDEND, length), (accumulator, length)], what,
                    regs={"d0": operand, "_pokes": pokes})
    assert leaf.read_int(info, BCD_ADDEND, length, what) == operand & (2 ** (length * 8) - 1), (
        f"{what}: the operand staged at {BCD_ADDEND:#x} is not d0's low {length} bytes")
    if expected is not None:
        ended = leaf.read_int(info, accumulator, length, what)
        assert ended == expected, (
            f"{what}: the accumulator ended at {ended:#x}, not the {expected:#x} the decimal "
            f"reading of packed BCD gives")


@pytest.mark.parametrize("name,accumulator,length,accumulated,operand,expected,why",
                         BCD_VALID_CASES,
                         ids=[f"{c[0]}_{c[3]:08x}_op_{c[4]:08x}" for c in BCD_VALID_CASES])
def test_a_bcd_accumulator_folds_its_operand_in_decimal(name, accumulator, length, accumulated,
                                                        operand, expected, why):
    assert expected is not None, f"{name}: {why} was written as a valid-BCD case and is not one"
    _run_bcd(name, accumulator, length, accumulated, operand,
             f"{name}: {why}", expected)


@pytest.mark.parametrize("accumulated,operand", INVALID_NIBBLE_CASES,
                         ids=[f"acc_{c[0]:04x}_op_{c[1]:08x}" for c in INVALID_NIBBLE_CASES])
@pytest.mark.parametrize("name,accumulator,length,_subtract,_cases", BCD_ROUTINES,
                         ids=[r[0] for r in BCD_ROUTINES])
def test_a_bcd_accumulator_reproduces_the_oracle_on_a_non_digit_nibble(name, accumulator, length,
                                                                       _subtract, _cases,
                                                                       accumulated, operand):
    seeded = accumulated & (2 ** (length * 8) - 1)
    _run_bcd(name, accumulator, length, seeded, operand,
             f"{name} over the non-BCD accumulator {seeded:0{length * 2}x}", expected=None)


def test_the_oracle_enters_every_run_with_the_condition_codes_clear():
    """The regression case for a defect this batch surfaced in the SHARED oracle.

    `abcd` folds in the entry X flag, and Musashi's `m68k_pulse_reset()` is faithful about a 68000
    reset NOT clearing the condition codes — so before `tools/recreate_kit/oracle/shim.c` forced
    ENTRY_SR, every run inherited the CCR the previous run left, and these four routines answered
    differently depending on what had run before them. It showed up as four cases that reddened
    under `-n auto` and passed alone.

    The kit pins the same property over `osh_run` itself (`test/test_entry_state.py`); this is the
    game-side half, over the reconstructions that surfaced it. The middle run is the one that arms
    it: `$99999999 + 1` wraps to zero and leaves X set.
    """
    entry = leaf.entry_of("bcd_add_score_bd70")

    def score_after(seed, operand):
        image = harness.make_image({BCD_SCORE: seed.to_bytes(BCD_SCORE_LEN, "big")})
        final, _writes, _regs = emu.run(image, entry, {"d0": operand},
                                        max_insns=leaf.LEAF_INSN_CAP)
        return int.from_bytes(final[BCD_SCORE:BCD_SCORE + BCD_SCORE_LEN], "big")

    assert score_after(0, 0) == 0, "0 + 0 was not 0 even on the first run of this test"
    assert score_after(0x99999999, 1) == 0, "the arming run did not wrap the score to zero"
    assert score_after(0, 0) == 0, (
        "0 + 0 came out 1 after a run that set the extend bit — the oracle is carrying the CCR "
        "across runs again, which makes every abcd/sbcd/addx/roxl differential order-dependent")


def test_a_bcd_add_of_zero_pins_the_entry_extend_bit():
    """0 + 0 is 0 with X = 0 on entry and 1 with X = 1, so this one case is what holds src/hud.c's
    BCD_ENTRY_EXTEND — and it holds it only for the harness's entry condition, which is the SR the
    shim forces after its reset (a reset of its own would leave the CCR alone). The game reaches
    these routines with X = 1 (see the module docstring)."""
    pokes = {BCD_COUNTER: b"\x00\x00", BCD_ADDEND: _filler(BCD_SCORE_LEN, 3)}
    info = leaf.run("bcd_add_counter_bd6e", _bcd["bcd_add_counter_bd6e"](0),
                    [(BCD_ADDEND, BCD_COUNTER_LEN), (BCD_COUNTER, BCD_COUNTER_LEN)],
                    "0 + 0 under the oracle's forced entry condition",
                    regs={"d0": 0, "_pokes": pokes})
    assert leaf.read_int(info, BCD_COUNTER, BCD_COUNTER_LEN, "0 + 0 on entry") == 0, (
        "0 + 0 came out non-zero — the oracle entered with X set, which this battery and src/hud.c "
        "both assume it does not")


# --- $b6c2: one meter cell -----------------------------------------------------------------------

# The five cell bitmaps $b61e passes in a2 — the filled cell, the three partial ones and the empty
# one — taken from its own `lea`s, so the battery plots the game's own data.
METER_CELLS = (0x146fc, 0x1471c, 0x1473c, 0x1475c, 0x1477c)
# Which entry of meter_cell_offsets the cursor starts on. 0 is where $b61e starts and the last is
# where it ends; 1 and 5 are there because half the table's offsets are ODD.
METER_CURSORS = (0, 1, 5, METER_CELL_ENTRIES - 1)


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
@pytest.mark.parametrize("cursor", METER_CURSORS, ids=[f"entry_{c}" for c in METER_CURSORS])
@pytest.mark.parametrize("cell", METER_CELLS, ids=[f"cell_{c:05x}" for c in METER_CELLS])
def test_a_meter_cell_plots_four_planes_a_row_and_advances_the_cursor(cell, cursor, screen):
    """Run over BOTH of the game's buffers, like the two blits that also read `screen_back`: this
    one takes its destination out of that longword too, so a port that hardcoded `$70000` would
    otherwise pass."""
    offset_cursor = METER_CELL_TABLE + cursor * METER_CELL_OFFSET_LEN
    origin = int.from_bytes(harness.BASE_IMAGE[offset_cursor:offset_cursor + 2], "big")
    destination = screen + origin
    # One (address, 1) per plane byte, so the bytes BETWEEN them are proved untouched: a port that
    # wrote a longword per row would be a stray write here, not only a diff.
    allowed = [(destination + row * SCREEN_LINE + plane * PLANE_STRIDE, 1)
               for row in range(METER_CELL_ROWS) for plane in range(PLANES)]
    pokes = {SCREEN_BACK: longword(screen)}
    pokes.update({addr: _filler(1, addr) for addr, _length in allowed})
    what = (f"meter cell {cell:#x} at table entry {cursor} (screen offset {origin:#x}) into "
            f"screen_back {screen:#x}")
    info = leaf.run("hud_blit_meter_cell", _meter_cell(offset_cursor, cell), allowed, what,
                    regs={"a1": offset_cursor, "a2": cell, "_pokes": pokes},
                    max_insns=PANEL_BLIT_INSN_CAP)
    source = bytes(harness.BASE_IMAGE[cell:cell + METER_CELL_ROWS * PLANES])
    for index, (addr, _length) in enumerate(allowed):
        assert leaf.read_int(info, addr, 1, what) == source[index], f"{what}: plane byte {index}"
    advanced = offset_cursor + METER_CELL_OFFSET_LEN
    assert info["regs"]["a1"] == advanced, f"{what}: the oracle left a1 at {info['regs']['a1']:#x}"
    assert info["ret"] == advanced, f"{what}: the reconstruction returned {info['ret']:#x}"


# --- $b6fe: the meter's clamped add --------------------------------------------------------------

# The largest maximum the game sets itself ($b74a picks $18..$28 off the score's thresholds).
METER_MAX_TYPICAL = 0x0028
# Where `value + amount` lands relative to that maximum. This routine's `ble` clamps at 0 where the
# effect handlers' `bgt` still stores — but at 0 both arms store the same word, so what the sweep
# pins is the comparison's POSITION (+1 must clamp, -1 must not), never its strictness.
BOUNDARY_OFFSETS = (-4, -1, 0, 1, 4)
# The amounts, as full longwords: `add.w d0,$b6fa` uses the low word only, so each carries garbage
# above it that a port must drop.
METER_AMOUNTS = (0x00000001, 0xdead0004, 0xffff0064)

# (value, maximum, does the clamp fire, why). Outside the meter's own $18..$28 range on purpose:
# these are what make the 16-bit wrap and the SIGNED compare observable.
METER_SIGNED_CASES = (
    (0x7ffe, 0x7fff, False, "the .w add wraps to a NEGATIVE value, which is below the maximum"),
    (0x8000, 0x7fff, False, "the most negative value there is, raised"),
    (0xfff0, 0x0028, False, "a negative value raised towards zero, still below the maximum"),
    (0x0010, 0xfff0, True, "a NEGATIVE maximum: the clamp fires and LOWERS the value"),
    (0x0000, 0x0000, True, "a zero maximum, which any raise reaches"),
)


def _run_meter_add(amount, value, maximum, what):
    """Runs one case and returns whether the clamp fired, so a caller can assert on the branch as
    well as on the word. The expected word is derived here from the two seeds rather than tabulated,
    which is what keeps the boundary sweep readable."""
    pokes = {METER_VALUE: word(value), METER_MAX: word(maximum)}
    info = leaf.run("hud_meter_add_clamped", _meter_add(amount), [(METER_VALUE, WORD_LEN)], what,
                    regs={"d0": amount, "_pokes": pokes})
    raised = (value + amount) & WORD_MASK
    clamps = _signed_word(maximum) <= _signed_word(raised)
    expected = maximum if clamps else raised
    ended = leaf.read_int(info, METER_VALUE, WORD_LEN, what)
    assert ended == expected, f"{what}: the meter ended at {ended:#06x}, not {expected:#06x}"
    return clamps


@pytest.mark.parametrize("offset", BOUNDARY_OFFSETS)
@pytest.mark.parametrize("amount", METER_AMOUNTS, ids=[f"amount_{a:08x}" for a in METER_AMOUNTS])
def test_the_meter_add_stops_at_the_maximum(amount, offset):
    value = (METER_MAX_TYPICAL + offset - amount) & WORD_MASK
    clamps = _run_meter_add(amount, value, METER_MAX_TYPICAL,
                            f"a raise of {amount:#010x} landing {offset:+d} from the maximum")
    assert clamps == (offset >= 0), (
        f"the raise landing {offset:+d} from the maximum took the "
        f"{'clamp' if clamps else 'store'} arm")


@pytest.mark.parametrize("value,maximum,clamps,why", METER_SIGNED_CASES,
                         ids=[f"{c[0]:04x}_max{c[1]:04x}" for c in METER_SIGNED_CASES])
def test_the_meter_add_compares_signed_and_adds_in_16_bits(value, maximum, clamps, why):
    assert _run_meter_add(4, value, maximum, f"meter add: {why}") == clamps, why


def test_the_meter_add_battery_reaches_both_branches():
    """A sweep that only ever clamped would still be green, and would pin half the routine."""
    branches = {offset >= 0 for offset in BOUNDARY_OFFSETS} | {c[2] for c in METER_SIGNED_CASES}
    assert branches == {False, True}


# --- $bb8a / $bba0: one HUD-slot cell ------------------------------------------------------------

# The sources $b8f0 itself passes: the blank tile it clears a cell with, and three of the icons it
# lays over one. The destinations are two of its own (`adda.w #$3ca0` and `#$4600` off screen_back).
HUD_CELL_BLANK = 0x1479c
HUD_CELL_ICONS = (0x1487c, 0x1495c, 0x14a3c)
HUD_CELL_SOURCES = (HUD_CELL_BLANK,) + HUD_CELL_ICONS
HUD_CELL_ORIGINS = (0x3ca0, 0x4600)

CELL_BLITS = (("hud_blit_cell_copy", False), ("hud_blit_cell_or", True))


@pytest.mark.parametrize("origin", HUD_CELL_ORIGINS, ids=[f"at_{o:04x}" for o in HUD_CELL_ORIGINS])
@pytest.mark.parametrize("source", HUD_CELL_SOURCES,
                         ids=[f"src_{s:05x}" for s in HUD_CELL_SOURCES])
@pytest.mark.parametrize("name,combines", CELL_BLITS, ids=[c[0] for c in CELL_BLITS])
def test_a_hud_cell_blit_moves_fourteen_rows_of_sixteen_bytes(name, combines, source, origin):
    screen = SCREEN_BUFFERS[0]
    destination = screen + origin
    rows = _rows(destination, HUD_CELL_BYTES, HUD_CELL_ROWS)
    seeds = _seeded_rows(rows)
    pokes = {SCREEN_BACK: longword(screen)}
    pokes.update(seeds)
    what = f"{name} of {source:#x} to screen_back + {origin:#x}"
    info = leaf.run(name, _cell_blit[name](source, destination), rows, what,
                    regs={"a0": source, "a1": destination, "_pokes": pokes},
                    max_insns=PANEL_BLIT_INSN_CAP)
    moved = _source_rows(source, HUD_CELL_BYTES, HUD_CELL_ROWS)
    expected = [bytes(a | b for a, b in zip(seeds[addr], moved[row])) if combines else moved[row]
                for row, (addr, _length) in enumerate(rows)]
    leaf.assert_rows(info, rows, expected, what)


def test_the_or_blit_is_seeded_with_something_to_combine_with():
    """The OR blit and the copy differ only where the destination is already non-zero, so a battery
    whose seeds were all zero would pass with either implementation. This is the guard on that."""
    icons = [bytes(harness.BASE_IMAGE[icon:icon + HUD_CELL_BYTES]) for icon in HUD_CELL_ICONS]
    overlaps = [any(a & b for a, b in zip(_filler(HUD_CELL_BYTES, row), icon))
                for row in range(HUD_CELL_ROWS) for icon in icons]
    assert any(overlaps), (
        "no seeded destination byte overlaps an icon byte — every OR case would agree with a copy")


# --- $bcd6: the panel's animation frame ----------------------------------------------------------

# The indices $bbca produces: 0 (its reset), 1, the $a it stamps directly, and the $c it wraps at.
PANEL_FRAME_INDICES = (0, 1, 0x0a, 0x0c)


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
@pytest.mark.parametrize("index", PANEL_FRAME_INDICES,
                         ids=[f"frame_{i}" for i in PANEL_FRAME_INDICES])
def test_the_panel_frame_blit_copies_the_frame_its_index_selects(index, screen):
    destination = screen + PANEL_FRAME_ORIGIN
    rows = _rows(destination, PANEL_FRAME_BYTES, PANEL_FRAME_ROWS)
    pokes = {SCREEN_BACK: longword(screen), PANEL_FRAME_INDEX: word(index)}
    pokes.update(_seeded_rows(rows))
    what = f"panel frame {index} into screen_back {screen:#x}"
    info = leaf.run("hud_blit_panel_frame", _panel_frame, rows, what,
                    regs={"_pokes": pokes}, max_insns=PANEL_BLIT_INSN_CAP)
    source = _indexed_bitmap(PANEL_FRAME_TABLE, index, PANEL_FRAME_LEN)
    expected = _source_rows(source, PANEL_FRAME_BYTES, PANEL_FRAME_ROWS)
    leaf.assert_rows(info, rows, expected, what)
