"""The ASM-TWIN differential for the four UNCLIPPED masked sprite blitters: the twin in
`../src/asm/sprite.S` must leave the image byte-for-byte where its C core in `../src/sprite.c`
leaves it.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_sprite.py` pins the C cores against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twin the target build substitutes for that core:

    original  ==(test_sprite.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_sprite.py`'S — its staging helpers, its sample records and its fuzz GENERATOR
are imported rather than restated, because the twin has to match the C on the C's own cases rather
than on cases chosen to suit it. What is composed here and not imported is the three lines that turn
one fuzz case into an image (`screen_pokes`, the `0x5a5a` source seed, `source_row_bytes`): they are
`test_sprite.py`'s own idiom and it already carries them twice, and a fourth copy is what a shared
`blit_fuzz_pokes()` there would remove — a change in a file this campaign does not own. Until then
the coupling is stated: WIDEN THE FUZZ SOURCE IN `test_sprite.py` AND THIS FILE MUST FOLLOW, or the
twin is judged on a different pixel stream from the core it is pinned to.

WHY THERE IS NO REJECTION CASE HERE. The unclipped blitters have no early exit: every entry draws
`rows_minus_one + 1` rows and returns, so every case below writes to the image and
`asm_twins.matches_the_c`'s default positive control covers all of them. The routines that DO reject
are the clipped ones, and those keep the C (`../src/sprite.c`, "THE ASM-TWIN SEAM").

WHAT A DIVERGENCE MEANS. The WHOLE image is compared; `AsmTwins.call` separately refuses a store
into the twin's own code or outside the image on either side, and the image is staged at a NON-ZERO
base so a twin that ignored its base argument and addressed the game's globals absolutely cannot
pass.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import pytest

import asm_twins
import harness
import test_sprite as sprite

TWIN = "blit_sprite_rows_unclipped_asm"

# The four transcribed spans and the address each was transcribed FROM — `test_sprite.py`'s own
# entry constants, so a body pinned against the wrong routine is impossible to spell here.
BODIES = (("sprite_blit_w16", sprite.ENTRY_SPRITE_BLIT_W16),
          ("sprite_blit_w32", sprite.ENTRY_SPRITE_BLIT_W32),
          ("sprite_blit_w48", sprite.ENTRY_SPRITE_BLIT_W48),
          ("sprite_blit_w64", sprite.ENTRY_SPRITE_BLIT_W64))

# WHAT THE TWIN COSTS OVER THE ORIGINAL, per width class, MEASURED. Everything the twin spends
# beyond the original's own body is the C-ABI frame the original does not have: a six-register
# `movem` each way, the four argument loads and the two `adda`s that make the image base real, the
# width ladder, and the `bsr.w` bracket that lets each body keep the original's own closing `rts`.
#
# IT IS A FIXED COST AND NOT A SHARE, so the bar is cycles rather than a ratio. A one-row class-0
# call is ~420 cycles and a 64-row class-3 call is ~84,000; the same ~280 cycles is most of the
# first and 0.3% of the second, so any single ratio would either exempt the small calls or fail the
# large ones.
#
# THE FOUR NUMBERS DIFFER BY THE LADDER ARM EACH CLASS WALKS, and that is the whole of the spread:
# class 0 leaves at the first `beq.s` and falls into the epilogue; each class after it pays one more
# `subq.l`/`beq.s` pair (16 cycles) plus the `bra.s` back to the epilogue (10), and class 3 falls
# through its last test instead of taking it (-2). Equality rather than a ceiling, so that ONE more
# register in either `movem` list (16 cycles) reddens it — a deliberate change to the ladder is
# re-measured here, not accommodated by loosening it.
TWIN_FRAME_CYCLES = (264, 290, 306, 304)


def _case(image, width_class, src, shift, rows_minus_one):
    """One case through both sides: the twin, and `test_sprite.py`'s own glue for the C core."""
    return asm_twins.matches_the_c(
        image, TWIN, (src, sprite.BLIT_DST, width_class, shift, rows_minus_one),
        lambda lib, buf: sprite.BLIT_GLUE[width_class](buf, src, sprite.BLIT_DST, shift,
                                                       rows_minus_one))


