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
from collections import namedtuple
from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[1]

# `## Verified — <component> (N)`, and the `| `0xADDR` | ... | ✅ verified |` rows beneath it.
_SECTION_RE = re.compile(r"^## Verified — (?P<name>\S+) \((?P<count>\d+)\)\s*$", re.M)
# ...a verified row of either kind: ✅ verified, and band 6 W3a's ✅ verified on target (R3) — the target-only kind (no host
# twin, no Tier 1: its rows the kind's own, `aes_desk_w3a`)
_ROW_RE = re.compile(r"^\| `0x[0-9a-f]+` \|.*\| ✅ verified(?: on target \(R3\))? \|", re.M)
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
# THE SECOND HEADING KIND (band 6 wave 1a's fix pass): `## Linked, unbound — <component> (N)` — C written, linked into
# both blobs and held at Tier 1, NOTHING bound or registered — and its rows, marked so and never `✅ verified`.
_LINKED_UNBOUND_RE = re.compile(r"^## Linked, unbound — (?P<name>\S+) \((?P<count>\d+)\)\s*$", re.M)
LINKED_UNBOUND = "🔗 linked, unbound"
_LINKED_UNBOUND_ROW_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|.*\| " + LINKED_UNBOUND + r" \|", re.M)
_ANY_HEADING_RE = re.compile(r"^## ", re.M)


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


def _linked_unbound_sections():
    """[(component, stated count, the rows' addresses, the body)] of the second heading kind, each to the next heading."""
    text, out = _status(), []
    for head in _LINKED_UNBOUND_RE.finditer(text):
        following = _ANY_HEADING_RE.search(text, head.end())
        body = text[head.end():following.start() if following else len(text)]
        out.append((head["name"], int(head["count"]), [int(row["addr"], 16) for row in _LINKED_UNBOUND_ROW_RE.finditer(body)], body))
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
    linked_unbound = {name for name, _count, _rows, _body in _linked_unbound_sections()}
    for directory in sorted(path for path in (REC / "src").iterdir() if path.is_dir()):
        cores = sorted(directory.glob("*.c"))
        if not cores or directory.name in linked_unbound and directory.name not in stated:
            continue                    # (a component linked and unbound: held by the test below, to the generator's list)
        assert directory.name in stated, (
            f"src/{directory.name}/ holds {len(cores)} reconstructed core(s) and STATUS.md has no "
            f"`## Verified — {directory.name} (N)` section — the ledger is missing a component, "
            f"which no count in it can show")
        assert stated[directory.name] >= len(cores), (
            f"STATUS.md's `## Verified — {directory.name} ({stated[directory.name]})` section "
            f"carries fewer rows than src/{directory.name}/ has .c files ({len(cores)}: "
            f"{', '.join(path.name for path in cores)}) — at least one reconstructed function has "
            f"no row")


def test_a_component_linked_and_unbound_is_held_to_the_line_f_table_s_exception_list():
    """THE SECOND HEADING KIND (band 6 wave 1a's fix pass; both reviews' remedy for the red `src/desk/` made):
    `## Linked, unbound — <component> (N)` — a component whose C is written, LINKED INTO BOTH BLOBS and held at Tier 1
    while nothing of it is bound or registered (ruling W6-R1 waits for the user). A `## Verified` section would not be
    honest — its rows would be `✅ verified` with no row of the table to quote. Its rows are marked otherwise, NONE
    `✅ verified`; N is its row count AND the number of routines HELD UNBOUND — `linef_table.LINKED_AND_NOT_FLIPPED`
    and (band 6 wave 2's R-W2-4) `LINKED_HELD_NO_TABLE_ENTRY`, the union `aes_deskbind.held_cores` reads —, and the
    rows' addresses are EXACTLY those routines: the exemption is the generator's own lists, and it expires at the flip by
    itself — a routine flipped leaves the list, and this reds until its row moves to a Verified section."""
    import sys
    sys.path.insert(0, str(REC / "bench"))
    import linef_table
    from harness import addrs

    sections = _linked_unbound_sections()
    assert [name for name, _count, _rows, _body in sections] == ["desk"], "one component is linked and unbound: the desk's two units"
    (name, count, rows, body), = sections
    held_unbound = {**linef_table.LINKED_AND_NOT_FLIPPED, **linef_table.LINKED_HELD_NO_TABLE_ENTRY}
    held = {getattr(addrs, routine) for routine in held_unbound}
    assert count == len(rows) == len(held_unbound), (
        f"`## Linked, unbound — {name} ({count})` carries {len(rows)} rows; the generator's lists hold {len(held_unbound)}")
    assert sorted(rows) == sorted(held), f"rows that are not the list's: {sorted(map(hex, set(rows) ^ held))}"
    assert not _ROW_RE.search(body), f"a row of `## Linked, unbound — {name}` says `✅ verified`"
    assert (REC / "src" / name).is_dir()


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


_FLIPPED_RE = re.compile(r"(\d+) of band 6's (\d+) FLIPPED")


def test_the_desk_s_flipped_count_is_the_blob_s():
    """THE DESK ROW'S "N of band 6's M FLIPPED" (band 6 W3b's prep: it read F4's 223 three slices after) is DERIVED:
    N the routines the shipped blob binds as ours (`aes_desk.flipped`), M band 6's routines (`aes_desk.routines`)."""
    import aes_desk
    desk_row, = [line for line in _status().splitlines() if line.startswith("| desk |")]
    (flipped, of), = _FLIPPED_RE.findall(desk_row)
    assert (int(flipped), int(of)) == (len(aes_desk.flipped()), len(aes_desk.routines())), (
        f"STATUS.md's desk row says {flipped} of {of} flipped; the blob binds {len(aes_desk.flipped())} of "
        f"{len(aes_desk.routines())}")


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
# A row that switches is registered (`aes_event.every_switching_row`), and the ledger states how many there are THREE ways,
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
    """{ROM address: how many registered rows that switch are of the routine there} (`aes_event.every_switching_row`)."""
    import collections

    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    from harness import addrs

    return collections.Counter(getattr(addrs, held.row.name) for held in aes_event.every_switching_row().values())


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
                       f"(`aes_event.every_switching_row`):" + "".join(f"\n  {line}" for line in wrong))


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
    for name, held in aes_event.every_switching_row().items():
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
#     that switch; A TURN OF OUR SCREEN MANAGER priced under K of its rows` — the table's rows with a window of the
#     ROM's process printed under them, the registry's rows whose drops name the word, and (FLIP 4) the table's rows
#     with a turn of our ctlmgr priced on a line of its own under them.
_THROUGH_INTERRUPTS_RE = re.compile(r"THROUGH INTERRUPTS \((?P<rows>\d+), (?P<lo>\d\.\d\d)–(?P<hi>\d\.\d\d) — "
                                    r"(?P<slices>\d+) of them SLICES of (?P<sessions>\d+) sessions")
_SLICES_IN_A_CASES_CELL_RE = re.compile(r"^\s*(?P<rows>\d+) rows \(.*?(?P<slices>\d+)(?: of them)? SLICES of (?P<sessions>\d+) session")
_UNROUNDED_RE = re.compile(r"\((?P<apart>\d+) on the unrounded cycles\), the caller's own is the HIGHER in (?P<higher>\d+), "
                           r"and (?P<over>\d+) are over 1\.00")
_THE_TABLE_TODAY_RE = re.compile(r"THE TABLE TODAY: a FOREIGN WINDOW in (?P<windows>\d+) of its rows; the save word `\$8996` "
                                 r"dropped by name in (?P<saved>\d+) of the rows that switch; A TURN OF OUR SCREEN MANAGER "
                                 r"priced under (?P<turns>\d+) of its rows")
