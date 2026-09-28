"""VDI write mode, input modes and clipping — vswr_mode (32), vsin_mode (33), vqin_mode (115), vs_clip (129),
and the corner sort vs_clip shares with the raster and rectangle layers, arb_corner ($fcb55e):
`src/vdi/attributes.c`.

    vswr_mode  contrl[4]=1; m = intin[0]-1; m outside 0..3 -> 0; WS_WRT_MODE = m; intout[0] = m+1
    vsin_mode  contrl[4]=1; intout[0] = intin[1] RAW; then by intin[0] — 1 LOC, 2 VAL, 3 CHC, 4 STR, else
               nothing (`cmp.w #4 / bhi`, unsigned) — that device's Line-A mode word = intin[1] - 1
    vqin_mode  contrl[4]=1; by intin[0] as above, intout[0] = the mode word; else intout[0] UNWRITTEN
    vs_clip    WS_CLIP = intin[0] RAW; nonzero: arb_corner(ptsin, y ascending) IN PLACE, then
               xmin/ymin floored at 0, xmax/ymax capped at DEV_TAB[0]/[1]; zero: the whole screen
    arb_corner (corners.l, order.w): x0 <= x1 always; y by order — 0 descending, 1 ascending, else untouched

TWO ROM QUIRKS PINNED. vqin_mode answers the STORED word, which vsin_mode made one less than it was
given: a device set to sample mode (2) reports 1 — the call does not round-trip. And vs_clip bounds
each corner on ONE side only, so a rectangle wholly off the screen keeps an off-screen edge (xmax -10).

WHAT THE DISPATCHER'S COPIES SHOW. vswr_mode and vs_clip set exactly the fields `$fca9f6` copies into
Line-A on every call (LINEA_WRT_MODE; LINEA_CLIP, the four LINEA_*CL words and INQ_TAB[19]) and write
none of the copies: the primitives draw with the old mode or rectangle until the next VDI call
re-dispatches. Every case stages the record STALE — so the copies are too — and holds them unchanged.
"""
import struct

import pytest

from harness import BASE_IMAGE, addrs

import abi
import case
import vdi
import vdi_attributes as attr

WRMODE, SIN, QIN, CLIP = "VDI_ROM_VSWR_MODE", "VDI_ROM_VSIN_MODE", "VDI_ROM_VQIN_MODE", "VDI_ROM_VS_CLIP"
WORD_EDGES = (-0x8000, 0x7FFF)
MODE_WORDS = ("LOC_MODE", "VAL_MODE", "CHC_MODE", "STR_MODE")         # devices 1..4, in the switch's order
# Each device's mode word staged DISTINCT, so a store to the wrong one — or an answer read from the
# wrong one — is a wrong value rather than a coincidence of the snapshot's 0, 0, 0, 1.
STAGED_MODES = {name: 0x0A00 + device for device, name in enumerate(MODE_WORDS, 1)}


# ---- vswr_mode --------------------------------------------------------------------------------------

@pytest.mark.parametrize("mode", (1, 2, 3, 4, 0, 5, -1, *WORD_EDGES))
def test_vswr_mode_stores_zero_based_and_leaves_the_line_a_copy(mode):
    result = attr.run(WRMODE, attr.call(WRMODE, (mode,), fields={"WRT_MODE": attr.STALE}))
    stored = mode - 1 if 1 <= mode <= 4 else 0
    assert result.workstation("WRT_MODE") == stored
    assert result.intout(1) == [stored + 1]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1
    assert result.linea("WRT_MODE") == attr.STALE, "the copy catches up at the next dispatch, not here"


# ---- vsin_mode / vqin_mode ----------------------------------------------------------------------------

def modes_pokes(name, intin):
    return attr.call(name, intin, linea=STAGED_MODES)


@pytest.mark.parametrize("device", (1, 2, 3, 4, 0, 5, -1, 0x8000))
@pytest.mark.parametrize("mode", (1, 2, 7, 0, -3))
def test_vsin_mode_echoes_the_mode_raw_and_stores_it_less_one(device, mode):
    result = attr.run(SIN, modes_pokes(SIN, (device, mode)))
    assert result.intout(1) == [mode & 0xFFFF]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1
    expected = dict(STAGED_MODES)
    if 1 <= device <= 4:
        expected[MODE_WORDS[device - 1]] = (mode - 1) & 0xFFFF
    assert {name: result.linea(name) for name in MODE_WORDS} == expected


@pytest.mark.parametrize("device", (1, 2, 3, 4, 0, 5, -1))
def test_vqin_mode_answers_the_stored_word_or_nothing(device):
    result = attr.run(QIN, modes_pokes(QIN, (device,)))
    answer = STAGED_MODES[MODE_WORDS[device - 1]] if 1 <= device <= 4 else vdi.FILL * 0x0101
    assert result.intout(1) == [answer]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 1, "one word is claimed even where none was written"


