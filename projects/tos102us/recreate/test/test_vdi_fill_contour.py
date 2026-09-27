"""The contour (seed) fill (`src/vdi/fill.c`): $a00f ($fd08f4) and its helpers fill_span ($fcfb54),
end_pts ($fcfb66), crunch_queue ($fd0dc8) and get_seed ($fd0e22); v_contourfill ($fd08e0, opcode 103) and
v_get_pixel ($fd0fde, opcode 105).

    $fd08f4  seed inside the clip; SEARCH_COLOR = intin[0]'s pen & the plane mask (SEED_TYPE 0: fill up to
             that colour) or, intin[0] < 0, the seed pixel's (SEED_TYPE 1: fill that colour's region);
             end_pts the seed's run, queue it going DOWN, walk it going UP; then take records round-robin
             and fill each, seeding its neighbour row and turning back under every overhang
    $fd0e22  end_pts; a twin already queued (same row, other way, same left) is drawn and taken; else
             into the first hole or on top, a full queue (QTOP > 1920) ending the fill
    $fd0dc8  empty top records dropped; the taker wrapped, SEEDABORT asked

The canvases are SHAPES: a closed box, a U whose fill must turn back up its other arm, an S of two such
turns, an island inside a ring, a random 2-colour field whose clusters are every shape at once, a region
open to the clip's edges, and a comb 1,280 pixels wide whose teeth overflow the queue.

UNPINNED, and why. crunch_queue's top index is a LONG (`movea.w` / `subq.w #3,a0`), which only a QTOP of
$8000..$8002 over a lower QBOTTOM takes past a word — to $ff16fc..$ff1704, where the machine bus-errors, so
no case stages it (`fill.c`, `queue_word`). A fill that never ends by itself (a pattern, or the seed colour
filled with itself) is bounded by SEEDABORT only, so those cases run without the attribution pass and SEED
what the fill writes instead (`seeded`).

THE STRICT MUTATION SWEEP (`recreate/README.md`, "Mutation sweeps"): the survivors are take_record's wrap of a
taker that skipped to QTOP (unreachable: every path that empties the top record crunches it, so the top is
never empty when a record is taken); crunch_queue's bound tested before the queue word (the difference is one
READ); and the long queue index and its 24-bit wrap (the I/O-page reach above). Mutants that make the fill
NEVER END (a direction, a twin test, DONE or the crunch dropped) spin the reconstruction past the sweep's
timeout, and one that leaves FILL_INT uncleared aborts on its own out-of-range sort: ABNORMAL by the strict
rule, not counted as kills.
"""
import random

import pytest

from harness import BASE_IMAGE, addrs

import case
import staging
import vdi
import vdi_fill
import vdi_raster
from case import merge_pokes

PLANES, WIDTH, HEIGHT = vdi.SCREEN.planes, vdi.SCREEN.width, vdi.SCREEN.height
PIXELS_PER_GROUP = vdi.PIXELS_PER_GROUP
MAP_COL = [vdi.rom_word(vdi.VDI_MAP_COL + index * vdi.WORD_BYTES) for index in range(vdi.VDI_MAP_COL_ENTRIES)]
DEV_TAB_COLOURS = vdi.LINEA_DEV_TAB + vdi.VDI_DEV_TAB_COLOURS_INDEX * vdi.WORD_BYTES
INQ_TAB_PLANES = vdi.LINEA_INQ_TAB + vdi.VDI_INQ_TAB_PLANES_INDEX * vdi.WORD_BYTES
SAME_COLOUR = -1                    # intin[0] < 0: fill the seed pixel's colour
LINEA_OPCODE = 15                   # $a00f


# ---- canvases --------------------------------------------------------------------------------------------

