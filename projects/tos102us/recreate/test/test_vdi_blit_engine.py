"""The bit-block engine ($fd1038, vector 4's CPU body) through $a007 ($fd05fc): `src/vdi/blit.c`.

    $fd05fc  A6 += 76; the far corners = the near ones + B_WD / B_HT - 1, STORED into the caller's block;
             D0/D2/D4/D6 = the x edges; `move.l VECTOR_BITBLT,a5 / jmp (a5)`
    $fd1038  spans and the shift; the FAST COPY ($fd1352) for a bit-aligned op-3 copy of four words or
             more; otherwise the ALIGNER by four bits (shift right, shift of 8+, backwards, odd spans) and
             per plane the op by the plane's colour bits, a row a chain of fragments ($fd1694..$fd19db)

Every case copies between forms whose every word is its own pseudo-random value, so a pixel from the
wrong source word, a wrong mask bit, a wrong plane or a skipped row is a changed bit. The block is in the
compared window, so everything the engine leaves in it — its working words, the colours it spends, the
plane count it counts down, the pattern pointer it steps — is compared too.

WHICH WAY THE ENGINE COPIES is decided by ADDRESS: backwards (from the bottom right) when the source's
first word is below the destination's in memory, or the same word with the source bit left of the
destination bit. So a source ABOVE the destination on the screen is a backwards copy whether or not the
two overlap, and the aligner matrix below runs every shift both ways by placing the source above or below.

NO CASE HERE POISONS: the block is the engine's input AND its output — it counts PLANE_CT down to 0 and
spends the colour words — so the attribution pass, which inverts every byte the ROM wrote and runs both
again, hands the ROM a plane count of $fffb. What stands in for it is staging: every scratch byte of the
block starts as $a5, every unused pattern word as $5a5a, and every form word is its own random value.

THE MUTATION SWEEP of `src/vdi/blit.c` (this battery and `test_vdi_blit_copy.py`, strict classifier — README,
"Mutation sweeps"): 109 mutants, 101 KILLED, 2 ABNORMAL, 6 SURVIVED. ABNORMAL, and caught by the C's own
failure rather than an assertion: PLANE_CT's decrement not stored (the plane loop never ends; the process aborts)
and the bus mask dropped (a form address with its top byte set reads outside the host image).
SURVIVED, none of them a divergence:
  * a shift of exactly 8 taken the long way (`> 8`): rotating 8 left or 8 right is the same word — EQUIVALENT;
  * the destination-plane `btst` not taken mod 32: the host's shift by 32..63 is UB, and on the machines it
    runs on masks the count mod 32 exactly as `btst` does — UNKILLABLE on the host, not equivalent;
  * $a00e's opaque op 16 allowed (`> 16`): intin[0]'s bit 4 is the pattern flag, cleared before the op test,
    so the op is never exactly 16 — EQUIVALENT;
  * the clip's `<` taken as `<=`: at the clip edge the source moves by 0 — EQUIVALENT;
  * a plane whose P_ADDR stepped to 0 reloading the row offset, or skipping the row loads: only the pattern
    READS differ (from address 0 on), and nothing is ANDed on that plane — EQUIVALENT.
"""
import pytest

from harness import BASE_IMAGE

import vdi
import vdi_blit
import vdi_raster
from case import merge_pokes
from vdi_blit import OP_D, OP_S, OPS

# (source x - destination x) within a word: none, right shifts (the source bit left of the destination's)
# and left shifts, each side of 8 — the short-way rotate — and both ends.
SHIFTS = (0, 1, 3, 7, 8, 9, 15, -1, -3, -7, -8, -9, -15)
# Source above (backwards) or below (forwards) the destination.
DIRECTIONS = {"forwards": (140, 30), "backwards": (30, 140)}
# Widths from one pixel to several words; with the shifts they make both parities of the span difference,
# a row inside one word, and a row across a word boundary with no middle word.
WIDTHS = (1, 5, 16, 23, 40, 77)
HEIGHT = 3
DESTINATION_GROUP_X = 64
PREFERRED_BIT = 3
SOURCE_GROUPS_RIGHT = 3


