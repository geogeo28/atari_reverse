"""Differential test for src/stage.c — the STAGE LOADER: what fills the eight pre-shifted background
buffers once, as against src/scroll.c, which maintains them once a frame.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and bounds or states the write set.

WHAT MAKES THIS BATTERY DIFFERENT FROM THE OTHERS HERE.

  * THE DESTINATIONS ARE THE SCROLL ENGINE'S OWN BUFFERS, AND THE SEAM IS ASSERTED RATHER THAN
    ASSUMED. `test_the_published_row_pointers_are_the_scroll_engines_invariant` derives all sixteen
    longwords $fb06 writes from `WB_BG_BUFFER_BASE + copy * WB_BG_BUFFER_LEN + row *
    WB_BG_BUFFER_LINE` — the invariant scroll.c's vertical steps preserve — and requires the
    instruction bytes the .PRG ships to spell exactly those. So a disagreement between this tier and
    that one fails on the shipped image, not on a model.
  * THE SOURCE IS THE GAME'S OWN PIXELS. `bg_build_buffer`'s tiles come from WB_TILE_BITMAPS'
    shipped range (tiles WB_TILE_SHIPPED_FIRST..+16, the only ones in the .PRG — test_scroll.py
    pins that split) and the banner glyphs from WB_BG_BANNER_FONT, which is shipped whole. Nothing
    here invents a tile or a glyph, so a wrong plane order, a wrong source stride or a wrong glyph
    index stays visible.
  * THE INDEX TABLE IS SEEDED SO THAT EVERY BYTE IS SAFE. WB_TILE_INDEX_TABLE lies past the program
    and is loaded at run time, so a case seeds all 256 entries — and seeds them to shipped tiles, so
    a case that deliberately walks the map cursor OUT of the region it seeded (the two below that
    do) still reads a real bitmap on both sides instead of addressing off the image.
  * ONE ROUTINE IS ENTERED FROM MEMORY AND ONE FROM REGISTERS. $fb06 and $fd46 take no argument at
    all; $fa30 takes three pointers in a0/a1/a6 and the banner pair takes a0/a1/a6 as well, so those
    are `leaf.register_glue`d and the returned cursor is compared THREE ways — model, the oracle's
    own a1/a6, and the reconstruction's return.

KNOWINGLY NOT PINNED
  * $f95c, THE CALLER. It latches WB_STAGE_MAP_PTR / WB_STAGE_START_PTR, calls the three builders
    back to back, computes WB_SCROLL_FOLLOW_X/_Y, and then writes the shifter's palette through
    set_palette and calls the sound module at $17adc through `jsr (a1)`. Both of those are outside
    the harness, and the sound call is on the UNCONDITIONAL path. So the hand-over from $f95c to
    the three routines below is stated by their own entry conventions, not by a run through it.
  * WHAT THE BUILDERS LEAVE IN THEIR REGISTERS. $fa30 walks out with a0/a1/a2/a5/a6 and d0-d7 well
    past where they started and $fd46 the same; $f95c reloads everything it needs from
    WB_STAGE_START_PTR. The oracle reports them all since batch 11 — what is missing is a
    reconstruction that models them, not an observer — so this is openable rather than blocked. The
    banner pair is the exception: its cursor IS the output and is asserted per case.
  * WHAT $fe1e's TABLE HOLDS. Only the FIRST longword of each 20-byte record is touched, and the
    other sixteen bytes are neither read nor named. The count word and the records are past the
    program (loaded from disk), so every case seeds them as plain RAM.
  * A BANNER CHARACTER BELOW WB_TEXT_FIRST_GLYPH_CHAR. `subi.b #$20,d0` is a BYTE subtract, so such
    a character would wrap and index the far end of the font. The two records the image ships are
    ASCII and neither reaches it; reaching it means fabricating a record, which is the thing
    CLAUDE.md's coverage rule refuses. Reproduced by construction (the port's index is a `uint8_t`)
    and left honestly unpinned.
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (RTS, add_w_dn_dn, branch, branch_over, bsr_w, btst_imm_dn, case_salt,
                  clr_w_abs_l,
                  dbf_over, forward_branch, keyed_block, lea_abs_l, lea_d16, lea_indexed, longword,
                  lsl_w_imm_dn, merge_bands, move_l_imm_abs_l, move_l_imm_postinc, move_w_abs_l_dn,
                  move_w_dn_dn, move_w_imm_dn, move_w_postinc_dn, movea_l_abs_l, moveq_0_dn,
                  opcode, program_writes, st_abs_l, subi_w_dn, swap_dn, tst_w_abs_l, u16, s16,
                  word)
from layout import wb
# `game_life_restart_reset` CALLS hud_draw_lives, so its write set CONTAINS that routine's.
# The geometry and the model are imported from the battery that owns them rather than
# restated here: two copies could disagree and both batteries would still pass.
from test_hud import LIVES_INSN_CAP, lives_pokes, model_lives_draw   # noqa: E402

# --- the geometry, from the header both languages read -------------------------------------------
BUFFER_BASE = wb("BG_BUFFER_BASE")
BUFFER_LEN = wb("BG_BUFFER_LEN")
BUFFER_LINE = wb("BG_BUFFER_LINE")
BUFFERS = wb("BG_BUFFERS")
CELL_BYTES = wb("BG_CELL_BYTES")
TILE_ROWS = wb("BG_TILE_ROWS")
TILE_BLOCK_LEN = wb("BG_TILE_BLOCK_LEN")
BUFFER_ROWS = wb("BG_BUFFER_ROWS")
BUFFER_ROW_TOP = wb("BG_BUFFER_ROW_TOP")
BUFFER_ROW_BOTTOM = wb("BG_BUFFER_ROW_BOTTOM")
BUFFER_ROW_PAIR = wb("BG_BUFFER_ROW_PAIR")
PRESHIFT_BITS = wb("BG_PRESHIFT_BITS")
PRESHIFT_CARRY = wb("BG_PRESHIFT_CARRY")
STATE_WORD_LEN = wb("BG_STATE_WORD_LEN")
PLANES = wb("PLANES")
PLANE_STRIDE = wb("PLANE_STRIDE")

TILE_BITMAPS = wb("TILE_BITMAPS")
TILE_BITMAP_LEN = wb("TILE_BITMAP_LEN")
TILE_SHIPPED_FIRST = wb("TILE_SHIPPED_FIRST")
TILE_SHIPPED_COUNT = wb("TILE_SHIPPED_COUNT")
TILE_INDEX_TABLE = wb("TILE_INDEX_TABLE")
TILE_INDEX_ENTRIES = wb("TILE_INDEX_ENTRIES")
TILE_INDEX_TAIL = wb("TILE_INDEX_TAIL")
TILE_INDEX_TAIL_LONGS = wb("TILE_INDEX_TAIL_LONGS")
MAP_ROW_STRIDE = wb("MAP_ROW_STRIDE")
MAP_HEADER_BYTES = wb("MAP_HEADER_BYTES")
MAP_HEADER_WIDTH = wb("MAP_HEADER_WIDTH")
MAP_HEADER_HEIGHT = wb("MAP_HEADER_HEIGHT")
MAP_CELL_SHIFT = wb("MAP_CELL_SHIFT")
COLLISION_MAP_CELLS = wb("COLLISION_MAP_CELLS")

STAGE_MAP_PTR = wb("STAGE_MAP_PTR")
STAGE_START_PTR = wb("STAGE_START_PTR")
RAW_TILE_INDEX = wb("STAGE_RAW_TILE_INDEX")
BUILD_CARRY = wb("BG_BUILD_CARRY")
BUILD_TILE_COLUMNS = wb("BG_BUILD_TILE_COLUMNS")
BUILD_TILE_ROWS = wb("BG_BUILD_TILE_ROWS")
BUILD_ROW_SKIP = wb("BG_BUILD_ROW_SKIP")
BUILD_CELL_REWIND = wb("BG_BUILD_CELL_REWIND")
BUILD_ROW_ADVANCE = wb("BG_BUILD_ROW_ADVANCE")
BUILD_MAP_SKIP = wb("BG_BUILD_MAP_SKIP")
BUILD_TILE_SHIFT = wb("BG_BUILD_TILE_SHIFT")
BUILD_PASSES = wb("BG_BUILD_PASSES")
BUILD_SCANLINES = wb("BG_BUILD_SCANLINES")
BUILD_CELLS_AFTER = wb("BG_BUILD_CELLS_AFTER")

SCROLL_LIMIT_X = wb("BG_SCROLL_LIMIT_X")
SCROLL_LIMIT_Y = wb("BG_SCROLL_LIMIT_Y")
LIMIT_X_BIAS = wb("BG_LIMIT_X_BIAS")
LIMIT_Y_BIAS = wb("BG_LIMIT_Y_BIAS")
MAP_CURSOR = wb("BG_MAP_CURSOR")
SCROLL_POS_X = wb("BG_SCROLL_POS_X")
SCROLL_POS_Y = wb("BG_SCROLL_POS_Y")
SCROLL_X = wb("BG_SCROLL_X")
SCROLL_Y = wb("BG_SCROLL_Y")
SCROLL_Y_BOTTOM = wb("BG_SCROLL_Y_BOTTOM")
SCROLL_Y_BOTTOM_INIT = wb("BG_SCROLL_Y_BOTTOM_INIT")
SCROLL_Y_COARSE = wb("BG_SCROLL_Y_COARSE")
SCROLL_PHASE = wb("BG_SCROLL_PHASE")
TILE_ROW = wb("BG_TILE_ROW")
ROW_BYTE_OFFSET = wb("BG_ROW_BYTE_OFFSET")
COPYLOCK_FLAG_A = wb("COPYLOCK_FLAG_A")
COPYLOCK_FLAG_B = wb("COPYLOCK_FLAG_B")

RESOURCE_HEADER = wb("RESOURCE_HEADER")
RESOURCE_RELOCATED = wb("RESOURCE_RELOCATED")
RESOURCE_COUNT_OFF = wb("RESOURCE_COUNT_OFF")
RESOURCE_TABLE = wb("RESOURCE_TABLE")
RESOURCE_RECORD_BYTES = wb("RESOURCE_RECORD_BYTES")

RESET_BLOCK = wb("STAGE_RESET_BLOCK")
RESET_BLOCK_LONGS = wb("STAGE_RESET_BLOCK_LONGS")
RESET_BLOCK_WORDS = wb("STAGE_RESET_BLOCK_WORDS")
PANEL_FRAME_TIMER = wb("PANEL_FRAME_TIMER")
PANEL_FRAME_DELAY = wb("PANEL_FRAME_DELAY")
PANEL_FRAME_DELAY_INIT = wb("PANEL_FRAME_DELAY_INIT")
PANEL_FRAME_PHASE = wb("PANEL_FRAME_PHASE")
PANEL_FRAME_INDEX = wb("PANEL_FRAME_INDEX")
PANEL_FRAME_SPARE = wb("PANEL_FRAME_SPARE")
TILE_33_FLAG = wb("TILE_33_FLAG")
STATE_FLAG_A34 = wb("STATE_FLAG_A34")
STATE_FLAG_A30 = wb("STATE_FLAG_A30")
STATE_FLAG_A32 = wb("STATE_FLAG_A32")
SCROLL_FOLLOW_FROZEN = wb("SCROLL_FOLLOW_FROZEN")
ACTOR_TABLE_SELECTED = wb("ACTOR_TABLE_SELECTED")
ACTOR_TABLE_DEFAULT = wb("ACTOR_TABLE_DEFAULT")

BANNER_ROUND = wb("BG_BANNER_ROUND")
BANNER_PERFECT = wb("BG_BANNER_PERFECT")
BANNER_FONT = wb("BG_BANNER_FONT")
BANNER_END = wb("BG_BANNER_END")
BANNER_BONUS = wb("BG_BANNER_BONUS")
GLYPH_ROWS = wb("TEXT_GLYPH_ROWS")
GLYPH_SHIFT = wb("TEXT_GLYPH_SHIFT")
GLYPH_BYTES = wb("TEXT_GLYPH_BYTES")
FIRST_GLYPH_CHAR = wb("TEXT_FIRST_GLYPH_CHAR")
ADVANCE_EVEN = wb("TEXT_CELL_ADVANCE_EVEN")
ADVANCE_ODD = wb("TEXT_CELL_ADVANCE_ODD")
HUD_METER_VALUE = wb("HUD_METER_VALUE")
HUD_METER_MAX = wb("HUD_METER_MAX")
BCD_SCORE = wb("BCD_SCORE")
BCD_SCORE_LEN = wb("BCD_SCORE_LEN")
BCD_ADDEND = wb("BCD_ADDEND")   # bcd_add_score_bd70 stages its LONGWORD addend here

# ...and the two RESETS' own (batch 13)
LEVEL_SEQ_INDEX = wb("LEVEL_SEQ_INDEX")
LIVES = wb("LIVES")
LIVES_ON_RESTART = wb("LIVES_ON_RESTART")
EFFECT_STATE_21E4 = wb("EFFECT_STATE_21E4")
EFFECT_STATE_BD66 = wb("EFFECT_STATE_BD66")
EFFECT_STATE_BD68 = wb("EFFECT_STATE_BD68")
EFFECT_STATE_BD6A = wb("EFFECT_STATE_BD6A")
EFFECT_STATE_BD6C = wb("EFFECT_STATE_BD6C")
EFFECT_RECORD_LIST = wb("EFFECT_RECORD_LIST")
EFFECT_RECORD_WRITE_PTR = wb("EFFECT_RECORD_WRITE_PTR")
EFFECT_RECORD_PTR_LEN = wb("EFFECT_RECORD_PTR_LEN")
EFFECT_RECORD_EMPTY = wb("EFFECT_RECORD_EMPTY")
HUD_METER_ON_RESTART = wb("HUD_METER_ON_RESTART")
BCD_COUNTER = wb("BCD_COUNTER")
STAGE_TUNE_LATCH = wb("STAGE_TUNE_LATCH")
STAGE_TUNE_LATCH_RESET = wb("STAGE_TUNE_LATCH_RESET")
HUD_SLOT_BBBE = wb("HUD_SLOT_BBBE")
HUD_SLOT_BBC0 = wb("HUD_SLOT_BBC0")
HUD_SLOT_BBC2 = wb("HUD_SLOT_BBC2")
HUD_SLOT_BBC4 = wb("HUD_SLOT_BBC4")
HUD_SLOT_BBC6 = wb("HUD_SLOT_BBC6")
HUD_SLOT_BBC8 = wb("HUD_SLOT_BBC8")

WORD_MASK = 0xffff
LONGWORD_MASK = 0xffffffff
BYTE_MASK = 0xff
LONGWORD_LEN = 4
GLYPH_SPAN = GLYPH_ROWS * BUFFER_LINE


# --- the opcodes only this battery spells ---------------------------------------------------------
A0, A1, A2, A5, A6 = 0, 1, 2, 5, 6
D0, D1, D2, D4, D5, D6, D7 = 0, 1, 2, 4, 5, 6, 7
BNE_W, BEQ_W = 0x6600, 0x6700
BPL_S = 0x6a00


def move_b_postinc_dn(reg, base):
    return opcode(0x1018 | (reg << 9) | base)


def move_w_dn_abs_l(reg, addr):
    return opcode(0x33c0 | reg) + longword(addr)


def move_w_an_dn(reg, an):
    """`move.w An,Dn` — the parity test's only way to look at a cursor."""
    return opcode(0x3000 | (reg << 9) | (1 << 3) | an)