def screen_bytes(colour_at, *, planes=PLANES, width=WIDTH, height=HEIGHT, bytes_per_line=None):
    """The framebuffer whose pixel (x, y) is `colour_at(x, y)`, `planes` interleaved words a group."""
    bytes_per_line = bytes_per_line or width // PIXELS_PER_GROUP * planes * vdi.WORD_BYTES
    out = bytearray(bytes_per_line * height)
    for y in range(height):
        for group in range(width // PIXELS_PER_GROUP):
            colours = [colour_at(group * PIXELS_PER_GROUP + column, y) for column in range(PIXELS_PER_GROUP)]
            for plane in range(planes):
                word = sum(1 << (15 - column) for column, colour in enumerate(colours) if colour >> plane & 1)
                at = y * bytes_per_line + (group * planes + plane) * vdi.WORD_BYTES
                out[at:at + vdi.WORD_BYTES] = word.to_bytes(vdi.WORD_BYTES, "big")
    return {vdi.SCREEN.base: bytes(out)}


def outlined(boxes, pen, background):
    """Rectangle OUTLINES in `pen` over `background`: `boxes` is [(x1, y1, x2, y2), ...]."""
    def colour_at(x, y):
        for x1, y1, x2, y2 in boxes:
            if (x in (x1, x2) and y1 <= y <= y2) or (y in (y1, y2) and x1 <= x <= x2):
                return pen
        return background
    return colour_at


BOUNDARY_INDEX = 6                  # VDI colour 6: pen MAP_COL[6]
BOUNDARY = MAP_COL[BOUNDARY_INDEX]
BACKGROUND = 0b1010
# A U: two arms up from a floor under both — the fill from the left arm goes down, across and back UP the
# right. The boxes OVERLAP, so the walls between them are open (see `shape`).
U_SHAPE = [(40, 30, 60, 150), (40, 130, 160, 150), (140, 30, 160, 150)]
# An S: the U's right arm opening into a second U hung upside down.
S_SHAPE = [(20, 40, 40, 160), (20, 140, 120, 160), (100, 20, 120, 160), (100, 20, 200, 40), (180, 20, 200, 180)]


def shape(boxes):
    """The union of `boxes` as a region of BACKGROUND walled in BOUNDARY, on a BOUNDARY screen."""
    def colour_at(x, y):
        inside = [(x1, y1, x2, y2) for x1, y1, x2, y2 in boxes if x1 <= x <= x2 and y1 <= y <= y2]
        if not inside:
            return BOUNDARY
        edge = all(x in (x1, x2) or y in (y1, y2) for x1, y1, x2, y2 in inside)
        return BOUNDARY if edge else BACKGROUND
    return colour_at


def ring_with_island(x, y):
    """A ring 20 pixels thick round a hollow, with an island in the hollow."""
    ring = 40 <= x <= 280 and 30 <= y <= 180 and not (60 <= x <= 260 and 50 <= y <= 160)
    island = 120 <= x <= 200 and 90 <= y <= 120
    return BOUNDARY if ring or island else BACKGROUND


RANDOM_SEED = 0xC0_A00F


def random_field(density, seed=RANDOM_SEED, *, pens=(BOUNDARY, BACKGROUND), width=WIDTH, height=HEIGHT):
    """Each pixel the first of `pens` with probability `density`, else the second — clusters of every shape."""
    rows = random.Random(seed)
    grid = [[pens[0] if rows.random() < density else pens[1] for _ in range(width)] for _ in range(height)]
    return lambda x, y: grid[y][x]


# Half the pixels boundary: the background is below its percolation threshold, so its clusters are
# finite and of every shape; the seed is a background pixel of one of the larger ones.
RANDOM_DENSITY = 0.45
CANVASES = {"box": outlined([(40, 30, 150, 110)], BOUNDARY, BACKGROUND), "U": shape(U_SHAPE), "S": shape(S_SHAPE),
            "ring": ring_with_island, "random": random_field(RANDOM_DENSITY)}
SEEDS = {"box": (70, 60), "U": (50, 60), "S": (30, 60), "ring": (80, 70), "random": (160, 100)}
_SCREENS = {}


def canvas(name):
    if name not in _SCREENS:
        _SCREENS[name] = screen_bytes(CANVASES[name])
    return _SCREENS[name]


# ---- the call ---------------------------------------------------------------------------------------------

def contour_pokes(screen, seed, index, *, colour=0b0110, clip=vdi_fill.DESKTOP_CLIP, pattern="solid", mode="replace",
                  seedabort=None, extra=None):
    """A contour fill from `seed` for intin[0] = `index`, over `screen`: the fill attributes dispatched,
    SEEDABORT at the ROM's default unless the case names its own."""
    work = vdi_fill.fill_workstation(colour=colour, mode=mode, pattern=pattern, clip=clip, onto=screen)
    call = vdi.function_pokes("VDI_ROM_V_CONTOURFILL", intin=(index,), ptsin=seed, workstation_pokes=work)
    return merge_pokes(call, seedabort or vdi_fill.default_seedabort_pokes(), extra)


FILL_INSNS = 60_000_000


def run(pokes, **kwargs):
    return vdi_fill.run_contour(pokes, max_insns=FILL_INSNS, **kwargs)


# A fill that never ends by itself is bounded by the countdown stub — whose counter is a byte the run
# writes, which the attribution pass pre-inverts: from 0 it counts down 65,535 calls, far past the budget.
# So those cases run without that pass, and every store they make is still compared by the plain one.
UNBOUNDED_WITHOUT_ITS_COUNTER = {"poison": False}
# ...which cannot see a store the reconstruction SKIPPED where the byte already held what the ROM stores. So
# such a case seeds what the fill writes — its variables, the queue and the scratch under them — with a
# byte no store of the fill leaves, and the case's own pokes go over it.
FILL_VARIABLES_AND_QUEUE = {vdi.VDI_SCRATCH: bytes([vdi.FILL]) * (vdi_fill.QUEUE_END - vdi.VDI_SCRATCH)}


def seeded(pokes):
    return merge_pokes(FILL_VARIABLES_AND_QUEUE, pokes)


def filled(result, seed, pen):
    return result.pixel(*seed) == pen


# A pixel each fill must reach the long way round: up the U's other arm, the S's last one, the far side
# of the ring's island (the random field's cluster is its own claim: the seed).
FAR = {"box": (140, 100), "U": (150, 60), "S": (190, 170), "ring": (230, 150), "random": SEEDS["random"]}


@pytest.mark.parametrize("name", CANVASES)
def test_up_to_the_boundary_colour(name):
    result = run(contour_pokes(canvas(name), SEEDS[name], BOUNDARY_INDEX))
    assert filled(result, SEEDS[name], 0b0110) and filled(result, FAR[name], 0b0110)
    assert result.linea("SEEDABORT") == addrs.LINEA_ROM_SEEDABORT_DEFAULT


@pytest.mark.parametrize("name", CANVASES)
def test_the_seed_colour_s_region(name):
    result = run(contour_pokes(canvas(name), SEEDS[name], SAME_COLOUR, colour=0b0011))
    assert filled(result, SEEDS[name], 0b0011)


@pytest.mark.parametrize("mode", vdi_raster.MODES)
def test_every_write_mode_over_a_pattern(mode):
    """The boundary mode with a pattern: the pixels a pass draws are not the boundary pen, so later
    passes find them fillable again and the fill never ends by itself — SEEDABORT, 30 passes in, is
    what stops it. Every write mode's span and the twin search over re-queued runs are exercised."""
    run(seeded(contour_pokes(canvas("U"), SEEDS["U"], BOUNDARY_INDEX, pattern="8 rows", mode=mode, colour=0b0101,
                             seedabort=vdi_fill.countdown_pokes(30))), **UNBOUNDED_WITHOUT_ITS_COUNTER)


# Two random fields, found by search, whose fill in a 16 x 10 window ENDS on a turn-back whose run reaches
# exactly one pixel past the new span — the case the turn's `NEWXLEFT - 1 > XLEFT` (and the right-hand
# `NEWXRIGHT + 1 < XRIGHT`) is strict for: the last pass's variables are what the fill leaves.
SMALL_WINDOW = (40, 40, 55, 49)
ONE_PIXEL_TURNS = {"left": 295, "right": 40}
ONE_PIXEL_TURN_DENSITY = 0.3


@pytest.mark.parametrize("side", ONE_PIXEL_TURNS)
def test_a_turn_back_one_pixel_past_the_span(side):
    field = screen_bytes(random_field(ONE_PIXEL_TURN_DENSITY, seed=ONE_PIXEL_TURNS[side]))
    run(contour_pokes(field, (42, 42), SAME_COLOUR, colour=0b0011, clip=SMALL_WINDOW))


def test_a_region_open_to_the_clip_edges():
    """No boundary at all: the fill stops at XMINCL..XMAXCL, YMINCL..YMAXCL, whose outside pixels the
    walk still reads (x = -1 is the row above's last group)."""
    screen = screen_bytes(lambda x, y: BACKGROUND if (x // 40 + y // 40) % 2 else 0b0001)
    run(contour_pokes(screen, (20, 20), BOUNDARY_INDEX, clip=(0, 0, WIDTH - 1, HEIGHT - 1)))
    run(contour_pokes(screen, (70, 70), SAME_COLOUR, clip=(33, 17, 250, 150)))


@pytest.mark.parametrize("seed", ((10, 5), (400, 50), (-3, 50), (50, 250)), ids=("above", "right", "left", "below"))
def test_a_seed_outside_the_clip_fills_nothing(seed):
    result = run(contour_pokes(canvas("box"), seed, BOUNDARY_INDEX))
    assert not any(vdi.SCREEN.base <= at < vdi.SCREEN.base + vdi.SCREEN.bytes for at in result.info["writes"])


# A seed ON each clip edge is inside: the four bounds are strict (`blt`/`bgt`).
SEEDS_ON_THE_CLIP = {"XMINCL": ((70, 60), (70, 11, 319, 199)), "XMAXCL": ((140, 60), (0, 11, 140, 199)),
                     "YMINCL": ((70, 60), (0, 60, 319, 199)), "YMAXCL": ((70, 60), (0, 11, 319, 60))}


@pytest.mark.parametrize("seed, clip", SEEDS_ON_THE_CLIP.values(), ids=SEEDS_ON_THE_CLIP.keys())
def test_a_seed_on_the_clip_edge_fills(seed, clip):
    run(contour_pokes(canvas("box"), seed, BOUNDARY_INDEX, clip=clip))


def test_colour_index_0_fills_up_to_pen_0():
    """0 is not negative (`bge`): a pen to fill up to, MAP_COL[0], not the seed's own colour."""
    screen = screen_bytes(outlined([(40, 30, 150, 110)], MAP_COL[0], BACKGROUND))
    run(contour_pokes(screen, SEEDS["box"], 0))


@pytest.mark.parametrize("index", (16, 0x7FFF), ids=("the colour count", "large"))
def test_a_colour_index_at_or_past_the_count_fills_nothing(index):
    run(contour_pokes(canvas("box"), SEEDS["box"], index))


def test_a_seed_on_the_boundary_colour_queues_its_run_and_stops():
    """end_pts answers 0 (the run IS the boundary colour): the queue is set up, and nothing drawn."""
    result = run(contour_pokes(canvas("box"), (40, 60), BOUNDARY_INDEX))
    assert result.word(vdi_fill.VDI_FILL_GOTSEED) == 0


def test_a_colour_count_past_the_table_and_a_zero_plane_count():
    """DEV_TAB[13] and INQ_TAB[4] are staged: index 20 reads past MAP_COL, and a plane count of 0 masks
    with the word before the mask table — VDI_PATTERN_SOLID's $ffff."""
    run(contour_pokes(canvas("box"), SEEDS["box"], 20, extra={DEV_TAB_COLOURS: (40).to_bytes(2, "big"),
                                                             INQ_TAB_PLANES: bytes(2)}))


def test_through_the_line_a_exception():
    """`dc.w $a00f`, as a program calls it — SEEDABORT its own business, here the countdown stub."""
    pokes = contour_pokes(canvas("box"), SEEDS["box"], BOUNDARY_INDEX, seedabort=vdi_fill.countdown_pokes(3))
    vdi_fill.hooked_run(vdi.STUB_AT, merge_pokes(pokes, vdi.exception_stub_pokes(LINEA_OPCODE)),
                        lambda _lib_, buf: vdi_fill.contour_core()(buf), width=None, max_insns=FILL_INSNS)


# ---- SEEDABORT --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("calls", (1, 3, 8))
def test_seedabort_stops_the_fill_on_its_nth_call(calls):
    result = run(contour_pokes(canvas("S"), SEEDS["S"], BOUNDARY_INDEX, seedabort=vdi_fill.countdown_pokes(calls)))
    assert result.word(vdi_fill.VDI_FILL_DONE) == vdi_fill.ABORT_ANSWER
    assert result.word(vdi_fill.COUNTER_AT) == 0


def test_seedabort_bounds_a_fill_that_would_never_end():
    """The seed colour's region filled with a pattern that leaves that colour in it: every pass re-finds
    the pixels it left, so only SEEDABORT ends the fill — which is what the vector is for."""
    run(seeded(contour_pokes(canvas("box"), SEEDS["box"], SAME_COLOUR, colour=BACKGROUND ^ 0b1111, pattern="8 rows",
                             seedabort=vdi_fill.countdown_pokes(40))), **UNBOUNDED_WITHOUT_ITS_COUNTER)


# ---- the queue overflows: a comb 1,280 pixels wide -------------------------------------------------------
# One plane and 160 bytes a line make the screen 1,280 x 200 — Line-A takes PLANES and BYTES_LIN from its
# caller. A spine across row 100 with a one-pixel tooth up at every even x: the first pass up queues a
# record per tooth, and the 640th finds QTOP past 1,920.
WIDE = (1, 160)
WIDE_WIDTH = 1280
SPINE = 100


def comb(x, y):
    return 0 if y == SPINE or x % 2 == 0 else 1


def wide_comb_pokes():
    screen = screen_bytes(comb, planes=1, width=WIDE_WIDTH)
    geometry = merge_pokes(vdi_raster.geometry_pokes(WIDE), {INQ_TAB_PLANES: (1).to_bytes(2, "big")})
    return contour_pokes(screen, (500, SPINE), SAME_COLOUR, colour=1, clip=(0, 0, WIDE_WIDTH - 1, HEIGHT - 1),
                         extra=geometry)


def test_the_queue_overflows():
    result = run(wide_comb_pokes())
    assert result.word(vdi_fill.VDI_FILL_DONE) == 1
    assert result.word(vdi_fill.VDI_FILL_QTOP) > vdi_fill.VDI_FILL_QUEUE_LAST


# ---- a span wider than a word: the walks' compares are SIGNED ------------------------------------------------
# One plane, 80 bytes a line, and a clip of -17,000..16,000: the seed row's run is 33,000 pixels wide (the
# walk reads on through the rows either side), and one pixel of pen 1 — row 199's x = -17,000 — makes the
# neighbour row's first run end there, 33,000 short of OLDXRIGHT. `cmp.w` / `blt` keeps walking; the sign
# of the wrapped word difference would stop. The countdown ends it on SEEDABORT's first call.
WIDE_SPAN_BLOCKER = (280, 172)


def test_the_walks_compare_across_a_span_wider_than_a_word():
    screen = screen_bytes(lambda x, y: 1 if (x, y) == WIDE_SPAN_BLOCKER else 0, planes=1, width=640, height=400)
    geometry = merge_pokes(vdi_raster.geometry_pokes(vdi_raster.HIGH), {INQ_TAB_PLANES: (1).to_bytes(2, "big")})
    run(seeded(contour_pokes(screen, (0, 200), SAME_COLOUR, colour=1, clip=(-17000, 0, 16000, 399),
                             seedabort=vdi_fill.countdown_pokes(1), extra=geometry)), **UNBOUNDED_WITHOUT_ITS_COUNTER)


# ---- v_contourfill ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ("ring", "S"))
@pytest.mark.parametrize("index", (BOUNDARY_INDEX, SAME_COLOUR), ids=("up to a colour", "the seed's colour"))
def test_v_contourfill_installs_the_never_abort_routine(name, index):
    """Over a SEEDABORT that would stop the fill on its first call: v_contourfill replaces it first."""
    pokes = contour_pokes(canvas(name), SEEDS[name], index, seedabort=vdi_fill.countdown_pokes(1))
    result = vdi.run_function("VDI_ROM_V_CONTOURFILL", pokes, max_insns=FILL_INSNS)
    assert result.linea("SEEDABORT") == addrs.LINEA_ROM_SEEDABORT_DEFAULT


# ---- the helpers entered directly --------------------------------------------------------------------------
XLEFT_AT, XRIGHT_AT, COLLIDE_AT = vdi_fill.VDI_FILL_NEWXLEFT, vdi_fill.VDI_FILL_NEWXRIGHT, vdi_fill.VDI_FILL_COLLISION


def search_pokes(seed_type, search):
    return {vdi_fill.VDI_FILL_SEED_TYPE: vdi.pack_words(seed_type, search)}


@pytest.mark.parametrize("point", ((70, 60), (0, 20), (319, 20), (41, 31), (5, 199), (60, 11), (60, 10), (60, 200)),
                         ids=("inside", "left edge", "right edge", "corner", "last row", "YMINCL", "above", "below"))
@pytest.mark.parametrize("seed_type", (0, 1))
def test_end_pts(point, seed_type):
    """The run through (x, y), both walks, answered against SEARCH_COLOR by SEED_TYPE; a row outside
    YMINCL..YMAXCL answers 0 and stores nothing."""
    screen = screen_bytes(random_field(0.2, seed=point[0] * 1000 + point[1]))
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=screen), search_pokes(seed_type, BACKGROUND),
                        {XLEFT_AT: vdi.pack_words(0x5A5A, 0x5A5A)})
    vdi_fill.run_call("LINEA_ROM_END_PTS", (*point, XLEFT_AT, XRIGHT_AT), pokes)


def test_end_pts_bounds_the_top_on_the_word_difference():
    """`cmp.w YMINCL,d1 / bmi`: with YMINCL = -32700, row 100 is 32,800 below it — a word difference whose
    sign bit is set, so the row is refused though a signed compare has it inside the clip."""
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=canvas("box"), clip=(0, -32700, 319, 199)),
                        search_pokes(0, BOUNDARY), {XLEFT_AT: vdi.pack_words(0x5A5A, 0x5A5A)})
    result = vdi_fill.run_call("LINEA_ROM_END_PTS", (60, 100, XLEFT_AT, XRIGHT_AT), pokes)
    assert vdi_fill.answer(result) == 0 and result.words(XLEFT_AT, 2) == [0x5A5A, 0x5A5A]


