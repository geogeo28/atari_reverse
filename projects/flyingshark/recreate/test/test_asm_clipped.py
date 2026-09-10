"""The ASM-TWIN differential for the four GATED (clipped) masked sprite bodies: the twin in
`../src/asm/clipped.S` must leave the image byte-for-byte where its C core in `../src/sprite.c`
leaves it.

    original  ==(test_sprite.py)==  C core  ==(THIS FILE)==  asm twin

THE STAGING IS `test_sprite.py`'S — its helpers, its sample records, its scratch screen and its
gate-overlap case are imported rather than restated. The FUZZ GENERATOR is this file's own, and that
is the one place the chain above is thinner than it looks: `test_sprite.py`'s generator draws no gate
byte, because the C's own cases reach these bodies through a ladder that installs one of ten. So
`gated_fuzz_cases()` draws the gate as well, and the sweep below pokes all 2^(c+2) — which means
that for the gate bytes no ladder installs, `original == C` is not pinned by any case and only the
twin's own byte pin ties it to the original. That is a widening of the twin's coverage, not a hole
in it, and it is stated here rather than left for a reader to work out.

**AND THE FUZZ SOURCE IS THE FOURTH COPY OF `test_sprite.py`'S IDIOM.** `test_asm_sprite.py`'s header
predicted this one and states the coupling; it holds here unchanged: **WIDEN THE FUZZ SOURCE IN
`test_sprite.py` AND THIS FILE MUST FOLLOW**, or the twin is judged on a different pixel stream from
the core it is pinned to. The fix both files want is a shared `blit_fuzz_pokes()` in `test_sprite.py`
— a change in a file this campaign does not own.

What this suite stages that no other does is THE GATE BYTE: the eight clipped entries reach these
four bodies through a ladder that installs one, and the twin has no ladder, so every case here pokes
`blit_clip_mask` itself.

WHAT MAKES THIS SUITE DIFFERENT FROM THE OTHER TWO, and it is the whole reason to read it:

**The twin is NOT byte-identical to the original, and cannot be.** Each gated body reads the gate
with `btst #n,$16426.l` — an ABSOLUTE address — once per screen group, and a reconstruction receives
the image base as a run-time argument, so no operand in a `.S` can name `image + 0x16426`.
`clipped.S` substitutes `btst #n,(%a2)` with `%a2` loaded once per call, and this suite is what makes
that a DECLARED SUBSTITUTION rather than a hole. Four pins together say "every byte is the
original's except these":

  * each body is transcribed as a LIST OF SEGMENTS between the substituted instructions, and each
    segment is compared against the .PRG at its own address (`test_the_twin_transcribes_the_original`);
  * the segments TILE the body exactly — declared length against assembled length, so a segment
    cannot silently shrink and still pass a prefix compare (`test_the_segments_tile_the_original`);
  * every GAP between two segments is exactly the 4-byte substitution for the 8-byte instruction the
    original holds there, on the original's own bit number
    (`test_the_substituted_instruction_reads_the_gate_through_a_register`);
  * the one CONSEQUENCE of the substitution — the row loop's closing `dbf` branches back over a
    body that is 4 bytes shorter per site — is pinned by that arithmetic
    (`test_the_loop_branch_shrank_by_exactly_the_substitution`).

...and the cost pin is therefore not equality with the original either: the substitution is 8 cycles
cheaper per group per row, so what is pinned is `original - 8 * groups * rows + FRAME`.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
import random

import pytest

import abi
import asm_twins
import emu
import harness
import test_sprite as sprite

TWIN = "blit_sprite_rows_gated_asm"

# The image pointer, then the five register words — through `abi.declare_glue`, which is what
# `../README.md`'s "Adding a function" step 4 requires of every `g_*` a battery calls, so that
# ctypes cannot pass a 64-bit image pointer as an `int`. The `void` return matters here on its own:
# ctypes' default is `int`, and `asm_twins.matches_the_c` would then compare whatever the host left
# in its return register against the twin's %d0. Declared here rather than beside `test_sprite.py`'s
# block of the same lines because this suite is the routine's only caller.
abi.declare_glue("g_blit_sprite_rows_gated", args=5)

# THE FOUR GATED BODIES, as (name, original entry, one past the closing `rts`, the `btst` sites).
# Each is the `bra.w` target the clip ladders above it jump to — 0x14de8 / 0x14ea6 / 0x14fe6 /
# 0x1519a and their siblings in `../../out/prg_dis.txt` — and each site is one
# `btst #n,$16426.l`, the ONE instruction `clipped.S` does not transcribe.
GATED_BODIES = (
    ("sprite_blit_w16_gated", 0x14e1e, 0x14e98, (0x14e40, 0x14e6c)),
    ("sprite_blit_w32_gated", 0x14f06, 0x14fd8, (0x14f28, 0x14f80, 0x14fac)),
    ("sprite_blit_w48_gated", 0x1505e, 0x15188, (0x15080, 0x150d8, 0x1512e, 0x1515c)),
    ("sprite_blit_w64_gated", 0x15230, 0x153b2, (0x15252, 0x152aa, 0x15302, 0x1535a, 0x15386)),
)
GATED_ENTRY = tuple(entry for _, entry, _, _ in GATED_BODIES)

# The two encodings the substitution is between. `btst #<data>,<ea>` is 8 cycles plus the effective
# address: 12 for `(xxx).L` and 4 for `(An)`, which is where the saving comes from.
BTST_ABS_LONG = bytes((0x08, 0x39))     # btst #n,$xxxxxxxx.l — 8 bytes, 20 cycles
BTST_A2_INDIRECT = bytes((0x08, 0x12))  # btst #n,(%a2)       — 4 bytes, 12 cycles
BTST_ABS_BYTES = 8
BTST_REG_BYTES = 4
BTST_SAVING_CYCLES = 8
# ...and the row loop's closing pair, which is why a body's last segment stops six bytes early: the
# `dbf` is outside every segment (its displacement moves; see the pin below) and the `rts` is a
# segment of its own.
DBF_BYTES = 4
DBF_OPCODE = bytes((0x51, 0xCF))        # dbf %d7,<the body's own entry>
RTS_BYTES = 2


def segments(body):
    """[(label, original address, length)] for one body's transcribed spans.

    DERIVED from the body's extent and its substitution sites rather than listed, so the spans tile
    by construction and the suite's job is to check that the ASSEMBLED ones are the same lengths.
    """
    name, lo, hi, sites = body
    excluded = [(site, BTST_ABS_BYTES) for site in sites]
    excluded.append((hi - RTS_BYTES - DBF_BYTES, DBF_BYTES))   # the `dbf`, see DBF_BYTES
    spans, at = [], lo
    for cut, skipped in excluded:
        spans.append((cut - at, at))
        at = cut + skipped
    spans.append((hi - at, at))
    return [(f"{name}_seg{i}", address, length)
            for i, (length, address) in enumerate(spans)]


def screen_groups(width_class):
    """A class-`c` sprite lands on c + 2 screen groups, so its body runs that many `btst`."""
    return width_class + 2


def gate_values(width_class):
    """Every gate byte a class can be given: one bit per screen group, and every combination."""
    return range(1 << screen_groups(width_class))


# WHAT THE TWIN COSTS OVER THE ORIGINAL ONCE THE SUBSTITUTION IS ACCOUNTED FOR, per width class,
# MEASURED. The twin cannot cost what the original costs — `btst #n,(%a2)` is 8 cycles cheaper than
# `btst #n,$16426.l` and runs once per screen group per row — so the pin is
#
#     twin == original - BTST_SAVING_CYCLES * screen_groups * rows + GATED_FRAME_CYCLES[class]
#
# with the last term the C-ABI frame the original does not have: a seven-register `movem` each way,
# the six argument loads, the two `adda`s that make the image base real, the `adda` that makes the
# gate address, the `bsr.s` into the register-ABI entry, and the width ladder's own arm.
#
# THE GAME DOES NOT PAY THAT FRAME. `../src/sprite.c`'s seam enters at `blit_sprite_rows_gated_regs`
# with the values already in the original's registers, so it pays the ladder and nothing else. What
# is pinned here is the C-ABI entry the SUITE drives, and it is still the right thing to pin: the
# ladder and the four bodies it reaches are the shipped ones.
#
# EQUALITY RATHER THAN A CEILING, and the four numbers differ only by the ladder arm each class
# walks — `sprite.S`'s ladder, one `subq.l`/`beq.s` pair (16 cycles) per class, class 3 falling
# through its last test instead of taking it.
#
# EACH IS `test_asm_sprite.py`'s TWIN_FRAME_CYCLES PLUS 36, and that number is the gate register:
# one more entry in each `movem` list (16), the `movea.l %a0,%a2` (4) and the `adda.l #imm,%a2` (16)
# that make the gate address. The unclipped twin's frame is 278/294/310/308 for the same four
# classes, which is what says these are the same prologue with one register added rather than a
# different one that happens to be near.
GATED_FRAME_CYCLES = (314, 330, 346, 344)

# The fuzz, chunked so `make test -n auto` spreads it (../README.md, "Writing a fuzz test so it
# parallelizes"), with case generation split from checking.
GATED_FUZZ_CASES = 96
GATED_FUZZ_CHUNKS = 4
GATED_FUZZ_MAX_ROWS = 32


def gated_fuzz_cases():
    """(case, width_class, gate, shift, rows_minus_one, seed) — the generator, separate from the
    checking. The gate is drawn from the WHOLE range including 0, so the all-skipped arm meets
    random pixels too."""
    rng = random.Random(GATED_BODIES[0][1])
    for case in range(GATED_FUZZ_CASES):
        width_class = rng.randrange(sprite.SPRITE_WIDTH_CLASSES)
        yield (case,
               width_class,
               rng.randrange(1 << screen_groups(width_class)),
               rng.randrange(16),
               rng.randrange(GATED_FUZZ_MAX_ROWS),
               rng.randrange(1 << 30))


def _pokes(seed, gate):
    """`test_sprite.py`'s scratch screen, plus the gate byte this suite exists to sweep."""
    pokes = sprite.screen_pokes(seed)
    pokes[sprite.A_BLIT_CLIP_MASK] = bytes((gate,))
    return pokes


