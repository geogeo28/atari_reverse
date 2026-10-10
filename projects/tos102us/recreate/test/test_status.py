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

import pytest

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
# only thing on a row that looks like one. The whole ROM, $fc0000..$feffff: the AES lives at $fe..., and a
# pattern that stopped at $fd would leave every AES row unpinned in both directions.
_TABLE_ROW_RE = re.compile(r"^.*\$(?P<addr>f[c-e][0-9a-f]+)\s.*?(?P<ratio>\d+\.\d\d)\s*\S*$", re.M)

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


# ...and the row a routine verified but NOT priced carries instead: its Status cell `⚠️ verified, unpriced`.
_UNPRICED_ROW_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|(?:[^|]*\|){4}[^|]*⚠️ verified, unpriced[^|]*\|", re.M)


def _unpriced_rom_entries():
    """The ROM addresses of every case registered VERIFIED and UNPRICED (`test_boot_snapshot.UNPRICED_CASES`) — a
    case entered at a staged stub in RAM names no routine, and is priced, if at all, by the routine's own rows."""
    import test_boot_snapshot
    from harness import addrs

    rom = range(addrs.ROM_BASE, addrs.ROM_BASE + addrs.ROM_BYTES)
    return {entry: name for name, entry, *_rest in test_boot_snapshot.UNPRICED_CASES if entry in rom}


def test_every_routine_verified_unpriced_has_a_row_too():
    """THE UNPRICED CASES' half of the pin above: a table walk cannot see a routine the table does not price, so a
    routine whose only cases are UNPRICED could be verified, swept and absent from the ledger. Each such address needs
    a row — `✅ verified` when another of its rows is priced (the pin above then holds its ratios to the table), or
    `⚠️ verified, unpriced` when none is, which the pin above leaves alone and a `✅` it would red."""
    rows = {address for address, _cell in _verified_rows()}
    rows |= {int(match["addr"], 16) for match in _UNPRICED_ROW_RE.finditer(_status())}
    missing = {entry: name for entry, name in _unpriced_rom_entries().items() if entry not in rows}
    assert not missing, (
        f"{len(missing)} routine(s) with verified, unpriced cases have no STATUS.md row: "
        + ", ".join(f"{entry:#x} ({name})" for entry, name in sorted(missing.items()))
        + ". Add one — `⚠️ verified, unpriced` with the reason, when no row of the routine is priced")


# ---- THE SECOND COUNT: a row that calls a rebound entry is held twice, and STATUS.md quotes both ------------------------
# `bench/tier3.py` prints the pair under such a row on a line of its own (`CALLER_LINE`: `TWO COUNTS: own / the
# caller's own (ours against the ROM's)`); STATUS.md quotes it in the row's notes in the same form — `0.45 / 0.37 (812
# against 2216)`. Hand-typed, a second count goes stale the day a caller's codegen moves, so it is held here both
# ways: a pair the ledger quotes is one the table measured for THAT address, and every pair the table measured
# whose two counts differ by more than TWO_COUNTS_QUOTED_FROM is quoted.
_TWO_COUNTS = r"(?P<own>\d+\.\d\d) / (?P<caller>\d+\.\d\d) \((?P<ours>\d+) against (?P<the_rom_s>\d+)\)"
_TABLE_TWO_COUNTS_RE = re.compile(r"^\s+TWO COUNTS: " + _TWO_COUNTS, re.M)
_QUOTED_TWO_COUNTS_RE = re.compile(_TWO_COUNTS)
_VERIFIED_LINE_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|.*✅ verified.*$", re.M)
_ADDRESS_ON_A_TABLE_ROW_RE = re.compile(r"\$(?P<addr>f[c-e][0-9a-f]+)\s")
TWO_COUNTS_QUOTED_FROM = 0.05
# ...and the section's own summary of them, in its words: "<N> rows carry both; they differ by more than 0.05 in <M>".
_TWO_COUNTS_SUMMARY_RE = re.compile(r"(?P<rows>\d+) rows carry both; they differ by more than 0\.05 in (?P<apart>\d+)")


def _pair(match):
    return match["own"], match["caller"], match["ours"], match["the_rom_s"]


def _measured_two_counts():
    """{ROM address: the `(own, caller's own, ours, the ROM's)` pairs the table printed under its rows} — each
    `TWO COUNTS` line belongs to the measured row above it."""
    measured, address = {}, None
    for line in BENCH_TABLE.read_text().splitlines():
        counted = _TABLE_TWO_COUNTS_RE.match(line)
        if counted:
            assert address is not None, f"a TWO COUNTS line under no measured row: {line.strip()[:80]}"
            measured.setdefault(address, []).append(_pair(counted))
        elif _TABLE_ROW_RE.match(line) and not line.startswith(" "):
            address = int(_ADDRESS_ON_A_TABLE_ROW_RE.search(line)["addr"], 16)
    return measured


def _apart(pair):
    own, caller, _ours, _the_rom_s = pair
    return round(abs(float(own) - float(caller)), 2) > TWO_COUNTS_QUOTED_FROM


def test_every_second_count_the_ledger_quotes_is_one_the_table_measured():
    """A `own / the caller's own (ours against the ROM's)` the ledger quotes in a verified row is a pair
    `make bench` printed for that address — all four numbers."""
    measured = _measured_two_counts()
    wrong = [f"{int(row['addr'], 16):#x}: quotes {' / '.join(_pair(quoted)[:2])} ({quoted['ours']} against "
             f"{quoted['the_rom_s']}), which the table does not print for it"
             for row in _VERIFIED_LINE_RE.finditer(_status()) for quoted in _QUOTED_TWO_COUNTS_RE.finditer(row[0])
             if _pair(quoted) not in measured.get(int(row["addr"], 16), ())]
    assert not wrong, f"{len(wrong)} second count(s) STATUS.md quotes were not measured:" + "".join(f"\n  {line}" for line in wrong)


