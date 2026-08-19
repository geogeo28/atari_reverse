"""Differential test for src/blit.c — the twelve masked planar sprite blitters at $8fce..$989c.

Every case runs the ORIGINAL under the Musashi oracle and the reconstruction on the same image,
requires the two to agree byte for byte, and then goes further in the two ways this family needs:
the write set is compared for EQUALITY against a Python model of the blit, and so is every register
the routine leaves — because for these twelve the registers are half the output.

THREE THINGS MAKE THIS BATTERY DIFFERENT FROM test_scroll.py's.

  * THE REGISTERS ARE OUTPUT. A blitter walks d0..d5 as a rolling window over the source, and walks
    out with a0 past the sprite, a1 a scanline past the last row and d7 at its own exit value —
    and the clipped four-column body leaves a DIFFERENT d3 depending on which column it skipped
    (the late `or.w d4,d3` at $9324, reproduced rather than tidied). So the reconstruction hands
    its whole register file back through `sprite_blit_regs` and every case asserts all fifteen of
    the oracle's reported registers against the model, plus the eleven the struct carries. As
    test_map.py's cell lookup is: two sides read the same way twice would otherwise agree wrongly.
  * THE TWELVE ARE ASSEMBLED, NOT TRANSCRIBED. All 2254 bytes of them are built here out of the
    same geometry src/blit.c is built out of — the column count, the clip ladder, the `lea` that
    closes a row — and required to equal the shipped image, which is what lets that file be one
    parametrised walk instead of twelve unrolled copies. A width, a threshold, a clip-mask value or
    a rotate that is wrong in the C is wrong in these bytes too. The four ways the original's own
    assembler broke the pattern (a `bra.s` where its neighbours are `bra.w`, a pair of word branches
    where the same test elsewhere is short) are stated as the exceptions they are.
  * NOTHING THE SPRITES ARE MADE OF IS IN THE IMAGE. The bitmaps come off disk (SPRITES.CRU), so
    every case seeds its own sprite at SPRITE_SOURCE, and the screen band under it is seeded once
    (SCREEN_SEED) — both ADDRESS-KEYED with a MARGIN, which is the property that matters: a blit
    that ran a row long, took the wrong stride or read the wrong cell must land on bytes that are
    wrong FOR WHERE THEY WERE WRITTEN rather than on zeros. WB_BLIT_CLIP_MASK is seeded to
    CLIP_MASK_SEED, which draws NOTHING: an unclipped body that read it would blit an empty sprite,
    and a clipped one whose prelude failed to write it would too.

THE PASS AT $8f02 IS THE SECOND HALF OF THIS FILE, added in batch 15 — the twelve above have no
other caller, and the pass has no other callee. It shares this battery rather than starting one
because the two are one story and the seam between them is what a case has to state: `_dest_for`
below is the pass's own screen arithmetic, `model_blit`'s entry registers are what the pass
computes, and the row count a wider body runs away on is a height byte the pass sign-extends. Two
files would each have had half.

KNOWINGLY NOT PINNED
  * WHOSE POINTER `subq.w #6,a5` UNWINDS. Six bytes is one WB_ACTOR_SCREEN_RECORDS record, but the
    sprite pass walks that array in a6 and never touches a5, so the caller this rewinds is still not
    established — reading the pass RULED THE OBVIOUS ANSWER OUT rather than confirming it.
  * A WIDTH CODE OUTSIDE 0..WB_BLIT_WIDTH_CODE_MAX. The original `jsr`s through whatever longword
    sits past the four-entry table; nothing here can stand in for that, so the pass battery refuses
    such a descriptor and src/blit.c's dispatch returns instead.
  * WHAT THE SHIPPED DESCRIPTORS HOLD. SPRITES.CRU and the table at $248d8 both come off disk, so
    every case seeds its own — including the negative height that reaches the runaway `dbf`. That
    the runaway is reachable BY DATA is pinned; that the game's own data reaches it is not.
"""
import ctypes
import random
from typing import NamedTuple

import pytest

import harness
import leaf
from harness import make_image
from layout import wb
from leaf import (RTS, adda_w_dn_an, add_w_dn_dn, addq_w_dn, andi_w_dn, asl_w_imm_dn,
                  asr_w_imm_dn, backward_branch,
                  branch_over, case_salt, clr_w_dn, cmp_w_dn_dn, cmp_w_imm_dn, cmpi_w_dn, ext_w_dn,
                  keyed_block, lea_abs_l, lea_d16,
                  longword, lsl_w_imm_dn, merge_bands, move_b_d16_dn, move_b_imm_abs_l,
                  move_w_dn_dn, move_w_imm_dn, move_w_ind_dn, move_w_postinc_dn, movea_l_abs_w,
                  mulu_w_imm_dn, opcode, program_writes, rotate_left32, rotate_right32, s8,
                  s16, set_low_word, sub_w_dn_dn, swap_dn, tst_w_dn, word)

import emu                                                       # noqa: E402
import loader                                                    # noqa: E402

# --- what one sprite row is made of ---------------------------------------------------------------
# Every number here that include/blit.h states is READ from it through the same scrape the image
# constants come through (test/layout.py), so this battery and the reconstruction cannot disagree
# about the geometry: a constant renamed or changed there fails here as a missing or moved key. The
# COMPOUND ones (a cell's bytes, a column's, a row's `lea`) stay derived in Python — that derivation
# is what cross-checks the header's own.
PLANES = wb("PLANES")
WORD_LEN = wb("STATE_WORD_LEN")
SCREEN_LINE = wb("SCREEN_LINE")
SCREEN_BUFFERS = leaf.SCREEN_BUFFERS

CELL_WORDS = wb("BLIT_CELL_WORDS")          # an AND mask, then the four bitplanes
CELL_BYTES = CELL_WORDS * WORD_LEN
COLUMN_PIXELS = wb("BLIT_COLUMN_PIXELS")    # what one plane word covers
COLUMN_BYTES = PLANES * WORD_LEN            # ...and what drawing it advances the screen cursor by
LAST_COLUMN_BYTES = COLUMN_BYTES - WORD_LEN  # the row's final `or.w` has no post-increment

SCRATCH_REGS = wb("BLIT_SCRATCH_REGS")      # d0..d5, the window the source cells are loaded through
# The four widths, in the order the jump tables hold them.
COLUMNS = tuple(range(wb("BLIT_COLUMNS_MIN"), wb("BLIT_COLUMNS_MAX") + 1))

# `move.l #$ffffffff,dn`'s own IMMEDIATE, which is what these bytes assemble — the mask word is then
# moved into its low half, so the bits the rotate brings down outside the sprite keep the screen.
# src/blit.c's WB_BLIT_MASK_FILL is the OTHER half of the same pair: the $ffff0000 the register
# holds once that `move.w` has landed. Two correct numbers for two different moments; the model
# below derives the second from this one rather than restating it. The plane words are `clr.l`ed.
MASK_FILL_IMMEDIATE = 0xffffffff

# One past the last on-screen pixel column, as the clip preludes measure it.
SCREEN_EDGE_X = wb("BLIT_SCREEN_EDGE_X")
UNWIND_BYTES = wb("BLIT_UNWIND_BYTES")      # `subq.w #6,a5` on the wholly-off-screen LEFT arm

WORD_MASK = leaf.WORD_MASK
WORD_SIGN_BIT = 0x8000                      # ...and the bit a `tst.w`'s `bmi` reads
LONG_MASK = leaf.LONGWORD_MASK
LONGWORD_LEN = 4

MID, LEFT, RIGHT = "mid", "left", "right"
SIDES = (MID, LEFT, RIGHT)

# The registers this family names, by the number the encoders want them as: a0 the sprite, a1 the
# screen, a5 the unwind, d6 the sub-word shift, d7 the row count and d4 the screen x a prelude
# clips against — plus the three the PASS's own walk uses, a6 the screen record, a4 the descriptor
# and a2 the blitter it calls through. d0..d5 are the scratch window and are addressed by index. The
# x register is the one of them include/blit.h has to name (it is scratch[4] under the body), so it
# is read from there.
A0, A1, A2, A4, A5, A6 = 0, 1, 2, 4, 5, 6
SHIFT_REG, ROWS_REG = 6, 7
X_REG = wb("BLIT_X_REG")

# Where the family begins and where it ends: the FIRST blitter ../names.txt names, and the table
# that sits immediately past the last one — so the region is measured against the things that name
# it rather than against itself.
CLIP_MASK = leaf.entry_of("blit_clip_mask")
TABLE_BY_SIDE = {MID: leaf.entry_of("blit_table_mid"),
                 LEFT: leaf.entry_of("blit_table_left"),
                 RIGHT: leaf.entry_of("blit_table_right")}
FAMILY_START = leaf.entry_of("blit_clip_left_w2")
FAMILY_END = TABLE_BY_SIDE[MID]

# Only the TWO-column bodies count their rows up front (`addq.w #1,d7 / tst / beq / bmi`); the wider
# ones just `dbf`. Only the clipped FOUR-column body defers a plane merge into its `btst`'s drawn
# arm. Both are include/blit.h's numbers, and the entry pins below are what check them.
GUARDED_COLUMNS = wb("BLIT_GUARDED_COLUMNS")
DEFERRED_MERGE_WIDTH = 4                    # ...and the width whose clipped body defers one
DEFERRED_MERGE = {DEFERRED_MERGE_WIDTH: wb("BLIT_DEFERRED_MERGE_COLUMN")}
NO_DEFERRED_MERGE = None


class Width:
    """One width: everything the twelve are parametrised by, derived from its column count."""

    def __init__(self, columns):
        self.columns = columns
        self.cells = columns - 1
        self.row_advance = SCREEN_LINE - (columns * COLUMN_BYTES - WORD_LEN)
        self.counts_rows_up_front = columns == GUARDED_COLUMNS
        self.deferred_merge_column = DEFERRED_MERGE.get(columns, NO_DEFERRED_MERGE)
        self.all_columns = (1 << columns) - 1

    def with_no_deferred_merge(self):
        """The same width with the $9324 quirk taken OUT, for the case that shows it is observable."""
        other = Width(self.columns)
        other.deferred_merge_column = NO_DEFERRED_MERGE
        return other


WIDTHS = {columns: Width(columns) for columns in COLUMNS}


def blitter_name(columns, side):
    """What ../names.txt calls the blitter of this width and clip case."""
    return f"blit_sprite_w{columns}" if side == MID else f"blit_clip_{side}_w{columns}"


BLITTERS = [(columns, side) for side in SIDES for columns in COLUMNS]


def cell_registers(cell):
    """Which of d0..d5 hold source cell ``cell`` — its mask, then its four planes.

    The original steps the window DOWN one register per cell (the masks land in d1, d0, d5, d4) so
    that the cell being loaded never overwrites the one it is still merging from.
    """
    mask = (SCRATCH_REGS + 1 - cell) % SCRATCH_REGS
    return mask, [(mask + 1 + plane) % SCRATCH_REGS for plane in range(PLANES)]


def column_bit(width, column):
    """`btst #n,blit_clip_mask`: the LEFTMOST column is the HIGHEST bit."""
    return width.columns - 1 - column


def clip_arms(width, side):
    """The ladder one prelude spells: (threshold, clip-mask byte) per arm, in the order the original
    tests them.

    A LEFT arm fires at or above its threshold and drops that many LEFT-hand columns; a RIGHT arm
    fires below its threshold and drops that many RIGHT-hand ones. ONE statement of the ladder, used
    both to assemble the preludes (which the image then pins) and to model which arm a case takes.
    """
    if side == LEFT:
        return [(-COLUMN_PIXELS * dropped, width.all_columns >> dropped)
                for dropped in range(1, width.columns)]
    return [(SCREEN_EDGE_X - COLUMN_PIXELS * (width.columns - dropped),
             width.all_columns & ~((1 << dropped) - 1))
            for dropped in range(width.columns)]


def clip_value(width, side, x):
    """Which arm fires at screen x ``x``, as the byte it writes — or None when the sprite has no
    column left on screen and the prelude returns without drawing."""
    fires = (lambda threshold: x >= threshold) if side == LEFT else (lambda threshold: x < threshold)
    for threshold, value in clip_arms(width, side):
        if fires(threshold):
            return value
    return None


# --- the encodings this battery adds ---------------------------------------------------------------
# `swap_dn` MOVED INTO leaf.py when this battery became its third user (test_scroll.py and
# test_stage.py had both spelt it). The rest are new here, and the ones that now stand at two users
# say so in their own docstring — this batch's STATUS.md section is where that list is registered.

def move_l_imm_dn(reg, value):
    """`move.l #imm,Dn` — the all-ones a mask word is moved into. ALSO IN test_stage.py."""
    return opcode(0x203c | (reg << 9)) + longword(value)


def clr_l_dn(reg):
    """`clr.l Dn` — the whole longword, which is what leaves a plane's wrapped half at zero.
    ALSO IN test_hud.py, where $bbca spells it over a register nothing reads."""
    return opcode(0x4280 | reg)


def ror_l_dn_dn(count_reg, reg):
    """`ror.l Dm,Dn` — the sub-word shift, applied to the whole longword so the pixels past the
    16-pixel boundary come out in the high half."""
    return opcode(0xe0b8 | (count_reg << 9) | reg)


def and_w_dn_dn(destination, source):
    """`and.w Dn,Dn` — how two cells' masks are merged at a column seam."""
    return opcode(0xc040 | (destination << 9) | source)


def or_w_dn_dn(destination, source):
    """`or.w Dn,Dn` — and how their planes are."""
    return opcode(0x8040 | (destination << 9) | source)


def and_w_dn_ind(reg, base):
    """`and.w Dn,(An)` — the mask going into the screen."""
    return opcode(0xc140 | (reg << 9) | 0x10 | base)


def or_w_dn_ind(reg, base):
    """`or.w Dn,(An)` — the row's LAST plane write, the one with no post-increment."""
    return opcode(0x8140 | (reg << 9) | 0x10 | base)


def or_w_dn_postinc(reg, base):
    """`or.w Dn,(An)+` — every other plane write.

    ALSO IN test_stage.py, in the SAME operand order: data register then address register, the way
    the mnemonic reads. (The two disagreed about it when this battery landed, which two encoders of
    one instruction can do silently — each one's own byte pins pass either way. test_scroll.py's
    `or_w_dn_postinc_a1` is a third spelling with the address register fixed, so it is not this.)
    """
    return opcode(0x8140 | (reg << 9) | 0x18 | base)


def btst_imm_abs_l(bit, addr):
    """`btst #n,<abs>.l` — a BYTE test against memory, so the bit is 0..7."""
    return opcode(0x0839) + word(bit) + longword(addr)


def subq_w_an(amount, reg):
    """`subq.w #n,An` — a WORD mnemonic over a 32-bit operation, which is the whole point of
    `test_the_unwind_is_a_longword_subtract`."""
    return opcode(0x5148 | ((amount & 7) << 9) | reg)


# The condition fields, as the whole opcode word of a WORD-displacement branch. The SHORT forms take
# their displacement in the low byte of the same word. The last two are the pass's alone — the
# twelve never spell them.
BRA, BEQ, BNE, BMI, BLT, BGE = 0x6000, 0x6700, 0x6600, 0x6b00, 0x6d00, 0x6c00
BPL, BGT = 0x6a00, 0x6e00
BRANCH_W_LEN = 4
BRANCH_S_LEN = 2
DBF_LEN = 4


def short_branch(condition, spanned_bytes):
    """`bcc.s`/`bra.s` FORWARD over ``spanned_bytes``.

    A short branch is the opcode word and nothing else, so its displacement is exactly the bytes it
    spans — where leaf.forward_branch's carries the extra 2 of the displacement WORD a long branch
    counts from. That two-byte difference is the whole reason this is not that.
    """
    return opcode(condition | (spanned_bytes & 0xff))


def short_branch_back(condition, spanned_bytes):
    """...and BACK over them, which is how the clipped two-column body reaches the `rts` of the
    prelude it was branched into. A backward displacement DOES carry leaf.backward_branch's 2: the
    span ends where the opcode starts, and the PC it is measured from is two bytes past that."""
    return opcode(condition | (int.from_bytes(backward_branch(spanned_bytes), "big") & 0xff))


# --- assembling the twelve --------------------------------------------------------------------------

