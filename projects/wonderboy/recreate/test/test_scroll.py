"""Differential test for the whole background scroll engine — the sixteen routines of src/scroll.c.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte over the whole image, and bounds the original's write set.
For everything that draws it goes further: the write set is compared for EQUALITY against the exact
addresses the geometry gives, and every written byte against a Python model built from the
disassembly — so a case says which bytes moved and where to, not only that both sides agree.

THREE THINGS MAKE THIS BATTERY DIFFERENT FROM test_hud.py's.

  * THE STEPS RETURN THROUGH THE STACK. All four decide whether their caller's redraw happens by
    adding to their own return address — `addq.l #4,(a7)` horizontally, `#8` vertically, where
    there are two calls to consume — so the oracle's `rts` lands PAST the sentinel and the run has
    to be given that address as a second stop PC (leaf.run's `stop_pc`). The decision is then read
    back off the oracle's OWN STACK — the skipped arm leaves sentinel+n at STACK_TOP and the other
    arm never writes there — and compared against the flag the C returns. Neither side is trusted
    to report it.
  * NOTHING IS SEEDED FROM A CONSTANT THE CODE ALSO USES. The map, its row stride and the 256-word
    tile index all live PAST the end of the program ($218d0), so a fresh image has them zero and
    every case builds them. The tile BITMAPS are shipped in the .PRG and are used as they are,
    which is what keeps the fills' source non-zero.
  * THE DESTINATION IS SEEDED WITH A MARGIN, address-keyed. A column fill is a read-modify-write
    over a buffer, so a fill that ran one row too far would `and` or `or` bytes that a zeroed image
    leaves indistinguishable — the hole batch 4's mutation sweep found and docs/methodology.md
    writes up. A horizontal case fills the whole $5800 buffer PLUS a scanline either side with a
    byte derived from the ADDRESS; a vertical one fills all EIGHT buffers, because the pre-shift
    walks a row through every copy. The write-set equality above catches the same fault from the
    other direction. Both seedings key on the address with the SAME salt, so a case that uses both
    gets one consistent image where they overlap.

KNOWINGLY NOT PINNED
  * THE REGISTERS THE COLUMN FILLS LEAVE BEHIND. Both walk out with every address register far past
    where it started, and both call sites `rts` immediately after, so nothing reads them. The kit's
    oracle REPORTS them all now (batch 11 widened it to d0-d7/a0-a6), so what is missing is no
    longer an observer but a reconstruction that models them — openable, not blocked. The two ROW
    fills are the exception: their d0 is an output and every case compares it.
  * THE 65536-ITERATION `dbf`. Every fill takes its two lengths from a split table whose first
    words count down to 0 — no seeding through bg_scroll_y_coarse or bg_scroll_x can produce a
    negative first count, because the tables are the game's own data and a case that rewrote one
    would be pinning an invented record. Reproduced by construction in src/scroll.c and left
    unreached. bg_scroll_run_queue's two drains loop on the same shape but NOT for the same reason:
    their count is a halved distance, and the wrapped-at-the-lowest-position case below proves $d28
    can return one that halves to a negative $c018 — 49,176 passes. What leaves that unreached is
    the range of the game's own follow positions, which this batch did not establish.
  * WHAT THE SCROLL IS FOR. ../names.txt names these for their mechanism; that the two column fills
    are the left and right edges of a visible window is read off their map offsets being fifteen
    cells apart, not proved here.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (RTS, branch, branch_over, bsr_w, case_salt, clr_b_abs_l, clr_w_abs_l, dbf,
                  keyed_block, keyed_byte, lea_abs_l, lea_d16, lea_indexed, longword, merge_bands,
                  move_l_imm_abs_l, move_w_abs_l_dn, move_w_dn_dn, move_w_imm_dn, move_w_ind_dn,
                  move_w_postinc_dn, movea_l_abs_l, movea_l_abs_w, moveq_0_dn, mulu_w_imm_dn,
                  opcode, program_writes, s16, st_abs_l, sub_w_dn_dn, subi_w_dn, subq_w_abs_l,
                  tst_b_abs_l, tst_w_abs_l, tst_w_abs_w, u16, word)
from layout import wb

import emu      # noqa: E402  (harness puts the kit's oracle on sys.path)
import loader   # noqa: E402

# --- the globals and the geometry, from the header both languages read ---------------------------
PHASE = wb("BG_SCROLL_PHASE")
SCROLL_X = wb("BG_SCROLL_X")
Y_COARSE = wb("BG_SCROLL_Y_COARSE")
POS_X = wb("BG_SCROLL_POS_X")
LIMIT_X = wb("BG_SCROLL_LIMIT_X")
PENDING = wb("BG_SCROLL_PENDING")
MAP_CURSOR = wb("BG_MAP_CURSOR")
ROW_BYTE_OFFSET = wb("BG_ROW_BYTE_OFFSET")
FILL_COUNTS = wb("BG_FILL_COUNTS")
FILL_COUNT_SECOND = wb("BG_FILL_COUNT_SECOND")
COL_SPLIT_TABLE = wb("BG_COL_SPLIT_TABLE")
COL_SPLIT_ENTRIES = wb("BG_COL_SPLIT_ENTRIES")
EDGE_MASK_TABLE = wb("BG_EDGE_MASK_TABLE")
REQUEST_UP = wb("BG_REQUEST_UP")
REQUEST_DOWN = wb("BG_REQUEST_DOWN")
REQUEST_LEFT = wb("BG_REQUEST_LEFT")
REQUEST_RIGHT = wb("BG_REQUEST_RIGHT")
STATE_WORD_LEN = wb("BG_STATE_WORD_LEN")

# --- the vertical half's own state, and the queue above both halves ------------------------------
POS_Y = wb("BG_SCROLL_POS_Y")
LIMIT_Y = wb("BG_SCROLL_LIMIT_Y")
SCROLL_Y = wb("BG_SCROLL_Y")
SCROLL_Y_BOTTOM = wb("BG_SCROLL_Y_BOTTOM")
SCROLL_Y_LAST = wb("BG_SCROLL_Y_LAST")
Y_COARSE_SHIFT = wb("BG_Y_COARSE_SHIFT")
BUFFER_ROWS = wb("BG_BUFFER_ROWS")
BUFFER_ROW_TOP = wb("BG_BUFFER_ROW_TOP")
BUFFER_ROW_BOTTOM = wb("BG_BUFFER_ROW_BOTTOM")
BUFFER_ROW_PAIR = wb("BG_BUFFER_ROW_PAIR")
BUFFERS = wb("BG_BUFFERS")
TILE_ROW = wb("BG_TILE_ROW")
TILE_ROW_STEP = wb("BG_TILE_ROW_STEP")
TILE_ROW_MASK = wb("BG_TILE_ROW_MASK")
ROW_SPLIT_TABLE = wb("BG_ROW_SPLIT_TABLE")
ROW_SPLIT_ENTRIES = wb("BG_ROW_SPLIT_ENTRIES")
ROW_CELLS = wb("BG_ROW_CELLS")
ROW_FILL_SCANLINES = wb("BG_ROW_FILL_SCANLINES")
BOTTOM_ROW_STRIDES = wb("BG_BOTTOM_ROW_STRIDES")
ROW_DRAWN_TOP = wb("BG_ROW_DRAWN_TOP")
ROW_DRAWN_BOTTOM = wb("BG_ROW_DRAWN_BOTTOM")
PRESHIFT_CARRY = wb("BG_PRESHIFT_CARRY")
PRESHIFT_COPIES = wb("BG_PRESHIFT_COPIES")
PRESHIFT_ROWS = wb("BG_PRESHIFT_ROWS")
PRESHIFT_BITS = wb("BG_PRESHIFT_BITS")
MAP_DATA_ROW = wb("MAP_DATA_ROW")

QUEUE_H_COUNT = wb("BG_QUEUE_H_COUNT")
QUEUE_V_COUNT = wb("BG_QUEUE_V_COUNT")
RAISED_V = wb("BG_RAISED_V")
RAISED_V_UP = wb("BG_RAISED_V_UP")
RAISED_V_DOWN = wb("BG_RAISED_V_DOWN")
RAISED_H = wb("BG_RAISED_H")
RAISED_H_LEFT = wb("BG_RAISED_H_LEFT")
RAISED_H_RIGHT = wb("BG_RAISED_H_RIGHT")
RAISED_SET = wb("BG_RAISED_SET")
FOLLOW_FROZEN = wb("SCROLL_FOLLOW_FROZEN")
FOLLOW_X = wb("SCROLL_FOLLOW_X")
FOLLOW_Y = wb("SCROLL_FOLLOW_Y")
CENTRE_X = wb("SCROLL_CENTRE_X")
CENTRE_Y = wb("SCROLL_CENTRE_Y")

TILE_BITMAPS = wb("TILE_BITMAPS")
TILE_BITMAP_LEN = wb("TILE_BITMAP_LEN")
TILE_INDEX_TABLE = wb("TILE_INDEX_TABLE")
TILE_INDEX_ENTRIES = wb("TILE_INDEX_ENTRIES")
TILE_SHIPPED_FIRST = wb("TILE_SHIPPED_FIRST")
TILE_SHIPPED_COUNT = wb("TILE_SHIPPED_COUNT")
MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")
MAP_DATA = wb("MAP_DATA")

BUFFER_BASE = wb("BG_BUFFER_BASE")
BUFFER_LEN = wb("BG_BUFFER_LEN")
BUFFER_PHASE_STRIDE = wb("BG_BUFFER_PHASE_STRIDE")
BUFFER_LINE = wb("BG_BUFFER_LINE")
CELL_BYTES = wb("BG_CELL_BYTES")
TILE_ROWS = wb("BG_TILE_ROWS")
TILE_BLOCK_LEN = wb("BG_TILE_BLOCK_LEN")
BUFFER_TILE_ROWS = wb("BG_BUFFER_TILE_ROWS")
SCROLL_STEP = wb("BG_SCROLL_STEP")
PHASE_MASK = wb("BG_PHASE_MASK")
PHASE_LAST = wb("BG_PHASE_LAST")
PENDING_SET = wb("BG_PENDING_SET")
ROW_OFFSET_MASK = wb("BG_ROW_OFFSET_MASK")
FILL_LEFT_MAP_OFF = wb("BG_FILL_LEFT_MAP_OFF")
FILL_RIGHT_MAP_OFF = wb("BG_FILL_RIGHT_MAP_OFF")
FILL_RIGHT_X_BIAS = wb("BG_FILL_RIGHT_X_BIAS")

PLANES = wb("PLANES")
PLANE_STRIDE = wb("PLANE_STRIDE")

# --- the consumer tier: bg_scroll_blit and the sixteen copy variants it jumps into ---------------
SCREEN_BUFFERS = leaf.SCREEN_BUFFERS
SCREEN_BACK = wb("SCREEN_BACK")
SCREEN_LINE = wb("SCREEN_LINE")
BLIT_TABLE = wb("BG_BLIT_TABLE")
BLIT_VARIANTS = wb("BG_BLIT_VARIANTS")
BLIT_SCREEN_ORIGIN = wb("BG_BLIT_SCREEN_ORIGIN")
BLIT_SCANLINES = wb("BG_BLIT_SCANLINES")
BLIT_LONGWORDS = wb("BG_BLIT_LONGWORDS")
BLIT_ROW_BYTES = wb("BG_BLIT_ROW_BYTES")
BUFFER_SCANLINES = wb("BG_BUFFER_SCANLINES")
BLIT_WRAP_ROW = wb("BG_BLIT_WRAP_ROW")
BLIT_NO_SECOND_HALF = wb("BG_BLIT_NO_SECOND_HALF")
BLIT_ROW_SHIFT = wb("BG_BLIT_ROW_SHIFT")
ROW_LONGWORDS = wb("BG_ROW_LONGWORDS")
CELL_LONGWORDS = wb("BG_CELL_LONGWORDS")

# One past the last copy variant, and so the end of the whole consumer tier ($82f8..$8dfe). It is
# also where the routine STATUS.md queues for a later batch begins, which is what makes it a
# boundary the family is measured against rather than a number derived from the family itself.
BLIT_FAMILY_END = 0x8dfe

WORD_BITS = 16
LONG_BITS = 32
LONGWORD_LEN = 4

# The rotation the right edge substitutes for a phase of zero: a whole 16-pixel cell.
FULL_CELL_ROTATION = 16

# `addq.l #n,(a7)` — what a step adds to its own return address to consume its caller's `bsr`s. One
# RETURN ADDRESS per call skipped: the horizontal steps consume the fill under them, the vertical
# ones the fill AND the pre-shift after it, which is the whole difference between `#4` and `#8`.
SKIP_ONE_CALL = LONGWORD_LEN
SKIP_TWO_CALLS = 2 * LONGWORD_LEN
STEP_SKIP_BYTES = {
    "bg_scroll_step_right": SKIP_ONE_CALL,
    "bg_scroll_step_left": SKIP_ONE_CALL,
    "bg_scroll_step_up": SKIP_TWO_CALLS,
    "bg_scroll_step_down": SKIP_TWO_CALLS,
}

# Where the oracle leaves the return address (emu.run writes it AT A7, not below it), so a step that
# skipped has REWRITTEN this longword and one that did not has never touched it.
RETURN_SLOT = emu.STACK_TOP


# --- how much of the game a fill is allowed to run -----------------------------------------------
# Per tile row the clear loop runs TILE_ROWS scanlines of three instructions, and the tile loop an
# eleven-instruction head plus TILE_ROWS scanlines of twenty-seven; the two halves together always
# run BUFFER_TILE_ROWS of each, whatever bg_scroll_y_coarse holds, because the split table's two
# counts sum to that. Doubled, because the point of a cap is to fail a run that fell into the
# 65536-iteration `dbf` rather than to predict the exact count.
_CLEAR_INSNS_PER_SCANLINE = 3
_TILE_INSNS_PER_SCANLINE = 27
_TILE_LOOP_HEAD_INSNS = 11
_FILL_ENTRY_INSNS = 40
FILL_INSN_CAP = 2 * (_FILL_ENTRY_INSNS + BUFFER_TILE_ROWS * (
    TILE_ROWS * (_CLEAR_INSNS_PER_SCANLINE + _TILE_INSNS_PER_SCANLINE)
    + _TILE_LOOP_HEAD_INSNS))

# A horizontal step is straight-line; a serve is a step and a fill under one entry.
STEP_INSN_CAP = leaf.LEAF_INSN_CAP
SERVE_INSN_CAP = FILL_INSN_CAP + STEP_INSN_CAP

# The vertical half, derived the same way and doubled for the same reason. A vertical step runs a
# three-instruction head and then, per ring cursor, a two-instruction test and one write per row
# word plus BUFFERS pointer writes; a row fill a head plus ROW_CELLS cells of a thirteen-instruction
# body; and the pre-shift, much the largest, PRESHIFT_COPIES x PRESHIFT_ROWS rows of a head,
# ROW_CELLS - 1 inner cells and a wrap-around tail.
_VERTICAL_STEP_HEAD_INSNS = 8
_ROW_CURSOR_INSNS = 3 + BUFFERS
VERTICAL_STEP_INSN_CAP = 2 * (_VERTICAL_STEP_HEAD_INSNS + 2 * _ROW_CURSOR_INSNS)

_ROW_FILL_HEAD_INSNS = 24
_ROW_FILL_CELL_INSNS = 13
ROW_FILL_INSN_CAP = 2 * (_ROW_FILL_HEAD_INSNS + ROW_CELLS * _ROW_FILL_CELL_INSNS)

_PRESHIFT_ROW_HEAD_INSNS = 25
_PRESHIFT_CELL_INSNS = 30
_PRESHIFT_ROW_TAIL_INSNS = 14
PRESHIFT_INSN_CAP = 2 * (PRESHIFT_COPIES * PRESHIFT_ROWS * (
    _PRESHIFT_ROW_HEAD_INSNS + (ROW_CELLS - 1) * _PRESHIFT_CELL_INSNS + _PRESHIFT_ROW_TAIL_INSNS))

VERTICAL_SERVE_INSN_CAP = VERTICAL_STEP_INSN_CAP + ROW_FILL_INSN_CAP + PRESHIFT_INSN_CAP

# A dispatch pass can serve all four directions; the queue drains at most QUEUE_MAX_STEPS of each
# and dispatches once more on top, which is what every queue case is seeded to respect.
SERVE_REQUESTS_INSN_CAP = 2 * VERTICAL_SERVE_INSN_CAP + 2 * SERVE_INSN_CAP
QUEUE_MAX_STEPS = 2
RUN_QUEUE_INSN_CAP = (2 * QUEUE_MAX_STEPS + 1) * SERVE_REQUESTS_INSN_CAP + leaf.LEAF_INSN_CAP


# --- the two edges, mirroring src/scroll.c's own descriptors -------------------------------------
class Edge:
    """What separates $7c08 from $7eb2, restated on this side so the model below can be one walk.

    Every field is a constant out of include/wonderboy.h or a sign the disassembly carries, so a
    reconstruction that swapped two of them fails against a model that did not.
    """

    def __init__(self, name, routine, serve, request, x_bias, map_offset, second_cell,
                 wrap_at_scroll_x, wrap_delta, invert_mask, full_cell_at_phase_zero,
                 or_takes_low_half):
        self.name = name
        self.routine = routine
        self.serve = serve
        self.request = request
        self.x_bias = x_bias
        self.map_offset = map_offset
        self.second_cell = second_cell
        self.wrap_at_scroll_x = wrap_at_scroll_x
        self.wrap_delta = wrap_delta
        self.invert_mask = invert_mask
        self.full_cell_at_phase_zero = full_cell_at_phase_zero
        self.or_takes_low_half = or_takes_low_half


RIGHT = Edge("right", "bg_scroll_fill_right_column", "bg_scroll_serve_right", REQUEST_RIGHT,
             x_bias=FILL_RIGHT_X_BIAS, map_offset=FILL_RIGHT_MAP_OFF, second_cell=CELL_BYTES,
             wrap_at_scroll_x=1, wrap_delta=-BUFFER_LINE, invert_mask=False,
             full_cell_at_phase_zero=True, or_takes_low_half=False)
LEFT = Edge("left", "bg_scroll_fill_left_column", "bg_scroll_serve_left", REQUEST_LEFT,
            x_bias=0, map_offset=FILL_LEFT_MAP_OFF, second_cell=-CELL_BYTES,
            wrap_at_scroll_x=0, wrap_delta=BUFFER_LINE, invert_mask=True,
            full_cell_at_phase_zero=False, or_takes_low_half=True)

EDGES = {edge.name: edge for edge in (RIGHT, LEFT)}


# --- reading the image the same way the 68000 does ------------------------------------------------
# `u16` and `s16` are leaf.py's, imported above: three batteries model their routine's arithmetic
# this way and one spelling of the sign extension is what keeps them agreeing about it.

def _rol32(value, count):
    if count == 0:
        return value
    return ((value << count) | (value >> (LONG_BITS - count))) & 0xffffffff


# --- seeding --------------------------------------------------------------------------------------
# The map is a rectangle wide enough for either fill's column offset and BUFFER_TILE_ROWS rows deep,
# with a margin so a walk that started one cell early still reads seeded bytes rather than zeros.
MAP_CURSOR_SEED = 0x30
MAP_STRIDE_SEED = 0x50
MAP_SEED_LEN = MAP_STRIDE_SEED * (BUFFER_TILE_ROWS + 2)

# Every case draws from the SIXTEEN tiles whose bitmaps are shipped in the .PRG (the other 133 in
# the region are zero in the file and filled at runtime, which
# test_the_shipped_tile_bitmaps_are_the_sixteen_the_header_names pins). A zero source would hide a
# wrong rotation the way a zero destination hides a wrong row count.

# One scanline of margin either side of the buffer, seeded like the buffer itself.
BUFFER_MARGIN = BUFFER_LINE


def _scroll_pokes(phase, scroll_x, y_coarse, map_cursor=MAP_CURSOR_SEED, salt=0,
                  whole_region=False):
    """The image a fill case runs on: the four position words, the map and its stride, the whole
    tile index, and the destination buffers widened by a scanline either side.

    ``whole_region`` seeds ALL EIGHT buffers rather than the phase's own — what a vertical case
    needs, because the pre-shift walks a row through every copy. The two seedings key on the same
    address and the same salt, so a case that wants both gets one consistent image.
    """
    if whole_region:
        band_lo, band_len = BUFFER_BASE - BUFFER_MARGIN, BUFFERS * BUFFER_LEN + 2 * BUFFER_MARGIN
    else:
        band_lo = BUFFER_BASE + phase * BUFFER_PHASE_STRIDE - BUFFER_MARGIN
        band_len = BUFFER_LEN + 2 * BUFFER_MARGIN
    pokes = {
        PHASE: word(phase),
        SCROLL_X: word(scroll_x),
        Y_COARSE: word(y_coarse),
        MAP_CURSOR: word(map_cursor),
        MAP_ROW_STRIDE: word(MAP_STRIDE_SEED),
        MAP_DATA: keyed_block(MAP_DATA, MAP_SEED_LEN, salt + 1),
        TILE_INDEX_TABLE: b"".join(
            word(TILE_SHIPPED_FIRST + keyed_byte(TILE_INDEX_TABLE + i, salt + 2)
                 % TILE_SHIPPED_COUNT)
            for i in range(TILE_INDEX_ENTRIES)),
        band_lo: keyed_block(band_lo, band_len, salt + 3),
    }
    return pokes


# --- the model ------------------------------------------------------------------------------------
# Everything above the two column fills is modelled on a STAGED image — a mutable copy each step
# writes into as it goes — because the routines above them run on each other's output: a serve fills
# from the phase its own step just wrote, and the queue dispatches on request bytes it just raised.
# `out` accumulates the write set the case then compares for equality.

def _put(out, staged, addr, value):
    for offset, byte in enumerate(word(value)):
        out[addr + offset] = byte
        staged[addr + offset] = byte


def _put32(out, staged, addr, value):
    for offset, byte in enumerate(longword(value)):
        out[addr + offset] = byte
        staged[addr + offset] = byte


def _put8(out, staged, addr, value):
    out[addr] = value
    staged[addr] = value


def _apply(out, staged, produced):
    """Fold a sub-model's {address: byte} into both the write set and the staged image."""
    for addr, byte in produced.items():
        out[addr] = byte
        staged[addr] = byte