def test_every_row_whose_two_counts_differ_is_quoted_with_both():
    """THE REVERSE: a row the table holds on two counts that differ by more than 0.05 has BOTH in the ledger's row
    for its address — and the section's summary of how many there are is the table's count."""
    measured, status = _measured_two_counts(), _status()
    quoted = {}
    for row in _VERIFIED_LINE_RE.finditer(status):
        quoted.setdefault(int(row["addr"], 16), set()).update(_pair(each) for each in _QUOTED_TWO_COUNTS_RE.finditer(row[0]))
    missing = [f"{address:#x}: {pair[0]} / {pair[1]} ({pair[2]} against {pair[3]})"
               for address, pairs in sorted(measured.items()) for pair in pairs
               if _apart(pair) and pair not in quoted.get(address, ())]
    assert not missing, (f"{len(missing)} row(s) whose two counts differ by more than {TWO_COUNTS_QUOTED_FROM} are not "
                         f"quoted with both in STATUS.md:" + "".join(f"\n  {line}" for line in missing))
    summary = _TWO_COUNTS_SUMMARY_RE.search(status)
    assert summary, "STATUS.md no longer says how many rows carry both counts (`N rows carry both; they differ … in M`)"
    rows = sum(len(pairs) for pairs in measured.values())
    apart = sum(_apart(pair) for pairs in measured.values() for pair in pairs)
    assert (int(summary["rows"]), int(summary["apart"])) == (rows, apart), (
        f"STATUS.md says {summary['rows']} rows carry both counts and {summary['apart']} differ by more than 0.05; "
        f"the table holds {rows} and {apart}")


# ---- THE EVENT DOOR'S STATE: what the ledger says of each entry's twin is what the BUILD says ------------------------
# A flip is one edit in `include/aes/evdoor.h` and everything in the suite follows it by derivation — so nothing but
# the ledger STATES which entries are rebound, and a ledger nothing holds would go on saying "pending" (or "rebound",
# over a wrapper put back on the ROM's call) with every test green. Each entry's row names its state in its Name cell,
# and the section's intro counts them in one fixed sentence; both are held to `aes_event.REBOUND` / `PENDING`.
_DOOR_STATE_RE = re.compile(r"— twin, (?P<state>REBOUND|PENDING)\b")
_DOOR_SUMMARY_RE = re.compile(r"THE DOOR TODAY: (?P<rebound>\d+) of its (?P<entries>\d+) entries REBOUND, (?P<pending>\d+) PENDING")
_NAME_CELL_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|(?P<name>[^|]*)\|", re.M)
NO_TWIN = "no twin"


def _door_states_built():
    """{entry: "REBOUND" | "PENDING" | NO_TWIN} as the host library has them (`test/aes_event.py`)."""
    import aes_event

    return {entry: "REBOUND" if entry in aes_event.REBOUND else "PENDING" if entry in aes_event.PENDING else NO_TWIN
            for entry in aes_event.ENTRIES}


def test_every_door_entry_s_row_says_what_the_build_says_of_its_twin():
    """`— twin, REBOUND` / `— twin, PENDING` in the Name cell of each door entry's row (neither, for an entry with no
    twin yet), and the intro's `THE DOOR TODAY: R of its N entries REBOUND, P PENDING` — against the library's markers."""
    built, status = _door_states_built(), _status()
    stated = {int(row["addr"], 16): state["state"] if (state := _DOOR_STATE_RE.search(row["name"])) else NO_TWIN
              for row in _NAME_CELL_RE.finditer(status)}
    wrong = [f"{entry:#x}: the build says {state}, its row says {stated.get(entry, 'nothing: it has no row')}"
             for entry, state in sorted(built.items()) if stated.get(entry) != state]
    assert not wrong, f"{len(wrong)} door entr(ies) whose STATUS.md row misstates the twin:" + "".join(f"\n  {line}" for line in wrong)
    strays = sorted(f"{address:#x}" for address, state in stated.items() if state != NO_TWIN and address not in built)
    assert not strays, f"STATUS.md calls a routine that is no door entry a door twin: {', '.join(strays)}"
    summary = _DOOR_SUMMARY_RE.search(status)
    assert summary, "STATUS.md no longer counts the door's entries (`THE DOOR TODAY: R of its N entries REBOUND, P PENDING`)"
    counted = tuple(sum(state == which for state in built.values()) for which in ("REBOUND", "PENDING"))
    assert (int(summary["rebound"]), int(summary["entries"]), int(summary["pending"])) == (counted[0], len(built), counted[1]), (
        f"STATUS.md says {summary[0]!r}; the build has {counted[0]} of {len(built)} rebound and {counted[1]} pending")


# ---- THE ROWS THAT SWITCH: what the ledger counts is what the registry holds -------------------------------------------
# A row that switches is registered (`aes_event.SWITCHING_ROWS`), and the ledger states how many there are THREE ways,
# each typed by hand: in each routine's Cases cell (`N rows (M of them SWITCH…`, `(1 SWITCHES…`, `N rows, ALL OF THEM
# SWITCH`), in the section's sentence (`N rows of the table are such runs`, `N rows of the table switch`) and in the
# Components table (`N rows SWITCH since band 4 wave 3`) — beside that cell's own count of the rows held on two
# counts. All of them are held here: a ledger that named one of a routine's rows fewer, or one more, reds.
_CASES_CELL_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|[^|]*\|(?P<cases>[^|]*)\|.*✅ verified", re.M)
_SWITCH_IN_A_CASES_CELL_RE = re.compile(r"(?P<count>\d+)(?: of them)? SWITCH(?:ES)?\b|(?P<every>\d+) rows, ALL OF THEM SWITCH\b")
_ROWS_THAT_SWITCH_RE = re.compile(r"(?P<rows>\d+) rows of the table (?:are such runs|switch)\b|(?P<component>\d+) rows SWITCH since"
                                  r"|THE ROWS THAT SWITCH, (?P<dsptch>\d+) since")
