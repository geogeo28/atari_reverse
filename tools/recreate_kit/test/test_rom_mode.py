"""Pin ROM MODE's memory map and its missing trap model, kit-side.

A .PRG project's image IS the machine's RAM: one bound says whether an address is image or not. A
ROM project's image is the whole 24-bit address space — RAM at the bottom, the decoded I/O blocks at
$ff0000, the ROM above them — so an address can be numerically inside the image and still not be
memory. Get that wrong and the PSG, the seeded hardware reads and the hardware write ledger all
silently stop being models and become ordinary image bytes, on BOTH sides, which is the quietest
false green the kit can produce (shim.c, "THE MEMORY MAP"; TRAP_MODEL.md, "ROM mode").

The other half is the trap model, which ROM mode does not install: the image IS the operating
system, so a `trap #13` must be taken through the image's own vector table into the ROM's handler.

Both are pinned from C (`rom_mode_probe.c`) for `test_entry_state.py`'s reason: this directory binds
no project, and `harness`/`emu` load a candidate `.so` at import, so the oracle is not reachable
from Python here. `probe_build.compile_probe` rebuilds `shim.c` from source on every run, so a
reverted guard reddens instead of hiding behind an up-to-date artifact.
"""
import re
import subprocess

from pathlib import Path

import pytest

from probe_build import compile_probe

PROBE_SRC = Path(__file__).with_name("rom_mode_probe.c")

# The probe's geometry and planted bytes, mirrored — it prints raw values and this file owns every
# claim about them. Kept as one dict so a claim added on one side without the other fails loudly.
SHIFTER_PEN0 = 0xFF8240
SHIFTER_RESOLUTION = 0xFF8260
EXPECTED = {
    "rom_mode_armed": 1,                            # osh_rom_window() took
    "ram_byte": 0x5A,                               # RAM below ram_end is still served from the image
    "psg_readback": 0x3C,                           # ...but $ff8800 answers the SEEDED register...
    "psg_select_did_not_reach_the_image": 0x99,     # ...and the decoy at that address is untouched
    "hw_write_count": 1,                            # a store to $ff8240 is ledgered...
    "hw_write_addr": SHIFTER_PEN0,
    "hw_write_value": 0x77,
    "hw_write_did_not_reach_the_image": 0,          # ...and dropped, not written into the image
    "modelled_io_unmodeled_reads": 0,              # a MODELLED port is not an unmodelled read...
    "unmodeled_io_value": 0,                       # ...while $ff8260 is still ANSWERED 0 (emu.run
                                                   # stays permissive; the harness refuses)...
    "unmodeled_io_reads": 1,                       # ...and counted, so a differential can refuse
    "unmodeled_io_first": SHIFTER_RESOLUTION,      # ...by naming the address
    "rom_stores": 1,                                # a store into the ROM window is counted...
    "rom_store_did_not_reach_the_image": 0,         # ...and changes nothing: ROM is read-only
    "trap_in_rom_mode_marker": 0x77,                # the image's OWN vector took the trap
    "trap_vector_untouched": 1,                     # ...and nothing patched it to restore afterwards
    "trap_off_rom_mode_marker": 0,                  # the control: the MODEL served it instead
}


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Build and run the probe once; return {claim: the value it printed}."""
    binary = compile_probe(PROBE_SRC, tmp_path_factory.mktemp("rom_mode"))
    out = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    return {name: int(value) for name, value in re.findall(r"^(\S+) (\d+)$", out, re.M)}


def test_the_probe_reports_every_claim(results):
    """Guard the fixture: a probe that stopped printing, or a parse that stopped matching, would
    make every assertion below vacuously pass."""
    assert set(results) == set(EXPECTED), (
        f"probe output and expectations disagree — only in the probe: "
        f"{sorted(set(results) - set(EXPECTED))}, only in EXPECTED: "
        f"{sorted(set(EXPECTED) - set(results))}")


@pytest.mark.parametrize("claim", sorted(EXPECTED))
def test_rom_mode_maps_the_address_space_the_way_the_model_needs(results, claim):
    assert results[claim] == EXPECTED[claim], (
        f"{claim}: the probe reported {results[claim]:#x}, not {EXPECTED[claim]:#x}")


def test_the_trap_pair_is_what_makes_the_claim(results):
    """The two trap cases run the SAME image and routine and must disagree — that difference is the
    whole of "ROM mode installs no trap model". Either case alone would pass against a shim that had
    lost the distinction in the other direction."""
    assert results["trap_in_rom_mode_marker"] != results["trap_off_rom_mode_marker"], (
        "the trap reached the same place with and without the ROM window installed — either the "
        "shim is patching the vector table in ROM mode, or it has stopped patching it at all")
