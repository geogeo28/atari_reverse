"""The ASM-TWIN differential for the FIVE restore blitters and the ring-seam copy: the twins in
`../src/asm/restore.S` must leave the image byte-for-byte where their C cores in `../src/sprite.c`
leave it.

    original  ==(test_sprite.py)==  C core  ==(THIS FILE)==  asm twin

THE CASES ARE `test_sprite.py`'S — its entry addresses, its glue, its arena and its staging helpers
are imported rather than restated, so the twin is judged on the cases the core was proven on. What
is composed here is the fuzz, which `test_sprite.py` has no restore equivalent of.

WHY THERE IS NO REJECTION CASE HERE. Neither routine has an early exit: a restore body draws
`rows_minus_one + 1` rows and returns, the seam copy is 80 unconditional longwords, so every case
below writes and `asm_twins.matches_the_c`'s default positive control covers all of them.

THE TWO ARGUMENT BOUNDARIES THIS SUITE OWNS, and they are the ones a transcription gets wrong:

  * `rows_minus_one == 0` still draws ONE row — `dbf` exits at -1, not at 0. A twin that loaded the
    count into the wrong half of a register would draw 65,536 rows instead of one;
  * a count whose HIGH WORD is non-zero. The C computes its passes as
    `loop_passes(rows_minus_one + 1, COUNT_MASK_WORD)` and the twin lets `dbf %d7` do it; `dbf`
    decrements only the low word and does not borrow, so the two agree — and nothing else in the
    suite would notice a twin that had been given a `.l` loop instead.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import random

import pytest

import asm_twins
import harness
import test_sprite as sprite

RESTORE_TWIN = "restore_blit_rows_asm"
SEAM_TWIN = "scroll_wrap_copy_1280_asm"
SEAM_BODY = "scroll_wrap_copy_1280"

# (the transcribed body's name, the address it was transcribed FROM, longwords per row), in
# `restore_blit_tbl`'s own order — which is `test_sprite.py`'s ENTRY_RESTORE and RESTORE_GLUE order,
# so ONE index means one thing across all three tables. The `longs` column is `../src/sprite.c`'s
# RESTORE_LONGS_W16..W80; that each is paired with the right entry is what the differential proves,
# since a mismatched pair makes the twin copy a different width from the C.
BODIES = (("restore_blit_w32", sprite.ENTRY_RESTORE_BLIT_W32, 4),
          ("restore_blit_w48", sprite.ENTRY_RESTORE_BLIT_W48, 6),
          ("restore_blit_w64", sprite.ENTRY_RESTORE_BLIT_W64, 8),
          ("restore_blit_w80", sprite.ENTRY_RESTORE_BLIT_W80, 10),
          ("restore_blit_w16", sprite.ENTRY_RESTORE_BLIT_W16, 2))
assert tuple(entry for _, entry, _ in BODIES) == sprite.ENTRY_RESTORE, (
    "BODIES is out of step with test_sprite.py's ENTRY_RESTORE — an index here would name one "
    "routine's glue and another's bytes")

# A row count whose LOW word is what both sides must use. 0x10000 + 3 is four passes on the C's
# `loop_passes(..., COUNT_MASK_WORD)` and four on the twin's `dbf`, and 65,540 on either side that
# got it wrong — which would run off the arena rather than pass quietly.
ROWS_WITH_HIGH_WORD = 0x10003

# WHAT THE TWIN COSTS OVER THE ORIGINAL, per width, MEASURED. Everything beyond the original's own
# body is the C-ABI frame the original does not have: the `%d7` push and pop, the five argument
# loads, the two `adda`s that make the image base real, the `bsr.s` into the register-ABI entry, and
# the width ladder's own rungs and `bra.w`.
#
# THE GAME DOES NOT PAY THIS FRAME. It enters at `restore_blit_rows_regs` with its arguments already
# in registers, so it pays the ladder and nothing else — MEASURED at 1,133 cycles a call through the
# C-ABI entry against 965 through the register one (`atari/profile.py ours`, shipped build). What is measured
# here is the C-ABI entry the SUITE drives, and it is still the right thing to pin: the ladder and
# the bodies it reaches are the shipped ones, so a translation that quietly cost cycles would show
# up in it.
#
# IT IS A FIXED COST AND NOT A SHARE, so the bar is cycles rather than a ratio, and it is EQUALITY
# rather than a ceiling: one more register in the prologue (16 cycles) reddens it, and a deliberate
# change to the ladder is re-measured here rather than accommodated by loosening it.
#
# THE FIVE NUMBERS DIFFER BY THE LADDER ARM EACH WIDTH WALKS, and that is the whole of the spread:
# 2 longs leaves at the first `beq.s`; 4, 6 and 8 each pay one more `subq.l`/`beq.s` pair (+16); and
# 10 falls THROUGH its last test rather than taking it, which is 2 cycles cheaper (-2).
RESTORE_FRAME_CYCLES = {2: 174, 4: 190, 6: 206, 8: 222, 10: 220}
# The seam copy's glue is four instructions and no bracket at all — see its own cost test.
SEAM_FRAME_CYCLES = 56

# The fuzz: enough cases that every width meets several counts and several src/dst alignments, cut
# into chunks so `make test -n auto` spreads them (../README.md, "Writing a fuzz test so it
# parallelizes"). Case generation is split from checking for the same reason.
RESTORE_FUZZ_CASES = 200
RESTORE_FUZZ_CHUNKS = 4
# The fuzz's arena, in SCREEN ROWS of `test_sprite.py`'s scratch screen. The destination band starts
# past the source band and both leave room for the tallest case: 130 + 63 rows is inside the 200-row
# screen, and the widest run is 40 bytes inside a 160-byte row.
FUZZ_SRC_ROWS = 30
FUZZ_DST_ROW_FIRST = 100
FUZZ_DST_ROWS = 30
FUZZ_ROWS_MINUS_ONE_MAX = 63
FUZZ_COLUMN_GROUPS = 14         # x SCREEN_GROUP_BYTES, and 14 * 8 + 40 is inside a 160-byte row


def restore_fuzz_cases():
    """(case, index, rows_minus_one, src, dst, seed) — the generator, separate from the checking."""
    rng = random.Random(sprite.ENTRY_RESTORE_BLIT_W16)
    for case in range(RESTORE_FUZZ_CASES):
        src_row = rng.randrange(FUZZ_SRC_ROWS)
        dst_row = FUZZ_DST_ROW_FIRST + rng.randrange(FUZZ_DST_ROWS)
        yield (case,
               rng.randrange(len(BODIES)),
               rng.randrange(FUZZ_ROWS_MINUS_ONE_MAX + 1),
               sprite.BLIT_SCREEN + src_row * sprite.SCREEN_ROW_BYTES
               + rng.randrange(FUZZ_COLUMN_GROUPS) * sprite.SCREEN_GROUP_BYTES,
               sprite.BLIT_SCREEN + dst_row * sprite.SCREEN_ROW_BYTES
               + rng.randrange(FUZZ_COLUMN_GROUPS) * sprite.SCREEN_GROUP_BYTES,
               rng.randrange(1 << 30))


def _restore_case(image, index, src, dst, rows_minus_one):
    """One case through both sides: the twin, and `test_sprite.py`'s own glue for the C core."""
    _name, _entry, longs = BODIES[index]
    return asm_twins.matches_the_c(
        image, RESTORE_TWIN, (src, dst, rows_minus_one, longs),
        lambda lib, buf: sprite.RESTORE_GLUE[index](buf, src, dst, rows_minus_one))