_COMPONENT_TWO_COUNTS_RE = re.compile(r"the caller's own net of those calls: (?P<rows>\d+) rows since")


def _registered_rows_that_switch():
    """{ROM address: how many registered rows that switch are of the routine there} (`aes_event.SWITCHING_ROWS`)."""
    import collections

    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    from harness import addrs

    return collections.Counter(getattr(addrs, held.row.name) for held in aes_event.SWITCHING_ROWS.values())


def test_every_routine_s_row_counts_its_rows_that_switch_as_the_registry_does():
    """THE CASES CELL of every verified row against the registry, address by address: the count it states of rows
    that SWITCH (none stated: none) is the number of rows registered for that routine — both ways, so a routine whose
    rows switch says so, and a cell cannot go on naming a row the registry dropped."""
    registered, stated = _registered_rows_that_switch(), {}
    for row in _CASES_CELL_RE.finditer(_status()):
        said = _SWITCH_IN_A_CASES_CELL_RE.search(row["cases"])
        stated[int(row["addr"], 16)] = int(said["count"] or said["every"]) if said else 0
    wrong = [f"{address:#x}: its Cases cell says {stated.get(address, 'nothing: it has no verified row')}, the registry holds "
             f"{registered.get(address, 0)}" for address in sorted(set(registered) | {at for at, count in stated.items() if count})
             if stated.get(address) != registered.get(address, 0)]
    assert not wrong, (f"{len(wrong)} STATUS.md row(s) miscount the routine's rows that switch "
                       f"(`aes_event.SWITCHING_ROWS`):" + "".join(f"\n  {line}" for line in wrong))


def test_every_count_of_the_rows_that_switch_is_the_registry_s():
    """...AND THE SENTENCES: every `N rows of the table are such runs` / `N rows of the table switch`, the Components
    cell's `N rows SWITCH since …` and dsptch's `THE ROWS THAT SWITCH, N since …` say the registry's total — and the
    Components cell's count of the rows held on TWO COUNTS is the table's (the section's own summary of them is held
    above)."""
    status, total = _status(), sum(_registered_rows_that_switch().values())
    said = [int(next(group for group in match.groups() if group)) for match in _ROWS_THAT_SWITCH_RE.finditer(status)]
    assert len(said) >= 3, "STATUS.md no longer counts the rows that switch in its three places (the section, the Components cell, dsptch's row)"
    assert set(said) == {total}, f"STATUS.md counts the rows that switch as {sorted(set(said))}; the registry holds {total}"
    in_the_component = _COMPONENT_TWO_COUNTS_RE.search(status)
    assert in_the_component, "the Components table no longer counts the rows held on two counts (`…net of those calls: N rows since…`)"
    on_two_counts = sum(len(pairs) for pairs in _measured_two_counts().values())
    assert int(in_the_component["rows"]) == on_two_counts, (
        f"the Components table says {in_the_component['rows']} rows are held on two counts; the table holds {on_two_counts}")


# ---- ...AND WHICH ROWS: the names, address by address ------------------------------------------------------------------
# A count of rows that switch is right for a ledger that names the WRONG rows: one renamed in its battery, one
# replaced by another of the same routine, a ratio quoted under a neighbour's name — all of them green above. Each
# verified row's Tier 3 cell lists its switching rows BY NAME after `THE ROWS THAT SWITCH:` (a routine all of whose
# rows switch lists them all there) — or after `THE ROWS THAT SWITCH (each the table's `<prefix>…`):`, where every
# one of them opens with the same words and the cell says them once (ev_multi's forty-five). Held, both ways:
#   * THE NAMES, the stated prefix put back, are the registry's;
#   * THE LIST IS A LIST: no name twice, and as many as the Cases cell counts (a set forgave a row listed twice
#     where another was missing from a cell whose count was right);
#   * EACH NAME'S RATIO IS ITS OWN: `**0.66** <name>` is the ratio the table prints on THAT row, and
#     `**0.66 / 0.32** <name>` the two counts it prints under it (a ratio quoted under a neighbour's name was one
#     "measured for the address", which is all the Tier 3 column's own pin asks);
#   * ONE VERIFIED ROW AN ADDRESS: a second one would be read over the first.
THE_ROWS_THAT_SWITCH = "THE ROWS THAT SWITCH"
_THE_ROWS_THAT_SWITCH_RE = re.compile(THE_ROWS_THAT_SWITCH + r"(?: \(each the table's `(?P<prefix>[^`]*?)…`\))?:")
_STATUS_COLUMN = " | ✅ verified"
# `**0.66** <the row's name> (`net`…)`: a name ends where its mechanism's tag opens (a name may hold parentheses).
_A_QUOTED_ROW_RE = re.compile(r"\*\*(?P<ratios>\d+\.\d\d(?: / \d+\.\d\d)?)\*\* (?P<case>.+?) \(`(?:net|glue|through|pinned|over)[^)]*\)")
# One measured row of the table with its NAME picked out: `<role> ($addr)  $addr  <name>  insns/cycles  insns/cycles  ratio`.
_TABLE_NAMED_ROW_RE = re.compile(r"^\S.*?\s\$(?P<addr>f[c-e][0-9a-f]+)\s+(?P<case>.+?)\s+\d+/\d+\s+\d+/\d+\s+(?P<ratio>\d+\.\d\d)\s")
_TWO_QUOTED = " / "