def _case(image, width_class, gate, src, shift, rows_minus_one, dst=None):
    """One case through both sides — the twin and `../src/sprite.c`'s gated-row-loop glue — returning
    whether the blit CHANGED the image.

    THE POSITIVE CONTROL IS THE SWEEP'S, NOT THE CASE'S, and that is the original's doing rather than
    a weakening: a gate of 0 draws nothing at all (asserted here as `REJECTS`, a real arm with a real
    `bra.w` past every merge), and at a SHIFT OF 0 a gate that admits only the spill group writes the
    background back over itself, because an absent group stands in as opaque mask and no pixels. A
    per-case `must_write` reddens on both. So each case answers whether it wrote and every sweep
    below asserts that its cases did.
    """
    dst = sprite.BLIT_DST if dst is None else dst
    before = bytes(image)
    run = asm_twins.matches_the_c(
        image, TWIN, (src, dst, width_class, shift, rows_minus_one),
        lambda lib, buf: harness._lib.g_blit_sprite_rows_gated(buf, src, dst, width_class, shift,
                                                               rows_minus_one),
        must_write=asm_twins.REJECTS if gate == 0 else False)
    return run.image != before


def _record_case(post_load_image, width_class, gate, shift, seed, rows=None):
    """`test_asm_sprite.py`'s staging over the game's own artwork, under a poked gate."""
    src, klass, record_rows = sprite.sprite_record(post_load_image,
                                                   sprite.SAMPLE_RECORD[width_class])
    assert klass == width_class
    image = harness.make_image(_pokes(seed, gate))
    return _case(image, width_class, gate, src, shift, record_rows if rows is None else rows)


