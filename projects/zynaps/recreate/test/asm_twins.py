"""The machinery every ASM-TWIN differential in this project shares.

A twin suite asks four things of one `src/asm/*.S` routine, and none of the four is specific to the
subsystem the routine belongs to:

    the differential      the twin leaves the image where its C core leaves it, byte for byte
    the transcription pin the assembled body IS the original's own machine code
    the cost pin          the twin costs what the original costs, on one instrument
    (the build gate lives in atari/build.sh and is asked of the objects, not from here)

`test_asm_scroll.py` was the first of them and `test_asm_sprite.py` the second; the four checks
moved here rather than being copied, because a second copy is a second thing to keep true and the
one that drifts is the one nobody re-reads. What stays in each suite is what is genuinely its own:
which cases to stage (borrowed from that subsystem's C battery), which spans are byte-pinned, and
what each twin's cost ceiling is.

    original  ==(test_<subsystem>.py)==  C core  ==(this machinery)==  asm twin

Both links are byte-exact over the WHOLE image, so a twin is pinned to the original transitively.
That is also why the comparison here is against the C rather than against a second oracle run: the
C is already proven equal to the original on exactly these cases.
"""
from pathlib import Path

import pytest

import harness

import loader
from recreate_kit.asm_twin import AsmTwins

_TWINS = None


class _Rejects:
    """The sentinel `matches_the_c`'s `must_write` takes for "this case must write NOTHING"."""

    def __repr__(self):
        return "REJECTS"

    def __bool__(self):
        raise TypeError("REJECTS is a third state, not a truthy False — compare it with `is`")


REJECTS = _Rejects()


def twins():
    """The assembled blob, loaded once per worker. `AsmTwins.require()` raises with the build
    command if the twins were never assembled — LOUD rather than skipped, since a skip would look
    like coverage."""
    global _TWINS
    if _TWINS is None:
        _TWINS = AsmTwins(Path(__file__).resolve().parents[1] / "build" / "asm", loader.IMAGE_SIZE)
    return _TWINS


def _c_image(image, glue):
    """Run the C CORE over a copy of `image` and return (the image it left, whatever it returned)."""
    buf = harness.candidate_image(image)
    returned = glue(harness._lib, buf)
    return bytes(buf), returned


def matches_the_c(image, symbol, args, glue, must_write=True):
    """The whole differential: one twin and its C core over one staged image, compared whole.

    `must_write` is the positive control, and it has THREE states, because "both sides agree" proves
    nothing when neither side wrote anything — a case whose destination the routine never reaches, or
    a glue call that silently did not happen, reads as a pass:

      True   (default) the C must have CHANGED the image. Every drawing case.
      REJECTS          the C must have left it UNTOUCHED, and so must the twin. A clip rejection is
                       a real arm with a real `rts`, and this is what makes such a case an assertion
                       rather than a hole; it lives here rather than in each suite because three
                       suites were about to spell it three ways.
      False            neither is asserted. ONLY for a sweep whose cases are a mixture of the two —
                       and such a sweep owes a control of its own that some case wrote (see
                       `test_asm_sprite.py`'s fuzz).
    """
    c_image, c_returned = _c_image(image, glue)
    if must_write is REJECTS:
        assert c_image == bytes(image), (
            f"{symbol}{args} was expected to reject, and the C core wrote to the image")
    elif must_write:
        assert c_image != bytes(image), (
            f"{symbol}: the C core wrote nothing, so comparing the twin against it tests nothing "
            f"— the case is staged wrong or the glue was not called")

    run = twins().call(image, symbol, *args)
    if run.image != c_image:
        diffs = [(addr, c_image[addr], run.image[addr])
                 for addr in range(len(c_image)) if c_image[addr] != run.image[addr]]
        pytest.fail(f"{symbol}{args} diverges from the C core in {len(diffs)} bytes "
                    f"(C, then asm)\n{harness.report(diffs)}")
    if c_returned is not None:
        assert run.d0 == c_returned, (
            f"{symbol}{args} returned {run.d0:#x}, the C core {c_returned:#x}")
    return run


def assert_transcribes_the_original(name, entry):
    """THE ASSEMBLED BODY IS THE ORIGINAL'S OWN BYTES, between `<name>_body` and `<name>_body_end`.

    Not "computes the same thing" — the same machine code, compared against the .PRG the harness
    already has loaded. This is what turns "1.00x by construction" from a claim into a measurement:
    a body byte-equal to the original's cannot cost more than the original's. The differential says
    the twin computes the right pixels; this says it does so the original's way, so an edit that
    happens to compute the same bytes by different instructions still fails here.

    The bracket covers the transcribed span only — the C-ABI prologue and epilogue outside it are
    ours and have no counterpart in the original.
    """
    blob = twins()
    lo, hi = blob.entry(f"{name}_body"), blob.entry(f"{name}_body_end")
    assert hi > lo, f"{name}: empty body bracket — the labels are in the wrong order"
    mine = blob.bin.read_bytes()[lo:hi]
    theirs = bytes(harness.BASE_IMAGE[entry:entry + len(mine)])
    assert mine == theirs, (
        f"{name} is not a transcription of the original @ {entry:#x}\n"
        f"  twin     {mine.hex()}\n"
        f"  original {theirs.hex()}")


def original_cycles(image, entry, regs):
    """What the ORIGINAL's own routine costs for this case, on the oracle."""
    import emu
    _, _, out_regs = emu.run(image, entry, regs)
    return out_regs["cycles"]


def cost_case(image, entry, regs, symbol, args, glue, must_write=True):
    """Run the original and the twin over ONE staged image and return (original, twin) cycles.

    Both sides are clocked by the same instrument — Musashi's cycle counter, over one call — so the
    ratio is a like-for-like reading and not two runs of different lengths compared. The twin is put
    through the differential on the way, so a cost reading can never be taken from a call that
    computed the wrong thing.

    `must_write` is `matches_the_c`'s, and REJECTS is a real thing to clock: a translation that moves
    work in FRONT of an early `rts` costs nothing a drawing case can see.
    """
    twin = matches_the_c(image, symbol, args, glue, must_write=must_write)
    return original_cycles(image, entry, regs), twin.cycles


def ceiling_for(symbol, ceilings):
    """The bar for one twin, by LONGEST matching prefix — a family of twins can share theirs.

    Longest and not tightest: a longer prefix is the more specific entry, and the more specific
    entry is the one that was measured for this twin. `min()` would agree only while no key is a
    prefix of another, and would silently judge `draw_sprite_masked_collide` against
    `draw_sprite_masked`'s bar the moment a table held both — reddening a correct twin with a
    message that sends the reader hunting a translation defect that is not there.

    For a suite whose bar varies by CASE rather than by twin (the collide blitter's three x bands
    cost different amounts per row), pass `assert_within_the_bar` that case's bar directly instead.
    """
    core = symbol[:-len("_asm")] if symbol.endswith("_asm") else symbol
    matches = [prefix for prefix in ceilings if core.startswith(prefix)]
    assert matches, (f"{symbol} has no cost ceiling — a twin without a cost bar is a twin nobody "
                     f"would notice regressing; measure it and add one")
    return ceilings[max(matches, key=len)]


def assert_within_the_bar(symbol, original, twin, bar):
    ratio = twin / original
    assert ratio <= bar, (
        f"{symbol} costs {twin} cycles against the original's {original} ({ratio:.4f}x), over its "
        f"{bar}x bar — find the translation that is costing it (an addressing mode the original did "
        f"not use, an argument reloaded inside the loop, a gas encoding), do not raise the bar")