_A_WINDOW_UNDER_A_ROW_RE = re.compile(r"^\s+\d+ foreign window\(s\):", re.M)
_A_TURN_UNDER_A_ROW_RE = re.compile(r"^\s+screen manager's turn: ours \d+ / ROM \d+ = \d\.\d\d", re.M)
_OWN_CYCLES_RE = re.compile(r"own (?P<ours>\d+) cycles against the ROM's (?P<the_rom_s>\d+)")


def _sessions_of(names):
    """How many SESSIONS the sliced rows `names` are cut from: a session is ONE record of its registry, whichever."""
    import aes_event

    switching_rows = aes_event.every_switching_row()
    return len({id(aes_event.INTERRUPTED_ROWS[name] if name in aes_event.INTERRUPTED_ROWS else switching_rows[name])
                for name in names})


def _sliced_rows_by_address():
    """{ROM address: the names of the registered rows of the routine there that are SLICES} (`aes_event.SLICED_ROWS`)."""
    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)
    from harness import addrs

    sliced, switching_rows = {}, aes_event.every_switching_row()
    for name in aes_event.SLICED_ROWS:
        held = aes_event.INTERRUPTED_ROWS.get(name) or switching_rows[name].row
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


_ACCESSORY_TURNS_TODAY_RE = re.compile(r"A TURN OF OURS, on a line of its own: (?P<turns>\w+) of them under (?P<rows>\w+) rows")
_A_TURN_OF_AN_ACCESSORY_RE = re.compile(r"^\s+an accessory's turn: ours \d+ / ROM \d+ = ")


def test_the_table_today_sentence_counts_the_windows_and_the_save_word_s_drops():
    """`THE TABLE TODAY: a FOREIGN WINDOW in N of its rows; the save word `$8996` dropped by name in M of the rows
    that switch; A TURN OF OUR SCREEN MANAGER priced under K of its rows`: the table's rows with a window of the
    ROM's process printed under them, the registered rows that switch whose Tier 3 drops name the mask bracket's save
    word, and the table's rows with a turn of our ctlmgr priced under them (one line a turn, one turn a row today)."""
    import aes
    import aes_event
    import test_boot_snapshot  # noqa: F401  (every battery registered)

    said = _THE_TABLE_TODAY_RE.search(" ".join(_status().split()))       # the sentence, whatever line it wraps at
    assert said, ("STATUS.md no longer has its `THE TABLE TODAY: a FOREIGN WINDOW in N of its rows; the save word …; A TURN OF "
                  "OUR SCREEN MANAGER priced under K of its rows` sentence")
    table = BENCH_TABLE.read_text()
    windows, turns = len(_A_WINDOW_UNDER_A_ROW_RE.findall(table)), len(_A_TURN_UNDER_A_ROW_RE.findall(table))
    saved = sum(any(lo <= aes.AES_SR_SPL < hi for lo, hi, _why in held.drops) for held in aes_event.every_switching_row().values())
    assert (int(said["windows"]), int(said["saved"]), int(said["turns"])) == (windows, saved, turns), (
        f"STATUS.md says {said[0]!r}; the table has a window under {windows} rows, {saved} rows that switch drop the word "
        f"and a turn of our screen manager is priced under {turns} rows")
    # ...AND, SINCE THE NARROW DOOR FLIP, THE ACCESSORIES' TURNS the same paragraph counts: the table's lines, and the
    # rows they stand under (a row may hold two).
    of_accessories = _ACCESSORY_TURNS_TODAY_RE.search(" ".join(_status().split()))
    assert of_accessories, "STATUS.md no longer counts the accessories' turns in its `THE TABLE TODAY` paragraph"
    lines, under, row = 0, set(), None
    for line in table.splitlines():
        if _A_TURN_OF_AN_ACCESSORY_RE.match(line):
            lines, under = lines + 1, under | {row}
        elif _TABLE_ROW_RE.match(line) and not line.startswith(" "):
            row = line
    assert (_number(of_accessories["turns"]), _number(of_accessories["rows"])) == (lines, len(under)), (
        f"STATUS.md says {of_accessories[0]!r}; the table prices {lines} turn(s) of an accessory under {len(under)} row(s)")


# ---- ...AND THE SECTION'S PROSE COUNTS OF ev_multi's ROWS -----------------------------------------------------------------
# The paragraph that opens with EV_MULTI_S_PARAGRAPH counts ev_multi's rows three more times in running prose — `and
# N WOKEN`, `Its N rows are all`, `the N that switch` — and its table row once more (`N WOKEN` in its notes). They
# went stale under green tests once (the counts above held the Cases cell and the three sentences, not these). Held
# here to the registry and to the row's own Cases cell. (The wave logs, further down and in `STATUS_ARCHIVE.md`, QUOTE HISTORY — "41 WOKEN" of the
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


# ---- band 5 wave 3: THE GATE'S SENTENCE (ruling W3-R8) AND THE WAVE'S OWN COUNTS ------------------------------------------------
# The wave-3 entry opened with a verdict in numbers — the trap path against PD2's stack: "DOES NOT FIT" — and
# `* **Next**` ordered the work by it. THE DOOR DIET's entry states the verdict that replaced it ("FITS"), in the
# same numbers: `test_aes_stack.py`'s pins (which that battery holds to the reading and to the runs), QUOTED here,
# so a frame that moves a pin reddens the sentence that still says the old margin. Beside it, two counts the wave's
# first entry would otherwise keep by hand: the registry's pending declarations and the table's length.
THE_WAVE_S_ENTRY = "BAND 5 WAVE 3 — THE TRAP DOOR AND THE LOADER"
# (...the wave's first entry is history since THE NARROW DOOR FLIP, whose own entry states the two counts as they are)
THE_FLIP_S_ENTRY = "WAVE 3 — SLICE F: THE NARROW DOOR FLIP"
THE_GATE_S_ENTRY = "WAVE 3 — THE DOOR DIET"
_COUNT_WORDS = {"no": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
                "ten": 10, "eleven": 11, "twelve": 12}
_THE_GATE_RE = re.compile(
    r"THE TRAP PATH FITS PD2's (?P<pd2>[\d,]+) BYTES ON THE\s+SHIPPED BLOB\*\*.*?the (?P<nest>\d+)-byte nest.*?"
    r"MEASURED (?P<measured>\d+) spare.*?BOUND (?P<bound>\d+) spare \(fsel_input: [\d,]+ \+ \d+ = (?P<needed>[\d,]+)\);\s+"
    r"all (?P<every>\d+) arms of the opcode switch fit PD2 \((?P<arms>\w+) did not\), and an allocated PD's (?P<allocated>[\d,]+)", re.S)
ARMS_OVER_PD2_BEFORE_THE_DOOR_DIET = 8      # the wave's first entry's count, history: quoted beside the new verdict
_PENDING_RE = re.compile(r"(?P<count>\w+) registry declarations? (?:are|is) PENDING")
_TABLE_LINES_RE = re.compile(r"THE TABLE against `[0-9a-f]+`'s \([\d,]+ lines → (?P<lines>[\d,]+)\)")
_WAS_PENDING_RE = re.compile(r"(?P<count>\w+) registry declarations are PENDING")
PENDING_BEFORE_THE_FLIP = 4             # the wave's first entry's count, history
PENDING_WHEN_THE_OUR_BOOT_BEGAN = 3     # ...the flip's entry's, as wave 4's slice M left it (its three declarations): history
TABLE_LINES_AT_THE_FLIP = 5678          # ...and the table's length then
THE_OUR_BOOT_S_ENTRY = "WAVE 4 — SLICE B: THE OUR BOOT"     # band 5 wave 4: where the two counts are stated as they are


