"""Pin STATUS.md's stated counts to the rows it actually carries.

Several agents append rows to their own component's section at once. Nothing else in the suite reads
STATUS.md, so a count that drifts is invisible — and a ledger whose numbers are wrong is worse than
none, because it is quoted in reports. Each section states its own count (the only number its owner
touches), and the Components table at the top of the file states the same number a second time,
which is exactly the shape that goes stale: so it is re-derived here rather than re-read by hand.

Ported from `projects/zynaps/recreate/test/test_status.py`, with one adaptation: a component of this
project is a DIRECTORY under `src/` (`src/xbios/`, later `src/bios/`, `src/gemdos/`…), not a single
`.c` file, because a TOS component is dozens of functions rather than one subsystem file.
"""
import re
from pathlib import Path

REC = Path(__file__).resolve().parents[1]

# `## Verified — <component> (N)`, and the `| `0xADDR` | ... | ✅ verified |` rows beneath it.
_SECTION_RE = re.compile(r"^## Verified — (?P<name>\S+) \((?P<count>\d+)\)\s*$", re.M)
_ROW_RE = re.compile(r"^\| `0x[0-9a-f]+` \|.*\| ✅ verified \|", re.M)
# ...and the Components table's own claim: `| <component> | <Tier 1 count> | …`.
_COMPONENT_RE = re.compile(r"^\| (?P<name>\S+) \| (?P<tier1>\d+) \|", re.M)


def _status():
    return (REC / "STATUS.md").read_text()


def _sections():
    """[(component, stated count, rows found)] in file order."""
    text = _status()
    heads = list(_SECTION_RE.finditer(text))
    out = []
    for i, head in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[head.end():end]
        out.append((head["name"], int(head["count"]), len(_ROW_RE.findall(body))))
    return out


def test_every_section_states_its_own_row_count():
    sections = _sections()
    assert sections, ("STATUS.md has no `## Verified — <component> (N)` section headings — either "
                      "the ledger's shape changed or the heading format did")
    for name, stated, rows in sections:
        assert stated == rows, (
            f"STATUS.md's `## Verified — {name} ({stated})` section carries {rows} verified rows — "
            f"re-count that section and update its heading")


def test_every_section_names_a_real_component():
    """The heading is a source DIRECTORY's name, so a section can only exist for code that does.

    Keeps the ledger's vocabulary and the tree's identical: a section named for something with no
    `src/<name>/` is a component nobody can find from a file name.
    """
    components = {path.name for path in (REC / "src").iterdir() if path.is_dir()}
    for name, _stated, _rows in _sections():
        assert name in components, (
            f"STATUS.md has a `## Verified — {name}` section but there is no src/{name}/; sections "
            f"are named after the component directory (one of {', '.join(sorted(components))})")


def test_the_components_table_agrees_with_the_sections():
    """The Tier 1 column is the same number as the section heading's, written twice — so it is the
    one nobody re-sums. A component with no section yet must say 0."""
    stated = {name: count for name, count, _rows in _sections()}
    table = {match["name"]: int(match["tier1"]) for match in _COMPONENT_RE.finditer(_status())}
    assert table, "STATUS.md's Components table has no `| <component> | <count> |` rows"
    for name, tier1 in table.items():
        assert tier1 == stated.get(name, 0), (
            f"STATUS.md's Components table says {name} has {tier1} verified function(s), but its "
            f"`## Verified — {name}` section carries {stated.get(name, 0)}")
