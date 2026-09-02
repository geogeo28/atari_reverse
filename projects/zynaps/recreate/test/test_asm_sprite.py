"""The ASM-TWIN differential for the two masked sprite blitters: each twin in ../src/asm/sprite.S
must leave the image byte-for-byte where its C core in ../src/sprite.c leaves it.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_sprite.py` pins the C cores against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twins the target build substitutes for those cores:

    original  ==(test_sprite.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_sprite.py`'S, IMPORTED RATHER THAN RESTATED — its staging helpers and its two
fuzz generators. A second, parallel case table here would be a second thing to keep true, and the
twin has to match the C on the C's OWN cases rather than on cases chosen to suit it.

THE REJECTION CASES ARE ASSERTED POSITIVELY. Four of the collide blitter's exits and four of its
sibling's write nothing at all, so "both sides agree" would be vacuous there. Those cases assert
that the image came back UNTOUCHED — which, with the differential, says both routines rejected
rather than that neither ran.

WHAT A DIVERGENCE MEANS is `test_asm_scroll.py`'s paragraph word for word: the whole image is
compared, `AsmTwins.call` separately refuses a store into the twin's own code or outside the image
on either side, and the image is staged at a NON-ZERO base so a twin that ignored its base argument
and addressed the game's globals absolutely cannot pass.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import pytest

import asm_twins
import harness
import test_sprite as sprite
from asm_twins import REJECTS

MASKED_TWIN = "draw_sprite_masked_asm"
COLLIDE_TWIN = "draw_sprite_masked_collide_asm"


# ================================================================ draw_sprite_masked @ 0x15ace

def _masked_case(x, y, height, half_frame, seed, must_write=True):
    """`test_sprite.py::blit_pokes`'s staging, run through the twin instead of the oracle."""
    image = harness.make_image(sprite.blit_pokes(x, y, height, seed))
    return asm_twins.matches_the_c(
        image, MASKED_TWIN, (sprite.BLIT_ENTITY, half_frame),
        lambda lib, buf: lib.g_draw_sprite_masked(buf, sprite.BLIT_ENTITY, half_frame),
        must_write=must_write)


def _masked_rejects(x, y, height, seed):
    """A case that must write NOTHING, asserted on BOTH sides by `asm_twins.REJECTS`."""
    _masked_case(x, y, height, sprite.SHIPPED_PRESHIFT_HALVES[1], seed, must_write=REJECTS)


@pytest.mark.parametrize("half_frame", sprite.SHIPPED_PRESHIFT_HALVES)
@pytest.mark.parametrize("phase", range(0, sprite.SPRITE_X_PHASE_MASK + 1, 2))
def test_masked_twin_every_phase(half_frame, phase):
    """The eight even sub-cell phases at both shipped frame sizes — the `mulu.w d2,d0` slot
    arithmetic end to end, which is the one place the twin reads its third argument."""
    _masked_case(0x40 + phase, 0x40, sprite.BLIT_HEIGHT, half_frame,
                 seed=phase * 16 + half_frame)


@pytest.mark.parametrize("x", (0, 2, 0x10, 0x12, 0x130, 0x13e))
def test_masked_twin_across_the_row(x):
    """Cell 0 to the last cell that fits — the `and.w #$fff0` + `lsr.w #1` cell index."""
    _masked_case(x, 0x40, sprite.BLIT_HEIGHT, sprite.SHIPPED_PRESHIFT_HALVES[1], seed=x)


@pytest.mark.parametrize("x", (-1, -2, sprite.SCREEN_PIXELS_WIDE, sprite.SCREEN_PIXELS_WIDE + 1))
def test_masked_twin_rejects_x_off_screen(x):
    """Both x rejections, either side of their edge. These are two of the twin's five `rts`
    instructions, and the `bsr` bracket in sprite.S exists so that they can be the original's own."""
    _masked_rejects(x, 0x40, sprite.BLIT_HEIGHT, seed=x & 0xffff)


