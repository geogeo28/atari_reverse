"""Differential test for the six horizontal routines of src/scroll.c.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte over the whole image, and bounds the original's write set.
For the two column fills it goes further: the write set is compared for EQUALITY against the exact
cell addresses the geometry gives, and every written byte against a Python model of the fill built
from the disassembly — so a case says which bytes moved and where to, not only that both sides
agree.

THREE THINGS MAKE THIS BATTERY DIFFERENT FROM test_hud.py's.

  * THE STEPS RETURN THROUGH THE STACK. `bg_scroll_step_right`/`_left` decide whether their caller's
    fill happens by adding to their own return address (`addq.l #4,(a7)`), so the oracle's `rts`
    lands four bytes PAST the sentinel and the run has to be given that address as a second stop PC
    (leaf.run's `stop_pc`). The decision is then read back off the oracle's OWN STACK — the skipped
    arm leaves sentinel+4 at STACK_TOP and the other arm never writes there — and compared against
    the flag the C returns. Neither side is trusted to report it.
  * NOTHING IS SEEDED FROM A CONSTANT THE CODE ALSO USES. The map, its row stride and the 256-word
    tile index all live PAST the end of the program ($218d0), so a fresh image has them zero and
    every case builds them. The tile BITMAPS are shipped in the .PRG and are used as they are,
    which is what keeps the fills' source non-zero.
  * THE DESTINATION IS SEEDED WITH A MARGIN, address-keyed. A column fill is a read-modify-write
    over a buffer, so a fill that ran one row too far would `and` or `or` bytes that a zeroed image
    leaves indistinguishable — the hole batch 4's mutation sweep found and docs/methodology.md
    writes up. Every case fills the whole $5800 buffer PLUS a scanline either side with a byte
    derived from the ADDRESS, so an over-run changes something, and the write-set equality above
    catches the same fault from the other direction.

KNOWINGLY NOT PINNED
  * THE REGISTERS THE FILLS LEAVE BEHIND. Both walk out with every address register far past where
    it started; the oracle reports d0/d1/a0/a1 only, and both call sites `rts` immediately after.
  * THE 65536-ITERATION `dbf`. Both fills take their two lengths from bg_scroll_col_split_table,
    whose first words are 10 down to 0 — no seeding through bg_scroll_y_coarse can produce a
    negative first count, because the table is the game's own data and a case that rewrote it would
    be pinning an invented record. Reproduced by construction in src/scroll.c and left unreached.
  * WHAT THE SCROLL IS FOR. ../names.txt names these for their mechanism; that the two fills are
    the left and right edges of a visible window is read off their map offsets being fifteen cells
    apart, not proved here.
"""
import ctypes
import zlib

import pytest

import harness
import leaf
from leaf import RTS, backward_branch, bsr_w, forward_branch, longword, word
from layout import wb

import emu   # noqa: E402  (harness puts the kit's oracle on sys.path)

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
REQUEST_LEFT = wb("BG_REQUEST_LEFT")
REQUEST_RIGHT = wb("BG_REQUEST_RIGHT")
STATE_WORD_LEN = wb("BG_STATE_WORD_LEN")

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

WORD_BITS = 16
LONG_BITS = 32
LONGWORD_LEN = 4

# The rotation the right edge substitutes for a phase of zero: a whole 16-pixel cell.
FULL_CELL_ROTATION = 16

# `addq.l #4,(a7)` — what a step adds to its own return address to consume its caller's `bsr`.
STEP_SKIP_BYTES = 4

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

# A step is straight-line; a serve is a step and a fill under one entry.
STEP_INSN_CAP = leaf.LEAF_INSN_CAP
SERVE_INSN_CAP = FILL_INSN_CAP + STEP_INSN_CAP


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

def _u16(image, addr):
    return int.from_bytes(bytes(image[addr:addr + STATE_WORD_LEN]), "big")


def _s16(value):
    value &= 0xffff
    return value - 0x10000 if value & 0x8000 else value


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


def _keyed_byte(addr, salt):
    """A byte derived from the ADDRESS, not from a row index.

    Batch 4's restore walk learned this the hard way: two widened bands that overlap let an
    index-keyed filler silently rewrite the earlier one, and the case then passes on bytes it did
    not mean to seed. Keyed on the address, an over-run lands on a byte that is wrong for where it
    was written.
    """
    mixed = (addr * 0x9d) ^ (addr >> 5) ^ (salt * 0x4f1b)
    return (mixed ^ (mixed >> 8)) & 0xff