@pytest.mark.parametrize("planes", ((vdi_raster.MEDIUM, 2), (vdi_raster.HIGH, 1)), ids=("medium", "high"))
def test_end_pts_fewer_planes(planes):
    shape_, count = planes
    bytes_per_line = shape_[1]
    width, height = bytes_per_line * 8 // count, vdi.SCREEN.bytes // bytes_per_line
    screen = screen_bytes(random_field(0.2, pens=(1, 0), width=width, height=height), planes=count, width=width,
                          height=height)
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=1, onto=screen), vdi_raster.geometry_pokes(shape_),
                        search_pokes(1, 0))
    vdi_fill.run_call("LINEA_ROM_END_PTS", (60, 50, XLEFT_AT, XRIGHT_AT), pokes)


# PLANES $4000..$7fff: `adda.w a3,a3` makes the group step a NEGATIVE word, and every pixel read leaves A5
# 64K lower than it found it; 0 reads 65,536 planes and leaves it 128K lower; $8000 steps 0. A caller-writable
# Line-A field. A read's colour is its LAST sixteen words — the lowest, 64K or 128K under where A5 started —
# so the seed's read and the next one land two RUNGS apart (64K -> 128K, or 128K -> 256K under the screen):
# rungs set, clear, set make that next pixel a different colour, where a walk re-reading the seed's window
# would find the same one. The walk is kept to four pixels (XMAXCL 3).
PLANE_STEP_RUNG = 0x10000
PLANE_STEP_RUNG_BYTES = 0x20
RUNG_FILL = {1: 0xFF, 2: 0x00, 4: 0xFF}         # rung -> the byte it is filled with
RUNGS = {staging.HIGH_BANDS.claim(vdi.SCREEN.base - rung * PLANE_STEP_RUNG, PLANE_STEP_RUNG_BYTES,
                                  "test_vdi_fill_contour.py: end_pts' reads under the screen"):
         bytes([byte]) * PLANE_STEP_RUNG_BYTES for rung, byte in RUNG_FILL.items()}


