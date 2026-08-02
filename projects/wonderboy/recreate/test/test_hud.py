"""Differential test for the twenty status-panel routines of src/hud.c.

Every case runs the ORIGINAL routine under the Musashi oracle and the reconstruction on the same
image, requires the two to agree byte for byte over the whole image, and bounds the original's write
set to the bytes the case says it may touch. Where a routine returns a register a caller reads back
(`hud_blit_meter_cell`'s and `hud_plot_digit`'s cursors) the case compares that too.

TWELVE OF THEM ARE LEAVES and eight are not — the three field walks, the four fields above them and
the meter's own pass. (`hud_plot_digit` came in with that second tier because the walks need it, but
it calls nothing and is a leaf like the other eleven.) A non-leaf case is the same differential with
one difference on each side: the original's `bsr` runs its callee under the oracle, and the C calls
the ported C callee directly — so a case over `hud_draw_score_and_size_meter` also exercises
`hud_draw_eight_digits` and `hud_plot_digit`, and a defect anywhere in that chain reddens it.

These are not the effect handlers' shape, and three things follow from that:

  * MOST OF THEM TAKE REGISTERS. Ghidra recovered `void FUN(void)` for all twenty; the register
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
  * THE REGISTERS THE BLITS LEAVE BEHIND, except `hud_blit_meter_cell`'s and `hud_plot_digit`'s
    cursors. The kit's oracle reports d0/d1/a0/a1 only, and every call site in the game reloads them
    (`../names.txt`), so a case would be pinning a value nothing reads.
  * `hud_plot_digit`'s OUTGOING d7. It rotates the register left by a nibble and its caller keeps the
    result, but d7 is not one of the four registers the oracle reports, so no case can read it back.
    What every case DOES pin is the rotation's effect on the digit selected, and the three field
    walks above it pin the carry-over: a wrong rotation there draws the wrong digits.
  * THE EMPTY-CELL LOOP OF `hud_draw_meter` WHEN THE MAXIMUM IS BELOW THE VALUE. The count goes
    negative, the `dbf` runs it down through 65535 iterations and the cursor leaves
    meter_cell_offsets entirely. Reproduced by construction (`../src/hud.c`), reached by no case,
    and registered in ../STATUS.md.
  * WHAT ANY OF IT MEANS. `../names.txt` names these for their mechanism; a green suite would not
    make a meaning-level name true.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (MOVE_W_ABS_L_ABS_L, MOVE_W_ABS_L_D0, MOVE_W_D0_ABS_L, MOVE_W_IMM_ABS_L, RTS,
                  longword, word)
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

METER_CELL_UNITS = wb("METER_CELL_UNITS")
METER_CELL_FULL = wb("METER_CELL_FULL")
METER_CELL_PARTIAL_3 = wb("METER_CELL_PARTIAL_3")
METER_CELL_PARTIAL_2 = wb("METER_CELL_PARTIAL_2")
METER_CELL_PARTIAL_1 = wb("METER_CELL_PARTIAL_1")
METER_CELL_EMPTY = wb("METER_CELL_EMPTY")
PANEL_RESTORE_FLAG = wb("PANEL_RESTORE_FLAG_DBB3")
PANEL_RESTORE_FLAG_SET = wb("PANEL_RESTORE_FLAG_SET")

DIGIT_SIGNIFICANT_SEEN = wb("DIGIT_SIGNIFICANT_SEEN")
DIGIT_SIGNIFICANT_SET = wb("DIGIT_SIGNIFICANT_SET")
DIGIT_GLYPHS = wb("DIGIT_GLYPHS")
DIGIT_GLYPHS_ALT = wb("DIGIT_GLYPHS_ALT")
DIGIT_FONT_ALT = wb("DIGIT_FONT_ALT")
DIGIT_FONT_DEFAULT = wb("DIGIT_FONT_DEFAULT")
DIGIT_GLYPH_LEN = wb("DIGIT_GLYPH_LEN")
DIGIT_ROWS = wb("DIGIT_ROWS")
DIGIT_NIBBLE_MASK = wb("DIGIT_NIBBLE_MASK")
DIGIT_BLANK_PLANE = wb("DIGIT_BLANK_PLANE")
DIGIT_BLANK_FILL = wb("DIGIT_BLANK_FILL")
DIGIT_REWIND_RIGHT_HALF = wb("DIGIT_REWIND_RIGHT_HALF")
DIGIT_REWIND_NEXT_GROUP = wb("DIGIT_REWIND_NEXT_GROUP")

COUNTER_ORIGIN = wb("COUNTER_ORIGIN")
SCORE_ORIGIN = wb("SCORE_ORIGIN")
HISCORE_ORIGIN = wb("HISCORE_ORIGIN")
STAGE_ORIGIN = wb("STAGE_ORIGIN")
STAGE_NUMBER = wb("STAGE_NUMBER")

# (score threshold, hud_meter_max), LOWEST first — the order include/wonderboy.h states them in.
METER_SIZE_STEPS = tuple(
    (wb(f"METER_SIZE_SCORE_{step}"), wb(f"METER_SIZE_MAX_{step}"))
    for step in range(1, wb("METER_SIZE_STEPS") + 1))

# How many digits each of the three field walks draws. Not scraped: nothing in the C is parametrised
# by them (each walk is written out), so they are this battery's own statement of the geometry, and
# the entry pins are what hold the C to it.
FOUR_DIGITS, EIGHT_DIGITS, TWO_DIGITS = 4, 8, 2
NIBBLE_BITS = DIGIT_NIBBLE_MASK.bit_length()
BITS_PER_BYTE = 8
BITS_PER_WORD = 16

# The `suba.l` after each digit, per walk — the entry pins and the expected-column model both read
# these, so a battery cannot pin one sequence and check another. All three ALTERNATE; they differ in
# which end they start at (a field beginning on an even byte steps to the right half first) and in
# whether the last digit is followed by a step at all. Only the two-digit walk's is.
FOUR_DIGIT_REWINDS = (DIGIT_REWIND_RIGHT_HALF, DIGIT_REWIND_NEXT_GROUP, DIGIT_REWIND_RIGHT_HALF)
EIGHT_DIGIT_REWINDS = tuple(DIGIT_REWIND_RIGHT_HALF if step % 2 else DIGIT_REWIND_NEXT_GROUP
                            for step in range(EIGHT_DIGITS - 1))
TWO_DIGIT_REWINDS = (DIGIT_REWIND_NEXT_GROUP, DIGIT_REWIND_RIGHT_HALF)

# Where each walk forces the latch, so that the digits from there on always print. $bd4a forces
# nothing, which is why a leading zero of the stage number is drawn blank.
FOUR_DIGIT_FORCED_AT = FOUR_DIGITS - 1
EIGHT_DIGIT_FORCED_AT = EIGHT_DIGITS - 2
TWO_DIGIT_FORCED_AT = None

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


def _signed_long(value):
    """What a `cmp.l` reads a longword as. The score, the high score and the five meter thresholds
    are all compared this way, so a field whose top nibble is 8 or 9 is NEGATIVE."""
    return value - 0x100000000 if value & 0x80000000 else value


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


def _plotted_column(cursor, rows):
    """The (address, 1) of every plane byte an 8-row column writes, in the order the original stores
    them. One entry PER BYTE, so the bytes between the planes are proved untouched and a wrong
    scanline stride shows up as a stray write and not only as a diff. Shared by the meter's cells and
    by every digit: the two have the same shape and differ only in where the source comes from."""
    return [(cursor + row * SCREEN_LINE + plane * PLANE_STRIDE, 1)
            for row in range(rows) for plane in range(PLANES)]


def _assert_column(info, cursor, rows, expected, what):
    """Compare one plotted column against the bytes the case says should have landed there."""
    for index, (addr, _length) in enumerate(_plotted_column(cursor, rows)):
        actual = leaf.read_int(info, addr, 1, what)
        assert actual == expected[index], (
            f"{what}: row {index // PLANES} plane {index % PLANES} at {addr:#x} is {actual:#04x}, "
            f"not {expected[index]:#04x}")


def _seeded_column(allowed):
    """Filler for every single-byte destination in ``allowed``, so a port that wrote nothing fails
    the value assert as well as the attribution pass."""
    return {addr: _filler(1, addr) for addr, length in allowed if length == 1}


# --- the encodings each entry is pinned against --------------------------------------------------
# Named so the builders below read as instructions. Every operand is one of the constants above, so
# a wrong address, immediate, row count or stride fails at its own entry point rather than surfacing
# as a puzzling diff somewhere in a 1 MiB image. The five test_effects.py also spells (RTS and the
# four `move.w` forms) are imported from leaf.py instead, so the two batteries cannot disagree.
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

# ...and the second tier's.
BSR_W = b"\x61\x00"
BEQ_W = b"\x67\x00"
BLT_W = b"\x6d\x00"
BGT_W = b"\x6e\x00"
MOVEQ_0_D0 = b"\x70\x00"
MOVEQ_0_D2 = b"\x74\x00"
MOVEQ_0_D6 = b"\x7c\x00"
SWAP_D7 = b"\x48\x47"
SWAP_D6 = b"\x48\x46"
ADDA_W_IMM_A0 = b"\xd0\xfc"         # adda.w #imm,a0
ADDA_L_IMM_A0 = b"\xd1\xfc"         # adda.l #imm,a0   — the digit column's row step
ADDA_L_D6_A1 = b"\xd3\xc6"          # adda.l d6,a1
SUBA_L_IMM_A0 = b"\x91\xfc"         # suba.l #imm,a0   — a field walk's column step
MOVE_W_ABS_L_D6 = b"\x3c\x39"
MOVE_W_ABS_L_D2 = b"\x34\x39"
MOVE_W_ABS_L_D7 = b"\x3e\x39"
MOVE_L_ABS_L_D7 = b"\x2e\x39"
MOVE_W_IMM_D1 = b"\x32\x3c"
MOVE_W_D6_D5 = b"\x3a\x06"
MOVE_L_D7_D6 = b"\x2c\x07"
MOVE_L_A0_D0 = b"\x20\x08"
MOVE_L_A1_D1 = b"\x22\x09"
MOVE_B_A1_INC_A0 = b"\x10\x99"      # move.b (a1)+,(a0)
MOVE_B_A1_INC_D16_A0 = b"\x11\x59"  # move.b (a1)+,d16(a0)
CLR_W_ABS_L = b"\x42\x79"
CLR_B_A0 = b"\x42\x10"
CLR_B_D16_A0 = b"\x42\x28"
ST_ABS_L = b"\x50\xf9"              # st <abs>.l   — writes $ff
ST_D16_A0 = b"\x50\xe8"             # st d16(a0)
TST_W_ABS_L = b"\x4a\x79"
TST_W_D5 = b"\x4a\x45"
TST_W_D6 = b"\x4a\x46"
CMPI_W_IMM_D0 = b"\x0c\x40"
CMPI_W_IMM_D6 = b"\x0c\x46"
CMP_L_IMM_D7 = b"\xbe\xbc"
CMP_L_ABS_L_D7 = b"\xbe\xb9"
ANDI_L_IMM_D6 = b"\x02\x86"
SUBI_W_IMM_D2 = b"\x04\x42"
SUBI_W_IMM_D5 = b"\x04\x45"
SUB_L_D0_D1 = b"\x92\x80"
SUB_W_D1_D2 = b"\x94\x41"
DIVU_W_IMM_D6 = b"\x8c\xfc"
LEA_ABS_L_A2 = b"\x45\xf9"
LEA_D16_PC_A0 = b"\x41\xfa"         # lea d16(pc),a0 — invisible to an abs.l scan (../names.txt)
DBF_D1 = b"\x51\xc9"
DBF_D2 = b"\x51\xca"
DBF_D5 = b"\x51\xcd"

# The 68000's shift/rotate-BY-IMMEDIATE encoding, `1110 ccc d ss i tt rrr`, with a count of 8 spelled
# as 0. Built rather than transcribed so that the shift COUNTS come out of the geometry constants the
# reconstruction uses: a 32-byte glyph stride IS the `asl.w #5`, a 2-byte table stride the `asr.w #1`
# and a 4-unit cell the `asr.w #2`. A transcribed `\xeb\x46` would pin none of those.
SHIFT_OPCODE = 0xe000
SHIFT_LEFT = 1 << 8
SHIFT_SIZE_WORD = 1 << 6
SHIFT_SIZE_LONG = 2 << 6
SHIFT_ARITHMETIC = 0 << 3
SHIFT_ROTATE = 3 << 3
SHIFT_COUNT_WIDTH = 8               # counts are 1..8, and 8 is encoded as 0


def _shift(count, size, kind, register, left):
    assert 1 <= count <= SHIFT_COUNT_WIDTH, f"{count} is not a 68000 immediate shift count"
    return word(SHIFT_OPCODE | ((count % SHIFT_COUNT_WIDTH) << 9) | (SHIFT_LEFT if left else 0)
                | size | kind | register)


def _shift_count(stride):
    """The shift count that multiplies (or divides) by ``stride``, which must be a power of two."""
    assert stride and not stride & (stride - 1), f"{stride} is not a power of two"
    return stride.bit_length() - 1

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


# --- the second tier's entry pins ----------------------------------------------------------------
# These routines CALL, so their pins carry `bsr.w` displacements — which count from the extension
# word and so depend on where the instruction sits. `_assemble` threads the running address through,
# and `_bsr_to` builds each displacement out of the two entry points ../names.txt gives, so a
# reconstruction aimed at the wrong callee fails here rather than as a diff.

def _assemble(base, pieces):
    """Concatenate ``pieces``; a callable piece is handed the address it starts at."""
    body = b""
    for piece in pieces:
        body += piece(base + len(body)) if callable(piece) else piece
    return body


def _bsr_to(name):
    return lambda at: BSR_W + word(leaf.entry_of(name) - (at + len(BSR_W)))


# `move.w #$ffff,latch` and `clr.w latch`. Four routines spell the raise — $b850 itself when a
# significant nibble arrives, and the four- and eight-digit walks before their forced tail — so it is
# one constant rather than one per builder.
_FORCE_LATCH = MOVE_W_IMM_ABS_L + word(DIGIT_SIGNIFICANT_SET) + longword(DIGIT_SIGNIFICANT_SEEN)
_CLEAR_LATCH = CLR_W_ABS_L + longword(DIGIT_SIGNIFICANT_SEEN)


def _plot_digit_column(first_store, plane_store):
    """`move.w #7,d1` and the 8-row loop $b850 ends in: the plane-0 store, three `d16(a0)` stores,
    `adda.l #$a0,a0` and the `dbf`. Its three columns — the glyph and the two blanks — differ only
    in what they store, which is the whole point of building them from one shape."""
    body = first_store + b"".join(plane_store(plane) + word(plane * PLANE_STRIDE)
                                  for plane in range(1, PLANES))
    body += ADDA_L_IMM_A0 + longword(SCREEN_LINE)
    return MOVE_W_IMM_D1 + word(DIGIT_ROWS - 1) + body + DBF_D1 + _dbf(len(body)) + RTS


def _plot_digit_entry():
    alt_lea = LEA_ABS_L_A1 + longword(DIGIT_GLYPHS_ALT)
    bra = BRA_W + _forward_branch(len(LEA_ABS_L_A1) + 4)
    blank_default = _plot_digit_column(
        CLR_B_A0, lambda plane: ST_D16_A0 if plane == DIGIT_BLANK_PLANE else CLR_B_D16_A0)
    blank_alt = _plot_digit_column(CLR_B_A0, lambda _plane: CLR_B_D16_A0)
    return (CMPI_W_IMM_D0 + word(DIGIT_FONT_ALT)
            + BNE_W + _forward_branch(len(alt_lea) + len(bra))
            + alt_lea + bra
            + LEA_ABS_L_A1 + longword(DIGIT_GLYPHS)
            + _shift(NIBBLE_BITS, SHIFT_SIZE_LONG, SHIFT_ROTATE, 7, left=True)
            + MOVE_L_D7_D6
            + ANDI_L_IMM_D6 + longword(DIGIT_NIBBLE_MASK)
            + TST_W_ABS_L + longword(DIGIT_SIGNIFICANT_SEEN)
            + BNE_W + _forward_branch(len(TST_W_D6) + 4 + len(CMPI_W_IMM_D0) + 2 + 4
                                      + len(blank_default) + len(blank_alt) + len(_FORCE_LATCH))
            + TST_W_D6
            + BNE_W + _forward_branch(len(CMPI_W_IMM_D0) + 2 + 4
                                      + len(blank_default) + len(blank_alt))
            + CMPI_W_IMM_D0 + word(DIGIT_FONT_ALT)
            + BEQ_W + _forward_branch(len(blank_default))
            + blank_default + blank_alt + _FORCE_LATCH
            + _shift(_shift_count(DIGIT_GLYPH_LEN), SHIFT_SIZE_WORD, SHIFT_ARITHMETIC, 6, left=True)
            + ADDA_L_D6_A1
            + _plot_digit_column(MOVE_B_A1_INC_A0, lambda _plane: MOVE_B_A1_INC_D16_A0))


def _column_step(rewind):
    return SUBA_L_IMM_A0 + longword(rewind)


def _four_digit_entry():
    plot = _bsr_to("hud_plot_digit")
    return _assemble(leaf.entry_of("hud_draw_four_digits"), [
        MOVEQ_0_D0,
        plot, _column_step(FOUR_DIGIT_REWINDS[0]),
        plot, _column_step(FOUR_DIGIT_REWINDS[1]),
        plot, _column_step(FOUR_DIGIT_REWINDS[2]),
        _FORCE_LATCH,
        plot, _CLEAR_LATCH, RTS])


def _eight_digit_entry():
    plot = _bsr_to("hud_plot_digit")
    # Digits 2..6 each follow a `moveq #0,d0`, which is what confines the caller's font to the first;
    # digits 7 and 8 run on the 0 the sixth left, and the latch is forced ahead of the seventh.
    middle = []
    for digit in range(1, EIGHT_DIGIT_FORCED_AT):
        middle += [_column_step(EIGHT_DIGIT_REWINDS[digit - 1]), MOVEQ_0_D0, plot]
    return _assemble(leaf.entry_of("hud_draw_eight_digits"), [plot] + middle + [
        _column_step(EIGHT_DIGIT_REWINDS[EIGHT_DIGIT_FORCED_AT - 1]), _FORCE_LATCH,
        plot, _column_step(EIGHT_DIGIT_REWINDS[EIGHT_DIGIT_FORCED_AT]), plot,
        _CLEAR_LATCH, RTS])


def _two_digit_entry():
    plot = _bsr_to("hud_plot_digit")
    return _assemble(leaf.entry_of("hud_draw_two_digits"), [
        plot, _column_step(TWO_DIGIT_REWINDS[0]),
        plot, _column_step(TWO_DIGIT_REWINDS[1]),
        _CLEAR_LATCH, RTS])


def _counter_entry():
    return _assemble(leaf.entry_of("hud_draw_counter_bd6e"), [
        MOVEA_L_ABS_W_A0 + word(SCREEN_BACK),
        ADDA_W_IMM_A0 + word(COUNTER_ORIGIN),
        MOVE_W_ABS_L_D7 + longword(BCD_COUNTER), SWAP_D7,
        _bsr_to("hud_draw_four_digits"), RTS])


def _stage_number_entry():
    return _assemble(leaf.entry_of("hud_draw_stage_number"), [
        MOVEA_L_ABS_W_A0 + word(SCREEN_BACK),
        ADDA_W_IMM_A0 + word(STAGE_ORIGIN),
        MOVE_W_ABS_L_D7 + longword(STAGE_NUMBER), SWAP_D7,
        _shift(BITS_PER_BYTE, SHIFT_SIZE_LONG, SHIFT_ROTATE, 7, left=True),
        _bsr_to("hud_draw_two_digits"), RTS])


def _meter_size_step(score, maximum, last):
    """One `cmp.l #imm,d7 / blt / move.w #max,hud_meter_max / rts`. The LAST step has no `rts` of
    its own — it falls through to the shared one, so its branch spans two bytes less."""
    store = MOVE_W_IMM_ABS_L + word(maximum) + longword(METER_MAX)
    return (CMP_L_IMM_D7 + longword(score)
            + BLT_W + _forward_branch(len(store) if last else len(store) + len(RTS))
            + store + (b"" if last else RTS))


def _score_entry():
    steps = list(reversed(METER_SIZE_STEPS))       # the original tests the highest threshold first
    return _assemble(leaf.entry_of("hud_draw_score_and_size_meter"), [
        MOVEA_L_ABS_W_A0 + word(SCREEN_BACK),
        ADDA_W_IMM_A0 + word(SCORE_ORIGIN),
        MOVE_L_ABS_L_D7 + longword(BCD_SCORE),
        _bsr_to("hud_draw_eight_digits"),
        MOVE_L_ABS_L_D7 + longword(BCD_SCORE),
    ] + [_meter_size_step(score, maximum, index == len(steps) - 1)
         for index, (score, maximum) in enumerate(steps)] + [RTS])


def _larger_score_entry():
    reload_hiscore = MOVE_L_ABS_L_D7 + longword(BCD_HISCORE)
    return _assemble(leaf.entry_of("hud_draw_larger_score"), [
        MOVE_L_ABS_L_D7 + longword(BCD_SCORE),
        CMP_L_ABS_L_D7 + longword(BCD_HISCORE),
        BGT_W + _forward_branch(len(reload_hiscore)),
        reload_hiscore,
        MOVEA_L_ABS_W_A0 + word(SCREEN_BACK),
        LEA_D16_A0_A0 + word(HISCORE_ORIGIN),
        _bsr_to("hud_draw_eight_digits"), RTS])


# The fixed-size pieces $b61e's own branch displacements are measured in: one `lea <cell>.l,a2`
# followed by one `bsr $b6c2`, and one arm of the partial-cell chain without its `bra`.
_CELL_DRAW_LEN = len(LEA_ABS_L_A2) + 4 + len(BSR_W) + 2
_BRA_LEN = len(BRA_W) + 2
_PARTIAL_ARM_LEN = len(CMPI_W_IMM_D6) + 2 + len(BNE_W) + 2 + _CELL_DRAW_LEN


def _meter_partial_chain(blit):
    """The three arms of the one-shot `cmpi.w #n,d6 / bne` chain that draws the single partial cell,
    highest remainder first. Each `bne` skips its own draw (and its `bra`, if it has one); each `bra`
    skips every arm after it, and the last arm has none because it falls through."""
    cells = ((3, METER_CELL_PARTIAL_3), (2, METER_CELL_PARTIAL_2), (1, METER_CELL_PARTIAL_1))
    pieces = []
    for index, (remainder, cell) in enumerate(cells):
        following = len(cells) - index - 1
        bra_len = _BRA_LEN if following else 0
        pieces += [CMPI_W_IMM_D6 + word(remainder),
                   BNE_W + _forward_branch(_CELL_DRAW_LEN + bra_len),
                   LEA_ABS_L_A2 + longword(cell), blit]
        if following:
            pieces.append(BRA_W + _forward_branch(following * _PARTIAL_ARM_LEN
                                                  + (following - 1) * _BRA_LEN))
    return pieces


def _meter_entry():
    """The 164 bytes of $b61e, built from its own geometry: a `dbf` loop over the full cells, the
    three-armed partial-cell chain, the cell count recovered from the cursor, and a `dbf` loop over
    the empty ones."""
    blit = _bsr_to("hud_blit_meter_cell")

    def table_base(at):
        """`lea $b6e4(pc),a0` — the reload that turns the walk's distance into a cell count, and the
        one PC-RELATIVE reference in this block (../names.txt's blind-spot note)."""
        return LEA_D16_PC_A0 + word(METER_CELL_TABLE - (at + len(LEA_D16_PC_A0)))

    return _assemble(leaf.entry_of("hud_draw_meter"), [
        LEA_ABS_L_A1 + longword(METER_CELL_TABLE),
        ST_ABS_L + longword(PANEL_RESTORE_FLAG),
        MOVEQ_0_D6, MOVE_W_ABS_L_D6 + longword(METER_VALUE),
        DIVU_W_IMM_D6 + word(METER_CELL_UNITS),
        MOVE_W_D6_D5, TST_W_D5,
        BEQ_W + _forward_branch(len(SUBI_W_IMM_D5) + 2 + _CELL_DRAW_LEN + len(DBF_D5) + 2),
        SUBI_W_IMM_D5 + word(1),
        LEA_ABS_L_A2 + longword(METER_CELL_FULL), blit,
        DBF_D5 + _dbf(_CELL_DRAW_LEN),
        SWAP_D6,
    ] + _meter_partial_chain(blit) + [
        table_base, MOVE_L_A0_D0, MOVE_L_A1_D1, SUB_L_D0_D1,
        _shift(_shift_count(METER_CELL_OFFSET_LEN), SHIFT_SIZE_WORD, SHIFT_ARITHMETIC, 1,
               left=False),
        MOVEQ_0_D2, MOVE_W_ABS_L_D2 + longword(METER_MAX),
        _shift(_shift_count(METER_CELL_UNITS), SHIFT_SIZE_WORD, SHIFT_ARITHMETIC, 2, left=False),
        SUB_W_D1_D2,
        BNE_W + _forward_branch(len(RTS)), RTS,
        SUBI_W_IMM_D2 + word(1),
        LEA_ABS_L_A2 + longword(METER_CELL_EMPTY), blit,
        DBF_D2 + _dbf(_CELL_DRAW_LEN), RTS])


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
    "hud_plot_digit": _plot_digit_entry(),
    "hud_draw_four_digits": _four_digit_entry(),
    "hud_draw_eight_digits": _eight_digit_entry(),
    "hud_draw_two_digits": _two_digit_entry(),
    "hud_draw_counter_bd6e": _counter_entry(),
    "hud_draw_stage_number": _stage_number_entry(),
    "hud_draw_score_and_size_meter": _score_entry(),
    "hud_draw_larger_score": _larger_score_entry(),
    "hud_draw_meter": _meter_entry(),
}