def test_sample_mode_does_not_round_trip():
    """vsin_mode(locator, 2) then vqin_mode(locator): the query answers 1, the stored word."""
    first = attr.run(SIN, modes_pokes(SIN, (1, 2)))
    arrays = vdi.function_pokes(QIN, (1,), workstation_pokes={})
    second = attr.run(QIN, case.merge_pokes(case.continued(first), arrays))
    assert second.intout(1) == [1]


# ---- vs_clip ------------------------------------------------------------------------------------------
LAST_X, LAST_Y = vdi.linea(BASE_IMAGE, "DEV_TAB")[:2]
CLIP_FIELDS = ("CLIP", "XMN_CLIP", "YMN_CLIP", "XMX_CLIP", "YMX_CLIP")
CLIP_COPIES = ("CLIP", "XMINCL", "YMINCL", "XMAXCL", "YMAXCL")
STALE_CLIP = {name: attr.STALE for name in CLIP_FIELDS}


def clip_pokes(flag, corners, virtual=False):
    return attr.call(CLIP, (flag,), corners, virtual=virtual, fields=STALE_CLIP)


def sorted_corners(corners):
    x0, y0, x1, y1 = corners
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def clipped(corners):
    x0, y0, x1, y1 = sorted_corners(corners)
    return [max(x0, 0), max(y0, 0), min(x1, LAST_X), min(y1, LAST_Y)]


def clip_rectangle(result, at=vdi.VDI_PHYS_WORK):
    return [result.workstation(name, at) & 0xFFFF for name in ("XMN_CLIP", "YMN_CLIP", "XMX_CLIP", "YMX_CLIP")]


def assert_copies_untouched(result):
    assert [result.linea(name) for name in CLIP_COPIES] == [attr.STALE] * len(CLIP_COPIES)
    assert result.linea("INQ_TAB")[vdi.VDI_INQ_TAB_CLIP_INDEX] == attr.STALE


RECTANGLES = ((10, 20, 100, 150),          # already sorted, inside
              (100, 150, 10, 20),          # both pairs reversed
              (100, 20, 10, 150),          # x reversed only
              (10, 150, 100, 20),          # y reversed only
              (-5, -7, 400, 300),          # cut on every side
              (-50, -60, -10, -20),        # wholly above and left: xmax/ymax stay negative
              (400, 300, 500, 350),        # wholly below and right: xmin/ymin stay past the edge
              (0, 0, 319, 199), (0, 0, 320, 200), (7, 7, 7, 7), (-0x8000, 0x7FFF, 0x7FFF, -0x8000))


@pytest.mark.parametrize("corners", RECTANGLES)
@pytest.mark.parametrize("flag", (1, 2, -1))
def test_vs_clip_on_sorts_ptsin_in_place_and_bounds_each_corner_on_one_side(flag, corners):
    result = attr.run(CLIP, clip_pokes(flag, corners))
    assert result.workstation("CLIP") == flag & 0xFFFF, "the flag is stored as given, not normalised"
    assert result.words(vdi.VDI_PTSIN_COPY, 4) == [value & 0xFFFF for value in sorted_corners(corners)]
    assert clip_rectangle(result) == [value & 0xFFFF for value in clipped(corners)]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 0 and result.intout(1) == [vdi.FILL * 0x0101]
    assert_copies_untouched(result)


@pytest.mark.parametrize("corners", ((100, 150, 10, 20), (10, 20, 100, 150)))
def test_vs_clip_off_is_the_whole_screen_and_leaves_ptsin_alone(corners):
    result = attr.run(CLIP, clip_pokes(0, corners))
    assert result.workstation("CLIP") == 0
    assert clip_rectangle(result) == [0, 0, LAST_X, LAST_Y]
    assert result.words(vdi.VDI_PTSIN_COPY, 4) == list(corners)
    assert_copies_untouched(result)


def test_vs_clip_bounds_against_dev_tab_not_constants():
    table = vdi.linea(BASE_IMAGE, "DEV_TAB")
    table[:2] = [639, 399]                 # the monochrome workstation's last column and row
    pokes = attr.call(CLIP, (1,), (-5, -5, 700, 500), onto=vdi.linea_pokes(DEV_TAB=table), fields=STALE_CLIP)
    assert clip_rectangle(attr.run(CLIP, pokes)) == [0, 0, 639, 399]


@pytest.mark.parametrize("flag", (0, 1))
def test_vs_clip_writes_the_current_workstation(flag):
    result = attr.run(CLIP, clip_pokes(flag, (100, 150, 10, 20), virtual=True))
    assert result.workstation("CLIP", at=vdi.VIRTUAL_WORK_AT) == flag
    attr.assert_physical_untouched(result)


# ---- arb_corner, entered directly -----------------------------------------------------------------------
CORNERS_AT = vdi.PTSIN_AT          # a claimed band of the window: the corners are a caller's ptsin


def arb_corner_pokes(corners, order):
    return {abi.FIRST_ARG: struct.pack(">IH", CORNERS_AT, order), CORNERS_AT: vdi.pack_words(*corners)}