@pytest.mark.parametrize("planes", (0x4000, 0x7FFF, 0, 0x8000, 0xC001))
def test_end_pts_with_a_plane_count_whose_step_is_not_a_word(planes):
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=canvas("box"), clip=(0, 0, 3, 199)),
                        search_pokes(0, BOUNDARY), {XLEFT_AT: vdi.pack_words(0x5A5A, 0x5A5A)},
                        vdi.linea_pokes(PLANES=planes), RUNGS)
    vdi_fill.run_call("LINEA_ROM_END_PTS", (1, 0, XLEFT_AT, XRIGHT_AT), pokes, max_insns=FILL_INSNS)


@pytest.mark.parametrize("mode", vdi_raster.MODES)
@pytest.mark.parametrize("pattern", ("16-row hatch", "user"))
def test_fill_span(mode, pattern):
    """x1, x2, y out of the frame into $a004's D4, D6, D5 — the row's own pattern row, a multi-plane one."""
    patterned = vdi_raster.user_pattern_pokes() if pattern == "user" else vdi_raster.pattern_pokes(pattern)
    pokes = vdi_raster.drawing_pokes(mode=mode, colour=0b0110, extra=patterned)
    vdi_fill.run_call("LINEA_ROM_FILL_SPAN", (7, 250, 33), pokes)


