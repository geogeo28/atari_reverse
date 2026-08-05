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

KNOWINGLY NOT PINNED
  * THE 65,537-ROW `dbf`. The three wider bodies decrement AFTER drawing, so an entry d7 of $ffff
    draws 65,537 rows and walks 10 MB of screen. Reproduced by construction in src/blit.c and left
    unreached: the sprite pass hands d7 a sprite HEIGHT read from a byte and then clamps it against
    the screen ($8f24..$8f66), so the count it produces is small and non-negative. Not reached by
    accident either — `_insn_cap` REFUSES any case whose entry count would run it, which is a
    statement of the same reading (`test_the_battery_refuses_to_ask_a_wider_body_for_those_counts`).
    The two-column bodies' own guard IS reached, from both ends
    (`test_the_two_column_bodies_refuse_*`).
  * WHOSE POINTER `subq.w #6,a5` UNWINDS. Six bytes is one WB_ACTOR_SCREEN_RECORDS record, but the
    sprite pass at $8f02 walks that array in a6 and never touches a5, so the caller this rewinds is
    not established. The arithmetic is pinned (including that it is a LONGWORD subtract); what it
    MEANS is not.
  * A WIDTH CODE OUTSIDE 0..3, and the dispatcher generally. $8f02 is not part of this batch: these
    twelve are entered directly, at the addresses the three jump tables hold, and those tables are
    pinned against ../names.txt rather than exercised.
  * THE SPRITE PASS'S OWN SCREEN ARITHMETIC. `_dest_for` mirrors it so that cases land where the
    game would put them, but nothing here proves it — that belongs to $8f02's own batch.
"""
import ctypes
import random

import pytest

import harness
import leaf
from harness import make_image
from layout import wb
from leaf import (RTS, backward_branch, branch_over, case_salt, keyed_block, lea_d16, longword,
                  merge_bands, move_b_imm_abs_l, move_w_postinc_dn, opcode, program_writes,
                  rotate_left32, rotate_right32, s16, set_low_word, swap_dn, tst_w_dn, word)

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
# clips against. d0..d5 are the scratch window and are addressed by index. The x register is the one
# of them include/blit.h has to name (it is scratch[4] under the body), so it is read from there.
A0, A1, A5 = 0, 1, 5
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

def cmp_w_imm_dn(reg, value):
    """`cmp.w #imm,Dn` — every clip threshold in the family. ALSO IN test_actor.py."""
    return opcode(0xb07c | (reg << 9)) + word(value)


def move_l_imm_dn(reg, value):
    """`move.l #imm,Dn` — the all-ones a mask word is moved into. ALSO IN test_stage.py."""
    return opcode(0x203c | (reg << 9)) + longword(value)


def clr_l_dn(reg):
    """`clr.l Dn` — the whole longword, which is what leaves a plane's wrapped half at zero."""
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


def addq_w_dn(amount, reg):
    """`addq.w #n,Dn`. ALSO IN test_map.py."""
    return opcode(0x5040 | ((amount & 7) << 9) | reg)


def subq_w_an(amount, reg):
    """`subq.w #n,An` — a WORD mnemonic over a 32-bit operation, which is the whole point of
    `test_the_unwind_is_a_longword_subtract`."""
    return opcode(0x5148 | ((amount & 7) << 9) | reg)


# The condition fields, as the whole opcode word of a WORD-displacement branch. The SHORT forms take
# their displacement in the low byte of the same word.
BRA, BEQ, BNE, BMI, BLT, BGE = 0x6000, 0x6700, 0x6600, 0x6b00, 0x6d00, 0x6c00
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

# `adda.w #$1420,a1` in the sprite pass at $8f6e: where the visible window starts inside a screen
# buffer. Context for `_dest_for`, not a claim this batch proves.
SCREEN_ORIGIN = wb("BG_BLIT_SCREEN_ORIGIN")
DEST_ROW = 60                       # mid-screen, with room above and below for any of these rows
COLUMN_ROUND_DOWN = 0xfff0          # `andi.w #$fff0,d0`: the x, down to a whole 16-pixel column

