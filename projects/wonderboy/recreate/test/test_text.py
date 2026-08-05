"""Differential test for src/text.c — the message box: its driver at $bd8a and the plotter below it.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and states the write set EXACTLY — the 32 bytes the
4-plane geometry gives for one glyph, or the whole WB_TEXT_BUFFER plus the state fields for a
compose, or the blitted rectangle plus the countdown for a blit.

WHAT MAKES THIS BATTERY DIFFERENT FROM THE OTHERS HERE.

  * THE TWO PLOTTER ROUTINES ARE ONE ROUTINE. $bf4e has no `rts`: it computes a glyph pointer and
    falls through into $bf5e, whose `rts` returns to ITS caller. That the two are contiguous is
    asserted (`test_the_prelude_falls_through_into_the_plotter`) rather than assumed, because it is
    the whole justification for reconstructing them as a prelude that CALLS the plotter and returns
    its result.
  * THE DESTINATION IS AN 88-BYTE-WIDE BUFFER, NOT THE SCREEN. Every case seeds the whole of
    WB_TEXT_BUFFER address-keyed, so a plot that stepped a 160-byte scanline, or ran a row long,
    lands on bytes that are wrong FOR WHERE THEY WERE WRITTEN. The plotter cases' leading margin is
    WB_TEXT_STATE_BYTES — the ten at $c030..$c039 — and stops there for a reason: the plotter's own
    code ends at $c02f, and poking over the instructions the oracle is about to execute would be a
    different test.
  * THE SOURCE IS THE GAME'S OWN DATA. The font at WB_TEXT_GLYPH_TABLE, the eight frame glyphs below
    it and the 117 message records at WB_TEXT_MESSAGE_TABLE are all shipped in the .PRG (unlike the
    tile bitmaps, which are loaded at runtime), so nothing here invents a glyph or a message — which
    is what keeps a wrong plane order, a wrong source stride or a wrong record layout visible.
  * THE DRIVER IS A STATE MACHINE IN TEN BYTES, AND ITS PHASES ARE SEEDED ONE BY ONE. $bd8a's three
    arms and the four sub-branches inside them are all picked by WB_TEXT_STATE_BYTES, which is plain
    RAM — so every phase and both sides of every branch are reachable from a case that pokes it,
    including the two no message RECORD can ask for: an already-armed countdown under a message that
    posts no lifetime, and a countdown that wraps past zero instead of landing on it. Those two are
    LIVE gameplay states rather than dead branches — a lifetime is posted by a caller alongside the
    request and is not part of a record at all, and WB_TEXT_LIFETIME_ARMED is never cleared, so both
    arise from what earlier messages left in the state band. What the cases seed is that history.
  * THE MESSAGE TABLE'S EXTENT IS READ OFF THE DATA. There is exactly ONE reference to $a09c in the
    whole image, so nothing declares how many messages there are;
    `test_the_message_table_is_bounded_by_its_own_data` derives WB_TEXT_MESSAGE_COUNT from three
    properties of the shipped bytes instead.

KNOWINGLY NOT PINNED
  * d7, WHICH THE PLOTTER CLOBBERS. It parks the ENDED cursor there for the `btst`; the kit's oracle
    reports d0/d1/a0/a1 only, so no case can compare it. No caller reads it either ($bd8a's own d0/
    d6/a6 are what its loops carry).
  * WHAT $bd8a LEAVES IN d0/d1/a0/a1/d6/a6. Each of the three arms walks out with different rubbish
    — the terminator byte and the last glyph's source, or the blit's two ended cursors — and
    game_main_loop's next `jsr` reloads everything. The C returns nothing; the driver cases assert
    the ORACLE's d0/a0/a1 against the model where the arm defines them, which documents them without
    pinning the reconstruction.
  * THE ATTRIBUTION (POISON) PASS, ON THE DRIVER'S CASES ONLY. Every non-trivial arm WRITES
    WB_TEXT_REQUEST, so poisoning the oracle's outputs turns a zero request into $ff and both cores
    then take the DISMISS arm — the pass would still agree, having tested the wrong arm. The cases
    below run with `poison=False` and get the same guarantee another way: they seed the destination
    address-keyed (so the pre-image is never the answer), state the oracle's write set EXACTLY, and
    compare every written byte against a model built from the game's own data.
  * AN ID PAST WB_TEXT_MESSAGE_COUNT. `subi.b #$1,d0 / lsl.w #2,d0` indexes with a word, so ids
    118..256 read a "pointer" out of the record bytes and walk wherever it names. Fifty-two writers
    raise WB_TEXT_REQUEST and only their immediates are bounded (they top out at $64), so this is
    not provably unreachable — but reaching it from a case means fabricating a pointer into a table
    the game ships, which is the thing CLAUDE.md's coverage rule refuses. Left honestly unpinned.
"""
import collections
import ctypes

import pytest

import harness
import leaf
from leaf import (RTS, branch, branch_over, case_salt, clr_b_abs_l, clr_w_abs_l, dbf, dbf_over,
                  forward_branch, keyed_block, keyed_byte, lea_abs_l, lea_d16, lea_indexed,
                  longword, merge_bands, move_w_imm_dn, movea_l_abs_w, moveq_0_dn, mulu_w_imm_dn,
                  opcode, program_writes, st_abs_l, subq_w_abs_l, tst_b_abs_l, tst_w_abs_l, word)
from layout import wb

import loader   # noqa: E402  (harness puts the kit's oracle on sys.path)

# --- the geometry, from the header both languages read -------------------------------------------
GLYPH_TABLE = wb("TEXT_GLYPH_TABLE")
FIRST_GLYPH_CHAR = wb("TEXT_FIRST_GLYPH_CHAR")
GLYPH_SHIFT = wb("TEXT_GLYPH_SHIFT")
GLYPH_BYTES = wb("TEXT_GLYPH_BYTES")
GLYPH_ROWS = wb("TEXT_GLYPH_ROWS")
FRAME_GLYPHS = wb("TEXT_FRAME_GLYPHS")
FRAME_GLYPH_COUNT = wb("TEXT_FRAME_GLYPH_COUNT")
BUFFER = wb("TEXT_BUFFER")
BUFFER_LEN = wb("TEXT_BUFFER_LEN")
BUFFER_LINE = wb("TEXT_BUFFER_LINE")
STATE_BYTES = wb("TEXT_STATE_BYTES")
ADVANCE_EVEN = wb("TEXT_CELL_ADVANCE_EVEN")
ADVANCE_ODD = wb("TEXT_CELL_ADVANCE_ODD")
PLANES = wb("PLANES")
PLANE_STRIDE = wb("PLANE_STRIDE")
SCREEN_LINE = wb("SCREEN_LINE")
SCREEN_SCANLINES = wb("SCREEN_SCANLINES")
SCREEN_BACK = wb("SCREEN_BACK")

# --- the driver's own state, table and geometry ---------------------------------------------------
REQUEST = wb("TEXT_REQUEST")
REQUEST_DISMISS = wb("TEXT_REQUEST_DISMISS")
BOX_ACTIVE = wb("TEXT_BOX_ACTIVE")
BOX_ACTIVE_SET = wb("TEXT_BOX_ACTIVE_SET")
BOX_ROWS = wb("TEXT_BOX_ROWS")
BOX_TOP_LINE = wb("TEXT_BOX_TOP_LINE")
LIFETIME_REQUEST = wb("TEXT_LIFETIME_REQUEST")
LIFETIME_ARMED = wb("TEXT_LIFETIME_ARMED")
LIFETIME_ARMED_SET = wb("TEXT_LIFETIME_ARMED_SET")
LIFETIME_LEFT = wb("TEXT_LIFETIME_LEFT")

MESSAGE_TABLE = wb("TEXT_MESSAGE_TABLE")
MESSAGE_COUNT = wb("TEXT_MESSAGE_COUNT")
MESSAGE_PTR_SHIFT = wb("TEXT_MESSAGE_PTR_SHIFT")
MESSAGE_FIRST_ID = wb("TEXT_MESSAGE_FIRST_ID")
RECORD_ROWS = wb("TEXT_RECORD_ROWS")
RECORD_TOP_LINE = wb("TEXT_RECORD_TOP_LINE")
RECORD_STRING = wb("TEXT_RECORD_STRING")
NEWLINE = wb("TEXT_NEWLINE")
STRING_END = wb("TEXT_STRING_END")

BOX_CELLS = wb("TEXT_BOX_CELLS")
BOX_EDGE_CELLS = wb("TEXT_BOX_EDGE_CELLS")
BOX_MIN_ROWS = wb("TEXT_BOX_MIN_ROWS")
CELL_GROUP = wb("TEXT_CELL_GROUP")
CELL_ROW_BYTES = wb("TEXT_CELL_ROW_BYTES")
ROW_ADVANCE = wb("TEXT_ROW_ADVANCE")
INTERIOR_SKIP = wb("TEXT_INTERIOR_SKIP")
FIRST_TEXT_LINE = wb("TEXT_FIRST_TEXT_LINE")
TEXT_ORIGIN = wb("TEXT_TEXT_ORIGIN")
BLIT_X_BYTES = wb("TEXT_BLIT_X_BYTES")
BLIT_LONGWORDS = wb("TEXT_BLIT_LONGWORDS")
BLIT_SKIP = wb("TEXT_BLIT_SKIP")
BLIT_ROW_SHIFT = wb("TEXT_BLIT_ROW_SHIFT")