def x_pair(shift):
    """(source x, destination x) whose bits in their words differ by exactly `shift` — the destination at
    bit 3 where the shift leaves room, else as near as it can — three groups apart."""
    destination_bit = min(max(PREFERRED_BIT, -shift), vdi_blit.PIXELS_PER_GROUP - 1 - max(shift, 0))
    destination_x = DESTINATION_GROUP_X + destination_bit
    return destination_x + shift + SOURCE_GROUPS_RIGHT * vdi_blit.PIXELS_PER_GROUP, destination_x


def xor_blit(shift, direction, width, *, height=HEIGHT, ops=(6,), **kwargs):
    """A copy of `width` x `height` whose source bit is `shift` right of the destination's — XOR, so the
    fast copy is never taken and both source and destination bits reach the result."""
    source_y, destination_y = DIRECTIONS[direction]
    source_x, destination_x = x_pair(shift)
    return vdi_blit.block_pokes(size=(width, height), source=(source_x, source_y),
                                destination=(destination_x, destination_y), ops=ops, **kwargs)


def bitblt(pokes, **kwargs):
    return vdi.run_primitive("LINEA_ROM_BITBLT", {"a6": vdi_blit.BLOCK_AT}, vdi_blit.canvas(pokes), poison=False, **kwargs)


def engine(registers, pokes, **kwargs):
    return vdi.run_primitive("LINEA_ROM_CPU_BLIT", registers, vdi_blit.canvas(pokes), poison=False, **kwargs)


@pytest.mark.parametrize("width", WIDTHS)
@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("shift", SHIFTS)
def test_every_aligner(shift, direction, width):
    result = bitblt(xor_blit(shift, direction, width))
    source_x, destination_x = x_pair(shift)
    corners = vdi_blit.far_corners((width, HEIGHT), (source_x, DIRECTIONS[direction][0]),
                                   (destination_x, DIRECTIONS[direction][1]))
    stored = tuple(result.word(vdi_blit.BLOCK_AT + vdi.field("BITBLT", name).at)
                   for name in ("S_XMAX", "S_YMAX", "D_XMAX", "D_YMAX"))
    assert stored == corners, "$a007 stores the far corners into the caller's block"


@pytest.mark.parametrize("op", OPS)
@pytest.mark.parametrize("shape", ({"shift": 5, "width": 40}, {"shift": -3, "width": 9}, {"shift": 0, "width": 50},
                                   {"shift": 11, "width": 1}), ids=("words", "one word", "aligned", "one pixel"))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_every_op(op, shape, direction):
    """Op 5 (the destination as it is) skips the plane; 0, 10 and 15 read no source and take their own
    row loop; the other twelve go through an aligner — and op 3 on the aligned shape takes the fast copy."""
    bitblt(xor_blit(shape["shift"], direction, shape["width"], ops=(op,), height=4))


# (address, next line, next plane, mask): the workstation's multi-plane user pattern, and the ROM's own
# one-plane 16-row hatch — $a00e's shape, two bytes a row and 16 rows.
USER_PATTERN = (vdi_raster.USER_PATTERN_AT, 2, vdi_raster.MULTIFILL_PLANE_WORDS * vdi.WORD_BYTES, 30)
HATCH = (vdi_raster.HATCH_16_ROWS[0], 2, 0, 30)


@pytest.mark.parametrize("op", OPS)
def test_every_op_through_a_pattern(op):
    """The multi-plane user pattern ANDed into the source, a plane of it per plane, the pattern pointer
    stepped per plane — which the no-source ops step too without reading it."""
    bitblt(merge_pokes(vdi_raster.user_pattern_pokes(),
                       xor_blit(7, "forwards", 37, ops=(op,), height=5, pattern=USER_PATTERN)))


@pytest.mark.parametrize("pattern", (USER_PATTERN, HATCH), ids=("user, multi-plane", "hatch, one plane"))
@pytest.mark.parametrize("direction", DIRECTIONS)
@pytest.mark.parametrize("shift", (0, 6, -10))
def test_a_pattern_both_ways(pattern, direction, shift):
    """Backwards, the pattern starts at the BOTTOM row's index and P_NXLN is negated IN THE BLOCK; the
    first row's index is y * |P_NXLN| masked by P_MASK. Op 3 with a pattern never takes the fast copy."""
    bitblt(merge_pokes(vdi_raster.user_pattern_pokes(),
                       xor_blit(shift, direction, 45, ops=(OP_S,), height=19, pattern=pattern)))


