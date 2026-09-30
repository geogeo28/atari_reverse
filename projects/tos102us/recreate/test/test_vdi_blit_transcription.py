"""`src/vdi/blit.S` — $a00e, $a007 and the CPU blit engine as the ROM wrote them, which the target build ships
because their C measures over Tier 3's 1.10 bar (`include/transcribed.h`, the TRANSCRIBED table).

Two claims hold it, neither of which needs the C: its WORDS are the ROM's, region by region, save the
fifty-seven longwords that name where blit.S itself puts the engine's fragments (each relocated to its exact
value); and it BEHAVES as the ROM over the batteries' own shapes — the same image, the whole register file
and the same traffic, through Tier 3's transcription relation.

WHAT EACH ENTRY'S BEHAVIOUR CASES REACH. The engine entered directly runs blit.S's engine and fragments on
one side and the ROM's on the other. The two front ends reach the engine through drawing vector 4 on BOTH
sides — the ROM's engine — so their cases pin the front ends' own instructions.

THE MUTATION SWEEP of `src/vdi/blit.S` against these BEHAVIOUR cases alone (the byte pin deselected — it kills
every mutant by construction; strict classifier): 56 same-size mutants — every aligner's first fragment and
middle loop swapped for its sibling, the word rotates, the setup's branches and constants, the plane loop, the
edge-mask table, the fast copy and a sample of the ops — 54 KILLED, 2 SURVIVED, both EQUIVALENT: a shift of
exactly 8 the long way (the same rotation), and a pattern step of 0 negated (-0 is 0).
"""

import pytest

from harness import BASE_IMAGE

import test_vdi_blit_copy as copy
import test_vdi_blit_engine as engine
import transcription
import vdi
import vdi_blit
import vdi_raster
from case import merge_pokes
from vdi_blit import OP_S

# ---- the words -------------------------------------------------------------------------------------------
FRAGMENTS = "LINEA_ROM_CPU_BLIT_OPS"
REGIONS = (
    transcription.pinned_region(0xFD0346, 0xFD0640, "LINEA_ROM_COPY_RASTER", ("LINEA_ROM_BITBLT",)),
    transcription.pinned_region(0xFD1038, 0xFD141C, "LINEA_ROM_CPU_BLIT", ()),
    transcription.pinned_region(0xFD1694, 0xFD19DC, FRAGMENTS, ()),
)
# The engine's two dispatch tables — the word rotates and aligners ($fd1158, 36 longwords) and the ops
# ($fd1278, 16) — and the five `lea (fragment).l` operands: every absolute reference from the engine's
# region into the fragments', which names blit.S's own copy of the fragment.
TABLES = ((0xFD1158, 0xFD11E8, "the engine's word-rotate and aligner table"), (0xFD1278, 0xFD12B8, "the engine's op table"))
LEAS = {0xFD113E: "the single-word rows' row end", 0xFD11F0: "the pattern row", 0xFD12C4: "the no-source rows' first word",
        0xFD12CA: "the no-source rows' middle loop", 0xFD12D4: "the no-source single word's row end"}
_OWN = "an absolute address of a fragment, which names where blit.S puts it"
RELOCATED = {
    **{at: transcription.Relocated(transcription.ABSOLUTE, FRAGMENTS, f"{what}: {_OWN}")
       for lo, hi, what in TABLES for at in range(lo, hi, vdi.LONG_BYTES)},
    **{at: transcription.Relocated(transcription.ABSOLUTE, FRAGMENTS, f"`lea` of {what}: {_OWN}") for at, what in LEAS.items()},
}


def test_every_relocated_longword_is_a_fragment_address():
    """The count is what the `.S` header claims, and every one points into the fragments' region."""
    assert len(RELOCATED) == 57
    fragments = REGIONS[2]
    for at in RELOCATED:
        target = int.from_bytes(bytes(BASE_IMAGE[at:at + vdi.LONG_BYTES]), "big")
        assert fragments.lo <= target < fragments.hi, f"${at:x} holds ${target:x}"


@pytest.mark.parametrize("region", REGIONS, ids=[f"${region.lo:x}" for region in REGIONS])
def test_each_region_is_the_rom_s_words(region):
    transcription.assert_transcribed(region, relocated=RELOCATED)


@pytest.mark.parametrize("registers", sorted({vdi_blit.ENGINE_CODE_POINTERS, vdi_blit.PATTERN_CODE_POINTERS}))
def test_a_code_pointer_caller_clears_its_registers_and_nothing_else(registers):
    left = transcription.assert_caller_cost(vdi_blit.code_pointer_caller(registers))
    assert transcription.changed_from_dirty(left) == set(registers)
    assert all(left[name] == 0 for name in registers)


# ---- the engine, entered directly ------------------------------------------------------------------------

def run_engine(case, *, pattern=False):
    registers, pokes = case
    pointers = vdi_blit.PATTERN_CODE_POINTERS if pattern else vdi_blit.ENGINE_CODE_POINTERS
    return vdi_blit.run_transcription("LINEA_ROM_CPU_BLIT", merge_pokes(vdi_raster.user_pattern_pokes(), pokes),
                                      registers, code_pointers=pointers)