SCREEN_BUFFERS = leaf.SCREEN_BUFFERS
# What one buffer HOLDS, which is not what the two are spaced by: $8000 apart leaves 768 bytes past
# the last scanline, so a bound taken from the spacing would admit a box drawn off the screen.
SCREEN_LEN = SCREEN_SCANLINES * SCREEN_LINE

WORD_LEN = 2
LONGWORD_LEN = 4
BYTE_MASK = 0xff
WORD_MASK = 0xffff
LONGWORD_MASK = 0xffffffff

# What the plotter's own body walks before the parity tail measures from it, and the two `lea`
# displacements the image carries — spelt as the geometry rather than as -621/-615, so a moved
# WB_TEXT_BUFFER_LINE fails the entry pin instead of quietly agreeing with it.
LAST_PLANE_OFFSET = (PLANES - 1) * PLANE_STRIDE
ROW_STEP = BUFFER_LINE - LAST_PLANE_OFFSET
GLYPH_SPAN = (GLYPH_ROWS - 1) * BUFFER_LINE + LAST_PLANE_OFFSET

# 32 stores, 32 `lea`s and a handful of instructions either side; a cap that stays a cap.
PLOT_INSN_CAP = 96


# --- the shipped message table, walked the way $bd8a walks it -------------------------------------
# Nothing in the image declares the table's length, so everything below — the case list, the
# instruction caps and the invariants the reconstruction relies on — is derived from this one walk
# of the game's own bytes rather than from numbers restated here.
Message = collections.namedtuple("Message", "index pointer rows top_line string length")


def _walk_message_table():
    image = harness.BASE_IMAGE
    messages = []
    for index in range(MESSAGE_COUNT):
        entry = MESSAGE_TABLE + (index << MESSAGE_PTR_SHIFT)
        pointer = int.from_bytes(image[entry:entry + LONGWORD_LEN], "big")
        assert 0 <= pointer < loader.PROGRAM_END, (
            f"message {index}'s pointer {pointer:#x} is outside the program — the table is not "
            f"{MESSAGE_COUNT} entries long, or WB_TEXT_MESSAGE_TABLE is not where it starts")
        at = pointer + RECORD_STRING
        # Bounded rather than a bare `while`: a record with no terminator would otherwise walk the
        # whole image here and fail as a MemoryError instead of naming the record.
        while at < loader.PROGRAM_END and image[at] != STRING_END:
            at += 1
        assert at < loader.PROGRAM_END, f"message {index}'s string has no WB_TEXT_STRING_END"
        messages.append(Message(index, pointer, image[pointer + RECORD_ROWS],
                                image[pointer + RECORD_TOP_LINE],
                                bytes(image[pointer + RECORD_STRING:at]), at + 1 - pointer))
    return messages


MESSAGES = _walk_message_table()
MAX_BOX_ROWS = max(message.rows for message in MESSAGES)
LONGEST_STRING = max(len(message.string) for message in MESSAGES)


def message_id(index):
    """The WB_TEXT_REQUEST value that selects ``MESSAGES[index]`` — the table is 1-based."""
    return index + MESSAGE_FIRST_ID


