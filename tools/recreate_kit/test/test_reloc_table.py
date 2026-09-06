"""Cross-language pin: the DRI relocation-table parsers in tools/ must agree.

``tools/prg_dis.py`` (Python — the canonical one, used by the differential oracle's loader) and
``tools/ghidra_scripts/PrgLoader.java`` (Java — used to build every project's Ghidra DB) each
carry a hand-written copy of the GEMDOS `.PRG` relocation stream decoder. CLAUDE.md §5 requires one
canonical definition with the other pinned equal by a test; they cannot import each other, so this
parses the Java source.

**Why this test exists.** The Java copy treated the stream's `1` byte as a fixup instead of a
254-byte span, which adds one bogus `+= load_base` every 254 bytes of the program. It shipped, and
it corrupted every project's DB — 536 spurious fixups in Wonder Boy's `SWB.PRG` (against 3 real
ones), 93 in BuggyBoy's, 44 in Joust's — silently: it deletes hardware operands, invents others,
and shifts immediates, with no impossible instruction and no desync to flag it. Nothing caught it,
because no project's `make test` touches `PrgLoader` at all. Hence a source-level pin.
"""
import re
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2]          # reverse/tools
JAVA = TOOLS / "ghidra_scripts" / "PrgLoader.java"

sys.path.insert(0, str(TOOLS))
import prg_dis                                        # noqa: E402

CONST_RE = re.compile(r"private static final int (RELOC_\w+) = (\d+);")
# The shape the fix must keep: the skip branch advances the cursor and reaches `continue`, so no
# offset is recorded for it. Matching the `continue` (rather than just the branch) is the point —
# the bug was an `fx.add(cur)` falling through this branch.
SKIP_BRANCH_RE = re.compile(
    r"if\s*\(\s*b\s*==\s*RELOC_SKIP\s*\)\s*\{[^}]*?cur\s*\+=\s*RELOC_SKIP_BYTES\s*;"
    r"[^}]*?continue\s*;[^}]*?\}", re.DOTALL)

# The other two shapes a header can describe, which the Java and the Python must agree on as
# firmly as they do on the skip byte: ABSFLAG set (offset +26) is a linker saying "no relocation
# table exists", while a file that stops before the table's first fixup LONGWORD is truncated and
# must be loud — an empty set there is a program loaded unrelocated in silence.
ABSFLAG_HEADER_OFF = 26
FIRST_FIXUP_BYTES = 4
ABSFLAG_CONST_RE = re.compile(r"static final int ABSFLAG_OFF = (\d+);")
ABSFLAG_READ_RE = re.compile(r"u16\(\s*data\s*,\s*ABSFLAG_OFF\s*\)")
ABSFLAG_BRANCH_RE = re.compile(
    r"if\s*\(\s*absflag\s*!=\s*0\s*\)\s*\{[^}]*?return\s+fx\s*;[^}]*?\}", re.DOTALL)
TRUNCATED_BOUND_RE = re.compile(
    r"if\s*\(\s*relocOff\s*\+\s*4\s*>\s*d\.length\s*\)\s*\{[^}]*?throw\s+new\s+Exception",
    re.DOTALL)

# A relocation stream exercising every byte the format defines, built here rather than read off a
# game so the expectation is arithmetic rather than a golden number: first fixup at 0x10, then a
# 4-byte step (fixup), then two spans (no fixups), then a 6-byte step (fixup), then the end.
FIRST_FIXUP = 0x10
STREAM = bytes([4, prg_dis.RELOC_SKIP, prg_dis.RELOC_SKIP, 6, prg_dis.RELOC_END])
EXPECTED = {FIRST_FIXUP,
            FIRST_FIXUP + 4,
            FIRST_FIXUP + 4 + 2 * prg_dis.RELOC_SKIP_BYTES + 6}


def _java_constants():
    return {name: int(value) for name, value in CONST_RE.findall(JAVA.read_text())}


