"""Pin the cycle-per-PC profile's slot map and what fills it, kit-side.

The profile keeps one tally per even PC: RAM's [0, 1 MiB) first, then — in ROM mode — the ROM
window's [rom_lo, rom_lo + 1 MiB), so the ORIGINAL's side of a ROM bench row, which runs the ROM in
place, can be split between its routines. `osh_prof_slot` is the one map from a PC to its slot, and
answers `osh_prof_slots()` for a PC no slot covers; `osh_run` tallies as `osh_run_bench` does (shim.c,
"optional cycle-per-PC profile").

Pinned from C (`profile_probe.c`) for test_rom_mode.py's reason: this directory binds no project, so
the oracle is not reachable from Python here, and `compile_probe` rebuilds `shim.c` on every run.
"""
import re
import subprocess

from pathlib import Path

import pytest

from probe_build import compile_probe

PROBE_SRC = Path(__file__).with_name("profile_probe.c")

# The probe's geometry, mirrored — it prints raw values and this file owns every claim about them.
PROF_RAM_BYTES = 1 << 20
PROF_ROM_BYTES = 1 << 20
PROF_SLOT_BYTES = 2
ROUTINE_OFFSET = 0x1000
PROF_SLOTS = (PROF_RAM_BYTES + PROF_ROM_BYTES) // PROF_SLOT_BYTES

EXACT = {
    "prof_slots": PROF_SLOTS,
    "slot_ram_pc": ROUTINE_OFFSET // PROF_SLOT_BYTES,                       # a RAM PC is pc / 2
    "slot_rom_pc": (PROF_RAM_BYTES + ROUTINE_OFFSET) // PROF_SLOT_BYTES,    # a ROM PC follows RAM's
    "slot_io_pc": PROF_SLOTS,                                              # the I/O page: uncovered
    "slot_above_rom_hi": PROF_SLOTS,                                       # past the window: uncovered
    "slot_rom_pc_rom_mode_off": PROF_SLOTS,                                # no window, no ROM slots
    "rom_run_ram_slots": 0,         # a ROM routine lands nowhere at its offset among RAM's slots...
    "ram_run_rom_slots": 0,         # ...and a RAM routine nowhere at its offset among the ROM's
    "rom_slots_after_reset": 0,     # osh_prof_reset clears the ROM slots too
    "off_whole_tally": 0,           # off, nothing is tallied at all
}
# Printed for the relational claims below, not compared to a constant.
RELATIONAL = {"rom_run_cycles", "rom_run_rom_slots", "ram_run_cycles", "ram_run_ram_slots",
              "off_run_cycles"}


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Build and run the probe once; return {claim: the value it printed}."""
    binary = compile_probe(PROBE_SRC, tmp_path_factory.mktemp("profile"))
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    return {name: int(value) for name, value in re.findall(r"^(\S+) (\d+)$", out, re.M)}


def test_the_probe_reports_every_claim(results):
    """Guard the fixture: a probe that stopped printing would make every assertion vacuous."""
    assert set(results) == set(EXACT) | RELATIONAL


@pytest.mark.parametrize("claim", sorted(EXACT))
def test_the_profile_maps_and_clears_its_slots(results, claim):
    assert results[claim] == EXACT[claim], (
        f"{claim}: the probe reported {results[claim]:#x}, not {EXACT[claim]:#x}")


@pytest.mark.parametrize("side", ["rom", "ram"])
def test_osh_run_tallies_every_cycle_in_the_routines_own_slots(side, results):
    """The whole run's cycles, and only those, land in the slots of the PCs that spent them."""
    cycles = results[f"{side}_run_cycles"]
    assert cycles > 0
    assert results[f"{side}_run_{side}_slots"] == cycles


def test_the_off_case_ran(results):
    """The control for `off_whole_tally`: an empty profile after runs that spent no cycles says nothing."""
    assert results["off_run_cycles"] > 0