# The batch this file was written for: the eleven leaves of batch 2 and the nine of batch 3. Recorded
# rather than derived from ENTRY_BYTES, so a routine dropped from a table shrinks the battery loudly
# instead of silently.
HUD_ROUTINE_COUNT = 20

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

_meter = leaf.image_glue("hud_draw_meter")
_four_digits = leaf.register_glue("hud_draw_four_digits", [ctypes.c_uint32] * 2)
_eight_digits = leaf.register_glue("hud_draw_eight_digits", [ctypes.c_uint32] * 3)
_two_digits = leaf.register_glue("hud_draw_two_digits", [ctypes.c_uint32] * 3)
_counter = leaf.register_glue("hud_draw_counter_bd6e", [ctypes.c_uint32])
_stage_number = leaf.register_glue("hud_draw_stage_number", [ctypes.c_uint32] * 2)
_score = leaf.register_glue("hud_draw_score_and_size_meter", [ctypes.c_uint32])
_larger_score = leaf.register_glue("hud_draw_larger_score", [ctypes.c_uint32])

# `hud_plot_digit` is the one reconstruction whose d7 is IN AND OUT, so `leaf.register_glue` (values
# only) does not fit it: the C takes a pointer to the digit register the way the original takes d7.
_plot_digit_fn = leaf.bind("hud_plot_digit",
                           leaf.IMAGE_ARG + [ctypes.c_uint32, ctypes.c_uint32,
                                             ctypes.POINTER(ctypes.c_uint32)],
                           ctypes.c_uint32)