def queue_pokes(records, *, qtop=None, qptr=0, qbottom=0, done=0, under=None):
    """The queue holding `records` [(row, left, right) or None for an empty one] from index 0, QTOP just
    past them unless given, and the word under the queue (LEFTSEED) when `under` is given."""
    words = []
    for record in records:
        words += list(record) if record else [vdi_fill.VDI_FILL_EMPTY, 0x1111, 0x2222]
    top = len(words) if qtop is None else qtop
    pokes = {vdi_fill.VDI_FILL_QBOTTOM: vdi.pack_words(qbottom, top, qptr),
             vdi_fill.VDI_FILL_DONE: vdi.pack_words(done)}
    if words:
        pokes[vdi_fill.VDI_FILL_QUEUE] = vdi.pack_words(*words)
    if under is not None:
        pokes[vdi_fill.VDI_FILL_LEFTSEED] = vdi.pack_words(under)
    return pokes


RECORD = (40 | vdi_fill.VDI_FILL_DOWN_FLAG, 50, 90)
CRUNCHES = {
    "empties on top": ([RECORD, None, None], {"qptr": 6}),
    "taker below the top": ([RECORD, RECORD, None], {"qptr": 3}),
    "all empty, the word under it empty too": ([None, None], {"qptr": 6, "under": vdi_fill.VDI_FILL_EMPTY}),
    "nothing to drop": ([RECORD, RECORD], {"qptr": 6}),
}