def _load_cell(cell, defer_last_merge=False):
    """One source cell read into the register window.

    The first cell is loaded flat: all-ones into the mask register, `clr.l` over the four planes,
    then the five words and the five rotates. Every later cell SWAPS the previous cell's register as
    it goes — exposing the half the rotate pushed past the column boundary — and folds that half in
    with an `and` (mask) or an `or` (plane), which is the seam between two columns.
    """
    mask, planes = cell_registers(cell)
    if cell == 0:
        return (move_l_imm_dn(mask, MASK_FILL_IMMEDIATE)
                + b"".join(clr_l_dn(plane) for plane in planes)
                + move_w_postinc_dn(mask, A0)
                + b"".join(move_w_postinc_dn(plane, A0) for plane in planes)
                + ror_l_dn_dn(SHIFT_REG, mask)
                + b"".join(ror_l_dn_dn(SHIFT_REG, plane) for plane in planes))

    previous_mask, previous_planes = cell_registers(cell - 1)
    out = (swap_dn(previous_mask) + move_l_imm_dn(mask, MASK_FILL_IMMEDIATE)
           + move_w_postinc_dn(mask, A0)
           + ror_l_dn_dn(SHIFT_REG, mask) + and_w_dn_dn(mask, previous_mask))
    for plane, (reg, previous) in enumerate(zip(planes, previous_planes)):
        out += (swap_dn(previous) + clr_l_dn(reg) + move_w_postinc_dn(reg, A0)
                + ror_l_dn_dn(SHIFT_REG, reg))
        if not (defer_last_merge and plane == PLANES - 1):
            out += or_w_dn_dn(reg, previous)
    return out


def _swap_cell(cell):
    """The row's LAST column: swap all five of the last cell's registers and draw from them."""
    mask, planes = cell_registers(cell)
    return b"".join(swap_dn(reg) for reg in [mask] + planes)


def _draw_column(cell, is_last):
    """`and.w mask,(a1) / or.w plane,(a1)+` per plane, the last of them without the increment."""
    mask, planes = cell_registers(cell)
    out = b""
    for plane, reg in enumerate(planes):
        out += and_w_dn_ind(mask, A1)
        out += (or_w_dn_ind(reg, A1) if is_last and plane == PLANES - 1
                else or_w_dn_postinc(reg, A1))
    return out


def _clip_guard(width, column, drawn_bytes):
    """`btst #n,blit_clip_mask / bne <draw> / lea n(a1),a1 / bra.w <past the draw>`.

    The skip steps the screen cursor by exactly what drawing would have, so where a row ends does
    not depend on what was clipped out of it.
    """
    is_last = column == width.cells
    skip = lea_d16(A1, LAST_COLUMN_BYTES if is_last else COLUMN_BYTES)
    return (btst_imm_abs_l(column_bit(width, column), CLIP_MASK)
            + short_branch(BNE, len(skip) + BRANCH_W_LEN)
            + skip + branch_over(BRA, drawn_bytes))


def _row(width, clipped):
    """One row: the columns, then the `lea` that steps to the next scanline."""
    out = b""
    for column in range(width.columns):
        is_last = column == width.cells
        cell = width.cells - 1 if is_last else column
        defer = clipped and column == width.deferred_merge_column

        out += _swap_cell(cell) if is_last else _load_cell(cell, defer)
        drawn = _draw_column(cell, is_last)
        if defer:
            # $9324: the merge the load left out, INSIDE the arm that draws — see src/blit.c.
            _mask, planes = cell_registers(cell)
            _previous_mask, previous_planes = cell_registers(cell - 1)
            drawn = or_w_dn_dn(planes[PLANES - 1], previous_planes[PLANES - 1]) + drawn
        if clipped:
            out += _clip_guard(width, column, len(drawn))
        out += drawn
    return out + lea_d16(A1, width.row_advance)


def _body(width, clipped, guard_exit_back=None):
    """One whole blit body, entry to `rts`.

    ``guard_exit_back`` is how far BACK the two-column body's `beq`/`bmi` reach — the clipped one is
    branched into from a prelude and exits through THAT routine's `rts`, two bytes before the body,
    with short branches; the unclipped one has its own `rts` at the end and reaches it with word
    ones. Nothing but the distance makes them different instructions.
    """
    rows = _row(width, clipped)
    if not width.counts_rows_up_front:
        return rows + leaf.dbf_over(ROWS_REG, len(rows)) + RTS

    bump = addq_w_dn(1, ROWS_REG)
    test = tst_w_dn(ROWS_REG)
    if guard_exit_back is None:
        # Forward, to this body's own `rts` — which is PAST the closing `dbf`, so both branches
        # span that as well as the rows, and the `beq` spans the `bmi` under it too.
        past = len(rows) + DBF_LEN
        guard = test + branch_over(BEQ, BRANCH_W_LEN + past) + branch_over(BMI, past)
    else:
        # Backward, to the prelude's: each branch spans everything between its own opcode and that
        # `rts` — the bump and the test it sits behind, plus whatever guard bytes precede it.
        before = guard_exit_back + len(bump) + len(test)
        guard = (test + short_branch_back(BEQ, before)
                 + short_branch_back(BMI, before + BRANCH_S_LEN))
    loop = guard + rows
    return bump + loop + leaf.dbf_over(ROWS_REG, len(loop)) + RTS


# The one arm in the family whose `bra` to the shared body is SHORT where its neighbours' are long:
# blit_clip_left_w5's third ($939e, `6072`). Its own successor's target is nearer still and is a
# `bra.w` all the same, so this is the original assembler's inconsistency and not a rule.
SHORT_BRA_ARMS = {"blit_clip_left_w5": {2}}

# cmp.w #imm,d4 (4) + the skip branch (2) + move.b #imm,blit_clip_mask.l (8).
_ARM_HEAD_BYTES = 14


def _clip_prelude(entry, width, side, name, body):
    """One clip prelude: the ladder, then the arm that draws nothing.

    A left prelude's last act is `subq.w #6,a5` and a right one's is a bare `rts`, which is the only
    structural difference between the two — everything else is which way the compare runs.
    """
    skip = BLT if side == LEFT else BGE
    short_bra = SHORT_BRA_ARMS.get(name, ())
    out = b""
    for arm, (threshold, value) in enumerate(clip_arms(width, side)):
        write = move_b_imm_abs_l(value, CLIP_MASK)
        at = entry + len(out) + _ARM_HEAD_BYTES
        displacement = body - (at + len(opcode(0)))
        enter = (opcode(BRA | (displacement & 0xff)) if arm in short_bra
                 else opcode(BRA) + word(displacement))
        out += (cmp_w_imm_dn(X_REG, threshold) + short_branch(skip, len(write) + len(enter))
                + write + enter)
    return out + (subq_w_an(UNWIND_BYTES, A5) + RTS if side == LEFT else RTS)


def _shared_body_address(columns):
    """Where the two clip preludes of one width meet: inside the RIGHT one, past its own ladder.

    The left prelude `bra.w`s into the middle of the right routine, so the shared body has no name
    of its own and this is what both preludes' branch displacements are built from.
    """
    width = WIDTHS[columns]
    name = blitter_name(columns, RIGHT)
    entry = leaf.entry_of(name)
    return entry + len(_clip_prelude(entry, width, RIGHT, name, body=0))


SHARED_BODY = {columns: _shared_body_address(columns) for columns in COLUMNS}


def _blitter_bytes(columns, side):
    """The whole of one of the twelve, as ../bin/disk1/AUTO/SWB.PRG should hold it."""
    width = WIDTHS[columns]
    name = blitter_name(columns, side)
    entry = leaf.entry_of(name)
    if side == MID:
        return _body(width, clipped=False)

    prelude = _clip_prelude(entry, width, side, name, SHARED_BODY[columns])
    if side == LEFT:
        return prelude
    # The right prelude OWNS the shared body: the left one only branches into it.
    return prelude + _body(width, clipped=True,
                           guard_exit_back=len(RTS) if width.counts_rows_up_front else None)


ENTRY_BYTES = {blitter_name(columns, side): _blitter_bytes(columns, side)
               for columns, side in BLITTERS}
BLITTER_COUNT = 12


# --- what the image says the twelve are ------------------------------------------------------------

def test_the_batch_is_the_twelve_blitters():
    leaf.assert_batch_is_complete(ENTRY_BYTES, BLITTER_COUNT)


@pytest.mark.parametrize("columns,side", BLITTERS,
                         ids=[f"w{c}-{s}" for c, s in BLITTERS])
def test_a_blitter_is_the_bytes_the_image_holds(columns, side):
    """Every byte of all twelve, assembled from this battery's own statement of the geometry.

    This is the pin that lets src/blit.c be one walk rather than twelve: a column count, a clip
    threshold, a clip-mask value, a rotate, a `btst` bit or a row `lea` that is wrong there is wrong
    in these bytes here.
    """
    leaf.assert_entry_is(blitter_name(columns, side), ENTRY_BYTES[blitter_name(columns, side)])


def test_the_twelve_tile_the_region_the_jump_tables_close():
    """$8fce..$989c with no gap and no overlap, ending exactly where blit_table_mid begins — so
    "the family is these twelve" is a reading of the image rather than a boundary someone chose."""
    spans = sorted((leaf.entry_of(blitter_name(columns, side)),
                    len(ENTRY_BYTES[blitter_name(columns, side)]), blitter_name(columns, side))
                   for columns, side in BLITTERS)
    # Where the family STARTS is stated rather than taken from the sorted spans: seeded from the
    # spans themselves, the walk below would tile from wherever the lowest routine happened to be
    # and only the family's END would be pinned.
    at = FAMILY_START
    for entry, length, name in spans:
        assert entry == at, (
            f"{name} starts at {entry:#x}, not at {at:#x} where its predecessor ends — the family "
            f"does not tile")
        at = entry + length
    assert at == FAMILY_END, (
        f"the twelve end at {at:#x}, not at blit_table_mid's {FAMILY_END:#x}")


@pytest.mark.parametrize("columns", COLUMNS)
def test_both_preludes_of_a_width_share_one_clipped_body(columns):
    """The left prelude has no body of its own: it `bra.w`s into the right one's, past that
    routine's own ladder. Stated as an address inside the right routine's span, which is what makes
    src/blit.c's single `blit_rows` call from both preludes a reading rather than a convenience."""
    right = leaf.entry_of(blitter_name(columns, RIGHT))
    body = SHARED_BODY[columns]
    assert right < body < right + len(ENTRY_BYTES[blitter_name(columns, RIGHT)])

    left = leaf.entry_of(blitter_name(columns, LEFT))
    assert body > left + len(ENTRY_BYTES[blitter_name(columns, LEFT)]), (
        f"w{columns}'s shared body at {body:#x} is not past the whole of its left prelude")


@pytest.mark.parametrize("side", SIDES)
def test_a_jump_table_names_the_four_widths_in_order(side):
    """Each table is four longwords the original `jsr`s through, indexed by the width code 0..3 —
    read off the image and required to be the four entry points ../names.txt gives."""
    table = TABLE_BY_SIDE[side]
    entries = [int.from_bytes(bytes(harness.BASE_IMAGE[table + index * LONGWORD_LEN:
                                                       table + (index + 1) * LONGWORD_LEN]), "big")
               for index in range(len(COLUMNS))]
    named = [leaf.entry_of(blitter_name(columns, side)) for columns in COLUMNS]
    assert entries == named, (
        f"blit_table_{side} holds {[hex(a) for a in entries]}, not the {[hex(a) for a in named]} "
        f"../names.txt names")


def test_the_three_tables_are_the_only_things_that_name_a_blitter():
    """A whole-image longword scan: each of the twelve addresses occurs exactly ONCE, in its own
    table slot, and the three tables sit back to back immediately past the last blitter. Together
    those readings are why entering these twelve directly is the whole of their interface — nothing
    else in the program reaches them."""
    program = bytes(harness.BASE_IMAGE[:loader.PROGRAM_END])
    wanted = {longword(leaf.entry_of(blitter_name(columns, side))): (columns, side)
              for columns, side in BLITTERS}

    sites = {key: [] for key in wanted.values()}
    # `+ 1` because the last longword STARTS at len - 4: a bare `len - 4` bound would leave the end
    # of the program unscanned, which is where a table would be least likely to be noticed.
    for at in range(0, len(program) - LONGWORD_LEN + 1, WORD_LEN):
        key = wanted.get(program[at:at + LONGWORD_LEN])
        if key is not None:
            sites[key].append(at)

    for columns, side in BLITTERS:
        slot = TABLE_BY_SIDE[side] + COLUMNS.index(columns) * LONGWORD_LEN
        assert sites[(columns, side)] == [slot], (
            f"{blitter_name(columns, side)} is named at "
            f"{[hex(a) for a in sites[(columns, side)]]}, not only by its own table slot "
            f"{slot:#x}")

    assert TABLE_BY_SIDE[LEFT] == TABLE_BY_SIDE[MID] + len(COLUMNS) * LONGWORD_LEN
    assert TABLE_BY_SIDE[RIGHT] == TABLE_BY_SIDE[LEFT] + len(COLUMNS) * LONGWORD_LEN


def test_the_derived_geometry_is_what_the_numbers_say():
    """The constants include/blit.h states, checked against each other and against the widths."""
    assert [WIDTHS[columns].row_advance for columns in COLUMNS] == [146, 138, 130, 122]
    # A cell is the AND mask and then one word per plane — the header states the total, and this is
    # what says the total is those two things.
    assert CELL_WORDS == 1 + PLANES
    # ...and the clip byte is one address in two places: the header's and ../names.txt's.
    assert CLIP_MASK == wb("BLIT_CLIP_MASK")
    for columns in COLUMNS:
        width = WIDTHS[columns]
        # A row walks its columns and then `lea`s the rest of the scanline: the two must add up.
        drawn = width.columns * COLUMN_BYTES - WORD_LEN
        assert drawn + width.row_advance == SCREEN_LINE
        # ...and the two clip ladders run from "every column" to "one", from opposite ends: the
        # last LEFT arm keeps the rightmost column alone and the last RIGHT arm the leftmost.
        left, right = clip_arms(width, LEFT), clip_arms(width, RIGHT)
        assert left[0][1] == width.all_columns >> 1 and left[-1][1] == 1
        assert right[0][1] == width.all_columns
        assert right[-1][1] == 1 << (width.columns - 1)
        assert len(left) == width.columns - 1 and len(right) == width.columns


# --- the model ----------------------------------------------------------------------------------
# Written from ../out/wonderboy_dis.txt rather than from src/blit.c, so it is a third statement of
# the same walk and the one that lets a case say WHICH bytes moved and which registers came back.
# The 68000 OPERATIONS it walks with are deliberately not restated: `ror.l`, `swap` and a word write
# into a longword register are leaf.py's, as machine.h's are the reconstruction's — two
# implementations under one name, and the oracle is the referee for both. What this file states of
# its own is the WALK.

# A `swap Dn` is a rotate by half a longword, which is how src/blit.c's `swap_halves` spells it too
# (WB_BLIT_SWAP_BITS).
SWAP_BITS = 16


def _swap(value):
    """68k `swap Dn`."""
    return rotate_left32(value, SWAP_BITS)


def model_blit(image, width, side, entry):
    """({address: final byte}, {register: final value}) for one call, walked in Python.

    ``side`` picks the prelude: MID enters the body with every column drawn and the clip byte
    untouched, LEFT and RIGHT run their own ladder first. The walk is done on a MUTABLE copy of the
    image, so a case whose destination overlapped the clip byte or its own source would be modelled
    the way the original behaves rather than the way it was meant to.
    """
    mem = bytearray(image)
    written = set()
    regs = dict(entry)
    scratch = [regs[f"d{n}"] for n in range(SCRATCH_REGS)]
    shift, rows = regs["d6"], regs["d7"]
    source, dest = regs["a0"], regs["a1"]
    clipped = side != MID

    if clipped:
        value = clip_value(width, side, s16(regs["d4"]))
        if value is None:
            if side == LEFT:
                regs["a5"] = (regs["a5"] - UNWIND_BYTES) & LONG_MASK
            return {}, regs
        mem[CLIP_MASK] = value
        written.add(CLIP_MASK)

    def read_word(addr):
        return int.from_bytes(bytes(mem[addr:addr + WORD_LEN]), "big")

    def take_word():
        nonlocal source
        value = read_word(source)
        source = (source + WORD_LEN) & LONG_MASK
        return value

    def load_cell(cell, defer_last_merge):
        mask, planes = cell_registers(cell)
        if cell:
            previous_mask, previous_planes = cell_registers(cell - 1)
        else:
            previous_mask, previous_planes = None, [None] * PLANES
        for word_index, (reg, previous) in enumerate(zip([mask] + planes,
                                                         [previous_mask] + previous_planes)):
            is_mask = word_index == 0
            # `move.l #$ffffffff,dn` (or `clr.l dn`), then the source word into the low half.
            filled = set_low_word(MASK_FILL_IMMEDIATE if is_mask else 0, take_word())
            loaded = rotate_right32(filled, shift)
            if cell == 0:
                scratch[reg] = loaded
                continue
            scratch[previous] = _swap(scratch[previous])
            if defer_last_merge and word_index == CELL_WORDS - 1:
                scratch[reg] = loaded
            else:
                scratch[reg] = _merge(loaded, scratch[previous], is_mask)

    def draw_column(cell, is_last):
        nonlocal dest
        mask, planes = cell_registers(cell)
        for plane, reg in enumerate(planes):
            value = (read_word(dest) & (scratch[mask] & WORD_MASK)) | (scratch[reg] & WORD_MASK)
            mem[dest:dest + WORD_LEN] = value.to_bytes(WORD_LEN, "big")
            written.update(range(dest, dest + WORD_LEN))
            if not (is_last and plane == PLANES - 1):
                dest = (dest + WORD_LEN) & LONG_MASK

    def row():
        nonlocal dest
        for column in range(width.columns):
            is_last = column == width.cells
            cell = width.cells - 1 if is_last else column
            defer = clipped and column == width.deferred_merge_column

            if is_last:
                mask, planes = cell_registers(cell)
                for reg in [mask] + planes:
                    scratch[reg] = _swap(scratch[reg])
            else:
                load_cell(cell, defer)

            if clipped and not mem[CLIP_MASK] & (1 << column_bit(width, column)):
                dest = (dest + (LAST_COLUMN_BYTES if is_last else COLUMN_BYTES)) & LONG_MASK
                continue
            if defer:
                _mask, planes = cell_registers(cell)
                _previous_mask, previous_planes = cell_registers(cell - 1)
                last = PLANES - 1
                scratch[planes[last]] = _merge(scratch[planes[last]],
                                               scratch[previous_planes[last]], is_mask=False)
            draw_column(cell, is_last)
        dest = (dest + width.row_advance) & LONG_MASK

    if width.counts_rows_up_front:
        rows = set_low_word(rows, rows + 1)
        while s16(rows) > 0:
            row()
            rows = set_low_word(rows, rows - 1)
    else:
        while True:
            row()
            rows = set_low_word(rows, rows - 1)
            if rows & WORD_MASK == WORD_MASK:
                break

    regs.update({f"d{n}": scratch[n] for n in range(SCRATCH_REGS)})
    regs.update({"d7": rows, "a0": source, "a1": dest})
    return {addr: mem[addr] for addr in written}, regs