def _plot_digit(font_select, cursor, digits):
    def with_registers(_lib, image):
        register = ctypes.c_uint32(digits)
        return _plot_digit_fn(image, font_select, cursor, ctypes.byref(register))
    return with_registers


def test_this_file_covers_the_whole_batch():
    leaf.assert_batch_is_complete(ENTRY_BYTES, HUD_ROUTINE_COUNT)


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
# one — so the battery plots the game's own data.
METER_CELLS = (METER_CELL_FULL, METER_CELL_PARTIAL_3, METER_CELL_PARTIAL_2,
               METER_CELL_PARTIAL_1, METER_CELL_EMPTY)
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
    allowed = _plotted_column(destination, METER_CELL_ROWS)
    pokes = {SCREEN_BACK: longword(screen)}
    pokes.update(_seeded_column(allowed))
    what = (f"meter cell {cell:#x} at table entry {cursor} (screen offset {origin:#x}) into "
            f"screen_back {screen:#x}")
    info = leaf.run("hud_blit_meter_cell", _meter_cell(offset_cursor, cell), allowed, what,
                    regs={"a1": offset_cursor, "a2": cell, "_pokes": pokes},
                    max_insns=PANEL_BLIT_INSN_CAP)
    source = bytes(harness.BASE_IMAGE[cell:cell + METER_CELL_ROWS * PLANES])
    _assert_column(info, destination, METER_CELL_ROWS, source, what)
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