@pytest.mark.parametrize("y", (sprite.PLAYFIELD_BOTTOM_Y, sprite.PLAYFIELD_BOTTOM_Y + 1,
                               sprite.PLAYFIELD_TOP_Y - sprite.BLIT_HEIGHT,
                               sprite.PLAYFIELD_TOP_Y - sprite.BLIT_HEIGHT - 1))
def test_masked_twin_rejects_y_off_playfield(y):
    """The other two rejections, at their exact edges."""
    _masked_rejects(0x40, y, sprite.BLIT_HEIGHT, seed=y & 0xffff)


@pytest.mark.parametrize("y", (sprite.PLAYFIELD_TOP_Y - sprite.BLIT_HEIGHT + 1,
                               sprite.PLAYFIELD_TOP_Y - 1,
                               sprite.PLAYFIELD_BOTTOM_Y - sprite.BLIT_HEIGHT,
                               sprite.PLAYFIELD_BOTTOM_Y - 1))
def test_masked_twin_clips(y):
    """Both clip arms: above the top the SOURCE steps forward, inside the playfield the ROW COUNT is
    cut and the destination steps down."""
    _masked_case(0x40, y, sprite.BLIT_HEIGHT, sprite.SHIPPED_PRESHIFT_HALVES[1],
                 seed=0x1000 + (y & 0xfff))


@pytest.mark.parametrize("y", (sprite.PLAYFIELD_TOP_Y - 1, sprite.PLAYFIELD_TOP_Y,
                               sprite.PLAYFIELD_TOP_Y + 1))
def test_masked_twin_clip_arms_are_exclusive(y):
    """The oversize height at which the two clips disagree — a sprite clipped at the top runs off
    the playfield's last row. Transcribed rather than guarded against, so the twin must too."""
    _masked_case(0x40, y, sprite.BLIT_OVERSIZE_HEIGHT, sprite.SHIPPED_PRESHIFT_HALVES[1],
                 seed=0x3000 + y)


# A fuzz chunk is a MIXTURE of drawing and rejecting cases, so neither `must_write` pole fits it
# and both suites pass False. That would let a broken staging — `blit_pokes` no longer pointing
# `A_SCREEN_BACK` at the staged screen, say — make every case reject on both sides and the whole
# sweep pass having compared nothing. So a chunk counts what it saw and asserts the mixture is
# still a mixture. The floor is deliberately 1 rather than a measured share: the point is that
# the sweep still reaches the row loops at all, and a tighter number would be a second thing to
# re-measure whenever the generator's seed changes.
FUZZ_MIN_DRAWING_CASES = 1


def _assert_the_sweep_drew(drawn, chunk, twin):
    assert drawn >= FUZZ_MIN_DRAWING_CASES, (
        f"{twin} chunk {chunk}: not one of its fuzz cases wrote to the image, so the sweep "
        f"compared two untouched images {M} the shared staging is broken, not the twin")


@pytest.mark.parametrize("chunk", range(sprite.BLIT_FUZZ_CHUNKS))
def test_masked_twin_fuzz(chunk):
    """`test_sprite.py`'s own 200-case sweep, replayed against the twin. The clip prologue is the
    half of this twin that is NOT byte-pinned (sprite.S says why), so it is the half that needs a
    sweep rather than a handful of edges."""
    drawn = 0
    for i, x, y, height, half_frame, seed in sprite.blit_fuzz_cases():
        if i % sprite.BLIT_FUZZ_CHUNKS != chunk:
            continue
        image = harness.make_image(sprite.blit_pokes(x, y, height, seed))
        run = _masked_case(x, y, height, half_frame, seed, must_write=False)
        drawn += run.image != bytes(image)
    _assert_the_sweep_drew(drawn, chunk, MASKED_TWIN)


# ======================================================== draw_sprite_masked_collide @ 0x15b7c