def _merge(loaded, wrapped, is_mask):
    """`and.w`/`or.w` of the previous cell's wrapped half into the word just loaded — a WORD op, so
    the loaded word's own wrapped half survives untouched."""
    half = wrapped & WORD_MASK
    return set_low_word(loaded, (loaded & half) if is_mask else (loaded | half))


# --- running one case -------------------------------------------------------------------------------
# Where a case puts its sprite. SPRITES.CRU is loaded at $25298 (../names.txt, $e87c) — past the
# program's last byte and holding nothing in a fresh image, which is what a seeded sprite needs.
SPRITE_SOURCE = 0x25298
SPRITE_BYTES = 0x400
SCREEN_BYTES = 2 * (SCREEN_BUFFERS[1] - SCREEN_BUFFERS[0])

# The screen band every case blits into, seeded ONCE. It is keyed on the ADDRESS, which is what
# makes a blit that ran a row long or took the wrong stride land on bytes that are wrong FOR WHERE
# THEY WERE WRITTEN; the salt only has to differ from the sprite's, and per-case screen bytes buy
# nothing over that. Rebuilding these 64 KB per case cost a quarter of the battery's time.
SCREEN_SALT = case_salt("screen")
SCREEN_SEED = keyed_block(SCREEN_BUFFERS[0], SCREEN_BYTES, SCREEN_SALT)

# THE SPRITE PASS'S OWN SCREEN ARITHMETIC ($8f6a..$8f98), which every blitter case's destination is
# built from and which the pass battery at the end of this file PINS: the buffer WB_SCREEN_BACK
# names, plus the window origin `adda.w #$1420,a1` adds, plus a SIXTEEN-BIT offset that the final
# `adda.w` sign-extends. Stated once here because the two halves of this file must not disagree
# about where a sprite goes.
SCREEN_ORIGIN = wb("BG_BLIT_SCREEN_ORIGIN")
COLUMN_ROUND_DOWN = wb("SPRITE_COLUMN_MASK")    # `andi.w #$fff0,d0`: the x, down to a whole column
X_BYTE_SHIFT = wb("SPRITE_X_BYTE_SHIFT")        # `asr.w #1,d0`, SIGNED: four planes put
                                                # COLUMN_PIXELS pixels in COLUMN_BYTES
ROW_SHIFT_LOW = wb("SPRITE_ROW_SHIFT_LOW")      # `asl.w #5,d1`
ROW_SHIFT_HIGH = wb("SPRITE_ROW_SHIFT_HIGH")    # ...and `asl.w #2,d1` over that, the two adding up
                                                # to a whole SCREEN_LINE
DEST_ROW = 60                       # mid-screen, with room above and below for any of these rows

# Neither the fully-off-screen arm nor an unclipped body touches a5, so a case that seeded it as
# zero could not tell "unchanged" from "cleared".
UNWIND_BASE = 0x00012345

# blit_clip_mask as a case finds it: NO column drawn. An unclipped body that read the byte would
# blit nothing, and a clipped one whose prelude failed to write it would too.
CLIP_MASK_SEED = 0

# What a run is allowed to execute, from the geometry: per row, a load per cell, a draw (and in a
# clipped body a `btst`) per column, and the `lea`/`dbf` that close it. Doubled, so the cap fails a
# run that fell into the runaway `dbf` rather than predicting the exact count.
_INSNS_PER_CELL = 25
_INSNS_PER_COLUMN = 13
_INSNS_PER_ROW = 4
_INSNS_ENTRY = 32

# No case here draws more rows than this. The bound is on the BATTERY, not on the game: a case that
# asked for the runaway `dbf` would otherwise be given a cap large enough to run it.
MAX_CASE_ROWS = 64
# What an entry count of $ffff draws on a `dbf` body. The counter is decremented ONCE PER ROW and
# the loop leaves when it is back at $ffff, so that is the whole 16-bit range and no more: 65,536,
# where batch 14 stated 65,537. Measured, not argued — the runaway case below walks a0 forward by
# exactly this many rows' worth of source and a1 by this many scanlines.
RUNAWAY_ROWS = WORD_MASK + 1


def _rows_drawn(width, rows):
    """How many rows this entry count draws.

    d7 + 1, and the two shapes part company on the two ways that can fail to be a small number. A
    two-column body BUMPS AND TESTS, so a count that is zero or negative once bumped draws nothing.
    A wider one just `dbf`s, so the bump wrapping to zero is not a refusal but the runaway: $ffff
    draws the whole 16-bit range. Counting that as "0 rows drawn" is the hole this closes — it
    handed the one entry count that runs RUNAWAY_ROWS of them a 64-instruction cap.
    """
    drawn = (rows + 1) & WORD_MASK
    if width.counts_rows_up_front:
        return 0 if drawn == 0 or drawn & WORD_SIGN_BIT else drawn
    return drawn if drawn else RUNAWAY_ROWS


def _blit_insns(width, rows):
    """What one blit that ENTERS A ROW LOOP may execute — and the battery's refusal to ask for the
    runaway `dbf`.

    Split from `_insn_cap` so that a PASS case, whose cap is the sum over the records it draws, can
    both bound each blit and inherit the refusal without restating either. A record whose x leaves
    no column on screen is not one of them: `_model_pass_record` budgets those for the prelude's
    ladder alone, since no `dbf` ever sees their count.
    """
    drawn = _rows_drawn(width, rows)
    assert drawn <= MAX_CASE_ROWS, (
        f"a case asking for {drawn} rows is asking for the runaway `dbf`, which only "
        f"`test_a_negative_height_runs_a_wider_body_away` is set up to survive, not for a blit")
    return _INSNS_ENTRY + drawn * (width.cells * _INSNS_PER_CELL
                                   + width.columns * _INSNS_PER_COLUMN + _INSNS_PER_ROW)


def _insn_cap(width, rows):
    """The instruction cap for a case entering one of the twelve directly."""
    return 2 * _blit_insns(width, rows)


def _screen_offset(x, y):
    """$8f84..$8f96: the SIXTEEN-BIT byte offset of (x, y) inside the window, and what the y
    register is left holding.

    Both a claim and a warning: the whole offset is a word, so a large x or y wraps inside it rather
    than reaching where the arithmetic points, and the two `asl.w`s leave the y register at y << 7
    and not at y.
    """
    column = s16(x & COLUMN_ROUND_DOWN) >> X_BYTE_SHIFT
    row = (y << ROW_SHIFT_LOW) & WORD_MASK
    offset = (column + row) & WORD_MASK
    row = (row << ROW_SHIFT_HIGH) & WORD_MASK
    return (offset + row) & WORD_MASK, row


def _dest_for(x, y, screen):
    """Where the sprite pass puts a sprite at (x, y) in the buffer `screen`."""
    offset, _row = _screen_offset(x, y)
    return (screen + SCREEN_ORIGIN + s16(offset)) & LONG_MASK


class BlitRegs(ctypes.Structure):
    """include/blit.h's `sprite_blit_regs` — the same fields in the same order, which is what lets a
    case hand the reconstruction its entry registers and read all eleven back."""
    _fields_ = [("scratch", ctypes.c_uint32 * SCRATCH_REGS),
                ("shift", ctypes.c_uint32), ("rows", ctypes.c_uint32),
                ("source", ctypes.c_uint32), ("dest", ctypes.c_uint32),
                ("unwind", ctypes.c_uint32)]


# Which field of that struct carries which register. d0..d5 are the `scratch` array, by index.
FIELD_BY_REG = {"d6": "shift", "d7": "rows", "a0": "source", "a1": "dest", "a5": "unwind"}
STRUCT_REGS = [f"d{n}" for n in range(SCRATCH_REGS)] + list(FIELD_BY_REG)

_BLIT_FNS = {blitter_name(columns, side):
             leaf.bind(blitter_name(columns, side),
                       leaf.IMAGE_ARG + [ctypes.POINTER(BlitRegs)])
             for columns, side in BLITTERS}


def _regs_glue(new_box, fn, entry):
    """Differential glue for a reconstruction whose result is an in/out ctypes REGISTER FILE.

    ``new_box`` returns (the box the call is handed, the `BlitRegs` carrying d0..d5, the
    [(owner, {register: field})] pairs that say which of its fields hold which named registers) —
    one for a bare blitter and one for the pass, whose box adds the three the walk itself uses. Both
    glues are then this function, so the fill and the read are one statement rather than two that
    could disagree about a field.

    The box is built FRESH per run: the kit's attribution pass runs a candidate a second time on a
    poisoned image, and a box carried over would start that run from the first one's OUTPUT
    registers. What comes back is a plain dict, for the same reason — the box is about to be written
    over.
    """
    def glue(_lib, image):
        box, blit, maps = new_box()
        for reg in range(SCRATCH_REGS):
            blit.scratch[reg] = entry[f"d{reg}"]
        for owner, field_by_reg in maps:
            for reg, field in field_by_reg.items():
                setattr(owner, field, entry[reg])

        fn(image, ctypes.byref(box))

        out = {f"d{reg}": blit.scratch[reg] for reg in range(SCRATCH_REGS)}
        for owner, field_by_reg in maps:
            out.update({reg: getattr(owner, field) for reg, field in field_by_reg.items()})
        return out
    return glue


def _blit_box():
    box = BlitRegs()
    return box, box, [(box, FIELD_BY_REG)]


def _blit_glue(name, entry):
    return _regs_glue(_blit_box, _BLIT_FNS[name], entry)


def _entry_registers(case, x, shift, rows, dest, unwind):
    """The fifteen longwords a case is entered with.

    The high halves are GARBAGE on purpose: d4 is compared with `cmp.w`, d6 is a rotate count the
    68000 reads mod 64 and d7 is stepped with `addq.w`/`dbf`, so a reconstruction that read any of
    them as a longword fails here rather than on the game's own small values. The scratch registers
    are seeded too, which is what makes "d0 is never touched by a two-column body" observable.
    """
    salt = case_salt(case)

    def garbage(reg):
        return (leaf.keyed_byte(salt, reg) << 8) | leaf.keyed_byte(reg, salt)

    entry = {f"d{reg}": (garbage(reg) << 16) | garbage(reg + 8) for reg in range(SCRATCH_REGS)}
    entry.update({f"a{reg}": 0 for reg in range(7)})
    entry["d4"] = (garbage(4) << 16) | (x & WORD_MASK)
    entry["d6"] = (garbage(6) << 16) | (shift & WORD_MASK)
    entry["d7"] = (garbage(7) << 16) | (rows & WORD_MASK)
    entry["a0"] = SPRITE_SOURCE
    entry["a1"] = dest
    entry["a5"] = unwind
    return entry


def _case_pokes(case):
    """What a case seeds: its own sprite, the screen band, and the clip byte.

    ONE statement of the seeding convention, so a case that wants to model something a second way
    (the late merge below, the unshifted last column) rebuilds the image from this rather than
    restating which salt goes where — two statements of it could drift, and the second one would
    then be modelling a different image from the one that ran.
    """
    return {
        SPRITE_SOURCE: keyed_block(SPRITE_SOURCE, SPRITE_BYTES, case_salt(case)),
        SCREEN_BUFFERS[0]: SCREEN_SEED,
        CLIP_MASK: bytes([CLIP_MASK_SEED]),
    }


def _run_blit(case, columns, side, x=0, shift=0, rows=1, y=DEST_ROW, unwind=UNWIND_BASE,
              screen=SCREEN_BUFFERS[0]):
    """One case: the model, the oracle and the reconstruction over one seeded image.

    Returns (model writes, model registers, oracle info) once the three have been required to agree
    — so a case asserting anything further is asserting on all of them.
    """
    width = WIDTHS[columns]
    name = blitter_name(columns, side)
    dest = _dest_for(x, y, screen)
    # BEFORE the model runs: a row count that asks for the runaway `dbf` is refused here, and the
    # Python walk would otherwise spin through all RUNAWAY_ROWS of its rows before the cap was
    # consulted.
    cap = _insn_cap(width, rows)

    pokes = _case_pokes(case)
    entry = _entry_registers(case, x, shift, rows, dest, unwind)
    image = make_image(pokes)
    expected_writes, expected_regs = model_blit(image, width, side, entry)

    what = f"{name} {case}"
    info = leaf.run(name, _blit_glue(name, entry), merge_bands(expected_writes), what,
                    regs=dict(entry, _pokes=pokes), max_insns=cap)

    written = program_writes(info)
    assert written == expected_writes, (
        f"{what}: the original wrote {len(written)} bytes and the model {len(expected_writes)} — "
        f"first difference at "
        f"{min(set(written) ^ set(expected_writes), default=-1):#x}")
    for reg in emu.REPORTED_REGS:
        assert info["regs"][reg] == expected_regs[reg], (
            f"{what}: the original left {reg}={info['regs'][reg]:#010x}, not the model's "
            f"{expected_regs[reg]:#010x}")
    for reg in STRUCT_REGS:
        assert info["ret"][reg] == expected_regs[reg], (
            f"{what}: the reconstruction left {reg}={info['ret'][reg]:#010x}, not the model's "
            f"{expected_regs[reg]:#010x}")
    return expected_writes, expected_regs, info


# --- every width, every clip case ---------------------------------------------------------------
# The two shifts: none at all (the sprite lands on a word boundary and the rotate is a no-op) and
# one that is neither 0 nor 8, so every plane word straddles two columns unevenly.
SHIFTS = (0, 5)
ROW_COUNTS = (0, 3)                  # one row, and four — d7 is a "one fewer than this many"
ON_SCREEN_X = 0x40                   # inside the window for every width, and a whole word in
LEFT_X = -COLUMN_PIXELS              # the shallowest left clip: one column dropped
RIGHT_X = SCREEN_EDGE_X - 2 * COLUMN_PIXELS   # ...and a right one that drops at least one


@pytest.mark.parametrize("columns", COLUMNS)
@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("shift", SHIFTS)
@pytest.mark.parametrize("rows", ROW_COUNTS)
def test_a_blit_draws_the_columns_its_width_and_its_clipping_leave(columns, side, shift, rows):
    """The matrix: four widths x three clip cases x two shifts x two row counts.

    Each case states the whole write set and all fifteen registers, so what it pins is not only that
    the two sides agree but which bytes moved, how far the source and the screen cursors walked and
    what the register window was left holding.
    """
    x = {MID: ON_SCREEN_X, LEFT: LEFT_X, RIGHT: RIGHT_X}[side]
    _run_blit(f"matrix-w{columns}-{side}-s{shift}-r{rows}", columns, side,
              x=x, shift=shift, rows=rows)


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
def test_a_blit_draws_wherever_its_destination_points(screen):
    """a1 is an argument, not a global: the same sprite is blitted into both of the game's screen
    buffers, so a reconstruction that reached for one of them would fail on the other."""
    _run_blit(f"screen-{screen:#x}", 4, MID, x=ON_SCREEN_X, shift=3, rows=2, screen=screen)


def test_a_blit_writes_exactly_its_own_rectangle():
    """The write set as a RECTANGLE rather than as whatever the model produced: one run of
    columns * 8 bytes per row, WB_SCREEN_LINE apart — so the 120-odd bytes between the end of one
    row and the start of the next are pinned as NOT written."""
    columns, rows = 5, 3
    dest = _dest_for(ON_SCREEN_X, DEST_ROW, SCREEN_BUFFERS[0])
    writes, _regs, _info = _run_blit("rectangle", columns, MID, x=ON_SCREEN_X, shift=7, rows=rows)
    rectangle = {dest + row * SCREEN_LINE + byte
                 for row in range(rows + 1)
                 for byte in range(columns * COLUMN_BYTES)}
    assert set(writes) == rectangle, (
        f"the blit wrote {len(writes)} bytes against the rectangle's {len(rectangle)} — first "
        f"difference at {min(set(writes) ^ rectangle):#x}")


