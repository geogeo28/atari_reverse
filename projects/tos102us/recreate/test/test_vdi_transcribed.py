"""THE TRANSCRIBED TABLE (`include/vdi/transcribed.h`), held to everything that reads it or that it describes.

The table is the one place the user's rule is applied — "port the hand-written 68000 to C first; where the
C measures over the 1.10 bar, SHIP a byte-pinned `.S`" — and three readers derive from it: Tier 3's (T)
rule (`test_tier3.py` gates that), the ROM build's contract (`atari/target.mk`), and the declarations a C
caller reaches an entry through. What this file pins is that the table cannot say one thing while the
tree does another:

* the MAKE lists are the table's rows, and the C cores are the entries less their `rom_`;
* every `.globl` of the `.S` sources is a row, and every row is one — a `.S` entry with no row would ship
  with nothing gating it, a row with no entry would carry C rows on a `.S` that does not exist;
* each row names a ROM routine, a host C core, and a blob entry for both;
* each row's REGISTER CONTRACT is the ROM's own, measured: the callee-saved registers the routine leaves
  changed over every registered `.S` case — which the transcription relation proves the `.S` leaves too;
* every C core is defined `TRANSCRIBED_CORE`, so it stays a call glue can replace;
* the C that still CALLS a transcribed C core is the list `vdi.C_CALLERS_OF_TRANSCRIBED_CORES` names, read
  out of the m68k build — and in the SHIPPED blob each of those calls reaches the core's generated glue;
* and every staged caller a transcription row is entered through costs what both columns are net of.
"""
import re
import subprocess
from pathlib import Path

import pytest

from harness import _lib, addrs, emu, make_image

# Every battery, so every transcription row and every staged caller is registered before collection.
import test_boot_snapshot  # noqa: F401
import vdi

RECREATE = Path(__file__).resolve().parents[1]
KIT = RECREATE.parents[2] / "tools" / "recreate_kit"
BENCH_ELF = RECREATE / "build" / "bench" / "bench.elf"
MAKE_LISTS = ("TRANSCRIBED_ENTRIES", "TRANSCRIBED_C_CORES", "TRANSCRIBED_SOURCES")
# The GCC m68k ABI: D0/D1/A0/A1 are the callee's to change, and these the caller's to keep (A7 is SP).
GCC_CALLEE_SAVED = ("d2", "d3", "d4", "d5", "d6", "d7", "a2", "a3", "a4", "a5", "a6")
# A register a row declares that its registered cases cannot show, and why. Only a routine whose cases
# must stand in for something the ROM does on target belongs here.
UNOBSERVED = {
    "vdi_rom_gemdos_call": ({"d2", "a2"}, "its cases take a RECORDING `trap #1` handler "
                                          "(`test_vdi_helpers_gemdos.py`); GEMDOS itself keeps only D3-D7/A3-A6"),
}
def _core(entry):
    return vdi.transcribed_core(entry)


@pytest.fixture(scope="module")
def make_lists():
    """`atari/target.mk`'s three lists, as make itself expands them."""
    probe = "".join(f"\t@echo {name}=$({name})\n" for name in MAKE_LISTS)
    makefile = f"RECREATE := {RECREATE}\nKIT := {KIT}\ninclude {RECREATE}/atari/target.mk\nall:\n{probe}"
    out = subprocess.run(["make", "-s", "-f", "-", "all"], input=makefile, capture_output=True, text=True,
                         check=True).stdout
    return {name: values.split() for name, _, values in (line.partition("=") for line in out.splitlines())}


def test_the_build_contract_is_the_table(make_lists):
    assert make_lists["TRANSCRIBED_ENTRIES"] == list(vdi.TRANSCRIBED), (
        "atari/target.mk's `sed` and test/vdi.py's parser read include/vdi/transcribed.h differently")
    assert make_lists["TRANSCRIBED_C_CORES"] == [_core(entry) for entry in vdi.TRANSCRIBED], (
        "the ROM build would exclude other C than the cores the table's entries are twins of")


def test_every_s_entry_is_a_row_and_every_row_an_s_entry(make_lists):
    globl = re.compile(r"^\s*\.globl\s+(\w+)", re.MULTILINE)
    defined = {name for source in make_lists["TRANSCRIBED_SOURCES"] for name in globl.findall(Path(source).read_text())}
    assert defined == set(vdi.TRANSCRIBED), (
        f"`.S` entries with no row (shipped with nothing gating them): {sorted(defined - set(vdi.TRANSCRIBED))}; "
        f"rows with no `.S` entry: {sorted(set(vdi.TRANSCRIBED) - defined)}")


@pytest.mark.parametrize("entry", list(vdi.TRANSCRIBED))
def test_each_row_names_a_rom_routine_a_c_core_and_both_blob_entries(entry):
    assert hasattr(addrs, vdi.transcription_routine(entry))
    assert hasattr(_lib, _core(entry)), f"the host build has no C core {_core(entry)} — Tier 1 proves nothing"
    assert vdi.bench().entry(entry) and vdi.bench().entry(_core(entry))