def _u32(image, addr):
    return int.from_bytes(bytes(image[addr:addr + LONGWORD_LEN]), "big")


def _model_fill(image, edge):
    """The column fill, walked in Python over the seeded image. Returns {address: final byte}.

    Written from the disassembly rather than from src/scroll.c: it is the third statement of the
    same geometry, and the one that lets a case say WHICH bytes moved.
    """
    phase = u16(image, PHASE)
    scroll_x = u16(image, SCROLL_X)
    coarse = u16(image, Y_COARSE)

    cleared = (BUFFER_BASE + phase * BUFFER_PHASE_STRIDE + coarse * TILE_BLOCK_LEN
               + s16(((scroll_x + edge.x_bias) & PHASE_MASK) * CELL_BYTES)) & 0xffffffff
    ored = cleared
    written = (cleared + edge.second_cell) & 0xffffffff
    if scroll_x == edge.wrap_at_scroll_x:
        written = (written + edge.wrap_delta) & 0xffffffff

    counts = bytes(image[COL_SPLIT_TABLE + coarse * LONGWORD_LEN:][:LONGWORD_LEN])
    out = {FILL_COUNTS + i: counts[i] for i in range(LONGWORD_LEN)}
    first = int.from_bytes(counts[:STATE_WORD_LEN], "big")
    second = int.from_bytes(counts[STATE_WORD_LEN:], "big")

    half = u16(image, EDGE_MASK_TABLE + phase)
    mask = (half << WORD_BITS) | half
    if edge.invert_mask and phase != 0:
        mask ^= 0xffffffff

    map_cursor = (MAP_DATA + s16(u16(image, MAP_CURSOR) + edge.map_offset)) & 0xffffffff

    def read(addr, length):
        return int.from_bytes(bytes(out.get(addr + i, image[addr + i]) for i in range(length)),
                              "big")

    def write(addr, length, value):
        for i, byte in enumerate(value.to_bytes(length, "big")):
            out[addr + i] = byte

    def clear(cursor, tile_rows):
        for _ in range(tile_rows + 1):
            for _row in range(TILE_ROWS):
                for at in range(0, CELL_BYTES, LONGWORD_LEN):
                    cell = (cursor + at) & 0xffffffff
                    write(cell, LONGWORD_LEN, read(cell, LONGWORD_LEN) & mask)
                cursor = (cursor + BUFFER_LINE) & 0xffffffff
        return cursor

    def draw(cursors, shift, tile_rows):
        ored_at, written_at, map_at = cursors
        stride = s16(u16(image, MAP_ROW_STRIDE))
        for _ in range(tile_rows + 1):
            tile_number = u16(image, TILE_INDEX_TABLE + image[map_at] * STATE_WORD_LEN)
            tile = (TILE_BITMAPS + tile_number * TILE_BITMAP_LEN) & 0xffffffff
            map_at = (map_at + stride) & 0xffffffff
            for _row in range(TILE_ROWS):
                rotated = [_rol32(u16(image, tile + plane * PLANE_STRIDE), shift)
                           for plane in range(PLANES)]
                tile = (tile + CELL_BYTES) & 0xffffffff
                for plane, value in enumerate(rotated):
                    low = value & 0xffff
                    high = value >> WORD_BITS
                    at_or = (ored_at + plane * PLANE_STRIDE) & 0xffffffff
                    at_move = (written_at + plane * PLANE_STRIDE) & 0xffffffff
                    write(at_or, STATE_WORD_LEN,
                          read(at_or, STATE_WORD_LEN) | (low if edge.or_takes_low_half else high))
                    write(at_move, STATE_WORD_LEN, high if edge.or_takes_low_half else low)
                ored_at = (ored_at + BUFFER_LINE) & 0xffffffff
                written_at = (written_at + BUFFER_LINE) & 0xffffffff
        return ored_at, written_at, map_at

    cleared = clear(cleared, first)
    shift = phase
    if edge.full_cell_at_phase_zero and shift == 0:
        shift = FULL_CELL_ROTATION
        map_cursor = (map_cursor - 1) & 0xffffffff
    cursors = draw((ored, written, map_cursor), shift, first)

    cleared = (cleared - BUFFER_LEN) & 0xffffffff
    cursors = tuple((c - BUFFER_LEN) & 0xffffffff for c in cursors[:2]) + (cursors[2],)
    if s16(second) < 0:
        return out
    clear(cleared, second)
    draw(cursors, shift, second)
    return out


# --- 68000 operand encoders, for the whole-body entry pins ----------------------------------------
# Single-use encodings belong next to the battery that needs them (test/leaf.py's docstring says
# so); what is shared with test_hud.py is imported from there. Each helper takes the same operands
# the reconstruction does, so a wrong address, mask or displacement fails at the routine's own entry
# rather than as a diff a hundred kilobytes away.
A0, A1, A2, A3, A4, A5, A6 = range(7)
D0, D1, D4, D5, D6, D7 = 0, 1, 4, 5, 6, 7


def move_w_indexed_d0(base, index):
    """`move.w (0,An,Dn.w),d0` — how a fill reads a word out of a table it just indexed."""
    return opcode(0x3030 | base) + word(index << 12)


def move_w_dn_abs_l(reg, addr):
    return opcode(0x33c0 | reg) + longword(addr)


def andi_w_abs_l(value, addr):
    return opcode(0x0279) + word(value) + longword(addr)


def addi_w_dn(reg, value):
    return opcode(0x0640 | reg) + word(value)


def andi_w_dn(reg, value):
    return opcode(0x0240 | reg) + word(value)


def cmpi_w_abs_l(value, addr):
    return opcode(0x0c79) + word(value) + longword(addr)


def addq_w_abs_l(amount, addr):
    return opcode(0x5079 | ((amount & 7) << 9)) + longword(addr)


def addq_l_ind_a7(amount):
    return opcode(0x5097 | ((amount & 7) << 9))


# --- the encodings the vertical half and the queue above it add -----------------------------------


def clr_l_abs_l(addr):
    return opcode(0x42b9) + longword(addr)


def addi_l_imm_abs_l(value, addr):
    return opcode(0x06b9) + longword(value) + longword(addr)


def subi_l_imm_abs_l(value, addr):
    return opcode(0x04b9) + longword(value) + longword(addr)


def move_w_abs_l_abs_l(source, destination):
    return leaf.MOVE_W_ABS_L_ABS_L + longword(source) + longword(destination)


def neg_w_dn(reg):
    return opcode(0x4440 | reg)


def add_w_d1_abs_l(addr):
    return opcode(0xd379) + longword(addr)


def sub_w_d1_abs_l(addr):
    return opcode(0x9379) + longword(addr)


def move_w_dn_postinc_a1(reg):
    return opcode(0x32c0 | reg)


def or_w_dn_postinc_a1(reg):
    return opcode(0x8159 | (reg << 9))


def shift_imm_dn(kind, count, reg):
    """`<shift>.<size> #count,Dn`. ``kind`` carries everything but the count and the register:
    direction, operand size, immediate-count, and which of ASL/LSL/ASR/ROL it is."""
    return opcode(kind | ((count & 7) << 9) | reg)


def swap_dn(reg):
    return opcode(0x4840 | reg)


def move_l_d0_dn(reg):
    return opcode(0x2000 | (reg << 9))


def tst_w_dn(reg):
    """`tst.w Dn` — three routines here test a different register, which is what collapsed the two
    single-register constants this replaces (the third-user rule ../STATUS.md records)."""
    return opcode(0x4a40 | reg)


# --- the encodings the consumer tier adds ---------------------------------------------------------
# bg_scroll_blit is the only routine here that addresses a longword through a table, jumps through a
# register, or reads WB_SCREEN_BACK, so these are its own.

def movea_l_indexed(reg, base, index):
    """`movea.l (0,An,Dn.w),Am` — the jump table read, and the whole of the original's dispatch."""
    return opcode(0x2070 | (reg << 9) | base) + word(index << 12)


def adda_w_imm_an(value, reg):
    return opcode(0xd0fc | (reg << 9)) + word(value)


def addq_l_imm_an(amount, reg):
    """`addq.l #n,An` — `#8` encodes as 0, which is what makes the family's `addq.l #8,a0` a word."""
    return opcode(0x5088 | ((amount & 7) << 9) | reg)


def subq_w_imm_dn(amount, reg):
    return opcode(0x5140 | ((amount & 7) << 9) | reg)


def sub_w_abs_l_dn(reg, addr):
    """`sub.w <abs>.l,Dn` — the other direction from sub_w_d1_abs_l above, which stores back."""
    return opcode(0x9040 | (reg << 9) | 0x39) + longword(addr)


def jmp_ind(reg):
    return opcode(0x4ed0 | reg)


def _shift_for(multiplier):
    """The `asl.w #n` count that multiplies by ``multiplier``.

    The blit scales three different things by a shift, and spelling each as the constant it scales
    BY — rather than as the count in the opcode — is what makes a header constant that moved fail
    here instead of quietly disagreeing with the pin.
    """
    shift = multiplier.bit_length() - 1
    assert multiplier == 1 << shift, f"{multiplier} is not a power of two, so no `asl.w` gives it"
    return shift


def _clear_plane_registers():
    """`moveq #0,d0 / move.l d0,d1 / d2 / d3` — how both the column fills and the pre-shift clear
    the four registers a scanline's plane words are read into, and what zero-extends them."""
    return MOVEQ_0_D0 + b"".join(move_l_d0_dn(reg) for reg in range(1, PLANES))


class _Assembler:
    """A body under construction, and where each piece of it lands.

    A `bsr.w`'s displacement depends on the address it is assembled AT, so the routines with callees
    cannot be written as one expression the way the straight-line ones are. This keeps the cursor, so
    a call's target comes out of ../names.txt and its displacement out of the geometry — a pin built
    at the wrong offset, or aimed at the wrong callee, fails on the bytes.
    """

    def __init__(self, entry):
        self.entry = entry
        self._pieces = []

    @property
    def at(self):
        """Where the NEXT piece will be assembled."""
        return self.entry + sum(len(piece) for piece in self._pieces)

    def emit(self, *pieces):
        self._pieces.extend(pieces)
        return self

    def call(self, name):
        return self.emit(bsr_w(self.at, leaf.entry_of(name)))

    def bytes(self):
        return b"".join(self._pieces)


def bra_s_over(spanned_bytes):
    """`bra.s <start of the body>`: a BYTE displacement back over the body and the opcode word."""
    displacement = -(spanned_bytes + leaf.BRANCH_EXTENSION)
    assert -0x80 <= displacement < 0, (
        f"{displacement} does not fit a `bra.s` byte displacement — the original spells this jump "
        f"short, so a body that outgrew it would need a different opcode here")
    return opcode(BRA_S | (displacement & BYTE_MASK))


BNE_W, BEQ_W, BMI_W, BPL_W, BGT_W, BLT_W = 0x6600, 0x6700, 0x6b00, 0x6a00, 0x6e00, 0x6d00
# `bra` is one opcode: a zero displacement byte means the WORD form follows, any other means the
# short form is the whole instruction. BRA_S names the second reading of the same number.
BRA_W = 0x6000
BRA_S = BRA_W
BYTE_MASK = 0xff
# The fixed half of a `#count,Dn` shift: direction, operand size, immediate count, and which shift.
ASR_W_IMM, LSL_W_IMM, ASL_W_IMM, LSL_L_IMM, ROL_L_IMM = 0xe040, 0xe148, 0xe140, 0xe188, 0xe198
LSL_L_7_D0 = shift_imm_dn(LSL_L_IMM, 7, D0)
LSL_L_4_D0 = shift_imm_dn(LSL_L_IMM, 4, D0)
LSL_W_2_D0 = shift_imm_dn(LSL_W_IMM, 2, D0)
ASL_W_3_D0 = shift_imm_dn(ASL_W_IMM, 3, D0)
MOVEQ_0_D0 = opcode(0x7000)
MULU_W_IMM_D0 = opcode(0xc0fc)
ADDA_L_D0_A0 = opcode(0xd1c0)
MOVEA_L_A0_A1, MOVEA_L_A0_A2 = opcode(0x2248), opcode(0x2448)
MOVE_W_POSTINC_A5_D0 = opcode(0x301d)
MOVE_L_POSTINC_A5_ABS_L = opcode(0x23dd)
MOVE_L_POSTINC_A5_ABS_W = opcode(0x21dd)
MOVE_W_ABS_W_D7 = opcode(0x3e38)
SWAP_D6, NOT_L_D6 = opcode(0x4846), opcode(0x4686)
MOVE_W_IND_A6_D6 = opcode(0x3c16)
MOVE_W_IMM_D5 = opcode(0x3a3c)
AND_L_D6_POSTINC_A0 = opcode(0xcd98)
MOVE_B_IND_A3_D0 = opcode(0x1013)
MOVE_B_POSTINC_A6_D0 = opcode(0x101e)
ADD_W_D0_D0 = opcode(0xd040)
ADD_W_D1_D0 = opcode(0xd041)
ADDQ_W_2_D0 = opcode(0x5440)
CMP_W_ABS_L_D0 = opcode(0xb079)
CLR_W_D0 = opcode(0x4240)
ADDA_W_D6_A0 = opcode(0xd0c6)
MOVE_L_POSTINC_A0_POSTINC_A1 = opcode(0x22d8)
MOVE_L_POSTINC_A0_D16_A1 = opcode(0x2358)

# Both `bcc.w` and `bsr.w` are one opcode word and one displacement word, whatever they span — which
# is what lets a loop's two branches be solved without solving each other.
BRANCH_W_LEN = 4
BSR_W_LEN = len(bsr_w(0, 0))


