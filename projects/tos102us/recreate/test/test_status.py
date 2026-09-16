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
# ...and the same row with its ADDRESS and its Tier 3 cell picked out. The columns are
# `| Addr | Name | Cases | Cost | Tier 3 | Status | Verification |`, so the cell is the fifth.
_VERIFIED_ROW_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|(?:[^|]*\|){3}"
                              r"(?P<tier3>[^|]*)\|[^|]*✅ verified[^|]*\|", re.M)
# A ratio as either file spells one: `0.62`, `**0.62**`, `1.50x`.
_RATIO_RE = re.compile(r"\d+\.\d\d")
# One measured row of `build/bench/tier3.txt`: its ROM address and the ratio at the end of the line.
# The costs on the way past are `insns/cycles` pairs and carry no decimal point, so the ratio is the
# only thing on a row that looks like one.
_TABLE_ROW_RE = re.compile(r"^.*\$(?P<addr>fc[0-9a-f]+)\s.*?(?P<ratio>\d+\.\d\d)\s*\S*$", re.M)

# The table `make bench` writes, which `../Makefile` makes a prerequisite of `test` — so it is
# always present and always current when this runs. STATUS.md QUOTES it; nothing re-derives a
# quoted number, which is the shape that goes stale.
BENCH_TABLE = REC / "build" / "bench" / "tier3.txt"
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


def test_every_component_with_code_has_a_section_that_covers_it():
    """THE REVERSE OF THE CHECK BELOW, and the one that catches a wave landing code without a ledger.

    `test_every_section_names_a_real_component` refuses a section for a component that does not
    exist; nothing refused a COMPONENT that has no section — which is the failure that goes
    unnoticed, because every stated count still agrees with every row when the rows were never
    written at all.

    The floor is the number of `.c` FILES in the directory rather than of functions, since several
    hold more than one ROM routine (`src/bios/bcon.c` is three, `src/bios/sysvars.c` two). A section
    may therefore be well ahead of this number, but it can never be behind it: a component with five
    reconstructed cores and four rows has lost one.
    """
    stated = {name: count for name, count, _rows in _sections()}
    for directory in sorted(path for path in (REC / "src").iterdir() if path.is_dir()):
        cores = sorted(directory.glob("*.c"))
        if not cores:
            continue
        assert directory.name in stated, (
            f"src/{directory.name}/ holds {len(cores)} reconstructed core(s) and STATUS.md has no "
            f"`## Verified — {directory.name} (N)` section — the ledger is missing a component, "
            f"which no count in it can show")
        assert stated[directory.name] >= len(cores), (
            f"STATUS.md's `## Verified — {directory.name} ({stated[directory.name]})` section "
            f"carries fewer rows than src/{directory.name}/ has .c files ({len(cores)}: "
            f"{', '.join(path.name for path in cores)}) — at least one reconstructed function has "
            f"no row")


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


# ---- the Tier 3 column, against the measurement it quotes -----------------------------------------

def _measured_ratios():
    """{ROM address: the set of ratios `make bench` measured for it}, out of the generated table."""
    assert BENCH_TABLE.exists(), (
        f"{BENCH_TABLE} is missing — `make bench` writes it and ../Makefile makes it a prerequisite "
        f"of `test`, so this ran outside that. Run `make bench`.")
    ratios = {}
    for match in _TABLE_ROW_RE.finditer(BENCH_TABLE.read_text()):
        ratios.setdefault(int(match["addr"], 16), set()).add(match["ratio"])
    assert ratios, f"{BENCH_TABLE} holds no measured rows — its shape has changed under this pin"
    return ratios


def _as_text(ratios):
    """A set of ratios as a reader would paste them: `0.60x, 0.74x`, smallest first."""
    return ", ".join(f"{ratio}x" for ratio in sorted(ratios))


def _verified_rows():
    """[(ROM address, the Tier 3 cell)] for every ✅ verified row in the ledger."""
    return [(int(match["addr"], 16), match["tier3"].strip())
            for match in _VERIFIED_ROW_RE.finditer(_status())]


def test_every_verified_row_quotes_its_measured_tier_3_ratios():
    """STATUS.md's Tier 3 column against `build/bench/tier3.txt`, ratio by ratio.

    The ledger is quoted in reports, and a number nobody re-derives is one nobody notices going
    wrong: a ratio hand-copied before a core changed, or a `—` left behind by a wave that added the
    row and not the cell. `bench/tier3.py` measures both sides on one instrument and writes that
    file; this holds the prose to it.

    Every ratio a cell names must be one the table measured for THAT address — a cell may name fewer
    (a row per branch is more than a summary wants), but not one that was never measured — and a row
    the table prices may not say `—`.
    """
    measured = _measured_ratios()
    rows = _verified_rows()
    assert rows, ("STATUS.md has no `| `0xADDR` | … | ✅ verified |` rows this pin can read — either "
                  "the ledger's columns moved or the Tier 3 column is no longer the fifth")
    # EVERY ROW, not the first that is wrong: this reds after a wave that measured a new set, and a
    # message naming one address at a time would be walked through a row per run.
    wrong = []
    for address, cell in rows:
        ratios = measured.get(address)
        quoted = set(_RATIO_RE.findall(cell))
        if not ratios:
            wrong.append(f"{address:#x}: ✅ verified, but `make bench` measured no row for it — "
                         f"add the routine to bench/tier3.py's CALL table")
        elif not quoted:
            wrong.append(f"{address:#x}: says {cell!r}; measured {_as_text(ratios)}")
        elif quoted - ratios:
            wrong.append(f"{address:#x}: quotes {_as_text(quoted - ratios)}, which was not measured "
                         f"for it; measured {_as_text(ratios)}")
    assert not wrong, (
        f"{len(wrong)} STATUS.md row(s) disagree with {BENCH_TABLE.name}, which `make bench` wrote:"
        + "".join(f"\n  {line}" for line in wrong))


def test_every_address_the_table_prices_has_a_verified_row():
    """THE REVERSE OF THE PIN ABOVE, and the one that catches a measurement nobody wrote down.

    The check above walks the LEDGER and asks the table about each row: a ✅ row with no measurement
    reds. Nothing walked the TABLE. So an address `make bench` prices and STATUS.md has no row for
    is invisible — the ledger is complete about itself, every count agrees, and a function that was
    reconstructed, verified and measured is missing from the only document anybody quotes.

    It is a live gap rather than a hypothetical one: the trap dispatcher has TWO exception entries
    at two addresses ($fc07f8 and $fc07f2), the table prices both, and the ledger carried one row.
    """
    measured = _measured_ratios()
    rows = {address for address, _cell in _verified_rows()}
    missing = sorted(set(measured) - rows)
    assert not missing, (
        f"{len(missing)} address(es) `make bench` measured have no `✅ verified` row in STATUS.md: "
        + ", ".join(f"{address:#x} ({_as_text(measured[address])})" for address in missing)
        + ". The ledger is the document reports quote; a measured function missing from it is a "
          "function nobody can find")