# Neither the fully-off-screen arm nor an unclipped body touches a5, so a case that seeded it as
# zero could not tell "unchanged" from "cleared".
UNWIND_BASE = 0x00012345

# blit_clip_mask as a case finds it: NO column drawn. An unclipped body that read the byte would
# blit nothing, and a clipped one whose prelude failed to write it would too.
CLIP_MASK_SEED = 0

# What a run is allowed to execute, from the geometry: per row, a load per cell, a draw (and in a
# clipped body a `btst`) per column, and the `lea`/`dbf` that close it. Doubled, so the cap fails a
# run that fell into the 65,537-row `dbf` rather than predicting the exact count.
_INSNS_PER_CELL = 25
_INSNS_PER_COLUMN = 13
_INSNS_PER_ROW = 4
_INSNS_ENTRY = 32

# No case here draws more rows than this. The bound is on the BATTERY, not on the game: a case that
# asked for the 65,537-row `dbf` would otherwise be given a cap large enough to run it.
MAX_CASE_ROWS = 64
RUNAWAY_ROWS = WORD_MASK + 2        # what an entry count of $ffff draws on a `dbf` body: 65,537


def _rows_drawn(width, rows):
    """How many rows this entry count draws.

    d7 + 1, and the two shapes part company on the two ways that can fail to be a small number. A
    two-column body BUMPS AND TESTS, so a count that is zero or negative once bumped draws nothing.
    A wider one just `dbf`s, so the bump wrapping to zero is not a refusal but the runaway: $ffff
    draws the whole 16-bit range and one more. Counting that as "0 rows drawn" is the hole this
    closes — it handed the one entry count that runs 65,537 rows a 64-instruction cap.
    """
    drawn = (rows + 1) & WORD_MASK
    if width.counts_rows_up_front:
        return 0 if drawn == 0 or drawn & WORD_SIGN_BIT else drawn
    return drawn if drawn else RUNAWAY_ROWS


def _insn_cap(width, rows):
    """The instruction cap for a case — and the battery's refusal to ask for the runaway `dbf`."""
    drawn = _rows_drawn(width, rows)
    assert drawn <= MAX_CASE_ROWS, (
        f"a case asking for {drawn} rows is asking for the runaway `dbf` this battery states as "
        f"unreached, not for a blit")
    return 2 * (_INSNS_ENTRY + drawn * (width.cells * _INSNS_PER_CELL
                                        + width.columns * _INSNS_PER_COLUMN + _INSNS_PER_ROW))


def _dest_for(x, y, screen):
    """Where the sprite pass would put this sprite: `screen + $1420 + y * 160 + (x & $fff0) / 2`,
    the `asr.w #1` being SIGNED so a negative x steps the cursor back."""
    return (screen + SCREEN_ORIGIN + y * SCREEN_LINE
            + (s16(x & COLUMN_ROUND_DOWN) >> 1)) & LONG_MASK


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


def _blit_glue(name, entry):
    """The reconstruction's result is an in/out register file rather than a returned d0.

    The struct is built FRESH inside the glue: the kit's attribution pass runs a candidate a second
    time on a poisoned image, and a box carried over would start that run from the first one's
    OUTPUT registers. What comes back is a plain dict, for the same reason — the box is about to be
    written over.
    """
    def glue(_lib, image):
        box = BlitRegs()
        for reg in range(SCRATCH_REGS):
            box.scratch[reg] = entry[f"d{reg}"]
        for reg, field in FIELD_BY_REG.items():
            setattr(box, field, entry[reg])
        _BLIT_FNS[name](image, ctypes.byref(box))
        out = {f"d{reg}": box.scratch[reg] for reg in range(SCRATCH_REGS)}
        out.update({reg: getattr(box, field) for reg, field in FIELD_BY_REG.items()})
        return out
    return glue


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
    # Python walk would otherwise spin through all 65,537 of its rows before the cap was consulted.
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
    range and one more — 65,537 rows, 10 MB of screen — where the BUMPED COUNTER alone says "zero".
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
# Sharded per the recipe in ../../buggyboy/recreate/README.md: one stream, generated in full by
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