# =================================================================================================
# THE SECOND TIER — $b850 and the eight routines above it.
#
# Every case here runs the original's callees under the oracle and the C's under the C, so a
# reconstruction of one routine cannot be verified in isolation: a defect in `hud_plot_digit` reddens
# every field walk, and a defect in a walk reddens the four fields above it. That is the point of
# running the tier as one battery rather than stubbing anything.
# =================================================================================================

# One plot runs 8 rows of (4 stores + `lea` + `dbf`) after a prologue of at most nine instructions,
# so 64 per digit is a cap with room and no slack for a second pass; the overhead covers a caller's
# own setup, its steps and its `moveq`s.
DIGIT_INSNS_PER_PLOT = 64
DIGIT_INSN_OVERHEAD = 32


def _digit_insn_cap(digits):
    return DIGIT_INSNS_PER_PLOT * digits + DIGIT_INSN_OVERHEAD


# The meter draws at most one cell per entry of meter_cell_offsets, each the same 8-row shape.
METER_INSN_CAP = _digit_insn_cap(METER_CELL_ENTRIES)


def test_the_two_column_steps_are_one_byte_and_seven():
    """The `suba.l` immediates are stated in include/wonderboy.h as the raw operands; this is what
    says WHY they are those numbers. A plot leaves the cursor eight scanlines lower, and a 16-pixel
    group is PLANES x PLANE_STRIDE bytes wide, so the two steps walk to the group's right half and
    on to the next group's left half."""
    advance = DIGIT_ROWS * SCREEN_LINE
    assert advance - DIGIT_REWIND_RIGHT_HALF == 1
    assert advance - DIGIT_REWIND_NEXT_GROUP == PLANES * PLANE_STRIDE - 1