def _clear_block():
    """One scanline of the clear loop: two `and.l` and the step to the next scanline."""
    return (AND_L_D6_POSTINC_A0 * (CELL_BYTES // LONGWORD_LEN)
            + lea_d16(A0, BUFFER_LINE - CELL_BYTES))


def _clear_loop():
    body = _clear_block() * TILE_ROWS
    return body + dbf(D7, body)


def _tile_loop(or_takes_low_half):
    """The tile loop both fills spell twice: a map byte through the index table into a tile pointer,
    then sixteen scanlines of four plane words rotated left as longwords."""
    move_to_a2 = b"".join(opcode(0x34c0 | reg) for reg in range(PLANES))
    or_to_a1 = b"".join(or_w_dn_postinc_a1(reg) for reg in range(PLANES))
    scanline = (
        _clear_plane_registers()
        + b"".join(opcode(0x301c | (reg << 9)) for reg in range(PLANES))  # move.w (a4)+,d0..d3
        + b"".join(opcode(0xebb8 | reg) for reg in range(PLANES))         # rol.l d5,d0..d3
        + (or_to_a1 if or_takes_low_half else move_to_a2)
        + b"".join(swap_dn(reg) for reg in range(PLANES))
        + (move_to_a2 if or_takes_low_half else or_to_a1)
        + lea_d16(A1, BUFFER_LINE - CELL_BYTES)
        + lea_d16(A2, BUFFER_LINE - CELL_BYTES))
    inner = move_w_imm_dn(D4, TILE_ROWS - 1) + scanline + dbf(D4, scanline)
    head = (lea_abs_l(A4, TILE_BITMAPS)
            + MOVEQ_0_D0 + MOVE_B_IND_A3_D0
            + lea_abs_l(A5, TILE_INDEX_TABLE) + ADD_W_D0_D0
            + move_w_indexed_d0(A5, D0) + LSL_L_7_D0 + lea_indexed(A4, D0, longword_index=True)
            + move_w_abs_l_dn(D0, MAP_ROW_STRIDE) + lea_indexed(A3, D0))
    return head + inner + dbf(D7, head + inner)


def _fill_column_body(edge, load_counts, load_first, load_second):
    """The whole of $7c08 / $7eb2. The two differ only in the pieces this takes as arguments and in
    the fields of `edge`, which is the claim the two reconstructions make about each other."""
    wrap = lea_d16(A2, edge.wrap_delta)
    if edge is RIGHT:
        cell_index = addi_w_dn(D0, edge.x_bias) + andi_w_dn(D0, PHASE_MASK)
        second_cell_test = cmpi_w_abs_l(edge.wrap_at_scroll_x, SCROLL_X) + branch(BNE_W, wrap)
        map_offset = addi_w_dn(D0, edge.map_offset)
        invert = b""
    else:
        cell_index = andi_w_dn(D0, PHASE_MASK)
        second_cell_test = tst_w_abs_l(SCROLL_X) + branch(BNE_W, wrap)
        map_offset = ADDQ_W_2_D0
        invert = tst_w_abs_l(PHASE) + branch(BEQ_W, NOT_L_D6) + NOT_L_D6

    head = (
        lea_abs_l(A0, BUFFER_BASE)
        + MOVEQ_0_D0 + move_w_abs_l_dn(D0, PHASE) + MULU_W_IMM_D0 + word(BUFFER_PHASE_STRIDE)
        + ADDA_L_D0_A0
        + MOVEQ_0_D0 + move_w_abs_l_dn(D0, Y_COARSE) + LSL_L_7_D0 + LSL_L_4_D0 + ADDA_L_D0_A0
        + move_w_abs_l_dn(D0, SCROLL_X) + cell_index + ASL_W_3_D0 + lea_indexed(A0, D0)
        + MOVEA_L_A0_A1 + MOVEA_L_A0_A2 + lea_d16(A2, edge.second_cell)
        + second_cell_test + wrap
        + lea_abs_l(A5, Y_COARSE) + MOVE_W_POSTINC_A5_D0 + LSL_W_2_D0 + lea_indexed(A5, D0)
        + load_counts
        + move_w_abs_l_dn(D6, PHASE) + lea_abs_l(A6, EDGE_MASK_TABLE) + lea_indexed(A6, D6)
        + MOVE_W_IND_A6_D6 + SWAP_D6 + MOVE_W_IND_A6_D6
        + invert
        + lea_abs_l(A3, MAP_DATA) + move_w_abs_l_dn(D0, MAP_CURSOR) + map_offset
        + lea_indexed(A3, D0))

    if edge is RIGHT:
        shift = (move_w_abs_l_dn(D5, PHASE) + tst_w_dn(D5)
                 + branch(BNE_W, MOVE_W_IMM_D5 + word(FULL_CELL_ROTATION),
                          lea_d16(A3, -1))
                 + MOVE_W_IMM_D5 + word(FULL_CELL_ROTATION) + lea_d16(A3, -1))
    else:
        shift = move_w_abs_l_dn(D5, PHASE)

    tiles = _tile_loop(edge.or_takes_low_half)
    rewind = (lea_d16(A0, -BUFFER_LEN) + lea_d16(A1, -BUFFER_LEN)
              + lea_d16(A2, -BUFFER_LEN))
    second_half = _clear_loop() + load_second + tiles
    return (head + load_first + _clear_loop() + shift + load_first + tiles
            + rewind + load_second + branch(BMI_W, second_half) + second_half + RTS)


FILL_BODIES = {
    "right": _fill_column_body(
        RIGHT,
        load_counts=MOVE_L_POSTINC_A5_ABS_L + longword(FILL_COUNTS),
        load_first=move_w_abs_l_dn(D7, FILL_COUNTS),
        load_second=move_w_abs_l_dn(D7, FILL_COUNT_SECOND)),
    "left": _fill_column_body(
        LEFT,
        load_counts=MOVE_L_POSTINC_A5_ABS_W + word(FILL_COUNTS),
        load_first=MOVE_W_ABS_W_D7 + word(FILL_COUNTS),
        load_second=MOVE_W_ABS_W_D7 + word(FILL_COUNT_SECOND)),
}

# The three cell-offset writes the two steps share at the end of their moving arm.
_STEP_CELL_TAIL_RIGHT = (addq_w_abs_l(CELL_BYTES, ROW_BYTE_OFFSET)
                         + addq_w_abs_l(1, MAP_CURSOR)
                         + addq_w_abs_l(1, SCROLL_X) + andi_w_abs_l(PHASE_MASK, SCROLL_X)
                         + branch(BEQ_W, RTS) + RTS
                         + clr_w_abs_l(ROW_BYTE_OFFSET) + RTS)
_STEP_CELL_TAIL_LEFT = (subq_w_abs_l(1, MAP_CURSOR)
                        + subq_w_abs_l(CELL_BYTES, ROW_BYTE_OFFSET)
                        + andi_w_abs_l(ROW_OFFSET_MASK, ROW_BYTE_OFFSET)
                        + subq_w_abs_l(1, SCROLL_X) + andi_w_abs_l(PHASE_MASK, SCROLL_X)
                        + branch(BEQ_W, RTS) + RTS
                        + clr_w_abs_l(ROW_BYTE_OFFSET) + RTS)

def _skip_and_return(skip):
    """The whole of a step's no-work arm: consume the caller's calls, then `rts` past them."""
    return addq_l_ind_a7(skip) + RTS


_SKIP_AND_RETURN = _skip_and_return(SKIP_ONE_CALL)

STEP_BODIES = {
    "right": (move_w_abs_l_dn(D0, POS_X) + CMP_W_ABS_L_D0 + longword(LIMIT_X)
              + branch(BNE_W, _SKIP_AND_RETURN) + _SKIP_AND_RETURN
              + tst_w_abs_l(PENDING)
              + branch(BMI_W, leaf.MOVE_W_IMM_ABS_L + word(PENDING_SET) + longword(PENDING), RTS)
              + leaf.MOVE_W_IMM_ABS_L + word(PENDING_SET) + longword(PENDING) + RTS
              + addq_w_abs_l(SCROLL_STEP, POS_X)
              + addq_w_abs_l(SCROLL_STEP, PHASE) + andi_w_abs_l(PHASE_MASK, PHASE)
              + branch(BEQ_W, RTS) + RTS
              + _STEP_CELL_TAIL_RIGHT),
    "left": (move_w_abs_l_dn(D0, POS_X) + tst_w_dn(D0)
             + branch(BNE_W, _SKIP_AND_RETURN) + _SKIP_AND_RETURN
             + tst_w_abs_l(PENDING)
             + branch(BEQ_W, clr_w_abs_l(PENDING), RTS) + clr_w_abs_l(PENDING) + RTS
             + subq_w_abs_l(SCROLL_STEP, POS_X)
             + subq_w_abs_l(SCROLL_STEP, PHASE)
             + branch(BMI_W, andi_w_abs_l(PHASE_MASK, PHASE), RTS)
             + andi_w_abs_l(PHASE_MASK, PHASE) + RTS
             + leaf.MOVE_W_IMM_ABS_L + word(PHASE_LAST) + longword(PHASE)
             + _STEP_CELL_TAIL_LEFT),
}


def _serve_body(edge, step_name):
    here = leaf.entry_of(edge.serve)
    clear = clr_b_abs_l(edge.request)
    step = bsr_w(here + len(clear), leaf.entry_of(step_name))
    fill = bsr_w(here + len(clear) + len(step), leaf.entry_of(edge.routine))
    return clear + step + fill + RTS


SERVE_BODIES = {
    "right": _serve_body(RIGHT, "bg_scroll_step_right"),
    "left": _serve_body(LEFT, "bg_scroll_step_left"),
}


# --- the vertical half's bodies -------------------------------------------------------------------
# The ring row a buffer's pointer must hold, which is the invariant the wrap reload writes out and
# the moving arm keeps by adding to what is there.
def _buffer_row_pointer(copy, row):
    return BUFFER_BASE + copy * BUFFER_LEN + row * BUFFER_LINE


def _row_cursor_block(row_word, first_pointer, wrap_from, wrap_to, down):
    """One ring cursor's step, twice per routine: reload when the row IS ALREADY at the wrap, else
    move the row by two and every pointer it owns by the two scanlines that is."""
    # `clr.w` is what the original spells where the reload value is zero — the down step's — and a
    # `move.w #imm` where it is not; the two are different instructions, so the pin says which.
    reload_row = (clr_w_abs_l(row_word) if wrap_to == 0
                  else leaf.MOVE_W_IMM_ABS_L + word(wrap_to) + longword(row_word))
    reload = reload_row + b"".join(
        move_l_imm_abs_l(_buffer_row_pointer(copy, wrap_to),
                         first_pointer + copy * BUFFER_ROW_PAIR)
        for copy in range(BUFFERS))
    step_pointer = addi_l_imm_abs_l if down else subi_l_imm_abs_l
    move = (addq_w_abs_l(SCROLL_STEP, row_word) if down else subq_w_abs_l(SCROLL_STEP, row_word))
    move += b"".join(step_pointer(SCROLL_STEP * BUFFER_LINE,
                                  first_pointer + copy * BUFFER_ROW_PAIR)
                     for copy in range(BUFFERS))
    # ...and likewise `tst.w` where the wrap row is zero (the up step's) against `cmpi.w`.
    test = (tst_w_abs_l(row_word) if wrap_from == 0 else cmpi_w_abs_l(wrap_from, row_word))
    return (test + branch(BNE_W, reload, branch(BRA_W, move))
            + reload + branch(BRA_W, move) + move)


def _vertical_step_body(down):
    """$761c / $77ba. The boundary test is the only place the two are not a mirror: up compares
    bg_scroll_pos_y against zero (`tst.w`), down against bg_scroll_limit_y (`move.w`/`cmp.w`)."""
    skip = _skip_and_return(SKIP_TWO_CALLS)
    if down:
        boundary = (move_w_abs_l_dn(D0, POS_Y) + CMP_W_ABS_L_D0 + longword(LIMIT_Y)
                    + branch(BNE_W, skip) + skip
                    + addq_w_abs_l(SCROLL_STEP, POS_Y))
        wrap_from, wrap_to = SCROLL_Y_LAST, 0
    else:
        boundary = (tst_w_abs_l(POS_Y) + branch(BNE_W, skip) + skip
                    + subq_w_abs_l(SCROLL_STEP, POS_Y))
        wrap_from, wrap_to = 0, SCROLL_Y_LAST
    cursors = b"".join(
        _row_cursor_block(row_word, BUFFER_ROWS + member, wrap_from, wrap_to, down)
        for row_word, member in ((SCROLL_Y, BUFFER_ROW_TOP),
                                 (SCROLL_Y_BOTTOM, BUFFER_ROW_BOTTOM)))
    coarse = (MOVEQ_0_D0 + move_w_abs_l_dn(D0, SCROLL_Y)
              + shift_imm_dn(ASR_W_IMM, Y_COARSE_SHIFT, D0) + move_w_dn_abs_l(D0, Y_COARSE))
    return boundary + cursors + coarse + RTS


def _row_fill_cell_loop(lea_before_moveq):
    """`cells + 1` map cells, each two scanlines of one cell copied out of a tile bitmap. The two
    fills differ only in whether the tile base is loaded before or after the `moveq` that clears the
    map byte's register — nothing observable, and spelt out so the pin says so."""
    head = lea_abs_l(A0, TILE_BITMAPS) + MOVEQ_0_D0
    if not lea_before_moveq:
        head = MOVEQ_0_D0 + lea_abs_l(A0, TILE_BITMAPS)
    body = (head
            + MOVE_B_POSTINC_A6_D0
            + lea_abs_l(A5, TILE_INDEX_TABLE) + ADD_W_D0_D0
            + move_w_indexed_d0(A5, D0) + LSL_L_7_D0 + lea_indexed(A0, D0, longword_index=True)
            + ADDA_W_D6_A0
            + MOVE_L_POSTINC_A0_POSTINC_A1 * (CELL_BYTES // LONGWORD_LEN)
            + b"".join(MOVE_L_POSTINC_A0_D16_A1
                       + word(BUFFER_LINE - CELL_BYTES + byte)
                       for byte in range(0, CELL_BYTES, LONGWORD_LEN)))
    return body + dbf(D7, body)


def _row_fill_body(bottom):
    """$7a3e / $7b1a."""
    if bottom:
        destination = movea_l_abs_l(A1, BUFFER_ROWS + BUFFER_ROW_BOTTOM)
        map_row = (move_w_abs_l_dn(D0, MAP_CURSOR) + move_w_abs_l_dn(D1, MAP_ROW_STRIDE)
                   + mulu_w_imm_dn(D1, BOTTOM_ROW_STRIDES) + ADD_W_D1_D0)
        # The tile row steps AFTER the draw, and pushes the map cursor a row DOWN when it wraps.
        step_tile_row = (move_w_abs_l_dn(D0, TILE_ROW) + addi_w_dn(D0, TILE_ROW_STEP)
                         + andi_w_dn(D0, TILE_ROW_MASK)
                         + branch(BNE_W, move_w_abs_l_dn(D1, MAP_ROW_STRIDE)
                                    + add_w_d1_abs_l(MAP_CURSOR))
                         + move_w_abs_l_dn(D1, MAP_ROW_STRIDE) + add_w_d1_abs_l(MAP_CURSOR)
                         + move_w_dn_abs_l(D0, TILE_ROW))
        head, tail = b"", step_tile_row + move_w_imm_dn(D0, ROW_DRAWN_BOTTOM)
        count_lead = moveq_0_dn(D7)
    else:
        destination = movea_l_abs_l(A1, BUFFER_ROWS + BUFFER_ROW_TOP)
        map_row = move_w_abs_l_dn(D0, MAP_CURSOR)
        # ...and BEFORE it going up, pulling the cursor a row UP on the same wrap.
        head = (move_w_abs_l_dn(D0, TILE_ROW) + subi_w_dn(D0, TILE_ROW_STEP)
                + branch(BPL_W, move_w_abs_l_dn(D1, MAP_ROW_STRIDE)
                           + sub_w_d1_abs_l(MAP_CURSOR))
                + move_w_abs_l_dn(D1, MAP_ROW_STRIDE) + sub_w_d1_abs_l(MAP_CURSOR)
                + andi_w_dn(D0, TILE_ROW_MASK) + move_w_dn_abs_l(D0, TILE_ROW))
        tail = CLR_W_D0
        count_lead = b""

    cursors = (destination + move_w_abs_l_dn(D0, ROW_BYTE_OFFSET) + lea_indexed(A1, D0)
               + lea_abs_l(A6, MAP_DATA_ROW) + map_row + lea_indexed(A6, D0))
    first = (lea_abs_l(A0, ROW_SPLIT_TABLE) + count_lead + move_w_abs_l_dn(D7, SCROLL_X)
             + shift_imm_dn(LSL_W_IMM, 2, D7) + lea_indexed(A0, D7) + move_w_ind_dn(D7, A0)
             + move_w_abs_l_dn(D6, TILE_ROW))
    cells = _row_fill_cell_loop(lea_before_moveq=bottom)
    second = (lea_d16(A1, -BUFFER_LINE)
              + lea_abs_l(A0, ROW_SPLIT_TABLE) + count_lead + move_w_abs_l_dn(D7, SCROLL_X)
              + shift_imm_dn(LSL_W_IMM, 2, D7) + lea_indexed(A0, D7)
              + move_w_ind_dn(D7, A0, STATE_WORD_LEN)
              + branch(BMI_W, cells))
    return head + cursors + first + cells + second + cells + tail + RTS


def _preshift_cell():
    """`moveq #0,d0 / move.l d0,d1..d3 / move.w (a0)+,d0..d3 / rol.l #2,d0..d3` — four plane words
    zero-extended into longwords and rotated, so the two pixels that leave the top of each word end
    up in the longword's high half."""
    return (_clear_plane_registers()
            + b"".join(move_w_postinc_dn(reg, A0) for reg in range(PLANES))
            + b"".join(shift_imm_dn(ROL_L_IMM, PRESHIFT_BITS, reg) for reg in range(PLANES)))


def _preshift_body():
    """$8144. Three nested loops: PRESHIFT_COPIES copies x PRESHIFT_ROWS rows x ROW_CELLS cells."""
    swap_all = b"".join(swap_dn(reg) for reg in range(PLANES))
    write_all = b"".join(move_w_dn_postinc_a1(reg) for reg in range(PLANES))
    or_all = b"".join(or_w_dn_postinc_a1(reg) for reg in range(PLANES))
    carry = [PRESHIFT_CARRY + plane * PLANE_STRIDE for plane in range(PLANES)]

    # Cell 0 is written and its carry PARKED; cells 1..15 each OR their carry into the cell before
    # them and write themselves; the tail ORs cell 0's parked carry into cell 15, closing the ring.
    row_head = (_preshift_cell() + write_all + swap_all
                + b"".join(move_w_dn_abs_l(plane, carry[plane]) for plane in range(PLANES))
                + move_w_imm_dn(D7, ROW_CELLS - 2))
    inner = (lea_d16(A1, -CELL_BYTES) + _preshift_cell() + swap_all + or_all + swap_all + write_all)
    row_tail = (lea_d16(A1, -CELL_BYTES) + _clear_plane_registers()
                + b"".join(move_w_abs_l_dn(plane, carry[plane]) for plane in range(PLANES))
                + or_all)
    row = row_head + inner + dbf(D7, inner) + row_tail

    load_top = movea_l_abs_l(A0, BUFFER_ROWS + BUFFER_ROW_TOP)
    load_bottom = movea_l_abs_l(A0, BUFFER_ROWS + BUFFER_ROW_BOTTOM)
    to_next_copy = lea_d16(A1, BUFFER_LEN, source=A0)
    head = (tst_w_dn(D0) + branch(BMI_W, load_top, branch(BRA_W, load_bottom))
            + load_top + branch(BRA_W, load_bottom) + load_bottom
            + to_next_copy + move_w_imm_dn(D5, PRESHIFT_COPIES - 1))
    one_copy = move_w_imm_dn(D6, PRESHIFT_ROWS - 1) + row + dbf(D6, row)
    advance = lea_d16(A0, -(PRESHIFT_ROWS * BUFFER_LINE), source=A1) + to_next_copy
    return head + one_copy + advance + dbf(D5, one_copy + advance) + RTS


def _vertical_serve_body(serve_name, request, step_name, fill_name):
    """$75d4 / $75e8 — the horizontal serve with one more call under the same skip."""
    asm = _Assembler(leaf.entry_of(serve_name))
    asm.emit(clr_b_abs_l(request))
    for callee in (step_name, fill_name, "bg_scroll_preshift_rows"):
        asm.call(callee)
    return asm.emit(RTS).bytes()


def _serve_requests_body():
    """$759a — four `tst.b`/`beq`/`bsr` in line, in the original's own order."""
    asm = _Assembler(leaf.entry_of("bg_scroll_serve_requests"))
    for request, handler in ((REQUEST_UP, "bg_scroll_serve_up"),
                             (REQUEST_DOWN, "bg_scroll_serve_down"),
                             (REQUEST_RIGHT, "bg_scroll_serve_right"),
                             (REQUEST_LEFT, "bg_scroll_serve_left")):
        asm.emit(tst_b_abs_l(request), branch_over(BEQ_W, BSR_W_LEN)).call(handler)
    return asm.emit(RTS).bytes()


def _raise_requests_body():
    """$d28. Each axis is `move.w`/`subi.w` and a THREE-way branch — raise one byte, raise the
    other, or neither — with the negative side alone negated, which is what makes both distances
    come back positive. The two axes are not spelt the same way round: the vertical one tests `bgt`
    first and joins through a third arm, the horizontal one tests `blt` first and returns outright."""
    up = st_abs_l(RAISED_V_UP) + neg_w_dn(D0)
    down = st_abs_l(RAISED_V_DOWN)
    to_down = branch(BRA_W, down)
    to_neither = branch(BRA_W, up, to_down, down)
    to_up = branch(BLT_W, to_neither)
    vertical = (move_w_abs_l_dn(D0, FOLLOW_Y) + subi_w_dn(D0, CENTRE_Y)
                + branch(BGT_W, to_up, to_neither, up, to_down)
                + to_up + to_neither + up + to_down + down)

    left = st_abs_l(RAISED_H_LEFT) + neg_w_dn(D1) + RTS
    right = st_abs_l(RAISED_H_RIGHT) + RTS
    to_right = branch(BGT_W, RTS, left)
    horizontal = (move_w_abs_l_dn(D1, FOLLOW_X) + subi_w_dn(D1, CENTRE_X)
                  + branch(BLT_W, to_right, RTS) + to_right + RTS + left + right)
    return vertical + horizontal


def _emit_drain(asm, count_word, raised, request):
    """One of bg_scroll_run_queue's two drains: serve the raised PAIR once per owed step, closing
    the loop with a `bra.s` back over the whole body."""
    test = tst_w_abs_l(count_word)
    consume = subq_w_abs_l(1, count_word) + move_w_abs_l_abs_l(raised, request)
    asm.emit(test)
    # Only the LENGTH of the loop's own `beq` is needed to place what follows it, which is what
    # makes the two branches solvable at all: each is fixed-width whatever it spans.
    call = bsr_w(asm.at + BRANCH_W_LEN + len(consume), leaf.entry_of("bg_scroll_serve_requests"))
    close = bra_s_over(len(test) + BRANCH_W_LEN + len(consume) + len(call))
    asm.emit(branch(BEQ_W, consume, call, close), consume, call, close)


def _run_queue_main(at):
    """Everything under bg_scroll_run_queue's `tst.w $d76` gate except the bypass arm."""
    asm = _Assembler(at)
    asm.call("bg_scroll_raise_requests")
    # `asr.w #1` on each distance: they are in pixels and one step is SCROLL_STEP of them.
    asm.emit(shift_imm_dn(ASR_W_IMM, 1, D0), shift_imm_dn(ASR_W_IMM, 1, D1),
             move_w_dn_abs_l(D0, QUEUE_V_COUNT), move_w_dn_abs_l(D1, QUEUE_H_COUNT))
    _emit_drain(asm, QUEUE_H_COUNT, RAISED_H, REQUEST_LEFT)
    _emit_drain(asm, QUEUE_V_COUNT, RAISED_V, REQUEST_UP)
    # Two `clr.l`, each covering a PAIR of words.
    return asm.emit(clr_l_abs_l(RAISED_V), clr_l_abs_l(QUEUE_H_COUNT), RTS).bytes()


def _run_queue_body():
    """$7522."""
    entry = leaf.entry_of("bg_scroll_run_queue")
    gate = tst_w_abs_w(FOLLOW_FROZEN)
    main = _run_queue_main(entry + len(gate) + BRANCH_W_LEN)
    bypass = _Assembler(entry + len(gate) + BRANCH_W_LEN + len(main))
    bypass.call("bg_scroll_serve_requests").emit(RTS)
    return gate + branch(BNE_W, main) + main + bypass.bytes()


# --- the consumer tier's bodies -------------------------------------------------------------------
# The sixteen copy variants are ONE pattern with one number in it, which is the claim src/scroll.c
# rests on. It is not assumed: every variant's whole body is assembled from the pattern below and
# pinned against the image, so a family member that differed anywhere would fail its own entry pin.

def variant_name(column):
    """../names.txt's name for the variant WB_BG_SCROLL_X == ``column`` selects."""
    return f"bg_scroll_copy_x{column}"


def _blit_variant_half(column, counter):
    """One half of a copy variant: `dbf` scanlines of BLIT_LONGWORDS `move.l (a0)+,(a1)+`, split
    about the source row's 128-byte ring seam wherever ``column`` puts it.

    The two runs and their `lea`s are the ONLY thing that varies across the sixteen. A column whose
    copy still fits the row (0 and 1) has no seam and closes with a bare `addq.l #8,a0`; every other
    one rewinds a whole row mid-scanline and closes with the `lea 136(a0),a0` that is that rewind
    plus the same 8.
    """
    before_seam = ROW_LONGWORDS - CELL_LONGWORDS * column
    copy = MOVE_L_POSTINC_A0_POSTINC_A1
    to_next_screen_row = lea_d16(A1, SCREEN_LINE - BLIT_ROW_BYTES)
    if before_seam >= BLIT_LONGWORDS:
        body = copy * BLIT_LONGWORDS + to_next_screen_row + addq_l_imm_an(CELL_BYTES, A0)
    else:
        body = (copy * before_seam
                + lea_d16(A0, -BUFFER_LINE)
                + copy * (BLIT_LONGWORDS - before_seam)
                + to_next_screen_row
                + lea_d16(A0, BUFFER_LINE + CELL_BYTES))
    return body + dbf(counter, body)


def _blit_variant_body(column):
    """$83b6, $8450, $84ea ... $8d58 — one of the sixteen. Two halves about the source BUFFER's own
    end, with the `tst.w d6 / bpl / rts` between them that is how "no second half" is spelt."""
    between = (tst_w_dn(D6) + branch(BPL_W, RTS) + RTS + lea_d16(A0, -BUFFER_LEN))
    return (_blit_variant_half(column, D7) + between + _blit_variant_half(column, D6) + RTS)


def _blit_dispatcher_body():
    """$82f8 — everything before the two `jmp (a2)`, which are its only exits.

    One screen address, one source address, one table entry and the two `dbf` counts. The counts are
    where the two arms part: below BLIT_WRAP_ROW the window fits the buffer and d6 is loaded with
    the "no second half" marker outright; at or above it both halves are computed from the ring row.
    """
    fits = (move_w_imm_dn(D6, BLIT_NO_SECOND_HALF)
            + move_w_imm_dn(D7, BLIT_SCANLINES - 1)
            + jmp_ind(A2))
    return (movea_l_abs_w(A1, SCREEN_BACK) + adda_w_imm_an(BLIT_SCREEN_ORIGIN, A1)
            + lea_abs_l(A0, BUFFER_BASE)
            + move_w_abs_l_dn(D0, PHASE) + mulu_w_imm_dn(D0, BUFFER_PHASE_STRIDE)
            + lea_indexed(A0, D0, longword_index=True)
            + move_w_abs_l_dn(D0, SCROLL_Y)
            + shift_imm_dn(ASL_W_IMM, _shift_for(BUFFER_LINE), D0) + lea_indexed(A0, D0)
            + move_w_abs_l_dn(D0, SCROLL_X) + move_w_dn_dn(D1, D0)
            + shift_imm_dn(ASL_W_IMM, _shift_for(CELL_BYTES), D0) + lea_indexed(A0, D0)
            + lea_abs_l(A2, BLIT_TABLE)
            + shift_imm_dn(ASL_W_IMM, _shift_for(LONGWORD_LEN), D1) + movea_l_indexed(A2, A2, D1)
            + move_w_abs_l_dn(D6, SCROLL_Y) + subi_w_dn(D6, BLIT_WRAP_ROW)
            + branch(BPL_W, fits) + fits
            + move_w_imm_dn(D7, BUFFER_SCANLINES) + sub_w_abs_l_dn(D7, SCROLL_Y)
            + move_w_imm_dn(D6, BLIT_SCANLINES - 1) + sub_w_dn_dn(D6, D7)
            + subq_w_imm_dn(1, D7) + jmp_ind(A2))


VERTICAL_STEP_BODIES = {"up": _vertical_step_body(down=False),
                        "down": _vertical_step_body(down=True)}
ROW_FILL_BODIES = {"top": _row_fill_body(bottom=False), "bottom": _row_fill_body(bottom=True)}

ENTRY_BYTES = {
    "bg_scroll_fill_right_column": FILL_BODIES["right"],
    "bg_scroll_fill_left_column": FILL_BODIES["left"],
    "bg_scroll_step_right": STEP_BODIES["right"],
    "bg_scroll_step_left": STEP_BODIES["left"],
    "bg_scroll_serve_right": SERVE_BODIES["right"],
    "bg_scroll_serve_left": SERVE_BODIES["left"],
    "bg_scroll_step_up": VERTICAL_STEP_BODIES["up"],
    "bg_scroll_step_down": VERTICAL_STEP_BODIES["down"],
    "bg_scroll_fill_top_row": ROW_FILL_BODIES["top"],
    "bg_scroll_fill_bottom_row": ROW_FILL_BODIES["bottom"],
    "bg_scroll_preshift_rows": _preshift_body(),
    "bg_scroll_serve_up": _vertical_serve_body("bg_scroll_serve_up", REQUEST_UP,
                                               "bg_scroll_step_up", "bg_scroll_fill_top_row"),
    "bg_scroll_serve_down": _vertical_serve_body("bg_scroll_serve_down", REQUEST_DOWN,
                                                 "bg_scroll_step_down",
                                                 "bg_scroll_fill_bottom_row"),
    "bg_scroll_serve_requests": _serve_requests_body(),
    "bg_scroll_raise_requests": _raise_requests_body(),
    "bg_scroll_run_queue": _run_queue_body(),
    "bg_scroll_blit": _blit_dispatcher_body(),
    **{variant_name(column): _blit_variant_body(column) for column in range(BLIT_VARIANTS)},
}
RECONSTRUCTED_ROUTINES = 17 + BLIT_VARIANTS


# --- glue -----------------------------------------------------------------------------------------
_FILL = {name: leaf.image_glue(name) for name in
         ("bg_scroll_fill_right_column", "bg_scroll_fill_left_column",
          "bg_scroll_serve_right", "bg_scroll_serve_left")}
_STEP = {name: leaf.bind(name, leaf.IMAGE_ARG, ctypes.c_int) for name in
         ("bg_scroll_step_right", "bg_scroll_step_left")}


def _step_glue(name, seen):
    """Run a step and record the skip flag it returned, so a case can compare it against what the
    ORACLE did with its own return address."""
    def call(_lib, image):
        seen.append(_STEP[name](image))
        return seen[-1]
    return call


def _oracle_skipped(info, skip):
    """Whether the ORIGINAL consumed its caller's `bsr`s, read off its own stack.

    `emu.run` writes the sentinel AT A7 rather than below it, so a step that did `addq.l #n,(a7)`
    has rewritten that longword and one that returned normally never wrote there at all. ``skip`` is
    the step's own distance, so a routine that consumed the WRONG NUMBER of calls fails here rather
    than being read as a skip.
    """
    if not all(RETURN_SLOT + i in info["writes"] for i in range(LONGWORD_LEN)):
        return False
    left = leaf.read_int(info, RETURN_SLOT, LONGWORD_LEN, "the step's own return address")
    assert left == emu.SENTINEL + skip, (
        f"the original rewrote its return address to {left:#x}, which is neither the oracle's "
        f"sentinel {emu.SENTINEL:#x} nor that plus the {skip}-byte skip")
    return True


# --- the entry pins -------------------------------------------------------------------------------

def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    ("bg_scroll_fill_right_column", 678),
    ("bg_scroll_fill_left_column", 658),
    ("bg_scroll_step_right", 106),
    ("bg_scroll_step_left", 116),
    ("bg_scroll_serve_right", 16),
    ("bg_scroll_serve_left", 16),
    ("bg_scroll_step_up", 414),
    ("bg_scroll_step_down", 420),
    ("bg_scroll_fill_top_row", 220),
    ("bg_scroll_fill_bottom_row", 238),
    ("bg_scroll_preshift_rows", 228),
    ("bg_scroll_serve_up", 20),
    ("bg_scroll_serve_down", 20),
    ("bg_scroll_serve_requests", 58),
    ("bg_scroll_raise_requests", 78),
    ("bg_scroll_run_queue", 112),
    ("bg_scroll_blit", 110),
    ("bg_scroll_copy_x0", 154),
    ("bg_scroll_copy_x1", 154),
    ("bg_scroll_copy_x2", 166),
    ("bg_scroll_copy_x3", 166),
    ("bg_scroll_copy_x4", 166),
    ("bg_scroll_copy_x5", 166),
    ("bg_scroll_copy_x6", 166),
    ("bg_scroll_copy_x7", 166),
    ("bg_scroll_copy_x8", 166),
    ("bg_scroll_copy_x9", 166),
    ("bg_scroll_copy_x10", 166),
    ("bg_scroll_copy_x11", 166),
    ("bg_scroll_copy_x12", 166),
    ("bg_scroll_copy_x13", 166),
    ("bg_scroll_copy_x14", 166),
    ("bg_scroll_copy_x15", 166),
], ids=lambda v: v if isinstance(v, str) else f"{v}B")
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    """The pins above would still pass on a PREFIX of a routine. These are the sizes the Ghidra
    function table gives (../out/hw_scan.tsv), so a body reconstructed one instruction short fails
    here instead of leaving the tail unpinned."""
    assert len(ENTRY_BYTES[name]) == size, (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {size} the scan records")


def test_the_split_tables_are_the_pairs_the_fills_assume():
    """bg_scroll_col_split_table is the game's own data and every fill's length comes out of it, so
    the shape the model and src/scroll.c both rely on is asserted rather than assumed: entry k is
    (BUFFER_TILE_ROWS - 1 - k, k - 1), and the two `dbf` counts therefore always draw the buffer's
    eleven tile rows exactly once."""
    for index in range(COL_SPLIT_ENTRIES):
        at = COL_SPLIT_TABLE + index * LONGWORD_LEN
        first = u16(harness.BASE_IMAGE, at)
        second = s16(u16(harness.BASE_IMAGE, at + STATE_WORD_LEN))
        assert first == BUFFER_TILE_ROWS - 1 - index, f"entry {index}'s first count is {first}"
        assert second == index - 1, f"entry {index}'s second count is {second}"
        assert (first + 1) + (second + 1) == BUFFER_TILE_ROWS, (
            f"entry {index}'s two halves draw {(first + 1) + (second + 1)} tile rows, not the "
            f"buffer's {BUFFER_TILE_ROWS}")


def test_the_edge_masks_are_the_shifts_the_phase_names():
    """The eight words at bg_scroll_edge_masks, which decide how much of a cell a fill keeps."""
    assert u16(harness.BASE_IMAGE, EDGE_MASK_TABLE) == 0, (
        "phase 0's mask is not $0000 — src/scroll.c's whole-cell redraw depends on it")
    for phase in range(SCROLL_STEP, PHASE_MASK + 1, SCROLL_STEP):
        expected = (0xffff << phase) & 0xffff
        assert u16(harness.BASE_IMAGE, EDGE_MASK_TABLE + phase) == expected, (
            f"phase {phase}'s mask is not {expected:#06x}")


# --- the column fills -----------------------------------------------------------------------------
# Each case names the three words that place the column: the phase (which buffer, which mask, how
# far the tiles rotate), the coarse scroll row (where the ring wrap falls) and bg_scroll_x (which
# cell of the 128-byte row, and whether the second cell wraps out of it).
FILL_CASES = [
    ("phase0", 0, 0, 5),
    ("phase2", 2, 0, 5),
    ("phase8", 8, 0, 5),
    ("phase14", PHASE_LAST, 0, 5),
    ("x1", 8, 1, 5),
    ("x15", 8, PHASE_MASK, 5),
    ("coarse0", 8, 3, 0),
    ("coarse1", 8, 3, 1),          # the second half's count is exactly 0: one tile row

    ("coarse10", 8, 3, COL_SPLIT_ENTRIES - 1),
    ("phase0-x0-coarse0", 0, 0, 0),
    ("phase0-x1-coarse10", 0, 1, COL_SPLIT_ENTRIES - 1),
    ("phase14-x15-coarse7", PHASE_LAST, PHASE_MASK, 7),
]


def _run_fill(edge, phase, scroll_x, coarse, salt):
    pokes = _scroll_pokes(phase, scroll_x, coarse, salt=salt)
    image = harness.make_image(pokes)
    expected = _model_fill(image, edge)
    allowed = merge_bands(expected)

    what = f"{edge.routine} phase={phase} x={scroll_x} coarse={coarse}"
    info = leaf.run(edge.routine, _FILL[edge.routine], allowed, what,
                    regs={"_pokes": pokes}, max_insns=FILL_INSN_CAP)

    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {len(written)} bytes against the model's "
        f"{len(expected)} — first difference at {min(set(written) ^ set(expected)):#x}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")
    return info