def test_a_pattern_index_that_wraps_by_its_mask():
    """An odd row step and a mask that is not 2^n - 2: the row offsets the engine really forms."""
    bitblt(merge_pokes(vdi_raster.user_pattern_pokes(),
                       xor_blit(2, "forwards", 30, ops=(9,), height=9, pattern=(vdi_raster.USER_PATTERN_AT, 6, 4, 22))))


def test_a_negative_pattern_offset_is_signed():
    """P_NXLN and P_MASK are the caller's: a negative row step under a mask that keeps the sign bit walks
    the offset below 0, and the word is read BEFORE P_ADDR (`move.w 0(a6,d0.w),d7`, a signed index)."""
    pattern = (vdi_raster.USER_PATTERN_AT + 32, -2, 0, 0xFFFE)
    bitblt(merge_pokes(vdi_raster.user_pattern_pokes(), vdi_blit.block_pokes(size=(20, 6), source=(40, 150), destination=(7, 1),
                                                                             ops=(OP_S,), pattern=pattern)))


# OP_TAB by (foreground bit, background bit): four different ops, and colours whose planes take each.
FOUR_OPS = (1, 12, 7, 2)


@pytest.mark.parametrize("colours", ((0b0110, 0b1010), (0b1111, 0), (0, 0b1111), (0b1001, 0b0101)))
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_op_follows_each_plane_s_colour_bits(colours, direction):
    """FG_COL and BG_COL are shifted right IN THE BLOCK once per plane, the index fg * 2 + bg."""
    foreground, background = colours
    bitblt(xor_blit(4, direction, 33, ops=FOUR_OPS, foreground=foreground, background=background))


@pytest.mark.parametrize("colours", ((0b0110, 0b1010), (0b0011, 0b0101)))
def test_a_one_plane_source_into_every_plane(colours):
    """The transparent shape $a00e builds: S_NXPL = 0, one source plane under every destination plane,
    each plane's op by its colours."""
    foreground, background = colours
    bitblt(vdi_blit.block_pokes(size=(29, 7), source=(3, 2), destination=(90, 60),
                                source_form=vdi_blit.off_screen(0, 1), source_next_plane=0,
                                ops=FOUR_OPS, foreground=foreground, background=background, planes=4))


@pytest.mark.parametrize("planes", (1, 2, 4))
@pytest.mark.parametrize("shift", (0, 5, -12))
def test_off_screen_forms_of_each_depth(planes, shift):
    """Form to form, `planes` deep: both strides the form's own."""
    bitblt(vdi_blit.block_pokes(size=(50, 6), source=(20 + shift, 3), destination=(20, 11),
                                source_form=vdi_blit.off_screen(0, planes),
                                destination_form=vdi_blit.off_screen(1, planes), ops=(9,)))


@pytest.mark.parametrize("height", (1, 20))
@pytest.mark.parametrize("shift", (0, 9))
def test_one_row_and_many(height, shift):
    bitblt(xor_blit(shift, "forwards", 60, height=height, ops=(OP_S,)))


def test_the_forms_band_is_dead_memory_in_this_snapshot():
    """Compared like any image: live bytes there would make every off-screen case a statement about the
    desktop's leftovers as well as about the engine."""
    assert bytes(BASE_IMAGE[vdi_blit.FORMS_AT:vdi_blit.FORMS_AT + vdi_blit.FORMS_BYTES]) == bytes(vdi_blit.FORMS_BYTES)


# ---- the fast copy --------------------------------------------------------------------------------------
# Op 3, colours 0, no pattern, source and destination on the same bit, and at least four words between the
# two spans: (x, width) that reach it — and the narrowest that does not.
FAST_SHAPES = {"aligned words": (16, 64), "unaligned ends": (5, 50), "just four words": (0, 33),
               "three words": (0, 32)}


@pytest.mark.parametrize("shape", FAST_SHAPES.values(), ids=FAST_SHAPES.keys())
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_the_fast_copy(shape, direction):
    x, width = shape
    source_y, destination_y = DIRECTIONS[direction]
    bitblt(vdi_blit.block_pokes(size=(width, 5), source=(x + 32, source_y), destination=(x, destination_y)))


@pytest.mark.parametrize("planes", (1, 2))
def test_the_fast_copy_off_screen(planes):
    """...its plane loop OUTSIDE the rows, S_START / D_START stepped and stored after every plane."""
    bitblt(vdi_blit.block_pokes(size=(70, 4), source=(3, 1), destination=(3, 13),
                                source_form=vdi_blit.off_screen(0, planes), destination_form=vdi_blit.off_screen(1, planes)))