def _collide_case(x, y, height, seed, must_write=True, **staging):
    """`test_sprite.py::collide_staging`'s staging, run through the twin instead of the oracle."""
    pokes, flag = sprite.collide_staging(x, y, height, seed, **staging)
    image = harness.make_image(pokes)
    return asm_twins.matches_the_c(
        image, COLLIDE_TWIN, (sprite.BLIT_ENTITY, flag),
        lambda lib, buf: lib.g_draw_sprite_masked_collide(buf, sprite.BLIT_ENTITY, flag),
        must_write=must_write)


def _collide_rejects(x, y, height, seed):
    """A case that must write NOTHING, asserted on BOTH sides by `asm_twins.REJECTS`."""
    _collide_case(x, y, height, seed, must_write=REJECTS)


@pytest.mark.parametrize("phase", range(0, sprite.SPRITE_X_PHASE_MASK + 1, 2))
def test_collide_twin_every_phase(phase):
    """The eight even phases: each picks a different `shift_mask_table` entry AND a different
    preshift slot, so the keep-mask split and the slot arithmetic are walked together."""
    _collide_case(sprite.SPRITE_COLLIDE_ORIGIN_X + 0x40 + phase, 0x40, sprite.COLLIDE_HEIGHT,
                  seed=0x100 + phase)


@pytest.mark.parametrize("x", (0x40, 0x48, 0x100, 0x168, 0x170))
def test_collide_twin_across_the_row(x):
    """The MIDDLE band from screen column 0 to 0x170 — whose second cell lands on the next row's
    first, which is the original's own behaviour and so must be the twin's."""
    _collide_case(x, 0x40, sprite.COLLIDE_HEIGHT, seed=0x200 + x)


@pytest.mark.parametrize("x", (0x32, 0x38, 0x3e))
def test_collide_twin_left_edge_band(x):
    """The left band — one cell, keep masks the other way round (`.Lc_left_band`)."""
    _collide_case(x, 0x40, sprite.COLLIDE_HEIGHT, seed=0x300 + x)


@pytest.mark.parametrize("x", (0x172, 0x178, 0x17e))
def test_collide_twin_right_edge_band(x):
    """The right band — one cell in the row's last (`.Lc_right_band`)."""
    _collide_case(x, 0x40, sprite.COLLIDE_HEIGHT, seed=0x400 + x)


@pytest.mark.parametrize("x", (0x2e, sprite.SPRITE_COLLIDE_LEFT_EDGE,
                               sprite.SPRITE_COLLIDE_RIGHT_OFF,
                               sprite.SPRITE_COLLIDE_RIGHT_OFF + 2))
def test_collide_twin_rejects_x_off_screen(x):
    """Both x rejections, at and past their edges."""
    _collide_rejects(x, 0x40, sprite.COLLIDE_HEIGHT, seed=0x500 + (x & 0xffff))


@pytest.mark.parametrize("y", (sprite.PLAYFIELD_BOTTOM_Y, sprite.PLAYFIELD_BOTTOM_Y + 1,
                               sprite.PLAYFIELD_TOP_Y - sprite.COLLIDE_HEIGHT,
                               sprite.PLAYFIELD_TOP_Y - sprite.COLLIDE_HEIGHT - 1))
def test_collide_twin_rejects_y_off_playfield(y):
    _collide_rejects(0x80, y, sprite.COLLIDE_HEIGHT, seed=0x600 + (y & 0xffff))


@pytest.mark.parametrize("y", (sprite.PLAYFIELD_TOP_Y - sprite.COLLIDE_HEIGHT + 1,
                               sprite.PLAYFIELD_TOP_Y - 1,
                               sprite.PLAYFIELD_BOTTOM_Y - sprite.COLLIDE_HEIGHT,
                               sprite.PLAYFIELD_BOTTOM_Y - 1))
def test_collide_twin_clips(y):
    _collide_case(0x80, y, sprite.COLLIDE_HEIGHT, seed=0x700 + (y & 0xffff))