@pytest.mark.parametrize("edge", sorted(EDGES), ids=sorted(EDGES))
@pytest.mark.parametrize("case,phase,scroll_x,coarse", FILL_CASES,
                         ids=[case[0] for case in FILL_CASES])
def test_a_column_fill_draws_the_cells_the_geometry_names(edge, case, phase, scroll_x, coarse):
    _run_fill(EDGES[edge], phase, scroll_x, coarse, salt=case_salt(case))


@pytest.mark.parametrize("edge", sorted(EDGES), ids=sorted(EDGES))
def test_a_column_fill_touches_exactly_one_buffers_worth_of_scanlines(edge):
    """The two halves always cover the buffer once over — 176 scanlines of one 8-byte cell for the
    cursor that is ORed and one for the cursor that is overwritten, plus the count scratch."""
    phase = 8
    info = _run_fill(EDGES[edge], phase=phase, scroll_x=5, coarse=4, salt=7)
    cells = sorted(a for a in program_writes(info) if a >= BUFFER_BASE)
    scanlines = BUFFER_TILE_ROWS * TILE_ROWS
    # TWO cells per scanline, not three: the clear walks the same cell the tile loop ORs into, and
    # only the overwritten one is a second address. That the two coincide is the whole reason the
    # masking is a preparation for the OR and not a separate region.
    assert len(cells) == 2 * scanlines * CELL_BYTES, (
        f"{len(cells)} buffer bytes, not the {2 * scanlines * CELL_BYTES} that {scanlines} "
        f"scanlines of one cleared-and-ORed cell and one overwritten cell give")
    assert min(cells) >= BUFFER_BASE + phase * BUFFER_PHASE_STRIDE
    assert max(cells) < BUFFER_BASE + phase * BUFFER_PHASE_STRIDE + BUFFER_LEN


# --- the position steps ---------------------------------------------------------------------------
# `pending` is the half-rate latch: the right step moves only when it is NEGATIVE and the left one
# only when it is ZERO, which is why every case names it.
STEP_STATE = dict(pos_x=0x40, limit_x=0x100, pending=PENDING_SET, phase=4, scroll_x=5,
                  map_cursor=MAP_CURSOR_SEED, row_offset=0x28)


def _step_pokes(**overrides):
    state = dict(STEP_STATE, **overrides)
    return {
        POS_X: word(state["pos_x"]),
        LIMIT_X: word(state["limit_x"]),
        PENDING: word(state["pending"]),
        PHASE: word(state["phase"]),
        SCROLL_X: word(state["scroll_x"]),
        MAP_CURSOR: word(state["map_cursor"]),
        ROW_BYTE_OFFSET: word(state["row_offset"]),
    }


STEP_WRITABLE = (POS_X, PENDING, PHASE, SCROLL_X, MAP_CURSOR, ROW_BYTE_OFFSET)


def _run_step(name, pokes, what):
    seen = []
    skip = STEP_SKIP_BYTES[name]
    allowed = [(addr, STATE_WORD_LEN) for addr in STEP_WRITABLE] + [(RETURN_SLOT, LONGWORD_LEN)]
    info = leaf.run(name, _step_glue(name, seen), allowed, what, regs={"_pokes": dict(pokes)},
                    max_insns=STEP_INSN_CAP, stop_pc=emu.SENTINEL + skip)
    skipped = _oracle_skipped(info, skip)
    assert bool(seen[0]) == skipped, (
        f"{what}: the reconstruction returned {seen[0]} while the original "
        f"{'skipped' if skipped else 'did not skip'} its caller's fill")
    return info, skipped


def _final(image, pokes, info, addr):
    """The word the original left at ``addr`` — from its write set when it wrote there, and from the
    seeded image when it did not, so a case can state the value either way."""
    if all(addr + i in info["writes"] for i in range(STATE_WORD_LEN)):
        return leaf.read_int(info, addr, STATE_WORD_LEN, "a scroll word")
    return u16(image, addr)


@pytest.mark.parametrize("name,pokes_kw,skips", [
    ("bg_scroll_step_right", dict(pos_x=0x100, limit_x=0x100), True),
    ("bg_scroll_step_right", dict(pos_x=0xfe, limit_x=0x100), False),
    ("bg_scroll_step_left", dict(pos_x=0), True),
    ("bg_scroll_step_left", dict(pos_x=2), False),
], ids=["right-at-limit", "right-below-limit", "left-at-zero", "left-above-zero"])
def test_a_step_consumes_its_callers_fill_exactly_at_its_own_boundary(name, pokes_kw, skips):
    pokes = _step_pokes(**pokes_kw)
    _, skipped = _run_step(name, pokes, f"{name} {pokes_kw}")
    assert skipped is skips


@pytest.mark.parametrize("name,pending,moves", [
    ("bg_scroll_step_right", PENDING_SET, True),
    ("bg_scroll_step_right", 0, False),
    ("bg_scroll_step_right", 1, False),
    ("bg_scroll_step_left", 0, True),
    ("bg_scroll_step_left", PENDING_SET, False),
    ("bg_scroll_step_left", 1, False),
], ids=["right-armed", "right-disarmed", "right-positive-latch",
        "left-disarmed", "left-armed", "left-positive-latch"])
def test_the_half_rate_latch_decides_whether_the_position_moves(name, pending, moves):
    """The two tests are not complements — `bmi` against `beq` — so a positive latch behaves
    differently in the two directions, and both cases say which."""
    pokes = _step_pokes(pending=pending)
    image = harness.make_image(pokes)
    info, skipped = _run_step(name, pokes, f"{name} pending={pending:#x}")
    assert not skipped
    step = SCROLL_STEP if name.endswith("right") else -SCROLL_STEP
    expected = (STEP_STATE["pos_x"] + step) if moves else STEP_STATE["pos_x"]
    assert _final(image, pokes, info, POS_X) == expected
    if not moves:
        assert _final(image, pokes, info, PENDING) == (PENDING_SET if name.endswith("right") else 0)