@pytest.mark.parametrize("columns", COLUMNS)
def test_a_clipped_blit_consumes_its_whole_sprite_anyway(columns):
    """A skipped column still owes the next one its wrapped half, so the source is read in full
    whatever the clip mask says: a0 walks CELL_BYTES per cell per row either way. Stated against the
    narrowest clip there is — one column drawn — so a reconstruction that skipped the read with the
    draw fails on the pointer even where it agrees on the pixels."""
    rows = 2
    _writes, regs, _info = _run_blit(f"consumed-w{columns}", columns, LEFT,
                                     x=-COLUMN_PIXELS * (columns - 1), shift=3, rows=rows)
    walked = regs["a0"] - SPRITE_SOURCE
    assert walked == (rows + 1) * WIDTHS[columns].cells * CELL_BYTES, (
        f"w{columns} read {walked} bytes of sprite, not the whole {rows + 1} rows of it")


# --- the clip ladders ------------------------------------------------------------------------------

LADDER_ROWS = 1                          # so a ladder case draws TWO rows: d7 is one fewer than that


def _ladder_cases(side):
    """One case per arm of every prelude on one side, named by the byte the arm writes."""
    return [(columns, threshold, value)
            for columns in COLUMNS
            for threshold, value in clip_arms(WIDTHS[columns], side)]


def _clipped_write_count(value):
    """What a ladder case's write set must come to: the clip byte the prelude wrote, plus one
    column of screen per bit that survived it, over every row drawn."""
    return 1 + bin(value).count("1") * COLUMN_BYTES * (LADDER_ROWS + 1)


@pytest.mark.parametrize("columns,threshold,value", _ladder_cases(LEFT),
                         ids=[f"w{c}-x{t}-mask{v:#x}" for c, t, v in _ladder_cases(LEFT)])
def test_a_left_clip_arm_drops_the_columns_its_mask_says(columns, threshold, value):
    """Every arm of all four left preludes, entered AT its own threshold — the first x that takes
    it. The mask each writes is asserted out of the oracle's write set rather than inferred, and the
    drawn columns follow from it through the model both sides are compared against."""
    writes, _regs, info = _run_blit(f"left-w{columns}-{value:#x}", columns, LEFT,
                                    x=threshold, shift=5, rows=LADDER_ROWS)
    assert leaf.read_int(info, CLIP_MASK, 1, "the clip byte") == value
    assert len(writes) == _clipped_write_count(value), (
        f"w{columns} at x={threshold} wrote {len(writes)} bytes, not the "
        f"{bin(value).count('1')} columns mask {value:#x} names")


@pytest.mark.parametrize("columns,threshold,value", _ladder_cases(RIGHT),
                         ids=[f"w{c}-x{t:#x}-mask{v:#x}" for c, t, v in _ladder_cases(RIGHT)])
def test_a_right_clip_arm_drops_the_columns_its_mask_says(columns, threshold, value):
    """The same for all fourteen right-hand arms, entered one pixel BELOW each threshold — the last
    x that takes it, so an arm whose compare was off by one falls through to its neighbour."""
    x = threshold - 1
    writes, _regs, info = _run_blit(f"right-w{columns}-{value:#x}", columns, RIGHT,
                                    x=x, shift=5, rows=LADDER_ROWS)
    assert leaf.read_int(info, CLIP_MASK, 1, "the clip byte") == value
    assert len(writes) == _clipped_write_count(value), (
        f"w{columns} at x={x:#x} wrote {len(writes)} bytes, not the "
        f"{bin(value).count('1')} columns mask {value:#x} names")


@pytest.mark.parametrize("columns", COLUMNS)
def test_a_left_clip_arm_is_taken_at_its_threshold_and_not_below_it(columns):
    """`cmp.w #-16k,d4 / blt` — the arm fires AT its threshold, so the pixel below it belongs to the
    next arm down. Both sides of the boundary, for the shallowest arm of each width."""
    threshold = -COLUMN_PIXELS
    assert clip_value(WIDTHS[columns], LEFT, threshold) != clip_value(WIDTHS[columns], LEFT,
                                                                     threshold - 1)
    _run_blit(f"left-edge-at-w{columns}", columns, LEFT, x=threshold, shift=1, rows=0)
    _run_blit(f"left-edge-below-w{columns}", columns, LEFT, x=threshold - 1, shift=1, rows=0)


@pytest.mark.parametrize("columns", COLUMNS)
def test_a_right_clip_arm_is_taken_below_its_threshold_and_not_at_it(columns):
    """...and `cmp.w #imm,d4 / bge` the other way about: the threshold itself belongs to the arm
    above."""
    threshold = SCREEN_EDGE_X - COLUMN_PIXELS
    assert clip_value(WIDTHS[columns], RIGHT, threshold - 1) is not None
    assert clip_value(WIDTHS[columns], RIGHT, threshold) is None
    _run_blit(f"right-edge-below-w{columns}", columns, RIGHT, x=threshold - 1, shift=1, rows=0)
    _run_blit(f"right-edge-at-w{columns}", columns, RIGHT, x=threshold, shift=1, rows=0)


@pytest.mark.parametrize("columns", COLUMNS)
def test_a_sprite_wholly_off_the_left_edge_draws_nothing_and_unwinds(columns):
    """Past the last left arm: no clip byte, no pixel, and a5 stepped back by six."""
    x = -COLUMN_PIXELS * columns
    assert clip_value(WIDTHS[columns], LEFT, x) is None
    writes, regs, _info = _run_blit(f"off-left-w{columns}", columns, LEFT, x=x, shift=5, rows=3)
    assert writes == {}
    assert regs["a5"] == UNWIND_BASE - UNWIND_BYTES


@pytest.mark.parametrize("columns", COLUMNS)
def test_a_sprite_wholly_off_the_right_edge_draws_nothing_and_leaves_a5_alone(columns):
    """The mirror arm, which does NOT unwind — the one asymmetry between the two ladders."""
    x = SCREEN_EDGE_X - COLUMN_PIXELS
    assert clip_value(WIDTHS[columns], RIGHT, x) is None
    writes, regs, _info = _run_blit(f"off-right-w{columns}", columns, RIGHT, x=x, shift=5, rows=3)
    assert writes == {}
    assert regs["a5"] == UNWIND_BASE


def test_the_unwind_is_a_longword_subtract():
    """`subq.w #6,a5` is a WORD mnemonic over a 32-BIT operation, which is the 68000's rule for
    address registers. Entered with a5 four bytes into a high word, so a word-wide subtract would
    wrap inside the low half and leave the high one alone — and be caught here."""
    unwind = 0x00010004
    _writes, regs, _info = _run_blit("unwind-borrow", 3, LEFT, x=-COLUMN_PIXELS * 3,
                                     shift=0, rows=0, unwind=unwind)
    assert regs["a5"] == unwind - UNWIND_BYTES == 0x0000fffe


# --- the row count ---------------------------------------------------------------------------------

@pytest.mark.parametrize("columns", COLUMNS)
def test_a_row_count_of_zero_draws_one_row(columns):
    """d7 is a "one fewer than this many": every body draws d7+1 rows, and zero draws one."""
    writes, _regs, _info = _run_blit(f"one-row-w{columns}", columns, MID,
                                     x=ON_SCREEN_X, shift=3, rows=0)
    assert len(writes) == WIDTHS[columns].columns * COLUMN_BYTES


@pytest.mark.parametrize("rows", [0xffff, 0xfffe, 0x7fff])
@pytest.mark.parametrize("side", [MID, LEFT])
def test_the_two_column_bodies_refuse_a_row_count_that_is_not_positive(rows, side):
    """`addq.w #1,d7 / tst.w d7 / beq / bmi`, which ONLY the two-column bodies have.

    $ffff bumps to zero and takes the `beq`; $fffe stays negative and takes the `bmi`; $7fff bumps
    to $8000, which is the case that separates a signed test from an unsigned one — 32,768 rows
    would be 5 MB of screen. All three draw nothing at all, and the counter comes back at whatever
    the bump left, which is how a case tells the two exits apart.
    """
    x = ON_SCREEN_X if side == MID else -COLUMN_PIXELS
    writes, regs, _info = _run_blit(f"no-rows-{side}-{rows:#x}", GUARDED_COLUMNS, side,
                                    x=x, shift=5, rows=rows)
    drawn = {addr: byte for addr, byte in writes.items() if addr != CLIP_MASK}
    assert drawn == {}, f"a row count of {rows:#x} drew {len(drawn)} bytes"
    assert regs["d7"] & WORD_MASK == (rows + 1) & WORD_MASK


@pytest.mark.parametrize("rows,runs", [(0xffff, RUNAWAY_ROWS), (0xfffe, 0xffff), (0x7fff, 0x8000)],
                         ids=["ffff", "fffe", "7fff"])
def test_the_battery_refuses_to_ask_a_wider_body_for_those_counts(rows, runs):
    """The same three counts a two-column body REFUSES are what the wider ones run away on, and the
    cap is where this battery declines to ask.

    $ffff is the one that has to be spelt out: a wider body `dbf`s, so it draws the whole 16-bit
    range — RUNAWAY_ROWS rows, 10 MB of screen — where the BUMPED COUNTER alone says "zero".
    A cap taken from that bumped counter would have been 64 instructions, and the case would have
    failed as a cap overrun on a run that was behaving exactly as reproduced.
    """
    guarded, wide = WIDTHS[GUARDED_COLUMNS], WIDTHS[max(COLUMNS)]
    assert _rows_drawn(wide, rows) == runs
    with pytest.raises(AssertionError, match="runaway"):
        _insn_cap(wide, rows)
    # ...while the width whose guard DOES refuse them is still a case this battery may run.
    assert _rows_drawn(guarded, rows) == 0
    assert _insn_cap(guarded, rows) > 0


@pytest.mark.parametrize("columns", COLUMNS)
def test_a_body_leaves_its_own_row_counter_behind(columns):
    """The two loop shapes part company on the way out: a two-column body exits through its `tst`
    with the counter at ZERO, and the three wider ones exit through the `dbf` with it at $ffff.
    Same interface, two exit values, and both are what the next caller sees."""
    rows = 2
    _writes, regs, _info = _run_blit(f"counter-w{columns}", columns, MID,
                                     x=ON_SCREEN_X, shift=1, rows=rows)
    expected = 0 if WIDTHS[columns].counts_rows_up_front else WORD_MASK
    assert regs["d7"] & WORD_MASK == expected


def test_a_two_column_body_never_touches_d0():
    """Five source words fit in d1..d5, so the narrowest width is the one that leaves d0 exactly as
    it found it — a register the other three widths all use. Seeded with garbage, so "unchanged" is
    distinguishable from "cleared"."""
    case = "d0-untouched"
    entry = _entry_registers(case, ON_SCREEN_X, 5, 3,
                             _dest_for(ON_SCREEN_X, DEST_ROW, SCREEN_BUFFERS[0]), UNWIND_BASE)
    _writes, regs, _info = _run_blit(case, 2, MID, x=ON_SCREEN_X, shift=5, rows=3)
    assert regs["d0"] == entry["d0"] != 0


# --- the rotate --------------------------------------------------------------------------------------

@pytest.mark.parametrize("columns", COLUMNS)
def test_an_unshifted_sprite_leaves_its_last_column_alone(columns):
    """At a shift of zero the rotate is a no-op, so every cell's wrapped half is the all-ones mask
    and four zero planes: the row's LAST column ANDs with $ffff and ORs nothing, and the screen
    under it comes back unchanged — while still being written, which is what the kit's attribution
    pass makes observable."""
    case = f"unshifted-w{columns}"
    dest = _dest_for(ON_SCREEN_X, DEST_ROW, SCREEN_BUFFERS[0])
    writes, _regs, _info = _run_blit(case, columns, MID, x=ON_SCREEN_X, shift=0, rows=1)
    image = make_image(_case_pokes(case))
    last = {dest + row * SCREEN_LINE + (columns - 1) * COLUMN_BYTES + byte
            for row in range(2) for byte in range(COLUMN_BYTES)}
    assert last <= set(writes)
    for addr in sorted(last):
        assert writes[addr] == image[addr], (
            f"w{columns}'s last column changed {addr:#x} at a shift of zero")


@pytest.mark.parametrize("shift", [1, 8, 15])
def test_a_shifted_sprite_carries_pixels_into_the_next_column(shift):
    """...and at any other shift it does not: the same sprite at the same place writes something
    else into that last column, because the rotate has pushed pixels into it."""
    columns = 4
    dest = _dest_for(ON_SCREEN_X, DEST_ROW, SCREEN_BUFFERS[0])
    unshifted, _regs, _info = _run_blit(f"carry-w4-s0-{shift}", columns, MID,
                                        x=ON_SCREEN_X, shift=0, rows=1)
    shifted, _regs, _info = _run_blit(f"carry-w4-s0-{shift}", columns, MID,
                                      x=ON_SCREEN_X, shift=shift, rows=1)
    last = [dest + (columns - 1) * COLUMN_BYTES + byte for byte in range(COLUMN_BYTES)]
    assert any(shifted[addr] != unshifted[addr] for addr in last), (
        f"a shift of {shift} moved nothing into the last column")


# --- the four-column clipped body's late merge --------------------------------------------------------
LATE_MERGE_SHIFT = 5                 # any shift that actually wraps a half into the next column


def _deferred_merge_arms():
    """Every arm of the four-column ladders whose mask SKIPS the deferred column, as (side, x,
    mask) — the x being the first (LEFT) or last (RIGHT) that takes the arm.

    Both ladders, because they skip it in different company: the LEFT one has an arm that skips
    column 2 and still DRAWS column 3, which is the row's last and comes out of the very register
    the skip left unmerged. That arm is what makes "it moves no pixel" a claim about a register the
    run reads; under the right-hand arms columns 2 and 3 are both dropped, and the pixel half of the
    case would hold vacuously.
    """
    width = WIDTHS[DEFERRED_MERGE_WIDTH]
    deferred_bit = 1 << column_bit(width, width.deferred_merge_column)
    last_bit = 1 << column_bit(width, width.columns - 1)
    arms = [(side, threshold if side == LEFT else threshold - 1, value)
            for side in (LEFT, RIGHT)
            for threshold, value in clip_arms(width, side)
            if not value & deferred_bit]

    assert arms, "no arm of the four-column ladders skips its deferred column"
    assert any(value & last_bit for _side, _x, value in arms), (
        "no arm that skips the deferred column still draws the row's last one, so nothing here "
        "reads the register the skip left unmerged and the pixel half of the case is vacuous")
    return arms


DEFERRED_MERGE_ARMS = _deferred_merge_arms()


@pytest.mark.parametrize("side,x,mask", DEFERRED_MERGE_ARMS,
                         ids=[f"{s}-mask{v:#x}" for s, _x, v in DEFERRED_MERGE_ARMS])
def test_the_clipped_four_column_body_leaves_a_plane_unmerged_when_it_skips_a_column(side, x, mask):
    """$9324: that body's `or.w d4,d3` sits INSIDE the arm the `btst` at $9312 branches to,
    where every other body merges before the test. So a run that skips column 2 leaves d3 holding
    the loaded word alone.

    It moves no pixel — the low word it would have merged is only drawn by the arm that merges it —
    and each case shows exactly that: the SAME width with the quirk taken out writes the same bytes
    and returns a DIFFERENT d3. Without the second half these cases would pass on a reconstruction
    that merged unconditionally; without the LEFT arm's mask $1, which skips column 2 and draws
    column 3 out of the unmerged d3, the first half would hold with nothing reading that register.
    """
    columns = DEFERRED_MERGE_WIDTH
    width = WIDTHS[columns]
    case = f"late-merge-{side}-{mask:#x}"
    writes, regs, _info = _run_blit(case, columns, side, x=x, shift=LATE_MERGE_SHIFT, rows=1)

    entry = _entry_registers(case, x, LATE_MERGE_SHIFT, 1,
                             _dest_for(x, DEST_ROW, SCREEN_BUFFERS[0]), UNWIND_BASE)
    image = make_image(_case_pokes(case))
    merged_writes, merged_regs = model_blit(image, width.with_no_deferred_merge(), side, entry)
    assert merged_writes == writes, "the late merge changed a pixel, which it must not"
    assert merged_regs != regs, "the late merge is invisible here, so this case pins nothing"
    differing = [reg for reg in emu.REPORTED_REGS if merged_regs[reg] != regs[reg]]
    assert differing == ["d3"], f"the late merge shows in {differing}, not in d3 alone"


