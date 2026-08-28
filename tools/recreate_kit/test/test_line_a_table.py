"""Cross-language pin: the Line-A opcode table in tools/ must match the one in docs/.

``tools/ghidra_scripts/LineAResolve.java`` names each Line-A call in the comment it writes into
``decomp.c``; ``docs/tos-os-calls.md`` carries the same table for the reader. They cannot import
each other, so CLAUDE.md §5 wants one pinned equal to the other by a test — this one. The pin is
worth having: the list that was in ``docs/hardware-map.md`` before this test had `$A00A` as "draw
sprite" (it is *hide mouse*) and `$A00D` as "copy raster" (it is *draw sprite*).

Canonical definition: the markdown table. The Java array is the copy under test.
"""
import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]           # reverse/tools
REVERSE = TOOLS.parent
JAVA = TOOLS / "ghidra_scripts" / "LineAResolve.java"
DOC = REVERSE / "docs" / "tos-os-calls.md"

JAVA_ARRAY_RE = re.compile(r"LINE_A_CALLS\s*=\s*\{(.*?)\}\s*;", re.DOTALL)
JAVA_STRING_RE = re.compile(r'"([^"]*)"')
# Two opcode/name pairs per markdown row: | `$a000` | Init | `$a008` | TextBlt |
DOC_PAIR_RE = re.compile(r"`\$(a[0-9a-f]{3})`\s*\|\s*([^|]+?)\s*\|")

LINE_A_BASE = 0xA000
LINE_A_CALL_COUNT = 16                                # $a000-$a00f are the documented calls


def _java_calls():
    """Ordered list of call names from the Java LINE_A_CALLS array literal."""
    body = JAVA_ARRAY_RE.search(JAVA.read_text())
    return JAVA_STRING_RE.findall(body.group(1)) if body else []


def _doc_calls():
    """opcode -> call name, parsed from the markdown table in docs/tos-os-calls.md."""
    return {int(op, 16): name for op, name in DOC_PAIR_RE.findall(DOC.read_text())}


def test_sources_parse():
    """Guard the regexes: a rewrite of either table must not silently empty this test."""
    java, doc = _java_calls(), _doc_calls()
    assert len(java) == LINE_A_CALL_COUNT, (
        f"parsed {len(java)} names out of {JAVA.name}'s LINE_A_CALLS — has the array form changed?")
    assert len(doc) == LINE_A_CALL_COUNT, (
        f"parsed {len(doc)} rows out of {DOC.name}'s Line-A table — has the table form changed?")


def test_line_a_tables_match():
    """The Java array == the markdown table, opcode for opcode."""
    java, doc = _java_calls(), _doc_calls()
    java_by_opcode = {LINE_A_BASE + i: name for i, name in enumerate(java)}
    assert java_by_opcode == doc, (
        f"Line-A tables diverged between {JAVA.name} and docs/{DOC.name}: "
        + str({f"${k:04x}": (doc.get(k), java_by_opcode.get(k))
               for k in set(doc) | set(java_by_opcode) if doc.get(k) != java_by_opcode.get(k)}))