def movea_l_an_an(destination, source):
    return opcode(0x2040 | (destination << 9) | (1 << 3) | source)


def mulu_w_dn_dn(destination, source):
    return opcode(0xc0c0 | (destination << 9) | source)


def adda_l_dn_an(an, dn):
    return opcode(0xd1c0 | (an << 9) | dn)


def move_w_indexed_dn(reg, base, index):
    """`move.w 0(An,Dn.w),Dm` — the index table's one lookup."""
    return opcode(0x3030 | (reg << 9) | base) + word(index << 12)


def lsl_l_imm_dn(count, reg):
    return opcode(0xe188 | ((count & 7) << 9) | reg)


def rol_l_imm_dn(count, reg):
    return opcode(0xe198 | ((count & 7) << 9) | reg)


def move_l_postinc_postinc(source, destination):
    return opcode(0x2000 | (destination << 9) | (3 << 6) | (3 << 3) | source)


def move_l_dn_dn(destination, source):
    return opcode(0x2000 | (destination << 9) | source)


def move_w_dn_postinc(an, dn):
    return opcode(0x3000 | (an << 9) | (3 << 6) | dn)


def or_w_dn_postinc(dn, an):
    """`or.w Dn,(An)+` — how a cell takes the carry its right-hand neighbour shifted out.

    ALSO IN test_blit.py, in the SAME operand order: data register then address register, the way
    the mnemonic reads. (The two disagreed about it when that battery landed — each one's own byte
    pins pass either way, so two encoders of one instruction can differ silently.)
    """
    return opcode(0x8100 | (dn << 9) | (1 << 6) | (3 << 3) | an)


def move_l_imm_dn(reg, value):
    return opcode(0x203c | (reg << 9)) + longword(value)


def lea_abs_w(reg, addr):
    return opcode(0x41f8 | (reg << 9)) + word(addr)


def clr_l_postinc(an):
    return opcode(0x4298 | an)


def clr_w_postinc(an):
    return opcode(0x4258 | an)


def clr_l_abs_w(addr):
    return opcode(0x42b8) + word(addr)


def clr_w_abs_w(addr):
    return opcode(0x4278) + word(addr)


def clr_l_abs_l(addr):
    return opcode(0x42b9) + longword(addr)


def move_w_imm_abs_w(value, addr):
    return opcode(0x31fc) + word(value) + word(addr)


def move_w_imm_abs_l(value, addr):
    return opcode(0x33fc) + word(value) + longword(addr)


def cmpi_b_ind(an, value):
    return opcode(0x0c10 | an) + word(value)


def move_b_imm_ind(an, value):
    return opcode(0x1000 | (an << 9) | (2 << 6) | 0x3c) + word(value)


def move_w_d16_dn(reg, base, displacement):
    return opcode(0x3028 | (reg << 9) | base) + word(displacement)


def addi_l_imm_ind(an, value):
    return opcode(0x0690 | an) + longword(value)


def move_b_postinc_ind(source, destination):
    return opcode(0x1000 | (destination << 9) | (2 << 6) | (3 << 3) | source)


def move_b_postinc_d16(source, destination, displacement):
    return opcode(0x1000 | (destination << 9) | (5 << 6) | (3 << 3) | source) + word(displacement)


def tst_b_ind(an):
    return opcode(0x4a10 | an)


def cmp_w_abs_l_dn(reg, addr):
    return opcode(0xb079 | (reg << 9)) + longword(addr)


def bpl_s(here, target):
    displacement = target - (here + STATE_WORD_LEN)
    assert -0x80 <= displacement < 0, f"{displacement} does not fit a `bpl.s` byte displacement"
    return opcode(BPL_S | (displacement & BYTE_MASK))


# --- the whole-body entry pins --------------------------------------------------------------------
# Each is the WHOLE routine, assembled out of the header's constants and this battery's own
# geometry, so a wrong constant fails where it is wrong instead of at a differential.