# --- a sweep over the geometry ------------------------------------------------------------------------
# Sharded per the recipe in ../../../buggyboy/recreate/README.md: one stream, generated in full by
# every worker (microseconds) and RUN by the one whose chunk owns the iteration, so the coverage
# is identical to the un-sharded loop.
#
# The GEOMETRY is enumerated rather than drawn: width x clip case x shift is 192 combinations and
# every one of them is a case, so "every shift against every width and every clip case" is a
# property of the list and not of a seed. What stays random — inside a range each combination picks
# for itself — is where on the screen the sprite lands and how many rows it draws.
FUZZ_CHUNKS = 6
MAX_SWEEP_ROWS = 5                   # entry counts 0..5, i.e. one to six rows
SWEEP_TOP_ROW, SWEEP_BOTTOM_ROW = 8, 120


def _fuzz_cases():
    rng = random.Random(0x8FCE)
    combinations = [(columns, side, shift)
                    for columns in COLUMNS
                    for side in SIDES
                    for shift in range(COLUMN_PIXELS)]
    for index, (columns, side, shift) in enumerate(combinations):
        rows = rng.randrange(0, MAX_SWEEP_ROWS + 1)
        y = rng.randrange(SWEEP_TOP_ROW, SWEEP_BOTTOM_ROW)
        if side == MID:
            x = rng.randrange(0, SCREEN_EDGE_X - COLUMN_PIXELS * columns)
        elif side == LEFT:
            # Past the last arm as well as inside the ladder: the wholly-off-screen arm is in range.
            x = -rng.randrange(1, COLUMN_PIXELS * columns + COLUMN_PIXELS)
        else:
            x = rng.randrange(SCREEN_EDGE_X - COLUMN_PIXELS * columns, SCREEN_EDGE_X)
        yield index, columns, side, x, shift, rows, y


FUZZ_CASES = len(list(_fuzz_cases()))


@pytest.mark.parametrize("chunk", range(FUZZ_CHUNKS))
def test_a_sweep_of_widths_shifts_and_clip_positions(chunk):
    """All 16 shifts against all four widths and all three clip cases — every combination once, at a
    screen position and a row count the case draws for itself, including x values that fall between
    two arms of a ladder and past the end of one."""
    for index, columns, side, x, shift, rows, y in _fuzz_cases():
        if index % FUZZ_CHUNKS != chunk:
            continue
        _run_blit(f"sweep-{index}", columns, side, x=x, shift=shift, rows=rows, y=y)


def test_the_sweep_covers_every_width_shift_and_clip_case():
    """The enumeration says what it covers, so this is what makes that a reading of the list rather
    than of its docstring — and what fails if a chunk's slice ever stops partitioning it."""
    geometry = {(columns, side, shift)
                for _index, columns, side, _x, shift, _rows, _y in _fuzz_cases()}
    assert geometry == {(columns, side, shift) for columns in COLUMNS for side in SIDES
                        for shift in range(COLUMN_PIXELS)}
    assert len(geometry) == FUZZ_CASES, "the sweep runs a combination more than once"
    sharded = sum(1 for index, *_rest in _fuzz_cases() for chunk in range(FUZZ_CHUNKS)
                  if index % FUZZ_CHUNKS == chunk)
    assert sharded == FUZZ_CASES, "the chunks do not partition the sweep"


# ==================================================================================================
# THE SPRITE PASS AT $8f02 — the caller of the twelve above (batch 15)
# ==================================================================================================
# 204 bytes, ONE caller (game_main_loop's `jsr $8f02.l`), and no other way into any of the twelve.
# It walks the nineteen screen records project_actor_list left at WB_ACTOR_SCREEN_RECORDS and, for
# each one naming a sprite, reads that sprite's descriptor out of WB_RESOURCE_TABLE, clips it to the
# band, builds the register file the twelve are entered with, and calls one of them.
#
# WHAT MAKES THESE CASES DIFFERENT FROM THE TWELVE'S. A blitter case names its own entry registers;
# a pass case names only MEMORY — records, descriptors, WB_SCREEN_BACK — and every register is
# something the pass computed. So the model below is the pass's arithmetic followed by `model_blit`,
# and a case's write set is the UNION of the rectangles the records it seeded drew.
#
# NOTHING THE PASS READS IS IN THE SHIPPED IMAGE either: the screen records are filled per frame,
# WB_RESOURCE_TABLE is past the program's last byte and loaded from disk, and so is SPRITES.CRU. A
# case therefore seeds all three, keyed on the address as everything else here is.

PASS_NAME = "sprite_draw_pass"

# The screen-record array, and the descriptor table it indexes. Every one of these is read through
# `wb(...)`, so this battery and src/blit.c cannot disagree about a field's offset.
RECORDS = wb("ACTOR_SCREEN_RECORDS")
RECORDS_END = wb("ACTOR_SCREEN_RECORDS_END")
RECORD_BYTES = wb("ACTOR_SCREEN_RECORD_BYTES")
RECORD_COUNT = wb("ACTOR_SCREEN_RECORD_COUNT")
RECORD_X = wb("ACTOR_SCREEN_X")
RECORD_Y = wb("ACTOR_SCREEN_Y")
RECORD_SPRITE = wb("ACTOR_SCREEN_SPRITE")
SPRITE_HIDDEN = wb("ACTOR_SPRITE_HIDDEN")

RESOURCE_TABLE = wb("RESOURCE_TABLE")
RESOURCE_RECORD_BYTES = wb("RESOURCE_RECORD_BYTES")
DESC_SOURCE = wb("SPRITE_DESC_SOURCE")
DESC_WIDTH_CODE = wb("SPRITE_DESC_WIDTH_CODE")
DESC_HEIGHT = wb("SPRITE_DESC_HEIGHT")
DESC_X_OFFSET = wb("SPRITE_DESC_X_OFFSET")
DESC_Y_OFFSET = wb("SPRITE_DESC_Y_OFFSET")

SCREEN_BACK = wb("SCREEN_BACK")
LAST_ROW = wb("SPRITE_LAST_ROW")             # `cmpi.w #$9f,d1` and `move.w #$9f,d2`
RIGHT_CLIP_X = wb("SPRITE_RIGHT_CLIP_X")     # `cmp.w #$b0,d4`
SHIFT_MASK = wb("SPRITE_SHIFT_MASK")         # `andi.w #$f,d6`
SLOT_SHIFT = wb("BLIT_TABLE_SLOT_SHIFT")     # `lsl.w #2,d2`
WIDTH_CODE_MAX = wb("BLIT_WIDTH_CODE_MAX")
TABLE_ADDR_BY_SIDE = {MID: wb("BLIT_TABLE_MID"), LEFT: wb("BLIT_TABLE_LEFT"),
                      RIGHT: wb("BLIT_TABLE_RIGHT")}

# Which of d0..d5 the pass uses for what — include/blit.h's numbers, so a register renamed there
# fails here as a missing key rather than as a silently different assert.
WORK_REG = wb("SPRITE_WORK_REG")
Y_REG = wb("SPRITE_Y_REG")
WIDTH_REG = wb("SPRITE_WIDTH_REG")
ECHO_Y_REG = wb("SPRITE_ECHO_Y_REG")

# --- the encodings the pass adds ------------------------------------------------------------------
# `clr_w_dn`, `cmp_w_dn_dn`, `andi_w_dn` and the `asr.w`/`asl.w` pair MOVED INTO leaf.py when this
# battery became their third user (test_actor.py and test_map.py had spelt the first, second and
# fourth between them, test_map.py and test_scroll.py the third); `s8` above went the same way when
# test_sound.py's signed SFX id became its second reader and machine.h grew `sign_ext8` for the C.
# What is left below stands at ONE user apart from three that stand at two and say so in their own
# docstrings — `adda_w_imm_an` (also test_scroll.py), `cmpa_l_imm` (also test_actor.py) and
# `clr_l_dn` (also test_hud.py); this batch's STATUS.md section registers them as the next hoist.
#
# BATCH 39 TOOK THREE OF THIS FILE'S OWN. `addq_w_dn`, `ext_w_dn` and `adda_w_dn_an` are imported
# from leaf.py now. The third is why the other two went with it: leaf.py had gained its own
# `adda_w_dn_an` in the OPPOSITE operand order, and two encoders of one instruction under one name
# is the failure `adda_w_imm_an`'s docstring already warns about — each battery's byte pins pass
# either way, so nothing fails until the two files meet. leaf.py's is destination-first, which is
# the order this file's three call sites already used.

def movea_l_ind(reg, base):
    """`movea.l (An),Am` — how the pass loads a descriptor's source pointer and its blitter."""
    return opcode(0x2050 | (reg << 9) | base)


def add_w_d16_dn(reg, base, displacement):
    """`add.w d16(An),Dn` — how a descriptor's x/y offset reaches the record's own."""
    return opcode(0xd068 | (reg << 9) | base) + word(displacement)


def muls_w_dn_dn(destination, source):
    """`muls.w Dn,Dn` — a SIGNED 16x16 product into the whole 32-bit register, which is what makes
    the top clip's source step come out negative."""
    return opcode(0xc1c0 | (destination << 9) | source)


def suba_l_dn_an(reg, source):
    """`suba.l Dn,An` — and what then ADDS that step's magnitude to the source cursor."""
    return opcode(0x91c0 | (reg << 9) | source)


def adda_w_imm_an(reg, value):
    """`adda.w #imm,An` — the window origin inside a screen buffer. ALSO IN test_scroll.py, in the
    same DESTINATION-FIRST operand order (the two disagreed about it when this battery landed, which
    two encoders of one instruction can do silently — each one's own byte pins pass either way)."""
    return opcode(0xd0fc | (reg << 9)) + word(value)


def cmpa_l_imm(reg, value):
    """`cmpa.l #imm,An` — a LONGWORD compare, which is what ends the record walk. ALSO IN
    test_actor.py, whose own record walk ends the same way; this battery had it under a second name
    (`cmpa_l_imm_an`) until the review, and two names for one instruction is how two spellings of it
    stay invisible to each other."""
    return opcode(0xb1fc | (reg << 9)) + longword(value)


def jsr_ind(reg):
    """`jsr (An)` — the indirect call the three jump tables exist for."""
    return opcode(0x4e90 | reg)


# --- assembling the pass ---------------------------------------------------------------------------

def _sprite_pass_bytes():
    """All of $8f02, assembled from this battery's own statement of the walk.

    Built in the same pieces src/blit.c is built in, and every branch displacement comes out of the
    LENGTHS of those pieces — so a field offset, a threshold, a shift, a register or a skip that is
    wrong there is wrong in these bytes here.
    """
    read_sprite = (lea_abs_l(A4, RESOURCE_TABLE) + clr_w_dn(WORK_REG) + clr_w_dn(Y_REG)
                   + move_w_ind_dn(WORK_REG, A6, RECORD_SPRITE))
    descriptor = (mulu_w_imm_dn(WORK_REG, RESOURCE_RECORD_BYTES) + adda_w_dn_an(A4, WORK_REG)
                  + move_w_imm_dn(ROWS_REG, 0) + move_b_d16_dn(ROWS_REG, A4, DESC_HEIGHT)
                  + ext_w_dn(ROWS_REG) + movea_l_ind(A0, A4)
                  + move_w_ind_dn(Y_REG, A6, RECORD_Y) + add_w_d16_dn(Y_REG, A4, DESC_Y_OFFSET))

    # $8f68..$8fbc: the screen cursor, the table and the call.
    cursor = (move_w_dn_dn(ECHO_Y_REG, Y_REG)
              + movea_l_abs_w(A1, SCREEN_BACK) + adda_w_imm_an(A1, SCREEN_ORIGIN)
              + move_w_ind_dn(WORK_REG, A6, RECORD_X) + add_w_d16_dn(WORK_REG, A4, DESC_X_OFFSET)
              + move_w_dn_dn(X_REG, WORK_REG)
              + move_w_imm_dn(WIDTH_REG, 0) + move_b_d16_dn(WIDTH_REG, A4, DESC_WIDTH_CODE)
              + ext_w_dn(WIDTH_REG)
              + move_w_dn_dn(SHIFT_REG, WORK_REG) + andi_w_dn(SHIFT_REG, SHIFT_MASK)
              + andi_w_dn(WORK_REG, COLUMN_ROUND_DOWN) + asr_w_imm_dn(X_BYTE_SHIFT, WORK_REG)
              + asl_w_imm_dn(ROW_SHIFT_LOW, Y_REG) + add_w_dn_dn(WORK_REG, Y_REG)
              + asl_w_imm_dn(ROW_SHIFT_HIGH, Y_REG) + add_w_dn_dn(WORK_REG, Y_REG)
              + adda_w_dn_an(A1, WORK_REG))
    pick_left = lea_abs_l(A2, TABLE_ADDR_BY_SIDE[LEFT])
    pick_right = lea_abs_l(A2, TABLE_ADDR_BY_SIDE[RIGHT])
    draw = (cursor + lea_abs_l(A2, TABLE_ADDR_BY_SIDE[MID])
            + tst_w_dn(X_REG) + short_branch(BPL, len(pick_left)) + pick_left
            + cmp_w_imm_dn(X_REG, RIGHT_CLIP_X) + short_branch(BLT, len(pick_right)) + pick_right
            + lsl_w_imm_dn(SLOT_SHIFT, WIDTH_REG) + adda_w_dn_an(A2, WIDTH_REG)
            + movea_l_ind(A2, A2) + jsr_ind(A2))

    # $8f54..$8f66: the sprite starts inside the band, so the count is clamped to what is left of it.
    clamp = move_w_dn_dn(ROWS_REG, WIDTH_REG)
    bottom_tail = (move_w_imm_dn(WIDTH_REG, LAST_ROW) + sub_w_dn_dn(WIDTH_REG, Y_REG)
                   + cmp_w_dn_dn(WIDTH_REG, ROWS_REG) + short_branch(BGE, len(clamp)) + clamp)
    bottom = (cmpi_w_dn(Y_REG, LAST_ROW) + branch_over(BGT, len(bottom_tail) + len(draw))
              + bottom_tail)

    # $8f36..$8f52: it starts above the band, so the rows off the top come out of the count and the
    # source, and the y becomes zero.
    top_tail = (move_w_imm_dn(WORK_REG, 0) + move_b_d16_dn(WORK_REG, A4, DESC_WIDTH_CODE)
                + ext_w_dn(WORK_REG) + addq_w_dn(1, WORK_REG)
                + mulu_w_imm_dn(WORK_REG, CELL_BYTES) + muls_w_dn_dn(WORK_REG, Y_REG)
                + suba_l_dn_an(A0, WORK_REG) + clr_w_dn(Y_REG) + short_branch(BRA, len(bottom)))
    top = (add_w_dn_dn(ROWS_REG, Y_REG)
           + branch_over(BMI, len(top_tail) + len(bottom) + len(draw)) + top_tail)

    record = descriptor + short_branch(BPL, len(top)) + top + bottom + draw
    walk = (read_sprite + branch_over(BEQ, len(record)) + record
            + lea_d16(A6, RECORD_BYTES) + cmpa_l_imm(A6, RECORDS_END))
    return (lea_abs_l(A6, RECORDS) + walk + opcode(BLT) + backward_branch(len(walk)) + RTS)


SPRITE_PASS_BYTES = _sprite_pass_bytes()
SPRITE_PASS_LEN = 204               # stated rather than derived, so an assembly that lost a
                                    # piece shrinks the pin loudly (leaf.assert_batch_is_complete)


def test_the_sprite_pass_is_the_bytes_the_image_holds():
    """Every byte of $8f02, assembled from this battery's statement of the walk."""
    leaf.assert_entry_is(PASS_NAME, SPRITE_PASS_BYTES)


def test_the_sprite_pass_runs_up_to_the_first_blitter():
    """...and stops exactly where blit_clip_left_w2 starts, so "the pass is these 204 bytes" is a
    reading of the image and not a length someone chose. With the twelve's own tiling test above,
    $8f02..$989c is now accounted for byte by byte."""
    assert len(SPRITE_PASS_BYTES) == SPRITE_PASS_LEN
    assert leaf.entry_of(PASS_NAME) + SPRITE_PASS_LEN == FAMILY_START


def test_the_pass_geometry_is_what_the_numbers_say():
    """The constants include/blit.h adds, checked against the ones it already had.

    Each of these is a DERIVATION the header states in prose and declines to spell as an
    expression — the scraper only reads plain integers — so this is where the two are held equal.
    """
    # The record walk covers exactly the nineteen records, and the terminator is one past the last.
    assert RECORDS_END - RECORDS == RECORD_COUNT * RECORD_BYTES
    # The band's last row is one below the window the background blit fills. The header spells it as
    # the literal $9f its two instructions carry (test/layout.py scrapes plain integers only), so
    # this is where the two numbers are held equal.
    assert LAST_ROW == wb("BG_BLIT_SCANLINES") - 1
    # The right table is selected from the first x at which even the widest sprite reaches the edge.
    assert RIGHT_CLIP_X == SCREEN_EDGE_X - max(COLUMNS) * COLUMN_PIXELS
    # The two masks that split the screen x partition the word between them.
    assert SHIFT_MASK == COLUMN_PIXELS - 1
    assert COLUMN_ROUND_DOWN == WORD_MASK & ~SHIFT_MASK
    # ...and the halving turns a 16-pixel column into the eight bytes four planes hold it in.
    assert COLUMN_PIXELS >> X_BYTE_SHIFT == COLUMN_BYTES
    # The two `asl.w`s add up to one scanline.
    assert (1 << ROW_SHIFT_LOW) + (1 << (ROW_SHIFT_LOW + ROW_SHIFT_HIGH)) == SCREEN_LINE
    # A table slot is one longword, and there are four of them.
    assert 1 << SLOT_SHIFT == LONGWORD_LEN
    assert WIDTH_CODE_MAX == len(COLUMNS) - 1
    # ...and include/blit.h's three table addresses are ../names.txt's.
    assert TABLE_ADDR_BY_SIDE == TABLE_BY_SIDE