@pytest.mark.parametrize("phase,x,expect_phase,expect_x,expect_row_offset", [
    (4, 5, 6, 5, STEP_STATE["row_offset"]),
    (PHASE_LAST, 5, 0, 6, STEP_STATE["row_offset"] + CELL_BYTES),
    (PHASE_LAST, PHASE_MASK, 0, 0, 0),
], ids=["mid-cell", "carry-into-the-next-cell", "carry-that-wraps-the-row"])
def test_the_right_step_carries_the_phase_into_the_cell_and_the_cell_into_the_row(
        phase, x, expect_phase, expect_x, expect_row_offset):
    pokes = _step_pokes(phase=phase, scroll_x=x)
    image = harness.make_image(pokes)
    info, _ = _run_step("bg_scroll_step_right", pokes, f"right phase={phase} x={x}")
    assert _final(image, pokes, info, PHASE) == expect_phase
    assert _final(image, pokes, info, SCROLL_X) == expect_x
    assert _final(image, pokes, info, ROW_BYTE_OFFSET) == expect_row_offset
    expected_cursor = MAP_CURSOR_SEED + (1 if expect_phase == 0 else 0)
    assert _final(image, pokes, info, MAP_CURSOR) == expected_cursor


@pytest.mark.parametrize("phase,x,row_offset,expect_phase,expect_x,expect_row_offset", [
    (4, 5, 0x28, 2, 5, 0x28),
    (0, 5, 0x28, PHASE_LAST, 4, 0x20),
    (0, 1, 0x08, PHASE_LAST, 0, 0),
    (0, 5, 0x00, PHASE_LAST, 4, BUFFER_LINE - CELL_BYTES),
], ids=["mid-cell", "borrow-into-the-previous-cell", "borrow-that-wraps-the-row",
        "borrow-that-underflows-the-row-offset"])
def test_the_left_step_borrows_the_phase_from_the_cell_and_masks_the_row_offset(
        phase, x, row_offset, expect_phase, expect_x, expect_row_offset):
    """The last case is the asymmetry: the left step masks bg_scroll_row_byte_offset to $7f, so a
    borrow from zero lands at $78 rather than at $fff8, where the right step's add is unmasked."""
    # The latch has to be DISARMED for the left step to move: it is the mirror of the right
    # step's, which moves only while it is armed (test_the_half_rate_latch... above).
    pokes = _step_pokes(phase=phase, scroll_x=x, row_offset=row_offset, pending=0)
    image = harness.make_image(pokes)
    info, _ = _run_step("bg_scroll_step_left", pokes, f"left phase={phase} x={x}")
    assert _final(image, pokes, info, PHASE) == expect_phase
    assert _final(image, pokes, info, SCROLL_X) == expect_x
    assert _final(image, pokes, info, ROW_BYTE_OFFSET) == expect_row_offset
    expected_cursor = MAP_CURSOR_SEED - (1 if expect_phase == PHASE_LAST else 0)
    assert _final(image, pokes, info, MAP_CURSOR) == expected_cursor


# --- the request handlers -------------------------------------------------------------------------

def _serve_pokes(edge, phase, scroll_x, coarse, pending, pos_x, salt):
    pokes = _scroll_pokes(phase, scroll_x, coarse, salt=salt)
    pokes.update(_step_pokes(pending=pending, pos_x=pos_x, phase=phase, scroll_x=scroll_x))
    pokes[edge.request] = b"\xff"
    return pokes


@pytest.mark.parametrize("edge", sorted(EDGES), ids=sorted(EDGES))
@pytest.mark.parametrize("armed", [True, False], ids=["moves-and-fills", "latches-only"])
def test_a_request_is_consumed_whether_or_not_the_step_moves(edge, armed):
    """The request byte is cleared before anything else happens, so it goes down even on the pass
    that only arms the latch — and on that pass the fill still runs, because only the position
    boundary makes a step skip it."""
    served = EDGES[edge]
    pending = PENDING_SET if served is RIGHT else 0
    if not armed:
        pending = 0 if served is RIGHT else PENDING_SET
    pokes = _serve_pokes(served, phase=8, scroll_x=5, coarse=4, pending=pending, pos_x=0x40,
                         salt=11 + armed)
    image = harness.make_image(pokes)
    expected = {}
    _model_serve_horizontal(bytearray(image), expected, served)
    allowed = merge_bands(expected)
    what = f"{served.serve} armed={armed}"
    info = leaf.run(served.serve, _FILL[served.serve], allowed, what,
                    regs={"_pokes": pokes}, max_insns=SERVE_INSN_CAP)
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: write set differs at {min(set(written) ^ set(expected)):#x}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not {expected[addr]:#04x}")
    assert written[served.request] == 0


@pytest.mark.parametrize("edge", sorted(EDGES), ids=sorted(EDGES))
def test_a_request_at_the_scrolls_boundary_clears_its_byte_and_draws_nothing(edge):
    """The skip arm end to end: the step consumes the `bsr`, so the ONLY byte the pass writes is the
    request it consumed. The buffer is seeded exactly as the moving cases seed it, so a fill that
    ran anyway would show up as a write set two hundred times the size."""
    served = EDGES[edge]
    pos_x = STEP_STATE["limit_x"] if served is RIGHT else 0
    pokes = _serve_pokes(served, phase=8, scroll_x=5, coarse=4, pending=PENDING_SET, pos_x=pos_x,
                         salt=23)
    info = leaf.run(served.serve, _FILL[served.serve], [(served.request, 1)],
                    f"{served.serve} at the boundary", regs={"_pokes": pokes},
                    max_insns=SERVE_INSN_CAP)
    written = program_writes(info)
    assert set(written) == {served.request}
    assert written[served.request] == 0


def _model_horizontal_step(staged, out, edge):
    """$79d2 / $795e on the staged image. Returns True when the step consumed its caller's `bsr`.

    Written out per direction rather than parametrised, because the two are NOT mirror images: the
    latch tests are `bmi` against `beq`, the phase wraps through the nibble mask one way and is
    written outright the other, and only the left step masks the row offset.
    """
    if edge is RIGHT:
        if u16(staged, POS_X) == u16(staged, LIMIT_X):
            return True
        if s16(u16(staged, PENDING)) >= 0:
            _put(out, staged, PENDING, PENDING_SET)
            return False
        _put(out, staged, POS_X, (u16(staged, POS_X) + SCROLL_STEP) & 0xffff)
        phase = (u16(staged, PHASE) + SCROLL_STEP) & PHASE_MASK
        _put(out, staged, PHASE, phase)
        if phase != 0:
            return False
        _put(out, staged, ROW_BYTE_OFFSET, (u16(staged, ROW_BYTE_OFFSET) + CELL_BYTES) & 0xffff)
        _put(out, staged, MAP_CURSOR, (u16(staged, MAP_CURSOR) + 1) & 0xffff)
        column = (u16(staged, SCROLL_X) + 1) & PHASE_MASK
    else:
        if u16(staged, POS_X) == 0:
            return True
        if u16(staged, PENDING) != 0:
            _put(out, staged, PENDING, 0)
            return False
        _put(out, staged, POS_X, (u16(staged, POS_X) - SCROLL_STEP) & 0xffff)
        phase = (u16(staged, PHASE) - SCROLL_STEP) & 0xffff
        if s16(phase) >= 0:
            _put(out, staged, PHASE, phase & PHASE_MASK)
            return False
        _put(out, staged, PHASE, PHASE_LAST)
        _put(out, staged, MAP_CURSOR, (u16(staged, MAP_CURSOR) - 1) & 0xffff)
        _put(out, staged, ROW_BYTE_OFFSET,
             (u16(staged, ROW_BYTE_OFFSET) - CELL_BYTES) & ROW_OFFSET_MASK)
        column = (u16(staged, SCROLL_X) - 1) & PHASE_MASK

    _put(out, staged, SCROLL_X, column)
    if column == 0:
        _put(out, staged, ROW_BYTE_OFFSET, 0)
    return False


def _model_serve_horizontal(staged, out, edge):
    """$75fc / $760c: the step's own words, then the fill's ON THE STEP'S OUTPUT — a serve that
    stepped and then filled from the pre-step phase would otherwise pass."""
    # The request is a BYTE (`clr.b`), unlike every other write below — a word here would claim the
    # pass also touched the byte after it, which for $8233 is bg_scroll_tile_row.
    _put8(out, staged, edge.request, 0)
    if _model_horizontal_step(staged, out, edge):
        return
    _apply(out, staged, _model_fill(staged, edge))


def test_the_shipped_tile_bitmaps_are_the_sixteen_the_header_names():
    """WHICH tiles a case may draw from, established rather than assumed.

    The region between bg_tile_bitmaps and bg_tile_index holds 148 bitmaps and all but sixteen of
    them are ZERO in the .PRG — the game fills the rest at runtime, as it does the map. A case that
    drew from a zeroed tile would rotate zeros and pin nothing, so every case seeds the index table
    with the shipped fifteen, and this is the reading that makes those two numbers right.
    """
    region_tiles = (TILE_INDEX_TABLE - TILE_BITMAPS) // TILE_BITMAP_LEN
    shipped = [tile for tile in range(region_tiles)
               if any(harness.BASE_IMAGE[TILE_BITMAPS + tile * TILE_BITMAP_LEN:][:TILE_BITMAP_LEN])]
    assert shipped == list(range(TILE_SHIPPED_FIRST, TILE_SHIPPED_FIRST + TILE_SHIPPED_COUNT)), (
        f"the non-zero bitmaps in the .PRG are {shipped}, not the "
        f"{TILE_SHIPPED_COUNT} from {TILE_SHIPPED_FIRST} include/wonderboy.h records")


# ==================================================================================================
# THE VERTICAL HALF, AND THE TIER ABOVE BOTH HALVES
#
# Same discipline as above and two additions the shape forces:
#
#   * A VERTICAL CASE SEEDS ALL EIGHT BUFFERS (`_scroll_pokes(whole_region=True)`), because
#     bg_scroll_preshift_rows walks a freshly drawn row through every copy — a pass that shifted
#     one copy too far, or chained by the wrong stride, lands on seeded bytes rather than on zeros.
#   * A SERVE AND EVERYTHING ABOVE IT RUNS WITHOUT THE POISON PASS. The vertical step writes the
#     sixteen bg_scroll_buffer_rows POINTERS and the fill under it then draws THROUGH them, so
#     inverting the step's outputs in the input image (which is what the attribution pass does)
#     would aim the fill at an address the run then stores to — the case leaf.run's `poison=False`
#     exists for. The step, the fills and the pre-shift are all run WITH it: none of them stores
#     through a value it also writes.
# ==================================================================================================

# The vertical seeds. The map cursor starts two map rows in so the top fill's step-back (which pulls
# the cursor a whole row UP) still lands inside the seeded map, and the bottom fill's own row —
# BOTTOM_ROW_STRIDES further down — still lands inside it too.
MAP_CURSOR_SEED_V = 2 * MAP_STRIDE_SEED
VERTICAL_STATE = dict(pos_y=0x40, limit_y=0x100, y=0x20, y_bottom=0x9e, tile_row=0x30,
                      row_offset=0x28, scroll_x=5)


def _buffer_row(copy, row):
    """The pointer a ring cursor at ``row`` must hold for pre-shifted copy ``copy``."""
    return BUFFER_BASE + copy * BUFFER_LEN + row * BUFFER_LINE


def _vertical_pokes(salt, **overrides):
    """The image a vertical case runs on: the horizontal seeding (which the map, the tile index and
    all eight buffers come from) plus this half's own words and its sixteen row pointers, seeded
    CONSISTENTLY — pointer = buffer + row * 128, the invariant the steps maintain."""
    state = dict(VERTICAL_STATE, **overrides)
    pokes = _scroll_pokes(phase=state.get("phase", 8), scroll_x=state["scroll_x"],
                          y_coarse=state["y"] >> Y_COARSE_SHIFT,
                          map_cursor=state.get("map_cursor", MAP_CURSOR_SEED_V),
                          salt=salt, whole_region=True)
    pokes.update({
        POS_Y: word(state["pos_y"]),
        LIMIT_Y: word(state["limit_y"]),
        SCROLL_Y: word(state["y"]),
        SCROLL_Y_BOTTOM: word(state["y_bottom"]),
        TILE_ROW: word(state["tile_row"]),
        ROW_BYTE_OFFSET: word(state["row_offset"]),
        BUFFER_ROWS: b"".join(
            longword(_buffer_row(copy, state["y" if member == BUFFER_ROW_TOP else "y_bottom"]))
            for copy in range(BUFFERS)
            for member in (BUFFER_ROW_TOP, BUFFER_ROW_BOTTOM)),
    })
    return pokes


# --- the vertical models --------------------------------------------------------------------------

def _model_row_cursor(staged, out, row_word, first_pointer, down):
    """One of the two ring cursors a vertical step moves, with its eight buffer-row pointers."""
    wrap_from, wrap_to = (SCROLL_Y_LAST, 0) if down else (0, SCROLL_Y_LAST)
    step = SCROLL_STEP if down else -SCROLL_STEP
    if u16(staged, row_word) == wrap_from:
        _put(out, staged, row_word, wrap_to)
        for copy in range(BUFFERS):
            _put32(out, staged, first_pointer + copy * BUFFER_ROW_PAIR,
                   _buffer_row(copy, wrap_to))
        return
    _put(out, staged, row_word, (u16(staged, row_word) + step) & 0xffff)
    for copy in range(BUFFERS):
        at = first_pointer + copy * BUFFER_ROW_PAIR
        _put32(out, staged, at, (_u32(staged, at) + step * BUFFER_LINE) & 0xffffffff)


def _model_vertical_step(staged, out, down):
    """$761c / $77ba. Returns True when the step consumed its caller's two `bsr`s."""
    boundary = u16(staged, LIMIT_Y) if down else 0
    if u16(staged, POS_Y) == boundary:
        return True
    step = SCROLL_STEP if down else -SCROLL_STEP
    _put(out, staged, POS_Y, (u16(staged, POS_Y) + step) & 0xffff)
    _model_row_cursor(staged, out, SCROLL_Y, BUFFER_ROWS + BUFFER_ROW_TOP, down)
    _model_row_cursor(staged, out, SCROLL_Y_BOTTOM, BUFFER_ROWS + BUFFER_ROW_BOTTOM, down)
    _put(out, staged, Y_COARSE, (s16(u16(staged, SCROLL_Y)) >> Y_COARSE_SHIFT) & 0xffff)
    return False


def _model_row_fill(staged, out, bottom):
    """$7a3e / $7b1a. Returns the original's d0 — the last tile's byte offset under the marker word
    the fill stamps into its low half, which is what bg_scroll_preshift_rows is handed."""
    if not bottom:
        # The tile row steps BACK first, and a step past the top of the bitmap pulls the map cursor
        # a whole map row up. The SIGN is tested before the mask, so the wrap and the pull are the
        # same test read two ways.
        row = (u16(staged, TILE_ROW) - TILE_ROW_STEP) & 0xffff
        if s16(row) < 0:
            _put(out, staged, MAP_CURSOR,
                 (u16(staged, MAP_CURSOR) - u16(staged, MAP_ROW_STRIDE)) & 0xffff)
        _put(out, staged, TILE_ROW, row & TILE_ROW_MASK)
        map_offset = u16(staged, MAP_CURSOR)
        pointer = BUFFER_ROWS + BUFFER_ROW_TOP
    else:
        map_offset = (u16(staged, MAP_CURSOR)
                      + BOTTOM_ROW_STRIDES * u16(staged, MAP_ROW_STRIDE)) & 0xffff
        pointer = BUFFER_ROWS + BUFFER_ROW_BOTTOM

    dest = (_u32(staged, pointer) + s16(u16(staged, ROW_BYTE_OFFSET))) & 0xffffffff
    map_at = (MAP_DATA_ROW + s16(map_offset)) & 0xffffffff
    counts = (ROW_SPLIT_TABLE + s16((u16(staged, SCROLL_X) * LONGWORD_LEN) & 0xffff)) & 0xffffffff
    tile_byte = u16(staged, TILE_ROW)

    def half(dest, map_at, cells):
        drawn = 0
        for _ in range(cells + 1):
            tile = u16(staged, TILE_INDEX_TABLE + staged[map_at] * STATE_WORD_LEN)
            map_at = (map_at + 1) & 0xffffffff
            drawn = tile * TILE_BITMAP_LEN
            source = (TILE_BITMAPS + drawn + s16(tile_byte)) & 0xffffffff
            for scanline in range(ROW_FILL_SCANLINES):
                for byte in range(0, CELL_BYTES, LONGWORD_LEN):
                    _put32(out, staged, (dest + scanline * BUFFER_LINE + byte) & 0xffffffff,
                           _u32(staged, (source + scanline * CELL_BYTES + byte) & 0xffffffff))
            dest = (dest + CELL_BYTES) & 0xffffffff
        return dest, map_at, drawn

    dest, map_at, drawn = half(dest, map_at, u16(staged, counts))
    dest = (dest - BUFFER_LINE) & 0xffffffff
    second = u16(staged, counts + STATE_WORD_LEN)
    if s16(second) >= 0:
        dest, map_at, drawn = half(dest, map_at, second)

    if bottom:
        # ...and AFTER the draw going down, pushing the cursor a row the other way on the same wrap.
        row = (u16(staged, TILE_ROW) + TILE_ROW_STEP) & TILE_ROW_MASK
        if row == 0:
            _put(out, staged, MAP_CURSOR,
                 (u16(staged, MAP_CURSOR) + u16(staged, MAP_ROW_STRIDE)) & 0xffff)
        _put(out, staged, TILE_ROW, row)
    return (drawn & ~0xffff) | (ROW_DRAWN_BOTTOM if bottom else ROW_DRAWN_TOP)


def _model_preshift_row(staged, out, source, dest):
    """One 128-byte buffer row shifted two pixels left into the copy above it."""
    def rotate(cell):
        shifted, carried = [], []
        for plane in range(PLANES):
            rotated = _rol32(u16(staged, (cell + plane * PLANE_STRIDE) & 0xffffffff), PRESHIFT_BITS)
            shifted.append(rotated & 0xffff)
            carried.append(rotated >> WORD_BITS)
        return shifted, carried

    def write(at, words):
        for plane, value in enumerate(words):
            _put(out, staged, (at + plane * PLANE_STRIDE) & 0xffffffff, value)

    def bitwise_or(at, words):
        for plane, value in enumerate(words):
            addr = (at + plane * PLANE_STRIDE) & 0xffffffff
            _put(out, staged, addr, u16(staged, addr) | value)

    shifted, carried = rotate(source)
    source = (source + CELL_BYTES) & 0xffffffff
    write(dest, shifted)
    write(PRESHIFT_CARRY, carried)          # cell 0's carry, parked for the row's last cell
    dest = (dest + CELL_BYTES) & 0xffffffff

    for _cell in range(1, ROW_CELLS):
        shifted, carried = rotate(source)
        source = (source + CELL_BYTES) & 0xffffffff
        bitwise_or((dest - CELL_BYTES) & 0xffffffff, carried)
        write(dest, shifted)
        dest = (dest + CELL_BYTES) & 0xffffffff

    parked = [u16(staged, PRESHIFT_CARRY + plane * PLANE_STRIDE) for plane in range(PLANES)]
    bitwise_or((dest - CELL_BYTES) & 0xffffffff, parked)
    return source, dest


def _model_preshift(staged, out, drawn):
    """$8144. Only the LOW WORD's sign of ``drawn`` picks the source row (`tst.w d0 / bmi`)."""
    member = BUFFER_ROW_BOTTOM if s16(drawn & 0xffff) < 0 else BUFFER_ROW_TOP
    source = _u32(staged, BUFFER_ROWS + member)
    dest = (source + BUFFER_LEN) & 0xffffffff
    for _copy in range(PRESHIFT_COPIES):
        for _row in range(PRESHIFT_ROWS):
            source, dest = _model_preshift_row(staged, out, source, dest)
        # The copy just written becomes the next one's source: the walk is a chain, not a re-read.
        source = (dest - PRESHIFT_ROWS * BUFFER_LINE) & 0xffffffff
        dest = (source + BUFFER_LEN) & 0xffffffff


def _model_serve_vertical(staged, out, down):
    """$75d4 / $75e8 — the request byte consumed, then step, fill and pre-shift under one skip."""
    _put8(out, staged, REQUEST_DOWN if down else REQUEST_UP, 0)
    if _model_vertical_step(staged, out, down):
        return
    _model_preshift(staged, out, _model_row_fill(staged, out, down))


def _model_serve_requests(staged, out):
    """$759a — the original's own order, and every handler consumes its own byte."""
    if staged[REQUEST_UP]:
        _model_serve_vertical(staged, out, down=False)
    if staged[REQUEST_DOWN]:
        _model_serve_vertical(staged, out, down=True)
    if staged[REQUEST_RIGHT]:
        _model_serve_horizontal(staged, out, RIGHT)
    if staged[REQUEST_LEFT]:
        _model_serve_horizontal(staged, out, LEFT)


def _model_raise_requests(staged, out, entry_d0, entry_d1):
    """$d28 — the two request bytes, and the two distances returned in the low words of d0/d1.

    Which side the object is on is a SIGNED COMPARISON of its position against the centre, not the
    sign of the wrapped difference: `subi.w` sets the overflow flag and `bgt`/`blt` read it. The two
    part company at a position of $8000, and the distance returned is still the wrapped difference.
    """
    follow_y = s16(u16(staged, FOLLOW_Y))
    vertical = (follow_y - CENTRE_Y) & 0xffff
    if follow_y > CENTRE_Y:
        _put8(out, staged, RAISED_V_DOWN, RAISED_SET)
    elif follow_y < CENTRE_Y:
        _put8(out, staged, RAISED_V_UP, RAISED_SET)
        vertical = -vertical & 0xffff

    follow_x = s16(u16(staged, FOLLOW_X))
    horizontal = (follow_x - CENTRE_X) & 0xffff
    if follow_x < CENTRE_X:
        _put8(out, staged, RAISED_H_LEFT, RAISED_SET)
        horizontal = -horizontal & 0xffff
    elif follow_x > CENTRE_X:
        _put8(out, staged, RAISED_H_RIGHT, RAISED_SET)
    return ((entry_d0 & ~0xffff) | vertical, (entry_d1 & ~0xffff) | horizontal)


def _model_run_queue(staged, out):
    """$7522 — raise, halve, drain each axis, clear both pairs."""
    if u16(staged, FOLLOW_FROZEN) != 0:
        _model_serve_requests(staged, out)
        return
    vertical, horizontal = _model_raise_requests(staged, out, 0, 0)
    _put(out, staged, QUEUE_V_COUNT, (s16(vertical & 0xffff) >> 1) & 0xffff)
    _put(out, staged, QUEUE_H_COUNT, (s16(horizontal & 0xffff) >> 1) & 0xffff)
    for count_word, raised, request in ((QUEUE_H_COUNT, RAISED_H, REQUEST_LEFT),
                                        (QUEUE_V_COUNT, RAISED_V, REQUEST_UP)):
        while u16(staged, count_word) != 0:
            _put(out, staged, count_word, (u16(staged, count_word) - 1) & 0xffff)
            _put(out, staged, request, u16(staged, raised))
            _model_serve_requests(staged, out)
    _put32(out, staged, RAISED_V, 0)
    _put32(out, staged, QUEUE_H_COUNT, 0)


# --- running one against the original -------------------------------------------------------------

_VERTICAL_STEP = {name: leaf.bind(name, leaf.IMAGE_ARG, ctypes.c_int)
                  for name in ("bg_scroll_step_up", "bg_scroll_step_down")}
_ROW_FILL = {name: leaf.bind(name, leaf.IMAGE_ARG, ctypes.c_uint32)
             for name in ("bg_scroll_fill_top_row", "bg_scroll_fill_bottom_row")}
_PRESHIFT = leaf.register_glue("bg_scroll_preshift_rows", [ctypes.c_uint32])
_RAISE = leaf.bind("bg_scroll_raise_requests",
                   leaf.IMAGE_ARG + [ctypes.POINTER(ctypes.c_uint32)] * 2)
_IMAGE_ONLY = {name: leaf.image_glue(name) for name in
               ("bg_scroll_serve_up", "bg_scroll_serve_down", "bg_scroll_serve_requests",
                "bg_scroll_run_queue")}


def _raise_glue(entry_d0, entry_d1, seen):
    """bg_scroll_raise_requests takes the caller's d0/d1 IN and hands them back OUT, so the glue
    supplies the entry values the oracle is given and records what came back."""
    def call(_lib, image):
        vertical = ctypes.c_uint32(entry_d0)
        horizontal = ctypes.c_uint32(entry_d1)
        _RAISE(image, ctypes.byref(vertical), ctypes.byref(horizontal))
        seen.append((vertical.value, horizontal.value))
    return call


def _run_modelled(name, glue, expected, what, max_insns, poison=True, regs=None):
    """Run one routine against the original and require the write set to be EXACTLY ``expected``.

    The shared body of every case below: the whole-image diff comes from leaf.run, and this adds the
    equality — both the address set and every byte in it — against the Python model.
    """
    info = leaf.run(name, glue, merge_bands(expected), what, regs=regs, max_insns=max_insns,
                    poison=poison)
    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {len(written)} bytes against the model's {len(expected)} — "
        f"first difference at {min(set(written) ^ set(expected)):#x}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")
    return info