def _number(text):
    return _COUNT_WORDS[text] if text in _COUNT_WORDS else int(text.replace(",", ""))


def test_the_gate_s_sentence_quotes_the_stack_battery_s_pins_and_the_wave_s_counts_are_derived():
    import aes_event
    import aes_stack
    import test_aes_stack as pinned

    said = _THE_GATE_RE.search(_paragraph_from(_status(), THE_GATE_S_ENTRY))
    assert said, "the door diet's entry no longer states the gate's verdict in the sentence this test reads"
    worst_arm, needed = pinned.THE_SHIPPED_BLOB_S_DEEPEST_CALLS[0]
    assert {name: _number(value) for name, value in said.groupdict().items()} == {
        "pd2": pinned.PD2_S_SPAN, "nest": pinned.THE_NEST, "measured": pinned.MEASURED_SPARE_OF_PD2,
        "bound": pinned.TRAP_PATH_SPARE[pinned.SHIPPED][aes_stack.PD2], "needed": needed,
        "arms": ARMS_OVER_PD2_BEFORE_THE_DOOR_DIET, "every": len(aes_stack.calls_of_the_switch(
            aes_stack.blob_of(pinned.SHIPPED).elf, pinned.SHIPPED)), "allocated": pinned.AN_ALLOCATED_SPAN}
    assert pinned.PD2_S_SPAN - needed == _number(said["bound"]) and worst_arm == 90, "the worst arm is fsel_input (opcode 90)"
    assert pinned.CALLS_OVER_PD2[pinned.SHIPPED] == (), "the sentence says every arm fits: the pin of the arms over PD2 is empty"
    was = _WAS_PENDING_RE.search(_paragraph_from(_status(), THE_WAVE_S_ENTRY))
    assert was and _number(was["count"]) == PENDING_BEFORE_THE_FLIP, "the wave's first entry: its history"
    # THE FLIP'S ENTRY IS HISTORY TOO since band 5 wave 4's slice B (the our boot): its two counts are what they were...
    flip = _paragraph_from(_status(), THE_FLIP_S_ENTRY)
    pending, lines = _PENDING_RE.search(flip), _TABLE_LINES_RE.search(flip)
    assert pending and _number(pending["count"].lower()) == PENDING_WHEN_THE_OUR_BOOT_BEGAN, "the flip's entry: its history"
    assert lines and _number(lines["lines"]) == TABLE_LINES_AT_THE_FLIP, "the flip's entry: its history"
    # ...AND THE OUR BOOT'S ENTRY STATES THEM AS THEY ARE: the registry's pending declarations, the table's length.
    entry = _paragraph_from(_status(), THE_OUR_BOOT_S_ENTRY)
    pending, lines = _PENDING_RE.search(entry), _TABLE_LINES_RE.search(entry)
    assert pending and _number(pending["count"].lower()) == len(aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3), (
        f"the our boot's entry counts the registry's pending declarations; it holds {sorted(aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3)}")
    assert lines and _number(lines["lines"]) == len(BENCH_TABLE.read_text().splitlines()), "the table's length, as the our boot's entry states it"


# ...AND THE DOOR DIET'S OTHER NUMBERS, which the sentence above does not hold (its review, B-F4: the per-arm table
# altered, "36 spare → 116" and "crit_err … 840" each passed every test). RE-DERIVED BY THE STACK BATTERY'S OWN
# READERS on the shipped blob — `calls_of_the_switch` (the same reading the sentence's count of arms asks), `need`
# and `crit_err_need` — never by quoting a pin. The table's "at `05bc5d6`" column is history no tree re-derives:
# held only to its own arithmetic (an "over by" is that figure less PD2's span).
_AN_ARM_S_ROW_RE = re.compile(r"^\s*\| (?P<arm>\d+ \w+|the default arm \((?P<opcodes>\d+) opcodes[^|]*) \| (?P<before>[\d,]+)"
                             r"(?: \(over by (?P<over>\d+)\))? \| (?P<now>[\d,]+) \| (?P<spare>\d+) \|$", re.M)
_THE_SCREEN_MANAGER_S_FIT_RE = re.compile(r"THE SCREEN MANAGER'S OWN FIT DID NOT GET WORSE: (?P<before>\d+) spare → \*\*(?P<now>\d+)\*\*")
_CRIT_ERR_S_FIT_RE = re.compile(r"crit_err's private stack: \d+ → (?P<now>\d+) spare of its (?P<span>[\d,]+)")
THE_ARMS_THE_TABLE_SHOWS = 12           # the deepest, as `aes_stack.report()` prints them (`CALLS_SHOWN`)


def test_the_door_diet_s_table_and_its_two_other_fits_are_the_stack_reading_s():
    import aes_stack
    import test_aes_stack as pinned

    entry, shipped = _paragraph_from(_status(), THE_GATE_S_ENTRY), aes_stack.blob_of(pinned.SHIPPED)
    rows = list(_AN_ARM_S_ROW_RE.finditer(entry))
    assert len(rows) == THE_ARMS_THE_TABLE_SHOWS == aes_stack.CALLS_SHOWN, "the door diet's per-arm table: one arm a row"
    for row, call in zip(rows, aes_stack.calls_of_the_switch(shipped.elf, pinned.SHIPPED)):
        needed = max(call.own, call.at_a_trap) + aes_stack.nest(pinned.SHIPPED)
        its_opcodes = len(call.opcodes) if row["opcodes"] else tuple(call.opcodes)
        assert its_opcodes == (_number(row["opcodes"]) if row["opcodes"] else (int(row["arm"].split()[0]),)), (
            f"{row['arm']}: the reading's next arm is {call.opcodes}")
        assert (_number(row["now"]), _number(row["spare"])) == (needed, pinned.PD2_S_SPAN - needed), f"{row['arm']}: {row[0].strip()}"
        assert row["over"] is None or _number(row["before"]) - pinned.PD2_S_SPAN == _number(row["over"]), row[0].strip()
    manager = _THE_SCREEN_MANAGER_S_FIT_RE.search(entry)
    assert manager and _number(manager["before"]) == pinned.SPARE_BEFORE_THE_DOOR_DIET
    assert _number(manager["now"]) == pinned.SPAN - aes_stack.need(shipped)[0], "the screen manager's spare, by the reading"
    crit_err = _CRIT_ERR_S_FIT_RE.search(entry)
    lo, top = aes_stack.CRIT_ERR_STACK
    assert crit_err and _number(crit_err["span"]) == top - lo
    assert _number(crit_err["now"]) == top - lo - aes_stack.crit_err_need(shipped)[0], "crit_err's spare, by the reading"


# ...AND THE COUNTS OF TWO BATTERIES THE WAVE'S ENTRIES QUOTE (wave 3's review: "17 arrivals" stood where the battery
# has 15, "258 cases" where it collects 259) — each re-derived: the tests a file COLLECTS, asked of pytest itself in
# a process of its own, and the loader's arrivals read off its own table of cases.
_LOADER_S_COUNTS_RE = re.compile(r"(?P<arrivals>\d+) ARRIVALS \((?P<tests>\d+) tests\) — (?P<made>\d+) a boot makes, (?P<staged>\d+) with one word staged")
_CRIT_ERR_S_CASES_RE = re.compile(r"^\| `0xfe3cbe` \|[^|]*\| (?P<cases>\d+) cases \(`test_aes_crit_err\.py`\)", re.M)
_COLLECTED_RE = re.compile(r"^(?P<tests>\d+) tests? collected", re.M)
A_STAGED_ARRIVAL = "ARGUMENT CLASS"     # how `test_aes_loader.CASES` labels an arrival with a word staged over it