def test_the_fast_copy_with_a_source_word_stride_of_0():
    """S_NXWD is the caller's: 0 repeats one source word across the row — and, being not negative, keeps
    the masks the forward way round ($fd13ac `tst.w d2 / bpl`)."""
    bitblt(vdi_blit.block_pokes(size=(64, 3), source=(21, 150), destination=(21, 40), S_NXWD=0))


def test_a_form_address_with_its_top_byte_set():
    """The 68000 drives 24 address bits: a form base with junk above them is the same form."""
    bitblt(xor_blit(6, "forwards", 40, S_FORM=vdi_blit.SCREEN_FORM.base | 0x5A000000,
                    D_FORM=vdi_blit.SCREEN_FORM.base | 0xA5000000))


def test_the_fast_copy_is_refused_by_a_colour():
    """One nonzero colour word and op 3 goes the aligned way, through OP_TAB's first entry for every plane
    whose bits are clear — the rest take their own ops."""
    bitblt(vdi_blit.block_pokes(size=(64, 3), source=(16, 150), destination=(16, 40), ops=(OP_S, 12, OP_S, 5),
                                background=0b0100))


# ---- overlap: the direction the ROM chooses, in both -------------------------------------------------------
# (dx, dy) from the source to the destination, over one form: every direction, bit-aligned and not.
OVERLAPS = {"onto itself": (0, 0), "right 3": (3, 0), "left 3": (-3, 0), "down 2": (0, 2), "up 2": (0, -2), "right 5 down 1": (5, 1),
            "left 5 up 1": (-5, -1), "right a word": (16, 0), "left a word": (-16, 0), "right 20 up 3": (20, -3),
            "left 11 down 4": (-11, 4)}


@pytest.mark.parametrize("op", (OP_S, 6))
@pytest.mark.parametrize("delta", OVERLAPS.values(), ids=OVERLAPS.keys())
def test_overlapping_source_and_destination(delta, op):
    """The engine reads a source word before it writes the destination word that could clobber it, in
    whichever direction it picked — with the carry in a register, not re-read."""
    dx, dy = delta
    bitblt(vdi_blit.block_pokes(size=(61, 9), source=(100, 80), destination=(100 + dx, 80 + dy), ops=(op,)))


def test_the_same_word_with_the_source_bit_left_goes_backwards():
    """Source and destination starting in the SAME word, the source bit left of the destination's: the
    address tie is broken by the shift's sign."""
    bitblt(vdi_blit.block_pokes(size=(30, 2), source=(97, 50), destination=(99, 50), ops=(6,)))


# ---- the special rows -----------------------------------------------------------------------------------
@pytest.mark.parametrize("op", (0, 10, 15))
@pytest.mark.parametrize("width", (1, 12, 16, 70))
def test_the_ops_that_read_no_source(op, width):
    """Their own row loop: the destination walked alone — A0 never stepped — under the two edge masks."""
    bitblt(xor_blit(-2, "backwards", width, ops=(op,), height=4))


def test_op_5_skips_the_plane_and_the_next_still_steps():
    """Op 5 for two planes' colour bits, 3 for the others: the skipped planes' pointers still step."""
    bitblt(xor_blit(3, "forwards", 40, ops=(OP_D, OP_S, OP_D, OP_S), foreground=0b0101, background=0b0011))


# ---- the block read again as the engine runs: what a destination over it, or a caller's stride, changes ------
MIDDLE_COUNT_AT = vdi_blit.BLOCK_AT + vdi.field("BITBLT", "MIDDLE_COUNT").at
# A form two planes deep, 160 bytes a line, whose plane-0 word at (0, 0) IS the block's MIDDLE_COUNT.
OVER_MIDDLE_COUNT = vdi_blit.Form(MIDDLE_COUNT_AT, 2, vdi_blit.FORM_LINE_BYTES)
ONE_PLANE_SOURCE = vdi_blit.Form(vdi_blit.FORMS_AT, 1, vdi_blit.FORM_LINE_BYTES)