# --- the model ------------------------------------------------------------------------------------
# The pass's own arithmetic, written from the listing, followed by `model_blit` for the record it
# decided to draw. It walks a MUTABLE image so that each record sees what the previous one drew —
# the clip byte in particular, which one record writes and the next reads.

class PassCall(NamedTuple):
    """One handoff from the pass to one of the twelve: the width and clip case it picked, the entry
    row count it handed over, and what that blit may execute. A case reads these to say WHICH
    blitter a screen x reached rather than only that the pixels came out right."""
    columns: int
    side: str
    rows: int
    budget: int


def _model_pass_record(mem, regs, written, calls):
    """$8f0e..$8fbc for the record ``regs['a6']`` names. Every skip in the original is a return."""
    def put(reg, value):
        """One `.w` write into d0..d7: the low word replaced, the caller's own high half kept."""
        regs[f"d{reg}"] = set_low_word(regs[f"d{reg}"], value)

    record = regs["a6"]
    regs["a4"] = descriptor = RESOURCE_TABLE
    put(WORK_REG, 0)
    put(Y_REG, 0)

    sprite = leaf.u16(mem, record + RECORD_SPRITE)
    put(WORK_REG, sprite)
    if sprite == SPRITE_HIDDEN:
        return

    # `mulu.w #$14,d0` is a 32-bit product; `adda.w d0,a4` takes only its SIGN-EXTENDED low word.
    regs[f"d{WORK_REG}"] = (sprite * RESOURCE_RECORD_BYTES) & LONG_MASK
    regs["a4"] = descriptor = (descriptor + s16(regs[f"d{WORK_REG}"])) & LONG_MASK

    put(ROWS_REG, s8(mem[descriptor + DESC_HEIGHT]))
    source = descriptor + DESC_SOURCE
    regs["a0"] = int.from_bytes(bytes(mem[source:source + LONGWORD_LEN]), "big")

    y = s16(leaf.u16(mem, record + RECORD_Y) + leaf.u16(mem, descriptor + DESC_Y_OFFSET))
    put(Y_REG, y)
    if y < 0:
        rows = s16(regs[f"d{ROWS_REG}"] + y)
        put(ROWS_REG, rows)
        if rows < 0:
            return
        # (width code + 1) cells per row, times ten bytes, times the NEGATIVE y — so the `suba.l`
        # under it steps the source cursor FORWARD past the rows that fell off the top.
        cells = (s8(mem[descriptor + DESC_WIDTH_CODE]) + 1) & WORD_MASK
        clipped = s16(cells * CELL_BYTES) * y
        regs[f"d{WORK_REG}"] = clipped & LONG_MASK
        regs["a0"] = (regs["a0"] - clipped) & LONG_MASK
        y = 0
        put(Y_REG, 0)
    else:
        if y > LAST_ROW:
            return
        # The rows left in the band are built in d2 and that intermediate is NOT modelled: the width
        # code below overwrites d2 before any exit, so it is unobservable — see src/blit.c.
        rows_left = LAST_ROW - y
        if rows_left < s16(regs[f"d{ROWS_REG}"]):             # SIGNED: a negative count is KEPT
            put(ROWS_REG, rows_left)

    put(ECHO_Y_REG, y)                                        # `move.w d1,d5`, dead
    x = (leaf.u16(mem, record + RECORD_X) + leaf.u16(mem, descriptor + DESC_X_OFFSET)) & WORD_MASK
    put(WORK_REG, x)
    put(X_REG, x)
    width_code = s8(mem[descriptor + DESC_WIDTH_CODE])
    put(WIDTH_REG, width_code)
    put(SHIFT_REG, x & SHIFT_MASK)

    offset, row = _screen_offset(x, y)
    put(Y_REG, row)
    put(WORK_REG, offset)
    screen = int.from_bytes(bytes(mem[SCREEN_BACK:SCREEN_BACK + LONGWORD_LEN]), "big")
    regs["a1"] = (screen + SCREEN_ORIGIN + s16(offset)) & LONG_MASK

    # Both tests are signed and they run in this order, so a negative x reaches the left table and
    # stays there.
    side = LEFT if s16(x) < 0 else (RIGHT if s16(x) >= RIGHT_CLIP_X else MID)
    slot = (width_code << SLOT_SHIFT) & WORD_MASK
    put(WIDTH_REG, slot)
    assert 0 <= width_code <= WIDTH_CODE_MAX, (
        f"a descriptor with width code {width_code} would `jsr` through the longword past "
        f"blit_table_{side}, which this battery refuses to ask for")

    table = TABLE_ADDR_BY_SIDE[side] + s16(slot)
    regs["a2"] = int.from_bytes(bytes(mem[table:table + LONGWORD_LEN]), "big")

    columns = COLUMNS[width_code]
    width = WIDTHS[columns]
    entry_rows = regs[f"d{ROWS_REG}"] & WORD_MASK
    # A record whose x leaves no column on screen returns from its prelude WITHOUT entering a row
    # loop, so its count never reaches a `dbf` and the runaway refusal is not its to fail — what it
    # costs is the ladder alone. Scoped here rather than in `_blit_insns`, so that a case wanting an
    # off-screen record with a negative height is not blocked by a bound on rows nothing draws.
    enters_a_body = side == MID or clip_value(width, side, s16(x)) is not None
    calls.append(PassCall(columns, side, entry_rows,
                          _blit_insns(width, entry_rows) if enters_a_body else _INSNS_ENTRY))

    blit_writes, after = model_blit(mem, width, side, dict(regs))
    for addr, byte in blit_writes.items():
        mem[addr] = byte
        written[addr] = byte
    regs.update(after)


def model_sprite_pass(image, entry):
    """({address: final byte}, {register: final value}, [PassCall]) for one whole pass."""
    mem = bytearray(image)
    regs = dict(entry)
    written, calls = {}, []
    record = RECORDS
    while True:
        regs["a6"] = record
        _model_pass_record(mem, regs, written, calls)
        record = (record + RECORD_BYTES) & LONG_MASK
        regs["a6"] = record
        if record >= RECORDS_END:
            return written, regs, calls


# --- running one case -------------------------------------------------------------------------------
# A pass case states MEMORY: nineteen records, the descriptors they name, and the screen pointer.

class PassRegs(ctypes.Structure):
    """include/blit.h's `sprite_pass_regs` — a blitter's whole register file, plus the three address
    registers the walk itself uses."""
    _fields_ = [("blit", BlitRegs), ("record", ctypes.c_uint32),
                ("descriptor", ctypes.c_uint32), ("blitter", ctypes.c_uint32)]


PASS_FIELD_BY_REG = {"a6": "record", "a4": "descriptor", "a2": "blitter"}
PASS_STRUCT_REGS = STRUCT_REGS + list(PASS_FIELD_BY_REG)

_PASS_FN = leaf.bind(PASS_NAME, leaf.IMAGE_ARG + [ctypes.POINTER(PassRegs)])


def _pass_box():
    """A pass box: the blitter's own file lives in its `blit` member, the walk's three beside it."""
    box = PassRegs()
    return box, box.blit, [(box.blit, FIELD_BY_REG), (box, PASS_FIELD_BY_REG)]


# The straight line one record costs, generously — the dispatcher's own longest path is about thirty
# instructions. Doubled with everything else in `_pass_insn_cap`.
_PASS_INSNS_PER_RECORD = 40

# One filler over the descriptors a case may reach, keyed on the ADDRESS: a reconstruction reading
# the wrong field offset, or the wrong record, lands on a byte that is wrong FOR WHERE IT IS rather
# than on a zero. Wide enough for every index a case names and no wider — SPRITE_SOURCE sits above
# it and must not be overwritten.
DESCRIPTOR_SLOTS = 32
DESCRIPTOR_SALT = case_salt("descriptors")

# A descriptor a case does not otherwise care about: the narrowest width and a height that draws a
# couple of rows, under the sprite index a single-record case names.
PASS_COLUMNS = 3
PASS_HEIGHT = 5
PASS_MID_X = 0x40                    # a whole word in, and inside the window for every width
PASS_SPRITE = 1                      # `_run_one`'s one sprite, and the index most cases seed


def _seeded_bands():
    """Every band a pass case pokes, as (what, start, length).

    Stated once so that two claims can be read off it: that the bands do not overwrite each other
    (the filler's width against SPRITE_SOURCE is the tight one), and that an EXTRA descriptor
    planted wherever a wrapped cursor lands misses all of them.
    """
    return [("the screen records", RECORDS, RECORDS_END - RECORDS),
            ("the clip byte", CLIP_MASK, 1),
            ("the WB_SCREEN_BACK pointer", SCREEN_BACK, LONGWORD_LEN),
            ("the descriptor filler", RESOURCE_TABLE, DESCRIPTOR_SLOTS * RESOURCE_RECORD_BYTES),
            ("the sprite cells", SPRITE_SOURCE, SPRITE_BYTES),
            ("the screen band", SCREEN_BUFFERS[0], SCREEN_BYTES)]


def _assert_clear_of_the_seeded_image(what, base, length):
    """``base``..``base + length`` overlaps nothing the case seeds — which is what makes a poke
    placed by ARITHMETIC rather than by choice safe to place at all."""
    for name, start, size in _seeded_bands():
        assert base >= start + size or base + length <= start, (
            f"{what} at {base:#x}+{length} overlaps {name} at {start:#x}+{size}, so the case is "
            f"seeding over its own image")


def test_the_bands_a_pass_case_seeds_do_not_overwrite_each_other():
    """The seeding convention as a claim rather than as an arrangement that happens to hold. The
    tight one is the descriptor filler, whose DESCRIPTOR_SLOTS is chosen to stop short of
    SPRITE_SOURCE: a slot count large enough to reach it would silently blank the sprite every case
    draws from, and the cases would still agree — on an empty sprite."""
    bands = _seeded_bands()
    for index, (name, start, size) in enumerate(bands):
        for other, other_start, other_size in bands[index + 1:]:
            assert start >= other_start + other_size or start + size <= other_start, (
                f"{name} at {start:#x}+{size} overlaps {other} at {other_start:#x}+{other_size}")


def _record_bytes(x, y, sprite):
    return word(x) + word(y) + word(sprite)


def _records(*filled):
    """The nineteen screen records, ``filled`` being (slot, x, y, sprite) for the ones that are not
    blank — so a case states only the records it means and the rest are the hidden ones the pass
    skips."""
    out = [(0, 0, SPRITE_HIDDEN)] * RECORD_COUNT
    for slot, x, y, sprite in filled:
        out[slot] = (x, y, sprite)
    return out


def _descriptor(columns=PASS_COLUMNS, height=PASS_HEIGHT, x_offset=0, y_offset=0,
                source=SPRITE_SOURCE, width_code=None):
    """One descriptor, stated by COLUMN COUNT because that is what a case means. The width CODE the
    image holds is its index in COLUMNS; ``width_code`` overrides it for a case that wants to say
    what the byte holds rather than what it means."""
    return (source, COLUMNS.index(columns) if width_code is None else width_code,
            height, x_offset, y_offset)


def _descriptor_bytes(base, fields):
    """...as the twenty bytes at ``base``: the five fields the pass reads, over the same keyed
    filler the rest of the table carries, so the ten it does not read are not zeros."""
    source, width_code, height, x_offset, y_offset = fields
    out = bytearray(keyed_block(base, RESOURCE_RECORD_BYTES, DESCRIPTOR_SALT))
    out[DESC_SOURCE:DESC_SOURCE + LONGWORD_LEN] = longword(source)
    out[DESC_WIDTH_CODE] = width_code & 0xff
    out[DESC_HEIGHT] = height & 0xff
    out[DESC_X_OFFSET:DESC_X_OFFSET + WORD_LEN] = word(x_offset)
    out[DESC_Y_OFFSET:DESC_Y_OFFSET + WORD_LEN] = word(y_offset)
    return bytes(out)


def _pass_pokes(case, records, descriptors, screen, extra=None):
    """What a pass case seeds, on top of the sprite/screen/clip-byte trio every blitter case seeds.

    ``descriptors`` is keyed by SPRITE INDEX; ``extra`` by ADDRESS, for the one case whose index
    wraps the cursor to a slot the table's own filler does not cover. The order matters: the filler
    goes down before the descriptors that overwrite parts of it.
    """
    pokes = dict(_case_pokes(case))
    pokes[RECORDS] = b"".join(_record_bytes(*record) for record in records)
    pokes[RESOURCE_TABLE] = keyed_block(RESOURCE_TABLE, DESCRIPTOR_SLOTS * RESOURCE_RECORD_BYTES,
                                        DESCRIPTOR_SALT)
    for index, fields in descriptors.items():
        base = RESOURCE_TABLE + index * RESOURCE_RECORD_BYTES
        pokes[base] = _descriptor_bytes(base, fields)
    for base, fields in (extra or {}).items():
        pokes[base] = _descriptor_bytes(base, fields)
    pokes[SCREEN_BACK] = longword(screen)
    return pokes


def _pass_entry_registers(case, unwind=UNWIND_BASE):
    """The fifteen longwords a pass case is entered with, all of them GARBAGE.

    The pass has no argument: everything it reads is memory, so what a register comes back holding
    is either the pass's own arithmetic or — for a `.w` write — the caller's own high half. Seeding
    all fifteen is what makes both observable, and what makes "a3 is never touched" and "a2 is not
    touched unless something was drawn" say something. a5 is the one a case names, because it is the
    one the pass hands on and the left ladder unwinds.
    """
    salt = case_salt(case)

    def garbage(reg):
        return (leaf.keyed_byte(salt, reg) << 8) | leaf.keyed_byte(reg, salt)

    entry = {f"d{reg}": (garbage(reg) << 16) | garbage(reg + 8) for reg in range(8)}
    entry.update({f"a{reg}": (garbage(reg + 16) << 16) | garbage(reg + 24) for reg in range(7)})
    entry["a5"] = unwind
    return entry


def _pass_insn_cap(calls):
    """What a pass case may execute: the walk itself plus each blit's own budget."""
    return 2 * (RECORD_COUNT * _PASS_INSNS_PER_RECORD + sum(call.budget for call in calls))


def _pass_glue(entry):
    return _regs_glue(_pass_box, _PASS_FN, entry)


def _run_pass(case, records, descriptors, screen=SCREEN_BUFFERS[0], unwind=UNWIND_BASE, extra=None):
    """One pass case: the model, the oracle and the reconstruction over one seeded image.

    Returns (model writes, model registers, the blitter calls the model made, oracle info) once the
    three have been required to agree on the whole write set and on all fifteen registers.
    """
    pokes = _pass_pokes(case, records, descriptors, screen, extra)
    entry = _pass_entry_registers(case, unwind)
    image = make_image(pokes)
    expected_writes, expected_regs, calls = model_sprite_pass(image, entry)

    what = f"{PASS_NAME} {case}"
    info = leaf.run(PASS_NAME, _pass_glue(entry), merge_bands(expected_writes), what,
                    regs=dict(entry, _pokes=pokes), max_insns=_pass_insn_cap(calls))

    written = program_writes(info)
    assert written == expected_writes, (
        f"{what}: the original wrote {len(written)} bytes and the model {len(expected_writes)} — "
        f"first difference at {min(set(written) ^ set(expected_writes), default=-1):#x}")
    for reg in emu.REPORTED_REGS:
        assert info["regs"][reg] == expected_regs[reg], (
            f"{what}: the original left {reg}={info['regs'][reg]:#010x}, not the model's "
            f"{expected_regs[reg]:#010x}")
    for reg in PASS_STRUCT_REGS:
        assert info["ret"][reg] == expected_regs[reg], (
            f"{what}: the reconstruction left {reg}={info['ret'][reg]:#010x}, not the model's "
            f"{expected_regs[reg]:#010x}")
    return expected_writes, expected_regs, calls, info


def _run_one(case, x, y, descriptor, slot=0, **kwargs):
    """One record naming ONE descriptor, which is the shape most pass cases want.

    The sprite index is PASS_SPRITE throughout: what those cases vary is the geometry, not which
    slot of the table it came out of. A case with more than one record calls `_run_pass` itself, and
    that call is then the signal that the WALK is what the case is about.
    """
    return _run_pass(case, _records((slot, x, y, PASS_SPRITE)), {PASS_SPRITE: descriptor}, **kwargs)