@pytest.mark.parametrize("records, where", CRUNCHES.values(), ids=CRUNCHES.keys())
@pytest.mark.parametrize("seedabort", ("default", "abort"))
def test_crunch_queue(records, where, seedabort):
    stub = vdi_fill.default_seedabort_pokes() if seedabort == "default" else vdi_fill.countdown_pokes(1)
    vdi_fill.run_call("LINEA_ROM_CRUNCH_QUEUE", (), merge_pokes(queue_pokes(records, **where), stub))


QTMP_AS_A_RECORD = (vdi_fill.VDI_FILL_QTMP - vdi_fill.VDI_FILL_QUEUE) // vdi.WORD_BYTES
# (x, y, queue, where): y carries the direction flag.
DOWN = vdi_fill.VDI_FILL_DOWN_FLAG
SEEDS_DIRECT = {
    "done": (70, 60, [RECORD], {"done": 1}),
    "not fillable": (40, 60, [RECORD], {}),
    "appended": (70, 60, [RECORD, RECORD], {}),
    "into a hole": (70, 60, [RECORD, None, RECORD], {}),
    "twin met, the last record": (70, 60, [RECORD, (60 | DOWN, 41, 149)], {}),
    "twin met below the top": (70, 60, [(60 | DOWN, 41, 149), RECORD], {}),
    "a same-row record going the same way is no twin": (70, 60 | DOWN, [RECORD, (60 | DOWN, 41, 149)], {}),
    "queue full": (70, 60, [RECORD] * (vdi_fill.VDI_FILL_QUEUE_LAST // 3), {}),
    # The queue's bottom staged BELOW it, so the record appended is over QTMP itself ($16e4 = queue[-17]):
    # the ROM re-reads QTMP between the record's three stores, and the row it stored there moves the rest.
    "the record appended over QTMP": (70, 60, [], {"qtop": QTMP_AS_A_RECORD, "qbottom": QTMP_AS_A_RECORD - 3}),
}


@pytest.mark.parametrize("x, y, records, where", SEEDS_DIRECT.values(), ids=SEEDS_DIRECT.keys())
def test_get_seed(x, y, records, where):
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=0b1001, onto=canvas("box")),
                        search_pokes(0, BOUNDARY), queue_pokes(records, **where), vdi_fill.default_seedabort_pokes())
    vdi_fill.run_call("LINEA_ROM_GET_SEED", (x, y, XLEFT_AT, XRIGHT_AT, COLLIDE_AT), pokes, max_insns=FILL_INSNS)