# The caps, from the routine's own geometry. A compose clears the buffer a longword at a time, plots
# two full-width frame rows plus two cells per interior row, and then one cell per character.
GLYPH_PLOT_INSNS = 2 * PLANES * GLYPH_ROWS + 8      # 32 stores, 32 `lea`s, the parity tail, the call
CLEAR_INSNS = 2 * (BUFFER_LEN // LONGWORD_LEN)
COMPOSE_CELLS = 2 * BOX_CELLS + 2 * (MAX_BOX_ROWS - 2)
COMPOSE_INSN_CAP = CLEAR_INSNS + (COMPOSE_CELLS + LONGEST_STRING) * GLYPH_PLOT_INSNS + 64
BLIT_INSN_CAP = (MAX_BOX_ROWS << BLIT_ROW_SHIFT) * (BLIT_LONGWORDS + 2) + 64


# --- the opcodes only this battery spells ---------------------------------------------------------
A0, A1, A6 = 0, 1, 6
D0, D1, D6, D7 = 0, 1, 6, 7
BNE_W, BEQ_W = 0x6600, 0x6700
BRA_S = 0x6000

MOVE_B_POSTINC_A0_IND_A1 = opcode(0x1298)
MOVE_L_A1_D7 = opcode(0x2e09)
MOVE_L_POSTINC_POSTINC = opcode(0x22d8)   # `move.l (a0)+,(a1)+`, the blit's unrolled row
CLR_L_POSTINC_A0 = opcode(0x4298)
MOVEA_L_A6_IND_A6 = opcode(0x2c56)
MOVE_B_POSTINC_A6_D0 = opcode(0x101e)
MOVE_L_D6_D1 = opcode(0x2206)

# The 68000 operand-size field, as `lsl` and `subq`/`addq` both spell it.
SIZE_WORD, SIZE_LONG = 1, 2


def subi_b_dn(reg, value):
    return opcode(0x0400 | reg) + word(value)


def lsl_imm_dn(count, reg, size):
    """`lsl.#n,Dn` at one of the three operand sizes — the prelude's index shift is a LONGWORD one
    (which is what lets d0's high bytes reach the index) and the driver's table index a WORD one."""
    return opcode(0xe108 | ((count & 7) << 9) | (size << 6) | reg)


def cmpi_b_abs_l(value, addr):
    return opcode(0x0c39) + word(value) + longword(addr)


def cmp_b_imm_dn(reg, value):
    return opcode(0xb03c | (reg << 9)) + word(value)


def move_b_abs_l_dn(reg, addr):
    return opcode(0x1039 | (reg << 9)) + longword(addr)


def move_b_postinc_abs_l(source, addr):
    """`move.b (An)+,<abs>.l` — how the record's two geometry bytes are latched."""
    return opcode(0x1000 | (1 << 9) | (7 << 6) | (3 << 3) | source) + longword(addr)


def move_w_abs_l_abs_l(source, destination):
    return leaf.MOVE_W_ABS_L_ABS_L + longword(source) + longword(destination)


def move_w_imm_abs_l(value, addr):
    return leaf.MOVE_W_IMM_ABS_L + word(value) + longword(addr)


def subq_dn(reg, value, size):
    return opcode(0x5100 | ((value & 7) << 9) | (size << 6) | reg)


def addq_l_dn(reg, value):
    return opcode(0x5000 | ((value & 7) << 9) | (SIZE_LONG << 6) | reg)


def bra_s(here, target):
    """`bra.s` as assembled AT ``here`` — the two inside the string loop close it backwards."""
    displacement = target - (here + WORD_LEN)
    assert -0x80 <= displacement < 0, f"{displacement} does not fit a `bra.s` byte displacement"
    return opcode(BRA_S | (displacement & BYTE_MASK))


def btst_imm_dn(bit, reg):
    return opcode(0x0800 | reg) + word(bit)


# --- the entry pins -------------------------------------------------------------------------------

def _plot_glyph_entry():
    plane_step = lea_d16(A1, PLANE_STRIDE)
    row = MOVE_B_POSTINC_A0_IND_A1 + (plane_step + MOVE_B_POSTINC_A0_IND_A1) * (PLANES - 1)
    body = (row + lea_d16(A1, ROW_STEP)) * (GLYPH_ROWS - 1) + row
    even = lea_d16(A1, -(GLYPH_SPAN - ADVANCE_EVEN)) + RTS
    return (body + MOVE_L_A1_D7 + btst_imm_dn(0, D7) + branch(BNE_W, even) + even
            + lea_d16(A1, -(GLYPH_SPAN - ADVANCE_ODD)) + RTS)


def _plot_char_entry():
    return (lea_abs_l(A0, GLYPH_TABLE) + subi_b_dn(D0, FIRST_GLYPH_CHAR)
            + lsl_imm_dn(GLYPH_SHIFT, D0, SIZE_LONG) + lea_indexed(A0, D0))


# The frame glyphs by the role src/text.c names them, in the order the eight `bsr` sites pass them.
(TOP_LEFT, TOP_EDGE, TOP_RIGHT, LEFT_EDGE, RIGHT_EDGE,
 BOTTOM_LEFT, BOTTOM_EDGE, BOTTOM_RIGHT) = range(FRAME_GLYPH_COUNT)

# The four instruction lengths a branch here is measured in. A `bra.s` carries its displacement IN
# the opcode word and so is half of a `bcc.w`; a glyph call is the `lea` that names the glyph plus
# the `bsr.w` itself. Named because a branch built out of the pieces it jumps over cannot state a
# span that has not been assembled yet — the string loop's two forward branches jump over their own
# closing `bra.s`, and the loop is not built at the point the branch is emitted.
SHORT_BRANCH_LEN = len(opcode(0))
BRANCH_LEN = len(opcode(0)) + WORD_LEN
CALL_LEN = len(leaf.BSR_W) + WORD_LEN
GLYPH_CALL_LEN = len(lea_abs_l(A0, 0)) + CALL_LEN


def frame_glyph(role):
    return FRAME_GLYPHS + role * GLYPH_BYTES


def _draw_box(at):
    """$be1e..$bed0: the frame's nine `bsr` sites and the string loop's tenth, assembled at the
    address ``at`` they actually land on — a `bsr` displacement depends on where it sits, so a piece
    inserted or dropped above one of them fails on the bytes rather than shifting silently."""
    plot_glyph = leaf.entry_of("text_plot_glyph")
    plot_char = leaf.entry_of("text_plot_char")
    body = bytearray()

    def emit(*pieces):
        for piece in pieces:
            body.extend(piece)

    def call(target):
        emit(leaf.bsr_w(at + len(body), target))

    def horizontal_row(left_corner):
        """A corner, BOX_EDGE_CELLS of the edge glyph under a `dbf`, the other corner."""
        emit(lea_abs_l(A0, frame_glyph(left_corner)))
        call(plot_glyph)
        emit(move_w_imm_dn(D0, BOX_EDGE_CELLS - 1), lea_abs_l(A0, frame_glyph(left_corner + 1)))
        call(plot_glyph)
        emit(dbf_over(D0, GLYPH_CALL_LEN), lea_abs_l(A0, frame_glyph(left_corner + 2)))
        call(plot_glyph)

    emit(lea_abs_l(A1, BUFFER))
    horizontal_row(TOP_LEFT)

    emit(lea_d16(A1, ROW_ADVANCE),
         moveq_0_dn(D0), move_b_abs_l_dn(D0, BOX_ROWS), subq_dn(D0, BOX_MIN_ROWS, SIZE_WORD))
    interior_at = len(body)
    emit(lea_abs_l(A0, frame_glyph(LEFT_EDGE)))
    call(plot_glyph)
    emit(lea_d16(A1, INTERIOR_SKIP), lea_abs_l(A0, frame_glyph(RIGHT_EDGE)))
    call(plot_glyph)
    emit(lea_d16(A1, ROW_ADVANCE))
    emit(dbf_over(D0, len(body) - interior_at))

    horizontal_row(BOTTOM_LEFT)

    emit(move_w_imm_dn(D6, FIRST_TEXT_LINE))
    line_at = at + len(body)
    emit(MOVE_L_D6_D1, lea_abs_l(A1, TEXT_ORIGIN), mulu_w_imm_dn(D1, CELL_ROW_BYTES),
         lea_indexed(A1, D1))
    char_at = at + len(body)
    # The newline test comes FIRST, so a $0a is a line break even though $ff is the terminator.
    emit(moveq_0_dn(D0), MOVE_B_POSTINC_A6_D0, cmp_b_imm_dn(D0, NEWLINE),
         branch_over(BNE_W, len(addq_l_dn(D6, 1)) + SHORT_BRANCH_LEN),
         addq_l_dn(D6, 1))
    emit(bra_s(at + len(body), line_at))
    emit(cmp_b_imm_dn(D0, STRING_END),
         branch_over(BEQ_W, CALL_LEN + SHORT_BRANCH_LEN))
    call(plot_char)
    emit(bra_s(at + len(body), char_at))
    emit(RTS)
    return bytes(body)


def _compose_arm(at):
    """$bda0: the dismiss test, the lifetime latch, the record walk, the buffer clear and the draw."""
    dismiss = clr_b_abs_l(REQUEST) + clr_b_abs_l(BOX_ACTIVE) + RTS
    latch = (move_w_abs_l_abs_l(LIFETIME_REQUEST, LIFETIME_LEFT)
             + clr_w_abs_l(LIFETIME_REQUEST)
             + move_w_imm_abs_l(LIFETIME_ARMED_SET, LIFETIME_ARMED))
    clear = (move_w_imm_dn(D0, BUFFER_LEN // LONGWORD_LEN - 1) + lea_abs_l(A0, BUFFER)
             + CLR_L_POSTINC_A0 + dbf(D0, CLR_L_POSTINC_A0))

    head = (cmpi_b_abs_l(REQUEST_DISMISS, REQUEST) + branch(BNE_W, dismiss) + dismiss
            + tst_w_abs_l(LIFETIME_REQUEST) + branch(BEQ_W, latch) + latch
            + st_abs_l(BOX_ACTIVE)
            + moveq_0_dn(D0) + move_b_abs_l_dn(D0, REQUEST) + subi_b_dn(D0, MESSAGE_FIRST_ID)
            + lea_abs_l(A6, MESSAGE_TABLE) + lsl_imm_dn(MESSAGE_PTR_SHIFT, D0, SIZE_WORD)
            + lea_indexed(A6, D0) + MOVEA_L_A6_IND_A6
            + move_b_postinc_abs_l(A6, BOX_ROWS) + move_b_postinc_abs_l(A6, BOX_TOP_LINE)
            + clr_b_abs_l(REQUEST)
            + clear)
    return head + _draw_box(at + len(head))


def _blit_arm():
    """$bed2: the countdown tick and the rectangle. No `bsr`, so it needs no address of its own."""
    blit_row = MOVE_L_POSTINC_POSTINC * BLIT_LONGWORDS + lea_d16(A1, BLIT_SKIP)
    take_down = clr_b_abs_l(BOX_ACTIVE)
    tick = subq_w_abs_l(1, LIFETIME_LEFT) + branch(BNE_W, take_down) + take_down
    return (clr_b_abs_l(REQUEST)
            + tst_w_abs_l(LIFETIME_ARMED) + branch(BEQ_W, tick) + tick
            + lea_abs_l(A0, BUFFER) + movea_l_abs_w(A1, SCREEN_BACK)
            + moveq_0_dn(D0) + move_b_abs_l_dn(D0, BOX_TOP_LINE)
            + mulu_w_imm_dn(D0, SCREEN_LINE) + lea_indexed(A1, D0, BLIT_X_BYTES)
            + moveq_0_dn(D0) + move_b_abs_l_dn(D0, BOX_ROWS)
            + lsl_imm_dn(BLIT_ROW_SHIFT, D0, SIZE_LONG) + subq_dn(D0, 1, SIZE_LONG)
            + blit_row + dbf(D0, blit_row)
            + RTS)


def _run_message_box_entry():
    """$bd8a: the two flag tests that pick the arm, then the two arms."""
    entry = leaf.entry_of("text_run_message_box")
    request_test = tst_b_abs_l(REQUEST)
    active_test = tst_b_abs_l(BOX_ACTIVE)
    prologue_len = len(request_test) + BRANCH_LEN + len(active_test) + BRANCH_LEN + len(RTS)

    compose = _compose_arm(entry + prologue_len)
    blit = _blit_arm()
    prologue = (request_test + opcode(BNE_W) + forward_branch(len(active_test) + BRANCH_LEN
                                                              + len(RTS))
                + active_test + opcode(BNE_W) + forward_branch(len(RTS) + len(compose))
                + RTS)
    assert len(prologue) == prologue_len, "the prologue's own length is not what its arms assumed"
    return prologue + compose + blit


ENTRY_BYTES = {
    "text_plot_glyph": _plot_glyph_entry(),
    "text_plot_char": _plot_char_entry(),
    "text_run_message_box": _run_message_box_entry(),
}
RECONSTRUCTED_ROUTINES = 3


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    ("text_plot_glyph", 210),
    ("text_plot_char", 16),
    ("text_run_message_box", 452),
], ids=lambda v: v if isinstance(v, str) else f"{v}B")
def test_the_reconstructed_body_is_the_whole_routine(name, size):
    """The sizes ../out/hw_scan.tsv records, so a body reconstructed one instruction short fails
    here instead of leaving the tail unpinned."""
    assert len(ENTRY_BYTES[name]) == size, (
        f"{name}'s pin is {len(ENTRY_BYTES[name])} bytes against the {size} the scan records")


# --- what the two entry points are ---------------------------------------------------------------

def test_the_prelude_falls_through_into_the_plotter():
    """$bf4e ends where $bf5e begins and has no `rts` of its own, which is the whole reason
    `text_plot_char` is written as a call to `text_plot_glyph` rather than as a routine of its
    own."""
    prelude = leaf.entry_of("text_plot_char")
    plotter = leaf.entry_of("text_plot_glyph")
    assert prelude + len(ENTRY_BYTES["text_plot_char"]) == plotter, (
        f"the prelude at {prelude:#x} does not end at the plotter's {plotter:#x}")
    assert RTS not in ENTRY_BYTES["text_plot_char"], (
        "the prelude carries an `rts`, so it does not fall through and the two are separate "
        "routines after all")