@pytest.mark.parametrize("height", (sprite.COLLIDE_HEIGHT,
                                    sprite.COLLIDE_HEIGHT | 0x8000))
def test_collide_twin_masks_the_height_flag(height):
    """`and.w #$7fff,d2` — the field's top bit is a flag its sibling does NOT mask off, so the two
    heights here must draw identically."""
    _collide_case(0x80, 0x40, height, seed=0x900 + (height & 0xffff))


def test_collide_twin_sets_the_flag_on_terrain():
    """An OPAQUE sprite over a background whose plane 2 is set: the `st (a5)` fires, and the flag it
    writes is OUTSIDE the image span the differential would otherwise be comparing to itself."""
    _collide_case(0x80, 0x40, sprite.COLLIDE_HEIGHT, seed=0xc00,
                  hit_flag=sprite.COLLIDE_FLAG,
                  sprite_bytes=sprite.collide_sprite(sprite.COLLIDE_HEIGHT,
                                                     *sprite.COLLIDE_OPAQUE_ROW),
                  screen_bytes=sprite.screen_with_planes((0, 0, 0xffff, 0)))


def test_collide_twin_leaves_the_flag_alone_over_low_planes():
    """The pair to the case above: the same opaque sprite over planes 0 and 1 only, where the flag
    must keep its seeded value. Between them they pin WHICH planes the twin's `and.l` consults."""
    _collide_case(0x80, 0x40, sprite.COLLIDE_HEIGHT, seed=0xb00,
                  hit_flag=sprite.COLLIDE_FLAG,
                  sprite_bytes=sprite.collide_sprite(sprite.COLLIDE_HEIGHT,
                                                     *sprite.COLLIDE_OPAQUE_ROW),
                  screen_bytes=sprite.screen_with_planes((0xffff, 0xffff, 0, 0)))