@pytest.mark.parametrize("middle_word", (0, 3))
def test_the_fast_copy_rereads_middle_count_before_every_row(middle_word):
    """$fd13f2 `move.w -6(a6),d5` heads EVERY row: a destination whose first row lands on the block's own
    MIDDLE_COUNT makes row 2 as wide as the source word copied there."""
    over_block = vdi_blit.Form(MIDDLE_COUNT_AT - vdi_blit.WORD_BYTES, 1, vdi_blit.FORM_LINE_BYTES)
    source_word = {vdi_blit.FORMS_AT + vdi_blit.WORD_BYTES: middle_word.to_bytes(vdi_blit.WORD_BYTES, "big")}
    bitblt(merge_pokes(vdi_blit.block_pokes(size=(64, 2), source=(0, 0), destination=(0, 0), source_form=ONE_PLANE_SOURCE,
                                            destination_form=over_block), source_word))


@pytest.mark.parametrize("second_op", (10, 15))
def test_the_no_source_rows_test_middle_count_afresh_each_plane(second_op):
    """$fd12ce `tst.w d5` picks the no-source row loop per PLANE from MIDDLE_COUNT: plane 0's one-word row
    IS the block's MIDDLE_COUNT, whole-masked, and ZERO rewrites it to 0 — so plane 1 (its background bit
    set: `second_op`) draws a TWO-word row. The source ops decided theirs once, at setup."""
    bitblt(vdi_blit.block_pokes(size=(16, 1), source=(37, 150), destination=(0, 0), destination_form=OVER_MIDDLE_COUNT,
                                ops=(0, second_op), background=0b10))


@pytest.mark.parametrize("step", (0x20, 0x100, 0x400))
def test_a_pattern_pointer_stepped_to_0_ands_nothing(step):
    """$fd1234 re-tests P_ADDR PER PLANE: four planes, P_ADDR 3 * step and P_NXPL -step, so the fourth
    plane's pointer is 0 — its op is entered without the `and.w d7,d0` (the row loads still run, from 0
    on), and a pointer at 0 is never stepped again."""
    pattern = (3 * step, 2, (-step) & 0xFFFF, 30)
    bitblt(vdi_blit.block_pokes(size=(40, 6), source=(37, 150), destination=(21, 30), ops=(OP_S,), pattern=pattern))


# ---- the runaway counts: 65,536 of them, harmless over strides of 0 ------------------------------------------
# A count of 0 on the aligned path is `subq.w #1 / beq` from 0: 65,536 rows or planes. With every stride 0
# each pass lands on the same words, so it is staged whole — XOR tells 65,536 passes from ONE (an even count
# of XORs is none), OR tells them from NONE.
RUNAWAY_INSNS = 20_000_000
RUNAWAY_OPS = (6, 7)


@pytest.mark.parametrize("op", RUNAWAY_OPS)
def test_a_height_of_0_runs_65536_rows(op):
    bitblt(vdi_blit.block_pokes(size=(20, 0), source=(37, 150), destination=(21, 30), ops=(op,), S_NXLN=0, D_NXLN=0),
           max_insns=RUNAWAY_INSNS)


@pytest.mark.parametrize("op", RUNAWAY_OPS)
def test_a_plane_count_of_0_runs_65536_planes(op):
    bitblt(vdi_blit.block_pokes(size=(20, 1), source=(37, 150), destination=(21, 30), ops=(op,), planes=0,
                                S_NXPL=0, D_NXPL=0), max_insns=RUNAWAY_INSNS)


# ...and a fast copy whose source is ONE word: MIDDLE_COUNT = span - 2 = -2, `dbf` from it runs 65,535 middle
# words. The destination's word stride 0 keeps every store on one word, which ends as the LAST source words
# read. The source is below the screen, so the copy runs BACKWARDS and the source walks down, a word at a
# time, 128 KB — from where it starts to the middle of the first off-screen form, whose words are random.
RUNAWAY_SOURCE_WALK = 0x20000
RUNAWAY_SOURCE_FORM = vdi_blit.FORMS_AT + vdi_blit.FORM_BYTES // 2 + RUNAWAY_SOURCE_WALK


def test_a_fast_copy_source_of_one_word_runs_65535_middle_words():
    """The engine entered directly with independent x edges (a one-word source, a five-word destination)."""
    size, source, destination = (80, 1), (32, 0), (32, 40)
    registers = {**vdi_blit.engine_registers(size, source, destination), "d4": 32 + vdi_blit.PIXELS_PER_GROUP - 1}
    engine(registers, vdi_blit.engine_block_pokes(size, source, destination, planes=1, S_NXWD=vdi_blit.WORD_BYTES, D_NXWD=0,
                                                  S_FORM=RUNAWAY_SOURCE_FORM),
           max_insns=RUNAWAY_INSNS)