def _keyed_block(base, length, salt):
    return bytes(_keyed_byte(base + i, salt) for i in range(length))


def _case_salt(case):
    """A salt derived from the case's NAME, and derived reproducibly.

    Python's `hash()` of a string is randomised per process unless PYTHONHASHSEED is pinned, which
    nothing here pins — seeding from it would give every run a different image, so a failure could
    not be replayed from its case id and a mutation sweep's red count could move between sweeps
    without the code changing. `crc32` is the same number in every process.
    """
    return zlib.crc32(case.encode()) & 0xff


def _scroll_pokes(phase, scroll_x, y_coarse, map_cursor=MAP_CURSOR_SEED, salt=0):
    """The image a fill case runs on: the four position words, the map and its stride, the whole
    tile index, and the phase's buffer widened by a scanline either side."""
    buffer_base = BUFFER_BASE + phase * BUFFER_PHASE_STRIDE
    band_lo = buffer_base - BUFFER_MARGIN
    pokes = {
        PHASE: word(phase),
        SCROLL_X: word(scroll_x),
        Y_COARSE: word(y_coarse),
        MAP_CURSOR: word(map_cursor),
        MAP_ROW_STRIDE: word(MAP_STRIDE_SEED),
        MAP_DATA: _keyed_block(MAP_DATA, MAP_SEED_LEN, salt + 1),
        TILE_INDEX_TABLE: b"".join(
            word(TILE_SHIPPED_FIRST + _keyed_byte(TILE_INDEX_TABLE + i, salt + 2)
                 % TILE_SHIPPED_COUNT)
            for i in range(TILE_INDEX_ENTRIES)),
        band_lo: _keyed_block(band_lo, BUFFER_LEN + 2 * BUFFER_MARGIN, salt + 3),
    }
    return pokes


# --- the model ------------------------------------------------------------------------------------