def test_the_row_advance_is_the_buffers_line_and_not_the_screens():
    """The 88 is the message buffer's own width: $bd8a blits it out WB_TEXT_BUFFER_LINE bytes at a
    time plus a skip that makes up a screen scanline, and the buffer is exactly
    WB_TEXT_BUFFER_LEN bytes ending where panel_restore_dirty_regions begins."""
    assert BUFFER_LINE < SCREEN_LINE, "an 88-byte line that is not narrower than the screen's 160"
    assert BUFFER + BUFFER_LEN == leaf.entry_of("panel_restore_dirty_regions"), (
        f"the buffer runs to {BUFFER + BUFFER_LEN:#x}, which is not the "
        f"{leaf.entry_of('panel_restore_dirty_regions'):#x} that bounds it")
    plotter_end = leaf.entry_of("text_plot_glyph") + len(ENTRY_BYTES["text_plot_glyph"])
    assert plotter_end == BUFFER - STATE_BYTES, (
        f"the band between the plotter's last byte and the buffer is {BUFFER - plotter_end} bytes, "
        f"not the {STATE_BYTES} WB_TEXT_STATE_BYTES names — so this battery's leading margin is no "
        f"longer the band it says it is")


def test_the_parity_the_tail_reads_is_the_starting_cursors_own():
    """The plotter tests bit 0 of the cursor its eight rows ENDED on, and src/text.c reproduces that
    rather than testing the start — but the two are the same bit, because the body spans an EVEN
    number of bytes.

    Stated here because it is this batch's one surviving mutation: reading the start instead is an
    EQUIVALENCE for every cursor rather than a hole in the sweep, and it stops being one the moment
    a geometry constant turns the span odd.
    """
    assert GLYPH_SPAN % 2 == 0, (
        f"the body spans {GLYPH_SPAN} bytes, which is odd — the ended cursor's parity is no longer "
        f"the starting cursor's, and src/text.c's `ended` has become load-bearing")


def test_the_eight_frame_glyphs_are_what_the_plotters_callers_pass():
    """A whole-image scan of the eight `bsr text_plot_glyph` sites: each is immediately preceded by
    a `lea <abs>.l,a0`, and the eight addresses those carry are the eight consecutive glyphs at
    WB_TEXT_FRAME_GLYPHS. So the constant is read off the callers rather than declared."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    plotter = leaf.entry_of("text_plot_glyph")

    sites = []
    for at in range(0, len(program) - LONGWORD_LEN, WORD_LEN):
        if program[at:at + WORD_LEN] != leaf.BSR_W:
            continue
        displacement = int.from_bytes(program[at + WORD_LEN:at + LONGWORD_LEN], "big")
        displacement -= 0x10000 if displacement & 0x8000 else 0
        if at + WORD_LEN + displacement == plotter:
            sites.append(at)
    assert len(sites) == FRAME_GLYPH_COUNT, (
        f"{len(sites)} `bsr` sites reach the plotter, not the {FRAME_GLYPH_COUNT} ../names.txt "
        f"records")

    passed = []
    for at in sites:
        lea = at - len(lea_abs_l(A0, 0))
        assert program[lea:lea + WORD_LEN] == opcode(0x41f9), (
            f"the `bsr` at {at:#x} is not preceded by a `lea <abs>.l,a0`")
        passed.append(int.from_bytes(program[lea + WORD_LEN:at], "big"))
    assert passed == [FRAME_GLYPHS + k * GLYPH_BYTES for k in range(FRAME_GLYPH_COUNT)], (
        f"the eight sites pass {[hex(a) for a in passed]}, not the eight consecutive glyphs at "
        f"{FRAME_GLYPHS:#x}")
    assert FRAME_GLYPHS + FRAME_GLYPH_COUNT * GLYPH_BYTES == GLYPH_TABLE, (
        "the frame glyphs do not run up to the font, so the two are not the one region this "
        "battery reads them as")


def test_the_shipped_font_is_data_this_battery_can_tell_apart():
    """The glyphs the cases below plot are the game's own bytes, so a zero source would make a
    wrong plane order or a wrong stride invisible. Space is deliberately all-zero (which is what a
    space plots); every other glyph a case uses must not be."""
    space = bytes(harness.BASE_IMAGE[GLYPH_TABLE:GLYPH_TABLE + GLYPH_BYTES])
    assert space == bytes(GLYPH_BYTES), "the glyph for char $20 is not the blank a space plots"
    for source in _NONBLANK_SOURCES:
        assert any(harness.BASE_IMAGE[source:source + GLYPH_BYTES]), (
            f"the glyph at {source:#x} is all zero, so a case plotting it holds nothing")


# --- seeding --------------------------------------------------------------------------------------
# The whole buffer plus a margin at each end, address-keyed. The leading margin is
# WB_TEXT_STATE_BYTES, the band between the plotter's last instruction and the buffer — it stops
# there because the bytes below them are the code the oracle is about to run. The trailing one is a
# buffer line past the end, which lands on panel_restore_dirty_regions' first instructions; nothing
# in this battery executes them, and an over-run has to be visible somewhere.
SEED_LO = BUFFER - STATE_BYTES
SEED_HI = BUFFER + BUFFER_LEN + BUFFER_LINE


def _pokes(salt):
    return {SEED_LO: bytes(keyed_byte(SEED_LO + i, salt) for i in range(SEED_HI - SEED_LO))}


def _model_plot(image, glyph, cursor):
    """The 32 bytes the plot moves, as {address: byte}, and the cursor it returns."""
    written = {}
    for row in range(GLYPH_ROWS):
        for plane in range(PLANES):
            at = (cursor + row * BUFFER_LINE + plane * PLANE_STRIDE) & LONGWORD_MASK
            written[at] = image[glyph + row * PLANES + plane]
    ended = (cursor + GLYPH_SPAN) & LONGWORD_MASK
    advance = ADVANCE_ODD if ended & 1 else ADVANCE_EVEN
    return written, (cursor + advance) & LONGWORD_MASK


# --- glue -------------------------------------------------------------------------------------------
_PLOT_GLYPH = leaf.register_glue("text_plot_glyph", [ctypes.c_uint32] * 2, ctypes.c_uint32)
_PLOT_CHAR = leaf.register_glue("text_plot_char", [ctypes.c_uint32] * 2, ctypes.c_uint32)


def _run_plot(name, glue, glyph, cursor, what, salt, entry_regs=None):
    """One plot under both arms: seed the buffer, run, and require exactly the 32 bytes and the
    returned cursor the model gives.

    ``entry_regs`` is what the routine is ENTERED with besides the destination cursor and the seed:
    a0 for the plotter, which is HANDED the glyph pointer, and d0 for the prelude, which computes
    it. That is the only difference between the two entry points as a case sees them — both end
    with a0 one glyph past ``glyph``, which is what says the prelude indexed the source the case
    names.
    """
    pokes = _pokes(salt)
    image = harness.make_image(pokes)
    expected, next_cursor = _model_plot(image, glyph, cursor)

    regs = dict(entry_regs if entry_regs is not None else {"a0": glyph},
                a1=cursor, _pokes=pokes)
    info = leaf.run(name, glue, merge_bands(expected), what, regs=regs, max_insns=PLOT_INSN_CAP)

    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {len(written)} bytes at "
        f"{sorted(hex(a) for a in written)[:6]}..., against the model's {len(expected)}")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {addr:#x} is {written[addr]:#04x}, not the model's {expected[addr]:#04x}")

    assert info["regs"]["a1"] == next_cursor, (
        f"{what}: the original returned a1={info['regs']['a1']:#x}, not the {next_cursor:#x} the "
        f"cell geometry gives")
    assert info["ret"] == info["regs"]["a1"], (
        f"{what}: the reconstruction returned {info['ret']:#x} against the original's "
        f"{info['regs']['a1']:#x}")
    assert info["regs"]["a0"] == glyph + GLYPH_BYTES, (
        f"{what}: the source cursor ended at {info['regs']['a0']:#x}, i.e. it read the glyph at "
        f"{info['regs']['a0'] - GLYPH_BYTES:#x} and not the {glyph:#x} the case names")
    return info


# --- $bf5e: the plotter -----------------------------------------------------------------------------
# Sources: the two ends of the frame-glyph run and three of the font's own, including the blank.
_NONBLANK_SOURCES = (FRAME_GLYPHS,
                     FRAME_GLYPHS + (FRAME_GLYPH_COUNT - 1) * GLYPH_BYTES,
                     GLYPH_TABLE + (ord("0") - FIRST_GLYPH_CHAR) * GLYPH_BYTES,
                     GLYPH_TABLE + (ord("A") - FIRST_GLYPH_CHAR) * GLYPH_BYTES)
GLYPH_SOURCES = _NONBLANK_SOURCES + (GLYPH_TABLE,)   # ...and the space, which writes 32 zeros

# Cursors: the buffer's own first cell (even) and its odd twin, a cell inside a later row, the odd
# cell of the LAST full text row a message can occupy, and an odd cursor deep in the buffer. Every
# one leaves eight rows of 88 inside the seeded band.
CURSORS = [
    ("first-cell", BUFFER),
    ("first-cell-odd", BUFFER + ADVANCE_EVEN),
    ("mid-row", BUFFER + 3 * BUFFER_LINE + 5 * PLANES * PLANE_STRIDE),
    ("mid-row-odd", BUFFER + 3 * BUFFER_LINE + 5 * PLANES * PLANE_STRIDE + ADVANCE_EVEN),
    ("last-row", BUFFER + BUFFER_LEN - GLYPH_ROWS * BUFFER_LINE),
    ("last-row-odd", BUFFER + BUFFER_LEN - GLYPH_ROWS * BUFFER_LINE + ADVANCE_EVEN),
]


@pytest.mark.parametrize("cursor_case,cursor", CURSORS, ids=[c[0] for c in CURSORS])
@pytest.mark.parametrize("glyph", GLYPH_SOURCES, ids=lambda v: f"glyph{v:#x}")
def test_the_plotter_moves_one_glyph_into_the_buffers_four_planes(glyph, cursor_case, cursor):
    what = f"text_plot_glyph glyph={glyph:#x} cursor={cursor:#x} ({cursor_case})"
    _run_plot("text_plot_glyph", _PLOT_GLYPH(glyph, cursor), glyph, cursor, what,
              case_salt(f"{glyph}-{cursor_case}"))


def test_the_returned_cursor_alternates_one_and_seven():
    """Two 8-pixel cells share each 8-byte plane group, so plotting a whole group's worth of cells
    from an even start walks +1 then +7 and lands on the NEXT group — which is the property the two
    `lea` displacements exist for, stated over a run of cells rather than one at a time."""
    cursor = BUFFER + 2 * BUFFER_LINE
    for step in range(4):
        info = _run_plot("text_plot_glyph", _PLOT_GLYPH(GLYPH_TABLE, cursor), GLYPH_TABLE, cursor,
                         f"text_plot_glyph cell walk step {step}", case_salt(f"walk{step}"))
        expected = cursor + (ADVANCE_EVEN if step % 2 == 0 else ADVANCE_ODD)
        assert info["ret"] == expected, f"cell walk step {step}"
        cursor = info["ret"]
    assert cursor == BUFFER + 2 * BUFFER_LINE + 2 * PLANES * PLANE_STRIDE, (
        f"four cells walked to {cursor:#x}, which is not two 8-byte plane groups on")


# --- $bf4e: the character prelude ------------------------------------------------------------------
# The codes: the space the table starts at, two ordinary glyphs, the largest byte, one BELOW the
# first char (where the byte subtraction wraps), and two that carry rubbish in d0's high half — one
# harmless, and one whose shifted low word is NEGATIVE and so indexes below the font.
CHAR_CASES = [
    ("space", FIRST_GLYPH_CHAR),
    ("digit-zero", ord("0")),
    ("letter-a", ord("A")),
    ("largest-byte", 0xff),
    ("below-the-first-char", 0x00),
    ("high-half-rubbish", 0x00010041),
    ("index-sign-extends", 0x00000420),
]


def _char_glyph(code):
    """The pointer the prelude's three instructions give, as arithmetic rather than as a lookup."""
    index = (code & ~BYTE_MASK) | ((code - FIRST_GLYPH_CHAR) & BYTE_MASK)
    indexed = (index << GLYPH_SHIFT) & 0xffff
    signed = indexed - 0x10000 if indexed & 0x8000 else indexed
    return (GLYPH_TABLE + signed) & LONGWORD_MASK