# ---- ...AND EACH QUOTED ROW'S VERDICT WORD IS THE TABLE'S ---------------------------------------------------------------------
# `**1.01** an image (V, `net`)` names the mechanism the table admitted the row by — `net`, `glue`, `through`, … — and a
# row whose word CHANGES has changed class: `glue` is over the bar as shipped and admitted net of its thunks. A ledger
# that goes on saying `net` under the new ratio hides that (the frame diet moved three, 2026-10-10, and every pin
# above stayed green: any of the words was accepted). Held, FOR EVERY QUOTE THAT CARRIES A WORD — none is skipped:
#   * where the cell quotes the row BY THE TABLE'S OWN NAME, the word is one the table prints on a row of that name
#     at that address;
#   * where it does not (a cell that abbreviates, or tags several rows at once: "…, all three clipped away (`glue`)"),
#     the word is one the table prints at that address ON A ROW OF THE RATIO THE WORD STANDS BESIDE — the last one
#     quoted before it. (The first form alone skipped 65 of 724 quotes in silence, and a word changed in one of them
#     stayed green: the fourth pass's review.) A quote that fits neither is a failure, by its address and its words.
_A_ROW_WITH_ITS_WORD_RE = re.compile(r"\*\*\d+\.\d\d(?: / \d+\.\d\d)?\*\* (?P<case>.+?) "
                                     r"\((?P<tags>[^)]*?`(?P<word>net|glue|through|pinned|over|rule|own|transcribed|accepted)`[^)]*)\)")
_A_QUOTED_RATIO_RE = re.compile(r"\*\*(\d+\.\d\d)(?: / \d+\.\d\d)?\*\*")
_TABLE_ROW_WITH_ITS_WORD_RE = re.compile(r"^\S.*?\s\$(?P<addr>f[c-e][0-9a-f]+)\s+(?P<case>.+?)\s+\d+/\d+\s+\d+/\d+\s+(?P<ratio>\d+\.\d\d)"
                                         r"[ \t]*(?P<word>\S*)[ \t]*$", re.M)
QUOTES_HELD_BY_THE_ROW_S_NAME_AT_LEAST, QUOTES_HELD_BY_THE_RATIO_AT_MOST = 600, 80


def _verdict_words_of_the_table():
    """`({(ROM address, a row's name): words}, {(ROM address, a ratio as printed): words})` — the verdict words the
    table prints on the rows of that name there (a `.S` row and its C twin's may share one), and on the rows of
    that ratio there."""
    by_name, by_ratio = {}, {}
    for row in _TABLE_ROW_WITH_ITS_WORD_RE.finditer(BENCH_TABLE.read_text()):
        by_name.setdefault((int(row["addr"], 16), row["case"].strip()), set()).add(row["word"])
        by_ratio.setdefault((int(row["addr"], 16), row["ratio"]), set()).add(row["word"])
    return by_name, by_ratio


def test_every_quoted_row_s_verdict_word_is_the_one_the_table_prints_for_it():
    by_name, by_ratio = _verdict_words_of_the_table()
    by_the_name, by_the_ratio, wrong = 0, 0, []
    for row in _VERIFIED_LINE_RE.finditer(_status()):
        address = int(row["addr"], 16)
        for quote in _A_ROW_WITH_ITS_WORD_RE.finditer(row[0]):
            beside = _A_QUOTED_RATIO_RE.findall(quote[0])[-1]
            if (address, quote["case"]) in by_name:
                by_the_name += 1
                printed = by_name[address, quote["case"]]
            else:
                by_the_ratio += 1
                printed = by_ratio.get((address, beside), set())
            if quote["word"] not in printed:
                wrong.append(f"{address:#x}: `{quote['word']}` beside {beside} for {quote['case'][-60:]!r}; the table prints {sorted(printed)}")
    assert by_the_name >= QUOTES_HELD_BY_THE_ROW_S_NAME_AT_LEAST and by_the_ratio <= QUOTES_HELD_BY_THE_RATIO_AT_MOST, (
        f"{by_the_name} quotes name their row as the table does, {by_the_ratio} do not: the cells' shape moved")
    assert not wrong, f"{len(wrong)} verdict word(s) STATUS.md quotes are not the table's:" + "".join(f"\n  {line}" for line in wrong)


# ---- ...AND THE CYCLES A ROW'S NOTES QUOTE IN WORDS ARE THE PINS' ------------------------------------------------------------
# "own 20598 against 30594" in a row's notes is a pinned price spelt in prose — `Priced((ours, the ROM's), …)` in the
# row's battery — and nothing re-derived it: a build change re-pins the battery (by tool) and leaves the sentence
# (the frame diet left 41 stale, 2026-10-10: its review found them). Held: EVERY `own N against M` of a current row
# is a pinned pair — N our count pinned beside the ROM's M. One whose M is no pinned ROM count at all is a failure
# too, not a quote passed over (it was: a mistyped M stayed green).
_OWN_AGAINST_RE = re.compile(r"own (?P<ours>\d+) against (?P<the_rom_s>\d+)")
_A_PINNED_PAIR_RE = re.compile(r"\((\d{3,}), (\d{3,})\)")


def _pinned_own_counts_by_the_rom_s():
    """{the ROM's count: our counts pinned beside it} over every `(ours, the ROM's)` pair the batteries spell."""
    pinned = {}
    for battery in sorted((REC / "test").glob("test_*.py")):
        for ours, the_rom_s in _A_PINNED_PAIR_RE.findall(battery.read_text()):
            pinned.setdefault(int(the_rom_s), set()).add(int(ours))
    return pinned