def _build_buffer_entry():
    """$fa30 — the tile draw, 214 bytes."""
    raw_arm = (add_w_dn_dn(D7, D7) + lea_abs_l(A5, TILE_INDEX_TABLE)
               + move_w_indexed_dn(D7, A5, D7))
    tile_row = (move_l_postinc_postinc(A1, A2) * (CELL_BYTES // LONGWORD_LEN)
                + lea_d16(A2, BUILD_ROW_SKIP))
    last_row = (move_l_postinc_postinc(A1, A2) * (CELL_BYTES // LONGWORD_LEN)
                + lea_d16(A2, -BUILD_CELL_REWIND))
    cell = (movea_l_an_an(A1, A6) + moveq_0_dn(D7) + move_b_postinc_dn(D7, A0)
            + tst_w_abs_l(RAW_TILE_INDEX) + branch(BNE_W, raw_arm) + raw_arm
            + lsl_l_imm_dn(BUILD_TILE_SHIFT, D7) + lea_indexed(A1, D7, longword_index=True)
            + tile_row * (TILE_ROWS - 1) + last_row)
    row = (move_w_imm_dn(D6, BUILD_TILE_COLUMNS - 1) + cell + dbf_over(D6, len(cell))
           + lea_d16(A2, BUILD_ROW_ADVANCE)
           + moveq_0_dn(D7) + move_w_dn_dn(D7, D2) + subi_w_dn(D7, BUILD_MAP_SKIP)
           + adda_l_dn_an(A0, D7))
    return (move_w_postinc_dn(D0, A1) + move_w_postinc_dn(D1, A1)
            + leaf.move_w_ind_dn(D2, A0)
            + mulu_w_dn_dn(D1, D2) + add_w_dn_dn(D1, D0)
            + lea_indexed(A0, D1, MAP_HEADER_BYTES)
            + lea_abs_l(A2, BUFFER_BASE)
            + move_w_imm_dn(D5, BUILD_TILE_ROWS - 1) + row + dbf_over(D5, len(row))
            + RTS)


def published_row_pointer(copy, row):
    """WB_BG_BUFFER_ROWS' invariant, which scroll.c's vertical steps preserve."""
    return BUFFER_BASE + copy * BUFFER_LEN + row * BUFFER_LINE


def _publish_scroll_state_entry():
    """$fb06 — the state publish, 320 bytes."""
    def limit(bias, destination):
        return (move_w_postinc_dn(D0, A0) + lsl_w_imm_dn(MAP_CELL_SHIFT, D0) + subi_w_dn(D0, bias)
                + move_w_dn_abs_l(D0, destination))

    pointers = b""
    for copy in range(BUFFERS):
        for row, member in ((0, BUFFER_ROW_TOP), (SCROLL_Y_BOTTOM_INIT, BUFFER_ROW_BOTTOM)):
            pointers += move_l_imm_abs_l(published_row_pointer(copy, row),
                                         BUFFER_ROWS + copy * BUFFER_ROW_PAIR + member)

    cleared = b"".join(clr_w_abs_l(addr) for addr in
                       [PRESHIFT_CARRY + plane * STATE_WORD_LEN for plane in range(PLANES)]
                       + [TILE_ROW, SCROLL_Y_COARSE, ROW_BYTE_OFFSET, SCROLL_X, SCROLL_Y,
                          COPYLOCK_FLAG_A])
    return (movea_l_abs_l(A0, STAGE_MAP_PTR) + movea_l_abs_l(A1, STAGE_START_PTR)
            + moveq_0_dn(D0) + limit(LIMIT_X_BIAS, SCROLL_LIMIT_X)
            + limit(LIMIT_Y_BIAS, SCROLL_LIMIT_Y)
            + move_w_postinc_dn(D0, A1) + move_w_postinc_dn(D1, A1)
            + move_w_abs_l_dn(D2, MAP_ROW_STRIDE)
            + mulu_w_dn_dn(D2, D1) + add_w_dn_dn(D2, D0) + move_w_dn_abs_l(D2, MAP_CURSOR)
            + lsl_w_imm_dn(MAP_CELL_SHIFT, D0) + lsl_w_imm_dn(MAP_CELL_SHIFT, D1)
            + move_w_dn_abs_l(D0, SCROLL_POS_X) + move_w_dn_abs_l(D1, SCROLL_POS_Y)
            + cleared + st_abs_l(COPYLOCK_FLAG_B)
            + leaf.MOVE_W_IMM_ABS_L + word(SCROLL_Y_BOTTOM_INIT) + longword(SCROLL_Y_BOTTOM)
            + clr_w_abs_l(SCROLL_PHASE)
            + pointers + RTS)


def _preshift_entry():
    """$fd46 — the seven derived copies, 198 bytes."""
    planes = range(PLANES)
    shift = (moveq_0_dn(D4) + b"".join(move_l_dn_dn(D4 + p, D4) for p in planes[1:])
             + b"".join(move_w_postinc_dn(D4 + p, A0) for p in planes)
             + b"".join(rol_l_imm_dn(PRESHIFT_BITS, D4 + p) for p in planes))
    swap_all = b"".join(swap_dn(D4 + p) for p in planes)
    prologue = (shift + b"".join(move_w_dn_postinc(A1, D4 + p) for p in planes) + swap_all
                + b"".join(move_w_dn_abs_l(D4 + p, BUILD_CARRY + p * STATE_WORD_LEN)
                           for p in planes))
    body = (lea_d16(A1, -CELL_BYTES) + shift + swap_all
            + b"".join(or_w_dn_postinc(D4 + p, A1) for p in planes) + swap_all
            + b"".join(move_w_dn_postinc(A1, D4 + p) for p in planes))
    epilogue = (lea_d16(A1, -CELL_BYTES)
                + b"".join(move_w_abs_l_dn(D4 + p, BUILD_CARRY + p * STATE_WORD_LEN)
                           for p in planes)
                + b"".join(or_w_dn_postinc(D4 + p, A1) for p in planes))

    scanline = (move_w_imm_dn(D2, BUILD_CELLS_AFTER - 1) + prologue
                + body + dbf_over(D2, len(body)) + epilogue)
    pass_ = move_w_imm_dn(D1, BUILD_SCANLINES - 1) + scanline + dbf_over(D1, len(scanline))
    return (lea_abs_l(A0, BUFFER_BASE) + lea_abs_l(A1, BUFFER_BASE + BUFFER_LEN)
            + move_w_imm_dn(D0, BUILD_PASSES - 1) + pass_ + dbf_over(D0, len(pass_)) + RTS)


def _resource_relocate_entry():
    """$fe1e — the one-time table relocation, 44 bytes."""
    body = addi_l_imm_ind(A5, RESOURCE_TABLE)
    relocate = (move_b_imm_ind(A6, RESOURCE_RELOCATED) + lea_abs_l(A5, RESOURCE_TABLE)
                + move_w_d16_dn(D7, A6, RESOURCE_COUNT_OFF)
                + body + lea_d16(A5, RESOURCE_RECORD_BYTES)
                + opcode(leaf.DBF_DN | D7) + leaf.backward_branch(len(body)
                                                                  + len(lea_d16(A5, 0))))
    return (lea_abs_l(A6, RESOURCE_HEADER) + cmpi_b_ind(A6, RESOURCE_RELOCATED)
            + branch(BEQ_W, relocate) + relocate + RTS)


def _reset_state_entry():
    """$fed2 — the per-stage state reset, 112 bytes."""
    tail = b"".join(move_l_imm_postinc(A1, value) for value in TILE_INDEX_TAIL_VALUES)
    return (lea_abs_w(A0, RESET_BLOCK)
            + clr_l_postinc(A0) * RESET_BLOCK_LONGS + clr_w_postinc(A0) * RESET_BLOCK_WORDS
            + clr_w_abs_l(PANEL_FRAME_TIMER)
            + leaf.MOVE_W_IMM_ABS_L + word(PANEL_FRAME_DELAY_INIT) + longword(PANEL_FRAME_DELAY)
            + clr_w_abs_l(PANEL_FRAME_PHASE) + clr_w_abs_l(PANEL_FRAME_INDEX)
            + clr_w_abs_l(PANEL_FRAME_SPARE)
            + clr_l_abs_w(TILE_33_FLAG)
            + clr_w_abs_w(STATE_FLAG_A34) + clr_w_abs_w(SCROLL_FOLLOW_FROZEN)
            + clr_w_abs_w(STATE_FLAG_A30) + clr_w_abs_w(STATE_FLAG_A32)
            + move_l_imm_abs_l(ACTOR_TABLE_DEFAULT, ACTOR_TABLE_SELECTED)
            + lea_abs_l(A1, TILE_INDEX_TABLE)
            + lea_d16(A1, TILE_INDEX_TAIL - TILE_INDEX_TABLE)
            + tail + RTS)


def _plot_banner_glyph_entry():
    """$e16a — one 8x8 glyph, 48 bytes."""
    row = (move_b_postinc_ind(A0, A1)
           + b"".join(move_b_postinc_d16(A0, A1, plane * PLANE_STRIDE)
                      for plane in range(1, PLANES))
           + lea_d16(A1, BUFFER_LINE))
    # `bne` is taken when bit 0 is SET, so the FALL-THROUGH arm is the even cursor's.
    even = lea_d16(A1, ADVANCE_EVEN - GLYPH_SPAN) + RTS
    return (move_w_imm_dn(D0, GLYPH_ROWS - 1) + row + dbf_over(D0, len(row))
            + move_w_an_dn(D0, A1) + btst_imm_dn(0, D0) + branch(BNE_W, even) + even
            + lea_d16(A1, ADVANCE_ODD - GLYPH_SPAN) + RTS)


def _plot_banner_entry(at):
    """$e140 — one banner record, 42 bytes. Its `bsr` displacement depends on where it sits."""
    head = (lea_abs_l(A1, BUFFER_BASE) + move_w_postinc_dn(D0, A6) + lea_indexed(A1, D0))
    loop = (moveq_0_dn(D0) + move_b_postinc_dn(D0, A6) + _subi_b_dn(D0, FIRST_GLYPH_CHAR)
            + lsl_w_imm_dn(GLYPH_SHIFT, D0) + lea_abs_l(A0, BANNER_FONT) + lea_indexed(A0, D0))
    call = leaf.bsr_w(at + len(head) + len(loop), leaf.entry_of("bg_plot_banner_glyph"))
    tail_at = at + len(head) + len(loop) + len(call) + len(tst_b_ind(A6))
    return (head + loop + call + tst_b_ind(A6) + bpl_s(tail_at, at + len(head)) + RTS)


def _plot_round_banner_entry(at):
    """$e110 — the round banner and the perfect bonus, 48 bytes."""
    plot = leaf.entry_of("bg_plot_banner")
    head = lea_abs_l(A6, BANNER_ROUND)
    first = leaf.bsr_w(at + len(head), plot)
    perfect = (move_l_imm_dn(D0, BANNER_BONUS)
               + leaf.bsr_w(at + len(head) + len(first)
                            + len(move_w_abs_l_dn(D0, 0)) + len(cmp_w_abs_l_dn(D0, 0))
                            + len(branch_over(BNE_W, 0)) + len(move_l_imm_dn(D0, 0)),
                            leaf.entry_of("bcd_add_score_bd70")))
    perfect += lea_abs_l(A6, BANNER_PERFECT)
    perfect += leaf.bsr_w(at + len(head) + len(first) + len(move_w_abs_l_dn(D0, 0))
                          + len(cmp_w_abs_l_dn(D0, 0)) + len(branch_over(BNE_W, 0)) + len(perfect),
                          plot)
    return (head + first
            + move_w_abs_l_dn(D0, HUD_METER_VALUE) + cmp_w_abs_l_dn(D0, HUD_METER_MAX)
            + branch_over(BNE_W, len(perfect)) + perfect + RTS)


def _subi_b_dn(reg, value):
    return opcode(0x0400 | reg) + word(value)


# The four longwords $fed2 writes over WB_TILE_INDEX_TAIL. They are IMMEDIATES in the instruction
# stream and nothing in the image derives them, so they are transcribed — and the entry pin is what
# makes a wrong transcription fail on the shipped bytes.
TILE_INDEX_TAIL_VALUES = (0x00460047, 0x00480049, 0x004a004b, 0x0040004d)

# The six `clr.w`s of the head, in the original's own order — the same six src/stage.c spells, and
# the reason both are lists rather than a stride: the instruction stream has six absolute operands.
GAME_RESET_HUD_SLOTS = [HUD_SLOT_BBBE, HUD_SLOT_BBC0, HUD_SLOT_BBC2,
                        HUD_SLOT_BBC4, HUD_SLOT_BBC6, HUD_SLOT_BBC8]


def _restart_reset_entry():
    """$fe4a's 66-byte HEAD. It has no `rts`: it falls through into the tail below, which is why the
    two sizes are asserted against Ghidra's single 136 rather than against the scan directly."""
    return (clr_w_abs_l(LEVEL_SEQ_INDEX)
            + move_w_imm_abs_w(LIVES_ON_RESTART, LIVES)
            + clr_w_abs_w(EFFECT_STATE_21E4)
            + move_w_imm_abs_l(EFFECT_RECORD_EMPTY, EFFECT_RECORD_LIST)
            + b"".join(clr_w_abs_l(slot) for slot in GAME_RESET_HUD_SLOTS)
            + clr_w_abs_l(EFFECT_STATE_BD6A))


def _life_restart_reset_entry():
    """$fe8c's 70-byte tail, the part both entrants run."""
    at = leaf.entry_of("game_life_restart_reset")
    return (bsr_w(at, leaf.entry_of("hud_draw_lives"))
            + move_w_imm_abs_l(HUD_METER_ON_RESTART, HUD_METER_VALUE)
            + move_w_imm_abs_l(HUD_METER_ON_RESTART, HUD_METER_MAX)
            + clr_l_abs_l(BCD_SCORE) + clr_w_abs_l(BCD_COUNTER)
            + clr_w_abs_l(EFFECT_STATE_BD66) + clr_w_abs_l(EFFECT_STATE_BD68)
            + clr_w_abs_l(EFFECT_STATE_BD6C)
            + leaf.move_b_imm_abs_l(STAGE_TUNE_LATCH_RESET, STAGE_TUNE_LATCH)
            + move_l_imm_abs_l(EFFECT_RECORD_LIST, EFFECT_RECORD_WRITE_PTR) + RTS)


ENTRY_BYTES = {
    "bg_build_buffer": _build_buffer_entry(),
    "stage_publish_scroll_state": _publish_scroll_state_entry(),
    "bg_build_preshifted_copies": _preshift_entry(),
    "resource_table_relocate": _resource_relocate_entry(),
    "stage_reset_state": _reset_state_entry(),
    "bg_plot_banner_glyph": _plot_banner_glyph_entry(),
    "bg_plot_banner": _plot_banner_entry(leaf.entry_of("bg_plot_banner")),
    "bg_plot_round_banner": _plot_round_banner_entry(leaf.entry_of("bg_plot_round_banner")),
    "game_restart_reset": _restart_reset_entry(),
    "game_life_restart_reset": _life_restart_reset_entry(),
}

# What ../out/hw_scan.tsv records for each, stated rather than derived so that a routine whose body
# moved fails here as well as on the bytes.
SIZES = {
    "bg_build_buffer": 214,
    "stage_publish_scroll_state": 320,
    "bg_build_preshifted_copies": 198,
    "resource_table_relocate": 44,
    "stage_reset_state": 112,
    "bg_plot_banner_glyph": 48,
    "bg_plot_banner": 42,
    "bg_plot_round_banner": 48,
    # NOT the scan's numbers: it records ONE 136-byte function at $fe4a and a whole-image scan says
    # it is two, because $fe8c has an entrant of its own (`jsr $fe8c.l` at $c00). The two halves are
    # required to add back up to that 136 by the test below.
    "game_restart_reset": 66,
    "game_life_restart_reset": 70,
}
GHIDRA_RESET_FUNCTION_BYTES = 136

RECONSTRUCTED_ROUTINES = 10


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)
    assert set(SIZES) == set(ENTRY_BYTES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", sorted(SIZES.items()))
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    assert len(ENTRY_BYTES[name]) == size, (
        f"{name} is reconstructed as {len(ENTRY_BYTES[name])} bytes against the {size} "
        f"../out/hw_scan.tsv records — a piece of the body is missing or doubled")


def test_the_map_header_is_the_collision_maps_own_cell_bias():
    """The two-word header this batch read off $fb06 is the same +4 the collision map's lookup
    already biased by, and WB_MAP_DATA_ROW already sat at above WB_MAP_ROW_STRIDE — three spellings
    of one number, which is three places to get it wrong."""
    assert MAP_HEADER_BYTES == COLLISION_MAP_CELLS == wb("STAMP_CELL_BIAS")
    assert wb("MAP_DATA_ROW") - MAP_ROW_STRIDE == MAP_HEADER_BYTES
    assert MAP_HEADER_HEIGHT == STATE_WORD_LEN and MAP_HEADER_WIDTH == 0


def test_the_published_row_pointers_are_the_scroll_engines_invariant():
    """All sixteen longwords $fb06 writes are `base + copy * LEN + row * LINE` — the invariant
    src/scroll.c's two vertical steps preserve — for rows 0 and WB_BG_SCROLL_Y_BOTTOM_INIT. Read out
    of the SHIPPED instruction stream, so this batch and the scroll batch cannot disagree about a
    buffer address without failing here."""
    entry = leaf.entry_of("stage_publish_scroll_state")
    body = bytes(harness.BASE_IMAGE[entry:entry + SIZES["stage_publish_scroll_state"]])
    for copy in range(BUFFERS):
        for row, member in ((0, BUFFER_ROW_TOP), (SCROLL_Y_BOTTOM_INIT, BUFFER_ROW_BOTTOM)):
            store = move_l_imm_abs_l(published_row_pointer(copy, row),
                                     BUFFER_ROWS + copy * BUFFER_ROW_PAIR + member)
            assert store in body, (
                f"copy {copy}'s {'top' if member == BUFFER_ROW_TOP else 'bottom'} pointer is not "
                f"{published_row_pointer(copy, row):#x} in the shipped body")
    assert SCROLL_Y_BOTTOM_INIT * BUFFER_LINE == published_row_pointer(0, SCROLL_Y_BOTTOM_INIT) \
        - BUFFER_BASE


def test_the_banner_font_is_reached_from_this_routine_alone():
    """A whole-image scan for WB_BG_BANNER_FONT's abs.l operand gives exactly one site, inside
    $e140 — so it is a SECOND font and not WB_TEXT_GLYPH_TABLE under another name."""
    program = bytes(harness.BASE_IMAGE)
    operand = longword(BANNER_FONT)
    sites = [at for at in range(0, wb("MAP_ROW_STRIDE"), 2) if program[at:at + 4] == operand]
    banner = leaf.entry_of("bg_plot_banner")
    assert sites == [at for at in sites if banner <= at < banner + SIZES["bg_plot_banner"]], (
        f"WB_BG_BANNER_FONT has operand sites outside $e140: {[hex(a) for a in sites]}")
    assert BANNER_FONT != wb("TEXT_GLYPH_TABLE")


# --- bg_build_buffer ------------------------------------------------------------------------------
# The map lives at the game's own WB_MAP_ROW_STRIDE, which is plain RAM past the program: a case
# seeds its header and its cells. The tile bank is WB_TILE_BITMAPS and every index-table entry is
# seeded to a SHIPPED tile, so a cursor that walks out of the seeded window still reads real pixels.

# The level map is a band of plain RAM past the program and clear of every other structure the
# memory map records (program 0x3f8..0x218d0, SPRITES.CRU at 0x25298, the buffers from 0x44000). It
# is deliberately NOT WB_MAP_ROW_STRIDE's own address: $fb06 reads the header off the level map and
# the cursor's stride off the GLOBAL, and while the two were one address no case could tell them
# apart — a mutation swapping them survived the first sweep, which is the only thing that said so.
MAP = 0x30000
MAP_STRIDE = 0x40
MAP_SEED_ROWS = BUILD_TILE_ROWS + 2          # a two-row margin below the window the build reads
BUILD_INSN_CAP = BUILD_TILE_ROWS * BUILD_TILE_COLUMNS * (TILE_ROWS * 3 + 16) + 256

_BUILD = leaf.register_glue("bg_build_buffer", [ctypes.c_uint32] * 3)


# A tile number this big puts `number * WB_TILE_BITMAP_LEN` past 16 bits, which is what the `lsl.l`
# and the LONGWORD index exist for. It is a plain RAM address like every other bitmap here — the
# banks past WB_TILE_BITMAPS are loaded from disk — so the case seeds it rather than inventing one.
FAR_TILE_BIAS = 0x200
assert FAR_TILE_BIAS * TILE_BITMAP_LEN > WORD_MASK


def shipped_tile(number, bias=0):
    """A tile whose bitmap the .PRG carries, or (with a bias) one a case seeds itself."""
    return TILE_SHIPPED_FIRST + number % TILE_SHIPPED_COUNT + bias


def _index_table_pokes(bias=0):
    """All WB_TILE_INDEX_ENTRIES entries, every one naming a tile whose bitmap exists."""
    return {TILE_INDEX_TABLE: b"".join(word(shipped_tile(entry, bias))
                                       for entry in range(TILE_INDEX_ENTRIES))}


def build_cursors(column, row, stride):
    """The eleven map cursors $fa30's OWN arithmetic lands on, one per tile row.

    Transcribed from the disassembly rather than assumed, per docs/methodology.md's second seeding
    rule: the first is `lea 4(a0,d1.w),a0` over a WORD index (so it SIGN-extends), and each one
    after it is the sixteen cells just read plus the UNSIGNED `subi.w #$10` row skip. Every band a
    case seeds is keyed off these, so a case cannot seed the right bytes in the wrong place.
    """
    cursor = (MAP + s16((row * stride + column) & WORD_MASK) + MAP_HEADER_BYTES) & LONGWORD_MASK
    for _ in range(BUILD_TILE_ROWS):
        yield cursor
        cursor = (cursor + BUILD_TILE_COLUMNS
                  + ((stride - BUILD_MAP_SKIP) & WORD_MASK)) & LONGWORD_MASK


# One cell of margin past each row's sixteen, so a walk that reads one cell too far lands on a byte
# that is wrong FOR ITS ADDRESS rather than on an unseeded zero that matches another unseeded zero.
MAP_ROW_MARGIN = CELL_BYTES


def _map_pokes(salt, stride, rows, column, start_row, raw):
    """The map header, and a band of cells at every cursor the routine actually reads from.

    In RAW mode the byte IS the tile number, so the cells are seeded inside the shipped range; in
    indexed mode any byte is safe (every index entry names a tile whose bitmap exists) and they are
    address-keyed. The header goes in LAST, since make_image applies pokes in insertion order and a
    band may reach back over it.
    """
    pokes = {}
    span = BUILD_TILE_COLUMNS + MAP_ROW_MARGIN
    for cursor in build_cursors(column, start_row, stride):
        cells = keyed_block(cursor, span, salt)
        pokes[cursor] = bytes(shipped_tile(value) for value in cells) if raw else cells
    pokes[MAP + MAP_HEADER_WIDTH] = word(stride)
    pokes[MAP + MAP_HEADER_HEIGHT] = word(rows)
    return pokes


def _model_build(image, start, tiles, stride, raw):
    """The 22,528 bytes $fa30 lays into copy 0, walked the way the routine walks them."""
    column = u16(image, start)
    row = u16(image, start + STATE_WORD_LEN)
    cursor = (MAP + s16(row * stride + column) + MAP_HEADER_BYTES) & LONGWORD_MASK
    buffer = bytearray(BUFFER_LEN)
    for tile_row in range(BUILD_TILE_ROWS):
        for tile_column in range(BUILD_TILE_COLUMNS):
            cell = image[cursor]
            cursor = (cursor + 1) & LONGWORD_MASK
            number = cell if raw else u16(image, TILE_INDEX_TABLE + 2 * cell)
            bitmap = (tiles + (number << BUILD_TILE_SHIFT)) & LONGWORD_MASK
            for line in range(TILE_ROWS):
                at = tile_row * TILE_BLOCK_LEN + tile_column * CELL_BYTES + line * BUFFER_LINE
                buffer[at:at + CELL_BYTES] = bytes(
                    image[bitmap + line * CELL_BYTES:bitmap + (line + 1) * CELL_BYTES])
        # `moveq #0,d7 / move.w d2,d7 / subi.w #$10,d7 / adda.l d7,a0` — see src/stage.c.
        cursor = (cursor + ((stride - BUILD_MAP_SKIP) & WORD_MASK)) & LONGWORD_MASK
    return bytes(buffer)


def _run_build(case, start_column=0, start_row=0, stride=MAP_STRIDE, raw=False,
               rows=MAP_SEED_ROWS, tile_bias=0):
    salt = case_salt(case)
    pokes = dict(_index_table_pokes(tile_bias))
    pokes.update(_map_pokes(salt, stride, rows, start_column, start_row, raw))
    if tile_bias:
        first = TILE_BITMAPS + shipped_tile(0, tile_bias) * TILE_BITMAP_LEN
        pokes[first] = keyed_block(first, TILE_SHIPPED_COUNT * TILE_BITMAP_LEN, salt)
    pokes[RAW_TILE_INDEX] = word(WORD_MASK if raw else 0)
    # Two words of plain RAM the case owns, placed clear of every band it seeded.
    start = max(pokes) + 0x100
    pokes[start] = word(start_column) + word(start_row)
    # Address-keyed, so an over-copy inside the buffer lands on a byte that is wrong FOR WHERE IT
    # WAS WRITTEN rather than on a zero that matches another zero.
    pokes[BUFFER_BASE] = keyed_block(BUFFER_BASE, BUFFER_LEN, salt)

    image = harness.make_image(pokes)
    expected = _model_build(image, start, TILE_BITMAPS, stride, raw)

    what = f"bg_build_buffer {case}"
    info = leaf.run("bg_build_buffer", _BUILD(MAP, start, TILE_BITMAPS),
                    [(BUFFER_BASE, BUFFER_LEN)], what,
                    regs={"a0": MAP, "a1": start, "a6": TILE_BITMAPS, "_pokes": pokes},
                    max_insns=BUILD_INSN_CAP)
    written = program_writes(info)
    assert sorted(written) == list(range(BUFFER_BASE, BUFFER_BASE + BUFFER_LEN)), (
        f"{what}: the original wrote {len(written)} bytes, not copy 0's own {BUFFER_LEN}")
    actual = bytes(written[BUFFER_BASE + offset] for offset in range(BUFFER_LEN))
    assert actual == expected, (
        f"{what}: the buffer differs from the model at offset "
        f"{next(i for i in range(BUFFER_LEN) if actual[i] != expected[i]):#x}")
    return info


def test_the_build_lays_every_tile_of_the_window_through_the_index_table():
    """Eleven tile rows of sixteen cells, each a WB_TILE_BITMAP_LEN bitmap laid down a
    WB_BG_BUFFER_LINE at a time — the whole of copy 0 and nothing else."""
    _run_build("indexed")


def test_the_raw_mode_makes_the_map_byte_the_tile_number():
    """`tst.w $fe14.l / bne` skips the WB_TILE_INDEX_TABLE lookup entirely, so the same map bytes
    name DIFFERENT tiles in the two modes — which is why the flag is a property of the tile BANK
    $f95c was handed and not of the map."""
    _run_build("raw", raw=True)


@pytest.mark.parametrize("column,row", [(0, 0), (3, 0), (0, 5), (7, 4)],
                         ids=["origin", "column", "row", "both"])
def test_the_window_opens_on_the_start_records_own_cell(column, row):
    """`mulu.w d2,d1 / add.w d0,d1 / lea 4(a0,d1.w),a0`: the record's two words are a map column and
    row, multiplied by the header's OWN stride word rather than by WB_MAP_ROW_STRIDE's."""
    _run_build(f"start-{column}-{row}", start_column=column, start_row=row)


def test_a_start_cell_past_7fff_addresses_below_the_map():
    """The cell index is built in a WORD and `lea 4(a0,d1.w),a0` sign-extends it, so a start row far
    enough down names a cell BELOW WB_MAP_ROW_STRIDE. Every index entry is a shipped tile, so the
    bytes it then reads are still real map-shaped input on both sides."""
    row = (0x8000 // MAP_STRIDE) + 1
    assert s16(row * MAP_STRIDE) < 0, "the case's own start row does not reach the sign bit"
    _run_build("negative-cell", start_row=row)


def test_a_tile_whose_bitmap_offset_does_not_fit_a_word():
    """`lsl.l #7,d7 / lea 0(a1,d7.l),a1` — a LONG shift and a LONG index, so a tile number past 511
    names a bitmap more than 64 KB above the bank rather than one wrapped back inside it. The index
    table is loaded from disk, so the number is seeded there and the bitmaps beside it."""
    _run_build("far-tile", tile_bias=FAR_TILE_BIAS)


def test_the_row_skip_is_unsigned_so_a_narrow_map_walks_forward():
    """`subi.w #$10,d7` on a stride BELOW WB_BG_BUILD_MAP_SKIP wraps in the word, and `adda.l d7,a0`
    then adds ~64 KB where a signed reading would step the cursor back. Reproduced, not tidied."""
    stride = BUILD_MAP_SKIP // 2
    assert (stride - BUILD_MAP_SKIP) & WORD_MASK > 0x8000
    _run_build("narrow-map", stride=stride, rows=BUILD_TILE_ROWS * BUILD_TILE_COLUMNS)


def test_the_row_skip_is_the_stride_less_the_columns_just_walked():
    """The ordinary case of the same instruction: a stride of exactly WB_BG_BUILD_MAP_SKIP leaves
    the cursor where it stands, so all eleven rows read the SAME sixteen cells."""
    _run_build("square-map", stride=BUILD_MAP_SKIP, rows=BUILD_TILE_ROWS)


# --- stage_publish_scroll_state -------------------------------------------------------------------

PUBLISH_INSN_CAP = 128
_PUBLISH = leaf.image_glue("stage_publish_scroll_state")

# Everything the routine writes, as (address, length). Stated exactly: this is a publish, and a
# field it forgot or a field it invented is the whole failure mode.
PUBLISHED_WORDS = ([SCROLL_LIMIT_X, SCROLL_LIMIT_Y, MAP_CURSOR, SCROLL_POS_X, SCROLL_POS_Y]
                   + [PRESHIFT_CARRY + plane * STATE_WORD_LEN for plane in range(PLANES)]
                   + [TILE_ROW, SCROLL_Y_COARSE, ROW_BYTE_OFFSET, SCROLL_X, SCROLL_Y,
                      COPYLOCK_FLAG_A, SCROLL_Y_BOTTOM, SCROLL_PHASE])


def _publish_bands():
    bands = [(addr, STATE_WORD_LEN) for addr in PUBLISHED_WORDS]
    bands.append((COPYLOCK_FLAG_B, 1))
    bands.append((BUFFER_ROWS, BUFFERS * BUFFER_ROW_PAIR))
    return merge_bands(sum(([addr + i for i in range(length)] for addr, length in bands), []))


# Deliberately unequal to any header width a case below uses: the cursor's `mulu.w` reads THIS word
# and the limits read the header's, and only a case that seeds them apart states which is which.
GLOBAL_STRIDE = 0x31

def _run_publish(case, width, height, column, row, stride=GLOBAL_STRIDE):
    salt = case_salt(case)
    start = MAP + MAP_HEADER_BYTES + MAP_STRIDE * MAP_SEED_ROWS + CELL_BYTES
    assert stride != width, "the case must seed the global stride apart from the header's width"
    pokes = {MAP + MAP_HEADER_WIDTH: word(width),
             MAP + MAP_HEADER_HEIGHT: word(height),
             MAP_ROW_STRIDE: word(stride),
             start: word(column) + word(row),
             STAGE_MAP_PTR: longword(MAP),
             STAGE_START_PTR: longword(start)}
    # A margin on both sides of the published band, so a write one word past it lands on a byte
    # that is wrong for its address rather than on a zero.
    pokes[PRESHIFT_CARRY - CELL_BYTES] = keyed_block(PRESHIFT_CARRY - CELL_BYTES, 0x40, salt)
    pokes[BUFFER_ROWS - CELL_BYTES] = keyed_block(
        BUFFER_ROWS - CELL_BYTES, BUFFERS * BUFFER_ROW_PAIR + 2 * CELL_BYTES, salt)

    image = harness.make_image(pokes)
    stride_word = u16(image, MAP_ROW_STRIDE)

    what = f"stage_publish_scroll_state {case}"
    info = leaf.run("stage_publish_scroll_state", _PUBLISH, _publish_bands(), what,
                    regs={"_pokes": pokes}, max_insns=PUBLISH_INSN_CAP)

    expected = {SCROLL_LIMIT_X: ((width << MAP_CELL_SHIFT) - LIMIT_X_BIAS) & WORD_MASK,
                SCROLL_LIMIT_Y: ((height << MAP_CELL_SHIFT) - LIMIT_Y_BIAS) & WORD_MASK,
                MAP_CURSOR: (row * stride_word + column) & WORD_MASK,
                SCROLL_POS_X: (column << MAP_CELL_SHIFT) & WORD_MASK,
                SCROLL_POS_Y: (row << MAP_CELL_SHIFT) & WORD_MASK,
                SCROLL_Y_BOTTOM: SCROLL_Y_BOTTOM_INIT}
    for addr in PUBLISHED_WORDS:
        want = expected.get(addr, 0)
        got = leaf.read_int(info, addr, STATE_WORD_LEN, what)
        assert got == want, f"{what}: {addr:#x} is {got:#06x}, not {want:#06x}"
    assert leaf.read_int(info, COPYLOCK_FLAG_B, 1, what) == BYTE_MASK
    for copy in range(BUFFERS):
        for buffer_row, member in ((0, BUFFER_ROW_TOP), (SCROLL_Y_BOTTOM_INIT, BUFFER_ROW_BOTTOM)):
            at = BUFFER_ROWS + copy * BUFFER_ROW_PAIR + member
            assert leaf.read_int(info, at, LONGWORD_LEN, what) \
                == published_row_pointer(copy, buffer_row)
    return info


@pytest.mark.parametrize("width,height", [(0x40, 0x20), (0x100, 0xb), (0xf, 0xa), (0xe, 0x9)],
                         ids=["ordinary", "wide", "on-the-bias", "smaller-than-the-bias"])
def test_the_limits_are_the_header_words_in_pixels_less_their_biases(width, height):
    """`move.w (a0)+,d0 / lsl.w #4,d0 / subi.w #$f0,d0` — a bare WORD subtraction with no floor.

    The third case's map is EXACTLY as wide as WB_BG_LIMIT_X_BIAS and exactly as tall as
    WB_BG_LIMIT_Y_BIAS, so both limits land ON zero — which a port that clamped at zero also
    produces. The FOURTH is one cell narrower and one cell shorter, so both limits WRAP ($fff0 and
    $fff0), and that is the case that tells the two readings apart."""
    # ONE number under two names: $fb18's `subi.w` builds the limit that $1170's clamp adds the same
    # 240 back to. wonderboy.h cannot say so in a `#define` — layout.py refuses a compound one — so
    # the identity is pinned here rather than left as two literals nothing ties together.
    assert LIMIT_X_BIAS == wb("BG_SCROLL_LIMIT_BIAS")

    case = f"limits-{width}-{height}"
    info = _run_publish(case, width, height, column=2, row=1)
    # The case ids are a claim about the arithmetic, so they are checked rather than trusted: a
    # header below the bias must leave a NEGATIVE limit, and one at or above it a non-negative one.
    for limit, cells, bias in ((SCROLL_LIMIT_X, width, LIMIT_X_BIAS),
                               (SCROLL_LIMIT_Y, height, LIMIT_Y_BIAS)):
        published = leaf.read_int(info, limit, STATE_WORD_LEN, case)
        assert (s16(published) < 0) == (((cells << MAP_CELL_SHIFT) & WORD_MASK) < bias), (
            f"{case}: {limit:#x} is {published:#06x} for {cells:#x} cells against a bias of "
            f"{bias:#x} — the `subi.w` neither clamps nor saturates")


@pytest.mark.parametrize("column,row", [(0, 0), (5, 0), (0, 9), (6, 3)],
                         ids=["origin", "column", "row", "both"])
def test_the_cursor_and_the_positions_come_from_the_start_record(column, row):
    """`move.w (a1)+,d0 / move.w (a1)+,d1 / move.w $22090.l,d2 / mulu.w d1,d2 / add.w d0,d2` — and
    then the same two words shifted into pixels. THE CURSOR'S STRIDE IS WB_MAP_ROW_STRIDE'S OWN
    WORD, not the header's: every case here seeds the two apart, so a port that read the header
    (which is what $fa30 does one routine away) fails."""
    _run_publish(f"start-{column}-{row}", 0x40, 0x20, column, row)


def test_the_copylock_flag_pair_is_a_word_and_a_byte():
    """`clr.w $f89a.l` against `st $f89c.l` — a Scc is a BYTE, so $f89d is NOT written. Neither has
    a reader anywhere in the plaintext image; PORTABILITY.md §6.1 records why."""
    info = _run_publish("copylock-flags", 0x40, 0x20, column=1, row=1)
    assert COPYLOCK_FLAG_B + 1 not in info["writes"], (
        "`st` wrote the byte beside the flag — a Scc is one byte wide")


# --- bg_build_preshifted_copies -------------------------------------------------------------------

PRESHIFT_SPAN = BUFFERS * BUFFER_LEN
PRESHIFT_INSN_CAP = BUILD_PASSES * BUILD_SCANLINES * (BUILD_CELLS_AFTER * 32 + 64) + 4096
_PRESHIFT = leaf.image_glue("bg_build_preshifted_copies")


def _model_preshift(image):
    """The seven derived copies, a 128-byte scanline at a time. Each row closes as a RING: cell 0's
    shifted-out bits are held until cell 15 has been written and then ORed into it."""
    cells = BUFFER_LINE // CELL_BYTES
    out = bytearray(image[BUFFER_BASE:BUFFER_BASE + PRESHIFT_SPAN])
    source = 0
    dest = BUFFER_LEN
    for _pass in range(BUILD_PASSES):
        for _line in range(BUILD_SCANLINES):
            shifted = []
            for cell in range(cells):
                planes = []
                for plane in range(PLANES):
                    at = source + (cell * PLANES + plane) * STATE_WORD_LEN
                    value = int.from_bytes(out[at:at + STATE_WORD_LEN], "big")
                    planes.append(value << PRESHIFT_BITS)
                shifted.append(planes)
            for cell in range(cells):
                carry = shifted[(cell + 1) % cells]
                for plane in range(PLANES):
                    at = dest + (cell * PLANES + plane) * STATE_WORD_LEN
                    value = (shifted[cell][plane] | (carry[plane] >> 16)) & WORD_MASK
                    out[at:at + STATE_WORD_LEN] = value.to_bytes(STATE_WORD_LEN, "big")
            source += BUFFER_LINE
            dest += BUFFER_LINE
    return bytes(out[BUFFER_LEN:])


def _run_preshift(case):
    salt = case_salt(case)
    # Every one of the eight buffers is seeded address-keyed: copy 0 is the source, and copies 1..7
    # are both destination and (for the next pass) source, so an over-run inside the span lands on
    # a byte that is wrong for where it was written.
    pokes = {BUFFER_BASE: keyed_block(BUFFER_BASE, PRESHIFT_SPAN, salt),
             BUILD_CARRY: keyed_block(BUILD_CARRY, PLANES * STATE_WORD_LEN, salt)}

    image = harness.make_image(pokes)
    expected = _model_preshift(image)

    what = f"bg_build_preshifted_copies {case}"
    allowed = [(BUFFER_BASE + BUFFER_LEN, PRESHIFT_SPAN - BUFFER_LEN),
               (BUILD_CARRY, PLANES * STATE_WORD_LEN)]
    info = leaf.run("bg_build_preshifted_copies", _PRESHIFT, allowed, what,
                    regs={"_pokes": pokes}, max_insns=PRESHIFT_INSN_CAP, poison=False)

    written = program_writes(info)
    actual = bytearray(image[BUFFER_BASE + BUFFER_LEN:BUFFER_BASE + PRESHIFT_SPAN])
    for addr, value in written.items():
        if BUFFER_BASE + BUFFER_LEN <= addr < BUFFER_BASE + PRESHIFT_SPAN:
            actual[addr - BUFFER_BASE - BUFFER_LEN] = value
    if bytes(actual) != expected:
        at = next(i for i in range(len(expected)) if actual[i] != expected[i])
        raise AssertionError(
            f"{what}: copy {at // BUFFER_LEN + 1} differs from the model at offset "
            f"{at % BUFFER_LEN:#x} — {actual[at]:#04x} against {expected[at]:#04x}")
    return info


def test_each_copy_is_the_one_below_it_shifted_two_pixels():
    """Seven passes over 176 scanlines, `rol.l #2` a plane word at a time, a1 and a0 never reloaded
    — so pass n reads copy n and writes copy n+1, and the eight copies tile
    WB_BG_BUFFER_BASE..+8*LEN exactly."""
    info = _run_preshift("chain")
    assert min(info["writes"]) >= BUILD_CARRY, "the pre-shift wrote below its own scratch"


def test_the_scanline_closes_as_a_ring():
    """The FIRST cell's shifted-out bits go to WB_BG_BUILD_CARRY and are ORed into the LAST cell of
    the same 128-byte row, so a pixel leaving a row's left edge re-enters at its right. The carry
    band is seeded to something else first, so a port that never wrote it fails."""
    info = _run_preshift("ring")
    for plane in range(PLANES):
        at = BUILD_CARRY + plane * STATE_WORD_LEN
        assert at in info["writes"], f"the carry word at {at:#x} was never written"


def test_the_carry_scratch_is_the_only_write_outside_the_buffers():
    info = _run_preshift("scratch")
    outside = sorted(addr for addr in program_writes(info)
                     if not BUFFER_BASE + BUFFER_LEN <= addr < BUFFER_BASE + PRESHIFT_SPAN)
    assert outside == list(range(BUILD_CARRY, BUILD_CARRY + PLANES * STATE_WORD_LEN)), (
        f"the run wrote {[hex(a) for a in outside[:8]]} outside the buffers")


# --- resource_table_relocate ----------------------------------------------------------------------

RELOCATE_INSN_CAP = 512
_RELOCATE = leaf.image_glue("resource_table_relocate")
RELOCATE_RECORDS = 5


def _run_relocate(case, count=RELOCATE_RECORDS - 1, signature=0):
    salt = case_salt(case)
    records = count + 1
    span = records * RESOURCE_RECORD_BYTES
    pokes = {RESOURCE_HEADER: bytes([signature]),
             RESOURCE_HEADER + RESOURCE_COUNT_OFF: word(count),
             # A margin one record past the band the walk may touch.
             RESOURCE_TABLE: keyed_block(RESOURCE_TABLE, span + RESOURCE_RECORD_BYTES, salt)}

    image = harness.make_image(pokes)
    already = signature == RESOURCE_RELOCATED
    expected = {}
    if not already:
        expected[RESOURCE_HEADER] = bytes([RESOURCE_RELOCATED])
        for record in range(records):
            at = RESOURCE_TABLE + record * RESOURCE_RECORD_BYTES
            offset = int.from_bytes(bytes(image[at:at + LONGWORD_LEN]), "big")
            expected[at] = longword(offset + RESOURCE_TABLE)

    what = f"resource_table_relocate {case}"
    allowed = [(RESOURCE_HEADER, 1)] + [(addr, LONGWORD_LEN) for addr in expected
                                        if addr != RESOURCE_HEADER]
    info = leaf.run("resource_table_relocate", _RELOCATE, allowed, what,
                    regs={"_pokes": pokes}, max_insns=RELOCATE_INSN_CAP)

    written = program_writes(info)
    assert sorted(written) == sorted(addr + i for addr, value in expected.items()
                                     for i in range(len(value))), (
        f"{what}: the write set is {[hex(a) for a in sorted(written)][:8]}, not the "
        f"{len(expected)} field(s) the model names")
    for addr, value in expected.items():
        assert leaf.read_bytes(info, addr, len(value), what) == value
    return info


def test_each_records_leading_offset_becomes_an_absolute_pointer():
    """`addi.l #$248d8,(a5) / lea 20(a5),a5 / dbf d7` — the base ADDED is the table's own address,
    which is why the conversion is not idempotent and needs the signature below."""
    _run_relocate("relocate")


def test_a_stamped_signature_makes_the_routine_a_no_op():
    """`cmpi.b #$45,(a6) / beq` — the whole point of the byte. Nothing at all is written."""
    info = _run_relocate("already-relocated", signature=RESOURCE_RELOCATED)
    assert not program_writes(info), "a second call rewrote the table"


@pytest.mark.parametrize("count", [0, 1, RELOCATE_RECORDS - 1],
                         ids=["one-record", "two-records", "many"])
def test_the_count_is_a_dbf_count_so_zero_relocates_one_record(count):
    """`move.w 8(a6),d7 / ... / dbf d7` runs the body count + 1 times, so no value of the word can
    make the walk skip the first record."""
    _run_relocate(f"count-{count}", count=count)


# --- stage_reset_state ----------------------------------------------------------------------------

RESET_INSN_CAP = 128
_RESET = leaf.image_glue("stage_reset_state")

RESET_CLEARED_WORDS = [PANEL_FRAME_TIMER, PANEL_FRAME_PHASE, PANEL_FRAME_INDEX, PANEL_FRAME_SPARE,
                       STATE_FLAG_A34, SCROLL_FOLLOW_FROZEN, STATE_FLAG_A30, STATE_FLAG_A32]


def _reset_bands():
    block = RESET_BLOCK_LONGS * LONGWORD_LEN + RESET_BLOCK_WORDS * STATE_WORD_LEN
    bands = [(RESET_BLOCK, block), (PANEL_FRAME_DELAY, STATE_WORD_LEN),
             (TILE_33_FLAG, LONGWORD_LEN), (ACTOR_TABLE_SELECTED, LONGWORD_LEN),
             (TILE_INDEX_TAIL, TILE_INDEX_TAIL_LONGS * LONGWORD_LEN)]
    bands += [(addr, STATE_WORD_LEN) for addr in RESET_CLEARED_WORDS]
    return merge_bands(sum(([addr + i for i in range(length)] for addr, length in bands), []))


def _run_reset(case):
    salt = case_salt(case)
    # Every band the reset writes, seeded address-keyed WITH a margin either side, so a clear one
    # word long or one word short lands on a byte that is wrong for its address.
    pokes = {}
    for base, span in ((RESET_BLOCK, 0x30), (PANEL_FRAME_TIMER - 8, 0x20), (TILE_33_FLAG - 8, 0x18),
                       (STATE_FLAG_A30 - 8, 0x20), (ACTOR_TABLE_SELECTED - 8, 0x18),
                       (TILE_INDEX_TAIL - 8, 0x28)):
        pokes[base] = keyed_block(base, span, salt)

    what = f"stage_reset_state {case}"
    info = leaf.run("stage_reset_state", _RESET, _reset_bands(), what,
                    regs={"_pokes": pokes}, max_insns=RESET_INSN_CAP)

    block = RESET_BLOCK_LONGS * LONGWORD_LEN + RESET_BLOCK_WORDS * STATE_WORD_LEN
    assert leaf.read_bytes(info, RESET_BLOCK, block, what) == bytes(block)
    for addr in RESET_CLEARED_WORDS:
        assert leaf.read_int(info, addr, STATE_WORD_LEN, what) == 0, f"{addr:#x} was not cleared"
    assert leaf.read_int(info, PANEL_FRAME_DELAY, STATE_WORD_LEN, what) == PANEL_FRAME_DELAY_INIT
    assert leaf.read_int(info, TILE_33_FLAG, LONGWORD_LEN, what) == 0
    assert leaf.read_int(info, ACTOR_TABLE_SELECTED, LONGWORD_LEN, what) == ACTOR_TABLE_DEFAULT
    return info


@pytest.mark.parametrize("case", ["reset-a", "reset-b"])
def test_the_reset_clears_its_block_and_seeds_the_two_fields_that_are_not_zero(case):
    """Eighteen bytes at $b08 as four longwords and a word, the panel's four timer words (one of
    them to WB_PANEL_FRAME_DELAY_INIT rather than to zero), the three mode flags, the scroll's
    follow gate, and WB_ACTOR_TABLE_SELECTED back to the default table."""
    _run_reset(case)


def test_the_two_tile_33_words_are_cleared_as_one_longword():
    """`clr.l $1514.w` covers WB_TILE_33_FLAG and WB_TILE_33_MODE together — the pair batch 11
    named, and the one place in the image that writes both at once."""
    info = _run_reset("tile-33")
    for offset in range(LONGWORD_LEN):
        assert TILE_33_FLAG + offset in info["writes"]
    assert wb("TILE_33_MODE") == TILE_33_FLAG + STATE_WORD_LEN


def test_the_index_tables_last_eight_entries_are_written_here_and_not_shipped():
    """`lea $21e90.l,a1 / lea 496(a1),a1` then four `move.l #imm,(a1)+`: map bytes $f8..$ff name
    tiles $46..$4b, $40 and $4d.

    WHAT THIS DOES NOT SAY. The .PRG ships NONE of WB_TILE_INDEX_TABLE — $21e90 is past the
    program's last byte, so all 256 entries are loaded from disk and $fed2 overwrites the last
    eight of them. What the DISK holds there beforehand is not pinned by anything here, and cannot
    be: the case seeds that band itself."""
    info = _run_reset("index-tail")
    written = leaf.read_bytes(info, TILE_INDEX_TAIL, TILE_INDEX_TAIL_LONGS * LONGWORD_LEN,
                              "stage_reset_state index-tail")
    assert written == b"".join(longword(value) for value in TILE_INDEX_TAIL_VALUES)
    assert TILE_INDEX_TAIL == TILE_INDEX_TABLE + 496
    entries = TILE_INDEX_TAIL_LONGS * LONGWORD_LEN // STATE_WORD_LEN
    assert TILE_INDEX_TAIL + entries * STATE_WORD_LEN == MAP_ROW_STRIDE, (
        "the tail does not end exactly where WB_MAP_ROW_STRIDE begins")


# --- the banner pair ------------------------------------------------------------------------------

GLYPH_INSN_CAP = 128
BANNER_INSN_CAP = 8192
ROUND_INSN_CAP = 32768

_GLYPH = leaf.register_glue("bg_plot_banner_glyph", [ctypes.c_uint32] * 2, ctypes.c_uint32)
_BANNER = leaf.register_glue("bg_plot_banner", [ctypes.c_uint32], ctypes.c_uint32)
_ROUND = leaf.image_glue("bg_plot_round_banner")


def banner_record(at):
    """(buffer offset, characters) for the record at ``at`` in the shipped image."""
    image = harness.BASE_IMAGE
    offset = u16(image, at)
    text = bytearray()
    cursor = at + STATE_WORD_LEN
    while image[cursor] & BANNER_END == 0:
        text.append(image[cursor])
        cursor += 1
    return offset, bytes(text), cursor


def _glyph_rows(image, glyph, cursor):
    """The (address, byte) pairs one glyph plots, and the cursor it hands back."""
    written = {}
    for row in range(GLYPH_ROWS):
        for plane in range(PLANES):
            written[(cursor + plane * PLANE_STRIDE) & LONGWORD_MASK] = \
                image[glyph + row * PLANES + plane]
        cursor = (cursor + BUFFER_LINE) & LONGWORD_MASK
    advance = ADVANCE_ODD if cursor & 1 else ADVANCE_EVEN
    return written, (cursor + advance - GLYPH_SPAN) & LONGWORD_MASK


def _run_glyph(case, character, cursor):
    salt = case_salt(case)
    glyph = BANNER_FONT + ((character - FIRST_GLYPH_CHAR) & BYTE_MASK) * GLYPH_BYTES
    # A margin a whole cell wide on both sides of the 8 rows the glyph touches.
    seeded = cursor - CELL_BYTES
    pokes = {seeded: keyed_block(seeded, GLYPH_SPAN + 2 * CELL_BYTES, salt)}

    image = harness.make_image(pokes)
    expected, advanced = _glyph_rows(image, glyph, cursor)

    what = f"bg_plot_banner_glyph {case}"
    info = leaf.run("bg_plot_banner_glyph", _GLYPH(glyph, cursor),
                    merge_bands(expected), what,
                    regs={"a0": glyph, "a1": cursor, "_pokes": pokes}, max_insns=GLYPH_INSN_CAP)

    written = program_writes(info)
    assert written == expected, (
        f"{what}: the glyph wrote {len(written)} bytes, not the {len(expected)} its 4-plane "
        f"geometry gives")
    assert info["regs"]["a1"] == advanced, (
        f"{what}: the original left a1={info['regs']['a1']:#x}, not {advanced:#x}")
    assert info["ret"] == advanced, (
        f"{what}: the reconstruction returned {info['ret']:#x}, not {advanced:#x}")
    return info


@pytest.mark.parametrize("parity", [0, 1], ids=["even-cell", "odd-cell"])
def test_the_glyph_hands_back_the_next_cells_cursor(parity):
    """`move.w a1,d0 / btst #0,d0`: an EVEN cell shares its 8-byte plane group with the odd cell
    after it (advance 1); an odd cell's successor is the next group's first byte (advance 7). The
    eight whole scanlines above the test leave the parity as it was on entry."""
    _run_glyph(f"parity-{parity}", ord("A"), BUFFER_BASE + 4 * BUFFER_LINE + CELL_BYTES + parity)


@pytest.mark.parametrize("character", [ord(" "), ord("A"), ord("!"), ord("0")])
def test_the_glyph_comes_from_the_banner_font(character):
    """One byte per plane at WB_PLANE_STRIDE, WB_TEXT_GLYPH_ROWS rows a WB_BG_BUFFER_LINE apart —
    the message box's cell layout over the BACKGROUND buffer's 128-byte line."""
    _run_glyph(f"char-{character}", character, BUFFER_BASE + 2 * BUFFER_LINE)


def _run_banner(case, record):
    salt = case_salt(case)
    offset, text, terminator = banner_record(record)
    cursor = BUFFER_BASE + s16(offset)
    # The whole band the string can reach, plus a cell of margin either side.
    span = (len(text) + 2) * CELL_BYTES + GLYPH_SPAN
    seeded = cursor - CELL_BYTES
    pokes = {seeded: keyed_block(seeded, span, salt)}

    image = harness.make_image(pokes)
    expected = {}
    at = cursor
    for character in text:
        glyph = BANNER_FONT + ((character - FIRST_GLYPH_CHAR) & BYTE_MASK) * GLYPH_BYTES
        rows, at = _glyph_rows(image, glyph, at)
        expected.update(rows)

    what = f"bg_plot_banner {case}"
    info = leaf.run("bg_plot_banner", _BANNER(record), merge_bands(expected), what,
                    regs={"a6": record, "_pokes": pokes}, max_insns=BANNER_INSN_CAP)

    assert program_writes(info) == expected, (
        f"{what}: the banner wrote {len(program_writes(info))} bytes against the "
        f"{len(expected)} its {len(text)} characters give")
    assert info["regs"]["a6"] == terminator, (
        f"{what}: the original left a6={info['regs']['a6']:#x}, not the terminator's "
        f"{terminator:#x} — `tst.b (a6)` does not consume it")
    assert info["ret"] == terminator
    return info, text


@pytest.mark.parametrize("name,record", [("round", BANNER_ROUND), ("perfect", BANNER_PERFECT)])
def test_the_banner_plots_the_record_the_image_ships(name, record):
    """A word of buffer offset then characters, ended by any byte with WB_BG_BANNER_END's bit set —
    which is a SIGN test (`tst.b (a6) / bpl`), not a compare against $ff."""
    info, text = _run_banner(name, record)
    assert text.isascii() and len(text) > 1
    assert harness.BASE_IMAGE[info["regs"]["a6"]] >= BANNER_END


def test_the_terminator_is_a_sign_test_and_the_records_cannot_say_so():
    """REGISTERED, because a mutation reading the terminator as `== $ff` SURVIVES the whole battery.

    $e164 is `tst.b (a6)` and $e166 a `bpl`, so ANY byte from WB_BG_BANNER_END up ends the string —
    but both records the image ships end with exactly $ff, and $e140's only two callers are
    $e110's, which pass exactly those two. So no case can tell the two readings apart without
    fabricating a record, which is what CLAUDE.md's coverage rule refuses. What IS pinned is the
    instruction: the whole-body entry pin above spells `tst.b (a6)` and a `bpl.s`, and this states
    the data that leaves the difference unobservable."""
    body = bytes(harness.BASE_IMAGE[leaf.entry_of("bg_plot_banner"):][:SIZES["bg_plot_banner"]])
    assert tst_b_ind(A6) in body, "$e140 does not sign-test the byte at (a6)"
    # The branch that CONSUMES that test, read out of the shipped body rather than restated: a `beq`
    # here would be the equality reading, and this registration would be about nothing.
    branch_at = body.index(tst_b_ind(A6)) + len(tst_b_ind(A6))
    assert body[branch_at] == opcode(BPL_S)[0], (
        f"$e140 branches on {body[branch_at]:#04x} after its `tst.b (a6)`, not on a `bpl`")
    terminators = {harness.BASE_IMAGE[banner_record(record)[2]]
                   for record in (BANNER_ROUND, BANNER_PERFECT)}
    assert terminators == {0xff}, (
        f"a shipped record ends with {terminators} — the equality reading would now be "
        f"distinguishable and this registration is stale")


def test_the_two_records_are_the_only_ones_the_banners_name():
    """$e110's two `lea`s, read off its own body — so the strings below are the game's and not this
    battery's."""
    body = bytes(harness.BASE_IMAGE[leaf.entry_of("bg_plot_round_banner"):][
        :SIZES["bg_plot_round_banner"]])
    assert body.count(lea_abs_l(A6, BANNER_ROUND)) == 1
    assert body.count(lea_abs_l(A6, BANNER_PERFECT)) == 1
    assert banner_record(BANNER_ROUND)[1] == b"ROUND BONUS"
    assert banner_record(BANNER_PERFECT)[1].startswith(b"PERFECT!")


def _run_round(case, meter_value, meter_max):
    salt = case_salt(case)
    perfect = meter_value == meter_max
    records = [BANNER_ROUND] + ([BANNER_PERFECT] if perfect else [])

    pokes = {HUD_METER_VALUE: word(meter_value), HUD_METER_MAX: word(meter_max),
             BCD_SCORE: b"\x00\x12\x34\x56"}
    for record in records:
        offset, text, _end = banner_record(record)
        seeded = BUFFER_BASE + s16(offset) - CELL_BYTES
        pokes[seeded] = keyed_block(seeded, (len(text) + 2) * CELL_BYTES + GLYPH_SPAN, salt)

    image = harness.make_image(pokes)
    expected = {}
    for record in records:
        offset, text, _end = banner_record(record)
        at = BUFFER_BASE + s16(offset)
        for character in text:
            glyph = BANNER_FONT + ((character - FIRST_GLYPH_CHAR) & BYTE_MASK) * GLYPH_BYTES
            rows, at = _glyph_rows(image, glyph, at)
            expected.update(rows)

    # The bonus arm's callee stages its addend at WB_BCD_ADDEND before folding it in, so that
    # word is part of THIS routine's write set even though nothing here names it.
    allowed = merge_bands(expected) + [(BCD_SCORE, BCD_SCORE_LEN), (BCD_ADDEND, BCD_SCORE_LEN)]
    what = f"bg_plot_round_banner {case}"
    info = leaf.run("bg_plot_round_banner", _ROUND, allowed, what,
                    regs={"_pokes": pokes}, max_insns=ROUND_INSN_CAP)

    written = program_writes(info)
    scoring = set(range(BCD_SCORE, BCD_SCORE + BCD_SCORE_LEN)) \
        | set(range(BCD_ADDEND, BCD_ADDEND + BCD_SCORE_LEN))
    plotted = {addr: value for addr, value in written.items() if addr not in scoring}
    assert plotted == expected, (
        f"{what}: {len(plotted)} plotted bytes against the model's {len(expected)}")
    scored = any(addr in scoring for addr in written)
    assert scored == perfect, (
        f"{what}: the score was {'' if scored else 'not '}touched and the meter was "
        f"{'' if perfect else 'not '}full")
    return info


def test_a_full_meter_scores_the_bonus_and_plots_the_second_banner():
    """`move.w $b6fa.l,d0 / cmp.w $b6f8.l,d0 / bne` — equality alone, so a meter ABOVE its own
    maximum takes the ordinary arm."""
    info = _run_round("perfect", 0x14, 0x14)
    assert leaf.read_int(info, BCD_SCORE, BCD_SCORE_LEN, "bonus") == 0x00133456, (
        "the packed-BCD addend is not WB_BG_BANNER_BONUS added to the seeded score")


@pytest.mark.parametrize("value,maximum", [(0x13, 0x14), (0x15, 0x14), (0, 0x14)],
                         ids=["below", "above", "empty"])
def test_anything_but_equality_plots_the_round_banner_alone(value, maximum):
    _run_round(f"meter-{value}-{maximum}", value, maximum)


# --- $fe4a and $fe8c: the new-game reset and the tail a lost life shares with it -------------------
# Every address either writes is seeded ADDRESS-KEYED with a margin either side, so a clear one word
# long or one word short lands on a byte that is wrong for where it was written. Several of the words
# are neighbours ($bd66..$bd70, $bbbe..$bbc8), so their margins overlap — which is exactly why the
# filler is keyed on the address and not on an index.
RESET_BAND_MARGIN = 4
GAME_RESET_INSN_CAP = LIVES_INSN_CAP + 64

_RESTART_RESET = leaf.image_glue("game_restart_reset")
_LIFE_RESET = leaf.image_glue("game_life_restart_reset")

LIFE_RESET_WORDS = [(HUD_METER_VALUE, HUD_METER_ON_RESTART), (HUD_METER_MAX, HUD_METER_ON_RESTART),
                    (BCD_COUNTER, 0), (EFFECT_STATE_BD66, 0), (EFFECT_STATE_BD68, 0),
                    (EFFECT_STATE_BD6C, 0)]
RESTART_RESET_WORDS = ([(LEVEL_SEQ_INDEX, 0), (LIVES, LIVES_ON_RESTART), (EFFECT_STATE_21E4, 0),
                        (EFFECT_RECORD_LIST, EFFECT_RECORD_EMPTY)]
                       + [(slot, 0) for slot in GAME_RESET_HUD_SLOTS]
                       + [(EFFECT_STATE_BD6A, 0)])
RESET_BANDS = ([(addr, STATE_WORD_LEN) for addr, _value in LIFE_RESET_WORDS + RESTART_RESET_WORDS]
               + [(BCD_SCORE, BCD_SCORE_LEN), (EFFECT_RECORD_WRITE_PTR, EFFECT_RECORD_PTR_LEN),
                  (STAGE_TUNE_LATCH, 1)])


def _put_word(out, addr, value):
    out[addr] = (value >> 8) & BYTE_MASK
    out[addr + 1] = value & BYTE_MASK


def _put_long(out, addr, value):
    _put_word(out, addr, (value >> 16) & WORD_MASK)
    _put_word(out, addr + 2, value & WORD_MASK)


def _life_reset_writes(image):
    """$fe8c's write set: the lives redraw, then the eight fields it reseeds."""
    out = dict(model_lives_draw(image))
    for addr, value in LIFE_RESET_WORDS:
        _put_word(out, addr, value)
    _put_long(out, BCD_SCORE, 0)                    # `clr.l` — the score is a LONGWORD
    out[STAGE_TUNE_LATCH] = STAGE_TUNE_LATCH_RESET  # ...and a BYTE, not the word beside it
    _put_long(out, EFFECT_RECORD_WRITE_PTR, EFFECT_RECORD_LIST)
    return out


def _restart_reset_writes(image):
    """$fe4a's: the head's own eleven words, and then the tail's — run against an image in which
    WB_LIVES ALREADY HOLDS WB_LIVES_ON_RESTART, because the head sets it before falling through."""
    out = {}
    for addr, value in RESTART_RESET_WORDS:
        _put_word(out, addr, value)
    after_head = bytearray(image)
    for addr, value in out.items():
        after_head[addr] = value
    out.update(_life_reset_writes(after_head))
    return out


def _reset_pokes(salt, lives):
    pokes = {}
    for addr, length in RESET_BANDS:
        lo = addr - RESET_BAND_MARGIN
        pokes[lo] = keyed_block(lo, length + 2 * RESET_BAND_MARGIN, salt)
    # ...and the screens, the icon and WB_LIVES itself, whose poke must land AFTER the band above
    # it so a case's own lives count survives the filler.
    pokes.update(lives_pokes(salt, lives))
    return pokes


def _run_game_reset(name, glue, model, lives, case):
    what = f"{name} {case}"
    pokes = _reset_pokes(case_salt(what), lives)
    image = harness.make_image(pokes)
    expected = model(image)

    info = leaf.run(name, glue, merge_bands(expected), what, regs={"_pokes": pokes},
                    max_insns=GAME_RESET_INSN_CAP)
    written = leaf.program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {len(written)} bytes against the model's {len(expected)}; "
        f"only in one of them: "
        f"{sorted(hex(a) for a in set(written) ^ set(expected))[:8]}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")
    return expected


@pytest.mark.parametrize("lives", [0, 1, 3, 5, 0xffff], ids=lambda v: f"lives{v:#06x}")
def test_the_life_restart_reset_redraws_the_lives_it_finds(lives):
    """$fe8c takes WB_LIVES as it stands — its caller at $c00 has already decremented it — so the
    number of icons is the case's own seed and not a constant."""
    _run_game_reset("game_life_restart_reset", _LIFE_RESET, _life_reset_writes, lives,
                    f"lives {lives:#06x}")


@pytest.mark.parametrize("lives", [0, 1, 5, 0xffff], ids=lambda v: f"lives{v:#06x}")
def test_the_new_game_reset_sets_the_lives_before_the_tail_draws_them(lives):
    """The head's `move.w #$3,$be2.w` runs BEFORE the fall-through, so however many lives the case
    seeds the display comes out at WB_LIVES_ON_RESTART. A port that drew first, or that called the
    tail with the old count, differs on the icons rather than on the count."""
    expected = _run_game_reset("game_restart_reset", _RESTART_RESET, _restart_reset_writes, lives,
                               f"lives {lives:#06x}")
    assert (expected[LIVES] << 8 | expected[LIVES + 1]) == LIVES_ON_RESTART


def test_the_new_game_reset_empties_the_record_list_and_the_life_one_does_not():
    """The one thing only the head does to the effect list: it writes WB_EFFECT_RECORD_EMPTY into
    the first word while BOTH halves point the write pointer back at the base. So a life restarted
    this way keeps whatever record was there, which is behaviour and not an omission."""
    head_only = {addr for addr, _value in RESTART_RESET_WORDS}
    assert EFFECT_RECORD_LIST in head_only
    assert EFFECT_RECORD_LIST not in {addr for addr, _value in LIFE_RESET_WORDS}

    life = _run_game_reset("game_life_restart_reset", _LIFE_RESET, _life_reset_writes, 2, "list intact")
    assert EFFECT_RECORD_LIST not in life, (
        "the life reset wrote the record list's first word, which only the new-game head does")
    assert EFFECT_RECORD_WRITE_PTR in life, "the life reset left the write pointer alone"


def test_the_two_resets_are_ghidras_one_function_split_at_its_second_entrant():
    """The claim ../names.txt makes, as arithmetic: the two bodies are adjacent and add back up to
    the 136 bytes ../out/hw_scan.tsv records for the single function at $fe4a. A split at the wrong
    instruction fails here as well as on the two entry pins."""
    head = leaf.entry_of("game_restart_reset")
    tail = leaf.entry_of("game_life_restart_reset")
    assert head + SIZES["game_restart_reset"] == tail, (
        f"the head ends at {head + SIZES['game_restart_reset']:#x}, not at the tail's {tail:#x}")
    assert SIZES["game_restart_reset"] + SIZES["game_life_restart_reset"] == (
        GHIDRA_RESET_FUNCTION_BYTES), (
        f"the two halves are {SIZES['game_restart_reset']} + "
        f"{SIZES['game_life_restart_reset']} bytes, which is not the scan's "
        f"{GHIDRA_RESET_FUNCTION_BYTES}")
    # The head has no `rts` of its own: the byte pair where one would be is the tail's first
    # instruction, which is what "falls through" means on the bytes.
    assert bytes(harness.BASE_IMAGE[tail - len(RTS):tail]) != RTS, (
        "the head ends in an `rts`, so it does not fall through and the split is wrong")