@pytest.mark.parametrize("cursor_case,cursor", CURSORS[:2], ids=[c[0] for c in CURSORS[:2]])
@pytest.mark.parametrize("case,code", CHAR_CASES, ids=[c[0] for c in CHAR_CASES])
def test_the_prelude_indexes_the_font_the_way_the_three_instructions_do(case, code, cursor_case,
                                                                       cursor):
    glyph = _char_glyph(code)
    assert 0 <= glyph < loader.PROGRAM_END - GLYPH_BYTES, (
        f"case {case} names a glyph at {glyph:#x}, outside the program — the divergence class this "
        f"battery does not enter")

    what = f"text_plot_char code={code:#x} ({case}) cursor={cursor:#x}"
    _run_plot("text_plot_char", _PLOT_CHAR(code, cursor), glyph, cursor, what,
              case_salt(f"{case}-{cursor_case}"), entry_regs={"d0": code})


def test_the_sign_extending_case_really_indexes_below_the_font():
    """The `index-sign-extends` case above is only worth having if it reaches the arm it names, so
    the arithmetic is stated here rather than left implicit in a case id."""
    below = _char_glyph(0x00000420)
    assert below < GLYPH_TABLE, (
        f"{below:#x} is not below the font at {GLYPH_TABLE:#x}, so nothing in this battery reaches "
        f"the sign extension")
    assert _char_glyph(0x00010041) > GLYPH_TABLE, (
        "the high-half case no longer indexes forwards, so the pair no longer separates the byte "
        "subtraction from the word index")


# --- $bd8a: what the message table is -------------------------------------------------------------

def test_the_message_table_is_bounded_by_its_own_data():
    """Nothing in the image declares WB_TEXT_MESSAGE_COUNT — a whole-image scan finds exactly one
    reference to $a09c, the driver's own `lea`, and no length anywhere. So the count is read off
    three properties of the shipped bytes: the first pointer names the byte immediately PAST the
    pointer block, every record ends exactly where the next begins, and the last one ends where the
    next named routine starts. A count one too small would leave a gap before that routine; one too
    large would read a "pointer" out of a record's text.
    """
    pointer_bytes = MESSAGE_COUNT << MESSAGE_PTR_SHIFT
    assert MESSAGES[0].pointer == MESSAGE_TABLE + pointer_bytes, (
        f"the first record is at {MESSAGES[0].pointer:#x}, not at the "
        f"{MESSAGE_TABLE + pointer_bytes:#x} that {MESSAGE_COUNT} pointers run up to")
    for earlier, later in zip(MESSAGES, MESSAGES[1:]):
        assert earlier.pointer + earlier.length == later.pointer, (
            f"message {earlier.index} ends at {earlier.pointer + earlier.length:#x}, not at "
            f"message {later.index}'s {later.pointer:#x} — the records are not contiguous")
    last = MESSAGES[-1]
    assert last.pointer + last.length == leaf.entry_of("panel_refresh_frame"), (
        f"the last record ends at {last.pointer + last.length:#x}, not at panel_refresh_frame's "
        f"{leaf.entry_of('panel_refresh_frame'):#x} that bounds the block")


def test_every_shipped_record_asks_for_a_box_the_composer_can_draw():
    """Two invariants the reconstruction leans on, asserted over all WB_TEXT_MESSAGE_COUNT records
    rather than assumed from the handful the cases below use.

    The height one is load-bearing: `subq.w #3,d0 / dbf` counts the interior rows in a WORD, so a
    height below WB_TEXT_BOX_MIN_ROWS would draw 65536 of them and walk far past the buffer. The
    shipped table cannot produce that — which is why src/text.c reproduces the wrap by construction
    and no case reaches it.
    """
    for message in MESSAGES:
        assert message.rows >= BOX_MIN_ROWS, (
            f"message {message.index} asks for {message.rows} rows, below the "
            f"{BOX_MIN_ROWS} the interior `dbf` needs — its count would wrap")
        lines = message.string.split(bytes([NEWLINE]))
        assert len(lines) <= message.rows - 2, (
            f"message {message.index} has {len(lines)} lines in a {message.rows}-row box, whose "
            f"interior is only {message.rows - 2}")
        top = message.top_line * SCREEN_LINE + BLIT_X_BYTES
        span = ((message.rows << BLIT_ROW_SHIFT) - 1) * SCREEN_LINE + BUFFER_LINE
        assert top + span <= SCREEN_LEN, (
            f"message {message.index} blits to {top + span:#x}, past the {SCREEN_LEN:#x} bytes a "
            f"screen buffer's {SCREEN_SCANLINES} scanlines hold")


def test_exactly_one_shipped_message_overruns_the_frames_right_edge():
    """Nothing clamps a text line to the box's WB_TEXT_BOX_EDGE_CELLS interior, and the shipped data
    proves it rather than the code merely permitting it: one message has a line one cell too long
    and really does plot over the frame's right edge. Stated as a case because it is the only reason
    to believe the missing clamp is reachable — and because the overrun stops at exactly one cell,
    which is what keeps every plot inside the buffer's own row.
    """
    widths = {message.index: max(len(line) for line in message.string.split(bytes([NEWLINE])))
              for message in MESSAGES}
    over = sorted(index for index, width in widths.items() if width > BOX_EDGE_CELLS)
    assert over == [112], (
        f"messages {over} exceed the {BOX_EDGE_CELLS}-cell interior, not the one this states")
    assert max(widths.values()) == BOX_EDGE_CELLS + 1, (
        f"the widest line is {max(widths.values())} cells; at more than {BOX_CELLS - 1} a glyph "
        f"would start past the buffer's own row and this claim would no longer hold")