def _drawn_rectangle(x, y, columns, rows, screen=SCREEN_BUFFERS[0]):
    """The bytes one record's blit covers: `rows` runs of the width's own bytes, a scanline apart."""
    dest = _dest_for(x, y, screen)
    return {dest + row * SCREEN_LINE + byte
            for row in range(rows) for byte in range(columns * COLUMN_BYTES)}


# --- the walk -----------------------------------------------------------------------------------

def test_the_pass_draws_nothing_when_no_record_names_a_sprite():
    """`move.w 4(a6),d0 / beq` on all nineteen: no descriptor is read, no pixel is drawn, and the
    walk still ends where it ends. d0 and d1 come back at zero because the two `clr.w`s sit AHEAD of
    that test, and a2 comes back at the caller's own value because `lea $989c.l,a2` does not."""
    case = "all-hidden"
    writes, regs, calls, _info = _run_pass(case, _records(), {})
    entry = _pass_entry_registers(case)

    assert writes == {} and calls == []
    assert regs["a6"] == RECORDS_END
    assert regs["a4"] == RESOURCE_TABLE
    assert regs["a5"] == UNWIND_BASE
    assert regs[f"d{WORK_REG}"] & WORD_MASK == 0 and regs[f"d{Y_REG}"] & WORD_MASK == 0
    for reg in ("a0", "a1", "a2", "a3"):
        assert regs[reg] == entry[reg] != 0, f"{reg} was touched by a pass that drew nothing"


def test_the_pass_visits_every_record_and_stops_at_the_end_of_the_array():
    """One drawn sprite in EVERY slot, including the last: nineteen rectangles, no twentieth, and
    the cursor stops at WB_ACTOR_SCREEN_RECORDS_END. A walk one record short or one long fails on
    the write set rather than on the pointer alone."""
    columns, rows = 2, 1
    # One row per slot, eight scanlines apart, all at the same x — so the nineteen rectangles are
    # disjoint and every one of them is inside the band and inside the middle table's x range.
    slots = [(slot, PASS_MID_X, slot * 8, 1) for slot in range(RECORD_COUNT)]
    writes, regs, calls, _info = _run_pass("every-slot", _records(*slots),
                                           {1: _descriptor(columns, height=rows - 1)})
    assert len(calls) == RECORD_COUNT
    assert regs["a6"] == RECORDS_END
    assert set(writes) == set().union(*(_drawn_rectangle(x, y, columns, rows)
                                        for _slot, x, y, _sprite in slots))


def test_a_pass_mixing_every_outcome_draws_only_what_survives():
    """One walk with all of it at once: hidden records, a top clip, a bottom clamp, a sprite past
    the bottom edge, one wholly off the left (which unwinds a5) and one wholly off the right (which
    does not), and three plain draws of different widths."""
    records = _records((0, PASS_MID_X, DEST_ROW, 1),                     # w2, plain
                       (2, PASS_MID_X + 0x20, 4, 2),                     # w4, plain
                       (5, PASS_MID_X, -4, 3),                           # w5, clipped at the top
                       (7, PASS_MID_X, LAST_ROW - 2, 1),                 # w2, clamped at the bottom
                       (9, PASS_MID_X, LAST_ROW + 1, 1),                 # past the bottom edge
                       (11, -COLUMN_PIXELS * 5, DEST_ROW, 3),            # wholly off the left
                       (13, SCREEN_EDGE_X - COLUMN_PIXELS, DEST_ROW, 2),  # wholly off the right
                       (18, 0x30, 0x20, 4))                              # w3, a sub-word shift
    descriptors = {1: _descriptor(2, height=3), 2: _descriptor(4, height=6),
                   3: _descriptor(5, height=9), 4: _descriptor(3, height=4, x_offset=7)}
    _writes, regs, calls, _info = _run_pass("mixed-walk", records, descriptors)

    assert [(call.columns, call.side) for call in calls] == [
        (2, MID), (4, MID), (5, MID), (2, MID), (5, LEFT), (4, RIGHT), (3, MID)]
    assert regs["a5"] == UNWIND_BASE - UNWIND_BYTES, (
        "only the wholly-off-LEFT record unwinds a5, and exactly once")


# --- the clip cases, reached by ARITHMETIC ---------------------------------------------------------
# Each of these states a screen x and lets the pass pick the table, which is the half batch 14 could
# not: the twelve were entered directly at the addresses the tables hold.

@pytest.mark.parametrize("columns", COLUMNS)
@pytest.mark.parametrize("side", SIDES)
def test_a_screen_x_reaches_the_clip_case_it_names(columns, side):
    """`tst.w d4 / bpl` then `cmp.w #$b0,d4 / blt`, both SIGNED and in that order."""
    x = {MID: PASS_MID_X, LEFT: -COLUMN_PIXELS, RIGHT: RIGHT_CLIP_X}[side]
    _writes, _regs, calls, _info = _run_one(f"table-w{columns}-{side}", x, DEST_ROW,
                                            _descriptor(columns))
    assert [(call.columns, call.side) for call in calls] == [(columns, side)]


@pytest.mark.parametrize("x,side", [(-1, LEFT), (0, MID), (RIGHT_CLIP_X - 1, MID),
                                    (RIGHT_CLIP_X, RIGHT)],
                         ids=["minus1", "zero", "below-b0", "at-b0"])
def test_the_two_table_thresholds_are_where_they_are(x, side):
    """Both boundaries from both sides: zero belongs to the middle table and $b0 to the right one,
    so an x one below either falls to its neighbour."""
    _writes, _regs, calls, _info = _run_one(f"threshold-{x:#x}", x, DEST_ROW, _descriptor())
    assert [call.side for call in calls] == [side]


def test_the_screen_x_is_the_record_and_the_descriptor_added():
    """`move.w (a6),d0 / add.w 8(a4),d0` — an x that is on screen in the record alone and off the
    LEFT once the descriptor's offset is added, so a reconstruction that dropped the field would
    reach the wrong table and not merely the wrong column."""
    x, offset = COLUMN_PIXELS, -COLUMN_PIXELS * 3
    _writes, _regs, calls, _info = _run_one("x-offset", x, DEST_ROW,
                                            _descriptor(x_offset=offset))
    assert [call.side for call in calls] == [LEFT]


def test_the_screen_y_is_the_record_and_the_descriptor_added():
    """...and `move.w 2(a6),d1 / add.w 10(a4),d1` the same way: a y inside the band in the record
    alone, and above it once the offset is added."""
    y, offset = 2, -6
    writes, _regs, calls, _info = _run_one("y-offset", PASS_MID_X, y,
                                           _descriptor(height=PASS_HEIGHT, y_offset=offset))
    columns, rows = PASS_COLUMNS, PASS_HEIGHT + (y + offset) + 1
    assert len(calls) == 1
    assert set(writes) == _drawn_rectangle(PASS_MID_X, 0, columns, rows), (
        "a top-clipped sprite starts at row 0")


# --- the top clip ----------------------------------------------------------------------------------

@pytest.mark.parametrize("columns", COLUMNS)
def test_the_top_clip_drops_rows_from_the_count_and_from_the_source(columns):
    """`add.w d1,d7` takes the rows above the band out of the count, and `muls.w d1,d0 / suba.l
    d0,a0` steps the source past exactly those rows.

    The source cursor is where the whole claim lands: it ends where it would have ended if nothing
    had been clipped, because the rows that were skipped were skipped IN THE DATA as well as on the
    screen. The drawn rectangle starting at row 0 is the other half.
    """
    above, height = 4, 12
    case = f"top-clip-w{columns}"
    writes, regs, calls, _info = _run_one(case, PASS_MID_X, -above,
                                          _descriptor(columns, height=height))
    cells = WIDTHS[columns].cells
    assert [call.rows for call in calls] == [height - above]
    assert regs["a0"] - SPRITE_SOURCE == (height + 1) * cells * CELL_BYTES, (
        "the source cursor did not end where an unclipped sprite of this height would have left it")
    assert set(writes) == _drawn_rectangle(PASS_MID_X, 0, columns, height - above + 1)


def test_a_sprite_wholly_above_the_band_is_skipped():
    """`bmi.w $8fbe`: the height taken away by the clip leaves the count negative, so the record is
    dropped before a screen address is ever built. Its neighbour still draws, which is what says the
    walk continued rather than stopped."""
    writes, regs, calls, _info = _run_pass(
        "above-band",
        _records((0, PASS_MID_X, -9, 1), (RECORD_COUNT - 1, PASS_MID_X, DEST_ROW, 2)),
        {1: _descriptor(height=4), 2: _descriptor(2, height=0)})
    assert [(call.columns, call.side) for call in calls] == [(2, MID)]
    assert set(writes) == _drawn_rectangle(PASS_MID_X, DEST_ROW, 2, 1)
    assert regs["a4"] == RESOURCE_TABLE + 2 * RESOURCE_RECORD_BYTES, (
        "the descriptor cursor belongs to the record that was DRAWN — the skipped one moved its "
        "own cursor first, and the `lea` at the top of the next record rebuilt it")


def test_a_skipped_record_still_leaves_the_cursor_it_read_its_descriptor_through():
    """...and where nothing rebuilds it, that cursor is what comes back.

    The skip is the same `bmi.w $8fbe`, but in the LAST slot: no record follows to run
    `lea $248d8.l,a4` again, so a4 at the `rts` is the SKIPPED record's own — moved by
    `mulu.w #$14,d0 / adda.w d0,a4` BEFORE the height was ever looked at. d0 holds that same
    32-bit product, which is the other half of saying the cursor moved and not merely that it was
    left alone. Every other skipping case in this file sits in slot 0, where the next record's `lea`
    hides the difference.
    """
    height, above = 4, 9                              # so the clip leaves the count negative
    writes, regs, calls, _info = _run_one("skip-cursor", PASS_MID_X, -above,
                                          _descriptor(height=height), slot=RECORD_COUNT - 1)
    assert writes == {} and calls == []
    assert regs["a4"] == RESOURCE_TABLE + PASS_SPRITE * RESOURCE_RECORD_BYTES, (
        "the skipped record's descriptor cursor was not moved before the skip, or was rebuilt")
    assert regs[f"d{WORK_REG}"] == PASS_SPRITE * RESOURCE_RECORD_BYTES, (
        "`mulu.w #$14,d0` writes the whole 32-bit register, and the skip leaves it there")


def test_the_top_clip_at_exactly_one_row_left_draws_that_row():
    """The boundary of the same `bmi`: a count that comes out at zero is one row, not none."""
    height, above = 6, 6
    writes, _regs, calls, _info = _run_one("top-clip-edge", PASS_MID_X, -above,
                                           _descriptor(height=height))
    assert [call.rows for call in calls] == [0]
    assert set(writes) == _drawn_rectangle(PASS_MID_X, 0, PASS_COLUMNS, 1)


# --- the bottom clamp --------------------------------------------------------------------------------

@pytest.mark.parametrize("y", [0, 1, LAST_ROW - 1, LAST_ROW])
def test_the_band_runs_from_zero_to_the_last_row(y):
    """Both edges of `cmpi.w #$9f,d1 / bgt` and of the clamp under it: a sprite at the last row
    draws exactly one row of itself, and one at row 0 draws all of itself."""
    height = 8
    writes, _regs, calls, _info = _run_one(f"band-y{y}", PASS_MID_X, y,
                                           _descriptor(height=height))
    rows = min(height, LAST_ROW - y) + 1
    assert [call.rows for call in calls] == [rows - 1]
    assert set(writes) == _drawn_rectangle(PASS_MID_X, y, PASS_COLUMNS, rows)


def test_a_sprite_below_the_band_is_skipped():
    """One row past the last: `bgt.w $8fbe`, and nothing is drawn at all."""
    writes, _regs, calls, _info = _run_one("below-band", PASS_MID_X, LAST_ROW + 1,
                                           _descriptor())
    assert writes == {} and calls == []


def test_the_clamp_keeps_the_shorter_of_the_two_counts():
    """`cmp.w d7,d2 / bge`: a sprite that fits is not clamped and one that does not is, both at the
    same y, so what the case pins is the compare and not the arithmetic either side of it."""
    y = LAST_ROW - 4
    for height, expected in ((2, 2), (40, 4)):
        _writes, _regs, calls, _info = _run_one(f"clamp-h{height}", PASS_MID_X, y,
                                                _descriptor(height=height))
        assert [call.rows for call in calls] == [expected]


# --- the descriptor cursor ---------------------------------------------------------------------------

def _wrapped_descriptor_index(target_low_word):
    """The smallest sprite index whose `mulu.w #$14` product OVERFLOWS a word and leaves
    ``target_low_word`` in its low half — stated as a search rather than as a number, so the case
    says WHAT it wants of the index instead of asserting a constant back to itself."""
    for index in range(1, WORD_MASK + 1):
        product = index * RESOURCE_RECORD_BYTES
        if product > WORD_MASK and product & WORD_MASK == target_low_word:
            return index
    raise AssertionError(f"no sprite index reaches a low word of {target_low_word:#x}")


WRAP_FORWARD = 0x4000               # a product past 16 bits whose low word is still positive
WRAP_BACKWARD = 0x8c00              # ...and one whose low word has bit 15 set, so the cursor moves
                                    # BACKWARDS off the front of the table


@pytest.mark.parametrize("low_word", [WRAP_FORWARD, WRAP_BACKWARD],
                         ids=["forward", "backward"])
def test_a_large_sprite_index_wraps_the_descriptor_cursor(low_word):
    """`mulu.w #$14,d0` builds a 32-bit product and `adda.w d0,a4` takes only its SIGN-EXTENDED LOW
    WORD, so an index whose product does not fit in a word does not walk off the table — it lands
    somewhere in +-32 KB of it, and for half the range that is BEHIND it.

    The descriptor is seeded where the arithmetic says, so a reconstruction that used the whole
    product, or the unsigned low word, reads a descriptor that is not there. WHERE that is, is the
    arithmetic's business and not the case's: the backward one lands 29 KB below the table, inside
    bg_tile_bitmaps, which nothing here reads — so the case says only that it misses everything the
    case itself seeded, rather than choosing an address and calling it free.
    """
    index = _wrapped_descriptor_index(low_word)
    base = (RESOURCE_TABLE + s16(low_word)) & LONG_MASK
    _assert_clear_of_the_seeded_image("the wrapped descriptor", base, RESOURCE_RECORD_BYTES)
    columns = 4
    # The LAST slot, because `lea $248d8.l,a4` runs again for every record after it: a4 at the `rts`
    # is the cursor of the last record the walk touched, drawn or not.
    writes, regs, calls, _info = _run_pass(
        f"wrap-{low_word:#x}", _records((RECORD_COUNT - 1, PASS_MID_X, DEST_ROW, index)), {},
        extra={base: _descriptor(columns, height=1)})
    assert regs["a4"] == base
    assert [(call.columns, call.side) for call in calls] == [(columns, MID)]
    assert set(writes) == _drawn_rectangle(PASS_MID_X, DEST_ROW, columns, 2)


def test_the_descriptor_cursor_is_rebuilt_from_the_table_base_every_record():
    """`lea $248d8.l,a4` sits INSIDE the loop, so one record's index cannot carry into the next.
    Two records naming the same sprite must therefore read the same descriptor and draw the same
    shape — where a cursor that accumulated would send the second one 20 bytes further on."""
    columns, height = 5, 2
    records = _records((0, PASS_MID_X, 0x10, 4), (RECORD_COUNT - 1, PASS_MID_X, 0x40, 4))
    writes, regs, calls, _info = _run_pass("cursor-rebuilt", records,
                                           {4: _descriptor(columns, height=height)})
    assert regs["a4"] == RESOURCE_TABLE + 4 * RESOURCE_RECORD_BYTES
    assert [(call.columns, call.side) for call in calls] == [(columns, MID)] * 2
    assert set(writes) == (_drawn_rectangle(PASS_MID_X, 0x10, columns, height + 1)
                           | _drawn_rectangle(PASS_MID_X, 0x40, columns, height + 1))


# --- what the pass hands the twelve --------------------------------------------------------------------

@pytest.mark.parametrize("shift", range(COLUMN_PIXELS))
def test_the_sub_word_shift_is_the_low_nibble_of_the_screen_x(shift):
    """`andi.w #$f,d6` — every one of the sixteen, each landing the sprite one pixel further into
    the same 16-pixel column, and the drawn rectangle staying where the rounded x put it."""
    x = PASS_MID_X + shift
    writes, regs, _calls, _info = _run_one(f"shift-{shift}", x, DEST_ROW, _descriptor(height=0))
    assert regs[f"d{SHIFT_REG}"] & WORD_MASK == shift
    assert set(writes) == _drawn_rectangle(x, DEST_ROW, PASS_COLUMNS, 1)