def _collected(battery):
    """How many tests pytest collects from `test/<battery>`: its own count, from a process of its own."""
    import subprocess
    import sys
    said = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                           "-p", "no:randomly", str(REC / "test" / battery)], cwd=REC, capture_output=True, text=True).stdout
    found = _COLLECTED_RE.search(said)
    assert found, f"pytest collected nothing it counts from {battery}: {said[-300:]}"
    return int(found["tests"])


def test_the_two_battery_counts_the_wave_3_entries_quote_are_the_batteries_own():
    import test_aes_loader

    status = _status()
    loader, crit_err = _LOADER_S_COUNTS_RE.search(status), _CRIT_ERR_S_CASES_RE.search(status)
    assert loader and crit_err, "STATUS.md no longer counts the loader's arrivals or crit_err's cases where it did"
    staged = [label for label in test_aes_loader.CASES if label.startswith(A_STAGED_ARRIVAL)]
    assert {name: int(value) for name, value in loader.groupdict().items()} == {
        "arrivals": len(test_aes_loader.CASES), "tests": _collected("test_aes_loader.py"),
        "made": len(test_aes_loader.CASES) - len(staged), "staged": len(staged)}
    assert int(crit_err["cases"]) == _collected("test_aes_crit_err.py")


# ---- THE NARROW DOOR FLIP'S FIX PASS: the turns' figures its entry quotes ARE THE TABLE'S (B-F2, B-F3) ---------------------
# The entry quotes, for the eight accessory turns, each turn's ratio with its thunks and THE FIGURE NET OF THE ROM'S
# LINE-F HANDLER (`tier3._line_f_of`: printed beside a turn, read by no rule) on both blobs, and compares that one
# figure with the screen manager's own lines. Each is re-derived here from the table's integers: the shipped blob's
# from its own lines; the bench blob's from the pinned turns (`aes_accessory_turns_pinned`) over the SAME ROM windows
# and Line-F shares (the ROM's run of a row is one run, whichever blob stands beside it).
_A_TURN_S_LINE_RE = re.compile(r"^\s+(?P<whose>an accessory's turn|screen manager's turn): ours (?P<ours>\d+) / ROM (?P<the_rom_s>\d+) = ")
_ITS_THUNKS_RE = re.compile(r", and (?P<glue>\d+) in thunks: ")
_ITS_LINE_F_RE = re.compile(r"the ROM's Line-F handler alone is (?P<line_f>\d+) of its (?P<the_rom_s>\d+) \(\d+%\): net of it (?P<net>\d\.\d\d)")
_THE_EIGHT_TURNS_RE = re.compile(
    r"THE EIGHT ACCESSORY TURNS IN THE TABLE'S ORDER, with thunks / net of the ROM's Line-F handler — shipped \(the table's own "
    r"lines\): (?P<shipped>[\d. /,]+); bench \(the pinned turns over the table's ROM windows and Line-F shares\): (?P<bench>[\d. /,]+)\.")
_ON_THAT_ONE_FIGURE_RE = re.compile(
    r"ON THAT ONE FIGURE: the screen manager's (?P<managers>\d+) lines that print it are (?P<manager_lo>\d\.\d\d) \.\. "
    r"(?P<manager_hi>\d\.\d\d), (?P<manager_over>\d+) over 1\.10 \((?P<earlier>\d+) of them under the earlier slices' rows, "
    r"(?P<earlier_lo>\d\.\d\d) \.\. (?P<earlier_hi>\d\.\d\d), (?P<earlier_over>\d+) over 1\.10; (?P<slice_b>\d+) under slice B's — the first "
    r"turn inside gem_main's three stretches — (?P<slice_b_lo>\d\.\d\d) \.\. (?P<slice_b_hi>\d\.\d\d), (?P<slice_b_over>\d+) over 1\.10\); "
    r"the accessories' (?P<accessories>\d+) are (?P<shipped_lo>\d\.\d\d) \.\. "
    r"(?P<shipped_hi>\d\.\d\d), (?P<shipped_over>\d+) over 1\.10 on the shipped blob and (?P<bench_lo>\d\.\d\d) \.\. "
    r"(?P<bench_hi>\d\.\d\d), (?P<bench_over>\d+) over 1\.10 on the bench blob")
THE_BAR_A_TURN_IS_HELD_TO = 1.10
A_STRETCH_S_CASE_BEGINS = "LABELLED STAGING (our boot)"     # `aes_ourboot.ON_THE_OUR_BOOT_MACHINE`: held equal below
AN_ACCESSORY_S, THE_BENCH_BLOB = "an accessory's turn", "bench"
TurnLine = namedtuple("TurnLine", "whose row nth ours the_rom_s glue line_f")


def _turn_lines_of_the_table():
    """Every turn's line of the table as a `TurnLine`: whose it is, the row's own line it stands under and which
    turn of that row it is, and its integers — `line_f` None where the line prints no Line-F share (a slice's). THE
    NET FIGURE EACH LINE PRINTS IS HELD HERE to those integers, to the two decimals."""
    turns, row, nth = [], None, 0
    for line in BENCH_TABLE.read_text().splitlines():
        if line and not line.startswith(" "):
            row, nth = line, 0
            continue
        a_turn = _A_TURN_S_LINE_RE.match(line)
        if not a_turn:
            continue
        thunks, share = _ITS_THUNKS_RE.search(line), _ITS_LINE_F_RE.search(line)
        turn = TurnLine(a_turn["whose"], row, nth, int(a_turn["ours"]), int(a_turn["the_rom_s"]), int(thunks["glue"]) if thunks else 0,
                        int(share["line_f"]) if share else None)
        if share:
            assert int(share["the_rom_s"]) == turn.the_rom_s and share["net"] == f"{_net_of_the_handler(turn):.2f}", (
                f"the table prints a net figure its own line's integers do not make: {line.strip()[:200]}")
        turns.append(turn)
        nth += 1
    return turns


def _with_thunks(turn):
    return (turn.ours + turn.glue) / turn.the_rom_s


def _net_of_the_handler(turn):
    return (turn.ours + turn.glue) / (turn.the_rom_s - turn.line_f)


def _on_the_bench_blob(turn):
    """The accessory `turn` of the table as the BENCH blob runs it: our member and our thunks the pinned ones of its
    row (found by the row's case, which the row's own line spells), the ROM's window and Line-F share the table's."""
    import aes_accessory_turns_pinned

    (pinned,) = [by_blob[THE_BENCH_BLOB] for name, by_blob in aes_accessory_turns_pinned.PINNED.items()
                 if name.split(", ", 1)[1] in turn.row]
    ours, the_rom_s, glue = pinned[turn.nth]
    assert the_rom_s == turn.the_rom_s, f"the pinned bench turn's ROM member {the_rom_s} is not the table's {turn.the_rom_s}"
    return turn._replace(ours=ours, glue=glue)


def _quoted(turns):
    return ", ".join(f"{_with_thunks(turn):.2f} / {_net_of_the_handler(turn):.2f}" for turn in turns)


def _spread(turns):
    net = [_net_of_the_handler(turn) for turn in turns]
    return f"{min(net):.2f}", f"{max(net):.2f}", str(sum(figure > THE_BAR_A_TURN_IS_HELD_TO for figure in net))