def test_the_alternate_glyphs_are_ten_entries_into_the_default_ones():
    """The two tables OVERLAP — $145bc is $1447c + 10 glyphs — so "the font" is a window into one
    twenty-glyph block, and a case that fed the wrong table would still read real image data."""
    assert DIGIT_GLYPHS_ALT - DIGIT_GLYPHS == 10 * DIGIT_GLYPH_LEN


# --- the model each case states its expectation with ---------------------------------------------
# None of it reads src/hud.c: a glyph is looked up in the game's own image, a blank is spelled from
# the plane constants, and the leading-zero rule is restated as a rule.

def _digit_glyph(nibble, font_select):
    table = DIGIT_GLYPHS_ALT if font_select & WORD_MASK == DIGIT_FONT_ALT else DIGIT_GLYPHS
    source = table + nibble * DIGIT_GLYPH_LEN
    return bytes(harness.BASE_IMAGE[source:source + DIGIT_GLYPH_LEN])


def _digit_blank(font_select):
    """A suppressed zero: four cleared planes under the alternate glyphs, but a solid $ff in one
    plane under the default ones — so a port that drew "nothing" either way fails half the cases."""
    planes = bytearray(PLANES)
    if font_select & WORD_MASK != DIGIT_FONT_ALT:
        planes[DIGIT_BLANK_PLANE] = DIGIT_BLANK_FILL
    return bytes(planes) * DIGIT_ROWS


def _digit_bytes(nibble, font_select, prints):
    return _digit_glyph(nibble, font_select) if prints else _digit_blank(font_select)


def _field_nibbles(digits, count):
    """The nibbles a walk draws, in order. Each plot rotates the register left by a nibble BEFORE
    reading the bottom one, so the digit drawn is the one that was at the top."""
    return [(digits >> (32 - NIBBLE_BITS * (index + 1))) & DIGIT_NIBBLE_MASK
            for index in range(count)]


def _field_columns(cursor, rewinds):
    """The cursor each digit of a field is drawn at, from the walk's own `suba.l` sequence."""
    cursors = [cursor]
    for rewind in rewinds:
        cursor += DIGIT_ROWS * SCREEN_LINE - rewind
        cursors.append(cursor)
    return cursors


def _field_expected(digits, fonts, latch, forced_at):
    """The bytes each digit of a field should leave. This restates the leading-zero RULE — a zero
    prints only once something before it has, or once the walk forces the latch — rather than
    src/hud.c's code, which is what makes it an independent statement of the same behaviour."""
    expected = []
    for index, (nibble, font) in enumerate(zip(_field_nibbles(digits, len(fonts)), fonts)):
        if index == forced_at:
            latch = True
        prints = latch or nibble != 0
        expected.append(_digit_bytes(nibble, font, prints))
        latch = prints
    return expected


def _run_field(name, glue, cursor, digits, fonts, rewinds, forced_at, what,
               pokes=(), regs=(), entry_latch=0, extra_allowed=()):
    """Run one field walk: check every column, that it left the latch clear, and that nothing else
    moved. ``pokes``/``regs`` are the caller's own (screen_back, the field, the entry registers)."""
    columns = _field_columns(cursor, rewinds)[:len(fonts)]
    allowed = [(DIGIT_SIGNIFICANT_SEEN, WORD_LEN)] + list(extra_allowed)
    for column in columns:
        allowed += _plotted_column(column, DIGIT_ROWS)
    seeded = {**dict(pokes), DIGIT_SIGNIFICANT_SEEN: word(entry_latch)}
    seeded.update(_seeded_column(allowed))
    info = leaf.run(name, glue, allowed, what, regs=dict(regs, _pokes=seeded),
                    max_insns=_digit_insn_cap(len(fonts)))
    expected = _field_expected(digits, fonts, entry_latch != 0, forced_at)
    for index, column in enumerate(columns):
        _assert_column(info, column, DIGIT_ROWS, expected[index], f"{what}: digit {index}")
    assert leaf.read_int(info, DIGIT_SIGNIFICANT_SEEN, WORD_LEN, what) == 0, (
        f"{what}: the walk did not leave digit_significant_seen_b84e clear")
    return info


# --- $b850: one digit ----------------------------------------------------------------------------

DIGIT_NIBBLES = tuple(range(DIGIT_NIBBLE_MASK + 1))
DIGIT_FONTS = (DIGIT_FONT_DEFAULT, DIGIT_FONT_ALT)
# What sits BELOW the nibble being drawn: a port that read the bottom of d7 instead of the top, or
# rotated the wrong way, draws one of these instead.
DIGIT_REGISTER_JUNK = 0x0a5a5a5a
# An even cursor and an ODD one, both inside a game screen buffer. $b850 does not read screen_back —
# a0 arrives whole — so these pin that nothing about the destination is assumed, parity included.
DIGIT_CURSORS = (SCREEN_BUFFERS[0] + COUNTER_ORIGIN, SCREEN_BUFFERS[1] + SCORE_ORIGIN)
# `cmpi.w #1,d0` reads d0's LOW WORD, so rubbish above it must not select a font and a 1 below it
# must. The blank paths differ by font, which is what makes these observable at all.
DIGIT_FONT_WORDS = (0x00000000, 0xdead0000, 0x00010000, 0x00000001, 0xdead0001)


def _run_plot_digit(nibble, font_select, cursor, latch, what):
    digits = (nibble << (32 - NIBBLE_BITS)) | (DIGIT_REGISTER_JUNK >> NIBBLE_BITS)
    allowed = _plotted_column(cursor, DIGIT_ROWS) + [(DIGIT_SIGNIFICANT_SEEN, WORD_LEN)]
    pokes = {**_seeded_column(allowed), DIGIT_SIGNIFICANT_SEEN: word(latch)}
    info = leaf.run("hud_plot_digit", _plot_digit(font_select, cursor, digits), allowed, what,
                    regs={"d0": font_select, "a0": cursor, "d7": digits, "_pokes": pokes},
                    max_insns=_digit_insn_cap(1))
    prints = latch != 0 or nibble != 0
    _assert_column(info, cursor, DIGIT_ROWS, _digit_bytes(nibble, font_select, prints), what)
    advanced = cursor + DIGIT_ROWS * SCREEN_LINE
    assert info["regs"]["a0"] == advanced, (
        f"{what}: the oracle left a0 at {info['regs']['a0']:#x}, not {advanced:#x}")
    assert info["ret"] == advanced, f"{what}: the reconstruction returned {info['ret']:#x}"
    return info


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("nibble", DIGIT_NIBBLES, ids=[f"nibble_{n:x}" for n in DIGIT_NIBBLES])
def test_a_plotted_digit_draws_the_glyph_its_top_nibble_selects(nibble, font_select):
    """All sixteen nibbles, not the ten the game can produce: the index is a plain `asl.w #5` on a
    masked nibble, so 10..15 address real glyphs and the port must reach the same ones."""
    _run_plot_digit(nibble, font_select, DIGIT_CURSORS[0], DIGIT_SIGNIFICANT_SET,
                    f"digit {nibble:x} in font {font_select} over a raised latch")


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("cursor", DIGIT_CURSORS, ids=[f"at_{c:x}" for c in DIGIT_CURSORS])
def test_a_plotted_digit_lands_where_a0_points(cursor, font_select):
    _run_plot_digit(0x7, font_select, cursor, DIGIT_SIGNIFICANT_SET,
                    f"digit 7 in font {font_select} at {cursor:#x}")


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
def test_a_suppressed_zero_is_drawn_blank_and_leaves_the_latch_clear(font_select):
    info = _run_plot_digit(0, font_select, DIGIT_CURSORS[0], 0,
                           f"a leading zero in font {font_select}")
    assert DIGIT_SIGNIFICANT_SEEN not in info["writes"], (
        "a suppressed zero raised digit_significant_seen_b84e — every digit after it would print")


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
def test_the_first_significant_digit_raises_the_latch(font_select):
    what = f"the first significant digit in font {font_select}"
    info = _run_plot_digit(0x5, font_select, DIGIT_CURSORS[0], 0, what)
    assert leaf.read_int(info, DIGIT_SIGNIFICANT_SEEN, WORD_LEN, what) == DIGIT_SIGNIFICANT_SET, (
        "a non-zero digit did not raise digit_significant_seen_b84e")