# ---- the engine entered directly ---------------------------------------------------------------------------

@pytest.mark.parametrize("shift", (0, 4, -9))
@pytest.mark.parametrize("op", (OP_S, 8))
def test_the_engine_entered_directly(shift, op):
    size, source, destination = (44, 6), (32 + shift, 90), (32, 20)
    engine(vdi_blit.engine_registers(size, source, destination),
           vdi_blit.engine_block_pokes(size, source, destination, ops=(op,)))


def test_the_engine_takes_its_spans_from_the_registers_and_its_masks_from_the_block():
    """The x edges in D0/D2/D4/D6 decide the spans, the shift and the aligner; the block's x edges the
    word addresses and the masks. Handed two different destination widths, the two disagree — the
    engine's own arithmetic, which neither front end ever feeds it."""
    size, source, destination = (44, 6), (37, 90), (32, 20)
    registers = {**vdi_blit.engine_registers(size, source, destination), "d6": 32 + 70}
    engine(registers, vdi_blit.engine_block_pokes(size, source, destination, ops=(6,)))


# ---- through the exception ---------------------------------------------------------------------------------

def test_through_the_line_a_exception():
    vdi.run_through_exception("LINEA_ROM_BITBLT", 7, {"a6": vdi_blit.BLOCK_AT},
                              vdi_blit.canvas(xor_blit(-6, "backwards", 40, ops=(13,))), poison=False)


# ---- the rows Tier 3 prices, each run here as the differential it is -------------------------------------
# The worst realistic of each path: the aligned path over several words and planes, a pattern on it, the
# fast copy, and one pixel. The engine's `.S` rows are entered with its code-pointer registers cleared.

def engine_case(shift, width, *, height=HEIGHT, ops=(6,), direction="forwards", **kwargs):
    """The engine entered directly on the aligner-matrix shape: its registers and its block."""
    size = (width, height)
    source_x, destination_x = x_pair(shift)
    source_y, destination_y = DIRECTIONS[direction]
    source, destination = (source_x, source_y), (destination_x, destination_y)
    return (vdi_blit.engine_registers(size, source, destination),
            vdi_blit.engine_block_pokes(size, source, destination, ops=ops, **kwargs))


ENGINE_ROWS = {
    "xor, 77 pixels shifted 9 right, 3 rows": (engine_case(9, 77), vdi_blit.ENGINE_CODE_POINTERS),
    "copy through the user pattern, 45 x 19": (engine_case(6, 45, height=19, ops=(OP_S,), pattern=USER_PATTERN),
                                               vdi_blit.PATTERN_CODE_POINTERS),
    "the fast copy, 64 x 5": ((vdi_blit.engine_registers((64, 5), (48, 150), (16, 40)),
                               vdi_blit.engine_block_pokes((64, 5), (48, 150), (16, 40))), ()),
    "one pixel": (engine_case(-4, 1, height=1), vdi_blit.ENGINE_CODE_POINTERS),
}
BITBLT_ROWS = {"xor, 40 pixels shifted 3 left, backwards": xor_blit(-3, "backwards", 40),
               "one pixel": xor_blit(2, "forwards", 1, height=1, ops=(OP_S,))}
for _label, ((_registers, _pokes), _pointers) in ENGINE_ROWS.items():
    vdi_blit.register(_label, "LINEA_ROM_CPU_BLIT", merge_pokes(vdi_raster.user_pattern_pokes(), _pokes),
                      regs=_registers, code_pointers=_pointers)
for _label, _pokes in BITBLT_ROWS.items():
    vdi_blit.register(_label, "LINEA_ROM_BITBLT", _pokes, regs={"a6": vdi_blit.BLOCK_AT})


@pytest.mark.parametrize("row", ENGINE_ROWS, ids=list(ENGINE_ROWS))
def test_the_engine_rows(row):
    (registers, pokes), _pointers = ENGINE_ROWS[row]
    engine(registers, merge_pokes(vdi_raster.user_pattern_pokes(), pokes))


@pytest.mark.parametrize("row", BITBLT_ROWS, ids=list(BITBLT_ROWS))
def test_the_bitblt_rows(row):
    bitblt(BITBLT_ROWS[row])