def test_the_fix_pass_s_figures_of_the_turns_net_of_the_line_f_handler_are_the_table_s():
    """THE EIGHT TURNS' TWO FIGURES ON EACH BLOB, and THE ONE-FIGURE COMPARISON with the screen manager's lines (how
    many print the figure, its lowest and highest, how many are over 1.10 ON THE CYCLES): each the table's."""
    status = " ".join(_status().split())
    eight, compared = _THE_EIGHT_TURNS_RE.search(status), _ON_THAT_ONE_FIGURE_RE.search(status)
    assert eight and compared, "STATUS.md no longer quotes the eight accessory turns' figures, or no longer compares them on one figure"
    turns = _turn_lines_of_the_table()
    of_accessories = [turn for turn in turns if turn.whose == AN_ACCESSORY_S]
    of_the_manager = [turn for turn in turns if turn.whose != AN_ACCESSORY_S and turn.line_f is not None]
    assert all(turn.line_f is not None for turn in of_accessories)
    on_the_bench = [_on_the_bench_blob(turn) for turn in of_accessories]
    assert (eight["shipped"], eight["bench"]) == (_quoted(of_accessories), _quoted(on_the_bench)), (
        f"STATUS.md quotes {eight['shipped']!r} and {eight['bench']!r}; the table and the pins make "
        f"{_quoted(of_accessories)!r} and {_quoted(on_the_bench)!r}")
    held = dict(zip(("managers", "manager_lo", "manager_hi", "manager_over"), (str(len(of_the_manager)), *_spread(of_the_manager))))
    # ...WHOSE LINES ARE WHICH SLICE'S (never folded into one statistic unsaid): the ones under a stretch of the our boot.
    under_slice_b = [turn for turn in of_the_manager if A_STRETCH_S_CASE_BEGINS in turn.row]
    under_earlier = [turn for turn in of_the_manager if turn not in under_slice_b]
    held |= dict(zip(("earlier", "earlier_lo", "earlier_hi", "earlier_over"), (str(len(under_earlier)), *_spread(under_earlier))))
    held |= dict(zip(("slice_b", "slice_b_lo", "slice_b_hi", "slice_b_over"), (str(len(under_slice_b)), *_spread(under_slice_b))))
    held |= dict(zip(("accessories", "shipped_lo", "shipped_hi", "shipped_over"), (str(len(of_accessories)), *_spread(of_accessories))))
    held |= dict(zip(("bench_lo", "bench_hi", "bench_over"), _spread(on_the_bench)))
    assert compared.groupdict() == held, f"STATUS.md says {compared[0]!r}; the table holds {held}"


# ---- BAND 5 WAVE 4, SLICE B: THE OUR BOOT — its entry's figures and the census of the six routines, derived ----------------------
# The entry's headline states how far ours boots, how many rows and routines that made, and the two stack gates as the
# our-boot machine measures them. Each is a pin or a registry of `test_aes_ourboot.py` / `aes_ourboot.py`, QUOTED here.
_THE_OUR_BOOT_RE = re.compile(
    r"OURS BOOTS TO deskmain's ENTRY AND NO FURTHER — (?P<rows>\d+) rows,\s+(?P<verified>\w+)\s+routines\s+verified\s+and\s+"
    r"(?P<unpriced>\w+)\s+unpriced.*?first stack (?P<bound>\d+) / (?P<span>\d+), bound and measured.*?"     # (the entry wraps)
    r"the shell entered at `\$(?P<shell>[0-9a-f]+)`.*?margins\s+(?P<deskmain>\d+) / (?P<dos_exec>\d+) / (?P<built_in>\d+)", re.S)
_AN_UNPRICED_LINE_RE = re.compile(r"^\| `0x(?P<addr>[0-9a-f]+)` \|.*⚠️ verified, unpriced.*$", re.M)


def test_the_our_boot_s_entry_quotes_the_battery_s_pins_and_the_registry_s_rows():
    import aes_ourboot
    import test_aes_ourboot as battery
    from harness import addrs, bench_tier3

    said = _THE_OUR_BOOT_RE.search(_paragraph_from(_status(), THE_OUR_BOOT_S_ENTRY))
    assert said, "the our-boot's entry no longer states its headline in the sentence this test reads"
    tier3 = bench_tier3()
    routines = {getattr(addrs, name): how for name, (how, _what) in aes_ourboot.THE_CENSUS.items()}
    rows = [row for row in tier3.ROWS if tier3.rom_address(row) in routines]
    priced = [how for how in routines.values() if how == aes_ourboot.IN_THE_TABLE]
    margins = battery.THE_MARGINS
    assert {name: _number(value.lower()) if name != "shell" else int(value, 16) for name, value in said.groupdict().items()} == {
        "rows": len(rows), "verified": len(priced), "unpriced": len(routines) - len(priced),
        "bound": battery.pinned.THE_FIRST_STACK_BOUND, "span": battery.pinned.THE_FIRST_STACK_S_SPAN,
        "shell": battery.THE_SHELL_IS_ENTERED_AT, "deskmain": margins[aes_ourboot.DESKMAIN_ENTERED],
        "dos_exec": margins[aes_ourboot.DOS_EXEC_ENTERED], "built_in": margins[aes_ourboot.SHOW_FILE]}


def test_the_ledger_holds_each_of_the_six_routines_as_the_census_says():
    """THE CENSUS OF WAVE 4's SIX (`aes_ourboot.THE_CENSUS`), against the ledger's own rows: a routine with rows of the
    table has a `✅ verified` row (the pins above hold its ratios to the table); one WITHOUT A SECOND COLUMN has a `⚠️
    verified, unpriced` row that says its reason in the census's own words."""
    import aes_ourboot
    from harness import addrs

    verified = {address for address, _cell in _verified_rows()}
    unpriced = {int(match["addr"], 16): match[0] for match in _AN_UNPRICED_LINE_RE.finditer(_status())}
    for name, (how, _what) in aes_ourboot.THE_CENSUS.items():
        address = getattr(addrs, name)
        if how == aes_ourboot.IN_THE_TABLE:
            assert address in verified and address not in unpriced, f"{name} ({address:#x}): rows of the table, and no ✅ row"
        else:
            assert address not in verified and how in unpriced.get(address, ""), f"{name} ({address:#x}): no ⚠️ row that says {how!r}"


# ---- BAND 5 WAVE 4, SLICE F: THE FULL FLIP — its entry's counts are the registry's, the batteries' pins and the table's --------------
# The entry states the flip in numbers a reader will quote: how many parts THE DOOR has and how many longwords of a
# machine it maps; how many of the registry's declarations are mapped at a run's entry; the two switches' rows' traps
# (the who-ran pins); who gives the door back; the registry's rows; the table's length; nothing pending. Each is read
# here off what holds it. (What the entry gives as A PROBE'S CENSUS — how many rows take a `trap #2` on a kit call — it
# labels so: one measuring pass, held by no test; the RULE, not one cycle of the ROM's selector switch on a kit call
# of ours, is `tier3.vet_who_ran_the_selector_switch`'s, asked on every such call of every row's own test.)
THE_FULL_FLIP_S_ENTRY = "WAVE 4 — SLICE F: THE FULL FLIP"
_THE_FULL_FLIP_RE = re.compile(
    r"THE DOOR of (?P<parts>\w+) parts over (?P<longwords>\w+) longwords of a machine.*?"
    r"(?P<at_entry>\w+) of the registry's (?P<declared>\w+) declarations are mapped AT A RUN'S ENTRY.*?"
    r"sh_tographic's (?P<graphic>\w+) VDI traps \((?P<graphic_cycles>\d+) cycles\) and sh_toalpha's (?P<alpha>\w+) "
    r"\((?P<alpha_cycles>\d+)\).*?(?P<given_back>\w+) routines GIVE THE DOOR BACK.*?(?P<taken>\w+) routine TAKES IT by a run of its own.*?"
    r"the registry's (?P<rows>[\d,]+) rows", re.S)
