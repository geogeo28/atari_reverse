"""Pin STATUS.md's stated counts to the rows it actually carries.

Several agents append rows to their own subsystem section at once. Nothing else in the suite reads
STATUS.md, so a count that drifts is invisible — and a ledger whose numbers are wrong is worse than
none, because it is quoted in reports. Each section states its own count (the only number its owner
touches) and the header states no literal at all, so there is no shared line to collide on.
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


def test_every_section_names_a_real_subsystem():
    """The heading is the source file's stem, so a section can only exist for code that does.

    Keeps the ledger's vocabulary and the tree's identical — the alias drift ("util", "sprite /
    video") this replaced made the sections unsearchable from a file name.
    """
    stems = {path.stem for path in (REC / "src").glob("*.c")}
    for name, _stated, _rows in _sections():
        assert name in stems, (
            f"STATUS.md has a `## Verified — {name}` section but there is no src/{name}.c; "
            f"sections are named after the source file (one of {', '.join(sorted(stems))})")
