"""The headers' own constants, held to ONE name per value and ONE value per name.

`include/addrs.h` and the four `include/gemdos_*.h` are the single source of truth this project's
cores and its cases both read (`tools/addrs.py` parses them; a battery binds them as module
attributes). Nothing in C diagnoses a SECOND SPELLING of one address: no translation unit includes
every header, so two names for one location never meet the compiler, and a case that pokes one while
a core reads the other is green on both shores having tested nothing.

That is not hypothetical here. `$87cc` spent a whole wave under two names — `GEMDOS_PROCESS_ID`,
guessed by the process wave from a table that is not a process table, and `GEMDOS_DISK_ERROR_DRIVE`,
read off the ROM storing a drive there by the file-system wave — and the two sat eight hundred lines
apart in one file with nothing refusing them.

WHAT IS AND IS NOT AN ERROR. A repeated NAME is always one. A repeated VALUE is one only for an
ADDRESS: two field offsets of different structures are equal all the time (`+0`, `+4`, `+8` are
every record's first fields) and naming that a collision would be noise. So the value rule applies
from `ADDRESS_FLOOR` up — above the small offsets, sizes, masks and counts — and the handful of
deliberate coincidences are allowed BY NAME, each with the reason it is one.

This file is the twin of `projects/zynaps/recreate/test/test_constants.py`, narrowed: that one pins a
Python copy against its C original, and here the cases have no copies to pin — they read the header.
What is left to refuse is the header disagreeing with itself.
"""
from collections import defaultdict
from pathlib import Path

from harness import addrs

INCLUDE = Path(__file__).resolve().parents[1] / "include"
# `addrs.h` plus the per-subsystem headers the batteries parse. Globbed rather than listed: a wave
# that adds `gemdos_<group>.h` gets it checked without editing this file, which is the failure mode
# a hand-written list has.
HEADERS = [INCLUDE / "addrs.h"] + sorted(INCLUDE.glob("gemdos_*.h"))

# Where a value starts being an ADDRESS rather than an offset, a size, a count or a mask: $400 is the
# top of the 68000's own vector table and the bottom of the system variables, so every location this
# project names is at or above it. A value at or above 0x1000000 is off the 24-bit bus and is a
# negative error code or a mask, not a place.
ADDRESS_FLOOR = 0x400
ADDRESS_CEILING = 0x1000000

# The deliberate coincidences, each with the reason it is one. A pair here is NOT two spellings of
# one thing: it is two different things that happen to be the same number.
ALLOWED_ALIASES = {
    frozenset(("GEMDOS_TRAP1_END", "GEMDOS_RESYNC_CLOCK")):
        "the trap #1 entry's last byte and the routine that begins at it — a boundary and a "
        "function, and a wave that moves either must not silently move the other",
    frozenset(("RANDOM_MASK", "BOOT_SERIAL_MAX")):
        "two 24-bit MASKS, not addresses: XBIOS Random's state and Protobt's serial bound",
}


def _defines(header):
    """`[(name, value)]` for every plain integer `#define` in one header, in file order.

    `tools/addrs.py`'s own regex, deliberately: this refuses duplicates among exactly the constants
    the cores and the cases really bind, and a second parser here would be a second opinion about
    which lines count.
    """
    out = []
    for line in header.read_text().splitlines():
        match = addrs._DEFINE.match(line)
        if match and match.group(2)[0].isdigit():
            out.append((match.group(1), int(match.group(2).rstrip("uUlL"), 0)))
    return out


def test_no_constant_is_defined_under_two_names():
    """Every header, one name per NAME — the plain half of the rule."""
    where = defaultdict(list)
    for header in HEADERS:
        for name, _value in _defines(header):
            where[name].append(header.name)
    twice = {name: files for name, files in where.items() if len(files) > 1}
    assert not twice, (
        f"these names are defined more than once: {twice} — one of the two is the value every "
        f"translation unit that includes both will see, and which one is the include order's to "
        f"decide")


def test_no_address_is_spelt_under_two_names():
    """...and one name per ADDRESS, which is what $87cc failed for a whole wave.

    A pair in `ALLOWED_ALIASES` is admitted with its reason; anything else is a finding, and the
    remedy is to delete the guess and keep the name the evidence gives — not to add an entry here.
    """
    names_of = defaultdict(set)
    for header in HEADERS:
        for name, value in _defines(header):
            if ADDRESS_FLOOR <= value < ADDRESS_CEILING:
                names_of[value].add(name)
    collisions = {value: names for value, names in names_of.items()
                  if len(names) > 1 and frozenset(names) not in ALLOWED_ALIASES}
    assert not collisions, (
        "these addresses are spelt under two names, so a core and a case can read one and poke the "
        "other: "
        + ", ".join(f"{value:#x} = {sorted(names)}" for value, names in sorted(collisions.items()))
        + " — delete the one the evidence does not support, or, if the two really are different "
          "things at one address, say so in ALLOWED_ALIASES")


def test_every_allowed_alias_is_still_a_real_pair():
    """An allow-list entry whose names no longer collide is a waiver for nothing, and the next
    reader would take it for a live exception. Deleted rather than kept."""
    values = defaultdict(set)
    for header in HEADERS:
        for name, value in _defines(header):
            values[name].add(value)
    for alias, why in ALLOWED_ALIASES.items():
        seen = {name: values.get(name) for name in alias}
        assert all(seen.values()), f"ALLOWED_ALIASES names a constant no header defines: {seen}"
        assert len(set().union(*seen.values())) == 1, (
            f"ALLOWED_ALIASES entry {sorted(alias)} ({why}) no longer names one value: {seen} — "
            f"the waiver is spent and should be deleted")