@pytest.mark.parametrize("font_select", DIGIT_FONT_WORDS,
                         ids=[f"d0_{f:08x}" for f in DIGIT_FONT_WORDS])
def test_the_font_select_reads_only_d0s_low_word(font_select):
    """Run on a SUPPRESSED ZERO, whose two forms differ in one plane byte — the cheapest place the
    `cmpi.w` is observable, and the one a port that compared the longword fails on."""
    _run_plot_digit(0, font_select, DIGIT_CURSORS[0], 0, f"a blank with d0 = {font_select:#010x}")


# --- $b5ea / $b7ea / $bd4a: the three field walks -------------------------------------------------

# The low half of d7 is never drawn by a four- or eight-digit walk; this is what a port that read it
# would draw instead.
FIELD_LOW_JUNK = 0xbeef

# (field, why). $00a5 and $abcd are not BCD at all — the walk indexes glyphs 10..15 the same way.
FOUR_DIGIT_FIELDS = (
    (0x0000, "all zeros: three blanks and a forced final 0"),
    (0x0001, "one significant digit, in the position the walk forces anyway"),
    (0x0900, "a significant digit with zeros on BOTH sides of it"),
    (0x1234, "no suppression at all"),
    (0x9999, "the largest four-digit field"),
    (0x00a5, "nibbles above 9, which index glyphs the game never asks for"),
)
EIGHT_DIGIT_FIELDS = (
    (0x00000000, "all zeros: six blanks and two forced"),
    (0x00000001, "the smallest score"),
    (0x00090000, "a significant digit mid-field"),
    (0x12345678, "no suppression at all"),
    (0x99999999, "the largest eight-digit field"),
    (0x0000abcd, "nibbles above 9"),
)
# The two-digit walk draws d7's top TWO nibbles and forces nothing, so a leading zero is blank here.
TWO_DIGIT_FIELDS = (
    (0x00000000, "both digits blank — the case $bd4a's missing force makes possible"),
    (0x05000000, "a blank leading digit over a significant one"),
    (0x50000000, "significant first, so the second prints even as a zero"),
    (0xa5000000, "nibbles above 9"),
)

FOUR_DIGIT_CURSORS = tuple(screen + COUNTER_ORIGIN for screen in SCREEN_BUFFERS)


@pytest.mark.parametrize("cursor", FOUR_DIGIT_CURSORS, ids=[f"at_{c:x}" for c in FOUR_DIGIT_CURSORS])
@pytest.mark.parametrize("field,why", FOUR_DIGIT_FIELDS,
                         ids=[f"{f[0]:04x}" for f in FOUR_DIGIT_FIELDS])
def test_the_four_digit_walk_draws_the_top_word_and_forces_its_last_digit(field, why, cursor):
    digits = (field << 16) | FIELD_LOW_JUNK
    _run_field("hud_draw_four_digits", _four_digits(cursor, digits), cursor, digits,
               (DIGIT_FONT_DEFAULT,) * FOUR_DIGITS, FOUR_DIGIT_REWINDS, FOUR_DIGIT_FORCED_AT,
               f"four digits of {field:04x} at {cursor:#x} ({why})",
               regs={"a0": cursor, "d7": digits})


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
def test_the_four_digit_walk_ignores_the_callers_font(font_select):
    """`moveq #0,d0` is the first instruction, so both entry values must draw the same bytes — which
    only shows on a field with a suppressed zero, since that is where the fonts differ."""
    cursor = FOUR_DIGIT_CURSORS[0]
    digits = FIELD_LOW_JUNK
    _run_field("hud_draw_four_digits", _four_digits(cursor, digits), cursor, digits,
               (DIGIT_FONT_DEFAULT,) * FOUR_DIGITS, FOUR_DIGIT_REWINDS, FOUR_DIGIT_FORCED_AT,
               f"four zeros entered with d0 = {font_select}",
               regs={"d0": font_select, "a0": cursor, "d7": digits})


def test_the_four_digit_walk_starts_from_the_latch_it_is_given():
    """Every caller in the game enters with the latch clear (each walk clears it on the way out), so
    this is the one case that shows the routine READS it rather than assuming zero: with it raised,
    the leading zeros print instead of blanking."""
    cursor = FOUR_DIGIT_CURSORS[0]
    digits = FIELD_LOW_JUNK
    _run_field("hud_draw_four_digits", _four_digits(cursor, digits), cursor, digits,
               (DIGIT_FONT_DEFAULT,) * FOUR_DIGITS, FOUR_DIGIT_REWINDS, FOUR_DIGIT_FORCED_AT,
               "four zeros entered with the latch already raised",
               regs={"a0": cursor, "d7": digits}, entry_latch=DIGIT_SIGNIFICANT_SET)


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("field,why", EIGHT_DIGIT_FIELDS,
                         ids=[f"{f[0]:08x}" for f in EIGHT_DIGIT_FIELDS])
def test_the_eight_digit_walk_gives_only_its_first_digit_the_callers_font(field, why, font_select):
    cursor = SCREEN_BUFFERS[0] + SCORE_ORIGIN
    fonts = (font_select,) + (DIGIT_FONT_DEFAULT,) * (EIGHT_DIGITS - 1)
    _run_field("hud_draw_eight_digits", _eight_digits(font_select, cursor, field), cursor, field,
               fonts, EIGHT_DIGIT_REWINDS, EIGHT_DIGIT_FORCED_AT,
               f"eight digits of {field:08x} in font {font_select} ({why})",
               regs={"d0": font_select, "a0": cursor, "d7": field})


def test_the_eight_digit_walk_starts_from_the_latch_it_is_given():
    """The eight-digit form of the four-digit case above: entered with the latch raised, the six
    digits ahead of the forced pair print their zeros instead of blanking. This is what says the walk
    READS the latch rather than clearing it on entry, which nothing else here would catch — every
    caller in the game enters with it clear."""
    cursor = SCREEN_BUFFERS[0] + SCORE_ORIGIN
    field = 0x00000000
    _run_field("hud_draw_eight_digits", _eight_digits(DIGIT_FONT_DEFAULT, cursor, field), cursor,
               field, (DIGIT_FONT_DEFAULT,) * EIGHT_DIGITS, EIGHT_DIGIT_REWINDS,
               EIGHT_DIGIT_FORCED_AT, "eight zeros entered with the latch already raised",
               regs={"d0": DIGIT_FONT_DEFAULT, "a0": cursor, "d7": field},
               entry_latch=DIGIT_SIGNIFICANT_SET)


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
def test_the_eight_digit_walk_lands_where_a0_points(screen):
    cursor = screen + SCORE_ORIGIN
    field = 0x01020304
    _run_field("hud_draw_eight_digits", _eight_digits(DIGIT_FONT_DEFAULT, cursor, field), cursor,
               field, (DIGIT_FONT_DEFAULT,) * EIGHT_DIGITS, EIGHT_DIGIT_REWINDS,
               EIGHT_DIGIT_FORCED_AT, f"eight digits at {cursor:#x}",
               regs={"a0": cursor, "d7": field})


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("field,why", TWO_DIGIT_FIELDS,
                         ids=[f"{f[0]:08x}" for f in TWO_DIGIT_FIELDS])