def test_every_own_against_a_row_s_notes_quote_is_a_pinned_pair():
    pinned = _pinned_own_counts_by_the_rom_s()
    quoted = [(int(row["addr"], 16), int(each["ours"]), int(each["the_rom_s"])) for row in _VERIFIED_LINE_RE.finditer(_status())
              for each in _OWN_AGAINST_RE.finditer(row[0])]
    assert len(quoted) > 20, f"only {len(quoted)} `own N against M` quotes are found: the notes' shape moved"
    stale = [f"{address:#x}: own {ours} against {the_rom_s}; the pin beside {the_rom_s} is {sorted(pinned.get(the_rom_s, ())) or 'NONE'}"
             for address, ours, the_rom_s in quoted if ours not in pinned.get(the_rom_s, ())]
    assert not stale, f"{len(stale)} cycle quote(s) in STATUS.md's rows are not the pins':" + "".join(f"\n  {line}" for line in stale)


def _names_of_the_registered_rows_that_switch():
    """{ROM address: the names of the registered rows that switch of the routine there}, each as the table and the
    ledger print it — the row's own label, without its routine."""
    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    from harness import addrs

    names = {}
    for name, held in aes_event.SWITCHING_ROWS.items():
        names.setdefault(getattr(addrs, held.row.name), set()).add(name.split(", ", 1)[1])
    return names


def _rows_the_ledger_lists_as_switching(status):
    """{ROM address: [(the ratio(s) quoted, the name), …] in the order its verified row lists them after
    THE_ROWS_THAT_SWITCH} — every row that says the words, each name with the prefix its cell states once. REFUSED:
    a second verified row for an address."""
    listed, seen = {}, set()
    for row in _VERIFIED_LINE_RE.finditer(status):
        address = int(row["addr"], 16)
        assert address not in seen, f"{address:#x} has two `✅ verified` rows in STATUS.md: the second would be read over the first"
        seen.add(address)
        line = row[0][:row[0].index(_STATUS_COLUMN)]
        said = _THE_ROWS_THAT_SWITCH_RE.search(line)
        if said:
            prefix = said["prefix"] or ""
            listed[address] = [(case["ratios"], prefix + case["case"]) for case in _A_QUOTED_ROW_RE.finditer(line[said.end():])]
    return listed


def _table_s_ratios_by_name(table):
    """{(ROM address, a row's name): (its ratio, its `own / the caller's own` where the table prints TWO COUNTS under
    it)} out of the generated table's text."""
    priced, last = {}, None
    for line in table.splitlines():
        row, counted = _TABLE_NAMED_ROW_RE.match(line), _TABLE_TWO_COUNTS_RE.match(line)
        if row:
            last = (int(row["addr"], 16), row["case"])
            priced[last] = (row["ratio"], None)
        elif counted and last:
            priced[last] = (priced[last][0], f"{counted['own']}{_TWO_QUOTED}{counted['caller']}")
    return priced


def _counts_stated_of_rows_that_switch(status):
    """{ROM address: the count of rows that SWITCH its Cases cell states} (0: none stated)."""
    stated = {}
    for row in _CASES_CELL_RE.finditer(status):
        said = _SWITCH_IN_A_CASES_CELL_RE.search(row["cases"])
        stated[int(row["addr"], 16)] = int(said["count"] or said["every"]) if said else 0
    return stated


def _wrongly_listed(status, registered, priced):
    """What is wrong with the lists of rows that switch in `status` (a ledger's text), against `registered` (the
    registry's names by address) and `priced` (`_table_s_ratios_by_name`): a line a complaint, by address."""
    listed, counted, wrong = _rows_the_ledger_lists_as_switching(status), _counts_stated_of_rows_that_switch(status), []
    for address in sorted(set(registered) | set(listed)):
        rows = listed.get(address, [])
        names = [name for _ratios, name in rows]
        missing, stale = sorted(registered.get(address, set()) - set(names)), sorted(set(names) - registered.get(address, set()))
        if missing or stale:
            wrong.append(f"{address:#x}: registered and not listed {missing}; listed and not registered {stale}")
        twice = sorted({name for name in names if names.count(name) > 1})
        if twice:
            wrong.append(f"{address:#x}: listed twice {twice}")
        if len(names) != counted.get(address, 0):
            wrong.append(f"{address:#x}: lists {len(names)} row(s) that switch; its Cases cell counts {counted.get(address, 0)}")
        for ratios, name in rows:
            ratio, two_counts = priced.get((address, name), (None, None))
            its_own = two_counts if _TWO_QUOTED in ratios else ratio
            if ratio is not None and ratios != its_own:
                wrong.append(f"{address:#x}: quotes {ratios} for {name!r}; the table prints {its_own} for that row")
            elif ratio is None and name in registered.get(address, ()):
                wrong.append(f"{address:#x}: {name!r} is registered and the table prints no row of that name")
    return wrong


def test_every_routine_s_row_names_the_rows_that_switch_the_registry_holds():
    """WHICH ROWS, NOT ONLY HOW MANY: for every routine the registry holds a switching row of, its verified row
    lists exactly those rows by name after `THE ROWS THAT SWITCH:` — a row renamed, dropped or added in a battery
    and not in the ledger reds by its name; no row lists a switching row the registry does not hold; none is listed
    twice, and the list is as long as the Cases cell's count; and the ratio before each name is THAT ROW'S in the
    table (`_wrongly_listed`)."""
    wrong = _wrongly_listed(_status(), _names_of_the_registered_rows_that_switch(), _table_s_ratios_by_name(BENCH_TABLE.read_text()))
    assert not wrong, (f"{len(wrong)} complaint(s) about the rows that switch STATUS.md lists (`{THE_ROWS_THAT_SWITCH}:` in the "
                       f"Tier 3 cell) against the registry and {BENCH_TABLE.name}:" + "".join(f"\n  {line}" for line in wrong))