def _random_case(width_class, gate, shift, rows_minus_one, seed):
    """...and the same over RANDOM pixel data, where no group is blank.

    The gate sweep needs that: a bit whose group the game's own artwork leaves transparent is a bit
    whose gate has no visible effect, and a `btst` transcribed against the wrong one would pass.
    """
    pokes = _pokes(seed, gate)
    pokes[sprite.BLIT_SOURCE] = sprite.seeded(
        seed ^ 0x5a5a, (rows_minus_one + 1) * sprite.source_row_bytes(width_class))
    return _case(harness.make_image(pokes), width_class, gate, sprite.BLIT_SOURCE, shift,
                 rows_minus_one)


# =============================================================== the differential

@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_matches_the_c_at_every_gate(width_class):
    """EVERY gate byte a class can be given, including 0 (no group drawn) and all-ones (every group).

    The eight ladders install ten distinct bytes between them; this sweeps all 2^(c+2), so a `btst`
    transcribed against the wrong bit — the one substitution's one free parameter — cannot survive."""
    wrote = [_random_case(width_class, gate, shift=5, rows_minus_one=7,
                          seed=0x6000 + width_class * 0x100 + gate)
             for gate in gate_values(width_class)]
    assert sum(wrote) == len(wrote) - 1, (
        f"class {width_class}: {sum(wrote)} of {len(wrote)} gate values drew anything, and over "
        f"random pixels every one but gate 0 must")