def test_get_seed_takes_no_empty_record_for_a_twin():
    """An EMPTY record's row, $ffff, is $7fff with its flag flipped — row 32767 going up — so only the
    `!= EMPTY` test keeps it from being a twin of a run there: YMAXCL 32767 lets end_pts take that row
    (off the end of RAM, all colour 0 on both shores), whose run is XMINCL..XMAXCL, and the empty record
    names the same left end. It is taken as the HOLE, not met as a twin."""
    pokes = merge_pokes(vdi_fill.fill_workstation(colour=0b1001, onto=canvas("box"), clip=(0, 11, 319, 0x7FFF)),
                        search_pokes(0, BOUNDARY), vdi_fill.default_seedabort_pokes(),
                        queue_pokes([(vdi_fill.VDI_FILL_EMPTY, 0, 319), RECORD]))
    result = vdi_fill.run_call("LINEA_ROM_GET_SEED", (50, 0x7FFF, XLEFT_AT, XRIGHT_AT, COLLIDE_AT), pokes)
    assert vdi_fill.answer(result) == 1 and result.words(vdi_fill.VDI_FILL_QUEUE, 3) == [0x7FFF, 0, 319]


# ---- v_get_pixel ------------------------------------------------------------------------------------------
PIXEL_SCREEN = screen_bytes(lambda x, y: (x + 3 * y) % 16)


@pytest.mark.parametrize("point", ((0, 0), (5, 7), (17, 3), (100, 100), (319, 199)))
def test_v_get_pixel(point):
    result = vdi.run_function("VDI_ROM_V_GET_PIXEL", vdi.function_pokes("VDI_ROM_V_GET_PIXEL", ptsin=point,
                                                                      workstation_pokes=vdi.dispatched_pokes(onto=PIXEL_SCREEN)))
    value = (point[0] + 3 * point[1]) % 16
    assert result.intout(2) == [value, vdi.rom_word(vdi.VDI_REV_MAP_COL + value * vdi.WORD_BYTES)]
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 2


@pytest.mark.parametrize("planes, value", ((1, 0), (1, 1), (2, 3), (2, 2), (3, 3)))
def test_v_get_pixel_mono_and_medium_pens_index_as_15(planes, value):
    """INQ_TAB[4] decides: one plane and a set pixel, or two planes and pen 3, index REV_MAP_COL[15]."""
    screen = screen_bytes(lambda x, y: value)
    pokes = merge_pokes(vdi.function_pokes("VDI_ROM_V_GET_PIXEL", ptsin=(30, 40), workstation_pokes=vdi.dispatched_pokes(onto=screen)),
                        {INQ_TAB_PLANES: planes.to_bytes(2, "big")})
    vdi.run_function("VDI_ROM_V_GET_PIXEL", pokes)


def test_v_get_pixel_sixteen_planes_indexes_below_the_table():
    """PLANES 16 reads a 16-bit pen; one with bit 15 set sign-extends into an index BELOW REV_MAP_COL."""
    screen = {vdi.SCREEN.base: bytes([0xFF, 0xFF] * 16)}
    pokes = merge_pokes(vdi.function_pokes("VDI_ROM_V_GET_PIXEL", ptsin=(3, 0), workstation_pokes=vdi.dispatched_pokes(onto=screen)),
                        vdi.linea_pokes(PLANES=16))
    result = vdi.run_function("VDI_ROM_V_GET_PIXEL", pokes)
    assert result.intout(2) == [0xFFFF, vdi.rom_word(vdi.VDI_REV_MAP_COL - vdi.WORD_BYTES)]


