"""The ASM-TWIN differential for the scroll path: every twin in ../src/asm/ must leave the image
byte-for-byte where its C core in ../src/scroll.c leaves it.

WHY THIS SUITE EXISTS AND WHAT IT IS NOT. `test_scroll.py` pins the C cores against the ORIGINAL
binary, executed under Musashi by the kit's oracle. It links C and cannot run m68k of ours, so it
says nothing about the hand-written twins the target build substitutes for those cores. This suite
closes that gap and nothing else:

    original  ==(test_scroll.py)==  C core  ==(THIS FILE)==  asm twin

Both links are byte-exact over the WHOLE image, so a twin is pinned to the original transitively.
That is also why the comparison here is against the C rather than against a second oracle run: the C
is already proven equal to the original on exactly these cases, and re-deriving that would be the
same measurement taken twice.

THE CASES ARE `test_scroll.py`'S, IMPORTED RATHER THAN RESTATED. Its batteries already drive all
twenty blits at both scratch and real-framebuffer destinations, both emitters with the prefill flag
clear and set, and the tile emitter over all twelve shipped levels and all four of its flip arms. A
second, parallel case table here would be a second thing to keep true — and the twin has to match
the C on the C's OWN cases, not on cases chosen to suit it.

WHAT A DIVERGENCE MEANS. The whole image is compared, not a window, so a twin that steps one row too
far, writes a fifth plane, or reaches outside its destination differs somewhere — there is nowhere in
the image for a wild store to hide. `AsmTwins.call` separately refuses a twin that stores into its
own code. The image is staged at a NON-ZERO base (asm_twin.py explains why), so a twin that ignored
its image-base argument and addressed the game's globals absolutely — the shape the original itself
uses — cannot pass.

Requires the assembled twins (`make asm`, which `make test` runs first). A missing blob FAILS these
tests rather than skipping them: a silent skip is how a broken twin ships.
"""
from pathlib import Path

import pytest

import abi
import harness
import test_scroll as scroll
from harness import report

import loader
from recreate_kit.asm_twin import AsmTwins

# ---- the twins, loaded once per worker ---------------------------------------------------------
_TWINS = None


def _twins():
    """The assembled blob, loaded once. `AsmTwins.require()` raises with the build command if the
    twins were never assembled — LOUD rather than skipped, since a skip would look like coverage."""
    global _TWINS
    if _TWINS is None:
        _TWINS = AsmTwins(Path(__file__).resolve().parents[1] / "build" / "asm", loader.IMAGE_SIZE)
    return _TWINS


def _c_image(image, glue):
    """Run the C CORE over a copy of `image` and return (the image it left, whatever it returned)."""
    buf = harness.candidate_image(image)
    returned = glue(harness._lib, buf)
    return bytes(buf), returned


def _twin_matches_the_c(image, symbol, args, glue, must_write=True):
    """The whole check: one twin and its C core over one staged image, compared whole.

    `must_write` is the positive control. Both sides agreeing proves nothing if neither wrote
    anything — a case whose destination the routine never reaches, or a glue call that silently did
    not happen, would read as a pass. So every case asserts that the C CHANGED the image; a case
    that legitimately writes nothing has to say so by passing False.
    """
    c_image, c_returned = _c_image(image, glue)
    if must_write:
        assert c_image != bytes(image), (
            f"{symbol}: the C core wrote nothing, so comparing the twin against it tests nothing "
            f"— the case is staged wrong or the glue was not called")

    run = _twins().call(image, symbol, *args)
    if run.image != c_image:
        diffs = [(addr, c_image[addr], run.image[addr])
                 for addr in range(len(c_image)) if c_image[addr] != run.image[addr]]
        pytest.fail(f"{symbol}{args} diverges from the C core in {len(diffs)} bytes "
                    f"(C, then asm)\n{report(diffs)}")
    if c_returned is not None:
        assert run.d0 == c_returned, (
            f"{symbol}{args} returned {run.d0:#x}, the C core {c_returned:#x}")
    return run