def _seam_case(image, src, dst):
    return asm_twins.matches_the_c(
        image, SEAM_TWIN, (src, dst),
        lambda lib, buf: harness._lib.g_scroll_wrap_copy_1280(buf, src, dst))


# =============================================================== the differential

@pytest.mark.parametrize("rows_minus_one", (0, 1, 31, 63))
@pytest.mark.parametrize("index", range(len(BODIES)))
def test_the_twin_matches_the_c_at_every_width(index, rows_minus_one):
    """`test_sprite.py::test_restore_blit_every_width`'s own battery, asked of the twin instead of
    the oracle: all five widths, and `rows_minus_one == 0` among the counts."""
    image = harness.make_image(sprite.screen_pokes(0x7000 + index * 0x100 + rows_minus_one))
    _restore_case(image, index, sprite.RESTORE_SRC, sprite.RESTORE_DST, rows_minus_one)


@pytest.mark.parametrize("index", range(len(BODIES)))
def test_the_twin_uses_only_the_low_word_of_the_row_count(index):
    """A count whose high word is set: the C masks it and the twin's `dbf` ignores it, so both make
    four passes. A twin given a 32-bit loop would copy 65,540 rows and run off the arena."""
    image = harness.make_image(sprite.screen_pokes(0x9000 + index))
    _restore_case(image, index, sprite.RESTORE_SRC, sprite.RESTORE_DST, ROWS_WITH_HIGH_WORD)