@pytest.mark.parametrize("phase", (2, 8, 14))
def test_collide_twin_second_cell_is_tested_too(phase):
    """Terrain in the SECOND cell only, so the near test misses and the FAR one has to fire — the
    only shape that can tell the middle band's two `st (a5)` arms apart."""
    clear_cell = sprite.cell_with_planes((0xffff, 0xffff, 0, 0))
    terrain_cell = sprite.cell_with_planes((0, 0, 0xffff, 0xffff))
    row = (clear_cell + terrain_cell) * (sprite.SCREEN_ROW_BYTES
                                         // (2 * sprite.SPRITE_CELL_BYTES))
    _collide_case(sprite.SPRITE_COLLIDE_ORIGIN_X + phase, 0x40, sprite.COLLIDE_HEIGHT,
                  seed=0xd00 + phase, hit_flag=sprite.COLLIDE_FLAG,
                  sprite_bytes=sprite.collide_sprite(sprite.COLLIDE_HEIGHT,
                                                     *sprite.COLLIDE_OPAQUE_ROW),
                  screen_bytes=row * (sprite.SCREEN_BYTES // sprite.SCREEN_ROW_BYTES))


def test_collide_twin_flag_inside_the_record():
    """The shape the game's own frame loop runs: A5 is the record's own ENTITY_PIXEL_HIT byte, so
    the twin writes into the record it is reading."""
    _collide_case(0x80, 0x40, sprite.COLLIDE_HEIGHT, seed=0xe00)


@pytest.mark.parametrize("chunk", range(sprite.COLLIDE_FUZZ_CHUNKS))
def test_collide_twin_fuzz(chunk):
    """`test_sprite.py`'s own 200-case sweep, replayed against the twin — the clip prologue and the
    three-way band dispatch, which are the parts sprite.S cannot byte-pin."""
    drawn = 0
    for i, x, y, height, in_record, seed in sprite.collide_fuzz_cases():
        if i % sprite.COLLIDE_FUZZ_CHUNKS != chunk:
            continue
        pokes, _flag = sprite.collide_staging(
            x, y, height, seed, hit_flag=None if in_record else sprite.COLLIDE_FLAG)
        run = _collide_case(x, y, height, seed, must_write=False,
                            hit_flag=None if in_record else sprite.COLLIDE_FLAG)
        drawn += run.image != bytes(harness.make_image(pokes))
    _assert_the_sweep_drew(drawn, chunk, COLLIDE_TWIN)


# ============================== the transcription pin: which spans ARE the original's own bytes

# The four ROW LOOPS, and the address in the original each starts at. `_body` / `_body_end` bracket
# them in ../src/asm/sprite.S.
#
# ONLY THE LOOPS, and that is a fact about gas rather than about the transcription: the original's
# assembler encoded `and.w #imm,Dn` / `cmp.w #imm,Dn` / `sub.w #imm,Dn` as the AND/CMP/SUB
# immediate-EA forms and gas spells all three as ANDI/CMPI/SUBI — same length, same cycles, a
# different opcode word. The clip prologues are almost nothing but those, so they cannot be
# byte-equal however faithfully they are copied; the loops contain no immediate-to-Dn operation at
# all, and they are where every cycle of a drawing call goes. The cost pins below are what stand in
# for the prologues, exactly as they do for `scroll_emit_tile_column`.
TRANSCRIBED_SPANS = {
    "draw_sprite_masked_rows": 0x15b56,                 # `move.w (a1),d0` — the mask word
    "draw_sprite_masked_collide_span2": 0x15c4a,        # the middle band, two cells wide
    "draw_sprite_masked_collide_right": 0x15cb6,        # the right edge band
    "draw_sprite_masked_collide_left": 0x15cfa,         # the left edge band
}


@pytest.mark.parametrize("name", sorted(TRANSCRIBED_SPANS))
def test_the_twins_transcribe_the_original(name):
    """Each bracketed body against the .PRG — see `asm_twins.assert_transcribes_the_original`."""
    asm_twins.assert_transcribes_the_original(name, TRANSCRIBED_SPANS[name])


# ======================================= what a twin COSTS, against what the original costs

# THE BAR IS PER CASE, AND IT IS SET FROM THE MEASUREMENT. These blitters are 5,000-13,000 cycles a
# call where a page blit is 110,000, so the C-ABI prologue they cannot avoid — a `movem.l` of seven
# or eleven callee-saved registers, the argument binding, the image-base adds and the `bsr` bracket
# — is a few percent rather than a quarter of one. Every reading below is that FIXED cost over a
# different call length, so the ratio differs per case while the excess does not:
#
#   case                              original   twin   excess   measured   ceiling
#   draw_sprite_masked, both sizes       4,846  5,068     +222    1.0458     1.047
#   collide, the left band               7,860  8,164     +304    1.0387     1.0392
#   collide, the right band              7,886  8,190     +304    1.0385     1.039
#   collide, the middle band            12,698 12,998     +300    1.0236     1.024
#
# THE MARGINS ARE FOUR OR FIVE CYCLES, which is what makes these bars a gate rather than a
# restatement of today's number: ONE more register in either `movem` costs 16 cycles round trip and
# reddens every one of them. The measurement is deterministic — Musashi counts cycles, the cases are
# fixed — so the margin is for a legitimate re-translation, not for noise. A twin that lands over
# its bar has a translation problem to find; DO NOT RAISE A CEILING to make a run pass.
MASKED_COST_CEILING = 1.047

COST_HEIGHT = sprite.BLIT_HEIGHT   # one asteroid frame: the tallest shape the game blits often


@pytest.mark.parametrize("half_frame", sprite.SHIPPED_PRESHIFT_HALVES)
def test_the_masked_twin_costs_what_the_original_costs(half_frame):
    """Both shipped frame sizes, drawing a whole unclipped sprite — the shape a live asteroid or
    boss segment produces, which is the only shape whose cost the frame notices."""
    image = harness.make_image(sprite.blit_pokes(0x40, 0x40, COST_HEIGHT, seed=0xb100 + half_frame))
    original, twin = asm_twins.cost_case(
        image, sprite.ENTRY_DRAW_SPRITE_MASKED,
        {"a2": sprite.BLIT_ENTITY, "d2": half_frame},
        MASKED_TWIN, (sprite.BLIT_ENTITY, half_frame),
        lambda lib, buf: lib.g_draw_sprite_masked(buf, sprite.BLIT_ENTITY, half_frame))
    asm_twins.assert_within_the_bar(MASKED_TWIN, original, twin, MASKED_COST_CEILING)


# The three x bands: {world x, that band's own ceiling}. Each band is its own transcribed loop with
# its own per-row cost, so one case would measure one of them and vouch for the other two — and a
# single shared ceiling would have to be the loosest of the three, which would leave the middle band
# (the one the game runs most) 190 cycles of slack it has no use for.
COLLIDE_COST_BANDS = {"left": (0x38, 1.0392), "middle": (0x80, 1.024), "right": (0x178, 1.039)}

# ...and one case that REJECTS, which the three bands above cannot stand in for. A translation that
# moves work in FRONT of an early `rts` — hoisting an absolute-address formation into the prologue,
# say — costs a drawing case nothing, because a drawing case reaches that work anyway. This twin had
# exactly that defect when it was written: the keep-mask table was formed in the prologue where the
# original forms it at 0x15c08, which sits AFTER both y-clip `rts`s, so every clipped sprite paid 20
# cycles the original does not. All three bands stayed green throughout. y is past the playfield's
# bottom, so the routine returns at 0x15bb6 having drawn nothing.
COLLIDE_REJECT_Y = sprite.PLAYFIELD_BOTTOM_Y
# 602 against 298. THE RATIO IS TWO AND THAT IS NOT A DEFECT: the excess is 304 cycles, the same
# fixed C-ABI frame every other case here pays (an eleven-register `movem` pair is 196 of it), and a
# 298-cycle call has nothing to amortise it against. What this bar polices is that the excess STAYS
# 304 — the hoist above made it 324 and moved this reading to 2.0872. The margin is one cycle, so any
# instruction added in front of an `rts` reddens it.
COLLIDE_REJECT_CEILING = 2.025


def _collide_cost(x, y, seed, must_write=True):
    """Clock the original and the twin over one staged collide case."""
    pokes, flag = sprite.collide_staging(x, y, COST_HEIGHT, seed=seed)
    image = harness.make_image(pokes)
    return asm_twins.cost_case(
        image, sprite.ENTRY_DRAW_SPRITE_MASKED_COLLIDE,
        {"a2": sprite.BLIT_ENTITY, "a5": flag},
        COLLIDE_TWIN, (sprite.BLIT_ENTITY, flag),
        lambda lib, buf: lib.g_draw_sprite_masked_collide(buf, sprite.BLIT_ENTITY, flag),
        must_write=must_write)


@pytest.mark.parametrize("band", sorted(COLLIDE_COST_BANDS))
def test_the_collide_twin_costs_what_the_original_costs(band):
    x, ceiling = COLLIDE_COST_BANDS[band]
    original, twin = _collide_cost(x, 0x40, seed=0xb200 + x)
    asm_twins.assert_within_the_bar(COLLIDE_TWIN, original, twin, ceiling)


def test_the_collide_twin_costs_what_the_original_costs_when_it_rejects():
    """A clipped sprite, which the three bands above cannot stand in for — see COLLIDE_REJECT_Y."""
    original, twin = _collide_cost(0x80, COLLIDE_REJECT_Y, seed=0xb2ff, must_write=REJECTS)
    asm_twins.assert_within_the_bar(COLLIDE_TWIN, original, twin, COLLIDE_REJECT_CEILING)
