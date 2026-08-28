"""The chunky-to-planar reference and the column drawer.

c2p is the oracle the hand-written 68000 version will be compared against, so
the format claims in host/c2p.h are asserted here rather than trusted.
"""
import ctypes

import pytest

import blackice
from blackice import CONST, make_level

PLANES = CONST["SCREEN_PLANES"]
LINE_BYTES = CONST["SCREEN_BYTES_PER_LINE"]
SCREEN_BYTES = CONST["SCREEN_BYTES"]
SCREEN_W = CONST["SCREEN_W"]
WINDOW_LINES = CONST["SCREEN_WINDOW_LINES"]
HUD_LINES = CONST["SCREEN_HUD_LINES"]


def planar_buffer():
    return ctypes.create_string_buffer(SCREEN_BYTES)


@pytest.mark.parametrize("columns,doubling",
                         [(CONST["RENDER_COLUMNS_HIGH"], 2), (CONST["RENDER_COLUMNS_LOW"], 4)])
def test_c2p_round_trips_every_pixel(lib, columns, doubling):
    chunky = blackice.chunky_buffer()
    raw = bytearray(chunky.raw)
    for x in range(columns):
        for y in range(blackice.RENDER_H):
            raw[x * blackice.RENDER_H + y] = (x * 7 + y * 3) % CONST["PALETTE_SIZE"]
    chunky.raw = bytes(raw)
    planar = planar_buffer()

    lib.c2p_window(chunky, columns, planar)

    for x in range(0, SCREEN_W, 3):
        for y in range(0, WINDOW_LINES, 5):
            expected = raw[(x // doubling) * blackice.RENDER_H + (y // 2)]
            assert lib.planar_pixel(planar, x, y) == expected


def test_c2p_leaves_the_hud_band_alone(lib):
    """The bottom 40 scanlines are the platform's static HUD; the engine must
    never touch them or the HUD would flicker."""
    chunky = blackice.chunky_buffer()
    chunky.raw = bytes([15]) * blackice.CHUNKY_BYTES
    planar = planar_buffer()
    planar.raw = bytes([0xa5]) * SCREEN_BYTES

    lib.c2p_window(chunky, CONST["RENDER_COLUMNS_HIGH"], planar)

    assert HUD_LINES == CONST["SCREEN_H"] - WINDOW_LINES
    tail = planar.raw[WINDOW_LINES * LINE_BYTES:]
    assert tail == bytes([0xa5]) * (HUD_LINES * LINE_BYTES)


def test_c2p_doubles_every_line(lib):
    chunky = blackice.chunky_buffer()
    raw = bytearray(chunky.raw)
    for x in range(CONST["RENDER_COLUMNS_HIGH"]):
        for y in range(blackice.RENDER_H):
            raw[x * blackice.RENDER_H + y] = y % CONST["PALETTE_SIZE"]
    chunky.raw = bytes(raw)
    planar = planar_buffer()

    lib.c2p_window(chunky, CONST["RENDER_COLUMNS_HIGH"], planar)

    for row in range(blackice.RENDER_H):
        first = planar.raw[(row * 2) * LINE_BYTES:(row * 2 + 1) * LINE_BYTES]
        second = planar.raw[(row * 2 + 1) * LINE_BYTES:(row * 2 + 2) * LINE_BYTES]
        assert first == second


def test_the_drawer_writes_exactly_the_rows_the_column_asks_for(lib):
    """The drawer has no clipping of its own; every byte it writes has to be
    accounted for by `top` and `rows`."""
    scratch = blackice.RenderScratch()
    chunky = blackice.chunky_buffer()
    lib.render_clear(chunky, CONST["RENDER_COLUMNS_HIGH"])

    column = scratch.columns[3]
    column.tex_id = CONST["TEX_CIRCUIT_LATTICE"]
    column.tex_col = 10
    column.top = 20
    column.rows = 30
    column.tex_v = 0
    column.tex_step = 512
    column.band = 0
    column.side = CONST["SIDE_NS"]
    scratch.columns[3] = column

    lib.render_draw_columns(ctypes.byref(scratch), CONST["RENDER_COLUMNS_HIGH"], chunky)

    written = [y for y in range(blackice.RENDER_H)
               if blackice.chunky_pixel(chunky, 3, y) != CONST["COLOUR_VOID"]]
    assert written, "the column drew nothing"
    assert min(written) >= 20 and max(written) < 50


def test_far_columns_use_the_far_fill_colour(lib):
    """A cut-off column is a flat fill; that is what makes the throttle cheap,
    and DESIGN 5 wants the boundary visible."""
    width = height = 40
    cells = [1 if (x in (0, width - 1) or y in (0, height - 1)) else 0
             for y in range(height) for x in range(width)]
    level = make_level(lib, width, height, cells, (20, 20))
    state = blackice.new_state(lib, level)
    state.throttle = CONST["THROTTLE_UNDERCLOCK"]           # radius 6 in a 40-cell room
    state.detail_level = CONST["DETAIL_COLUMNS_80"]         # and half width, independently
    scratch = blackice.RenderScratch()
    chunky = blackice.chunky_buffer()

    lib.render_frame(ctypes.byref(state), ctypes.byref(scratch), chunky)

    columns = CONST["RENDER_COLUMNS_LOW"]
    far = [c for c in range(columns)
           if scratch.columns[c].tex_id == CONST["COLUMN_TEX_FAR"]]
    assert far, "nothing was cut off at radius 6 in a 40-cell room"
    for c in far:
        assert scratch.wall_dist[c] == CONST["WALL_DIST_NONE"]
        top = scratch.columns[c].top
        assert blackice.chunky_pixel(chunky, c, top) == CONST["COLOUR_FAR_FILL"]


# ---------------------------------------------------------------------------
# c2p against something other than its own inverse
# ---------------------------------------------------------------------------

def test_a_hand_computed_planar_group(lib):
    """Every c2p test above compares the converter with planar_pixel, which is
    the converter's own inverse: both could share a wrong bit order and agree.

    So here is one 16-pixel group worked out by hand.  The ST packs 16 pixels
    as four words, one per plane, leftmost pixel in bit 15; a pixel's colour
    index is bit `plane` of its value across the four planes.
    """
    colours = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    chunky = blackice.chunky_buffer()
    raw = bytearray(chunky.raw)
    for x, colour in enumerate(colours):
        for y in range(blackice.RENDER_H):
            raw[x * blackice.RENDER_H + y] = colour
    chunky.raw = bytes(raw)
    planar = planar_buffer()

    # 160 columns doubles each chunky pixel to two screen pixels, so this group
    # of 16 screen pixels is chunky columns 0..7.
    lib.c2p_window(chunky, CONST["RENDER_COLUMNS_HIGH"], planar)

    screen = [colours[x // 2] for x in range(16)]
    expected = []
    for plane in range(PLANES):
        word = 0
        for bit, colour in enumerate(screen):
            if (colour >> plane) & 1:
                word |= 1 << (15 - bit)
        expected += [word >> 8, word & 0xff]

    assert list(planar.raw[:PLANES * 2]) == expected, "the first planar group is wrong"


def test_c2p_agrees_with_the_art_pipelines_planar_writer(lib):
    """host/c2p.c is a third implementation of the ST's planar format, and the
    art pipeline's is the one the .PI1 files and the real art go through.  Two
    implementations that only ever check themselves are two chances to be
    wrong in the same way, so they are checked against each other."""
    import sys

    sys.path.insert(0, str(blackice.ROOT / "pipeline"))
    import numpy
    from stepix import planar as stepix_planar

    # The engine's screen constants are the pipeline's, or the bytes the
    # platform layer writes are not the bytes the art was built for.
    assert stepix_planar.SCREEN_W == SCREEN_W
    assert stepix_planar.SCREEN_H == CONST["SCREEN_H"]
    assert stepix_planar.PLANES == PLANES
    assert stepix_planar.SCREEN_ROW_BYTES == LINE_BYTES
    assert stepix_planar.SCREEN_BYTES == SCREEN_BYTES

    columns = CONST["RENDER_COLUMNS_HIGH"]
    doubling = SCREEN_W // columns
    chunky = blackice.chunky_buffer()
    raw = bytearray(chunky.raw)
    for x in range(columns):
        for y in range(blackice.RENDER_H):
            raw[x * blackice.RENDER_H + y] = (x * 5 + y * 11 + (x & y)) % CONST["PALETTE_SIZE"]
    chunky.raw = bytes(raw)

    planar = planar_buffer()
    lib.c2p_window(chunky, columns, planar)

    # The same image as a screen-shaped index array, doubled the way c2p does.
    indices = numpy.zeros((WINDOW_LINES, SCREEN_W), dtype=numpy.uint8)
    for y in range(WINDOW_LINES):
        for x in range(SCREEN_W):
            indices[y][x] = raw[(x // doubling) * blackice.RENDER_H + (y // 2)]

    assert bytes(planar.raw[:WINDOW_LINES * LINE_BYTES]) == \
        stepix_planar.indices_to_planar(indices)
