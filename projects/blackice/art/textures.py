"""BLACK ICE wall textures - 8 walls, a door and a sector-key panel, 64x64 indexed.

Design rules every texture obeys, because the renderer doubles pixels 2x2 and then minifies
them again with distance:

  * Nothing thinner than 2 px, and no isolated single pixels.  Structure is 4-8 px.
  * One light direction for the whole mainframe: light from the top-left.  Every raised face
    gets a bright edge top/left and a dark edge bottom/right (see `panel`), so eight unrelated
    patterns still read as one building.
  * Anything spanning the full tile height uses `vertical_panel`, which bevels the sides only:
    a top/bottom bevel would print a hard line across the wall every 64 texels.
  * Vertical period divides 64, so a wall taller than one tile has no seam (`vertical_seam_ok`).
  * Cyan = infrastructure you can use.  Magenta = ICE.  Yellow = data.  Green = safe.
  * No wall may contain a RESERVED sprite colour (white RIM, orange ALERT) - checked in main().
"""

import random

import numpy as np

import drawlib
import palette
import pixelio
from drawlib import Canvas

TEX_SIZE = 64
TEX_MAX = TEX_SIZE - 1
#: The mainframe's structural grid.  Every texture's big features land on it.
CELL = 32
HALF_CELL = CELL // 2
BEVEL = 2
TRIM_HEIGHT = 6
STUD_SIZE = 4
LAMP_SIZE = 6

# --- shared construction -------------------------------------------------------------------


def panel(canvas, x0, y0, x1, y1, face, light, shadow, bevel=BEVEL):
    """A raised slab lit from the top-left - the single lighting rule of the whole world."""
    canvas.rect(x0, y0, x1, y1, face)
    canvas.rect(x0, y0, x1, y0 + bevel - 1, light)
    canvas.rect(x0, y0, x0 + bevel - 1, y1, light)
    canvas.rect(x0, y1 - bevel + 1, x1, y1, shadow)
    canvas.rect(x1 - bevel + 1, y0, x1, y1, shadow)


def vertical_panel(canvas, x0, x1, face, light, shadow, bevel=BEVEL):
    """A full-height slab: side bevels only, so the tile stays seamless top-to-bottom."""
    canvas.rect(x0, 0, x1, TEX_MAX, face)
    canvas.rect(x0, 0, x0 + bevel - 1, TEX_MAX, light)
    canvas.rect(x1 - bevel + 1, 0, x1, TEX_MAX, shadow)


def recess(canvas, x0, y0, x1, y1, hole, lip, bevel=BEVEL):
    """A sunken slot: the hole, plus the machined lip the light catches on its top/left edge.

    The inverse of `panel`, so a recess never reads as a raised slab.  `lip` is a trim colour,
    not a shadow - slate stopped being a shadow colour when it moved to Y 71.8.
    """
    canvas.rect(x0, y0, x1, y1, hole)
    canvas.rect(x0, y0, x1, y0 + bevel - 1, lip)
    canvas.rect(x0, y0, x0 + bevel - 1, y1, lip)


def stud(canvas, x, y, face, core, size=STUD_SIZE):
    """A fastener / via / lamp.  Two colours - the smallest legible detail in the world."""
    canvas.rect(x, y, x + size - 1, y + size - 1, face)
    canvas.rect(x + 1, y + 1, x + size - 2, y + size - 2, core)


def tiled_positions(period, offset=0, span=TEX_SIZE):
    """Feature origins for a pattern of `period`, including the one that wraps the seam."""
    return range(offset - period, span + period, period)


# --- the eight walls -------------------------------------------------------------------------


TRACE_TRIM = 3
VIA_COLUMN_X = 30
VIA_COLUMN_WIDTH = 4
VIA_PITCH = 8
VIA_LENGTH = 6