def test_a_negative_screen_x_steps_the_cursor_back_before_the_window():
    """`asr.w #1,d0` is SIGNED, so a sprite hanging off the left edge is drawn from an address
    BELOW the window's origin — which is also why the left ladder has anything left to clip.

    A whole column below it, here, and the prelude then steps over exactly that column: so the one
    column this width has left lands ON the origin, out of a cursor that was pointed COLUMN_BYTES
    under it. Both halves are named, because the clip is what makes the step-back invisible in the
    pixels — read the write set alone and a cursor that had not been stepped back looks the same.
    An UNSIGNED shift would put the cursor 32 KB the other way instead.
    """
    x = -COLUMN_PIXELS
    writes, _regs, calls, _info = _run_one("negative-x", x, DEST_ROW, _descriptor(2, height=0))
    assert [call.side for call in calls] == [LEFT]

    origin = _dest_for(0, DEST_ROW, SCREEN_BUFFERS[0])
    drawn = set(writes) - {CLIP_MASK}
    assert _dest_for(x, DEST_ROW, SCREEN_BUFFERS[0]) + COLUMN_BYTES == origin
    assert drawn and min(drawn) == origin, (
        f"the drawn column starts at {min(drawn, default=-1):#x}, not at the window origin "
        f"{origin:#x} the stepped-back cursor and the skipped column add back up to")


@pytest.mark.parametrize("screen", SCREEN_BUFFERS, ids=[f"screen_{s:05x}" for s in SCREEN_BUFFERS])
def test_the_pass_draws_into_whichever_buffer_screen_back_names(screen):
    """`movea.l $750.w,a1` — the destination comes out of memory, so the same walk draws into the
    other buffer when WB_SCREEN_BACK says so."""
    writes, _regs, _calls, _info = _run_one(f"buffer-{screen:#x}", PASS_MID_X, DEST_ROW,
                                            _descriptor(4, height=2), screen=screen)
    assert set(writes) == _drawn_rectangle(PASS_MID_X, DEST_ROW, 4, 3, screen=screen)


def test_every_sprite_wholly_off_the_left_takes_six_more_off_a5():
    """a5 passes through the pass untouched and each wholly-off-left record's prelude takes
    WB_BLIT_UNWIND_BYTES off it, so the accumulation over a walk is observable output — and it is
    the only thing in the whole family that carries state from one record to the next."""
    off_left = [(slot, -COLUMN_PIXELS * 6, DEST_ROW, 1) for slot in range(4)]
    writes, regs, calls, _info = _run_pass("unwind-accumulates", _records(*off_left),
                                           {1: _descriptor(5, height=1)})
    assert len(calls) == len(off_left)
    assert writes == {}, "a sprite wholly off the left draws nothing, not even the clip byte"
    assert regs["a5"] == UNWIND_BASE - len(off_left) * UNWIND_BYTES


def test_the_dead_y_copy_is_left_in_d5():
    """`move.w d1,d5` at $8f68, written by the pass and read by nothing — not here and not in any of
    the twelve.

    It is observable through ONE kind of record: a sprite wholly off screen, whose prelude returns
    without touching a data register at all, so the pass's own write is the last thing d5 saw.
    Every other record's blitter walks d5 as part of its source window and the copy is buried. Both
    off-screen arms are run, because the LEFT one also unwinds a5 and the right one does not.
    """
    y = 0x33
    for side, x in ((LEFT, -COLUMN_PIXELS * 6), (RIGHT, SCREEN_EDGE_X - COLUMN_PIXELS)):
        _writes, regs, calls, _info = _run_one(f"dead-d5-{side}", x, y, _descriptor(3, height=2))
        assert [call.side for call in calls] == [side]
        assert regs[f"d{ECHO_Y_REG}"] & WORD_MASK == y, (
            f"the {side} off-screen arm did not leave the pass's own d5 behind")


def test_the_pass_leaves_the_blitter_it_last_called_in_a2():
    """`movea.l (a2),a2 / jsr (a2)`: the register the call went through is one of the fifteen the
    caller gets back, and it holds the ENTRY ADDRESS of one of the twelve — read out of the image's
    own table, which is what makes src/blit.c's dispatch by width code a reading of it."""
    columns, side = 4, RIGHT
    x = RIGHT_CLIP_X
    _writes, regs, _calls, _info = _run_one("blitter-in-a2", x, DEST_ROW,
                                            _descriptor(columns, height=0))
    assert regs["a2"] == leaf.entry_of(blitter_name(columns, side))


# --- the negative height, which is this batch's headline ------------------------------------------
# The height is a BYTE the pass `ext.w`s, so a descriptor may ask for a negative number of rows. The
# top clip cannot pass one on — its own `bmi` skips the record — but the BOTTOM CLAMP can: it is
# `cmp.w d7,d2 / bge` against a rows-left count that is never negative, so it keeps a negative d7
# rather than clamping it. That count reaches a blitter, and what happens there is the width's.

NEGATIVE_HEIGHTS = (0xff, 0xfe, 0x80)      # -1, -2, and the deepest a signed byte reaches


@pytest.mark.parametrize("height", NEGATIVE_HEIGHTS, ids=[f"{h:#x}" for h in NEGATIVE_HEIGHTS])
def test_a_negative_height_reaches_a_guarded_body_which_refuses_it(height):
    """The whole handoff, end to end, through the ONE width whose body guards its row count.

    `$9594`'s `addq.w #1,d7 / tst.w d7 / beq / bmi` refuses every count that is not positive, so
    this draws nothing and comes back with the counter at whatever the bump left — 0 for -1 and the
    bumped value for the other two, which is how the two exits are told apart. The record after it
    still draws, so what the case shows is that the pass CARRIED ON rather than that it crashed.
    """
    records = _records((0, PASS_MID_X, DEST_ROW, 1), (1, PASS_MID_X, 0x10, 2))
    descriptors = {1: _descriptor(GUARDED_COLUMNS, height=height), 2: _descriptor(2, height=0)}
    writes, regs, calls, _info = _run_pass(f"negative-height-{height:#x}", records, descriptors)

    assert [(call.columns, call.rows) for call in calls] == [
        (GUARDED_COLUMNS, height | (WORD_MASK ^ 0xff)), (2, 0)]
    assert set(writes) == _drawn_rectangle(PASS_MID_X, 0x10, 2, 1), (
        "the guarded body drew something, or the record after it did not")
    assert regs["d7"] & WORD_MASK == 0, "the LAST record's own count, which was a proper one"


def test_the_bottom_clamp_keeps_a_negative_count_rather_than_clamping_it():
    """The reading the case above rests on, stated on its own: the clamp's compare is SIGNED and the
    rows left in the band are never negative, so `bge` is always taken and d7 survives intact. The
    model is the third statement of it, and the oracle is the referee."""
    for y in (0, LAST_ROW):
        _writes, _regs, calls, _info = _run_one(f"negative-kept-y{y}", PASS_MID_X, y,
                                                _descriptor(GUARDED_COLUMNS, height=0xff))
        assert [call.rows for call in calls] == [WORD_MASK], (
            f"at y={y} the clamp changed a negative row count")


def test_the_top_clip_can_never_hand_on_a_negative_count():
    """...and the other path cannot: `add.w d1,d7 / bmi` drops the record instead.

    Stated over EVERY height a signed byte can hold, against a y above the band: the model says
    which of them reach a blitter and with what, and the claim is that none of those counts is
    negative. Three of them are then run under the oracle — the deepest height, the last one that
    is dropped and the first one that is not — so the reading is differentially anchored at its own
    boundary rather than only in Python.
    """
    above = 3
    reached = {height: s16(height - above) for height in range(-0x80, 0x80)
               if s16(height - above) >= 0}
    assert reached and all(rows >= 0 for rows in reached.values())
    assert min(reached) == above, "the first height that survives a clip of three rows is three"

    for height in (-0x80, above - 1, above):
        _writes, _regs, calls, _info = _run_one(f"top-negative-{height:#x}", PASS_MID_X, -above,
                                                _descriptor(GUARDED_COLUMNS, height=height))
        assert [call.rows for call in calls] == ([] if height < above else [0]), (
            f"height {height:#x} above the band reached the wrong count")


# The one input that reaches the 65,536-row `dbf`, and the only case in this file that runs it.
RUNAWAY_HEIGHT = 0xff
RUNAWAY_COLUMNS = 3
RUNAWAY_INSN_CAP = 12_000_000       # measured: 4,653,254, and the analytic bound is 6.1 M
# WHERE THE RUNAWAY IS POINTED, and why it is not a screen buffer. 65,536 rows is 10 MB of screen
# cursor, so a runaway starting anywhere inside the image walks THROUGH the band the oracle keeps
# its own machine stack in and past the end of the image — and one row landing on the sentinel
# return address would leave the "original" being compared against a run that had been derailed by
# its own output. Pointed one byte past the image instead, every row of it is dropped by the same
# guard on both sides, and what the case pins is the CONTROL FLOW: that all 65,536 rows ran.
RUNAWAY_SCREEN = loader.IMAGE_SIZE


def test_a_negative_height_runs_a_wider_body_away():
    """THE RUNAWAY IS REACHABLE BY DATA, and this is the case that runs it.

    A descriptor with a negative height and a y inside the band hands a width whose body does not
    guard its count an entry d7 of $ffff, and `dbf` then draws the whole 16-bit range of rows:
    RUNAWAY_ROWS of them over 4.65 M instructions. The source cursor and the screen cursor are what
    say so, and they say it to the row.

    Both sides survive the walk because both bound their accesses the same way — the oracle's shim
    by construction, src/blit.c through `blit_read_word`/`blit_write_word`, which batch 14 added for
    exactly this. Here that guard is the whole output: the destination is past the end of the image
    (see RUNAWAY_SCREEN) so all 65,536 rows are dropped, and a reconstruction that walked a host
    pointer instead would smash the ctypes buffer rather than agree.

    WHAT THIS CASE DOES NOT PIN. Not the PIXELS of a runaway — nothing can, since the only way to
    make it draw is to point it into the image and let it march over the harness's own stack. The
    per-row drawing is pinned to exhaustion by the twelve's own cases; what is new here is the
    count. And it is two implementations agreeing rather than three: `model_sprite_pass` is not run,
    because 65,536 rows of Python cost tens of seconds against the machines' three.

    WHETHER THE GAME'S OWN DATA REACHES IT is NOT establishable from the image — the descriptors are
    in a table loaded from disk past the program's last byte. Reachable by data, unpinned in fact.
    """
    case = "runaway"
    width = WIDTHS[RUNAWAY_COLUMNS]
    pokes = _pass_pokes(case, _records((0, PASS_MID_X, DEST_ROW, 1)),
                        {1: _descriptor(RUNAWAY_COLUMNS, height=RUNAWAY_HEIGHT)}, RUNAWAY_SCREEN)
    entry = _pass_entry_registers(case)
    # `poison` off: the run writes nothing, so there is no output to invert and nothing to attribute
    # — and the pass would be run twice more for it.
    diffs, info = harness.differential(leaf.entry_of(PASS_NAME), dict(entry, _pokes=pokes),
                                       _pass_glue(entry), max_insns=RUNAWAY_INSN_CAP, poison=False)
    assert not diffs, f"{PASS_NAME} {case}\n{harness.report(diffs)}"

    dest = _dest_for(PASS_MID_X, DEST_ROW, RUNAWAY_SCREEN)
    assert program_writes(info) == {}, (
        "a destination past the end of the image should leave every row dropped")
    assert info["regs"]["a0"] == SPRITE_SOURCE + RUNAWAY_ROWS * width.cells * CELL_BYTES, (
        "the source cursor does not say RUNAWAY_ROWS rows were drawn")
    assert info["regs"]["a1"] == dest + RUNAWAY_ROWS * SCREEN_LINE, (
        "...and neither does the screen cursor")
    assert info["regs"]["d7"] & WORD_MASK == WORD_MASK, "a `dbf` body exits with its counter at -1"
    assert info["regs"]["a6"] == RECORDS_END and info["regs"]["a5"] == UNWIND_BASE

    for reg in PASS_STRUCT_REGS:
        assert info["ret"][reg] == info["regs"][reg], (
            f"the reconstruction left {reg}={info['ret'][reg]:#010x} where the original left "
            f"{info['regs'][reg]:#010x}")


def test_the_battery_refuses_a_width_code_outside_the_table():
    """A descriptor whose width code is not 0..WB_BLIT_WIDTH_CODE_MAX `jsr`s through the longword
    past the four-entry table, which nothing here can stand in for — src/blit.c returns instead. So
    the refusal is stated as a case rather than left to whichever assert happened to fire.

    IT IS ALSO WHY `ext.w d2` IS NOT PINNED, which this states rather than leaves to the mutation
    sweep to discover: the sign extension only changes a byte with bit 7 set, and every such byte is
    a width code outside the table. So no case that RUNS can tell the signed reading from the
    unsigned one — the `ext.w` is pinned as an INSTRUCTION by the entry pin and reproduced from the
    listing, and its effect is unreachable. Unreachable is all this battery can say: it is stated
    here and in src/blit.c, and there is no assertion to be had, since the width codes that would
    tell the two readings apart are exactly the ones refused above.
    """
    for width_code in (-1, WIDTH_CODE_MAX + 1, 0x7f, -0x80):
        pokes = _pass_pokes("bad-width", _records((0, PASS_MID_X, DEST_ROW, 1)),
                            {1: _descriptor(width_code=width_code)}, SCREEN_BUFFERS[0])
        with pytest.raises(AssertionError, match="refuses to ask for"):
            model_sprite_pass(make_image(pokes), _pass_entry_registers("bad-width"))


# --- a sweep over the pass's own geometry -----------------------------------------------------------
# Sharded per the recipe in ../../../buggyboy/recreate/README.md: one stream, generated in full by every
# worker and RUN by the one whose chunk owns the iteration.
#
# The GEOMETRY is enumerated rather than drawn — width x clip case x band position is every
# combination that changes which arm of which routine runs — and what stays random inside each
# combination is the sub-word shift, the height and the exact row.

PASS_FUZZ_CHUNKS = 4
BANDS = ("above", "top", "middle", "bottom", "below")
PASS_MAX_HEIGHT = 12


def _pass_fuzz_cases():
    rng = random.Random(0x8F02)
    combinations = [(columns, side, band)
                    for columns in COLUMNS for side in SIDES for band in BANDS]
    for index, (columns, side, band) in enumerate(combinations):
        height = rng.randrange(0, PASS_MAX_HEIGHT + 1)
        shift = rng.randrange(0, COLUMN_PIXELS)
        if side == MID:
            x = rng.randrange(0, RIGHT_CLIP_X - COLUMN_PIXELS)
        elif side == LEFT:
            x = -rng.randrange(1, COLUMN_PIXELS * columns + COLUMN_PIXELS)
        else:
            x = rng.randrange(RIGHT_CLIP_X, SCREEN_EDGE_X)
        y = {"above": -rng.randrange(1, PASS_MAX_HEIGHT + 2),
             "top": 0,
             "middle": rng.randrange(1, LAST_ROW - PASS_MAX_HEIGHT),
             "bottom": rng.randrange(LAST_ROW - PASS_MAX_HEIGHT, LAST_ROW + 1),
             "below": LAST_ROW + rng.randrange(1, 0x40)}[band]
        yield index, columns, side, (x & ~SHIFT_MASK) | shift, y, height


PASS_FUZZ_CASES = len(list(_pass_fuzz_cases()))


@pytest.mark.parametrize("chunk", range(PASS_FUZZ_CHUNKS))
def test_a_sweep_of_the_pass_over_every_width_clip_case_and_band(chunk):
    """All four widths against all three clip cases against all five ways a sprite can meet the
    band, at a shift, a height and a row each case draws for itself."""
    for index, columns, side, x, y, height in _pass_fuzz_cases():
        if index % PASS_FUZZ_CHUNKS != chunk:
            continue
        _run_one(f"pass-sweep-{index}", x, y, _descriptor(columns, height=height),
                 slot=index % RECORD_COUNT)


def test_the_pass_sweep_covers_every_width_clip_case_and_band():
    """The enumeration says what it covers, so this is what makes that a reading of the list rather
    than of its docstring — and what fails if a chunk's slice ever stops partitioning it.

    The BAND a case lands in is not carried out of the generator (it is a y), so it is recovered
    here from that y — which also checks that each band's own range puts the sprite where its name
    says, and that the five ranges do not overlap.
    """
    def band_of(y):
        if y < 0:
            return "above"
        if y > LAST_ROW:
            return "below"
        if y == 0:
            return "top"
        return "middle" if y < LAST_ROW - PASS_MAX_HEIGHT else "bottom"

    covered = {(columns, side, band_of(y))
               for _index, columns, side, _x, y, _height in _pass_fuzz_cases()}
    assert covered == {(columns, side, band) for columns in COLUMNS for side in SIDES
                       for band in BANDS}
    assert len(covered) == PASS_FUZZ_CASES, "the sweep runs a combination more than once"
    sharded = sum(1 for index, *_rest in _pass_fuzz_cases() for chunk in range(PASS_FUZZ_CHUNKS)
                  if index % PASS_FUZZ_CHUNKS == chunk)
    assert sharded == PASS_FUZZ_CASES, "the chunks do not partition the sweep"