# --- the vertical position steps ------------------------------------------------------------------

@pytest.mark.parametrize("name,down", [("bg_scroll_step_up", False),
                                       ("bg_scroll_step_down", True)],
                         ids=["up", "down"])
@pytest.mark.parametrize("case,state,skips", [
    ("mid-ring", dict(y=0x20, y_bottom=0x9e), False),
    ("top-cursor-at-the-up-wrap", dict(y=0, y_bottom=0x9e), False),
    ("bottom-cursor-at-the-up-wrap", dict(y=0x20, y_bottom=0), False),
    ("top-cursor-at-the-down-wrap", dict(y=SCROLL_Y_LAST, y_bottom=0x40), False),
    ("bottom-cursor-at-the-down-wrap", dict(y=0x20, y_bottom=SCROLL_Y_LAST), False),
    ("cursors-at-the-rings-two-ends", dict(y=0, y_bottom=SCROLL_Y_LAST), False),
    ("coarse-row-republished", dict(y=0x10, y_bottom=0x40), False),
    ("at-the-boundary", dict(pos_y=0), True),
], ids=lambda v: v if isinstance(v, str) else "")
def test_a_vertical_step_moves_both_ring_cursors_or_consumes_two_calls(name, down, case, state,
                                                                       skips):
    """The two cursors wrap on their OWN tests, so a case that put one of them at its wrap and not
    the other fails a port that drove both from one row word.

    Each direction has its own wrap ROW — up reloads a cursor sitting at 0, down one sitting at
    SCROLL_Y_LAST — so the four `*-at-the-*-wrap` cases name a ROW, not a direction, and running
    each under both directions is what covers all four one-cursor-at-a-time combinations. Under the
    direction the case names, the parked cursor reloads and the other moves; under the other
    direction neither reloads, which pins that a step ignores the wrap row it is not walking
    towards. `cursors-at-the-rings-two-ends` is the only seed with a cursor on EACH wrap row: either
    direction reloads one of them to the row the other is leaving, and NEITHER direction wraps both
    — which is what the two cursors having separate tests means.

    The boundary case is the up step's zero and the down step's limit at once: `at-the-boundary`
    seeds pos_y = 0 and, for the down step, a limit equal to it."""
    seeded = dict(state)
    if skips and down:
        seeded["limit_y"] = seeded["pos_y"]
    pokes = _vertical_pokes(salt=case_salt(f"{name}-{case}"), **seeded)
    image = harness.make_image(pokes)

    expected = {}
    staged = bytearray(image)
    modelled_skip = _model_vertical_step(staged, expected, down)
    assert modelled_skip is skips, f"{case}: the model disagrees with the case about the skip"

    seen = []
    skip = STEP_SKIP_BYTES[name]
    allowed = merge_bands(expected) + [(RETURN_SLOT, LONGWORD_LEN)]
    info = leaf.run(name, _vertical_step_glue(name, seen), allowed, f"{name} {case}",
                    regs={"_pokes": pokes}, max_insns=VERTICAL_STEP_INSN_CAP,
                    stop_pc=emu.SENTINEL + skip)
    assert _oracle_skipped(info, skip) is skips
    assert bool(seen[0]) is skips, (
        f"{name} {case}: the reconstruction returned {seen[0]} while the original "
        f"{'skipped' if skips else 'did not skip'} its caller's two calls")

    # The rewritten return address is program output (it is the skip), and `_oracle_skipped` above
    # is what states its value — so it is not part of the write set the model predicts.
    written = {addr: value for addr, value in program_writes(info).items()
               if not RETURN_SLOT <= addr < RETURN_SLOT + LONGWORD_LEN}
    assert set(written) == set(expected), (
        f"{name} {case}: write set differs at {min(set(written) ^ set(expected)):#x}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr]


def _vertical_step_glue(name, seen):
    def call(_lib, image):
        seen.append(_VERTICAL_STEP[name](image))
        return seen[-1]
    return call


def test_a_vertical_step_keeps_every_buffer_rows_pointer_on_its_own_ring_row():
    """The invariant the sixteen pointers exist to hold: pair member m of copy k is
    `$44000 + k * $5800 + row_m * 128`. Asserted after a wrap in each direction, which is the only
    place the original writes them outright rather than adjusting them."""
    for name, down, seeded, expected_rows in (
            ("bg_scroll_step_up", False, dict(y=0, y_bottom=0), (SCROLL_Y_LAST, SCROLL_Y_LAST)),
            ("bg_scroll_step_down", True, dict(y=SCROLL_Y_LAST, y_bottom=SCROLL_Y_LAST), (0, 0))):
        pokes = _vertical_pokes(salt=case_salt(name + "-wrap"), **seeded)
        image = harness.make_image(pokes)
        expected = {}
        _model_vertical_step(bytearray(image), expected, down)
        allowed = merge_bands(expected) + [(RETURN_SLOT, LONGWORD_LEN)]
        info = leaf.run(name, _vertical_step_glue(name, []), allowed, f"{name} wrap",
                        regs={"_pokes": pokes}, max_insns=VERTICAL_STEP_INSN_CAP,
                        stop_pc=emu.SENTINEL + STEP_SKIP_BYTES[name])
        for copy in range(BUFFERS):
            for member, row in zip((BUFFER_ROW_TOP, BUFFER_ROW_BOTTOM), expected_rows):
                at = BUFFER_ROWS + copy * BUFFER_ROW_PAIR + member
                actual = leaf.read_int(info, at, LONGWORD_LEN, f"{name} pointer {copy}/{member}")
                assert actual == _buffer_row(copy, row), (
                    f"{name}: copy {copy} member {member} is {actual:#x}, not the "
                    f"{_buffer_row(copy, row):#x} that row {row:#x} gives")


# --- the row fills --------------------------------------------------------------------------------
# Each case names bg_scroll_tile_row (which scanline pair of the tile, and whether the step-back or
# the step-forward wraps it) and bg_scroll_x (which cell the seam falls on, and so how the sixteen
# cells split between the two halves).
ROW_FILL_CASES = [
    ("mid-tile", 0x30, 5),
    ("tile-row-0", 0, 5),                      # the top fill's step-back wraps and pulls the map
    ("tile-row-last", TILE_ROW_MASK + 1 - TILE_ROW_STEP, 5),   # ...and the bottom fill's pushes it
    ("x0", 0x30, 0),                           # entry 0's second count is -1: no second half
    ("x1", 0x30, 1),                           # ...and entry 1's is exactly 0: one cell
    ("x15", 0x30, ROW_SPLIT_ENTRIES - 1),
]


@pytest.mark.parametrize("bottom", [False, True], ids=["top", "bottom"])
@pytest.mark.parametrize("case,tile_row,scroll_x", ROW_FILL_CASES,
                         ids=[case[0] for case in ROW_FILL_CASES])
def test_a_row_fill_copies_the_cells_the_geometry_names(bottom, case, tile_row, scroll_x):
    name = "bg_scroll_fill_bottom_row" if bottom else "bg_scroll_fill_top_row"
    pokes = _vertical_pokes(salt=case_salt(f"{name}-{case}"), tile_row=tile_row,
                            scroll_x=scroll_x, row_offset=scroll_x * CELL_BYTES)
    image = harness.make_image(pokes)
    expected = {}
    drawn = _model_row_fill(bytearray(image), expected, bottom)

    seen = []

    def glue(_lib, buf):
        seen.append(_ROW_FILL[name](buf))
        return seen[-1]

    info = _run_modelled(name, glue, expected, f"{name} {case}", ROW_FILL_INSN_CAP,
                         regs={"_pokes": pokes})
    assert seen[0] == drawn, f"{name} {case}: returned {seen[0]:#x}, not the model's {drawn:#x}"
    assert info["regs"]["d0"] == drawn, (
        f"{name} {case}: the ORIGINAL left d0 = {info['regs']['d0']:#x}, not {drawn:#x} — the low "
        f"word is what bg_scroll_preshift_rows tests and the high half is the last tile's offset")


@pytest.mark.parametrize("bottom", [False, True], ids=["top", "bottom"])
def test_a_row_fill_touches_exactly_one_row_pair(bottom):
    """The two halves cover the 128-byte row once over: ROW_FILL_SCANLINES scanlines of it, and
    nothing else in the buffer."""
    name = "bg_scroll_fill_bottom_row" if bottom else "bg_scroll_fill_top_row"
    pokes = _vertical_pokes(salt=case_salt(name + "-extent"))
    image = harness.make_image(pokes)
    expected = {}
    _model_row_fill(bytearray(image), expected, bottom)
    cells = sorted(addr for addr in expected if addr >= BUFFER_BASE)
    assert len(cells) == ROW_FILL_SCANLINES * BUFFER_LINE, (
        f"{name}: {len(cells)} buffer bytes, not the {ROW_FILL_SCANLINES * BUFFER_LINE} that "
        f"{ROW_FILL_SCANLINES} whole scanlines give")
    row = VERTICAL_STATE["y" if not bottom else "y_bottom"]
    assert min(cells) == _buffer_row(0, row)
    assert max(cells) == _buffer_row(0, row) + ROW_FILL_SCANLINES * BUFFER_LINE - 1


def test_the_row_split_table_is_the_pairs_the_row_fills_assume():
    """bg_scroll_row_split_table is the game's own data, the horizontal counterpart of
    bg_scroll_col_split_table: entry k is (15 - k, k - 1), so the two halves always draw the row's
    sixteen cells exactly once."""
    for index in range(ROW_SPLIT_ENTRIES):
        at = ROW_SPLIT_TABLE + index * LONGWORD_LEN
        first = u16(harness.BASE_IMAGE, at)
        second = s16(u16(harness.BASE_IMAGE, at + STATE_WORD_LEN))
        assert first == ROW_CELLS - 1 - index, f"entry {index}'s first count is {first}"
        assert second == index - 1, f"entry {index}'s second count is {second}"
        assert (first + 1) + (second + 1) == ROW_CELLS, (
            f"entry {index}'s two halves draw {(first + 1) + (second + 1)} cells, not {ROW_CELLS}")


def test_the_headers_derived_geometry_is_what_the_numbers_say():
    """Three constants include/wonderboy.h states as literals with their derivation in a comment
    (the scraper reads plain integers only). Pinned here so the comment cannot go stale."""
    assert ROW_CELLS == BUFFER_LINE // CELL_BYTES
    assert ROW_CELLS == ROW_SPLIT_ENTRIES
    assert PRESHIFT_COPIES == BUFFERS - 1
    assert PRESHIFT_ROWS == ROW_FILL_SCANLINES
    assert TILE_ROW_STEP == ROW_FILL_SCANLINES * CELL_BYTES
    assert BUFFER_LEN == BUFFER_TILE_ROWS * TILE_BLOCK_LEN
    assert SCROLL_Y_LAST * BUFFER_LINE + ROW_FILL_SCANLINES * BUFFER_LINE == BUFFER_LEN, (
        "the last ring row plus its own scanline pair is not the whole buffer")


# --- the pre-shift --------------------------------------------------------------------------------

@pytest.mark.parametrize("drawn,member", [
    (ROW_DRAWN_TOP, BUFFER_ROW_TOP),
    (ROW_DRAWN_BOTTOM, BUFFER_ROW_BOTTOM),
    (0x1234_0000 | ROW_DRAWN_TOP, BUFFER_ROW_TOP),      # a row fill's real d0: the tile offset...
    (0x1234_0000 | ROW_DRAWN_BOTTOM, BUFFER_ROW_BOTTOM),  # ...sits above the marker and is ignored
    (0x0000_8000, BUFFER_ROW_BOTTOM),                   # any NEGATIVE low word picks the bottom row
    (0x0000_7fff, BUFFER_ROW_TOP),                      # ...and any non-negative one the top
], ids=["top", "bottom", "top-under-a-tile-offset", "bottom-under-a-tile-offset",
        "lowest-negative-word", "highest-positive-word"])
def test_the_preshift_walks_the_row_its_argument_names_through_every_copy(drawn, member):
    """`tst.w d0 / bmi` reads the LOW WORD only, so the tile offset a row fill leaves in the high
    half must not reach the choice — the two `under-a-tile-offset` cases are what says so."""
    pokes = _vertical_pokes(salt=case_salt(f"preshift-{drawn:#x}"))
    image = harness.make_image(pokes)
    expected = {}
    _model_preshift(bytearray(image), expected, drawn)

    info = _run_modelled("bg_scroll_preshift_rows", _PRESHIFT(drawn), expected,
                         f"bg_scroll_preshift_rows d0={drawn:#x}", PRESHIFT_INSN_CAP,
                         regs={"_pokes": pokes, "d0": drawn})

    row = VERTICAL_STATE["y" if member == BUFFER_ROW_TOP else "y_bottom"]
    touched = sorted(addr for addr in program_writes(info) if addr >= BUFFER_BASE)
    assert min(touched) == _buffer_row(1, row), (
        f"the first byte written is {min(touched):#x}, not copy 1's own row {_buffer_row(1, row):#x}"
        f" — the pre-shift writes every copy ABOVE the drawn one and none of the drawn one itself")
    assert max(touched) == _buffer_row(BUFFERS - 1, row) + PRESHIFT_ROWS * BUFFER_LINE - 1
    assert len(touched) == PRESHIFT_COPIES * PRESHIFT_ROWS * BUFFER_LINE


def test_the_preshift_carries_the_rows_first_cell_round_to_its_last():
    """The wrap that makes a buffer row circular: cell 0's two rotated-out pixels are parked in
    bg_scroll_preshift_carry and ORed into cell 15. Read straight off the written bytes, so a port
    that dropped the carry (or ORed it into the wrong cell) fails here as well as on the diff."""
    pokes = _vertical_pokes(salt=case_salt("preshift-carry"))
    image = harness.make_image(pokes)
    expected = {}
    _model_preshift(bytearray(image), expected, ROW_DRAWN_TOP)
    info = _run_modelled("bg_scroll_preshift_rows", _PRESHIFT(ROW_DRAWN_TOP), expected,
                         "bg_scroll_preshift_rows carry", PRESHIFT_INSN_CAP,
                         regs={"_pokes": pokes, "d0": ROW_DRAWN_TOP})

    # What is left in the scratch is the LAST row's carry: the second scanline of the last copy the
    # walk read, which is itself a copy the walk wrote — so both sides of the claim come out of the
    # write set rather than out of the seeded image.
    row = VERTICAL_STATE["y"]
    source_cell = _buffer_row(BUFFERS - 2, row) + BUFFER_LINE
    last_cell = _buffer_row(BUFFERS - 1, row) + BUFFER_LINE + BUFFER_LINE - CELL_BYTES
    for plane in range(PLANES):
        parked = leaf.read_int(info, PRESHIFT_CARRY + plane * PLANE_STRIDE, STATE_WORD_LEN,
                               "the parked carry")
        source = leaf.read_int(info, source_cell + plane * PLANE_STRIDE, STATE_WORD_LEN,
                               "the row's first cell")
        assert parked == source >> (WORD_BITS - PRESHIFT_BITS), (
            f"plane {plane}: the parked carry {parked:#06x} is not the top {PRESHIFT_BITS} bits of "
            f"the row's first cell {source:#06x}")
        written = leaf.read_int(info, last_cell + plane * PLANE_STRIDE, STATE_WORD_LEN,
                                "the row's last cell")
        assert written & parked == parked, (
            f"plane {plane}: the last cell {written:#06x} does not carry the parked {parked:#06x}")


# --- the vertical request handlers ----------------------------------------------------------------

@pytest.mark.parametrize("down", [False, True], ids=["up", "down"])
@pytest.mark.parametrize("at_boundary", [False, True], ids=["moves-fills-and-preshifts",
                                                           "at-the-boundary"])
def test_a_vertical_request_is_consumed_whether_or_not_the_step_moves(down, at_boundary):
    """The request byte is cleared before anything else happens, so it goes down even on the pass
    that draws nothing — and on that pass it is the ONLY byte written, because the step consumes
    both of its caller's calls at once."""
    name = "bg_scroll_serve_down" if down else "bg_scroll_serve_up"
    request = REQUEST_DOWN if down else REQUEST_UP
    state = dict(pos_y=0, limit_y=0) if at_boundary else {}
    pokes = _vertical_pokes(salt=case_salt(f"{name}-{at_boundary}"), **state)
    pokes[request] = b"\xff"
    image = harness.make_image(pokes)

    expected = {}
    _model_serve_vertical(bytearray(image), expected, down)
    if at_boundary:
        assert set(expected) == {request}, (
            "the boundary model should write the request byte and nothing else")

    info = _run_modelled(name, _IMAGE_ONLY[name], expected, f"{name} boundary={at_boundary}",
                         VERTICAL_SERVE_INSN_CAP, poison=False, regs={"_pokes": pokes})
    assert program_writes(info)[request] == 0


# --- the dispatch pass and the queue above it -----------------------------------------------------

def _word_of(pokes, addr):
    """The word a poke dict already carries at ``addr`` — so the horizontal seeding below extends
    the vertical one rather than overwriting words it just set."""
    return int.from_bytes(pokes[addr], "big")


def _dispatch_pokes(raised, salt, **overrides):
    """One image with every position word BOTH halves need, and ``raised`` request bytes set."""
    pokes = _vertical_pokes(salt=salt, **overrides)
    pokes.update(_step_pokes(pending=PENDING_SET, pos_x=0x40, phase=_word_of(pokes, PHASE),
                             scroll_x=_word_of(pokes, SCROLL_X),
                             map_cursor=_word_of(pokes, MAP_CURSOR),
                             row_offset=_word_of(pokes, ROW_BYTE_OFFSET)))
    for request in raised:
        pokes[request] = b"\xff"
    return pokes


@pytest.mark.parametrize("case,raised", [
    ("up", (REQUEST_UP,)),
    ("down", (REQUEST_DOWN,)),
    ("right", (REQUEST_RIGHT,)),
    ("left", (REQUEST_LEFT,)),
    ("all-four", (REQUEST_UP, REQUEST_DOWN, REQUEST_RIGHT, REQUEST_LEFT)),
    ("none", ()),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_dispatch_pass_serves_exactly_the_requests_that_are_raised(case, raised):
    """Four `tst.b`/`beq`/`bsr` in line. The `all-four` case is what pins the ORDER — up, down,
    right, left — because each handler runs on the state the previous one left."""
    pokes = _dispatch_pokes(raised, salt=case_salt("dispatch-" + case))
    image = harness.make_image(pokes)
    expected = {}
    _model_serve_requests(bytearray(image), expected)
    if not raised:
        assert not expected, "a pass with nothing raised must write nothing at all"

    info = _run_modelled("bg_scroll_serve_requests", _IMAGE_ONLY["bg_scroll_serve_requests"],
                         expected, f"bg_scroll_serve_requests {case}", SERVE_REQUESTS_INSN_CAP,
                         poison=False, regs={"_pokes": pokes})
    for request in raised:
        assert program_writes(info)[request] == 0


# case -> (follow_x, follow_y, the raised bytes, the distance each axis returns). The distances are
# stated rather than derived so the `neg.w` is pinned by a number and not by the model alone.
RAISE_CASES = [
    ("centred", CENTRE_X, CENTRE_Y, (), 0, 0),
    ("above-and-left", CENTRE_X - 6, CENTRE_Y - 4, (RAISED_V_UP, RAISED_H_LEFT), 4, 6),
    ("below-and-right", CENTRE_X + 6, CENTRE_Y + 4, (RAISED_V_DOWN, RAISED_H_RIGHT), 4, 6),
    ("one-pixel-above", CENTRE_X, CENTRE_Y - 1, (RAISED_V_UP,), 1, 0),
    ("one-pixel-below", CENTRE_X, CENTRE_Y + 1, (RAISED_V_DOWN,), 1, 0),
    ("at-the-origin", 0, 0, (RAISED_V_UP, RAISED_H_LEFT), CENTRE_Y, CENTRE_X),
    # The one position where BOTH claims about this routine break, and they break together: $8000
    # minus a small centre OVERFLOWS, so the difference reads positive while the `blt` (which reads
    # the overflow flag) takes the negative arm — and the `neg.w` of that positive difference then
    # comes back NEGATIVE. Reproduced, not tidied.
    ("wrapped-at-the-lowest-position", 0x8000, 0x8000, (RAISED_V_UP, RAISED_H_LEFT),
     -(0x8000 - CENTRE_Y) & 0xffff, -(0x8000 - CENTRE_X) & 0xffff),
]
ALL_RAISED = (RAISED_V_UP, RAISED_V_DOWN, RAISED_H_LEFT, RAISED_H_RIGHT)


@pytest.mark.parametrize("case,follow_x,follow_y,raised,vertical,horizontal", RAISE_CASES,
                         ids=[case[0] for case in RAISE_CASES])
def test_the_raiser_raises_the_side_the_followed_object_is_on(case, follow_x, follow_y, raised,
                                                              vertical, horizontal):
    entry_d0, entry_d1 = 0xdead_0000, 0xbeef_0000
    pokes = {FOLLOW_X: word(follow_x), FOLLOW_Y: word(follow_y)}
    image = harness.make_image(pokes)
    expected = {}
    modelled = _model_raise_requests(bytearray(image), expected, entry_d0, entry_d1)
    assert modelled == ((entry_d0 & ~0xffff) | vertical, (entry_d1 & ~0xffff) | horizontal), (
        f"{case}: the model returns {modelled}, not the distances the case states")

    seen = []
    info = _run_modelled("bg_scroll_raise_requests", _raise_glue(entry_d0, entry_d1, seen),
                         expected, f"bg_scroll_raise_requests {case}", leaf.LEAF_INSN_CAP,
                         regs={"_pokes": pokes, "d0": entry_d0, "d1": entry_d1})

    assert seen[0] == modelled
    assert (info["regs"]["d0"], info["regs"]["d1"]) == modelled, (
        f"{case}: the ORIGINAL returned d0/d1 = {info['regs']['d0']:#x}/{info['regs']['d1']:#x}, "
        f"not {modelled[0]:#x}/{modelled[1]:#x} — the high halves are the CALLER'S and must survive")
    assert set(expected) == set(raised), (
        f"{case}: raised {sorted(hex(a) for a in expected)}, not {sorted(hex(a) for a in raised)}")
    for request in ALL_RAISED:
        assert expected.get(request, 0) == (RAISED_SET if request in raised else 0)


@pytest.mark.parametrize("case,follow_x,follow_y,frozen,raised", [
    ("frozen-serves-what-is-already-raised", CENTRE_X, CENTRE_Y, 1, (REQUEST_UP,)),
    ("frozen-with-nothing-raised", CENTRE_X, CENTRE_Y, 0xffff, ()),
    ("centred-raises-nothing", CENTRE_X, CENTRE_Y, 0, ()),
    ("one-step-left-and-up", CENTRE_X - 2 * SCROLL_STEP, CENTRE_Y - 2 * SCROLL_STEP, 0, ()),
    ("two-steps-right-and-down", CENTRE_X + 2 * QUEUE_MAX_STEPS * SCROLL_STEP,
     CENTRE_Y + 2 * QUEUE_MAX_STEPS * SCROLL_STEP, 0, ()),
], ids=lambda v: v if isinstance(v, str) else "")
def test_the_queue_drains_half_of_each_distance_in_two_pixel_steps(case, follow_x, follow_y,
                                                                   frozen, raised):
    """`asr.w #1` on each distance, then that many dispatch passes per axis — horizontal first.
    The two `frozen` cases are the gate: the raiser never runs, no count is written, and the pass
    is one bare dispatch."""
    pokes = _dispatch_pokes(raised, salt=case_salt("queue-" + case))
    pokes.update({FOLLOW_X: word(follow_x), FOLLOW_Y: word(follow_y),
                  FOLLOW_FROZEN: word(frozen)})
    image = harness.make_image(pokes)
    expected = {}
    _model_run_queue(bytearray(image), expected)

    _run_modelled("bg_scroll_run_queue", _IMAGE_ONLY["bg_scroll_run_queue"], expected,
                  f"bg_scroll_run_queue {case}", RUN_QUEUE_INSN_CAP, poison=False,
                  regs={"_pokes": pokes})


def test_the_queue_owes_no_more_steps_than_the_cases_cap():
    """The instruction cap above is derived from QUEUE_MAX_STEPS, so a case seeded further from the
    centre than that would silently rely on the cap's factor of two instead of on the number. This
    is the reading that keeps the cap a bound: the furthest case must still be within it."""
    furthest = 2 * QUEUE_MAX_STEPS * SCROLL_STEP
    assert (furthest // SCROLL_STEP) // 2 <= QUEUE_MAX_STEPS


# ==================================================================================================
# THE CONSUMER TIER: bg_scroll_blit ($82f8) AND ITS SIXTEEN COPY VARIANTS ($83b6..$8dfe)
#
# Everything above PRODUCES the eight pre-shifted buffers; this reads one of them and copies the
# visible window into WB_SCREEN_BACK. Three things make it different from the engine's batteries:
#
#   * THE DISPATCH IS A JUMP TABLE GHIDRA CANNOT FOLLOW, which is why $83b6..$8dfe was in no
#     function at all until ../names.txt named it (PORTABILITY.md §8.1). A case entered at $82f8
#     runs the dispatcher AND the variant its `jmp (a2)` reaches, so the table is exercised as the
#     original exercises it; a case entered at a VARIANT supplies the four registers the dispatcher
#     would have and pins that body on its own. Both kinds are here, because either alone would
#     leave one of the two halves of the mechanism unpinned.
#   * THE SIXTEEN VARIANTS ARE ONE PATTERN, AND THAT IS TESTED RATHER THAN ASSUMED. Each one's
#     WHOLE body is assembled from `_blit_variant_half` and pinned against the image, three of them
#     are ALSO pinned against bytes transcribed straight out of ../out/wonderboy_dis.txt (so the
#     pattern itself cannot be what is wrong), and the entry addresses, the lengths and the gaps
#     between them are pinned against the jump table. That is what lets src/scroll.c be one
#     parametrised function instead of sixteen copies.
#   * BOTH SCREENS ARE SEEDED, AND THE SOURCE REGION TOO. The destination is 19,200 bytes with
#     40-byte gaps between its rows and the source is a ring inside one of eight buffers, so a copy
#     that ran one scanline long, chained by the wrong stride or read the wrong buffer must land on
#     bytes that are wrong FOR WHERE THEY WERE WRITTEN rather than on zeros — the address-keyed
#     seeding the engine's batteries use, extended over $70000..$80000.
#
# KNOWINGLY NOT PINNED
#   * A COLUMN OUTSIDE 0..15. `movea.l (0,a2,d1.w),a2` bounds nothing, so the original would jump
#     through whatever longword follows the table; C has no such behaviour to reproduce. The domain
#     is established instead: WB_BG_SCROLL_X is written at exactly three places in the whole image,
#     and every one of them leaves a nibble — a `subq.w #1` and an `addq.w #1`, each immediately
#     followed by its own `andi.w #$f`, plus one `clr.w`
#     (test_the_column_is_a_nibble_wherever_the_image_writes_it).
#   * THE `bpl` ARM'S OWN OVERFLOW. `subi.w #$10,d6 / bpl` reads N alone, so it really is the
#     wrapped difference's sign — the reading `bgt`/`blt` would NOT support (STATUS.md, batch 6).
#     The two readings part company only for a ring row at or above $8000, and such a row also
#     asks the first half for 32,944 scanlines, which walks off the image. Reproduced by
#     construction and honestly unreached; the game's own writers of WB_BG_SCROLL_Y keep it on the
#     0..$ae grid.
#   * THE REGISTERS THE COPY LEAVES BEHIND. It walks out with a0/a1 far past where they started and
#     its one call site `rts`s immediately, so there is nothing to compare against — the same
#     family as the column fills'.
# ==================================================================================================

# A variant is thirty `move.l` and three instructions per scanline; the dispatcher adds twenty-odd
# ahead of them. Doubled, so the cap fails a run that fell into a 65536-iteration `dbf` rather than
# predicting the exact count.
_BLIT_SCANLINE_INSNS = BLIT_LONGWORDS + 4
_BLIT_ENTRY_INSNS = 24
BLIT_INSN_CAP = 2 * (_BLIT_ENTRY_INSNS + BLIT_SCANLINES * _BLIT_SCANLINE_INSNS)

# What the two screen buffers cost to seed, and where a blit's destination sits inside one.
SCREEN_BYTES = 2 * (SCREEN_BUFFERS[1] - SCREEN_BUFFERS[0])


def _blit_pokes(phase, scroll_x, row, salt, screen=SCREEN_BUFFERS[0]):
    """The image a blit case runs on.

    All eight source buffers are seeded (`whole_region=True`) rather than only the phase's own, so a
    run that picked the wrong buffer lands on seeded-but-wrong bytes; both screens are seeded for the
    same reason on the destination side, and with the SAME address key, so the two agree where a
    case reads one and writes the other.
    """
    pokes = _scroll_pokes(phase, scroll_x, y_coarse=row >> Y_COARSE_SHIFT, salt=salt,
                          whole_region=True)
    pokes.update({
        SCROLL_Y: word(row),
        SCREEN_BACK: longword(screen),
        SCREEN_BUFFERS[0]: keyed_block(SCREEN_BUFFERS[0], SCREEN_BYTES, salt + 4),
    })
    return pokes


# --- the model ------------------------------------------------------------------------------------
# Written from ../out/wonderboy_dis.txt rather than from src/scroll.c, so it is a third statement of
# the same geometry and the one that lets a case say WHICH bytes moved.

def _blit_geometry(image):
    """What $82f8 computes before its `jmp (a2)`: which variant, from where, to where, and the two
    `dbf` counts. Returned separately from the copy so a case can assert the SPLIT on its own."""
    phase = u16(image, PHASE)
    row = u16(image, SCROLL_Y)
    column = u16(image, SCROLL_X)

    source = (BUFFER_BASE + phase * BUFFER_PHASE_STRIDE
              + s16((row << BLIT_ROW_SHIFT) & 0xffff)
              + s16((column * CELL_BYTES) & 0xffff)) & 0xffffffff
    dest = (_u32(image, SCREEN_BACK) + BLIT_SCREEN_ORIGIN) & 0xffffffff

    if s16((row - BLIT_WRAP_ROW) & 0xffff) < 0:
        return column, source, dest, BLIT_SCANLINES - 1, BLIT_NO_SECOND_HALF
    to_the_end = (BUFFER_SCANLINES - row) & 0xffff
    return (column, source, dest,
            (to_the_end - 1) & 0xffff, ((BLIT_SCANLINES - 1) - to_the_end) & 0xffff)


def _model_blit_copy(image, column, source, dest, first_rows, second_rows):
    """One of the sixteen copy variants, walked in Python. Returns ({address: final byte},
    (lowest source address read, one past the highest)) — the span being what pins that the ring
    walk never leaves the buffer the phase named."""
    out = {}
    before_seam = ROW_LONGWORDS - CELL_LONGWORDS * column
    wraps = before_seam < BLIT_LONGWORDS
    read_lo, read_hi = source, source

    def run(longwords):
        nonlocal source, dest, read_lo, read_hi
        for _ in range(longwords):
            for byte in range(LONGWORD_LEN):
                at = (source + byte) & 0xffffffff
                out[(dest + byte) & 0xffffffff] = out.get(at, image[at])
            read_lo = min(read_lo, source)
            read_hi = max(read_hi, source + LONGWORD_LEN)
            source = (source + LONGWORD_LEN) & 0xffffffff
            dest = (dest + LONGWORD_LEN) & 0xffffffff

    def scanlines(rows):
        nonlocal source, dest
        for _ in range(rows + 1):
            run(before_seam if wraps else BLIT_LONGWORDS)
            if wraps:
                # `lea -128(a0),a0` — back to the START of the same source row, not the next one.
                source = (source - BUFFER_LINE) & 0xffffffff
                run(BLIT_LONGWORDS - before_seam)
            dest = (dest + SCREEN_LINE - BLIT_ROW_BYTES) & 0xffffffff
            source = (source + CELL_BYTES + (BUFFER_LINE if wraps else 0)) & 0xffffffff

    scanlines(first_rows)
    if s16(second_rows) >= 0:
        source = (source - BUFFER_LEN) & 0xffffffff
        scanlines(second_rows)
    return out, (read_lo, read_hi)


def _model_blit(image):
    """$82f8 end to end, dispatcher and variant together."""
    return _model_blit_copy(image, *_blit_geometry(image))


# --- glue -------------------------------------------------------------------------------------------
_BLIT = leaf.image_glue("bg_scroll_blit")
_COPY_COLUMN = leaf.register_glue("bg_scroll_copy_column", [ctypes.c_uint32] * 5)


# --- what the jump table is, and that the family really is one pattern ------------------------------

def test_the_blit_table_names_the_sixteen_variants_and_they_tile_the_region():
    """The table is DATA the original jumps through, so its sixteen longwords are read off the image
    and required to be the sixteen entry points ../names.txt gives — and to tile $83b6..$8dfe with
    no gap and no overlap, which is what makes "the family is exactly these sixteen" a reading
    rather than a boundary someone chose."""
    entries = [_u32(harness.BASE_IMAGE, BLIT_TABLE + column * LONGWORD_LEN)
               for column in range(BLIT_VARIANTS)]
    named = [leaf.entry_of(variant_name(column)) for column in range(BLIT_VARIANTS)]
    assert entries == named, (
        f"the table holds {[hex(a) for a in entries]}, not the {[hex(a) for a in named]} "
        f"../names.txt names")

    for column in range(BLIT_VARIANTS - 1):
        body = len(ENTRY_BYTES[variant_name(column)])
        assert entries[column] + body == entries[column + 1], (
            f"variant {column} is {body} bytes from {entries[column]:#x} and variant {column + 1} "
            f"starts at {entries[column + 1]:#x} — the family does not tile")

    # The last variant has no successor to butt against, so its end is pinned against the address
    # the family is documented to reach — not against itself, which no arrangement of bytes fails.
    last = variant_name(BLIT_VARIANTS - 1)
    family_end = entries[BLIT_VARIANTS - 1] + len(ENTRY_BYTES[last])
    assert family_end == BLIT_FAMILY_END, (
        f"{last} ends at {family_end:#x}, so the family is not the {BLIT_FAMILY_END:#x} region "
        f"../names.txt and include/wonderboy.h both describe")

    # ...and the table itself begins where the dispatcher's body ends, so nothing falls into it.
    assert BLIT_TABLE == leaf.entry_of("bg_scroll_blit") + len(ENTRY_BYTES["bg_scroll_blit"])


def test_the_table_is_the_only_thing_that_names_a_variant():
    """A whole-image abs.l scan: each variant's address occurs exactly ONCE, in its own table entry,
    and WB_BG_BLIT_TABLE itself exactly once, in the dispatcher's `lea`. Together those two readings
    are why one `column` argument can stand in for the original's computed jump — there is no other
    way into the family, and no other reader of the table."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    wanted = {longword(leaf.entry_of(variant_name(column))): variant_name(column)
              for column in range(BLIT_VARIANTS)}
    wanted[longword(BLIT_TABLE)] = "the table itself"

    sites = {name: [] for name in wanted.values()}
    for at in range(0, len(program) - LONGWORD_LEN, STATE_WORD_LEN):
        name = wanted.get(program[at:at + LONGWORD_LEN])
        if name is not None:
            sites[name].append(at)

    for column in range(BLIT_VARIANTS):
        name = variant_name(column)
        assert sites[name] == [BLIT_TABLE + column * LONGWORD_LEN], (
            f"{name} @ {leaf.entry_of(name):#x} is named at {[hex(a) for a in sites[name]]}, not "
            f"only by its own table entry")
    dispatcher = leaf.entry_of("bg_scroll_blit")
    named_at = sites["the table itself"]
    assert len(named_at) == 1 and dispatcher <= named_at[0] < dispatcher + len(
        ENTRY_BYTES["bg_scroll_blit"]), (
        f"the jump table is named at {[hex(a) for a in named_at]}, which is not the single "
        f"reference inside bg_scroll_blit's own body that its `lea $8366.l,a2` is")


# Everything the image does to WB_BG_SCROLL_X, read off ../out/wonderboy_dis.txt. The two `move.w`
# forms are the two registers it is read into; the `cmpi.w` is the right-hand fill's wrap test and
# the `tst.w` the left-hand one's, which is why the compared value comes from RIGHT rather than
# from a literal here.
SCROLL_X_STEPS = (subq_w_abs_l(1, SCROLL_X), addq_w_abs_l(1, SCROLL_X))
SCROLL_X_MASK = andi_w_abs_l(PHASE_MASK, SCROLL_X)
SCROLL_X_CLEAR = clr_w_abs_l(SCROLL_X)
SCROLL_X_READS = (move_w_abs_l_dn(D0, SCROLL_X), move_w_abs_l_dn(D7, SCROLL_X),
                  tst_w_abs_l(SCROLL_X), cmpi_w_abs_l(RIGHT.wrap_at_scroll_x, SCROLL_X))
SCROLL_X_ENCODINGS = (*SCROLL_X_STEPS, SCROLL_X_MASK, SCROLL_X_CLEAR, *SCROLL_X_READS)

# An `abs.w` operand is sign-extended, so a word can only name an address below this one.
ABS_W_REACH = 0x8000


def _scroll_x_instruction_ending_at(program, past_operand):
    """(address, encoding) of whichever WB_BG_SCROLL_X instruction ends at `past_operand`, or None.

    All of them carry the operand LAST, so the candidates are told apart by the words in FRONT of
    it and at most one can match.
    """
    for encoding in SCROLL_X_ENCODINGS:
        at = past_operand - len(encoding)
        if program[at:past_operand] == encoding:
            return at, encoding
    return None


def test_the_column_is_a_nibble_wherever_the_image_writes_it():
    """The domain 0..15 that `bg_scroll_copy_column`'s `column` argument stands on, scanned for
    rather than read off the two steps this battery happens to run.

    `movea.l (0,a2,d1.w),a2` bounds nothing, so what keeps the dispatched jump inside the table is
    WB_BG_SCROLL_X's own range — a claim about every writer in the IMAGE. Every even-aligned abs.l
    reference to the word is found and matched against the encodings the disassembly shows, and the
    ones that write it are required to be exactly three: a `subq.w #1` and an `addq.w #1`, each
    immediately followed by its own `andi.w #$f`, and the `clr.w` at $fb7e.

    The two limits test_copylock.py's sweep states apply here too. `abs.w` cannot reach the word at
    all — it is above $8000, so a word operand would sign-extend into $ffffxxxx — which is asserted
    rather than argued; and a register-indirect write would be invisible to this or to any operand
    scan (PORTABILITY.md §2).
    """
    assert SCROLL_X >= ABS_W_REACH, (
        f"{SCROLL_X:#x} is inside an abs.w's reach, so this abs.l-only scan is not the whole image")

    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    operand = longword(SCROLL_X)
    writers = {}
    for at in range(0, len(program) - LONGWORD_LEN, STATE_WORD_LEN):
        if program[at:at + LONGWORD_LEN] != operand:
            continue
        found = _scroll_x_instruction_ending_at(program, at + LONGWORD_LEN)
        assert found is not None, (
            f"{SCROLL_X:#x} is named at {at:#x} by an instruction outside the ones "
            f"../out/wonderboy_dis.txt shows, so what it can hold is no longer established")
        site, encoding = found
        if encoding not in SCROLL_X_READS:
            writers[site] = encoding

    stepped = {site: enc for site, enc in writers.items() if enc in SCROLL_X_STEPS}
    masks = {site for site, enc in writers.items() if enc == SCROLL_X_MASK}
    cleared = {site for site, enc in writers.items() if enc == SCROLL_X_CLEAR}

    assert set(stepped.values()) == set(SCROLL_X_STEPS) and len(stepped) == len(SCROLL_X_STEPS), (
        f"the word is stepped at {sorted(hex(a) for a in stepped)}, which is not one `subq.w #1` "
        f"and one `addq.w #1`")
    assert len(cleared) == 1, (
        f"the word is cleared at {sorted(hex(a) for a in cleared)}, not at the one `clr.w` $fb7e")
    assert masks == {site + len(enc) for site, enc in stepped.items()}, (
        f"the `andi.w #${PHASE_MASK:x}`s are at {sorted(hex(a) for a in masks)} and the steps end "
        f"at {sorted(hex(a + len(e)) for a, e in stepped.items())} — a step that is not masked "
        f"immediately after can put the column outside 0..{PHASE_MASK}")


@pytest.mark.parametrize("column,body", [
    (0, "22d8" * 30 + "43e90028" + "5088" + "51cfffbc"
        + "4a46" + "6a000004" + "4e75" + "41e8a800"
        + "22d8" * 30 + "43e90028" + "5088" + "51ceffbc" + "4e75"),
    (2, "22d8" * 28 + "41e8ff80" + "22d8" * 2 + "43e90028" + "41e80088" + "51cfffb6"
        + "4a46" + "6a000004" + "4e75" + "41e8a800"
        + "22d8" * 28 + "41e8ff80" + "22d8" * 2 + "43e90028" + "41e80088" + "51ceffb6" + "4e75"),
    (15, "22d8" * 2 + "41e8ff80" + "22d8" * 28 + "43e90028" + "41e80088" + "51cfffb6"
         + "4a46" + "6a000004" + "4e75" + "41e8a800"
         + "22d8" * 2 + "41e8ff80" + "22d8" * 28 + "43e90028" + "41e80088" + "51ceffb6" + "4e75"),
], ids=["x0", "x2", "x15"])
def test_three_variants_are_the_bytes_the_disassembly_shows(column, body):
    """Three of the sixteen transcribed straight out of ../out/wonderboy_dis.txt.

    Every other pin in this battery is built from `_blit_variant_half`, so a pattern that was wrong
    in the same way twice would pass them all. These are the ones that fix the pattern itself: the
    first variant (no seam), the first that needs one, and the last, whose seam is at the other end.
    """
    assert ENTRY_BYTES[variant_name(column)].hex() == body


def test_the_consumer_tiers_derived_geometry_is_what_the_numbers_say():
    """The constants include/wonderboy.h states as literals with their derivation in a comment."""
    assert BLIT_ROW_BYTES == BLIT_LONGWORDS * LONGWORD_LEN
    assert ROW_LONGWORDS == BUFFER_LINE // LONGWORD_LEN
    assert CELL_LONGWORDS == CELL_BYTES // LONGWORD_LEN
    assert BUFFER_SCANLINES == BUFFER_LEN // BUFFER_LINE
    assert BLIT_WRAP_ROW == BUFFER_SCANLINES - BLIT_SCANLINES
    assert BLIT_ROW_SHIFT == _shift_for(BUFFER_LINE)
    assert BLIT_VARIANTS == PHASE_MASK + 1, "the table's extent is not bg_scroll_x's whole range"
    # ...and what an unbounded index would reach past the end of it: bg_scroll_x's own word.
    assert BLIT_TABLE + BLIT_VARIANTS * LONGWORD_LEN == SCROLL_X
    # The window fits the screen it is copied into: 240 px across from 64, 160 rows from row 32.
    assert BLIT_SCREEN_ORIGIN % SCREEN_LINE + BLIT_ROW_BYTES <= SCREEN_LINE
    assert BLIT_SCREEN_ORIGIN + BLIT_SCANLINES * SCREEN_LINE <= SCREEN_BUFFERS[1] - SCREEN_BUFFERS[0]


def test_the_two_halves_always_copy_the_windows_own_height():
    """Over EVERY ring row the game's own vertical steps can produce.

    The `bpl` arm and the computed arm are different code, and the claim that binds them is that
    both copy exactly WB_BG_BLIT_SCANLINES scanlines — which is also why no `dbf` count here can run
    away. A statement about the MODEL, which every case below pins against the original byte for
    byte; running eighty-eight more oracle passes would say nothing this does not.
    """
    image = bytearray(harness.make_image({PHASE: word(0), SCROLL_X: word(0),
                                          SCREEN_BACK: longword(SCREEN_BUFFERS[0])}))
    for row in range(0, SCROLL_Y_LAST + 1, SCROLL_STEP):
        image[SCROLL_Y:SCROLL_Y + STATE_WORD_LEN] = word(row)
        _column, _source, _dest, first, second = _blit_geometry(image)
        copied = (first + 1) + (second + 1 if s16(second) >= 0 else 0)
        assert copied == BLIT_SCANLINES, (
            f"ring row {row:#x} copies {copied} scanlines, not the window's {BLIT_SCANLINES}")
        assert first < BLIT_SCANLINES and s16(second) < BLIT_SCANLINES


# --- one variant on its own, entered where the jump table would enter it ----------------------------
# The registers the dispatcher hands over: a0 = source, a1 = destination, d7 = the first half's
# count, d6 = the second's. Four scanlines to the source buffer's end and two past the rewind — the
# real geometry in miniature, so every variant runs BOTH of its halves for a few hundred bytes.
VARIANT_FIRST_ROWS = 3
VARIANT_SECOND_ROWS = 1
VARIANT_PHASE = 8
VARIANT_START_ROW = BUFFER_SCANLINES - (VARIANT_FIRST_ROWS + 1)


def _run_variant(column, first_rows, second_rows, start_row, salt):
    pokes = _blit_pokes(VARIANT_PHASE, column, start_row, salt)
    image = harness.make_image(pokes)
    source = (BUFFER_BASE + VARIANT_PHASE * BUFFER_PHASE_STRIDE + start_row * BUFFER_LINE
              + column * CELL_BYTES)
    dest = SCREEN_BUFFERS[0] + BLIT_SCREEN_ORIGIN
    expected, _span = _model_blit_copy(image, column, source, dest, first_rows, second_rows)

    what = (f"{variant_name(column)} from row {start_row:#x}, {first_rows + 1} + "
            f"{second_rows + 1 if s16(second_rows) >= 0 else 0} scanlines")
    return _run_modelled(variant_name(column), _COPY_COLUMN(column, source, dest, first_rows,
                                                            second_rows),
                         expected, what, BLIT_INSN_CAP,
                         regs={"_pokes": pokes, "a0": source, "a1": dest,
                               "d7": first_rows, "d6": second_rows})


@pytest.mark.parametrize("column", range(BLIT_VARIANTS))
def test_every_copy_variant_moves_the_scanlines_its_own_seam_splits(column):
    """One case per variant, entered AT the variant. Columns 0 and 1 copy each scanline in one run;
    the other fourteen rewind a whole source row mid-scanline, at a point that moves two longwords
    further along with every column — which is the only thing that distinguishes them."""
    _run_variant(column, VARIANT_FIRST_ROWS, VARIANT_SECOND_ROWS, VARIANT_START_ROW,
                 salt=case_salt(f"variant-{column}"))


@pytest.mark.parametrize("column", [0, 1, 2, PHASE_MASK])
def test_a_copy_variant_stops_at_its_first_half_when_the_second_count_is_negative(column):
    """`tst.w d6 / bpl / rts`: the marker the dispatcher's non-wrapping arm loads ends the copy
    there, so the `lea -$5800(a0),a0` rewind never happens and no second half is drawn."""
    _run_variant(column, VARIANT_FIRST_ROWS, BLIT_NO_SECOND_HALF, 0x20,
                 salt=case_salt(f"variant-{column}-first-half-only"))


def test_a_copy_variants_second_half_starts_one_whole_buffer_back():
    """The rewind, stated as an address rather than inferred from the pixels: the first half ends
    past the buffer's last scanline and the second resumes at the SAME column of its first."""
    column = 5
    source = (BUFFER_BASE + VARIANT_PHASE * BUFFER_PHASE_STRIDE
              + VARIANT_START_ROW * BUFFER_LINE + column * CELL_BYTES)
    pokes = _blit_pokes(VARIANT_PHASE, column, VARIANT_START_ROW, salt=case_salt("variant-rewind"))
    image = harness.make_image(pokes)
    _writes, (read_lo, read_hi) = _model_blit_copy(image, column, source,
                                                   SCREEN_BUFFERS[0] + BLIT_SCREEN_ORIGIN,
                                                   VARIANT_FIRST_ROWS, VARIANT_SECOND_ROWS)
    buffer_lo = BUFFER_BASE + VARIANT_PHASE * BUFFER_PHASE_STRIDE
    assert read_lo == buffer_lo, (
        f"the second half read from {read_lo:#x}, not the buffer's own first scanline "
        f"{buffer_lo:#x} — the rewind is not one whole buffer")
    assert read_hi <= buffer_lo + BUFFER_LEN


# --- the whole thing, through the jump table --------------------------------------------------------
# Each case names the three words that place the copy: the phase (which of the eight buffers), the
# ring row (where the window starts, and so how the two halves split) and bg_scroll_x (which variant
# the table reaches, and so where each scanline's seam falls).
BLIT_CASES = [
    ("phase0-x0-row0", 0, 0, 0),
    ("phase14-x15-row0", PHASE_LAST, PHASE_MASK, 0),
    ("x1-just-below-the-wrap", 8, 1, BLIT_WRAP_ROW - SCROLL_STEP),
    ("x2-exactly-at-the-wrap", 8, 2, BLIT_WRAP_ROW),
    ("x5-one-row-past-the-wrap", 8, 5, BLIT_WRAP_ROW + SCROLL_STEP),
    ("x5-mid-ring", 8, 5, 0x40),
    ("x15-at-the-last-ring-row", PHASE_LAST, PHASE_MASK, SCROLL_Y_LAST),
    ("x0-at-the-last-ring-row", 0, 0, SCROLL_Y_LAST),
]


def _run_blit(case, phase, scroll_x, row, screen=SCREEN_BUFFERS[0]):
    pokes = _blit_pokes(phase, scroll_x, row, salt=case_salt(case), screen=screen)
    image = harness.make_image(pokes)
    expected, span = _model_blit(image)
    _run_modelled("bg_scroll_blit", _BLIT, expected, f"bg_scroll_blit {case}", BLIT_INSN_CAP,
                  regs={"_pokes": pokes})
    return image, expected, span


@pytest.mark.parametrize("case,phase,scroll_x,row", BLIT_CASES, ids=[c[0] for c in BLIT_CASES])
def test_a_blit_copies_the_window_the_three_position_words_place(case, phase, scroll_x, row):
    _run_blit(case, phase, scroll_x, row)


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
def test_a_blit_draws_into_whichever_buffer_screen_back_names(screen):
    """The destination comes out of MEMORY (`movea.l $750.w,a1`), so both buffers are run: a
    reconstruction that hardcoded one would pass on the other's case and fail here."""
    _run_blit(f"screen-{screen:#x}", phase=8, scroll_x=5, row=0x40, screen=screen)


def test_the_wrap_test_reads_the_wrapped_signs_and_not_the_row_against_the_boundary():
    """`subi.w #$10,d6 / bpl` tests the sign of the WRAPPED difference, because `bpl` reads N alone
    — where bg_scroll_raise_requests' `bgt`/`blt` read N xor V (STATUS.md, batch 6). The two
    readings of the same instruction pair agree on every row the game itself produces, and this is
    the case that separates them.

    WB_BG_SCROLL_Y has exactly three writers in the whole image — the two vertical steps, which keep
    it on the 0..$ae grid, and the `clr.w` at $fb84 — so the range they part company over ($8010 and
    up) is out of the game's reach. Most of it is out of the HARNESS's reach as well, since the same
    word feeds `move.w #$b0,d7 / sub.w`: a row of $8010 asks for 32,928 scanlines and walks off the
    image. A row of $fffe does not. The wrapped-sign reading copies the window's own 160 scanlines
    from two scanlines before the buffer; the boundary reading takes the other arm and copies 178.
    Seeded rather than argued about, and named for the out-of-range row it is.
    """
    _run_blit("ring-row-below-zero", phase=8, scroll_x=5, row=(0 - SCROLL_STEP) & 0xffff)


def test_a_blit_writes_exactly_the_visible_window():
    """The write set stated as a rectangle rather than as whatever the model produced: 160 scanlines
    of 120 bytes, one WB_SCREEN_LINE apart, from WB_SCREEN_BACK + $1420 — so the 40 bytes between
    the end of one row and the start of the next are pinned as NOT written."""
    _image, expected, _span = _run_blit("window-geometry", phase=8, scroll_x=5, row=0x40)
    window = {SCREEN_BUFFERS[0] + BLIT_SCREEN_ORIGIN + scanline * SCREEN_LINE + byte
              for scanline in range(BLIT_SCANLINES) for byte in range(BLIT_ROW_BYTES)}
    assert set(expected) == window, (
        f"the blit wrote {len(expected)} bytes against the window's {len(window)} — first "
        f"difference at {min(set(expected) ^ window):#x}")


@pytest.mark.parametrize("case,phase,scroll_x,row", BLIT_CASES, ids=[c[0] for c in BLIT_CASES])
def test_a_blit_reads_only_the_buffer_its_phase_names(case, phase, scroll_x, row):
    """Both rings, from the source side: whatever the row and the column, the walk stays inside one
    $5800 buffer. A copy that chained by the wrong stride, or rewound by a row where it should have
    rewound by a buffer, leaves it.

    Read off the MODEL, whose every written byte the case above pins against the original — the
    oracle reports what a run WROTE and has no read set to compare against, so a second oracle pass
    here would add nothing.
    """
    image = harness.make_image(_blit_pokes(phase, scroll_x, row, salt=case_salt(case)))
    _writes, (read_lo, read_hi) = _model_blit(image)
    buffer_lo = BUFFER_BASE + phase * BUFFER_PHASE_STRIDE
    assert buffer_lo <= read_lo and read_hi <= buffer_lo + BUFFER_LEN, (
        f"{case}: the copy read ${read_lo:x}..${read_hi:x}, which is not inside the buffer "
        f"${buffer_lo:x}..${buffer_lo + BUFFER_LEN:x} the phase names")