def test_the_two_digit_walk_gives_both_digits_the_callers_font_and_forces_nothing(field, why,
                                                                                  font_select):
    cursor = SCREEN_BUFFERS[0] + STAGE_ORIGIN
    _run_field("hud_draw_two_digits", _two_digits(font_select, cursor, field), cursor, field,
               (font_select,) * TWO_DIGITS, TWO_DIGIT_REWINDS, TWO_DIGIT_FORCED_AT,
               f"two digits of {field:08x} in font {font_select} ({why})",
               regs={"d0": font_select, "a0": cursor, "d7": field})


def test_the_two_digit_walk_starts_from_the_latch_it_is_given():
    """This walk forces the latch nowhere, so a raised one is the ONLY way both of its digits print
    a zero — which makes it the case that says it reads the latch instead of clearing it on entry."""
    cursor = SCREEN_BUFFERS[0] + STAGE_ORIGIN
    field = 0x00000000
    _run_field("hud_draw_two_digits", _two_digits(DIGIT_FONT_DEFAULT, cursor, field), cursor, field,
               (DIGIT_FONT_DEFAULT,) * TWO_DIGITS, TWO_DIGIT_REWINDS, TWO_DIGIT_FORCED_AT,
               "two zeros entered with the latch already raised",
               regs={"d0": DIGIT_FONT_DEFAULT, "a0": cursor, "d7": field},
               entry_latch=DIGIT_SIGNIFICANT_SET)


# --- $b54c / $bd32: the two fields loaded as a WORD -----------------------------------------------

# What the caller left in d7. Its high word ends up BELOW the digits drawn and must not reach them.
FIELD_ENTRY_D7 = (0x00000000, 0xdeadbeef, 0xffffffff)

COUNTER_FIELDS = (0x0000, 0x0001, 0x0900, 0x1234, 0x9999)
STAGE_FIELDS = (0x0000, 0x0001, 0x0010, 0x1234, 0xff99)


def _staged_word(field, entry_d7):
    """`move.w field,d7 / swap d7` — the field becomes d7's HIGH word and the caller's own high word
    drops into the low half. Both routines below stage their field exactly this way."""
    return (field << BITS_PER_WORD) | (entry_d7 >> BITS_PER_WORD)


def _run_counter(counter, screen, entry_d7, what):
    cursor = screen + COUNTER_ORIGIN
    digits = _staged_word(counter, entry_d7)
    _run_field("hud_draw_counter_bd6e", _counter(entry_d7), cursor, digits,
               (DIGIT_FONT_DEFAULT,) * FOUR_DIGITS, FOUR_DIGIT_REWINDS, FOUR_DIGIT_FORCED_AT, what,
               pokes={SCREEN_BACK: longword(screen), BCD_COUNTER: word(counter)},
               regs={"d7": entry_d7})


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
@pytest.mark.parametrize("counter", COUNTER_FIELDS, ids=[f"{c:04x}" for c in COUNTER_FIELDS])
def test_the_counter_draw_takes_its_origin_from_screen_back(counter, screen):
    _run_counter(counter, screen, 0, f"counter {counter:04x} into screen_back {screen:#x}")


@pytest.mark.parametrize("entry_d7", FIELD_ENTRY_D7, ids=[f"d7_{d:08x}" for d in FIELD_ENTRY_D7])
def test_the_counter_draw_buries_the_callers_d7_below_the_digits(entry_d7):
    """`move.w`/`swap` leave the caller's high word in d7's LOW half, where four rotations cannot
    reach it — so all three entry values must draw the same four digits."""
    _run_counter(0x0100, SCREEN_BUFFERS[0], entry_d7,
                 f"counter 0100 entered with d7 {entry_d7:#010x}")


def _run_stage_number(stage, font_select, screen, entry_d7, what):
    cursor = screen + STAGE_ORIGIN
    staged = _staged_word(stage, entry_d7)
    digits = ((staged << BITS_PER_BYTE) | (staged >> (32 - BITS_PER_BYTE))) & 0xffffffff
    _run_field("hud_draw_stage_number", _stage_number(font_select, entry_d7), cursor, digits,
               (font_select,) * TWO_DIGITS, TWO_DIGIT_REWINDS, TWO_DIGIT_FORCED_AT, what,
               pokes={SCREEN_BACK: longword(screen), STAGE_NUMBER: word(stage)},
               regs={"d0": font_select, "d7": entry_d7})


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("stage", STAGE_FIELDS, ids=[f"{s:04x}" for s in STAGE_FIELDS])
def test_the_stage_draw_shows_the_low_byte_of_stage_number(stage, font_select):
    """The `rol.l #8` after the swap is what selects the low byte: $ff99 must draw 9 and 9, not
    f and f."""
    _run_stage_number(stage, font_select, SCREEN_BUFFERS[0], 0,
                      f"stage {stage:04x} in font {font_select}")


@pytest.mark.parametrize("entry_d7", FIELD_ENTRY_D7, ids=[f"d7_{d:08x}" for d in FIELD_ENTRY_D7])
def test_the_stage_draw_buries_the_callers_d7_below_the_digits(entry_d7):
    _run_stage_number(0x0012, DIGIT_FONT_DEFAULT, SCREEN_BUFFERS[1], entry_d7,
                      f"stage 0012 entered with d7 {entry_d7:#010x}")


# --- $b74a: the score, and the meter it sizes -----------------------------------------------------

def _meter_max_for(score, seeded):
    """What $b74a leaves in hud_meter_max: the highest step the score REACHES, compared as a signed
    longword, and the seeded word untouched when it reaches none."""
    for threshold, maximum in reversed(METER_SIZE_STEPS):
        if _signed_long(score) >= threshold:
            return maximum
    return seeded


# Both sides of every threshold, plus the three the table's ends do not cover.
SCORE_THRESHOLD_CASES = tuple(
    score for threshold, _maximum in METER_SIZE_STEPS for score in (threshold - 1, threshold)
) + (0x00000000, 0x7fffffff, 0x99999999)

# A maximum unlike any step's, so "left untouched" is distinguishable from "set to a step's value".
METER_MAX_SEED = 0x0014


@pytest.mark.parametrize("score", SCORE_THRESHOLD_CASES,
                         ids=[f"{s:08x}" for s in SCORE_THRESHOLD_CASES])
def test_the_score_draw_sizes_the_meter_from_its_thresholds(score):
    screen = SCREEN_BUFFERS[0]
    cursor = screen + SCORE_ORIGIN
    what = f"score {score:08x} sizing hud_meter_max"
    info = _run_field(
        "hud_draw_score_and_size_meter", _score(DIGIT_FONT_DEFAULT), cursor, score,
        (DIGIT_FONT_DEFAULT,) * EIGHT_DIGITS, EIGHT_DIGIT_REWINDS, EIGHT_DIGIT_FORCED_AT, what,
        pokes={SCREEN_BACK: longword(screen), BCD_SCORE: longword(score),
               METER_MAX: word(METER_MAX_SEED)},
        regs={"d0": DIGIT_FONT_DEFAULT}, extra_allowed=[(METER_MAX, WORD_LEN)])
    expected = _meter_max_for(score, METER_MAX_SEED)
    if expected == METER_MAX_SEED:
        assert METER_MAX not in info["writes"], (
            f"{what}: a score below every threshold still wrote hud_meter_max")
    else:
        assert leaf.read_int(info, METER_MAX, WORD_LEN, what) == expected, (
            f"{what}: the meter's maximum is not the step this score reaches")