@pytest.mark.parametrize("chunk", range(RESTORE_FUZZ_CHUNKS))
def test_the_twin_matches_the_c_on_random_pixels(chunk):
    """Random background, random width, random count and random src/dst alignments — the two
    cursors and the `lea` that closes each row are what a shear would show up in."""
    for case, index, rows_minus_one, src, dst, seed in restore_fuzz_cases():
        if case % RESTORE_FUZZ_CHUNKS != chunk:
            continue
        _restore_case(harness.make_image(sprite.screen_pokes(seed)), index, src, dst,
                      rows_minus_one)


def test_the_seam_twin_matches_the_c():
    """`test_sprite.py::test_scroll_wrap_copy_1280_copies_two_whole_rows`'s case: 320 bytes and not
    319 or 321, over a seeded destination that shows either end."""
    src = sprite.BLIT_SCREEN + 8 * sprite.SCREEN_ROW_BYTES
    dst = sprite.BLIT_SCREEN + 120 * sprite.SCREEN_ROW_BYTES
    image = harness.make_image(sprite.screen_pokes(sprite.ENTRY_SCROLL_WRAP_COPY_1280))
    _seam_case(image, src, dst)


# =============================================================== the transcription and cost pins

@pytest.mark.parametrize("name,entry", [(name, entry) for name, entry, _ in BODIES]
                                       + [(SEAM_BODY, sprite.ENTRY_SCROLL_WRAP_COPY_1280)])
def test_the_twin_transcribes_the_original(name, entry):
    """THE ASSEMBLED BODY IS THE ORIGINAL'S OWN BYTES — not "computes the same thing".

    This is what turns "1.00x by construction" from a claim into a measurement: a body byte-equal to
    the original's cannot cost more than the original's."""
    asm_twins.assert_transcribes_the_original(name, entry)


@pytest.mark.parametrize("index", range(len(BODIES)))
def test_the_twin_costs_what_the_original_costs(index):
    """The original and the twin over ONE staged case, clocked by the same instrument."""
    name, entry, longs = BODIES[index]
    rows_minus_one = 31
    image = harness.make_image(sprite.screen_pokes(0x7100 + index))
    original, twin = asm_twins.cost_case(
        image, entry,
        {"a0": sprite.RESTORE_SRC, "a1": sprite.RESTORE_DST, "d7": rows_minus_one},
        RESTORE_TWIN, (sprite.RESTORE_SRC, sprite.RESTORE_DST, rows_minus_one, longs),
        lambda lib, buf: sprite.RESTORE_GLUE[index](buf, sprite.RESTORE_SRC, sprite.RESTORE_DST,
                                                    rows_minus_one))
    assert twin - original == RESTORE_FRAME_CYCLES[longs], (
        f"the {name} twin costs {twin} cycles against the original's {original} — "
        f"{twin - original} more, not the {RESTORE_FRAME_CYCLES[longs]} of C-ABI frame it is "
        f"supposed to be. Find the translation that moved (an addressing mode the original did not "
        f"use, an argument reloaded inside the loop, a prologue that grew); do not move the bar to "
        f"make a slower twin fit")


def test_the_seam_twin_costs_what_the_original_costs():
    """The seam copy's glue is four instructions and NO bracket — the prologue falls through into
    the body, whose own `rts` returns to the C caller — so its frame is the smallest here."""
    src = sprite.BLIT_SCREEN + 8 * sprite.SCREEN_ROW_BYTES
    dst = sprite.BLIT_SCREEN + 120 * sprite.SCREEN_ROW_BYTES
    image = harness.make_image(sprite.screen_pokes(0x7200))
    original, twin = asm_twins.cost_case(
        image, sprite.ENTRY_SCROLL_WRAP_COPY_1280, {"a0": src, "a1": dst},
        SEAM_TWIN, (src, dst),
        lambda lib, buf: harness._lib.g_scroll_wrap_copy_1280(buf, src, dst))
    assert twin - original == SEAM_FRAME_CYCLES, (
        f"the seam twin costs {twin} cycles against the original's {original} — {twin - original} "
        f"more, not the {SEAM_FRAME_CYCLES} of C-ABI frame it is supposed to be")
