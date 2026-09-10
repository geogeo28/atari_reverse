#!/usr/bin/env python3
"""Assert that the asm twin THIS BUILD LINKS is the original binary's own machine code.

    assert_twin_bytes.py <twin.o> <FLYSHARK.IMG> <load base> <span> ...

...where each `<span>` names either ONE transcribed body or one SEGMENTED body:

    <name>=<address>                                 a body: `<name>_body` .. `<name>_body_end`
    <name>=<lo>:<hi>:<site>,<site>,...               a body cut into `<name>_seg0`, `_seg1`, ...

THE SEGMENTED FORM IS FOR A TWIN THAT IS NOT BYTE-IDENTICAL, which today is `../src/asm/clipped.S`
alone: its four bodies read the clip gate at an ABSOLUTE address, which a reconstruction whose image
base is a run-time argument cannot spell, so each `btst #n,$16426.l` becomes a 4-byte
`btst #n,(%a2)` and the body is pinned as the runs BETWEEN those instructions. `<lo>`/`<hi>` are the
body's own extent (`<hi>` one past its closing `rts`) and `<site>` each substituted instruction;
this file derives the segments from them — the same derivation `../test/test_asm_clipped.py`'s
`segments()` makes, from the same four numbers — and then asserts that the assembled segments TILE
that extent, which the per-span compare cannot say on its own: a segment that lost its last
instruction still matches a PREFIX of the original. `src/asm/README.md`, "The gated twin's declared
substitution", carries the case; what is NOT checked here is the substituted instruction itself,
which is the suite's job because it needs the original's bit numbers.

WHY THE TEST SUITE IS NOT ENOUGH, which is the whole reason this file exists. `../test/
test_asm_sprite.py` compares the KIT's blob (`../build/asm/twins.bin`, assembled by `kit.mk` with
its own flags — no `-O`, no `-ffreestanding`, and `-DRECREATE_HOST_DIFFERENTIAL`, which is what a
twin's callback-door stubs select on) against the .PRG, span by span. `build.sh` assembles the same
`.S` with a disjoint flag set. So the suite's byte pin vouches for an object nobody assembled, and
the day an `#ifdef RECREATE_HOST_DIFFERENTIAL` lands inside a body — which the kit's door mechanism
explicitly invites — it would check the off-target arm while the machine runs the other one. The
pixels would still be right and only the frame rate would say so, which is the silent-failure class
the whole twin gate exists for.

WHAT IT COMPARES. `<name>_body` .. `<name>_body_end` in the SHIPPED object, against `FLYSHARK.IMG`
— the original's own relocated TEXT+DATA, which `gen_image.py` staged for this build minutes ago —
at `original address - load base`. The bodies carry no absolute operand (the twin's own README says
why: every access is `(%a0)+`, `(%a1)+`, `lea N(%a1)` or a PC-relative `dbf`), so no relocation can
move a byte inside one and the comparison is exact.

IT IS DELIBERATELY NOT A COMPARISON AGAINST `build/asm/twins.bin`. That was the first shape, and it
was wrong twice: it made the target build DELETE and remake a directory `make test`'s workers hold
open (this workspace runs builds and suites in parallel), and it compared one object against a blob
`kit.mk` links from EVERY `src/asm/*.S`, so the second twin anyone adds would have reddened it with
a message naming the wrong cause. Going to the original's bytes needs no artefact of the suite's at
all.
"""
import subprocess
import sys
from pathlib import Path

NM = "m68k-elf-nm"
OBJCOPY = "m68k-elf-objcopy"
# What `src/asm/*.S` brackets a transcribed span with, and what `../src/asm/README.md` calls them.
BODY_SUFFIX = "_body"
BODY_END_SUFFIX = "_body_end"
# How much of a mismatch to print. Enough to see which instruction moved, short enough to read.
DIFF_BYTES = 32
# `nm` type letters for a symbol that names an ADDRESS IN `.text`: global and local. Everything else
# a twin defines — an `.equ`, which is `a` — is a value, not a place.
TEXT_SYMBOL_TYPES = "Tt"
# What a SEGMENTED body's spans are called: `<name>_seg0`, `_seg1`, ... — `../src/asm/clipped.S`'s
# labels and `../test/test_asm_clipped.py`'s `segments()`, which derives the same list.
SEGMENT_SUFFIX = "_seg"
# The instruction a segmented twin substitutes, and its consequence — both EXCLUDED from the spans
# this file compares, and both pinned by `../test/test_asm_clipped.py` instead (it needs the
# original's bit numbers, which are not derivable from the extent). 8 bytes of
# `btst #n,$xxxxxxxx.l`, and the row loop's own 4-byte `dbf`, which sits six bytes before the end.
SUBSTITUTED_BYTES = 8
LOOP_BRANCH_BYTES = 4
CLOSING_RTS_BYTES = 2