_A_MADE_ROW = ("| `0xfe6874` | `ev_block` | 3 rows (2 of them SWITCH) | 1 / 2 | **0.70** a read of a full pipe (`net`); "
               "THE ROWS THAT SWITCH: **0.67** woken by the screen manager's own write (the menu chain) (`net`, 1 foreign "
               "window), **0.64** woken by Return at the first idle (`net`) | ✅ verified | notes: **0.99** not a row (`net`) |")
_THE_MADE_ROW_S_NAMES = ("woken by the screen manager's own write (the menu chain)", "woken by Return at the first idle")
_A_MADE_TABLE = """\
AES ev_block ($fe6874)       $fe6874  a read of a full pipe                                       1030/11682    754/8520    0.70  net
AES ev_block ($fe6874)       $fe6874  woken by the screen manager's own write (the menu chain)    111888/1175772  111340/1169694    0.67  net
                                        TWO COUNTS: 0.67 / 0.31 (14628 against 21128) — own / the caller's own
AES ev_block ($fe6874)       $fe6874  woken by Return at the first idle     2130/31730   1651/26282    0.64  net
"""


def test_the_parser_of_the_names_reads_a_name_with_parentheses_and_stops_at_the_status_column():
    """THE READING, on a made row (RED for the parser itself: a name cut at its own parenthesis, or a note's
    sentence after the status column read as a row, would hold the test above to the wrong sets) — and the made
    table's: each row's name, its ratio, the two counts printed under it."""
    by_name, by_return = _THE_MADE_ROW_S_NAMES
    assert _rows_the_ledger_lists_as_switching(_A_MADE_ROW) == {0xFE6874: [("0.67", by_name), ("0.64", by_return)]}
    # ...and a prefix the cell states once is put back before every name it lists.
    stated_once = _A_MADE_ROW.replace("THE ROWS THAT SWITCH:", "THE ROWS THAT SWITCH (each the table's `blocked; …`):")
    assert _rows_the_ledger_lists_as_switching(stated_once) == {
        0xFE6874: [("0.67", f"blocked; {by_name}"), ("0.64", f"blocked; {by_return}")]}
    assert _table_s_ratios_by_name(_A_MADE_TABLE) == {
        (0xFE6874, "a read of a full pipe"): ("0.70", None), (0xFE6874, by_name): ("0.67", "0.67 / 0.31"),
        (0xFE6874, by_return): ("0.64", None)}


def test_a_wrong_list_of_the_rows_that_switch_is_refused_each_way():
    """THE HOLD'S OWN REDs, on the made row against the made table (each of these ledgers was GREEN while the hold
    compared two sets of names): the made row is right; A ROW LISTED TWICE in place of another is refused (twice,
    and missing); a list longer than the Cases cell's count; A RATIO QUOTED UNDER A NEIGHBOUR'S NAME (each one
    "measured for the address"); two counts that are not that row's; and A SECOND VERIFIED ROW FOR THE ADDRESS."""
    registered, priced = {0xFE6874: set(_THE_MADE_ROW_S_NAMES)}, _table_s_ratios_by_name(_A_MADE_TABLE)
    by_name, by_return = (f"**{ratio}** {name} (`net`" for ratio, name in zip(("0.67", "0.64"), _THE_MADE_ROW_S_NAMES))
    assert by_name in _A_MADE_ROW and by_return in _A_MADE_ROW and _wrongly_listed(_A_MADE_ROW, registered, priced) == []

    def complaints(ledger):
        return " | ".join(_wrongly_listed(ledger, registered, priced))
    twice_for_another = _A_MADE_ROW.replace(by_name, by_return)
    assert "listed twice" in complaints(twice_for_another) and "registered and not listed" in complaints(twice_for_another)
    once_more = _A_MADE_ROW.replace(by_return, f"{by_return}), {by_return}")
    assert "listed twice" in complaints(once_more) and "its Cases cell counts 2" in complaints(once_more)
    swapped = _A_MADE_ROW.replace("**0.67** woken", "**0.64** woken").replace("**0.64** woken by Return", "**0.67** woken by Return")
    assert complaints(swapped).count("the table prints") == 2
    assert _wrongly_listed(_A_MADE_ROW.replace("**0.67** woken", "**0.67 / 0.31** woken"), registered, priced) == []
    assert "the table prints 0.67 / 0.31" in complaints(_A_MADE_ROW.replace("**0.67** woken", "**0.67 / 0.32** woken"))
    assert "the table prints None" in complaints(_A_MADE_ROW.replace("**0.64** woken", "**0.64 / 0.64** woken"))
    with pytest.raises(AssertionError, match="two `✅ verified` rows"):
        _wrongly_listed(_A_MADE_ROW.replace("woken by Return", "A ROW THE REGISTRY DOES NOT HOLD") + "\n" + _A_MADE_ROW, registered, priced)


# ---- ...AND THE OTHER COUNTS THE LEDGER STATES OF THE TABLE TODAY, each typed by hand until it was held here ------------------
# Each is a PRESENT-TENSE statement in a fixed form (the wave logs further down quote history and are not held):
#   * the Components cell: `the rows taken THROUGH INTERRUPTS (N, lo–hi — M of them SLICES of K sessions` — N the
#     registry's (`aes_event.INTERRUPTED_ROWS`: it said 55 over a registry of 56), lo–hi their ratios in the table, M
#     and K the sliced ones and their sessions;
#   * a Cases cell that says `N rows (… M SLICES of K session(s)`: N the table's rows of that address, M and K the
#     registry's (`aes_event.SLICED_ROWS`; a session is one record, interrupted or switching);
#   * the two counts' paragraph, beside the summary held above: `(N on the unrounded cycles)`, `the HIGHER in N`,
#     `N are over 1.00`;
#   * `THE TABLE TODAY: a FOREIGN WINDOW in N of its rows; the save word `$8996` dropped by name in M of the rows
#     that switch` — the table's rows with a window printed under them, the registry's rows whose drops name the word.
_THROUGH_INTERRUPTS_RE = re.compile(r"THROUGH INTERRUPTS \((?P<rows>\d+), (?P<lo>\d\.\d\d)–(?P<hi>\d\.\d\d) — "
                                    r"(?P<slices>\d+) of them SLICES of (?P<sessions>\d+) sessions")
