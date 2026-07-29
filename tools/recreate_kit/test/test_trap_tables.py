"""Cross-language pin: the TOS trap-name tables in tools/ must agree.

``tools/prg_dis.py`` (Python, the first-pass disassembler) and
``tools/ghidra_scripts/AtariOsTrapAnnotate.java`` (Java, the Ghidra annotator) each carry a
hand-written copy of the GEMDOS/BIOS/XBIOS function-number -> name maps. CLAUDE.md §5 requires
one canonical definition with the other pinned equal by a test; they cannot import each other,
so this test parses the Java source's ``put(TABLE, 0xNN, "Name")`` calls and compares.

Scope: **XBIOS only**. That is the table the sound layer depends on and the one whose
decimal-vs-hex trap numbering already mislabelled a game once (see the warning in prg_dis.py's
XBIOS dict). The GEMDOS/BIOS maps have a known pre-existing divergence — the Java annotator
lists a deliberate subset — which is tracked separately, not fixed here.
"""
import re
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2]          # reverse/tools
JAVA = TOOLS / "ghidra_scripts" / "AtariOsTrapAnnotate.java"

sys.path.insert(0, str(TOOLS))
import prg_dis                                        # noqa: E402

PUT_RE = re.compile(r'put\(\s*(GEMDOS|BIOS|XBIOS)\s*,\s*(0[xX][0-9a-fA-F]+)\s*,\s*"([^"]+)"\s*\)')


def _java_tables():
    """table name -> {opcode: name}, parsed from the annotator's put(...) calls."""
    tables = {"GEMDOS": {}, "BIOS": {}, "XBIOS": {}}
    for table, num, name in PUT_RE.findall(JAVA.read_text()):
        tables[table][int(num, 16)] = name
    return tables


def test_java_source_parses():
    """Guard the regex itself: a rewrite of the Java table must not silently empty this test."""
    tables = _java_tables()
    assert JAVA.exists(), f"{JAVA} is missing — the pin cannot check anything"
    for name, table in tables.items():
        assert table, f"parsed no {name} entries out of {JAVA.name} — has the put(...) form changed?"


def test_xbios_tables_match():
    """prg_dis.XBIOS == the annotator's XBIOS map, entry for entry."""
    java = _java_tables()["XBIOS"]
    assert java == prg_dis.XBIOS, (
        "XBIOS trap tables diverged between tools/prg_dis.py and "
        f"{JAVA.name}: only-in-python={sorted(set(prg_dis.XBIOS) - set(java))} "
        f"only-in-java={sorted(set(java) - set(prg_dis.XBIOS))} "
        "renamed=" + str({k: (prg_dis.XBIOS[k], java[k]) for k in set(java) & set(prg_dis.XBIOS)
                          if java[k] != prg_dis.XBIOS[k]}))