def circuit_lattice():
    """THE LEDGER's default wall: a bus lattice, chip pads, and one live via column.

    The via column is this texture's band-3 signature.  Data yellow fogs UP into cyan 3, so at
    ten rows the column is the brightest thing on the wall while the lattice itself has
    collapsed to two values - the only reason this does not become bus_trunk at nine cells.
    """
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.GRID)
    trace_width = 6
    for base in tiled_positions(CELL, offset=8):
        canvas.rect(0, base, TEX_MAX, base + trace_width - 1, palette.CYAN_4)
        canvas.rect(0, base, TEX_MAX, base + TRACE_TRIM - 1, palette.CYAN_1)
        canvas.rect(base, 0, base + trace_width - 1, TEX_MAX, palette.CYAN_4)
        canvas.rect(base, 0, base + TRACE_TRIM - 1, TEX_MAX, palette.CYAN_1)
    pad_size = 18
    for cx in (11, 43):
        for cy in (11, 43):
            x0, y0 = cx - pad_size // 2, cy - pad_size // 2
            panel(canvas, x0, y0, x0 + pad_size - 1, y0 + pad_size - 1,
                  palette.CYAN_3, palette.CYAN_1, palette.CYAN_5)
            recess(canvas, cx - 4, cy - 4, cx + 3, cy + 3, palette.CYAN_5, palette.CYAN_4)
    _via_column(canvas)
    return canvas.array


def _via_column(canvas):
    """A full-height chain of live vias: the one feature of this wall that reads at ten rows."""
    canvas.rect(VIA_COLUMN_X - 2, 0, VIA_COLUMN_X + VIA_COLUMN_WIDTH + 1, TEX_MAX, palette.CYAN_5)
    for y in range(0, TEX_SIZE, VIA_PITCH):
        canvas.rect(VIA_COLUMN_X, y, VIA_COLUMN_X + VIA_COLUMN_WIDTH - 1, y + VIA_LENGTH - 1,
                    palette.DATA)