def test_the_score_thresholds_reach_every_step_and_the_no_match_arm():
    """A sweep that never matched a step, or always matched one, would pin half the chain."""
    reached = {_meter_max_for(score, METER_MAX_SEED) for score in SCORE_THRESHOLD_CASES}
    assert reached == {maximum for _threshold, maximum in METER_SIZE_STEPS} | {METER_MAX_SEED}


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
def test_the_score_draw_takes_its_origin_from_screen_back(screen, font_select):
    cursor = screen + SCORE_ORIGIN
    score = 0x00012345
    _run_field("hud_draw_score_and_size_meter", _score(font_select), cursor, score,
               (font_select,) + (DIGIT_FONT_DEFAULT,) * (EIGHT_DIGITS - 1), EIGHT_DIGIT_REWINDS,
               EIGHT_DIGIT_FORCED_AT, f"score {score:08x} into screen_back {screen:#x}",
               pokes={SCREEN_BACK: longword(screen), BCD_SCORE: longword(score),
                      METER_MAX: word(METER_MAX_SEED)},
               regs={"d0": font_select}, extra_allowed=[(METER_MAX, WORD_LEN)])


# --- $b7c6: whichever of the two fields is larger -------------------------------------------------

# (score, high score, why). The compare is `cmp.l hiscore,d7 / bgt`: SIGNED and STRICT.
LARGER_SCORE_CASES = (
    (0x00001234, 0x00000000, "the score is ahead"),
    (0x00000000, 0x00001234, "the high score is ahead"),
    (0x00012345, 0x00012345, "equal — the `bgt` takes the HIGH SCORE arm, whose bytes are the same"),
    (0x99999999, 0x00000001, "a score with bit 31 set reads NEGATIVE and loses to a tiny one"),
    (0x00000001, 0x99999999, "...and a high score with bit 31 set loses the same way"),
    (0x80000000, 0x7fffffff, "the signed boundary itself"),
)


def _run_larger_score(score, hiscore, font_select, screen, what):
    cursor = screen + HISCORE_ORIGIN
    drawn = score if _signed_long(score) > _signed_long(hiscore) else hiscore
    _run_field("hud_draw_larger_score", _larger_score(font_select), cursor, drawn,
               (font_select,) + (DIGIT_FONT_DEFAULT,) * (EIGHT_DIGITS - 1), EIGHT_DIGIT_REWINDS,
               EIGHT_DIGIT_FORCED_AT, what,
               pokes={SCREEN_BACK: longword(screen), BCD_SCORE: longword(score),
                      BCD_HISCORE: longword(hiscore)},
               regs={"d0": font_select})


@pytest.mark.parametrize("score,hiscore,why", LARGER_SCORE_CASES,
                         ids=[f"{c[0]:08x}_vs_{c[1]:08x}" for c in LARGER_SCORE_CASES])
def test_the_larger_score_draw_compares_the_two_fields_signed(score, hiscore, why):
    _run_larger_score(score, hiscore, DIGIT_FONT_DEFAULT, SCREEN_BUFFERS[0],
                      f"max({score:08x}, {hiscore:08x}) — {why}")


@pytest.mark.parametrize("font_select", DIGIT_FONTS, ids=[f"font_{f}" for f in DIGIT_FONTS])
@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
def test_the_larger_score_draw_takes_its_origin_from_screen_back(screen, font_select):
    _run_larger_score(0x00098765, 0x00001111, font_select, screen,
                      f"the larger score into screen_back {screen:#x}")


# --- $b61e: the meter's own pass ------------------------------------------------------------------

# (value, maximum, why). Every pair keeps the empty count at or above zero and the cell count within
# meter_cell_offsets — the negative case is the one this battery deliberately cannot reach.
METER_CASES = (
    (0x00, 0x00, "nothing at all: no full cells, no partial one, no empty ones"),
    (0x00, 0x14, "an empty meter at the value $fe4a resets both words to"),
    (0x01, 0x14, "remainder 1 alone"),
    (0x02, 0x14, "remainder 2"),
    (0x03, 0x14, "remainder 3"),
    (0x04, 0x14, "exactly one full cell and no remainder"),
    (0x14, 0x14, "a full meter at the reset maximum"),
    (0x0d, 0x18, "the lowest maximum $b74a sets, part filled"),
    (0x27, 0x28, "the highest maximum $b74a sets, one unit short"),
    (0x28, 0x28, "...and full, which is every entry of meter_cell_offsets"),
)


def _meter_plan(value, maximum):
    """The cell bitmaps $b61e draws, in order: `value/4` full ones, a partial one for a non-zero
    remainder, then `maximum/4` minus the cells already drawn of the empty one."""
    partials = {3: METER_CELL_PARTIAL_3, 2: METER_CELL_PARTIAL_2, 1: METER_CELL_PARTIAL_1}
    cells = [METER_CELL_FULL] * (value // METER_CELL_UNITS)
    if value % METER_CELL_UNITS:
        cells.append(partials[value % METER_CELL_UNITS])
    empty = (maximum // METER_CELL_UNITS) - len(cells)
    assert empty >= 0, f"value {value:#x} / maximum {maximum:#x} would enter the runaway dbf"
    cells += [METER_CELL_EMPTY] * empty
    assert len(cells) <= METER_CELL_ENTRIES, f"{len(cells)} cells would walk off the offset table"
    return cells


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
@pytest.mark.parametrize("value,maximum,why", METER_CASES,
                         ids=[f"{c[0]:02x}_of_{c[1]:02x}" for c in METER_CASES])
def test_the_meter_draws_full_then_partial_then_empty_cells(value, maximum, why, screen):
    cells = _meter_plan(value, maximum)
    offsets = [METER_CELL_TABLE + index * METER_CELL_OFFSET_LEN for index in range(len(cells))]
    destinations = [
        screen + int.from_bytes(harness.BASE_IMAGE[at:at + METER_CELL_OFFSET_LEN], "big")
        for at in offsets]
    allowed = [(PANEL_RESTORE_FLAG, 1)]
    for destination in destinations:
        allowed += _plotted_column(destination, METER_CELL_ROWS)
    pokes = {**_seeded_column(allowed), SCREEN_BACK: longword(screen),
             METER_VALUE: word(value), METER_MAX: word(maximum)}
    what = f"a meter of {value:#04x}/{maximum:#04x} into screen_back {screen:#x} ({why})"
    info = leaf.run("hud_draw_meter", _meter, allowed, what,
                    regs={"_pokes": pokes}, max_insns=METER_INSN_CAP)
    assert leaf.read_int(info, PANEL_RESTORE_FLAG, 1, what) == PANEL_RESTORE_FLAG_SET, (
        f"{what}: panel_restore_flag_dbb3 was not raised")
    for index, (cell, destination) in enumerate(zip(cells, destinations)):
        source = bytes(harness.BASE_IMAGE[cell:cell + METER_CELL_ROWS * PLANES])
        _assert_column(info, destination, METER_CELL_ROWS, source, f"{what}: cell {index}")


def test_the_meter_battery_draws_every_one_of_the_five_cells():
    """A sweep that never produced a remainder, or never an empty cell, would leave whole arms of
    the chain unpinned while staying green."""
    drawn = {cell for value, maximum, _why in METER_CASES for cell in _meter_plan(value, maximum)}
    assert drawn == set(METER_CELLS)