@pytest.mark.parametrize("shift", range(16))
@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_matches_the_c_at_every_shift(post_load_image, width_class, shift):
    """The whole `ror.l %d6` range at every width, over the game's own artwork, under a gate that
    lets the FIRST and LAST group through and skips whatever is between them — the arrangement in
    which a mis-tiled segment would shear one group's spill into the next."""
    gate = 1 | (1 << (screen_groups(width_class) - 1))
    assert _record_case(post_load_image, width_class, gate, shift,
                        seed=0x7000 + width_class * 16 + shift), "the case drew nothing"


@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_matches_the_c_on_one_row(post_load_image, width_class):
    """`dbf` with a count of 0 still draws one row — the twin's own argument boundary, and the case
    a transcription that loaded the wrong register would turn into 65,536 rows."""
    assert _record_case(post_load_image, width_class, gate=(1 << screen_groups(width_class)) - 1,
                        shift=7, seed=0x8000 + width_class, rows=0), "the case drew nothing"


@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_uses_only_the_low_word_of_the_row_count(post_load_image, width_class):
    """A count whose high word is set: the C masks it (`loop_passes(..., COUNT_MASK_WORD)`) and the
    twin lets `dbf %d7` do it, so both make four passes."""
    assert _record_case(post_load_image, width_class, gate=(1 << screen_groups(width_class)) - 1,
                        shift=3, seed=0x9000 + width_class, rows=0x10003), "the case drew nothing"


def test_the_twin_re_reads_its_gate_from_memory_every_group():
    """THE SUBSTITUTION KEPT THE SEMANTICS, and this is the case that says so BEHAVIOURALLY rather
    than structurally.

    The original never holds `blit_clip_mask` in a register: every screen group of every row is gated
    by its own `btst #n,$16426.l` INSIDE the row loop, so a blit whose own destination covers 0x16426
    draws its later groups under the gate its earlier ones wrote. `btst #n,(%a2)` keeps that — the
    byte is still fetched from memory — and a twin that had hoisted it into a data register instead
    would still pass every other case in this file, because every one of them blits into the screen
    ring where nothing can write the gate.

    The staging is `test_sprite.py`'s own `test_a_clipped_blit_re_reads_its_gate_from_memory_every_
    group`, which pins the same property of the C against the ORIGINAL: a class-0 sprite at a
    destination six bytes below the gate, source words chosen so group 0's fourth plane word leaves
    the gate byte's bit 0 CLEAR, under a gate of 0x03 that admitted both groups. So group 1 must not
    draw — on the original, on the C, and here.
    """
    gate = 0x03
    pokes = {sprite.BLIT_SOURCE: sprite.CLIP_MASK_OVERLAP_SOURCE,
             sprite.A_BLIT_CLIP_MASK: bytes((gate,))}
    assert _case(harness.make_image(pokes), 0, gate, sprite.BLIT_SOURCE,
                 sprite.CLIP_MASK_OVERLAP_SHIFT, 0,
                 dst=sprite.CLIP_MASK_OVERLAP_DST), "the case drew nothing"


@pytest.mark.parametrize("chunk", range(GATED_FUZZ_CHUNKS))
def test_the_twin_matches_the_c_on_random_pixels(chunk):
    """RANDOM PIXEL DATA, not the game's: every bit of every mask word is in play, which the real
    artwork's runs of 0xffff and 0x0000 are not — and a random gate and shift over it."""
    wrote = [_random_case(width_class, gate, shift, rows_minus_one, seed)
             for case, width_class, gate, shift, rows_minus_one, seed in gated_fuzz_cases()
             if case % GATED_FUZZ_CHUNKS == chunk]
    assert sum(wrote) > len(wrote) // 2, (
        f"only {sum(wrote)} of {len(wrote)} fuzz cases drew anything — the chunk is staged wrong")