def test_the_boxs_geometry_constants_are_one_set_of_numbers():
    """Every constant the composer steps by is the SAME geometry seen from a different side, so each
    is asserted against the others rather than transcribed. A wrong one then fails here as well as
    in the entry pin."""
    assert BOX_CELLS * CELL_GROUP // 2 == BUFFER_LINE, (
        f"{BOX_CELLS} cells span {BOX_CELLS * CELL_GROUP // 2} bytes, not the buffer's "
        f"{BUFFER_LINE} — the box is not exactly as wide as the buffer")
    assert BOX_EDGE_CELLS == BOX_CELLS - 2, "the edge run is not the width less its two corners"
    assert CELL_GROUP == PLANES * PLANE_STRIDE
    assert CELL_ROW_BYTES == GLYPH_ROWS * BUFFER_LINE, (
        "a cell row is not WB_TEXT_GLYPH_ROWS buffer lines, so `mulu.w #$2c0` is not a text line")
    assert ROW_ADVANCE == CELL_ROW_BYTES - BUFFER_LINE, (
        "the row advance is not 'the rest of the cell row' from the cursor the last glyph left")
    assert INTERIOR_SKIP == BOX_EDGE_CELLS * CELL_GROUP // 2, (
        "the interior skip does not carry the cursor across the box's interior")
    assert TEXT_ORIGIN == BUFFER + ADVANCE_EVEN, "the text does not start at the buffer's cell 1"
    assert BLIT_LONGWORDS * LONGWORD_LEN == BUFFER_LINE, (
        "the unrolled blit row is not one buffer line")
    assert BLIT_SKIP == SCREEN_LINE - BUFFER_LINE, (
        "the blit's skip and its copy do not make up a screen scanline")
    assert 1 << BLIT_ROW_SHIFT == GLYPH_ROWS, "a cell row is not WB_TEXT_GLYPH_ROWS scanlines"


# --- $bd8a: the ten state bytes -------------------------------------------------------------------
# Seven fields, addressed by name so a case says which phase it is seeding rather than laying out a
# blob. Each is (address, length); `_state_pokes` defaults an unnamed one to zero.
STATE_FIELDS = {
    "request": (REQUEST, 1),
    "active": (BOX_ACTIVE, 1),
    "rows": (BOX_ROWS, 1),
    "top_line": (BOX_TOP_LINE, 1),
    "lifetime": (LIFETIME_REQUEST, WORD_LEN),
    "armed": (LIFETIME_ARMED, WORD_LEN),
    "left": (LIFETIME_LEFT, WORD_LEN),
}


def test_the_seven_state_fields_tile_the_band_exactly():
    """WB_TEXT_STATE_BYTES was pinned by its EXTENT alone until this batch. The seven fields are now
    named, so the extent and the fields are checked against each other: they must start at the band's
    first byte, leave no gap and overlap nowhere, and end at WB_TEXT_BUFFER."""
    spans = sorted(STATE_FIELDS.values())
    assert spans[0][0] == BUFFER - STATE_BYTES, (
        f"the first field is at {spans[0][0]:#x}, not at the band's own start "
        f"{BUFFER - STATE_BYTES:#x}")
    for (addr, length), (next_addr, _) in zip(spans, spans[1:]):
        assert addr + length == next_addr, (
            f"{addr:#x}+{length} does not meet the next field at {next_addr:#x} — the seven fields "
            f"do not tile the band")
    assert spans[-1][0] + spans[-1][1] == BUFFER, (
        "the last field does not end where WB_TEXT_BUFFER begins")
    assert sum(length for _addr, length in spans) == STATE_BYTES


def _state_pokes(**values):
    """The state band as a case's INPUT, one named field at a time. An unnamed field is zero."""
    pokes = {}
    for name, (addr, length) in STATE_FIELDS.items():
        pokes[addr] = values.pop(name, 0).to_bytes(length, "big")
    assert not values, f"{sorted(values)} are not WB_TEXT_STATE_BYTES fields"
    return pokes


def _state_writes(**values):
    """The state fields a model expects the arm to WRITE, as {address: byte}.

    Unlike `_state_pokes`, an unnamed field is one the arm must leave ALONE rather than one seeded
    to zero — the write set is stated exactly, so a field listed here that the original never wrote
    fails just as loudly as one it wrote and this omits.
    """
    writes = {}
    for name, value in values.items():
        assert name in STATE_FIELDS, f"{name!r} is not a WB_TEXT_STATE_BYTES field"
        addr, length = STATE_FIELDS[name]
        writes.update({addr + offset: byte
                       for offset, byte in enumerate(value.to_bytes(length, "big"))})
    return writes


# --- seeding the driver's cases -------------------------------------------------------------------
# The buffer plus a line past its end, address-keyed. It is the compose arm's destination (so the
# clear has to be visible) and the blit arm's source (so a wrong stride reads bytes that are wrong
# for where they came from). The state band is NOT part of it: each case pokes those ten bytes by
# field, which also means a stray write into them is caught rather than seeded over.
BOX_SEED_LO = BUFFER
BOX_SEED_HI = BUFFER + BUFFER_LEN + BUFFER_LINE


def _buffer_pokes(salt):
    return {BOX_SEED_LO: keyed_block(BOX_SEED_LO, BOX_SEED_HI - BOX_SEED_LO, salt)}


def _run_driver(pokes, expected, what, max_insns):
    """One driver run under both arms, with the write set stated EXACTLY.

    `poison=False`, and the module docstring says why: every arm writes WB_TEXT_REQUEST, so a
    poisoned image turns a zero request into WB_TEXT_REQUEST_DISMISS and both cores would take the
    dismiss arm. What replaces it is stronger here anyway — an address-keyed destination, the
    oracle's write set required to be exactly `expected`, and every byte of it compared against a
    model built out of the game's own data.
    """
    glue = leaf.image_glue("text_run_message_box")
    info = leaf.run("text_run_message_box", glue, merge_bands(expected), what,
                    regs={"_pokes": pokes}, poison=False, max_insns=max_insns)

    written = program_writes(info)
    assert set(written) == set(expected), (
        f"{what}: the original wrote {len(written)} bytes, the model {len(expected)}; "
        f"{sorted(hex(a) for a in set(written) ^ set(expected))[:8]}... differ")
    for addr in sorted(expected):
        assert written[addr] == expected[addr], (
            f"{what}: {harness.label(addr)} @ {addr:#x} is {written[addr]:#04x}, not the model's "
            f"{expected[addr]:#04x}")
    assert info["ret"] is None, f"{what}: the reconstruction is void and returned {info['ret']}"
    return info


# --- $bd8a: the arms that draw nothing ------------------------------------------------------------

def test_an_idle_frame_writes_no_byte_at_all():
    """Both flags clear: `tst.b / bne` twice and an `rts`. The write set is EMPTY, which is the one
    thing this arm can be wrong about — a driver that cleared a flag "for safety" would show here."""
    pokes = dict(_buffer_pokes(case_salt("idle")))
    pokes.update(_state_pokes(rows=MESSAGES[0].rows, top_line=MESSAGES[0].top_line,
                              armed=LIFETIME_ARMED_SET, left=5))
    _run_driver(pokes, {}, "text_run_message_box with both flags clear", PLOT_INSN_CAP)


@pytest.mark.parametrize("case,active", [("dismiss-a-box-that-is-up", BOX_ACTIVE_SET),
                                         ("dismiss-with-no-box-up", 0)],
                         ids=lambda v: v if isinstance(v, str) else f"active{v:#04x}")
def test_the_dismiss_request_clears_both_flags_and_draws_nothing(case, active):
    """WB_TEXT_REQUEST_DISMISS is checked before the table is indexed, so it composes nothing — and
    it is the only value of the request byte that does not name a message."""
    pokes = dict(_buffer_pokes(case_salt(case)))
    pokes.update(_state_pokes(request=REQUEST_DISMISS, active=active,
                              lifetime=50, armed=LIFETIME_ARMED_SET, left=5))
    expected = _state_writes(request=0, active=0)
    # The two `clr.b` are the whole arm: the lifetime fields it walks past are left standing.
    _run_driver(pokes, expected, f"text_run_message_box {case}", PLOT_INSN_CAP)


# --- $bd8a: the compose arm -----------------------------------------------------------------------