@pytest.mark.parametrize("width", (1, 16, 23, 77))
@pytest.mark.parametrize("direction", engine.DIRECTIONS)
@pytest.mark.parametrize("shift", engine.SHIFTS)
def test_every_aligner(shift, direction, width):
    """Every shift BOTH ways: backwards is where aligners 4..7 and 12..15 run."""
    run_engine(engine.engine_case(shift, width, direction=direction))


@pytest.mark.parametrize("shift", (-9, 3))
@pytest.mark.parametrize("width", (5, 40))
def test_backwards(shift, width):
    size, source, destination = (width, 3), (69 + shift + 48, 30), (69, 140)
    run_engine((vdi_blit.engine_registers(size, source, destination),
                vdi_blit.engine_block_pokes(size, source, destination, ops=(6,))))


@pytest.mark.parametrize("op", vdi_blit.OPS)
@pytest.mark.parametrize("width", (9, 40))
def test_every_op(op, width):
    run_engine(engine.engine_case(-3, width, ops=(op,)))


@pytest.mark.parametrize("op", (OP_S, 0, 9))
def test_through_a_pattern(op):
    run_engine(engine.engine_case(7, 37, height=5, ops=(op,), pattern=engine.USER_PATTERN), pattern=True)


def test_the_colours_pick_each_plane_s_op():
    run_engine(engine.engine_case(4, 33, ops=engine.FOUR_OPS, foreground=0b0110, background=0b1010))


@pytest.mark.parametrize("shape", engine.FAST_SHAPES.values(), ids=engine.FAST_SHAPES.keys())
def test_the_fast_copy(shape):
    x, width = shape
    size, source, destination = (width, 5), (x + 32, 140), (x, 30)
    registers = vdi_blit.engine_registers(size, source, destination)
    pokes = vdi_blit.engine_block_pokes(size, source, destination)
    fast = (x + width - 1) // 16 - x // 16 >= 2
    vdi_blit.run_transcription("LINEA_ROM_CPU_BLIT", pokes, registers,
                               code_pointers=() if fast else vdi_blit.ENGINE_CODE_POINTERS)


# The engine's own tie-breaks and a caller's stride, which only the engine entered directly runs through blit.S:
# (size, source, destination, block fields).
ENGINE_EDGES = {
    "the same word, the source bit left: backwards": ((30, 2), (97, 50), (99, 50), dict(ops=(6,))),
    "onto itself, no shift: forwards": ((61, 3), (100, 80), (100, 80), dict(ops=(6,))),
    "a fast copy backwards over a source word stride of 0": ((64, 3), (21, 40), (21, 150), dict(S_NXWD=0)),
}


@pytest.mark.parametrize("edge", ENGINE_EDGES.values(), ids=ENGINE_EDGES.keys())
def test_the_engine_s_tie_breaks_and_strides(edge):
    size, source, destination, fields = edge
    fast = fields.get("ops") is None
    vdi_blit.run_transcription("LINEA_ROM_CPU_BLIT", vdi_blit.engine_block_pokes(size, source, destination, **fields),
                               vdi_blit.engine_registers(size, source, destination),
                               code_pointers=() if fast else vdi_blit.ENGINE_CODE_POINTERS)


# ---- the front ends ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("shift", (0, 5, -12))
@pytest.mark.parametrize("direction", engine.DIRECTIONS)
def test_bitblt(shift, direction):
    vdi_blit.run_transcription("LINEA_ROM_BITBLT", engine.xor_blit(shift, direction, 40), {"a6": vdi_blit.BLOCK_AT})


@pytest.mark.parametrize("op", (OP_S, 6, 12))
def test_copy_raster_opaque(op):
    transcription.run_transcription("LINEA_ROM_COPY_RASTER", copy.call(copy.COPY, copy.ON_SCREEN, mode=op))


@pytest.mark.parametrize("corners", copy.CLIP_CASES.values(), ids=copy.CLIP_CASES.keys())
def test_copy_raster_clipped(corners):
    transcription.run_transcription("LINEA_ROM_COPY_RASTER", copy.call(copy.COPY, corners, mode=OP_S, clip=copy.CLIP))


@pytest.mark.parametrize("mode", vdi_blit.MODES.values(), ids=vdi_blit.MODES.keys())
@pytest.mark.parametrize("colours", copy.COLOURS.values(), ids=copy.COLOURS.keys())
def test_copy_raster_transparent(mode, colours):
    transcription.run_transcription("LINEA_ROM_COPY_RASTER", copy.call(copy.TRANSPARENT_COPY, copy.FROM_FORM, mode=mode, colours=colours,
                                                                       source_form=copy.ONE_PLANE, transparent=1))


@pytest.mark.parametrize("refusal", copy.REFUSALS.values(), ids=copy.REFUSALS.keys())
def test_copy_raster_refusals(refusal):
    transcription.run_transcription("LINEA_ROM_COPY_RASTER", copy.call(copy.COPY, copy.ON_SCREEN, **refusal))


def test_copy_raster_through_the_pattern():
    transcription.run_transcription("LINEA_ROM_COPY_RASTER",
                                    copy.call(copy.COPY, copy.ON_SCREEN, mode=vdi_blit.PATTERN_MODE | 6,
                                              extra=merge_pokes(vdi_raster.user_pattern_pokes(), vdi.linea_pokes(MULTIFILL=1))))