# =============================================================== the substitution's four pins

@pytest.mark.parametrize("name,entry", [(label, address) for body in GATED_BODIES
                                        for label, address, _ in segments(body)])
def test_the_twin_transcribes_the_original(name, entry):
    """EVERY SEGMENT IS THE ORIGINAL'S OWN BYTES at its own address. What lies BETWEEN two segments
    is the substitution, and the two tests below are what pin that."""
    asm_twins.assert_transcribes_the_original(name, entry)


@pytest.mark.parametrize("body", GATED_BODIES, ids=lambda body: body[0])
def test_the_segments_tile_the_original(body):
    """The assembled segments are the DECLARED lengths, and together with the excluded instructions
    they cover the original body exactly.

    `assert_transcribes_the_original` compares only as many bytes as the twin has, so a segment that
    lost its last instruction would still match a prefix of the original and pass. This is what says
    it did not: the length is asserted, and the spans plus the excluded bytes are asserted to reach
    from the body's first byte to its last."""
    blob = asm_twins.twins()
    _name, lo, hi, sites = body
    covered = 0
    for label, address, length in segments(body):
        assembled = blob.entry(f"{label}_body_end") - blob.entry(f"{label}_body")
        assert assembled == length, (
            f"{label} assembles to {assembled} bytes and the original's span at {address:#x} is "
            f"{length} — the segment gained or lost an instruction")
        covered += length
    excluded = len(sites) * BTST_ABS_BYTES + DBF_BYTES
    assert covered + excluded == hi - lo, (
        f"the segments cover {covered} bytes and {excluded} are declared un-transcribed, which is "
        f"not the original body's {hi - lo}")


@pytest.mark.parametrize("body", GATED_BODIES, ids=lambda body: body[0])
def test_the_substituted_instruction_reads_the_gate_through_a_register(body):
    """THE ONE DIVERGENCE, named byte for byte on both sides.

    At each declared site the ORIGINAL holds `btst #n,$16426.l` and the twin holds `btst #n,(%a2)`
    on the SAME bit — and nothing else: the gap between two segments is exactly four bytes, so an
    instruction smuggled in beside the substitution has nowhere to hide."""
    blob = asm_twins.twins()
    text = blob.bin.read_bytes()
    spans = segments(body)
    _name, _lo, _hi, sites = body
    for index, site in enumerate(sites):
        original = bytes(harness.BASE_IMAGE[site:site + BTST_ABS_BYTES])
        bit = original[3]
        assert original == (BTST_ABS_LONG + bytes((0, bit))
                            + sprite.A_BLIT_CLIP_MASK.to_bytes(4, "big")), (
            f"the original at {site:#x} is not `btst #n,$16426.l` — the substitution table names an "
            f"instruction that is not there")
        gap_lo = blob.entry(f"{spans[index][0]}_body_end")
        gap_hi = blob.entry(f"{spans[index + 1][0]}_body")
        assert text[gap_lo:gap_hi] == BTST_A2_INDIRECT + bytes((0, bit)), (
            f"the twin's substitution for {site:#x} is {text[gap_lo:gap_hi].hex()}, not "
            f"`btst #{bit},(%a2)`")


@pytest.mark.parametrize("body", GATED_BODIES, ids=lambda body: body[0])
def test_the_loop_branch_shrank_by_exactly_the_substitution(body):
    """THE SUBSTITUTION'S ONE CONSEQUENCE. The row loop's closing `dbf %d7,<body>` branches back over
    every substituted site, so the twin's displacement is the original's plus four for each of them
    and its encoding is NOT the original's. Every other branch in these bodies is intra-group — the
    `bne.s` over a skipped group and the `bra.w` past its merge both stay between two gates — which
    is why this is the only instruction outside a segment that is not a substitution itself.
    """
    blob = asm_twins.twins()
    text = blob.bin.read_bytes()
    spans = segments(body)
    _name, _lo, hi, sites = body
    dbf = hi - RTS_BYTES - DBF_BYTES
    original = bytes(harness.BASE_IMAGE[dbf:dbf + DBF_BYTES])
    assert original[:2] == DBF_OPCODE, (
        f"the original at {dbf:#x} is not `dbf %d7,...` — the body's extent is wrong")

    gap_lo = blob.entry(f"{spans[-2][0]}_body_end")
    gap_hi = blob.entry(f"{spans[-1][0]}_body")
    shrank = len(sites) * (BTST_ABS_BYTES - BTST_REG_BYTES)
    expected = DBF_OPCODE + ((int.from_bytes(original[2:], "big") + shrank) & 0xffff).to_bytes(2,
                                                                                              "big")
    assert text[gap_lo:gap_hi] == expected, (
        f"the twin's loop branch is {text[gap_lo:gap_hi].hex()} and the original's is "
        f"{original.hex()}; {shrank} bytes of substitution should have moved it to {expected.hex()}")


