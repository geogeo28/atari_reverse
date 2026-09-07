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
import functools
import re
from pathlib import Path

import pytest

REC = Path(__file__).resolve().parents[1]

# `## Verified — <subsystem> (N)`, and the `| `0xADDR` | ... | ✅ verified |` rows beneath it.
_SECTION_RE = re.compile(r"^## Verified — (?P<name>\S+) \((?P<count>\d+)\)\s*$", re.M)
_ROW_RE = re.compile(r"^\| `(?P<addr>0x[0-9a-f]+)` \|.*\| ✅ verified \|", re.M)
# ...and the heading of the table that has to account for everything the rows do not.
_NOT_RECONSTRUCTED_HEADING = "## Not reconstructed, and why"
# A row of that table: its FIRST column names the routine(s), and only addresses there count as
# "this is why it has no ✅ row". The other columns cite verified addresses on purpose — several
# rows say which now-ported routine unblocked them — so a sweep for hex over the whole section would
# read those citations as deferrals and let a real hole hide behind one.
_NOT_RECONSTRUCTED_ROW_RE = re.compile(r"^\| (?P<routines>[^|]*) \|", re.M)
# `fn 0x<addr> <name>` in the name map, which is the list of everything that must be accounted for.
_FN_RE = re.compile(r"^fn (?P<addr>0x[0-9a-f]+)\s+(?P<name>\S+)", re.M)


@functools.lru_cache(maxsize=None)
def _status():
    return (REC / "STATUS.md").read_text()


def _section_bodies():
    """[(subsystem, stated count, the text under that heading)] in file order.

    One slicing of the file, because two of them drifting apart is the failure this whole module is
    about: a section boundary read one way for the counts and another way for the addresses would let
    a row be counted under one heading and attributed to another.
    """
    text = _status()
    heads = list(_SECTION_RE.finditer(text))
    return [(head["name"], int(head["count"]),
             text[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)])
            for i, head in enumerate(heads)]


def _sections():
    """[(subsystem, stated count, rows found)] in file order."""
    return [(name, stated, len(_ROW_RE.findall(body))) for name, stated, body in _section_bodies()]


def _verified_rows():
    """{address: [subsystem, ...]} over every `✅ verified` row in the file."""
    rows = {}
    for name, _stated, body in _section_bodies():
        for row in _ROW_RE.finditer(body):
            rows.setdefault(int(row["addr"], 16), []).append(name)
    return rows


def _deferred_addresses():
    """Every address named in the FIRST column of the "Not reconstructed" table."""
    text = _status()
    section = text[text.index(_NOT_RECONSTRUCTED_HEADING):]
    return {int(addr, 16)
            for row in _NOT_RECONSTRUCTED_ROW_RE.finditer(section)
            for addr in re.findall(r"0x[0-9a-f]+", row["routines"])}


def _named_functions():
    """{address: name} for every `fn` line in `../names.txt`, the name map that is the source of
    truth (CLAUDE.md). It is what the ledger has to account for, one routine at a time."""
    return {int(m["addr"], 16): m["name"]
            for m in _FN_RE.finditer((REC.parent / "names.txt").read_text())}


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


def test_no_address_has_two_verified_rows():
    """One routine, one ✅ row — across sections, not just within one.

    Two sections claiming the same address is how the ledger comes to say more work was done than
    was: the per-section counts both include it and the total double-counts. It is not hypothetical —
    in `projects/bubbleghost/recreate`, where this check was written, `draw_room_to_stage` @ 0x13a08
    carried a whole-routine row under `frontend` and a slice row under `blit` at the same time. A
    slice that really is a DIFFERENT span gets an address of its own (that project's
    `build_sprite_bank_grab_cells` @ 0x13330), which is what keeps the legitimate case out of here.
    """
    duplicated = {addr: sections for addr, sections in _verified_rows().items()
                  if len(sections) > 1}
    assert not duplicated, "addresses with more than one ✅ verified row: " + "; ".join(
        f"{addr:#x} in {', '.join(sections)}" for addr, sections in sorted(duplicated.items()))


def test_every_named_function_is_verified_or_deferred():
    """Every `fn` in `../names.txt` has a ✅ row or a row in "Not reconstructed" — and not both.

    THE LEDGER'S WHOLE CLAIM is that "what is left" is one list rather than several asides, and
    without this nothing checks that the list is complete: a routine with neither row is simply
    absent, which reads exactly like a routine nobody had to think about. In
    `projects/bubbleghost/recreate`, where this check was written, two were — `crt0_setup_args`
    @ 0x10116, and `fp_cmp`, whose row was filed at its interior entry point rather than at the
    address the name map gives it.

    A ✅ row for an address the name map does NOT carry is allowed and is not an oversight: a slice
    of a routine is filed under the address it starts at, which is not a function's entry.

    IT ARMS AT THE FIRST ROW. A bootstrap ledger accounts for nothing at all, and listing every one
    of `../names.txt`'s `fn` lines as "not started" before anyone has read them would be prose
    nobody would maintain. So while BOTH tables are empty this skips, loudly, rather than reddening
    a skeleton — and the moment a wave files its first ✅ row or its first deferral, the whole name
    map has to be accounted for. That is the commit boundary the gate exists to force
    (`docs/agent-playbook.md` §12: "a ledger gate COUPLES a subsystem to its rows").
    """
    verified, deferred = set(_verified_rows()), _deferred_addresses()
    functions = _named_functions()
    assert functions, "../names.txt has no `fn` lines — the name map or its format has moved"
    if not verified and not deferred:
        pytest.skip(f"the ledger is empty, so this gate is not armed yet; it accounts for all "
                    f"{len(functions)} `fn` lines from the first row filed (README.md, "
                    f"'Adding a function', step 7)")

    unaccounted = sorted(addr for addr in functions if addr not in verified | deferred)
    assert not unaccounted, (
        "these `fn` lines in ../names.txt have neither a ✅ row nor a row in "
        f'"{_NOT_RECONSTRUCTED_HEADING[3:]}": '
        + ", ".join(f"{addr:#x} {functions[addr]}" for addr in unaccounted))

    both = sorted(verified & deferred)
    assert not both, (
        "these addresses have a ✅ row AND a row in "
        f'"{_NOT_RECONSTRUCTED_HEADING[3:]}", so the ledger says both that they are done and that '
        "they are not: "
        + ", ".join(f"{addr:#x} {functions.get(addr, '?')}" for addr in both))