def _model_compose_buffer(image, message):
    """The WB_TEXT_BUFFER_LEN bytes the compose arm leaves behind, as the composer's own geometry
    gives them: a cleared buffer, then the frame, then the string.

    Built out of `_model_plot` — the primitive the plotter's own cases already pin — rather than
    restated, so this states the LAYOUT and borrows the plotting. Every glyph is required to land
    inside the buffer, which is what makes a wrong row advance or a wrong skip fail here instead of
    quietly writing over the state band or past the buffer's end.
    """
    buffer = bytearray(BUFFER_LEN)

    def plot(glyph, cursor):
        written, next_cursor = _model_plot(image, glyph, cursor)
        for addr, value in written.items():
            assert BUFFER <= addr < BUFFER + BUFFER_LEN, (
                f"message {message.index}: a glyph at cursor {cursor:#x} writes {addr:#x}, outside "
                f"the buffer")
            buffer[addr - BUFFER] = value
        return next_cursor

    def horizontal_row(cursor, left_corner):
        cursor = plot(frame_glyph(left_corner), cursor)
        for _cell in range(BOX_EDGE_CELLS):
            cursor = plot(frame_glyph(left_corner + 1), cursor)
        return plot(frame_glyph(left_corner + 2), cursor)

    cursor = horizontal_row(BUFFER, TOP_LEFT) + ROW_ADVANCE
    for _row in range(message.rows - 2):
        cursor = plot(frame_glyph(LEFT_EDGE), cursor) + INTERIOR_SKIP
        cursor = plot(frame_glyph(RIGHT_EDGE), cursor) + ROW_ADVANCE
    horizontal_row(cursor, BOTTOM_LEFT)

    line = FIRST_TEXT_LINE
    cursor = TEXT_ORIGIN + line * CELL_ROW_BYTES
    for code in message.string:
        if code == NEWLINE:
            line += 1
            cursor = TEXT_ORIGIN + line * CELL_ROW_BYTES
            continue
        cursor = plot(_char_glyph(code), cursor)
    return buffer


def _model_compose(image, message, lifetime):
    """Everything the compose arm writes: the whole buffer and the state fields it latches."""
    expected = {BUFFER + offset: byte
                for offset, byte in enumerate(_model_compose_buffer(image, message))}
    expected.update(_state_writes(request=0, active=BOX_ACTIVE_SET,
                                  rows=message.rows, top_line=message.top_line))
    if lifetime != 0:
        expected.update(_state_writes(left=lifetime, lifetime=0, armed=LIFETIME_ARMED_SET))
    return expected


# One message per property the composer can be wrong about: the minimum height, the other top line,
# the maximum height and line count, the shortest string, the line that overruns the frame, and the
# table's last entry (whose record ends where the block does). Read off MESSAGES, so a case names
# the property it is here for and the index is checked against it.
COMPOSE_MESSAGES = [
    ("min-height-one-line", 0),
    ("top-line-fifty", 3),
    ("max-height-seven-lines", 5),
    ("shortest-string", 73),
    ("overruns-the-right-edge", 112),
    ("last-in-the-table", MESSAGE_COUNT - 1),
]

# The two sides of the `tst.w $c034` that opens the arm, crossed with the latch either way.
# `already-armed` is not a record's doing — no record encodes a lifetime — but it is the state the
# game is in from the first timed message onwards, since nothing ever clears the latch.
COMPOSE_LIFETIMES = [
    ("no-lifetime", 0, 0),
    ("no-lifetime-already-armed", 0, LIFETIME_ARMED_SET),
    ("posts-a-lifetime", 50, 0),
    ("posts-a-lifetime-already-armed", 50, LIFETIME_ARMED_SET),
]


def test_the_compose_cases_are_the_messages_they_say_they_are():
    """Each case above is here for a property of its record, not for its index. Asserted so that a
    reshuffled table fails by name instead of quietly testing six ordinary messages."""
    by_case = {case: MESSAGES[index] for case, index in COMPOSE_MESSAGES}
    assert by_case["min-height-one-line"].rows == BOX_MIN_ROWS
    assert NEWLINE not in by_case["min-height-one-line"].string
    assert by_case["top-line-fifty"].top_line != by_case["min-height-one-line"].top_line, (
        "the two top-line cases ask for the same scanline, so neither pins the multiply")
    assert by_case["max-height-seven-lines"].rows == MAX_BOX_ROWS
    assert by_case["max-height-seven-lines"].string.count(bytes([NEWLINE])) == MAX_BOX_ROWS - 3
    assert len(by_case["shortest-string"].string) == min(len(m.string) for m in MESSAGES)
    assert max(len(line) for line
               in by_case["overruns-the-right-edge"].string.split(bytes([NEWLINE]))) > BOX_EDGE_CELLS
    assert by_case["last-in-the-table"].index == MESSAGE_COUNT - 1


@pytest.mark.parametrize("lifetime_case,lifetime,armed", COMPOSE_LIFETIMES,
                         ids=[c[0] for c in COMPOSE_LIFETIMES])
@pytest.mark.parametrize("case,index", COMPOSE_MESSAGES, ids=[c[0] for c in COMPOSE_MESSAGES])
def test_a_requested_message_is_composed_into_the_buffer(case, index, lifetime_case, lifetime,
                                                         armed):
    """The compose arm end to end: the buffer is cleared, a WB_TEXT_BOX_CELLS-wide frame of the
    record's height is drawn into it and the record's string plotted a line at a time — and the
    frame is NOT blitted, which is why every case's write set stops at the buffer."""
    message = MESSAGES[index]
    salt = case_salt(f"{case}-{lifetime_case}")
    pokes = dict(_buffer_pokes(salt))
    # `left` and the box geometry are seeded to values the arm must overwrite: `left` only when a
    # lifetime is posted, the two geometry bytes always, from the record.
    pokes.update(_state_pokes(request=message_id(index), lifetime=lifetime, armed=armed,
                              left=keyed_byte(LIFETIME_LEFT, salt), rows=1, top_line=1))
    image = harness.make_image(pokes)
    expected = _model_compose(image, message, lifetime)

    what = f"text_run_message_box composing message {index} ({case}, {lifetime_case})"
    info = _run_driver(pokes, expected, what, COMPOSE_INSN_CAP)

    # The arm returns at the string's terminator, so the oracle's d0 is that byte and its a0 one
    # glyph past the last character plotted — documented rather than pinned (the C returns neither).
    assert info["regs"]["d0"] == STRING_END, (
        f"{what}: the arm left d0={info['regs']['d0']:#x}, not the terminator it stopped on")
    last = message.string.replace(bytes([NEWLINE]), b"")[-1]
    assert info["regs"]["a0"] == _char_glyph(last) + GLYPH_BYTES, (
        f"{what}: the arm left a0={info['regs']['a0']:#x}, not one glyph past the last character")


def test_a_request_is_served_even_while_a_box_is_already_up():
    """The two flag tests are in order, not exclusive: WB_TEXT_REQUEST is tested first, so a message
    posted while a box is up recomposes over it instead of waiting for the countdown. That ordering
    is the only thing separating the two arms, so it gets a case of its own."""
    message = MESSAGES[0]
    salt = case_salt("request-beats-an-active-box")
    pokes = dict(_buffer_pokes(salt))
    pokes.update(_state_pokes(request=message_id(0), active=BOX_ACTIVE_SET,
                              rows=MESSAGES[5].rows, top_line=MESSAGES[5].top_line,
                              armed=LIFETIME_ARMED_SET, left=5))
    image = harness.make_image(pokes)
    expected = _model_compose(image, message, lifetime=0)

    _run_driver(pokes, expected, "text_run_message_box with a request AND a box already up",
                COMPOSE_INSN_CAP)


# --- $bd8a: the blit arm --------------------------------------------------------------------------
# The screen band the blit lands in, plus a scanline of margin either side, address-keyed: a blit
# that took the wrong skip or ran a row long writes bytes that are wrong for where they were written.
SCREEN = SCREEN_BUFFERS[0]
SCREEN_BYTES = SCREEN_BUFFERS[1] - SCREEN_BUFFERS[0]


def _blit_pokes(salt, rows, top_line, **state):
    pokes = dict(_buffer_pokes(salt))
    pokes[SCREEN] = keyed_block(SCREEN, SCREEN_BYTES, salt + 1)
    pokes[SCREEN_BACK] = longword(SCREEN)
    pokes.update(_state_pokes(active=BOX_ACTIVE_SET, rows=rows, top_line=top_line, **state))
    return pokes


def _model_blit(image, rows, top_line, armed, left):
    """Everything the blit arm writes: the countdown it ticks and the rectangle it moves."""
    expected = _state_writes(request=0)
    if armed != 0:
        remaining = (left - 1) & WORD_MASK
        expected.update(_state_writes(left=remaining))
        if remaining == 0:
            expected.update(_state_writes(active=0))

    source = BUFFER
    dest = (SCREEN + _sign_extended_word(top_line * SCREEN_LINE) + BLIT_X_BYTES) & LONGWORD_MASK
    for _scanline in range(rows << BLIT_ROW_SHIFT):
        for byte in range(BUFFER_LINE):
            expected[(dest + byte) & LONGWORD_MASK] = image[source + byte]
        source += BUFFER_LINE
        dest = (dest + SCREEN_LINE) & LONGWORD_MASK
    return expected


def _sign_extended_word(value):
    """`lea d8(An,Dn.w),An` indexes with the low WORD of Dn, sign-extended."""
    low = value & WORD_MASK
    return low - 0x10000 if low & 0x8000 else low