def segments_of(name, lo, hi, sites):
    """[(span name, original address, length)] for one SEGMENTED body — the runs between the
    substituted instructions, plus the run between the last of them and the `dbf`, plus the `rts`.

    THE SAME DERIVATION `../test/test_asm_clipped.py`'s `segments()` MAKES, from the same four
    numbers, so the two spellings of the table are the four numbers and not twenty-two addresses.
    """
    excluded = [(site, SUBSTITUTED_BYTES) for site in sites]
    excluded.append((hi - CLOSING_RTS_BYTES - LOOP_BRANCH_BYTES, LOOP_BRANCH_BYTES))
    spans, at = [], lo
    for cut, skipped in excluded:
        spans.append((cut - at, at))
        at = cut + skipped
    spans.append((hi - at, at))
    return [(f"{name}{SEGMENT_SUFFIX}{i}", address, length)
            for i, (length, address) in enumerate(spans)]


def parse_span(argument):
    """One `<span>` argument into [(span name, original address, expected length or None)].

    `<name>=<address>` is one whole body and this gate learns its length from the object's own
    bracket; `<name>=<lo>:<hi>:<sites>` is a segmented one and the lengths are DERIVED, which is what
    makes the tiling assertion below possible at all.
    """
    name, _, extent = argument.partition("=")
    if ":" not in extent:
        return [(name, int(extent, 0), None)]
    lo, hi, sites = extent.split(":")
    return segments_of(name, int(lo, 0), int(hi, 0),
                       tuple(int(site, 0) for site in sites.split(",")))


def symbols(obj):
    """{name: text offset} for the object's own CODE symbols, which for a `.o` are section-relative.

    TYPE-FILTERED, because a `.S` here also defines `.equ` names and `nm` prints those with the same
    three fields and an ABSOLUTE value — 152, say, for a `lea` displacement. The moment a twin
    derives a symbol name inside a macro (`restore.S`'s `RESTORE_BODY` does), one of those could be
    read back as a span offset and this gate would compare a wrong, short slice of `.text` and pass.
    The kit's own parser keeps the type letter for the same reason (`recreate_kit/asm_twin.py`).
    """
    found = {}
    for line in subprocess.run([NM, str(obj)], check=True, capture_output=True,
                               text=True).stdout.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[1] in TEXT_SYMBOL_TYPES:
            found[fields[2]] = int(fields[0], 16)
    return found


def text_of(obj):
    """The object's `.text`, as bytes."""
    out = Path(str(obj) + ".text.bin")
    subprocess.run([OBJCOPY, "-O", "binary", "--only-section=.text", str(obj), str(out)],
                   check=True)
    return out.read_bytes()


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    obj, image_path, load_base = Path(argv[0]), Path(argv[1]), int(argv[2], 0)
    spans = [span for argument in argv[3:] for span in parse_span(argument)]

    table, text, image = symbols(obj), text_of(obj), image_path.read_bytes()
    # EVERY TRANSCRIBED SPAN IN THE OBJECT MUST BE ON THE COMMAND LINE. `kit.mk` globs `src/asm/` and
    # the test suites list their own bodies, so a body added to a `.S` is pinned there the day it is
    # written — but this gate is an argv list, and a body missing from it is a span the SHIPPED
    # object carries and nobody compared. That is the silent half of this file's own argument.
    named = {name for name, _, _ in spans}
    unpinned = sorted(sym[:-len(BODY_SUFFIX)] for sym in table
                      if sym.endswith(BODY_SUFFIX) and sym[:-len(BODY_SUFFIX)] not in named)
    if unpinned:
        raise SystemExit(f"ERROR: {obj} defines transcribed bodies this gate was not asked about: "
                         f"{', '.join(unpinned)}\n"
                         f"       add each as <name>=<original address> to the build.sh call, or "
                         f"the object that ships carries a span nobody compared")
    for name, address, expected in spans:
        try:
            lo, hi = table[name + BODY_SUFFIX], table[name + BODY_END_SUFFIX]
        except KeyError:
            raise SystemExit(f"ERROR: {obj} carries no {name}{BODY_SUFFIX} / {name}{BODY_END_SUFFIX} "
                             f"bracket — a transcribed span has to name itself to be pinned") from None
        if hi <= lo:
            raise SystemExit(f"ERROR: {name}'s body bracket is empty ({lo:#x}..{hi:#x})")
        # THE TILING ASSERTION, and it is only possible for a SEGMENTED body: the byte compare below
        # is a PREFIX compare — a segment that lost its last instruction still matches the original's
        # first bytes and passes. The derived length is what says it did not, and the segments'
        # derivation is what makes them cover the body's whole extent.
        if expected is not None and hi - lo != expected:
            raise SystemExit(f"ERROR: {name} assembles to {hi - lo} bytes and the original's span at "
                             f"{address:#x} is {expected} — the segment gained or lost an "
                             f"instruction, and a byte compare alone could not have said so")
        mine = text[lo:hi]
        theirs = image[address - load_base:address - load_base + len(mine)]
        if mine != theirs:
            at = next(i for i, (a, b) in enumerate(zip(mine, theirs)) if a != b)
            raise SystemExit(
                f"ERROR: the {name} twin THIS BUILD LINKS is not the original's code at "
                f"{address:#x}\n"
                f"       first difference at +{at:#x} (original {address + at:#x})\n"
                f"       linked   {mine[at:at + DIFF_BYTES].hex()}\n"
                f"       original {theirs[at:at + DIFF_BYTES].hex()}\n"
                f"       The suite pins the KIT's assembly of the same source; this pins the one\n"
                f"       that ships, and the two have diverged.")
        print(f"   {name}: {len(mine)} bytes at {address:#x}, identical to the original's")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