# ======================================= scroll_page_to_screen_p00..p19 @ 0x15d56..0x16284

def _blit_twin(phase):
    return f"scroll_page_to_screen_p{phase:02d}_asm"


def _blit_case(phase, page, screen, seed):
    """`test_scroll.py::_blit_case`'s staging, run through the twin instead of the oracle."""
    pokes = scroll._noise(seed, ((page, page + scroll.PLAYFIELD_BYTES),
                                 (screen, screen + scroll.PLAYFIELD_BYTES)))
    image = harness.make_image(pokes)
    return _twin_matches_the_c(
        image, _blit_twin(phase), (page, screen),
        lambda lib, buf: lib.g_scroll_page_to_screen(buf, phase, page, screen))


@pytest.mark.parametrize("phase", range(scroll.SCROLL_PHASES))
def test_blit_twin_every_phase(phase):
    """All twenty twins. Each is its own transcription of its own entry point in the original, so
    twenty bodies need twenty cases — the chunking that distinguishes them is exactly what a shared
    case would fail to reach."""
    _blit_case(phase, scroll.SCRATCH_PAGE, scroll.SCRATCH_SCREEN, seed=phase)


@pytest.mark.parametrize("phase", (0, scroll.SCROLL_PHASES // 2, scroll.SCROLL_PHASES - 1))
def test_blit_twin_at_the_real_framebuffer(phase):
    """The shape the game runs: the destination is `screen_back`, one of the two framebuffers."""
    _blit_case(phase, scroll.SCRATCH_PAGE, abi.SCREEN_BACK, seed=0x5c000 + phase)


# The twins whose transcribed span is BYTE-IDENTICAL to the original's machine code, and the address
# in the original that span starts at. `_body` / `_body_end` bracket it in the `.S`.
#
# The blits are bracketed whole: they mention no address at all (they walk %a5 and %a6, which the
# prologue set up), so there was nothing in them to translate. The emitters are bracketed from their
# pass counter on — only their two entry instructions needed translating — which still covers 21 of
# their 23 instructions, the `dbf` displacement included.
#
# `scroll_emit_tile_column` has NO entry here, and that is a fact about it rather than an omission:
# it reloads a global address inside its tile-row loop, so four of its instructions are substituted
# and its bodies cannot be byte-equal. Its cost pin below is what stands in, and src/asm/README.md
# records the substitution and its cycle cost.
TRANSCRIBED_SPANS = {
    **{f"scroll_page_to_screen_p{phase:02d}": entry
       for phase, entry in enumerate(scroll.ENTRY_SCROLL_PAGE_TO_SCREEN)},
    "scroll_emit_column_shift2": 0x169fe,   # the `moveq #$47,d0` after the prefill branch
    "scroll_emit_column_shift0": 0x16a62,
}


@pytest.mark.parametrize("name", sorted(TRANSCRIBED_SPANS))
def test_the_twins_transcribe_the_original(name):
    """THE ASSEMBLED BODY IS THE ORIGINAL'S OWN BYTES. Not "computes the same thing" — the same
    machine code, compared against the .PRG the harness already has loaded.

    This is what turns "1.00x by construction" from a claim into a measurement: a body that is
    byte-equal to the original's cannot cost more than the original's. The differential above says
    the twin computes the right pixels; this says it does so the original's way, so an edit that
    happens to compute the same bytes by different instructions still fails here.

    The bracket covers the transcribed span only — the C-ABI prologue and epilogue outside it are
    ours and have no counterpart in the original.
    """
    twins = _twins()
    lo, hi = twins.entry(f"{name}_body"), twins.entry(f"{name}_body_end")
    assert hi > lo, f"{name}: empty body bracket — the labels are in the wrong order"
    mine = twins.bin.read_bytes()[lo:hi]
    entry = TRANSCRIBED_SPANS[name]
    theirs = bytes(harness.BASE_IMAGE[entry:entry + len(mine)])
    assert mine == theirs, (
        f"{name} is not a transcription of the original @ {entry:#x}\n"
        f"  twin     {mine.hex()}\n"
        f"  original {theirs.hex()}")


# ================================ scroll_emit_column_shift2 @ 0x169f2 / _shift0 @ 0x16a56

_EMIT_TWINS = {
    "shift2": ("scroll_emit_column_shift2_asm", "g_scroll_emit_column_shift2"),
    "shift0": ("scroll_emit_column_shift0_asm", "g_scroll_emit_column_shift0"),
}


def _emit_case(variant, workspace, page, edge, hide_screen, seed):
    """`test_scroll.py::_emit_case`'s staging, run through the twin instead of the oracle."""
    rows = scroll.EMIT_ROWS * scroll.SCREEN_ROW_BYTES
    pokes = scroll._noise(seed, ((workspace, workspace + scroll.WORKSPACE_BYTES),
                                 (page, page + rows),
                                 (edge, edge + rows)))
    pokes[scroll.A_SCROLL_PREFILL_HIDE_SCREEN] = bytes([hide_screen])
    image = harness.make_image(pokes)
    twin, glue_name = _EMIT_TWINS[variant]
    return _twin_matches_the_c(
        image, twin, (workspace, page, edge),
        lambda lib, buf: getattr(lib, glue_name)(buf, workspace, page, edge))


@pytest.mark.parametrize("variant", sorted(_EMIT_TWINS))
@pytest.mark.parametrize("hide_screen", (0, 1, 0xff))
def test_emit_twin(variant, hide_screen):
    """Both emitters, prefill flag clear and set — the flag is the twin's one branch, and the case
    with it set is what says the edge destination is redirected onto the page at all."""
    _emit_case(variant, scroll.SCRATCH_WORKSPACE, scroll.SCRATCH_PAGE, scroll.SCRATCH_EDGE,
               hide_screen, seed=0x169f2 + hide_screen)


@pytest.mark.parametrize("variant", sorted(_EMIT_TWINS))
def test_emit_twin_at_the_real_workspace(variant):
    """The shape the game runs: the workspace is `scroll_col_workspace` and the edge destination is
    the screen's own right-edge column."""
    _emit_case(variant, scroll.A_SCROLL_COL_WORKSPACE, scroll.SCRATCH_PAGE,
               abi.SCREEN_BACK + scroll.SCROLL_WINDOW_BYTES, 0, seed=0x16a56)


# ================================================== scroll_emit_tile_column @ 0x162c2

_TILE_TWIN = "scroll_emit_tile_column_asm"


def _tile_staging(level, column, screen_base, page, hide_screen, seed):
    """`test_scroll.py::_tile_column_case`'s staging: the image, and the three cursors the routine
    takes. Shared by the differential below and the cost reading further down, so neither can be
    measuring a case the other is not.

    The map is the level's own bytes AS THE ORIGINAL'S OWN UNPACKER LEFT THEM and the tile set is the
    ZYN*.DAT that level really names, both borrowed from `test_scroll.py` rather than fabricated:
    a map word is a tile index scaled by 64 into an absolute address, so an invented one reaches
    megabytes past the tile set and the case would be measuring a read neither side should make.
    """
    edge = screen_base + scroll.SCROLL_WINDOW_BYTES
    map_cursor = scroll.A_MAP_UNPACKED + column * scroll.MAP_COLUMN_BYTES
    workspace = scroll.A_SCROLL_COL_WORKSPACE
    pokes = scroll._noise(seed, ((page, page + scroll.MAP_PAGE_BYTES),
                                 (screen_base, screen_base + scroll.PLAYFIELD_BYTES),
                                 (workspace, workspace + scroll.WORKSPACE_BYTES)))
    pokes[scroll.A_MAP_UNPACKED] = scroll._unpacked_map(level)
    pokes[scroll.A_TILE_SET_BASE] = scroll._tile_set_for(level)
    pokes[scroll.A_SCROLL_PREFILL_HIDE_SCREEN] = bytes([hide_screen])
    return harness.make_image(pokes), edge, map_cursor


def _tile_column_case(level, column, screen_base, page, hide_screen, seed):
    """One twin run against the C core. `_twin_matches_the_c` compares the whole image AND the
    return value, which here is the map cursor one column on — the routine's only register output
    and the one thing about it that never reaches memory."""
    image, edge, map_cursor = _tile_staging(level, column, screen_base, page, hide_screen, seed)
    return _twin_matches_the_c(
        image, _TILE_TWIN, (edge, page, map_cursor),
        lambda lib, buf: lib.g_scroll_emit_tile_column(buf, edge, page, map_cursor))


@pytest.mark.parametrize("level", scroll.LEVEL_FILES)
def test_tile_twin_every_level(level):
    """Every level the disk ships, at a column whose own eighteen rows reach ALL FOUR FLIP ARMS.

    That is what covers the four arms: the twin writes the eight-row body out four times over, and
    `_column_reaching_every_arm` returns a column that reaches each of them inside ONE call — so a
    single case per level exercises every arm against the same destinations, and an arm that
    transcribed a cursor step wrongly differs in the rows it and only it produced. Real tiles are
    what let the arms tell each other apart, a flipped tile being the same 64 bytes walked
    backwards; twelve levels is twelve different tile sets and twelve different arm orderings.
    """
    _tile_column_case(level, scroll._column_reaching_every_arm(level), abi.SCREEN_BACK,
                      scroll.SCRATCH_PAGE, 0, seed=scroll.LEVEL_FILES.index(level))


@pytest.mark.parametrize("column", scroll.TILE_COLUMN_SPREAD)
def test_tile_twin_walks_the_map(column):
    """Columns across one level, so the 36-byte map stride and the 34-byte peek at the next column
    are exercised at more than one place in the buffer — including column 0, whose cursor starts at
    the map's first byte, and 398, the last whose peek stays inside it."""
    _tile_column_case(scroll.LEVEL_FILES[0], column, abi.SCREEN_BACK, scroll.SCRATCH_PAGE, 0,
                      seed=0xd00 + column)


def test_tile_twin_last_column_peeks_past_the_map():
    """Column 399's peek reads the 36 bytes AFTER the unpacked map — the loaded image's own zeroes,
    so the far tile is index 0 for all eighteen rows. The reach is the routine's own behaviour at the
    end of a level and it is transcribed, not guarded against, so the twin must reach exactly as far.
    """
    _tile_column_case(scroll.LEVEL_FILES[0], scroll.MAP_COLUMNS - 1, abi.SCREEN_BACK,
                      scroll.SCRATCH_PAGE, 0, seed=0xdff)


@pytest.mark.parametrize("hide_screen", (0, 1, 0xff))
def test_tile_twin_prefill_redirects_the_screen(hide_screen):
    """The twin's one entry branch. Set, the screen destination is redirected onto the page, so the
    column is written into the page twice and the framebuffer is not touched at all; the guard is a
    `tst.b`, so 0xff is as good as 1, and the case with it clear says the screen IS written."""
    _tile_column_case(scroll.LEVEL_FILES[0], 11, abi.SCREEN_BACK, scroll.SCRATCH_PAGE, hide_screen,
                      seed=0xe00 + hide_screen)


@pytest.mark.parametrize("phase", (0, 9, scroll.SCROLL_PHASES - 1))
def test_tile_twin_at_the_real_destinations(phase):
    """The shape the game runs: the edge cursor is `screen_back` + 152 and the page cursor is a real
    page from `map_page_table` offset by the column phase."""
    page_base = int.from_bytes(
        bytes(harness.BASE_IMAGE[scroll.A_MAP_PAGE_TABLE + 4:scroll.A_MAP_PAGE_TABLE + 8]), "big")
    _tile_column_case(scroll.LEVEL_FILES[0], 11, abi.SCREEN_BACK,
                      page_base + phase * scroll.SCROLL_PHASE_STEP, 0, seed=0xf00 + phase)


def test_tile_twin_at_a_third_screen():
    """A framebuffer that is neither of the game's two, which says the edge cursor is a pointer the
    caller passes and not a `screen_back` the twin read for itself."""
    _tile_column_case(scroll.LEVEL_FILES[0], 11, scroll.SCRATCH_EDGE_SCREEN, scroll.SCRATCH_PAGE,
                      0, seed=0x1000)


# ======================================= what a twin COSTS, against what the original costs

# The whole point of a twin is the cycle count, so the suite measures it rather than trusting that a
# transcription stayed one. Both sides are clocked by the SAME instrument — Musashi's cycle counter,
# over one call on one staged image — so the ratio is a like-for-like reading and not two runs of
# different lengths compared.
#
# THE BAR IS PER TWIN AND IT IS TIGHT, because a shared loose one pins nothing. A single 1.15x bar
# was measured to be useless here: the one substitution in the whole wave that is NOT free — moving
# `scroll_emit_tile_column`'s frame slot off displacement 0, so the per-tile-row reload stops being
# `movea.l (%sp),%a1` — costs 76 cycles on ~31,700, i.e. 1.011x becomes 1.0134x. A 1.15 bar is sixty
# times looser than the effect it exists to catch, and the mutation passed it.
#
# Each ceiling below is the MEASURED ratio plus a small margin, and the margin is what makes it a
# gate rather than a restatement of today's number. The measurement is deterministic — Musashi
# counts cycles, the cases are fixed — so the margin is for a legitimate re-translation, not noise.
# The excess over 1.0 is the C-ABI prologue and epilogue the original does not have: a `movem.l` of
# the callee-saved file, the argument loads and the image-base adds, ~256 cycles for the blits.
#
#   twin                          measured   ceiling   what the margin is
#   scroll_page_to_screen_p*      1.0024     1.005     the blit bodies are byte-pinned above, so the
#                                                      only thing that can move is the prologue
#   scroll_emit_column_shift2     1.0083     1.011     ditto, from the pass counter on
#   scroll_emit_column_shift0     1.0136     1.016     ditto (a shorter body, so a larger share)
#   scroll_emit_tile_column       1.0111     1.0125    the only twin with no byte pin, so this bar
#                                                      IS its pin — set under the 1.0134 the frame
#                                                      -slot mutation produces, and mutation-proven
#
# A twin that lands over its bar has a translation problem to find. DO NOT RAISE A CEILING to make a
# run pass; raising one is how the wave's one costly substitution got in unnoticed the first time.
TWIN_COST_CEILINGS = {
    "scroll_page_to_screen_p": 1.005,
    "scroll_emit_column_shift2": 1.011,
    "scroll_emit_column_shift0": 1.016,
    "scroll_emit_tile_column": 1.0125,
}


def _ceiling_for(symbol):
    """The bar for one twin, by longest matching prefix — the twenty blits share theirs."""
    core = symbol[:-len("_asm")] if symbol.endswith("_asm") else symbol
    matches = [bar for prefix, bar in TWIN_COST_CEILINGS.items() if core.startswith(prefix)]
    assert matches, (f"{symbol} has no entry in TWIN_COST_CEILINGS — a twin without a cost bar is a "
                     f"twin nobody would notice regressing; measure it and add one")
    return min(matches)


def _original_cycles(image, entry, regs):
    """What the ORIGINAL's own routine costs for this case, on the oracle."""
    import emu
    _, _, out_regs = emu.run(image, entry, regs)
    return out_regs["cycles"]


def _cost_case(image, entry, regs, symbol, args, glue):
    """Run the original and the twin over one staged image and return (original, twin) cycles."""
    twin = _twin_matches_the_c(image, symbol, args, glue)
    return _original_cycles(image, entry, regs), twin.cycles


def _assert_within_the_bar(symbol, original, twin):
    ratio = twin / original
    bar = _ceiling_for(symbol)
    assert ratio <= bar, (
        f"{symbol} costs {twin} cycles against the original's {original} ({ratio:.4f}x), over its "
        f"{bar}x bar — find the translation that is costing it (an addressing mode the original did "
        f"not use, an argument reloaded inside the loop, a gas encoding), do not raise the bar")


@pytest.mark.parametrize("phase", range(scroll.SCROLL_PHASES))
def test_the_blit_twin_costs_what_the_original_costs(phase):
    """All twenty, because all twenty are separately transcribed bodies with their own chunking."""
    page, screen = scroll.SCRATCH_PAGE, scroll.SCRATCH_SCREEN
    pokes = scroll._noise(0xb100 + phase, ((page, page + scroll.PLAYFIELD_BYTES),
                                           (screen, screen + scroll.PLAYFIELD_BYTES)))
    image = harness.make_image(pokes)
    original, twin = _cost_case(
        image, scroll.ENTRY_SCROLL_PAGE_TO_SCREEN[phase], {"a5": page, "a6": screen},
        _blit_twin(phase), (page, screen),
        lambda lib, buf: lib.g_scroll_page_to_screen(buf, phase, page, screen))
    _assert_within_the_bar(_blit_twin(phase), original, twin)


@pytest.mark.parametrize("variant", sorted(_EMIT_TWINS))
def test_the_emit_twin_costs_what_the_original_costs(variant):
    workspace, page, edge = scroll.SCRATCH_WORKSPACE, scroll.SCRATCH_PAGE, scroll.SCRATCH_EDGE
    rows = scroll.EMIT_ROWS * scroll.SCREEN_ROW_BYTES
    pokes = scroll._noise(0xb200, ((workspace, workspace + scroll.WORKSPACE_BYTES),
                                   (page, page + rows), (edge, edge + rows)))
    pokes[scroll.A_SCROLL_PREFILL_HIDE_SCREEN] = bytes([0])
    image = harness.make_image(pokes)
    twin, glue_name = _EMIT_TWINS[variant]
    entry = scroll._EMIT_ENTRIES[variant][0]
    original, measured = _cost_case(
        image, entry, {"a0": workspace, "a1": page, "a2": edge},
        twin, (workspace, page, edge),
        lambda lib, buf: getattr(lib, glue_name)(buf, workspace, page, edge))
    _assert_within_the_bar(twin, original, measured)


@pytest.mark.parametrize("level", scroll.LEVEL_FILES)
def test_the_tile_twin_costs_what_the_original_costs(level):
    """The tile decoder, whose transcription had ONE thing to translate that was not free by
    inspection: the original re-forms the tile-set base with `lea $4b3be.l,a1` once per tile row, and
    with all seven address registers spoken for the twin reloads it from its own frame instead. The
    frame slot sits at displacement zero precisely so that reload assembles to `movea.l (%sp),%a1` —
    12 cycles and three reads, exactly what the `lea` was (src/asm/scroll_tile.S has the arithmetic).
    This is the reading that says so rather than the file merely claiming it.

    Every level, because the arms cost different amounts (a flipped side is a `movem.w (aN)` plus a
    `lea`, an unflipped one a single `movem.w (aN)+`), so which arms a level's column takes is what
    sets the call's cycle count — one level would measure one mix.
    """
    page = scroll.SCRATCH_PAGE
    image, edge, map_cursor = _tile_staging(
        level, scroll._column_reaching_every_arm(level), abi.SCREEN_BACK, page, 0,
        seed=0xb300 + scroll.LEVEL_FILES.index(level))
    original, measured = _cost_case(
        image, scroll.ENTRY_SCROLL_EMIT_TILE_COLUMN,
        {"a0": edge, "a5": page, "a6": map_cursor},
        _TILE_TWIN, (edge, page, map_cursor),
        lambda lib, buf: lib.g_scroll_emit_tile_column(buf, edge, page, map_cursor))
    _assert_within_the_bar(_TILE_TWIN, original, measured)


# NO `MIRRORS` / `ENTRY_PROLOGUES` HERE, and test_constants.py does not ask for them: this file is
# not one of its batteries (there is no ../src/asm_scroll.c) and it restates no constant of its own.
# Every address, span and count it stages comes from `test_scroll.py`, which pins all of them; the
# twins' own `.equ` values are pinned against the headers by
# test_constants.py::test_asm_twin_equates_match_the_headers.