def hex_mesh():
    """Structural mesh - a load-bearing wall.  Flat-top hex rings on the CELL grid."""
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_5)
    radius, shoulder, rise, ring = HALF_CELL, HALF_CELL // 2, 14, 5
    span = range(-CELL * 2, TEX_SIZE + CELL * 2, CELL)
    centres = [(cx, cy) for cx in span for cy in span]
    centres += [(cx + HALF_CELL, cy + HALF_CELL) for cx, cy in list(centres)]
    outer = lambda cx, cy, inset: [(cx - radius + inset, cy),
                                   (cx - shoulder + inset // 2, cy - rise + inset),
                                   (cx + shoulder - inset // 2, cy - rise + inset),
                                   (cx + radius - inset, cy),
                                   (cx + shoulder - inset // 2, cy + rise - inset),
                                   (cx - shoulder + inset // 2, cy + rise - inset)]
    for cx, cy in centres:
        canvas.polygon(outer(cx, cy, 0), palette.CYAN_3)
    for cx, cy in centres:
        canvas.polygon(outer(cx, cy, ring), palette.CYAN_5)
    for cx, cy in centres:
        canvas.polyline([(cx - radius + 1, cy), (cx - shoulder, cy - rise + 1),
                         (cx + shoulder, cy - rise + 1)], palette.CYAN_1, width=BEVEL)
        canvas.polyline([(cx + radius - 1, cy), (cx + shoulder, cy + rise - 1),
                         (cx - shoulder, cy + rise - 1)], palette.CYAN_5, width=BEVEL)
        stud(canvas, cx - STUD_SIZE // 2, cy - STUD_SIZE // 2, palette.CYAN_4, palette.CYAN_2)
    _mesh_diagonals(canvas)
    return canvas.array


DIAGONAL_WIDTH = 6
DIAGONAL_PITCH = 32


def _mesh_diagonals(canvas):
    """Unbroken 45-degree braces - the only diagonal in the whole texture set, and so the one
    thing that still says `hex_mesh` when the rings have fogged into two flat values."""
    # A 45-degree brace entering the bottom-left corner starts a whole tile off the left edge,
    # so the offsets have to run two pitches past the tile in both directions or the corner is
    # missed and the tile is 12 pixels short of its own period.
    overhang = DIAGONAL_WIDTH * 2
    for offset in range(-TEX_SIZE, TEX_SIZE * 2, DIAGONAL_PITCH):
        canvas.line(offset - overhang, -overhang, offset + TEX_SIZE + overhang,
                    TEX_SIZE + overhang, palette.GRID, width=DIAGONAL_WIDTH)


RAIL_TRIM = 5
GLYPH_PITCH = 16
GLYPH_SEED = 0x1CE
GLYPH_RECORDS = 2
GLYPH_BAR_HEIGHT = 3
GLYPH_BARS = 3
GLYPH_MARK_WIDTH = 12


def glyph_column():
    """A data stack: side rails and a recessed channel of machine records you cannot read."""
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_4)
    rail_width = 12
    channel_x0, channel_x1 = rail_width, TEX_MAX - rail_width
    vertical_panel(canvas, 0, rail_width - 1, palette.CYAN_3, palette.CYAN_1, palette.CYAN_5,
                   bevel=RAIL_TRIM)
    vertical_panel(canvas, TEX_MAX - rail_width + 1, TEX_MAX,
                   palette.CYAN_3, palette.CYAN_5, palette.CYAN_5)
    canvas.rect(TEX_SIZE - RAIL_TRIM, 0, TEX_MAX, TEX_MAX, palette.CYAN_1)
    canvas.rect(channel_x0, 0, channel_x1, TEX_MAX, palette.CYAN_5)
    canvas.rect(channel_x0, 0, channel_x0 + BEVEL - 1, TEX_MAX, palette.GRID)
    canvas.rect(channel_x1 - BEVEL + 1, 0, channel_x1, TEX_MAX, palette.GRID)
    #: Two records repeated, not four random ones: a tile whose text never repeats has no
    #: vertical pitch, and a wall taller than one tile then prints a seam where it wraps.
    for slot, row_y in enumerate(range(0, TEX_SIZE, GLYPH_PITCH)):
        record = slot % GLYPH_RECORDS
        _glyph_record(canvas, channel_x0 + 4, row_y + 2, random.Random(GLYPH_SEED + record),
                      live_mark=record)
        canvas.rect(channel_x0 + BEVEL, row_y + GLYPH_PITCH - 3, channel_x1 - BEVEL,
                    row_y + GLYPH_PITCH - 2, palette.GRID)
    for y in tiled_positions(CELL, offset=HALF_CELL - STUD_SIZE // 2):
        stud(canvas, 4, y, palette.CYAN_2, palette.CYAN_5)
        stud(canvas, TEX_SIZE - 8, y, palette.CYAN_2, palette.CYAN_5)
    return canvas.array


def _glyph_record(canvas, x, y, rng, live_mark):
    """One record: three stacked bars of random length - machine data, deliberately not Latin.

    Exactly one mark per record is live data, so the yellow budget is a property of the
    design rather than of whatever the seed happened to roll.
    """
    for slot in range(3):
        origin_x = x + slot * (GLYPH_MARK_WIDTH + 1)
        ink = palette.DATA if slot == live_mark else palette.CYAN_2
        for bar in range(GLYPH_BARS):
            indent = rng.choice((0, 3, 5))
            bar_y = y + bar * (GLYPH_BAR_HEIGHT + 1)
            canvas.rect(origin_x + indent, bar_y, origin_x + GLYPH_MARK_WIDTH - 1,
                        bar_y + GLYPH_BAR_HEIGHT - 1, ink)


RIB_WIDTH = 8
BAR_TRIM = 3


def bus_trunk():
    """Three armoured data buses running floor to ceiling, strapped every CELL.

    Its band-3 signature is three unbroken full-height slate ribs drawn OVER the straps: slate
    fogs up into cyan 4, so at ten rows this wall is three bright columns and nothing else.
    """
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_5)
    bar_width = 16
    bar_gap = (TEX_SIZE - 3 * bar_width) // 4
    strap_height = 10
    bar_origins = [bar_gap + slot * (bar_width + bar_gap) for slot in range(3)]
    for x in bar_origins:
        vertical_panel(canvas, x, x + bar_width - 1, palette.CYAN_4, palette.CYAN_1,
                       palette.CYAN_5, bevel=BAR_TRIM)
    for y in tiled_positions(CELL, offset=6):
        panel(canvas, 0, y, TEX_MAX, y + strap_height - 1,
              palette.CYAN_3, palette.CYAN_3, palette.CYAN_5)
    for x in bar_origins:
        rib_x = x + (bar_width - RIB_WIDTH) // 2
        canvas.rect(rib_x, 0, rib_x + RIB_WIDTH - 1, TEX_MAX, palette.GRID)
        canvas.rect(x, 0, x + BAR_TRIM - 1, TEX_MAX, palette.CYAN_1)
    return canvas.array


CHEVRON_THICKNESS = 14
CHEVRON_SHADOW = 4
CHEVRON_DROP = HALF_CELL


def firewall_chevron():
    """ICE wall: hard magenta chevrons pointing the way you are not allowed to go."""
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.MAG_4)
    for y in tiled_positions(CELL, offset=-6):
        _chevron_band(canvas, y, CHEVRON_THICKNESS + CHEVRON_SHADOW, palette.MAG_5)
        _chevron_band(canvas, y, CHEVRON_THICKNESS, palette.MAG_2)
        _chevron_band(canvas, y, BEVEL + 1, palette.MAG_1)
    for y in tiled_positions(CELL, offset=CELL - 8):
        for x in (HALF_CELL // 2, TEX_SIZE - HALF_CELL // 2 - STUD_SIZE):
            stud(canvas, x, y, palette.MAG_3, palette.MAG_1)
    return canvas.array


def _chevron_band(canvas, y, thickness, ink):
    """A filled V band spanning the tile, apex at the centre column."""
    left, right = -1, TEX_SIZE
    canvas.polygon([(left, y), (HALF_CELL, y + CHEVRON_DROP), (right, y),
                    (right, y + thickness), (HALF_CELL, y + CHEVRON_DROP + thickness),
                    (left, y + thickness)], ink)


def anchor_pylon():
    """A load anchor - Black ICE teleports between four of these.  Green means still holding."""
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_5)
    pylon_x0, pylon_x1 = 12, 51
    core_x0, core_x1 = 25, 38
    vertical_panel(canvas, pylon_x0, pylon_x1, palette.CYAN_4, palette.CYAN_2, palette.CYAN_5)
    canvas.rect(core_x0, 0, core_x1, TEX_MAX, palette.MAG_4)
    canvas.rect(core_x0, 0, core_x0 + BEVEL - 1, TEX_MAX, palette.MAG_5)
    canvas.rect(core_x1 - BEVEL + 1, 0, core_x1, TEX_MAX, palette.MAG_5)
    for y in tiled_positions(CELL, offset=2):
        panel(canvas, pylon_x0 - 4, y, pylon_x1 + 4, y + 9,
              palette.CYAN_3, palette.CYAN_2, palette.CYAN_5)
        canvas.rect(core_x0 + BEVEL, y + BEVEL, core_x1 - BEVEL, y + 7, palette.MAG_2)
        for lamp_x in (pylon_x0 - 1, pylon_x1 - LAMP_SIZE + 2):
            stud(canvas, lamp_x, y + 2, palette.INTEGRITY, palette.CYAN_1, size=LAMP_SIZE)
    for y in tiled_positions(CELL, offset=HALF_CELL):
        canvas.rect(core_x0 + BEVEL, y - 6, core_x1 - BEVEL, y + 5, palette.MAG_1)
        canvas.rect(core_x0 + 4, y - 4, core_x1 - 4, y + 3, palette.MAG_3)
        canvas.rect(core_x0 + 6, y - 2, core_x1 - 6, y + 1, palette.MAG_5)
    return canvas.array


GATE_TRIM = 2


def exit_gate():
    """The Exit Gate.  A green-lit portal in a heavy frame - the only way out of the sector."""
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_4)
    frame_inset = 7
    canvas.rect(0, 0, TEX_MAX, TEX_MAX, palette.CYAN_4)
    canvas.rect(0, 0, BEVEL - 1, TEX_MAX, palette.CYAN_2)
    canvas.rect(TEX_MAX - BEVEL + 1, 0, TEX_MAX, TEX_MAX, palette.CYAN_5)
    recess(canvas, frame_inset, frame_inset, TEX_MAX - frame_inset, TEX_MAX - frame_inset,
           palette.VOID, palette.GRID)
    canvas.outline_rect(frame_inset + 2, frame_inset + 2, TEX_MAX - frame_inset - 2,
                        TEX_MAX - frame_inset - 2, palette.CYAN_5, width=BEVEL)
    arch_x0, arch_x1 = 17, 46
    arch_top, arch_bottom = 16, TEX_MAX - frame_inset - 3
    canvas.rect(arch_x0, arch_top + 6, arch_x1, arch_bottom, palette.INTEGRITY)
    canvas.ellipse(arch_x0, arch_top - 10, arch_x1, arch_top + 22, palette.INTEGRITY)
    canvas.rect(arch_x0 + 5, arch_top + 8, arch_x1 - 5, arch_bottom, palette.VOID)
    canvas.ellipse(arch_x0 + 5, arch_top - 5, arch_x1 - 5, arch_top + 17, palette.VOID)
    for y in range(arch_top + 12, arch_bottom - 2, 9):
        canvas.rect(arch_x0 + 5, y, arch_x1 - 5, y + 3, palette.INTEGRITY)
    canvas.rect(arch_x0 - 4, arch_bottom + 1, arch_x1 + 4, arch_bottom + 3, palette.INTEGRITY)
    for corner_x in (frame_inset - 5, TEX_SIZE - frame_inset + 1):
        for corner_y in (frame_inset - 5, TEX_SIZE - frame_inset + 1):
            stud(canvas, corner_x, corner_y, palette.CYAN_1, palette.CYAN_5)
    canvas.rect(0, 0, TEX_MAX, GATE_TRIM - 1, palette.GRID)
    canvas.rect(0, TEX_SIZE - GATE_TRIM, TEX_MAX, TEX_MAX, palette.GRID)
    return canvas.array


CORRUPT_SEED = 0xDEAD
DRIFT_BAND = 8
#: Rows 0..TRIM_KEEP and the mirror band at the bottom stay intact so the vertical seam holds.
TRIM_KEEP = 8
MAX_DRIFT = 14
WRONG_RAMP_BANDS = 2
WRONG_RAMP_HEIGHT = 12
TEAR_STEP = 4
#: cyan rung -> magenta rung: a band read back through the wrong ramp is *wrong memory*, not dirt.
#: The slate substrate and the data yellow are decoded wrong too - the whole band is, or it is
#: not a decode fault.  This is also what keeps a corrupt wall separable from its clean parent at
#: ten rows, where magenta indices can never collide with cyan ones.
WRONG_RAMP = dict(zip(palette.CYAN_RAMP, palette.MAGENTA_RAMP))
WRONG_RAMP[palette.GRID] = palette.MAG_4
WRONG_RAMP[palette.DATA] = palette.MAG_1


def corrupted_sector():
    """Sector 7.  The lattice, but the memory holding it has rotted."""
    return corrupt(circuit_lattice(), CORRUPT_SEED)


def corrupt(array, seed):
    """Damage a clean texture the way failing memory damages an image.  Deterministic.

    Four named failures, all of them *data* faults rather than dirt:
      grid drift  - whole 8-px row bands displaced sideways, the way a bad DMA read lands
      wrong ramp  - a band decoded through the magenta ramp: the cyan is simply not there
      stuck bits  - one row latched and repeated down the wall
      torn page   - a stepped hole where the page is not mapped at all, edged in slate
    """
    rng = random.Random(seed)
    out = array.copy()
    top, bottom = TRIM_KEEP, TEX_SIZE - TRIM_KEEP
    # Every other band drifts: the undisplaced bands are what makes the damage read as damage
    # to *this* wall rather than as a second, noisier texture.
    for index, band_y in enumerate(range(top, bottom, DRIFT_BAND)):
        if index % 2:
            continue
        drift = rng.randrange(-MAX_DRIFT, MAX_DRIFT + 1)
        out[band_y:band_y + DRIFT_BAND] = np.roll(out[band_y:band_y + DRIFT_BAND], drift, axis=1)
    for _ in range(WRONG_RAMP_BANDS):
        _wrong_ramp_band(out, rng.randrange(top, bottom - WRONG_RAMP_HEIGHT), WRONG_RAMP_HEIGHT)
    stuck_y = rng.randrange(top, bottom - DRIFT_BAND)
    out[stuck_y:stuck_y + DRIFT_BAND] = out[stuck_y:stuck_y + 1]
    _torn_page(out, rng)
    return out


def _wrong_ramp_band(array, y, height):
    band = array[y:y + height]
    for cyan, magenta in WRONG_RAMP.items():
        band[band == cyan] = magenta


def _torn_page(array, rng):
    """A hole with a stepped left edge: pages fail on a boundary, never on a smooth curve."""
    height, width = DRIFT_BAND * 2, DRIFT_BAND * 2
    y0 = rng.randrange(TRIM_KEEP + DRIFT_BAND, TEX_SIZE - TRIM_KEEP - height)
    x0 = rng.randrange(TEAR_STEP, TEX_SIZE - width - TEAR_STEP)
    for step, row in enumerate(range(y0, y0 + height, TEAR_STEP)):
        left = x0 + (TEAR_STEP if step % 2 else 0)
        array[row:row + TEAR_STEP, left:x0 + width] = palette.VOID
        array[row:row + TEAR_STEP, left:left + BEVEL] = palette.GRID
    array[y0 + height - BEVEL:y0 + height, x0:x0 + width] = palette.GRID


# --- door and key panel ----------------------------------------------------------------------
HAZARD_PITCH = 16


def door():
    """A sliding bulkhead.  Two leaves, a lit seam, and hazard bands you read at 30 metres."""
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_4)
    seam_x = HALF_CELL
    hazard_height = 12
    vertical_panel(canvas, 0, seam_x - 1, palette.CYAN_4, palette.CYAN_2, palette.CYAN_5)
    vertical_panel(canvas, seam_x, TEX_MAX, palette.CYAN_4, palette.CYAN_2, palette.CYAN_5)
    for y in (10, TEX_SIZE - 10 - hazard_height):
        _hazard_band(canvas, y, hazard_height)
    canvas.rect(seam_x - BEVEL, 0, seam_x + BEVEL - 1, TEX_MAX, palette.CYAN_5)
    canvas.rect(seam_x - 1, 0, seam_x, TEX_MAX, palette.CYAN_1)
    plate_y = HALF_CELL - 7
    panel(canvas, seam_x - 15, plate_y, seam_x + 14, plate_y + 13,
          palette.CYAN_3, palette.CYAN_2, palette.CYAN_5)
    canvas.rect(seam_x - 11, plate_y + 4, seam_x + 10, plate_y + 9, palette.DATA)
    canvas.rect(seam_x - 1, plate_y + 4, seam_x, plate_y + 9, palette.CYAN_5)
    canvas.rect(0, 0, TEX_MAX, BEVEL - 1, palette.GRID)
    canvas.rect(0, TEX_SIZE - BEVEL, TEX_MAX, TEX_MAX, palette.GRID)
    return canvas.array


def _hazard_band(canvas, y, height):
    """Diagonal yellow/slate hazard stripes - the one place a wall is allowed to shout."""
    canvas.rect(0, y, TEX_MAX, y + height - 1, palette.GRID)
    for x in tiled_positions(HAZARD_PITCH):
        canvas.polygon([(x, y + height - 1), (x + height, y),
                        (x + height + HAZARD_PITCH // 2, y),
                        (x + HAZARD_PITCH // 2, y + height - 1)], palette.DATA)
    canvas.rect(0, y, TEX_MAX, y + BEVEL - 1, palette.CYAN_2)
    canvas.rect(0, y + height - BEVEL, TEX_MAX, y + height - 1, palette.CYAN_5)


READER_INSET = 6
READER_SCAN_PITCH = 16
KEYWAY_WIDTH = 4
LOCK_LAMP_SIZE = 8


def sector_key_panel():
    """The token reader beside a locked gate.  Three lamps; you need all three to leave.

    Deliberately the inverse of `door`: the door's yellow is two horizontal hazard bands, this
    panel's yellow is one vertical keyway.  They were 51.9% identical at band 2 as a functional
    confusion between what you walk through and what needs a key.
    """
    canvas = Canvas(TEX_SIZE, TEX_SIZE, palette.CYAN_5)
    panel(canvas, 0, 0, TEX_MAX, TEX_MAX, palette.CYAN_4, palette.CYAN_1, palette.CYAN_5)
    canvas.rect(READER_INSET, 0, TEX_MAX - READER_INSET, TEX_MAX, palette.CYAN_1)
    canvas.rect(READER_INSET, 0, READER_INSET + BEVEL - 1, TEX_MAX, palette.CYAN_2)
    canvas.rect(TEX_SIZE - READER_INSET - BEVEL, 0, TEX_MAX - READER_INSET, TEX_MAX,
                palette.CYAN_2)
    for scan_y in range(4, TEX_SIZE, READER_SCAN_PITCH):
        canvas.rect(READER_INSET + BEVEL, scan_y, TEX_MAX - READER_INSET - BEVEL, scan_y + 1,
                    palette.CYAN_2)
    keyway_x = HALF_CELL - KEYWAY_WIDTH // 2 - 2
    recess(canvas, keyway_x - 4, 6, keyway_x + KEYWAY_WIDTH + 3, TEX_MAX - 6,
           palette.CYAN_5, palette.CYAN_1)
    canvas.rect(keyway_x, 10, keyway_x + KEYWAY_WIDTH - 1, TEX_MAX - 10, palette.DATA)
    canvas.rect(keyway_x - 2, HALF_CELL - 3, keyway_x + KEYWAY_WIDTH + 1, HALF_CELL + 2,
                palette.DATA)
    #: two tokens read, the third still missing - the panel states the objective by itself
    for slot, present in enumerate((True, True, False)):
        lamp_y = 14 + slot * (LOCK_LAMP_SIZE + 8)
        for lamp_x in (7, TEX_SIZE - 7 - LOCK_LAMP_SIZE):
            stud(canvas, lamp_x, lamp_y, palette.INTEGRITY if present else palette.MAG_2,
                 palette.CYAN_5, size=LOCK_LAMP_SIZE)
    canvas.rect(0, 0, TEX_MAX, BEVEL - 1, palette.GRID)
    canvas.rect(0, TEX_SIZE - BEVEL, TEX_MAX, TEX_MAX, palette.GRID)
    return canvas.array


# --- registry --------------------------------------------------------------------------------
WALL_BUILDERS = (
    ("circuit_lattice", circuit_lattice),
    ("hex_mesh", hex_mesh),
    ("glyph_column", glyph_column),
    ("bus_trunk", bus_trunk),
    ("firewall_chevron", firewall_chevron),
    ("corrupted_sector", corrupted_sector),
    ("anchor_pylon", anchor_pylon),
    ("exit_gate", exit_gate),
)
EXTRA_BUILDERS = (
    ("door", door),
    ("sector_key_panel", sector_key_panel),
)
ALL_BUILDERS = WALL_BUILDERS + EXTRA_BUILDERS


def build_all():
    """name -> 64x64 index array, in ledger order."""
    return {name: builder() for name, builder in ALL_BUILDERS}


# --- the band-agreement gate ------------------------------------------------------------------
# Two textures that resolve to the same pixels at distance are one material, and three sectors
# built from them are one place.  This measures it at the size a wall actually occupies on
# screen, sampling the way the raycaster samples: nearest-neighbour, no filtering.
BAND_SAMPLE_COLUMNS = 32
#: On-screen wall height in rows at each band, taken from the raycaster's own projection.
BAND_SAMPLE_ROWS = {0: 60, 1: 26, 2: 15, 3: 10, 4: 7}
#: Above this two walls are the same material.  Two 2-value images agree ~50% by chance, so the
#: headroom here is deliberately thin: it is a floor on *positional* difference, not on colour.
MAX_BAND_AGREEMENT = 0.60
AGREEMENT_GATE_BANDS = (2, 3)


def sampled(array, band):
    """A texture as the renderer would show it at `band`: shaded, then point-sampled small."""
    shaded = drawlib.shade(array, band)
    rows, columns = BAND_SAMPLE_ROWS[band], BAND_SAMPLE_COLUMNS
    row_index = (np.arange(rows) * array.shape[0]) // rows
    column_index = (np.arange(columns) * array.shape[1]) // columns
    return shaded[np.ix_(row_index, column_index)]


def band_agreement(array_a, array_b, band):
    """Fraction of identical pixels between two textures at one band.  1.0 = same material."""
    return float((sampled(array_a, band) == sampled(array_b, band)).mean())


def agreement_pairs(band, tiles=None):
    """[(agreement, name_a, name_b), ...] for every texture pair, worst first."""
    tiles = tiles if tiles is not None else build_all()
    names = list(tiles)
    return sorted(((band_agreement(tiles[a], tiles[b], band), a, b)
                   for index, a in enumerate(names) for b in names[index + 1:]), reverse=True)


def agreement_failures(band, tiles=None):
    return [row for row in agreement_pairs(band, tiles) if row[0] > MAX_BAND_AGREEMENT]


#: A deliberately aperiodic tile qualifies on its wrap band instead, measured against the
#: clean tile it was damaged from.  Everything else must be periodic on its own.
SEAM_REFERENCE = {"corrupted_sector": circuit_lattice()}


def reserved_colours_used(array):
    """The RESERVED sprite-only colours a wall must never contain.  Empty list = legal."""
    used = set(drawlib.indices_used(array))
    return [palette.PALETTE[index].name for index in sorted(used & set(palette.SPRITE_ONLY))]


def main():
    pixelio.ensure_dirs()
    built = build_all()
    failures = 0
    print("texture            bytes  v-period  seam  reserved check     indices")
    for name, array in built.items():
        seam_ok, period = drawlib.vertical_seam_ok(array, SEAM_REFERENCE.get(name))
        illegal = reserved_colours_used(array)
        failures += (not seam_ok) + bool(illegal)
        pixelio.save(array, "tex_" + name)
        print("  %-17s %5d  %8s  %-5s %-18s %s"
              % (name, array.size, period if period else "wrap-band",
                 "OK" if seam_ok else "SEAM!",
                 "clean" if not illegal else "USES " + ",".join(illegal),
                 ",".join(str(i) for i in drawlib.indices_used(array))))
    total = sum(array.size for array in built.values())
    print("total %d textures = %d bytes (byte per texel), %d bytes nibble-packed"
          % (len(ALL_BUILDERS), total, total // 2))
    print()
    print("band agreement (identical pixels at %d columns x the band's own wall height)"
          % BAND_SAMPLE_COLUMNS)
    for band in AGREEMENT_GATE_BANDS:
        rows = agreement_pairs(band, built)
        bad = [row for row in rows if row[0] > MAX_BAND_AGREEMENT]
        failures += len(bad)
        print("  band %d (%2d rows): worst 5 of %d pairs, gate <= %.0f%%"
              % (band, BAND_SAMPLE_ROWS[band], len(rows), MAX_BAND_AGREEMENT * 100))
        for agreement, name_a, name_b in rows[:5]:
            print("    %5.1f%%  %-18s %-18s %s"
                  % (agreement * 100, name_a, name_b,
                     "FAIL" if agreement > MAX_BAND_AGREEMENT else "ok"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