def run_arb_corner(corners, order):
    def glue(lib, buf):
        lib.vdi_arb_corner.restype = None
        return lib.vdi_arb_corner(buf, CORNERS_AT, order)

    pokes = arb_corner_pokes(corners, order)
    return vdi.Result(case.run(addrs.VDI_ROM_ARB_CORNER, {"_pokes": pokes}, glue, width=case.NO_RESULT), pokes)


def arb_sorted(corners, order):
    x0, y0, x1, y1 = corners
    x0, x1 = min(x0, x1), max(x0, x1)
    if order == 0:
        y0, y1 = max(y0, y1), min(y0, y1)
    elif order == 1:
        y0, y1 = min(y0, y1), max(y0, y1)
    return [value & 0xFFFF for value in (x0, y0, x1, y1)]


@pytest.mark.parametrize("order", (0, 1, 2, 0xFFFF))
@pytest.mark.parametrize("corners", ((1, 2, 3, 4), (3, 4, 1, 2), (3, 2, 1, 4), (1, 4, 3, 2), (5, 5, 5, 5),
                                     (-1, 1, 1, -1), (0x7FFF, -0x8000, -0x8000, 0x7FFF)))
def test_arb_corner_sorts_x_always_and_y_by_order(corners, order):
    result = run_arb_corner(corners, order)
    assert result.words(CORNERS_AT, 4) == arb_sorted(corners, order)


# ---- store order ----------------------------------------------------------------------------------------

# vsin_mode's (device, mode) are two DIFFERENT devices' numbers: with intout over intin, the echoed mode
# lands on intin[0], so the ROM — which reads the device only after the echo — sets device 3's mode, and
# a reconstruction that read it first would set device 1's. Equal words would show nothing.
@pytest.mark.parametrize("name, field, intin", ((WRMODE, "WRT_MODE", (3,)), (SIN, "WRT_MODE", (1, 3)),
                                                (QIN, "WRT_MODE", (4,))))
def test_the_stores_land_in_the_roms_order(name, field, intin):
    for _label, pokes in attr.overlap_cases(name, field, intin):
        attr.run(name, pokes)


def test_vs_clip_reads_the_corners_it_sorted():
    """ptsin laid over the workstation's clip words: the sort and the stores race for the same memory,
    and only the ROM's order — sort, then read x0 and store it, then y0 — leaves each word."""
    ptsin_at = vdi.VDI_PHYS_WORK + vdi.field("WS", "XMN_CLIP").at
    pokes = case.merge_pokes(clip_pokes(1, (100, 150, 10, 20)), vdi.linea_pokes(PTSIN=ptsin_at),
                             vdi.field_pokes("WS", vdi.VDI_PHYS_WORK, XMN_CLIP=100, XMX_CLIP=150,
                                             YMN_CLIP=10, YMX_CLIP=20))
    attr.run(CLIP, pokes)


def test_vs_clip_reads_the_ptsin_pointer_once_before_its_sort():
    """ptsin laid over Line-A's own INTIN and PTSIN pointers: the corners' y words are intin's low word and
    ptsin's, and the sort swaps them — MOVING the PTSIN pointer. The ROM loaded the pointer once, before the
    sort (`movea.l $29a6,a5`), and walks the corners where it sorted them; a core that re-read the pointer per
    word would read its corners from wherever the sort pointed it. The routine writes the pointer it reads, so
    the attribution pass is off (`vdi.READS_A_POINTER_IT_WRITES`)."""
    ptsin_at = vdi.field("LINEA", "INTIN").at
    pokes = case.merge_pokes(clip_pokes(1, (100, 150, 10, 20)), vdi.linea_pokes(PTSIN=ptsin_at))
    result = attr.run(CLIP, pokes, **vdi.READS_A_POINTER_IT_WRITES)
    assert result.linea("PTSIN") != ptsin_at, "the sort left the pointer where it was: the case shows nothing"


# ---- Tier 3 ---------------------------------------------------------------------------------------------
attr.register("in range", WRMODE, attr.call(WRMODE, (3,)))
attr.register("out of range", WRMODE, attr.call(WRMODE, (5,)))
attr.register("string, sample", SIN, modes_pokes(SIN, (4, 2)))
attr.register("no such device", SIN, modes_pokes(SIN, (0, 2)))
attr.register("string", QIN, modes_pokes(QIN, (4,)))
attr.register("reversed, cut", CLIP, clip_pokes(1, (400, 300, -5, -7)))
attr.register("off", CLIP, clip_pokes(0, (10, 20, 100, 150)))
vdi.register("vdi_arb_corner, both swapped", addrs.VDI_ROM_ARB_CORNER, arb_corner_pokes((3, 2, 1, 4), 1))
vdi.register("vdi_arb_corner, sorted", addrs.VDI_ROM_ARB_CORNER, arb_corner_pokes((1, 2, 3, 4), 0))