def test_v_get_pixel_answers_before_reading_the_plane_count():
    """intout laid over INQ_TAB[4]: intout[0] is stored FIRST, so the plane count read is the pixel just
    answered — pen 1 over one plane indexes as 15."""
    pokes = vdi.intout_over(vdi.function_pokes("VDI_ROM_V_GET_PIXEL", ptsin=(1, 0),
                                               workstation_pokes=vdi.dispatched_pokes(onto=PIXEL_SCREEN)),
                            at=INQ_TAB_PLANES)
    result = vdi.run_function("VDI_ROM_V_GET_PIXEL", pokes)
    assert result.word(INQ_TAB_PLANES) == 1


def test_v_get_pixel_counts_after_answering():
    """intout laid over contrl[4]: the count is stored LAST."""
    pokes = vdi.intout_over(vdi.function_pokes("VDI_ROM_V_GET_PIXEL", ptsin=(5, 7),
                                               workstation_pokes=vdi.dispatched_pokes(onto=PIXEL_SCREEN)))
    result = vdi.run_function("VDI_ROM_V_GET_PIXEL", pokes)
    assert result.contrl(vdi.CONTRL_N_INTOUT) == 2


# ---- Tier 3: small regions, since every row is also run whole by the snapshot's mask test ------------------
SMALL_BOX = outlined([(40, 30, 72, 42)], BOUNDARY, BACKGROUND)
vdi.register("vdi_v_contourfill, a 31 x 11 box", addrs.VDI_ROM_V_CONTOURFILL,
             contour_pokes(screen_bytes(SMALL_BOX), (50, 35), BOUNDARY_INDEX))
vdi.register("linea_contour_fill, the S aborted on SEEDABORT's 2nd call", addrs.LINEA_ROM_CONTOUR_FILL,
             contour_pokes(canvas("S"), SEEDS["S"], BOUNDARY_INDEX, seedabort=vdi_fill.countdown_pokes(2)))
END_PTS_POKES = merge_pokes(vdi_fill.fill_workstation(colour=3, onto=canvas("box")), search_pokes(0, BOUNDARY))
vdi_fill.register_call("a 109-pixel run", "LINEA_ROM_END_PTS", (70, 60, XLEFT_AT, XRIGHT_AT), END_PTS_POKES)
vdi_fill.register_call("a row above the clip", "LINEA_ROM_END_PTS", (70, 5, XLEFT_AT, XRIGHT_AT), END_PTS_POKES)
for _label, _point in (("a 109-pixel run", (70, 60)), ("a row above the clip", (70, 5))):
    vdi_fill.register_transcription(_label, "LINEA_ROM_END_PTS", END_PTS_POKES, (*_point, XLEFT_AT, XRIGHT_AT))
_GET_SEED_POKES = merge_pokes(END_PTS_POKES, vdi_fill.default_seedabort_pokes())
vdi_fill.register_call("appended past eight records", "LINEA_ROM_GET_SEED", (70, 60, XLEFT_AT, XRIGHT_AT, COLLIDE_AT),
                       merge_pokes(_GET_SEED_POKES, queue_pokes([RECORD] * 8)))
vdi_fill.register_call("twin met", "LINEA_ROM_GET_SEED", (70, 60, XLEFT_AT, XRIGHT_AT, COLLIDE_AT),
                       merge_pokes(_GET_SEED_POKES, queue_pokes([RECORD, (60 | DOWN, 41, 149)])))
vdi_fill.register_call("two empties dropped, the taker wrapped", "LINEA_ROM_CRUNCH_QUEUE", (),
                       merge_pokes(queue_pokes([RECORD, None, None], qptr=6), vdi_fill.default_seedabort_pokes()))
FILL_SPAN_POKES = vdi_raster.drawing_pokes(mode="replace", colour=0b0110, extra=vdi_raster.pattern_pokes("8 rows"))
vdi_fill.register_call("a 244-pixel span", "LINEA_ROM_FILL_SPAN", (7, 250, 33), FILL_SPAN_POKES)
vdi_fill.register_transcription("a 244-pixel span", "LINEA_ROM_FILL_SPAN", FILL_SPAN_POKES, (7, 250, 33))
vdi.register("vdi_v_get_pixel, a pixel of pen 10", addrs.VDI_ROM_V_GET_PIXEL,
             vdi.function_pokes("VDI_ROM_V_GET_PIXEL", ptsin=(17, 3), workstation_pokes=vdi.dispatched_pokes(onto=PIXEL_SCREEN)))