THE_LEGEND_SAYS_WHO_RUNS_THE_TRAP = "WHO RUNS THE TRAP: vector $88 holds the build's own `trap #2` handler as every Tier 3 run of ours is entered"


def test_the_full_flip_s_entry_quotes_the_registry_the_who_ran_pins_and_the_table():
    import aes_event
    import test_aes_shlib as switches
    from harness import bench_tier3

    entry = " ".join(_paragraph_from(_status(), THE_FULL_FLIP_S_ENTRY).split())      # (the ledger wraps where it will)
    said = _THE_FULL_FLIP_RE.search(entry)
    assert said, "the full flip's entry no longer states its counts in the sentences this test reads"
    tier3 = bench_tier3()
    traps = switches.VDI_CALLS_OF
    graphic, alpha = traps[(switches.SH_TOGRAPHIC, switches.TO_GRAPHIC_ROW)], traps[(switches.SH_TOALPHA, switches.TO_ALPHA_ROW)]
    assert {name: _number(value.lower()) for name, value in said.groupdict().items()} == {
        "parts": len(aes_event.THE_DOOR),
        "longwords": sum(len(aes_event.THE_MACHINE_S_VECTORS.get(part.what, ())) for part in aes_event.THE_DOOR),
        "at_entry": sum(declared.at_entry for declared in aes_event.CODE_RELOCATIONS), "declared": len(aes_event.CODE_RELOCATIONS),
        "graphic": graphic, "graphic_cycles": graphic * switches.THE_VDI_ARM_S_PASS_CYCLES,
        "alpha": alpha, "alpha_cycles": alpha * switches.THE_VDI_ARM_S_PASS_CYCLES,
        "given_back": len(tier3.THE_DOOR_GIVEN_BACK_BY_THE_ROW_S_OWN_RUN), "taken": len(tier3.THE_DOOR_TAKEN_BY_THE_ROW_S_OWN_RUN),
        "rows": len(tier3.ROWS)}
    assert aes_event.GEM_TRAP_VECTOR.at_entry, "the word itself"
    pending, lines = _PENDING_RE.search(entry), _TABLE_LINES_RE.search(entry)
    assert pending and _number(pending["count"].lower()) == len(aes_event.DECLARED_NOT_YET_MAPPED_AT_TIER3) == 0
    assert lines and _number(lines["lines"]) == len(BENCH_TABLE.read_text().splitlines()), "the table's length, as the full flip's entry states it"
    # ...AND THE ONE LINE OF THE TABLE THE FLIP MOVED SAYS IT: the legend.
    legend = [line for line in BENCH_TABLE.read_text().splitlines() if THE_LEGEND_SAYS_WHO_RUNS_THE_TRAP in line]
    assert len(legend) == 1 and legend[0].startswith("`net`: ")


# ---- ...AND ITS FIX PASS (after the two reviews): what the reworded sentences quote, and the legend's label -------------------------
# The reviews found two claims worded wider than any test held ("no entry of band <= 5 is the ROM's by value"; "every
# run of ours") and a staging stated as a property of the machine. The fix pass reworded them; this holds the
# numbers the new sentences give — the scan's list, the Line-F entries held live, the one longword at deskmain's
# entry, the rows not entered behind our door — to what derives each, and THE LEGEND'S LABEL to the table's line.
_THE_SCAN_S_LIST_RE = re.compile(r"THE\s+SCAN'S LIST IS (?P<scanned>\w+) VALUES")
_THE_HEADLINE_S_LIST_RE = re.compile(r"A ROUTINE THE REGISTRY DECLARES \((?P<scanned>\w+) routines")
_THE_COPIED_ENTRIES_RE = re.compile(r"THE FIRST (?P<copied>\w+) ENTRIES OF THE LINE-F CALL TABLE")
_AT_DESKMAIN_S_ENTRY_RE = re.compile(r"AT deskmain's ENTRY the takeover machine behind THE DOOR holds the ROM's tick glue in (?P<held>\w+) longword")
_NOT_ENTERED_BEHIND_OUR_DOOR_RE = re.compile(
    r"(?P<rows>\w+) rows' machines hold another value in `\$88` than the ROM's handler.*?(?P<takers>\w+) TAKE THE DOOR", re.S)
THE_AES_ROW_S_SCAN = "the ROM's copy of a routine the registry declares ({} routines"


def test_the_full_flip_s_fix_pass_quotes_the_scan_s_list_the_longword_at_deskmain_s_entry_and_the_legend_says_a_labelled_staging():
    import aes_boot
    import aes_event
    import test_aes_boot_w4 as door_machines
    import test_aes_shlib as switches
    from harness import bench_tier3

    status = _status()
    entry = " ".join(_paragraph_from(status, THE_FULL_FLIP_S_ENTRY).split())
    said = {}
    for reading in (_THE_SCAN_S_LIST_RE, _THE_HEADLINE_S_LIST_RE, _THE_COPIED_ENTRIES_RE, _AT_DESKMAIN_S_ENTRY_RE, _NOT_ENTERED_BEHIND_OUR_DOOR_RE):
        found = reading.search(entry)
        assert found, f"the full flip's entry no longer has the sentence {reading.pattern!r} reads"
        said.setdefault(reading.pattern, {name: _number(value.lower()) for name, value in found.groupdict().items()})
    scanned = len(aes_boot.routines_by_value())
    takers, never = switches.ROWS_THAT_TAKE_THE_DOOR, switches.ROWS_THAT_NEVER_HOLD_IT
    assert list(said.values()) == [
        {"scanned": scanned}, {"scanned": scanned}, {"copied": door_machines.LINE_F_ENTRIES_COPIED},
        {"held": len(door_machines.HELD_AT_DESKMAIN_S_ENTRY)},
        {"rows": sum(takers.values()) + sum(never.values()), "takers": sum(takers.values())}]
    assert THE_AES_ROW_S_SCAN.format(scanned) in status, "the Components table's aes row states the scan's list too"
    # ...AND THE TABLE'S LEGEND SAYS WHAT THE IDLE ROWS' MACHINE IS: a door takeover, laid by the harness, a labelled
    # staging — in the words `tier3` names — with the door's longwords and the scan's list counted as the registry has them.
    tier3 = bench_tier3()
    legend, = [line for line in BENCH_TABLE.read_text().splitlines() if THE_LEGEND_SAYS_WHO_RUNS_THE_TRAP in line]
    longwords = sum(len(aes_event.THE_MACHINE_S_VECTORS.get(part.what, ())) for part in aes_event.THE_DOOR)
    for words in (tier3.THE_IDLE_ROWS_MACHINE_IS_A_LABELLED_STAGING, "A DOOR TAKEOVER", "A LABELLED STAGING", "LAID BY THE HARNESS",
                  f"with {longwords} longwords of the machine", f"({scanned} routines, not every ROM routine)"):
        assert words in legend, f"the table's legend no longer says {words!r}"
    assert "EVERY run of ours" not in legend and "holds a ROM routine of band" not in legend, "the two sentences the reviews found too wide"


