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


def test_empty_reloc_table_is_no_relocations():
    assert prg_dis.parse_reloc(b"\x00\x00\x00\x00", {"reloc_off": 0}) == set()
    assert prg_dis.parse_reloc(b"", {"reloc_off": 0}) == set()