def _record_case(post_load_image, width_class, shift, seed, rows=None):
    """`test_sprite.py::_blit_case`'s staging over the game's own artwork, run through the twin."""
    src, klass, record_rows = sprite.sprite_record(post_load_image,
                                                   sprite.SAMPLE_RECORD[width_class])
    assert klass == width_class
    image = harness.make_image(sprite.screen_pokes(seed))
    return _case(image, width_class, src, shift, record_rows if rows is None else rows)


# =============================================================== the differential

@pytest.mark.parametrize("shift", range(16))
@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_matches_the_c_at_every_shift(post_load_image, width_class, shift):
    """The whole `ror.l %d6` range at every width, over the game's own artwork — which is
    `test_sprite.py`'s first battery, asked of the twin instead of the oracle."""
    _record_case(post_load_image, width_class, shift, seed=width_class * 16 + shift)


@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_matches_the_c_on_one_row(post_load_image, width_class):
    """`dbf` with a count of 0 still draws one row. It is also the twin's own argument boundary:
    the C computes its pass count and the twin lets `dbf` do it, so a count of 0 is where a
    transcription that loaded the wrong register would draw 65,536 rows instead of one."""
    _record_case(post_load_image, width_class, shift=7, seed=0x100 + width_class, rows=0)


@pytest.mark.parametrize("chunk", range(sprite.BLIT_FUZZ_CHUNKS))
def test_the_twin_matches_the_c_on_random_pixels(chunk):
    """RANDOM PIXEL DATA, not the game's: every bit of every mask word is in play, which the real
    artwork's runs of 0xffff and 0x0000 are not. `test_sprite.py`'s generator, unchanged, so the
    twin is judged on the same stream the C core was."""
    for i, width_class, shift, rows_minus_one, seed in sprite.blit_fuzz_cases():
        if i % sprite.BLIT_FUZZ_CHUNKS != chunk:
            continue
        pokes = sprite.screen_pokes(seed)
        pokes[sprite.BLIT_SOURCE] = sprite.seeded(
            seed ^ 0x5a5a, (rows_minus_one + 1) * sprite.source_row_bytes(width_class))
        _case(harness.make_image(pokes), width_class, sprite.BLIT_SOURCE, shift, rows_minus_one)


# =============================================================== the transcription and cost pins

@pytest.mark.parametrize("name,entry", BODIES)
def test_the_twin_transcribes_the_original(name, entry):
    """THE ASSEMBLED BODY IS THE ORIGINAL'S OWN BYTES — not "computes the same thing".

    This is what turns "1.00x by construction" from a claim into a measurement: a body byte-equal to
    the original's cannot cost more than the original's."""
    asm_twins.assert_transcribes_the_original(name, entry)


@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_costs_what_the_original_costs(post_load_image, width_class):
    """The original and the twin over ONE staged case, clocked by the same instrument.

    Musashi's cycle counter on both sides, so the difference is a like-for-like reading: everything
    the twin spends beyond the original is the C-ABI frame the original does not have."""
    src, klass, rows = sprite.sprite_record(post_load_image, sprite.SAMPLE_RECORD[width_class])
    assert klass == width_class
    shift = 5
    image = harness.make_image(sprite.screen_pokes(0x7000 + width_class))
    original, twin = asm_twins.cost_case(
        image, sprite.ENTRY_BLIT[width_class],
        {"a0": src, "a1": sprite.BLIT_DST, "d6": shift, "d7": rows},
        TWIN, (src, sprite.BLIT_DST, width_class, shift, rows),
        lambda lib, buf: sprite.BLIT_GLUE[width_class](buf, src, sprite.BLIT_DST, shift, rows))
    assert twin - original == TWIN_FRAME_CYCLES[width_class], (
        f"the class-{width_class} twin costs {twin} cycles against the original's {original} — "
        f"{twin - original} more, not the {TWIN_FRAME_CYCLES[width_class]} of C-ABI frame it is "
        f"supposed to be. Find the translation that moved (an addressing mode the original did not "
        f"use, an argument reloaded inside the loop, a `movem` list that grew); do not move the bar "
        f"to make a slower twin fit")