# ---- SLICE B's FIX PASS: THE STRETCHES' LINE NET OF THE ROM'S LINE-F HANDLER, READ FROM THE TABLE ---------------------------
# The table prints, under each of the sixteen stretches, its ratio NET OF THE ROM'S LINE-F HANDLER — the one place the
# figures over the bar that the slice REPORTS are printed. Nothing read that line (a line capped at the bar, or printed
# with no handler's share at all, passed every test), and STATUS quoted its figures by hand. So: EVERY STRETCH'S LINE IS
# READ HERE, all sixteen, held to its own integers; the battery's pins of the figures over 1.00 and STATUS's quotes —
# the entry's (f) and AWAITING (22) B-1 — are THOSE LINES' PRINTED DIGITS; and the battery holds each line's integers
# to the stretch's measured price (`test_aes_ourboot.py`: the table cannot print a figure the run did not make). THE
# LINES' READER IS `aes_ourboot.stretch_lines_of` — the battery's too, which may not import this module: one that did
# would reach the bench's registry through it, and be handed out after it (`derived._registry_modules`).
_THE_SIXTEEN_STRETCHES_RE = re.compile(
    r"THE SIXTEEN STRETCHES IN THE TABLE'S ORDER, with thunks / net of the ROM's Line-F handler \(the table's own lines\): "
    r"(?P<shipped>[\d. /,]+); THE BENCH BLOB'S, the same sixteen \(the battery's pins\): (?P<bench>[\d. /,]+)\.")
_FIGURES_OVER_RE = re.compile(r"(?P<over_1>\w+) FIGURES ARE OVER 1\.00 AND (?P<over_the_bar>\w+) OVER 1\.10")
_A_FIGURE_WITH_ITS_CYCLES_RE = re.compile(
    r"(?P<net>\d\.\d\d) \((?P<ours>[\d,]+) \+ (?P<glue>[\d,]+) in thunks to (?P<the_rom_s>[\d,]+) less (?P<line_f>[\d,]+)\)")
_B_1_RE = re.compile(
    r"B-1 — .*?(?P<stretches>\w+) STRETCHES AND ONE TURN ARE OVER 1\.10.*?THE STRETCHES OVER 1\.00 ON THAT LINE, IN THE TABLE'S ORDER: "
    r"(?P<figures>[\d., ]+) \(.*?THE TURN: (?P<turn>\d\.\d\d) under (?P<rows>\d+) rows")
_B_12_RE = re.compile(r"B-12 .*?NET OF THE ROM'S LINE-F HANDLER, the stretches over 1\.10 in the registry's order: (?P<figures>[\d., ]+) \(")
_A_LEDGER_ROW_S_NET_RE = re.compile(r"(?i:net of the ROM's Line-F handler) (?P<net>\d\.\d\d(?: / \d\.\d\d)*)")
THE_OUR_BOOT_S_AWAITING = "(22) WAVE 4, SLICE B — THE OUR BOOT"


def _with_its_cycles(net, ours, glue, the_rom_s, line_f):
    return (net, *(f"{value:,}" for value in (ours, glue, the_rom_s, line_f)))


def test_the_stretches_figures_net_of_the_line_f_handler_are_the_table_s_own_lines():
    """EVERY STRETCH'S LINE NET OF THE ROM'S LINE-F HANDLER, all sixteen, and every quote of one: the battery's pins of
    the figures over 1.00 (and so of the five over the bar) and of the turn inside gem_main's stretches; the entry's
    sixteen pairs, its count of figures over 1.00 and over 1.10, and each figure it spells with its cycles; AWAITING
    (22) B-1's list and B-12's (the bench blob's, the battery's pins) — EACH THE TABLE'S PRINTED DIGITS."""
    import aes_ourboot
    import test_aes_ourboot as battery
    from harness import addrs

    assert aes_ourboot.THE_TABLE == BENCH_TABLE, "one table"
    lines = aes_ourboot.stretch_lines_of(BENCH_TABLE.read_text())
    keyed = {battery.key_of(aes_ourboot.STRETCHES[name]): line for name, line in lines.items()}
    assert len(lines) == 16 and list(keyed) == [battery.key_of(stretch) for stretch in battery.STRETCHES], "the table's order is the registry's"
    assert A_STRETCH_S_CASE_BEGINS == aes_ourboot.ON_THE_OUR_BOOT_MACHINE
    over_1 = {key: line.net for key, line in keyed.items() if float(line.net) > 1.00}
    assert over_1 == battery.NET_OF_LINE_F_OVER_1_00 and list(over_1) == list(battery.NET_OF_LINE_F_OVER_1_00), (
        f"the battery pins {battery.NET_OF_LINE_F_OVER_1_00} as the figures over 1.00 net of the ROM's Line-F handler; the table prints {over_1}")
    turns = [turn for line in lines.values() for turn in line.turns]
    shipped_turn = battery.THE_TURN_INSIDE[battery.SHIPPED]
    assert {(turn.with_thunks, turn.net) for turn in turns} == {shipped_turn} and len(turns) == sum(stretch.turns for stretch in battery.STRETCHES) == 3
    status = " ".join(_status().split())
    entry = " ".join(_paragraph_from(_status(), THE_OUR_BOOT_S_ENTRY).split())
    sixteen, counted = _THE_SIXTEEN_STRETCHES_RE.search(entry), _FIGURES_OVER_RE.search(entry)
    assert sixteen and counted, "the our-boot's entry no longer quotes the sixteen stretches' two figures, or no longer counts the ones over"
    assert sixteen["shipped"] == ", ".join(f"{line.with_thunks} / {line.net}" for line in lines.values()), (
        f"STATUS.md quotes {sixteen['shipped']!r} for the sixteen stretches; the table prints "
        f"{', '.join(f'{line.with_thunks} / {line.net}' for line in lines.values())!r}")
    assert sixteen["bench"] == ", ".join(f"{with_thunks} / {net}" for with_thunks, net in battery.ON_THE_BENCH_BLOB.values())
    printed = [*over_1.values(), *(turn.net for turn in turns)]
    assert {name: _number(value.lower()) for name, value in counted.groupdict().items()} == {
        "over_1": len(printed), "over_the_bar": sum(float(figure) > battery.BAR for figure in printed)}, f"STATUS.md says {counted[0]!r}"
    spelt = [tuple(found.groups()) for found in _A_FIGURE_WITH_ITS_CYCLES_RE.finditer(entry)]
    held = [_with_its_cycles(line.net, line.ours, line.glue, line.the_rom_s, line.line_f) for key, line in keyed.items() if key in over_1]
    held.append(_with_its_cycles(turns[0].net, turns[0].ours, turns[0].glue, turns[0].the_rom_s, turns[0].line_f))
    assert spelt == held, f"the entry spells {spelt} with their cycles; the table's lines over 1.00, in its order, and the turn's are {held}"
    # ...and THE LEDGER'S OWN ROWS of the four routines quote the same line, every stretch of each in the table's order.
    for routine in aes_ourboot.SYMBOL_OF:
        ledger_row = re.search(rf"^\| `0x{getattr(addrs, routine):x}` \|.*$", _status(), re.M)[0]
        quoted = _A_LEDGER_ROW_S_NET_RE.search(ledger_row)
        assert quoted and quoted["net"] == " / ".join(line.net for (its_routine, _what), line in keyed.items() if its_routine == routine), (
            f"{routine}'s row of the ledger quotes {quoted and quoted['net']!r} net of the ROM's Line-F handler")
    awaiting = status[status.index(THE_OUR_BOOT_S_AWAITING):]
    b_1, b_12 = _B_1_RE.search(awaiting), _B_12_RE.search(awaiting)
    assert b_1 and b_12, "AWAITING (22) no longer lists B-1's figures, or B-12's, in the sentence this test reads"
    assert (_number(b_1["stretches"].lower()), b_1["figures"], b_1["turn"], int(b_1["rows"])) == (
        len(battery.OVER_THE_BAR_NET_OF_LINE_F), ", ".join(over_1.values()), shipped_turn[1], len(turns)), f"AWAITING (22) says {b_1[0][-200:]!r}"
    assert b_12["figures"] == ", ".join(net for _with_thunks, net in battery.ON_THE_BENCH_BLOB.values() if float(net) > battery.BAR), (
        f"AWAITING (22) B-12 says {b_12['figures']!r}")