def _changed_callee_saved(entry):
    """The callee-saved registers the ROM routine leaves changed over the entry's registered `.S` rows."""
    changed = set()
    for _label, symbol, caller_at, regs, pokes, _cost, io_seed in vdi.TRANSCRIPTIONS:
        if symbol == entry:
            _final, _writes, left = emu.run(make_image(pokes), caller_at, regs, io_seed=io_seed)
            changed |= {name for name in GCC_CALLEE_SAVED if left[name] != regs[name]}
    return changed


@pytest.mark.parametrize("entry", list(vdi.TRANSCRIBED))
def test_each_row_declares_the_callee_saved_registers_the_rom_leaves_changed(entry):
    """Measured on the ROM routine rather than read off the `.S`: the transcription relation already
    holds the `.S` to the ROM's whole register file on these cases, so the ROM's run answers for both."""
    declared = set(vdi.TRANSCRIBED[entry])
    assert declared <= set(GCC_CALLEE_SAVED), f"{entry} declares a register the ABI already lets it change"
    unobserved, _why = UNOBSERVED.get(entry, (set(), ""))
    assert declared == _changed_callee_saved(entry) | unobserved, (
        f"{entry} declares {sorted(declared)}, but the ROM leaves {sorted(_changed_callee_saved(entry))} changed "
        f"over its registered cases{f' (and {sorted(unobserved)} unobservable here)' if unobserved else ''}")


def test_the_c_callers_of_a_transcribed_core_are_the_ones_the_door_names():
    """Read out of the m68k build, where the compiler has said which calls it made: every reference to a
    transcribed C core from a function outside the table — the list the shipped build's glue is made for."""
    assert vdi.callers_of_transcribed_cores(vdi.call_graph(BENCH_ELF)) == vdi.C_CALLERS_OF_TRANSCRIBED_CORES


# `TRANSCRIBED_CORE` on the line before a definition: the attribute, then the return type and the name.
_MARKED_DEFINITION = re.compile(r"^TRANSCRIBED_CORE\n[a-z][\w ]*?\b(\w+)\(", re.MULTILINE)


def test_every_transcribed_core_is_defined_as_one():
    """Without the attribute GCC may inline a core into its caller, where no link-time glue reaches it:
    the shipped build would go on running the C, and the caller pairs above would name the wrong call."""
    marked = {name for source in (RECREATE / "src").glob("*/*.c")
              for name in _MARKED_DEFINITION.findall(source.read_text())}
    assert marked == set(vdi.TRANSCRIBED_CORES), (
        f"cores defined without TRANSCRIBED_CORE: {sorted(set(vdi.TRANSCRIBED_CORES) - marked)}; "
        f"marked functions no row names: {sorted(marked - set(vdi.TRANSCRIBED_CORES))}")


def test_in_the_shipped_configuration_every_called_core_is_its_glue():
    """The shipped blob (`build/bench_shipped/`): each call a C caller makes of a core still names the core,
    and that name is now the GENERATED thunk, whose one reference is the core's `.S` entry — not the C body,
    which the weak attribute let the thunk displace."""
    graph = vdi.call_graph(vdi.SHIPPED_ELF)
    assert vdi.callers_of_transcribed_cores(graph) == vdi.C_CALLERS_OF_TRANSCRIBED_CORES
    for core in sorted({core for _caller, core in vdi.C_CALLERS_OF_TRANSCRIBED_CORES}):
        assert graph[core] == {vdi.TRANSCRIBED_CORES[core]}, (
            f"{core} in the shipped blob references {sorted(graph[core])}, not its `.S` entry alone — the "
            f"call links to the C body rather than to bench/shipped_glue.py's thunk")


def test_the_declarations_compile_and_refuse_a_plain_call():
    """The header declares each entry as a LABEL: its address is usable, a C call of it is not."""
    flags = ["m68k-elf-gcc", "-m68000", "-ffreestanding", "-fsyntax-only", "-Wall", "-Werror", "-x", "c", "-",
             f"-I{RECREATE / 'atari' / 'shim_include'}", f"-I{RECREATE / 'include'}", f"-I{KIT / 'include'}"]
    addresses = " + ".join(f"(unsigned long){entry}" for entry in vdi.TRANSCRIBED)
    source = f'#include "vdi/transcribed.h"\nunsigned long every_entry(void) {{ return {addresses}; }}\n'
    assert subprocess.run(flags, input=source, capture_output=True, text=True).returncode == 0
    call = f'#include "vdi/transcribed.h"\nvoid call(void) {{ {next(iter(vdi.TRANSCRIBED))}(); }}\n'
    assert subprocess.run(flags, input=call, capture_output=True, text=True).returncode != 0


@pytest.mark.parametrize("caller", vdi.CALLERS, ids=lambda caller: f"{caller.at:#x}")
def test_every_staged_caller_costs_what_both_columns_are_net_of(caller):
    vdi.assert_caller_cost(caller)