def test_java_source_parses():
    """Guard the regexes: a rewrite of the Java parser must not silently empty this test."""
    assert JAVA.exists(), f"{JAVA} is missing — the pin cannot check anything"
    consts = _java_constants()
    assert consts, (f"parsed no RELOC_* constants out of {JAVA.name} — has the parser been "
                    "rewritten? This pin is now checking nothing.")


def test_reloc_constants_match():
    java = _java_constants()
    python = {"RELOC_END": prg_dis.RELOC_END,
              "RELOC_SKIP": prg_dis.RELOC_SKIP,
              "RELOC_SKIP_BYTES": prg_dis.RELOC_SKIP_BYTES}
    assert java == python, (
        f"DRI relocation constants diverged between tools/prg_dis.py and {JAVA.name}: "
        f"python={python} java={java}")


def test_java_skip_byte_records_no_fixup():
    """The exact bug: RELOC_SKIP must advance the cursor and record NOTHING."""
    assert SKIP_BRANCH_RE.search(JAVA.read_text()), (
        f"{JAVA.name}'s RELOC_SKIP branch no longer advances the cursor and `continue`s. If it "
        "falls through into the fixup path again, every Ghidra DB built with it gets one "
        "corrupted longword every 254 bytes — see docs/binary-formats.md.")


def test_python_skip_byte_records_no_fixup():
    """And the canonical side, behaviourally: spans move the cursor without adding offsets."""
    header = {"reloc_off": 0}
    data = FIRST_FIXUP.to_bytes(4, "big") + STREAM
    assert prg_dis.parse_reloc(data, header) == EXPECTED


def test_java_reads_absflag_and_returns_no_fixups():
    """ABSFLAG set is the one legitimate 'no table' shape — and the Java must read the word."""
    src = JAVA.read_text()
    const = ABSFLAG_CONST_RE.search(src)
    assert const and int(const.group(1)) == ABSFLAG_HEADER_OFF, (
        f"{JAVA.name} no longer names the ABSFLAG header word at offset {ABSFLAG_HEADER_OFF}")
    assert ABSFLAG_READ_RE.search(src), (
        f"{JAVA.name} does not read the header's ABSFLAG word; a .PRG with no relocation table "
        "then gets fixups invented out of whatever bytes follow the image.")
    assert ABSFLAG_BRANCH_RE.search(src), (
        f"{JAVA.name}'s parseRelocs no longer returns an empty list when ABSFLAG is set.")


def test_java_refuses_a_truncated_reloc_table():
    """The bound is `+ 4`, not `>= d.length`: 1-3 trailing bytes cannot hold the first fixup."""
    assert TRUNCATED_BOUND_RE.search(JAVA.read_text()), (
        f"{JAVA.name}'s parseRelocs no longer throws on relocOff + {FIRST_FIXUP_BYTES} > "
        "d.length. Guarding only `relocOff >= d.length` reads past the array on a file with "
        "1-3 spare bytes (projects/bubbleghost/bin/GHOST.LOA is one).")


def test_empty_reloc_table_is_no_relocations():
    assert prg_dis.parse_reloc(b"\x00\x00\x00\x00", {"reloc_off": 0}) == set()


def test_absflag_header_means_no_relocations():
    """ABSFLAG wins over whatever bytes sit at the reloc offset — they are not a table."""
    data = FIRST_FIXUP.to_bytes(4, "big") + STREAM
    assert prg_dis.parse_reloc(data, {"reloc_off": 0, "absf": 0xffff}) == set()


@pytest.mark.parametrize("spare", range(FIRST_FIXUP_BYTES))
def test_truncated_reloc_table_raises(spare):
    """0-3 bytes where a longword belongs is a truncated file, and every caller must hear it."""
    data = b"\x00" * (10 + spare)
    with pytest.raises(ValueError, match="truncated reloc table"):
        prg_dis.parse_reloc(data, {"reloc_off": 10, "absf": 0})