_SLICES_IN_A_CASES_CELL_RE = re.compile(r"^\s*(?P<rows>\d+) rows \(.*?(?P<slices>\d+)(?: of them)? SLICES of (?P<sessions>\d+) session")
_UNROUNDED_RE = re.compile(r"\((?P<apart>\d+) on the unrounded cycles\), the caller's own is the HIGHER in (?P<higher>\d+), "
                           r"and (?P<over>\d+) are over 1\.00")
_THE_TABLE_TODAY_RE = re.compile(r"THE TABLE TODAY: a FOREIGN WINDOW in (?P<windows>\d+) of its rows; the save word `\$8996` "
                                 r"dropped by name in (?P<saved>\d+) of the rows that switch")
_A_WINDOW_UNDER_A_ROW_RE = re.compile(r"^\s+\d+ foreign window\(s\):", re.M)
_OWN_CYCLES_RE = re.compile(r"own (?P<ours>\d+) cycles against the ROM's (?P<the_rom_s>\d+)")


def _sessions_of(names):
    """How many SESSIONS the sliced rows `names` are cut from: a session is ONE record of its registry, whichever."""
    import aes_event

    return len({id(aes_event.INTERRUPTED_ROWS[name] if name in aes_event.INTERRUPTED_ROWS else aes_event.SWITCHING_ROWS[name])
                for name in names})


def _sliced_rows_by_address():
    """{ROM address: the names of the registered rows of the routine there that are SLICES} (`aes_event.SLICED_ROWS`)."""
    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    from harness import addrs

    sliced = {}
    for name in aes_event.SLICED_ROWS:
        held = aes_event.INTERRUPTED_ROWS.get(name) or aes_event.SWITCHING_ROWS[name].row
        sliced.setdefault(getattr(addrs, held.name), []).append(name)
    return sliced


def test_the_rows_taken_through_interrupts_are_counted_as_the_registry_and_the_table_have_them():
    """The Components cell's `THROUGH INTERRUPTS (N, lo–hi — M of them SLICES of K sessions`: the registry's rows
    taken through interrupts at their door calls, the lowest and the highest ratio the table prints for them, and
    how many of them are slices, of how many sessions."""
    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    from harness import addrs

    said = _THROUGH_INTERRUPTS_RE.search(_status())
    assert said, "STATUS.md no longer counts the rows taken through interrupts (`THROUGH INTERRUPTS (N, lo–hi — M of them SLICES of K sessions`)"
    interrupted, priced = aes_event.INTERRUPTED_ROWS, _table_s_ratios_by_name(BENCH_TABLE.read_text())
    ratios = sorted(priced[(getattr(addrs, row.name), name.split(", ", 1)[1])][0] for name, row in interrupted.items())
    sliced = [name for name in aes_event.SLICED_ROWS if name in interrupted]
    assert said.groupdict() == {"rows": str(len(interrupted)), "lo": ratios[0], "hi": ratios[-1], "slices": str(len(sliced)),
                                "sessions": str(_sessions_of(sliced))}, f"STATUS.md says {said[0]!r}"


def test_a_cases_cell_that_counts_slices_counts_them_as_the_registry_does():
    """`N rows (… M SLICES of K session(s)` in a verified row's Cases cell: N the rows the table prints for the
    address, M the registered slices of its routine and K the sessions they are cut from — for every routine the
    registry holds a slice of, both ways."""
    sliced, stated = _sliced_rows_by_address(), {}
    rows_priced = {}
    for address, _name in _table_s_ratios_by_name(BENCH_TABLE.read_text()):
        rows_priced[address] = rows_priced.get(address, 0) + 1
    for row in _CASES_CELL_RE.finditer(_status()):
        said = _SLICES_IN_A_CASES_CELL_RE.match(row["cases"])
        if said:
            stated[int(row["addr"], 16)] = tuple(int(said[group]) for group in ("rows", "slices", "sessions"))
    held = {address: (rows_priced[address], len(names), _sessions_of(names)) for address, names in sliced.items()}
    assert stated == held, (f"STATUS.md's Cases cells count (rows, slices, sessions) as { {hex(at): said for at, said in stated.items()} }; "
                            f"the table and the registry hold { {hex(at): said for at, said in held.items()} }")


def _own_and_caller_s_own_cycles():
    """[((ours, the ROM's) own, (ours, the ROM's) the caller's own)] for every row the table holds on TWO COUNTS: the
    own cycles its `whole run` line states, the caller's own its TWO COUNTS line states."""
    counted, own = [], None
    for line in BENCH_TABLE.read_text().splitlines():
        if _TABLE_NAMED_ROW_RE.match(line):
            own = None
        elif _TABLE_TWO_COUNTS_RE.match(line):
            pair = _TABLE_TWO_COUNTS_RE.match(line)
            assert own, f"a TWO COUNTS line under a row that states no own cycles: {line.strip()[:80]}"
            counted.append((own, (int(pair["ours"]), int(pair["the_rom_s"]))))
        elif own is None and _OWN_CYCLES_RE.search(line):
            stated = _OWN_CYCLES_RE.search(line)
            own = (int(stated["ours"]), int(stated["the_rom_s"]))
    return counted


