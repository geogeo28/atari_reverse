"""Differential test for src/text.c — the glyph plotter at $bf4e..$c030, both entry points.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, states the write set EXACTLY (32 bytes, at the addresses
the 4-plane geometry gives) and compares the returned cursor against BOTH the oracle's a1 and the
reconstruction's return value.

WHAT MAKES THIS BATTERY DIFFERENT FROM THE OTHERS HERE.

  * THE TWO ROUTINES ARE ONE ROUTINE. $bf4e has no `rts`: it computes a glyph pointer and falls
    through into $bf5e, whose `rts` returns to ITS caller. That the two are contiguous is asserted
    (`test_the_prelude_falls_through_into_the_plotter`) rather than assumed, because it is the whole
    justification for reconstructing them as a prelude that CALLS the plotter and returns its
    result.
  * THE DESTINATION IS AN 88-BYTE-WIDE BUFFER, NOT THE SCREEN. Every case seeds the whole of
    WB_TEXT_BUFFER address-keyed, so a plot that stepped a 160-byte scanline, or ran a row long,
    lands on bytes that are wrong FOR WHERE THEY WERE WRITTEN. The leading margin is
    WB_TEXT_STATE_BYTES — the ten at $c030..$c039 — and stops there for a reason: the plotter's own
    code ends at $c02f, and poking over the instructions the oracle is about to execute would be a
    different test.
  * THE SOURCE IS THE GAME'S OWN DATA. The font at WB_TEXT_GLYPH_TABLE and the eight frame glyphs
    below it are shipped in the .PRG (unlike the tile bitmaps, which are loaded at runtime), so
    nothing here invents a glyph — which is what keeps a wrong plane order or a wrong source stride
    visible.

KNOWINGLY NOT PINNED
  * d7, WHICH THE PLOTTER CLOBBERS. It parks the ENDED cursor there for the `btst`; the kit's oracle
    reports d0/d1/a0/a1 only, so no case can compare it. No caller reads it either ($bd8a's own d0/
    d6/a6 are what its loops carry).
  * A GLYPH POINTER OUTSIDE THE IMAGE. `text_plot_char` indexes with a SIGN-EXTENDED word, so a
    caller's d0 can name a source far below the font; the case below reaches that arithmetic with a
    source that is still inside the image, and off-image is the divergence class src/rad.c's comment
    registers (the oracle's shim answers zeros, the C indexes a host buffer).
"""
import ctypes

import pytest

import harness
import leaf
from leaf import (RTS, case_salt, forward_branch, keyed_byte, lea_abs_l, lea_d16, merge_bands,
                  opcode, program_writes, word)
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

WORD_LEN = 2
LONGWORD_LEN = 4
BYTE_MASK = 0xff
LONGWORD_MASK = 0xffffffff

# What the plotter's own body walks before the parity tail measures from it, and the two `lea`
# displacements the image carries — spelt as the geometry rather than as -621/-615, so a moved
# WB_TEXT_BUFFER_LINE fails the entry pin instead of quietly agreeing with it.
LAST_PLANE_OFFSET = (PLANES - 1) * PLANE_STRIDE
ROW_STEP = BUFFER_LINE - LAST_PLANE_OFFSET
GLYPH_SPAN = (GLYPH_ROWS - 1) * BUFFER_LINE + LAST_PLANE_OFFSET

# 32 stores, 32 `lea`s and a handful of instructions either side; a cap that stays a cap.
PLOT_INSN_CAP = 96


# --- the opcodes only this battery spells ---------------------------------------------------------
A0, A1 = 0, 1
D0, D7 = 0, 7
BNE_W = 0x6600

MOVE_B_POSTINC_A0_IND_A1 = opcode(0x1298)
MOVE_L_A1_D7 = opcode(0x2e09)


def lea_indexed(reg, index):
    """`lea (0,An,Dn.w),An` — the extension word is the whole of the index encoding."""
    return opcode(0x41f0 | (reg << 9) | reg) + word(index << 12)


def subi_b_dn(reg, value):
    return opcode(0x0400 | reg) + word(value)


def lsl_l_imm_dn(count, reg):
    """`lsl.l #n,Dn` — a LONGWORD shift, which is what lets d0's high bytes reach the index."""
    return opcode(0xe188 | ((count & 7) << 9) | reg)


def btst_imm_dn(bit, reg):
    return opcode(0x0800 | reg) + word(bit)


def _branch(condition, *over):
    return opcode(condition) + forward_branch(sum(len(piece) for piece in over))


# --- the entry pins -------------------------------------------------------------------------------

def _plot_glyph_entry():
    plane_step = lea_d16(A1, PLANE_STRIDE)
    row = MOVE_B_POSTINC_A0_IND_A1 + (plane_step + MOVE_B_POSTINC_A0_IND_A1) * (PLANES - 1)
    body = (row + lea_d16(A1, ROW_STEP)) * (GLYPH_ROWS - 1) + row
    even = lea_d16(A1, -(GLYPH_SPAN - ADVANCE_EVEN)) + RTS
    return (body + MOVE_L_A1_D7 + btst_imm_dn(0, D7) + _branch(BNE_W, even) + even
            + lea_d16(A1, -(GLYPH_SPAN - ADVANCE_ODD)) + RTS)


def _plot_char_entry():
    return (lea_abs_l(A0, GLYPH_TABLE) + subi_b_dn(D0, FIRST_GLYPH_CHAR)
            + lsl_l_imm_dn(GLYPH_SHIFT, D0) + lea_indexed(A0, D0))


ENTRY_BYTES = {
    "text_plot_glyph": _plot_glyph_entry(),
    "text_plot_char": _plot_char_entry(),
}
RECONSTRUCTED_ROUTINES = 2


def test_the_battery_covers_every_routine_it_was_written_for():
    leaf.assert_batch_is_complete(ENTRY_BYTES, RECONSTRUCTED_ROUTINES)


@pytest.mark.parametrize("name", sorted(ENTRY_BYTES), ids=sorted(ENTRY_BYTES))
def test_the_whole_body_is_the_bytes_this_battery_reconstructs(name):
    leaf.assert_entry_is(name, ENTRY_BYTES[name])


@pytest.mark.parametrize("name,size", [
    ("text_plot_glyph", 210),
    ("text_plot_char", 16),
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