def _model_fill(image, edge):
    """The column fill, walked in Python over the seeded image. Returns {address: final byte}.

    Written from the disassembly rather than from src/scroll.c: it is the third statement of the
    same geometry, and the one that lets a case say WHICH bytes moved.
    """
    phase = _u16(image, PHASE)
    scroll_x = _u16(image, SCROLL_X)
    coarse = _u16(image, Y_COARSE)

    cleared = (BUFFER_BASE + phase * BUFFER_PHASE_STRIDE + coarse * TILE_BLOCK_LEN
               + _s16(((scroll_x + edge.x_bias) & PHASE_MASK) * CELL_BYTES)) & 0xffffffff
    ored = cleared
    written = (cleared + edge.second_cell) & 0xffffffff
    if scroll_x == edge.wrap_at_scroll_x:
        written = (written + edge.wrap_delta) & 0xffffffff

    counts = bytes(image[COL_SPLIT_TABLE + coarse * LONGWORD_LEN:][:LONGWORD_LEN])
    out = {FILL_COUNTS + i: counts[i] for i in range(LONGWORD_LEN)}
    first = int.from_bytes(counts[:STATE_WORD_LEN], "big")
    second = int.from_bytes(counts[STATE_WORD_LEN:], "big")

    half = _u16(image, EDGE_MASK_TABLE + phase)
    mask = (half << WORD_BITS) | half
    if edge.invert_mask and phase != 0:
        mask ^= 0xffffffff

    map_cursor = (MAP_DATA + _s16(_u16(image, MAP_CURSOR) + edge.map_offset)) & 0xffffffff

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
        stride = _s16(_u16(image, MAP_ROW_STRIDE))
        for _ in range(tile_rows + 1):
            tile_number = _u16(image, TILE_INDEX_TABLE + image[map_at] * STATE_WORD_LEN)
            tile = (TILE_BITMAPS + tile_number * TILE_BITMAP_LEN) & 0xffffffff
            map_at = (map_at + stride) & 0xffffffff
            for _row in range(TILE_ROWS):
                rotated = [_rol32(_u16(image, tile + plane * PLANE_STRIDE), shift)
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
    if _s16(second) < 0:
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
D0, D4, D5, D6, D7 = 0, 4, 5, 6, 7


def _op(value):
    return value.to_bytes(2, "big")


def lea_abs_l(reg, addr):
    return _op(0x41f9 | (reg << 9)) + longword(addr)


def lea_d16(reg, displacement):
    """`lea d16(An),An` — every one of these advances the register it reads."""
    return _op(0x41e8 | (reg << 9) | reg) + word(displacement)


def lea_indexed(reg, index, longword_index=False):
    """`lea (0,An,Dn.w),An` — likewise, and the extension word is the whole of the index encoding."""
    return _op(0x41f0 | (reg << 9) | reg) + word((index << 12) | (0x800 if longword_index else 0))


def move_w_indexed_d0(base, index):
    """`move.w (0,An,Dn.w),d0` — how a fill reads a word out of a table it just indexed."""
    return _op(0x3030 | base) + word(index << 12)


def move_w_abs_l_dn(reg, addr):
    return _op(0x3039 | (reg << 9)) + longword(addr)


def move_w_dn_abs_l(reg, addr):
    return _op(0x33c0 | reg) + longword(addr)


def move_w_imm_dn(reg, value):
    return _op(0x303c | (reg << 9)) + word(value)


def andi_w_abs_l(value, addr):
    return _op(0x0279) + word(value) + longword(addr)


def addi_w_dn(reg, value):
    return _op(0x0640 | reg) + word(value)


def andi_w_dn(reg, value):
    return _op(0x0240 | reg) + word(value)


def tst_w_abs_l(addr):
    return _op(0x4a79) + longword(addr)


def clr_w_abs_l(addr):
    return _op(0x4279) + longword(addr)


def clr_b_abs_l(addr):
    return _op(0x4239) + longword(addr)


def cmpi_w_abs_l(value, addr):
    return _op(0x0c79) + word(value) + longword(addr)


def addq_w_abs_l(amount, addr):
    return _op(0x5079 | ((amount & 7) << 9)) + longword(addr)


def subq_w_abs_l(amount, addr):
    return _op(0x5179 | ((amount & 7) << 9)) + longword(addr)


def addq_l_ind_a7(amount):
    return _op(0x5097 | ((amount & 7) << 9))


def branch_w(opcode, *over):
    """`bcc.w` past exactly ``over`` — leaf.forward_branch turns the pieces into the displacement."""
    return _op(opcode) + forward_branch(sum(len(piece) for piece in over))


def dbf(reg, *body):
    """`dbf Dn,<start of body>`: the displacement runs back over the body and the opcode word."""
    return _op(DBF_DN | reg) + backward_branch(sum(len(piece) for piece in body))


BNE_W, BEQ_W, BMI_W = 0x6600, 0x6700, 0x6b00
DBF_DN = 0x51c8
MOVEQ_0_D0 = _op(0x7000)
MULU_W_IMM_D0 = _op(0xc0fc)
ADDA_L_D0_A0 = _op(0xd1c0)
LSL_L_7_D0, LSL_L_4_D0, LSL_W_2_D0, ASL_W_3_D0 = _op(0xef88), _op(0xe988), _op(0xe548), _op(0xe740)
MOVEA_L_A0_A1, MOVEA_L_A0_A2 = _op(0x2248), _op(0x2448)
MOVE_W_POSTINC_A5_D0 = _op(0x301d)
MOVE_L_POSTINC_A5_ABS_L = _op(0x23dd)
MOVE_L_POSTINC_A5_ABS_W = _op(0x21dd)
MOVE_W_ABS_W_D7 = _op(0x3e38)
SWAP_D6, NOT_L_D6 = _op(0x4846), _op(0x4686)
MOVE_W_IND_A6_D6 = _op(0x3c16)
TST_W_D5 = _op(0x4a45)
MOVE_W_IMM_D5 = _op(0x3a3c)
AND_L_D6_POSTINC_A0 = _op(0xcd98)
MOVE_B_IND_A3_D0 = _op(0x1013)
ADD_W_D0_D0 = _op(0xd040)
ADDQ_W_2_D0 = _op(0x5440)
CMP_W_ABS_L_D0 = _op(0xb079)


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
    move_to_a2 = b"".join(_op(0x34c0 | reg) for reg in range(PLANES))
    or_to_a1 = b"".join(_op(0x8159 | (reg << 9)) for reg in range(PLANES))
    scanline = (
        MOVEQ_0_D0
        + b"".join(_op(0x2000 | (reg << 9)) for reg in (1, 2, 3))     # move.l d0,d1/d2/d3
        + b"".join(_op(0x301c | (reg << 9)) for reg in range(PLANES))  # move.w (a4)+,d0..d3
        + b"".join(_op(0xebb8 | reg) for reg in range(PLANES))         # rol.l d5,d0..d3
        + (or_to_a1 if or_takes_low_half else move_to_a2)
        + b"".join(_op(0x4840 | reg) for reg in range(PLANES))         # swap d0..d3
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
        second_cell_test = cmpi_w_abs_l(edge.wrap_at_scroll_x, SCROLL_X) + branch_w(BNE_W, wrap)
        map_offset = addi_w_dn(D0, edge.map_offset)
        invert = b""
    else:
        cell_index = andi_w_dn(D0, PHASE_MASK)
        second_cell_test = tst_w_abs_l(SCROLL_X) + branch_w(BNE_W, wrap)
        map_offset = ADDQ_W_2_D0
        invert = tst_w_abs_l(PHASE) + branch_w(BEQ_W, NOT_L_D6) + NOT_L_D6

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
        shift = (move_w_abs_l_dn(D5, PHASE) + TST_W_D5
                 + branch_w(BNE_W, MOVE_W_IMM_D5 + word(FULL_CELL_ROTATION),
                            lea_d16(A3, -1))
                 + MOVE_W_IMM_D5 + word(FULL_CELL_ROTATION) + lea_d16(A3, -1))
    else:
        shift = move_w_abs_l_dn(D5, PHASE)

    tiles = _tile_loop(edge.or_takes_low_half)
    rewind = (lea_d16(A0, -BUFFER_LEN) + lea_d16(A1, -BUFFER_LEN)
              + lea_d16(A2, -BUFFER_LEN))
    second_half = _clear_loop() + load_second + tiles
    return (head + load_first + _clear_loop() + shift + load_first + tiles
            + rewind + load_second + branch_w(BMI_W, second_half) + second_half + RTS)


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
                         + branch_w(BEQ_W, RTS) + RTS
                         + clr_w_abs_l(ROW_BYTE_OFFSET) + RTS)
_STEP_CELL_TAIL_LEFT = (subq_w_abs_l(1, MAP_CURSOR)
                        + subq_w_abs_l(CELL_BYTES, ROW_BYTE_OFFSET)
                        + andi_w_abs_l(ROW_OFFSET_MASK, ROW_BYTE_OFFSET)
                        + subq_w_abs_l(1, SCROLL_X) + andi_w_abs_l(PHASE_MASK, SCROLL_X)
                        + branch_w(BEQ_W, RTS) + RTS
                        + clr_w_abs_l(ROW_BYTE_OFFSET) + RTS)

_SKIP_AND_RETURN = addq_l_ind_a7(STEP_SKIP_BYTES) + RTS

STEP_BODIES = {
    "right": (move_w_abs_l_dn(D0, POS_X) + CMP_W_ABS_L_D0 + longword(LIMIT_X)
              + branch_w(BNE_W, _SKIP_AND_RETURN) + _SKIP_AND_RETURN
              + tst_w_abs_l(PENDING)
              + branch_w(BMI_W, leaf.MOVE_W_IMM_ABS_L + word(PENDING_SET) + longword(PENDING), RTS)
              + leaf.MOVE_W_IMM_ABS_L + word(PENDING_SET) + longword(PENDING) + RTS
              + addq_w_abs_l(SCROLL_STEP, POS_X)
              + addq_w_abs_l(SCROLL_STEP, PHASE) + andi_w_abs_l(PHASE_MASK, PHASE)
              + branch_w(BEQ_W, RTS) + RTS
              + _STEP_CELL_TAIL_RIGHT),
    "left": (move_w_abs_l_dn(D0, POS_X) + _op(0x4a40)                      # tst.w d0
             + branch_w(BNE_W, _SKIP_AND_RETURN) + _SKIP_AND_RETURN
             + tst_w_abs_l(PENDING)
             + branch_w(BEQ_W, clr_w_abs_l(PENDING), RTS) + clr_w_abs_l(PENDING) + RTS
             + subq_w_abs_l(SCROLL_STEP, POS_X)
             + subq_w_abs_l(SCROLL_STEP, PHASE)
             + branch_w(BMI_W, andi_w_abs_l(PHASE_MASK, PHASE), RTS)
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

ENTRY_BYTES = {
    "bg_scroll_fill_right_column": FILL_BODIES["right"],
    "bg_scroll_fill_left_column": FILL_BODIES["left"],
    "bg_scroll_step_right": STEP_BODIES["right"],
    "bg_scroll_step_left": STEP_BODIES["left"],
    "bg_scroll_serve_right": SERVE_BODIES["right"],
    "bg_scroll_serve_left": SERVE_BODIES["left"],
}
RECONSTRUCTED_ROUTINES = 6


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


def _program_writes(info):
    """The oracle's write set with the MACHINE STACK left out.

    A `bsr`'s pushed return address is not program output, and the equality assertions below compare
    against a model of what the routine draws. The band is leaf.on_machine_stack's, the same one
    leaf.stray_writes permits; this is the other side of it, for the cases that state the write set
    exactly rather than bound it. Its upper bound EXCLUDES the return slot at STACK_TOP, which is
    program output: it is what a step rewrites to consume its caller's `bsr`.
    """
    return {addr: value for addr, value in info["writes"].items() if not leaf.on_machine_stack(addr)}


def _oracle_skipped(info):
    """Whether the ORIGINAL consumed its caller's `bsr`, read off its own stack.

    `emu.run` writes the sentinel AT A7 rather than below it, so a step that did `addq.l #4,(a7)`
    has rewritten that longword and one that returned normally never wrote there at all.
    """
    if not all(RETURN_SLOT + i in info["writes"] for i in range(LONGWORD_LEN)):
        return False
    left = leaf.read_int(info, RETURN_SLOT, LONGWORD_LEN, "the step's own return address")
    assert left == emu.SENTINEL + STEP_SKIP_BYTES, (
        f"the original rewrote its return address to {left:#x}, which is neither the oracle's "
        f"sentinel {emu.SENTINEL:#x} nor that plus the {STEP_SKIP_BYTES}-byte skip")
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
        first = _u16(harness.BASE_IMAGE, at)
        second = _s16(_u16(harness.BASE_IMAGE, at + STATE_WORD_LEN))
        assert first == BUFFER_TILE_ROWS - 1 - index, f"entry {index}'s first count is {first}"
        assert second == index - 1, f"entry {index}'s second count is {second}"
        assert (first + 1) + (second + 1) == BUFFER_TILE_ROWS, (
            f"entry {index}'s two halves draw {(first + 1) + (second + 1)} tile rows, not the "
            f"buffer's {BUFFER_TILE_ROWS}")


def test_the_edge_masks_are_the_shifts_the_phase_names():
    """The eight words at bg_scroll_edge_masks, which decide how much of a cell a fill keeps."""
    assert _u16(harness.BASE_IMAGE, EDGE_MASK_TABLE) == 0, (
        "phase 0's mask is not $0000 — src/scroll.c's whole-cell redraw depends on it")
    for phase in range(SCROLL_STEP, PHASE_MASK + 1, SCROLL_STEP):
        expected = (0xffff << phase) & 0xffff
        assert _u16(harness.BASE_IMAGE, EDGE_MASK_TABLE + phase) == expected, (
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
    allowed = _merge(sorted(expected))

    what = f"{edge.routine} phase={phase} x={scroll_x} coarse={coarse}"
    info = leaf.run(edge.routine, _FILL[edge.routine], allowed, what,
                    regs={"_pokes": pokes}, max_insns=FILL_INSN_CAP)

    written = _program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {len(written)} bytes against the model's "
        f"{len(expected)} — first difference at {min(set(written) ^ set(expected)):#x}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")
    return info


def _merge(addresses):
    """Adjacent addresses collapsed into (start, length) bands, for leaf.run's `allowed`."""
    bands = []
    for addr in addresses:
        if bands and addr == bands[-1][0] + bands[-1][1]:
            bands[-1] = (bands[-1][0], bands[-1][1] + 1)
        else:
            bands.append((addr, 1))
    return bands


@pytest.mark.parametrize("edge", sorted(EDGES), ids=sorted(EDGES))
@pytest.mark.parametrize("case,phase,scroll_x,coarse", FILL_CASES,
                         ids=[case[0] for case in FILL_CASES])
def test_a_column_fill_draws_the_cells_the_geometry_names(edge, case, phase, scroll_x, coarse):
    _run_fill(EDGES[edge], phase, scroll_x, coarse, salt=_case_salt(case))


@pytest.mark.parametrize("edge", sorted(EDGES), ids=sorted(EDGES))
def test_a_column_fill_touches_exactly_one_buffers_worth_of_scanlines(edge):
    """The two halves always cover the buffer once over — 176 scanlines of one 8-byte cell for the
    cursor that is ORed and one for the cursor that is overwritten, plus the count scratch."""
    phase = 8
    info = _run_fill(EDGES[edge], phase=phase, scroll_x=5, coarse=4, salt=7)
    cells = sorted(a for a in _program_writes(info) if a >= BUFFER_BASE)
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
    allowed = [(addr, STATE_WORD_LEN) for addr in STEP_WRITABLE] + [(RETURN_SLOT, LONGWORD_LEN)]
    info = leaf.run(name, _step_glue(name, seen), allowed, what, regs={"_pokes": dict(pokes)},
                    max_insns=STEP_INSN_CAP, stop_pc=emu.SENTINEL + STEP_SKIP_BYTES)
    skipped = _oracle_skipped(info)
    assert bool(seen[0]) == skipped, (
        f"{what}: the reconstruction returned {seen[0]} while the original "
        f"{'skipped' if skipped else 'did not skip'} its caller's fill")
    return info, skipped


def _final(image, pokes, info, addr):
    """The word the original left at ``addr`` — from its write set when it wrote there, and from the
    seeded image when it did not, so a case can state the value either way."""
    if all(addr + i in info["writes"] for i in range(STATE_WORD_LEN)):
        return leaf.read_int(info, addr, STATE_WORD_LEN, "a scroll word")
    return _u16(image, addr)


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
    expected = _model_step_then_fill(image, served, pokes)
    allowed = _merge(sorted(expected))
    what = f"{served.serve} armed={armed}"
    info = leaf.run(served.serve, _FILL[served.serve], allowed, what,
                    regs={"_pokes": pokes}, max_insns=SERVE_INSN_CAP)
    written = _program_writes(info)
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
    written = _program_writes(info)
    assert set(written) == {served.request}
    assert written[served.request] == 0


def _model_step_then_fill(image, edge, pokes):
    """What a serve leaves behind: the step's own words, then the fill's, on the image the step left.

    The step is modelled here rather than reused from the step cases because the fill has to run on
    its OUTPUT — a serve that stepped and then filled from the pre-step phase would otherwise pass.
    """
    out = {}
    staged = bytearray(image)

    def put(addr, value):
        for i, byte in enumerate(word(value)):
            out[addr + i] = byte
            staged[addr + i] = byte

    # The request is a BYTE (`clr.b`), unlike every other write below — a word here would claim the
    # pass also touched the byte after it, which for $8233 is bg_scroll_tile_row.
    out[edge.request] = 0
    staged[edge.request] = 0

    if edge is RIGHT:
        assert _u16(staged, POS_X) != _u16(staged, LIMIT_X), "this model is for the moving arm"
        if _s16(_u16(staged, PENDING)) >= 0:
            put(PENDING, PENDING_SET)
        else:
            put(POS_X, (_u16(staged, POS_X) + SCROLL_STEP) & 0xffff)
            phase = (_u16(staged, PHASE) + SCROLL_STEP) & PHASE_MASK
            put(PHASE, phase)
            if phase == 0:
                put(ROW_BYTE_OFFSET, (_u16(staged, ROW_BYTE_OFFSET) + CELL_BYTES) & 0xffff)
                put(MAP_CURSOR, (_u16(staged, MAP_CURSOR) + 1) & 0xffff)
                column = (_u16(staged, SCROLL_X) + 1) & PHASE_MASK
                put(SCROLL_X, column)
                if column == 0:
                    put(ROW_BYTE_OFFSET, 0)
    else:
        assert _u16(staged, POS_X) != 0, "this model is for the moving arm"
        if _u16(staged, PENDING) != 0:
            put(PENDING, 0)
        else:
            put(POS_X, (_u16(staged, POS_X) - SCROLL_STEP) & 0xffff)
            phase = (_u16(staged, PHASE) - SCROLL_STEP) & 0xffff
            if _s16(phase) >= 0:
                put(PHASE, phase & PHASE_MASK)
            else:
                put(PHASE, PHASE_LAST)
                put(MAP_CURSOR, (_u16(staged, MAP_CURSOR) - 1) & 0xffff)
                put(ROW_BYTE_OFFSET,
                    ((_u16(staged, ROW_BYTE_OFFSET) - CELL_BYTES) & ROW_OFFSET_MASK))
                column = (_u16(staged, SCROLL_X) - 1) & PHASE_MASK
                put(SCROLL_X, column)
                if column == 0:
                    put(ROW_BYTE_OFFSET, 0)

    out.update(_model_fill(staged, edge))
    return out


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