def test_the_two_counts_paragraph_counts_what_the_table_holds():
    """...AND THE REST OF THE TWO COUNTS' SENTENCE (its first two numbers are held above): how many rows differ by
    more than 0.05 ON THE CYCLES (not on the two decimals printed), in how many the caller's own is the higher, and
    how many are over 1.00 — each the table's."""
    said = _UNROUNDED_RE.search(" ".join(_status().split()))             # the sentence, whatever line it wraps at
    assert said, ("STATUS.md no longer says `(N on the unrounded cycles), the caller's own is the HIGHER in N, and N are "
                  "over 1.00` after its count of the rows that carry both")
    pairs = [pair for pairs in _measured_two_counts().values() for pair in pairs]
    cycles = _own_and_caller_s_own_cycles()
    assert len(cycles) == len(pairs)
    held = {"apart": sum(abs(own[0] / own[1] - caller[0] / caller[1]) > TWO_COUNTS_QUOTED_FROM for own, caller in cycles),
            "higher": sum(float(caller) > float(own) for own, caller, _ours, _the_rom_s in pairs),
            "over": sum(float(caller) > 1.00 for _own, caller, _ours, _the_rom_s in pairs)}
    assert {name: int(count) for name, count in said.groupdict().items()} == held, f"STATUS.md says {said[0]!r}; the table holds {held}"


def test_the_table_today_sentence_counts_the_windows_and_the_save_word_s_drops():
    """`THE TABLE TODAY: a FOREIGN WINDOW in N of its rows; the save word `$8996` dropped by name in M of the rows
    that switch`: the table's rows with a window printed under them, and the registered rows that switch whose
    Tier 3 drops name the mask bracket's save word."""
    import aes
    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)

    said = _THE_TABLE_TODAY_RE.search(" ".join(_status().split()))       # the sentence, whatever line it wraps at
    assert said, "STATUS.md no longer has its `THE TABLE TODAY: a FOREIGN WINDOW in N of its rows; the save word …` sentence"
    windows = len(_A_WINDOW_UNDER_A_ROW_RE.findall(BENCH_TABLE.read_text()))
    saved = sum(any(lo <= aes.AES_SR_SPL < hi for lo, hi, _why in held.drops) for held in aes_event.SWITCHING_ROWS.values())
    assert (int(said["windows"]), int(said["saved"])) == (windows, saved), (
        f"STATUS.md says {said[0]!r}; the table has a window under {windows} rows and {saved} rows that switch drop the word")


# ---- ...AND THE SECTION'S PROSE COUNTS OF ev_multi's ROWS -----------------------------------------------------------------
# The paragraph that opens with EV_MULTI_S_PARAGRAPH counts ev_multi's rows three more times in running prose — `and
# N WOKEN`, `Its N rows are all`, `the N that switch` — and its table row once more (`N WOKEN` in its notes). They
# went stale under green tests once (the counts above held the Cases cell and the three sentences, not these). Held
# here to the registry and to the row's own Cases cell. (The wave logs further down QUOTE HISTORY — "41 WOKEN" of the
# retired hook — and are not held: only this paragraph and ev_multi's own row state the present.)
EV_MULTI_S_PARAGRAPH = "ev_multi's TWIN IS HELD ON BOTH HALVES OF A WAIT:"
_EV_MULTI = "AES_ROM_EV_MULTI"
_WOKEN_RE = re.compile(r"\b(?P<count>\d+) WOKEN\b")
_ITS_ROWS_RE = re.compile(r"\bIts (?P<count>\d+) rows are all\b")
_THE_ONES_THAT_SWITCH_RE = re.compile(r"\bthe (?P<count>\d+) that switch\b")
_ROWS_IN_A_CASES_CELL_RE = re.compile(r"^\s*(?P<count>\d+) rows\b")


def _paragraph_from(status, opening):
    assert opening in status, f"STATUS.md no longer has the paragraph that opens {opening!r}: the prose counts it held are unheld"
    start = status.index(opening)
    return status[start:status.index("\n\n", start)]


def test_the_prose_counts_of_ev_multi_s_rows_are_the_registry_s_and_its_row_s():
    """`and N WOKEN`, `the N that switch` — in the section's paragraph — and every `N WOKEN` of ev_multi's own table
    row are the number of ev_multi's registered rows that switch; `Its N rows are all` is the row count its Cases
    cell states (which the ledger's own tests hold to the table)."""
    from harness import addrs

    status, address = _status(), getattr(addrs, _EV_MULTI)
    switching = _registered_rows_that_switch()[address]
    paragraph = _paragraph_from(status, EV_MULTI_S_PARAGRAPH)
    its_row = next(row for row in _VERIFIED_LINE_RE.finditer(status) if int(row["addr"], 16) == address)[0]
    cases = next(row["cases"] for row in _CASES_CELL_RE.finditer(status) if int(row["addr"], 16) == address)
    said = {"WOKEN, in the paragraph": [int(found["count"]) for found in _WOKEN_RE.finditer(paragraph)],
            "that switch, in the paragraph": [int(found["count"]) for found in _THE_ONES_THAT_SWITCH_RE.finditer(paragraph)],
            "WOKEN, in ev_multi's row": [int(found["count"]) for found in _WOKEN_RE.finditer(its_row)]}
    assert all(said.values()), f"STATUS.md no longer counts ev_multi's woken rows where it did: {said}"
    assert all(set(counts) == {switching} for counts in said.values()), (
        f"STATUS.md's prose counts ev_multi's rows that switch as {said}; the registry holds {switching}")
    its_rows = [int(found["count"]) for found in _ITS_ROWS_RE.finditer(paragraph)]
    assert its_rows == [int(_ROWS_IN_A_CASES_CELL_RE.match(cases)["count"])], (
        f"the paragraph says `Its {its_rows} rows`; ev_multi's Cases cell opens {cases.strip()[:40]!r}")
