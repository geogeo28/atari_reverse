"""Pin STATUS.md's stated counts to the rows it actually carries.

Several agents append rows to their own subsystem section at once. Nothing else in the suite reads
STATUS.md, so a count that drifts is invisible — and a ledger whose numbers are wrong is worse than
none, because it is quoted in reports. Each section states its own count (the only number its owner
touches) and the header states no literal at all, so there is no shared line to collide on.

Ported from `projects/zynaps/recreate/test/test_status.py` with ONE difference, and it is the
bootstrap's: a section may exist before its `src/<name>.c` does, as long as it is EMPTY. This
project opens with the five planned subsystems and no rows, so that the first agent into each finds
a heading rather than inventing one — and the moment a section carries a row, the source file it is
named after must exist. See `test_a_section_with_rows_names_a_real_subsystem`.
"""
import re
from pathlib import Path

REC = Path(__file__).resolve().parents[1]

# `## Verified — <subsystem> (N)`, and the `| `0xADDR` | ... | ✅ verified |` rows beneath it.
_SECTION_RE = re.compile(r"^## Verified — (?P<name>\S+) \((?P<count>\d+)\)\s*$", re.M)
_ROW_RE = re.compile(r"^\| `0x[0-9a-f]+` \|.*\| ✅ verified \|", re.M)


def _sections():
    """[(subsystem, stated count, rows found)] in file order."""
    text = (REC / "STATUS.md").read_text()
    heads = list(_SECTION_RE.finditer(text))
    out = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[head.end():end]
        out.append((head["name"], int(head["count"]), len(_ROW_RE.findall(body))))
    return out


def test_every_section_states_its_own_row_count():
    sections = _sections()
    assert sections, ("STATUS.md has no `## Verified — <subsystem> (N)` section headings — either "
                      "the ledger's shape changed or the heading format did")
    for name, stated, rows in sections:
        assert stated == rows, (
            f"STATUS.md's `## Verified — {name} ({stated})` section carries {rows} verified rows — "
            f"re-count that section and update its heading")


def test_a_section_with_rows_names_a_real_subsystem():
    """The heading is the source file's stem, so a section with rows implies code that has them.

    Keeps the ledger's vocabulary and the tree's identical — the alias drift ("util", "sprite /
    video") this replaced in the sibling projects made the sections unsearchable from a file name.
    An EMPTY section is exempt: it is a placeholder for a subsystem nobody has started, and the
    first row landing in it is what obliges `src/<name>.c` to exist.
    """
    stems = {path.stem for path in (REC / "src").glob("*.c")}
    for name, _stated, rows in _sections():
        if rows:
            assert name in stems, (
                f"STATUS.md's `## Verified — {name}` section carries {rows} rows but there is no "
                f"src/{name}.c; sections are named after the source file"
                + (f" (one of {', '.join(sorted(stems))})" if stems else ""))


def test_the_headline_total_is_not_a_second_count():
    """No section's count may be restated at the top, where nobody would re-derive it.

    `docs/agent-playbook.md` §12: a headline nobody recomputes stays at whichever wave last wrote
    it. The ledger's rule here is that the verified total is the SUM of the section headings and is
    written nowhere else, so this refuses a `**Verified: N**` literal creeping back in.
    """
    text = (REC / "STATUS.md").read_text()
    stated = re.findall(r"^\*\*Verified: *(\d+)", text, re.M)
    assert not stated, (
        f"STATUS.md states a literal verified total ({', '.join(stated)}). It is the sum of the "
        f"per-section counts and must stay unwritten, or it drifts the moment a section changes")
