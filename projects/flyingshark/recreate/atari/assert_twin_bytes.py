#!/usr/bin/env python3
"""Assert that the asm twin THIS BUILD LINKS is the original binary's own machine code.

    assert_twin_bytes.py <twin.o> <FLYSHARK.IMG> <load base> <name>=<original address> ...

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


def symbols(obj):
    """{name: offset} for the object's own symbols, which for a `.o` are section-relative."""
    found = {}
    for line in subprocess.run([NM, str(obj)], check=True, capture_output=True,
                               text=True).stdout.splitlines():
        fields = line.split()
        if len(fields) == 3:
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
    spans = [pair.split("=") for pair in argv[3:]]

    table, text, image = symbols(obj), text_of(obj), image_path.read_bytes()
    for name, address in spans:
        address = int(address, 0)
        try:
            lo, hi = table[name + BODY_SUFFIX], table[name + BODY_END_SUFFIX]
        except KeyError:
            raise SystemExit(f"ERROR: {obj} carries no {name}{BODY_SUFFIX} / {name}{BODY_END_SUFFIX} "
                             f"bracket — a transcribed span has to name itself to be pinned") from None
        if hi <= lo:
            raise SystemExit(f"ERROR: {name}'s body bracket is empty ({lo:#x}..{hi:#x})")
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