# The four phases of the countdown, and the two geometries. `armed` clear is the only one that skips
# the tick; `left` of 1 is the one that lands on zero and takes the box down; `left` of 0 is where
# the `subq.w` wraps past zero and the box stays up forever. That last is a state the game reaches
# rather than a branch nothing takes: WB_TEXT_LIFETIME_ARMED is a latch nothing in the image clears,
# so a box composed with no lifetime of its own ticks down from whatever the last one left.
BLIT_COUNTDOWNS = [
    ("not-armed", 0, 7),
    ("armed-and-ticking", LIFETIME_ARMED_SET, 7),
    ("armed-and-expiring", LIFETIME_ARMED_SET, 1),
    ("armed-and-wrapping-past-zero", LIFETIME_ARMED_SET, 0),
]
BLIT_GEOMETRIES = [
    ("min-box-low-on-screen", BOX_MIN_ROWS, 60),
    ("max-box-higher-up", MAX_BOX_ROWS, 50),
]


def test_the_blit_geometries_are_the_ones_the_table_asks_for():
    """The two geometries above are not invented: they are the extremes of the shipped records, so
    the cases cover the whole range the game can actually blit."""
    heights = {message.rows for message in MESSAGES}
    top_lines = {message.top_line for message in MESSAGES}
    assert {rows for _case, rows, _top in BLIT_GEOMETRIES} == {min(heights), max(heights)}
    assert {top for _case, _rows, top in BLIT_GEOMETRIES} == top_lines, (
        f"the cases blit at {sorted(t for _c, _r, t in BLIT_GEOMETRIES)}, not at the "
        f"{sorted(top_lines)} the table asks for")


@pytest.mark.parametrize("geometry_case,rows,top_line", BLIT_GEOMETRIES,
                         ids=[c[0] for c in BLIT_GEOMETRIES])
@pytest.mark.parametrize("countdown_case,armed,left", BLIT_COUNTDOWNS,
                         ids=[c[0] for c in BLIT_COUNTDOWNS])
def test_an_active_box_is_ticked_and_blitted_to_the_back_screen(countdown_case, armed, left,
                                                                geometry_case, rows, top_line):
    """The blit arm end to end: the already-composed buffer goes out to WB_SCREEN_BACK at the
    geometry the compose frame latched, WB_TEXT_BUFFER_LINE at a time with a WB_TEXT_BLIT_SKIP
    between scanlines — and the countdown is ticked FIRST, so the frame the box expires on is still
    drawn."""
    case = f"{countdown_case}-{geometry_case}"
    pokes = _blit_pokes(case_salt(case), rows, top_line, armed=armed, left=left)
    image = harness.make_image(pokes)
    expected = _model_blit(image, rows, top_line, armed, left)

    what = f"text_run_message_box blitting a {rows}-row box at line {top_line} ({countdown_case})"
    info = _run_driver(pokes, expected, what, BLIT_INSN_CAP)

    # Both cursors walk out at the end of what they moved; the C returns neither.
    assert info["regs"]["a0"] == BUFFER + (rows << BLIT_ROW_SHIFT) * BUFFER_LINE, (
        f"{what}: the source ended at {info['regs']['a0']:#x}, not at the end of the rows it moved")
    assert info["regs"]["a1"] == (SCREEN + _sign_extended_word(top_line * SCREEN_LINE)
                                  + BLIT_X_BYTES + (rows << BLIT_ROW_SHIFT) * SCREEN_LINE), (
        f"{what}: the destination ended at {info['regs']['a1']:#x}, not one scanline past the last "
        f"row it wrote")


def test_the_blit_draws_into_whichever_buffer_screen_back_names():
    """WB_SCREEN_BACK is a longword IN MEMORY, so the destination comes out of the image and not out
    of a constant. The cases above all use the first buffer; this one moves it to the second and
    requires the whole rectangle to move with it."""
    rows, top_line = BOX_MIN_ROWS, 60
    salt = case_salt("blit-into-the-front-buffer")
    other = SCREEN_BUFFERS[1]
    pokes = dict(_buffer_pokes(salt))
    pokes[other] = keyed_block(other, SCREEN_BYTES, salt + 1)
    pokes[SCREEN_BACK] = longword(other)
    pokes.update(_state_pokes(active=BOX_ACTIVE_SET, rows=rows, top_line=top_line))
    image = harness.make_image(pokes)

    expected = _state_writes(request=0)
    source = BUFFER
    dest = other + top_line * SCREEN_LINE + BLIT_X_BYTES
    for _scanline in range(rows << BLIT_ROW_SHIFT):
        for byte in range(BUFFER_LINE):
            expected[dest + byte] = image[source + byte]
        source += BUFFER_LINE
        dest += SCREEN_LINE

    _run_driver(pokes, expected, "text_run_message_box blitting into the second screen buffer",
                BLIT_INSN_CAP)


# The smallest top line whose scanline offset overflows a signed word. WB_TEXT_BOX_TOP_LINE is a
# plain RAM byte the blit arm reads directly — it is not re-read from the record — so a case can
# seed it, the same way the countdown phases above seed WB_TEXT_LIFETIME_LEFT. That is what makes
# this a reading of the instruction rather than a fabricated table entry.
SIGN_EXTENDING_TOP_LINE = next(top for top in range(1 << 8)
                               if (top * SCREEN_LINE) & WORD_MASK >= 0x8000)


def test_the_blits_scanline_offset_is_a_sign_extended_word():
    """`mulu.w #$a0,d0` is a 32-bit product but `lea 48(a1,d0.w),a1` takes only its low word, SIGN-
    EXTENDED — so a top line at or above SIGN_EXTENDING_TOP_LINE places the box BELOW WB_SCREEN_BACK
    rather than far past it. The shipped records only ask for two top lines and neither reaches this
    (`test_every_shipped_record_asks_for_a_box_the_composer_can_draw` bounds them), so the game
    cannot produce it; without a case, reading the index as a plain 32-bit offset survives."""
    assert all(message.top_line < SIGN_EXTENDING_TOP_LINE for message in MESSAGES), (
        "a shipped record already reaches the sign extension, so this case is not the only way in")

    rows, top_line = BOX_MIN_ROWS, SIGN_EXTENDING_TOP_LINE
    salt = case_salt("blit-below-the-screen-base")
    offset = _sign_extended_word(top_line * SCREEN_LINE)
    assert offset < 0, "the case's top line does not overflow the word after all"

    dest = SCREEN + offset + BLIT_X_BYTES
    span = (rows << BLIT_ROW_SHIFT) * SCREEN_LINE
    assert loader.PROGRAM_END < dest and dest + span < SCREEN, (
        f"the box would land at {dest:#x}, not in the free band between the program and the "
        f"screen buffers — the case would be seeding over something that matters")

    pokes = dict(_buffer_pokes(salt))
    pokes[dest - SCREEN_LINE] = keyed_block(dest - SCREEN_LINE, span + 2 * SCREEN_LINE, salt + 1)
    pokes[SCREEN_BACK] = longword(SCREEN)
    pokes.update(_state_pokes(active=BOX_ACTIVE_SET, rows=rows, top_line=top_line))
    image = harness.make_image(pokes)

    expected = _model_blit(image, rows, top_line, armed=0, left=0)
    _run_driver(pokes, expected, f"text_run_message_box blitting at top line {top_line}",
                BLIT_INSN_CAP)


# --- the two equivalences the mutation sweep found, stated rather than left implicit --------------

def test_the_newline_and_the_terminator_cannot_be_the_same_byte():
    """The string loop tests WB_TEXT_NEWLINE first and WB_TEXT_STRING_END second, and src/text.c
    keeps that order — but swapping them is an EQUIVALENCE for every input rather than a hole in the
    sweep, because no byte can satisfy both. It stops being one the moment the two constants meet.
    """
    assert NEWLINE != STRING_END, (
        "the newline and the terminator are the same byte, so which test comes first now decides "
        "what a string does and src/text.c's order has become load-bearing")


def test_the_blit_arms_request_clear_is_a_write_of_a_byte_already_zero():
    """`clr.b $c030.l` opens the blit arm, which is reached only when WB_TEXT_REQUEST is ALREADY
    zero — the arm above it takes every nonzero value. So the write changes no byte, and dropping it
    from the reconstruction survives the sweep.

    src/text.c keeps it anyway, because it is a write the ORIGINAL makes: the cases' write set is
    stated exactly, so the oracle making it is pinned even though the candidate omitting it would
    not be. Both entry pins say the same thing about the bytes, and this states the reason the two
    sides of that write differ in what can be checked.
    """
    entry = ENTRY_BYTES["text_run_message_box"]
    blit_arm = entry.index(clr_b_abs_l(REQUEST) + tst_w_abs_l(LIFETIME_ARMED))
    assert entry[:len(tst_b_abs_l(REQUEST))] == tst_b_abs_l(REQUEST), (
        "the routine no longer opens by testing WB_TEXT_REQUEST, so the arm below it is no longer "
        "reached with that byte known to be zero")
    assert blit_arm > 0, "the blit arm's own `clr.b` is not in the pin"
