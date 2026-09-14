#!/usr/bin/env python3
"""test_atari_pins.py — the host-side pins for the tables this directory measures a ROM with.

    make test-host        (or: ../.venv/bin/python -m pytest -q test_atari_pins.py)

NO EMULATOR AND NO TARGET BUILD. Everything here is a statement about two files agreeing, and it
runs in a second, which is what makes it a gate rather than an errand.

WHAT IT PINS. `sysvars.py` gives the system-variable block one definition, and two other files say
the same things in their own language: `projects/tos102us/names.txt`, the workspace's source of
truth for NAMES, and `prg/tosapi.h`, which spells two of the same ADDRESSES in C for the programs
that run on the machine. A renamed variable in the name map, or a `SYSVAR_*` that drifted from the
table, is exactly the kind of difference nothing else here can see: the ledger and the boot surface
would keep reporting, in the old name, about the new address.
"""
import re
from pathlib import Path

import pytest

import cdefines
import sysvars

HERE = Path(__file__).resolve().parent
# projects/tos102us/names.txt — the name map for the whole ROM, Ghidra addresses = ROM addresses,
# and for RAM addresses (which the $400 block is) the plain address.
NAME_MAP = HERE.parents[1] / "names.txt"
TOSAPI_HEADER = HERE / "prg" / "tosapi.h"

# `var 0x0424 memctrl`, with the optional trailing `# ctx` confidence tag the workspace uses.
NAME_MAP_VAR = re.compile(r"^var\s+(0x[0-9A-Fa-f]+)\s+(\S+)")
# The header's spelling of one of these addresses: SYSVAR_HZ200 for the table's `_hz_200`.
TOSAPI_SYSVAR_PREFIX = "SYSVAR_"

NAMED_SYSVARS = tuple(entry for entry in sysvars.SYSVARS if entry[3] != sysvars.PAD_NAME)


def comparable_name(name):
    """A name with the punctuation taken out, so `_hz_200` and C's `SYSVAR_HZ200` are one name."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def name_map_variables():
    """{address: name} for every `var` line of names.txt inside the system-variable block."""
    found = {}
    for line in NAME_MAP.read_text().splitlines():
        match = NAME_MAP_VAR.match(line.strip())
        if match and sysvars.BLOCK_START <= int(match.group(1), 0) < sysvars.BLOCK_END:
            found[int(match.group(1), 0)] = match.group(2)
    return found


@pytest.mark.parametrize("address,_width,_count,name",
                         NAMED_SYSVARS, ids=[entry[3] for entry in NAMED_SYSVARS])
def test_sysvar_carries_the_name_the_name_map_gives_it(address, _width, _count, name):
    named = name_map_variables()
    assert address in named, f"names.txt has no `var ${address:03x}` — sysvars.py calls it {name}"
    assert named[address] == name, (f"names.txt calls ${address:03x} {named[address]} and "
                                    f"sysvars.py calls it {name}; names.txt is the source of truth")


def test_every_named_variable_in_the_block_is_in_the_table():
    """The other direction: a variable the name map knows about and the table does not would be
    rendered as part of the one before it, at the wrong width, in silence."""
    addresses = {address for address, _width, _count, _name in sysvars.SYSVARS}
    missing = {f"${address:03x}": name for address, name in name_map_variables().items()
               if address not in addresses}
    assert not missing, f"names.txt names these and sysvars.py has no entry at their address: {missing}"


def test_the_table_covers_its_block_with_no_gap_and_no_overlap():
    """What catches an entry that moved: the tail of this table has TWO published layouts that
    differ by two bytes (a `prt_cnt` word at $59E, or not), and taking the wrong one shifts every
    variable after it without changing a single name."""
    at = sysvars.BLOCK_START
    for address, width, count, name in sysvars.SYSVARS:
        assert address == at, (f"{name} is at ${address:03X} and the entry before it ends at "
                               f"${at:03X}")
        at += sysvars.WIDTH_BYTES[width] * count
    assert at == sysvars.BLOCK_END


def test_tosapi_sysvars_are_the_table_s_addresses():
    """prg/tosapi.h reads these addresses on the machine itself; the table renders them afterwards.
    Two spellings of $4BA is one chance for the program and the driver to mean different bytes."""
    by_name = {comparable_name(name): address for address, _width, _count, name in NAMED_SYSVARS}
    header = {name[len(TOSAPI_SYSVAR_PREFIX):]: value
              for name, value in cdefines.defines(TOSAPI_HEADER).items()
              if name.startswith(TOSAPI_SYSVAR_PREFIX)}
    assert header, f"{TOSAPI_HEADER} defines no {TOSAPI_SYSVAR_PREFIX}* — has the prefix changed?"
    for name, address in header.items():
        assert comparable_name(name) in by_name, (f"{TOSAPI_SYSVAR_PREFIX}{name} names no system "
                                                  f"variable in sysvars.py")
        assert by_name[comparable_name(name)] == address, (
            f"{TOSAPI_SYSVAR_PREFIX}{name} is {address:#x} and sysvars.py has that variable at "
            f"{by_name[comparable_name(name)]:#x}")