# =============================================================== the cost pin

@pytest.mark.parametrize("width_class", range(sprite.SPRITE_WIDTH_CLASSES))
def test_the_twin_costs_what_the_original_costs_less_the_substitution(post_load_image, width_class):
    """The original and the twin over ONE staged case, clocked by the same instrument, with the
    substitution's saving spelt out rather than absorbed into a ceiling."""
    src, klass, rows_minus_one = sprite.sprite_record(post_load_image,
                                                      sprite.SAMPLE_RECORD[width_class])
    assert klass == width_class
    gate = (1 << screen_groups(width_class)) - 1     # every group drawn: the longest path
    shift = 5
    image = harness.make_image(_pokes(0xa000 + width_class, gate))
    original, twin = asm_twins.cost_case(
        image, GATED_ENTRY[width_class],
        {"a0": src, "a1": sprite.BLIT_DST, "d6": shift, "d7": rows_minus_one},
        TWIN, (src, sprite.BLIT_DST, width_class, shift, rows_minus_one),
        lambda lib, buf: harness._lib.g_blit_sprite_rows_gated(buf, src, sprite.BLIT_DST,
                                                               width_class, shift, rows_minus_one))
    saved = BTST_SAVING_CYCLES * screen_groups(width_class) * (rows_minus_one + 1)
    assert twin - (original - saved) == GATED_FRAME_CYCLES[width_class], (
        f"the class-{width_class} gated twin costs {twin} cycles against the original's {original} "
        f"less {saved} of substitution ({original - saved}) — {twin - (original - saved)} more, not "
        f"the {GATED_FRAME_CYCLES[width_class]} of C-ABI frame it is supposed to be. Find the "
        f"translation that moved (an addressing mode the original did not use, a `movem` list that "
        f"grew); do not move the bar to make a slower twin fit")


def test_the_substitution_saves_what_the_arithmetic_says(post_load_image):
    """THE SAVING IS A MEASUREMENT, not a table lookup: run one class-3 case at two row counts and
    check that the twin's advantage over the original grows by exactly
    `BTST_SAVING_CYCLES * screen_groups` per row.

    It is the pin the cost test above cannot be: that one takes the saving on trust from this file's
    own constants, so a wrong BTST_SAVING_CYCLES would move both sides of it together."""
    width_class = sprite.SPRITE_WIDTH_CLASSES - 1
    src, _klass, _rows = sprite.sprite_record(post_load_image, sprite.SAMPLE_RECORD[width_class])
    gate = (1 << screen_groups(width_class)) - 1
    counts = (3, 11)
    advantage = []
    for rows_minus_one in counts:
        image = harness.make_image(_pokes(0xb000 + rows_minus_one, gate))
        regs = {"a0": src, "a1": sprite.BLIT_DST, "d6": 5, "d7": rows_minus_one}
        _, _, out = emu.run(image, GATED_ENTRY[width_class], regs)
        twin = asm_twins.twins().call(image, TWIN, src, sprite.BLIT_DST, width_class, 5,
                                      rows_minus_one)
        advantage.append(out["cycles"] - twin.cycles)
    per_row = (advantage[1] - advantage[0]) // (counts[1] - counts[0])
    assert per_row == BTST_SAVING_CYCLES * screen_groups(width_class), (
        f"each extra row buys the twin {per_row} cycles over the original, not the "
        f"{BTST_SAVING_CYCLES * screen_groups(width_class)} that {screen_groups(width_class)} "
        f"substituted `btst` are supposed to")