# ---- BAND 6 WAVE 0: THE OPENING'S GROUNDWORK — the entry's counts are the three batteries' and the build's -----------------
# The entry quotes the hands' campaign (chains, steps, reach, the four depths), the table (its three verdicts, the
# thunks and native routines entered through it), the pre-init captures and the read guard. EACH IS READ HERE off what
# holds it: the batteries' pins (each held to its derivation by the battery's own tests — a chain walked, a thunk
# entered), the generator's entries, the makefile test's captures, the registry's rows.
THE_OPENING_S_ENTRY = "BAND 6 WAVE 0 — THE OPENING'S GROUNDWORK"
_THE_HANDS_RE = re.compile(
    r"THE HANDS' CAMPAIGN IS (?P<chains>\d+) CHAINS / (?P<steps>\d+) STEPS, EVERY ONE NAMING A ROUTINE OF ITS ACT; REACH (?P<reached>\d+) OF "
    r"BAND 6's (?P<routines>\d+); THE DEEPEST BY THE WRITE LEDGERS: PD0 (?P<pd0>[\d,]+) of (?P<pd0_bytes>[\d,]+), PD1 (?P<pd1>\d+) of "
    r"(?P<pd1_bytes>[\d,]+), the dispatcher (?P<dispatcher>\d+) \((?P<elsewhere>\d+) on every other chain[^)]*\), the userdef stack (?P<userdef>\d+) "
    r"of (?P<userdef_bytes>[\d,]+)")
_THE_TABLE_OF_OURS_RE = re.compile(
    r"THE TABLE IS (?P<entries>\d+) ENTRIES: (?P<native>\d+) native \((?P<native_routines>\d+) routines\), (?P<thunked>\d+) through "
    r"(?P<thunks>\d+) thunks, (?P<the_rom_s>\d+) the ROM's; (?P<entered>\d+) THUNKS ENTERED THROUGH IT, (?P<unentered>\w+) UNENTERED BY NAME; "
    r"(?P<natives_entered>\d+) NATIVE ROUTINES ENTERED, (?P<natives_unentered>\w+) NOT, BY NAME")
_THE_CAPTURES_RE = re.compile(r"THE PRE-INIT CAPTURES ARE (?P<captures>\w+)")
_THE_READ_GUARD_RE = re.compile(r"THE READ GUARD: (?P<rows>[\d,]+) rows in (?P<chunks>\d+) chunks, (?P<not_held>\w+) NOT HELD BY NAME")


HANDS_AT_WAVE_0 = {"chains": 46, "steps": 133, "reached": 215}
THE_WAVE_1A_ENTRY = "BAND 6 WAVE 1a — UNITS O AND D"


def hands_now(hands, *, with_the_campaign_s_size=False):
    """What `_THE_HANDS_RE` reads, as the battery and the derivations have it today (the four depths; and the
    campaign's size where asked)."""
    import aes_desk as desk

    deepest = {which: depth for which, (_chain, depth) in hands.DEEPEST.items()}
    now = {"routines": len(desk.routines()), "pd0": deepest[desk.PD0_STACK], "pd0_bytes": hands.PD0_BYTES, "pd1": deepest[desk.PD1_STACK],
           "pd1_bytes": hands.PD1_BYTES, "dispatcher": deepest[desk.DISPATCHER_STACK], "elsewhere": hands.DISPATCHER_ELSEWHERE,
           "userdef": deepest[desk.USERDEF_STACK], "userdef_bytes": desk.USERDEF_STACK_BYTES}
    if with_the_campaign_s_size:
        now.update(chains=len(desk.CHAINS), steps=sum(len(chain.steps) for chain in desk.CHAINS.values()), reached=hands.REACHED)
    return now


def test_the_wave_1a_entry_states_the_hands_campaign_as_it_stands():
    """BAND 6 WAVE 1a's fix pass added five chains (the dialogs' less-trodden buttons): its entry states the
    campaign's size, its reach and the four depths in the opening's sentence, read here off the battery and the
    derivations as the opening's is."""
    import test_aes_desk_rom as hands

    entry = " ".join(_paragraph_from(_status(), THE_WAVE_1A_ENTRY).split())
    found = _THE_HANDS_RE.search(entry)
    assert found, "band 6 wave 1a's entry no longer states the hands' campaign in the sentence this test reads"
    assert {key: _number(value.lower()) for key, value in found.groupdict().items()} == hands_now(hands, with_the_campaign_s_size=True)


def test_the_opening_s_entry_quotes_the_hands_the_table_the_captures_and_the_read_guard():
    import aes_desk as desk
    import test_aes_desk_rom as hands
    import test_aes_lineftable as table
    import test_makefile
    import test_room_poison as guard
    from harness import bench_tier3

    entry = " ".join(_paragraph_from(_status(), THE_OPENING_S_ENTRY).split())
    said = {name: pattern.search(entry) for name, pattern in (("the hands", _THE_HANDS_RE), ("the table", _THE_TABLE_OF_OURS_RE),
                                                              ("the captures", _THE_CAPTURES_RE), ("the read guard", _THE_READ_GUARD_RE))}
    missing = [name for name, found in said.items() if not found]
    assert not missing, f"band 6 wave 0's entry no longer states {missing} in the sentence this test reads"
    numbers = {name: {key: _number(value.lower()) for key, value in found.groupdict().items()} for name, found in said.items()}
    # (the campaign's size AS THE ENTRY WROTE IT — history since band 6 wave 1a's fix pass added chains: its entry
    # states the campaign as it stands, and `test_the_wave_1a_entry_states_the_hands_campaign_as_it_stands` reads it)
    assert {key: numbers["the hands"].pop(key) for key in HANDS_AT_WAVE_0} == HANDS_AT_WAVE_0
    assert numbers["the hands"] == hands_now(hands)
    assert (hands.CHAINS, hands.STEPS, hands.BAND_6_ROUTINES) == (len(desk.CHAINS), sum(len(chain.steps) for chain in desk.CHAINS.values()),
                                                                  len(desk.routines()))
    verdicts = [made.verdict for made in table.linef_table.entries()]
    natives_entered, natives_unentered = table.native_cases()
    assert numbers["the table"] == {
        "entries": len(verdicts), "native": verdicts.count(table.OURS_NATIVE), "native_routines": len(table.native_routines()),
        "thunked": verdicts.count(table.OURS_THROUGH_A_THUNK), "thunks": len(table.THUNKED), "the_rom_s": verdicts.count(table.THE_ROM_S),
        "entered": len(table.ENTERED), "unentered": len(table.UNENTERED), "natives_entered": len(natives_entered),
        "natives_unentered": len(natives_unentered)}
    assert numbers["the captures"] == {"captures": len(test_makefile.PREINIT_CAPTURES)}
    tier3 = bench_tier3()
    assert numbers["the read guard"] == {"rows": len(tier3.ROWS), "chunks": guard.CHUNKS, "not_held": guard.NOT_HELD_ROWS}
