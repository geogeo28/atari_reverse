"""THE TRANSCRIBED TABLE (`include/transcribed.h`), held to everything that reads it or that it describes — for
every component whose hand-68000 ships as `.S` (the VDI and Line-A's `src/vdi/`, the AES's `src/aes/`).

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
* the C that still CALLS a transcribed C core is the list `transcription.C_CALLERS_OF_TRANSCRIBED_CORES` names, read
  out of the m68k build — and in the SHIPPED blob each of those calls reaches the core's generated glue, which
  refuses a core whose routine declares no contract it could follow;
* every staged caller a transcription row is entered through costs what both columns are net of;
* and an AES row's two constraints (the header's "AN AES ROW"), over the ROM routine's executed path: no Line-F word
  executed, and every return tail of the optimize layer it reaches in its own pinned region.
"""
import re
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

import pytest

from harness import BASE_IMAGE, _lib, addrs, emu, make_image

# Every battery, so every transcription row and every staged caller is registered before collection.
import test_boot_snapshot  # noqa: F401
import aes
import case
import routines
import transcription
import vdi
from layouts import WORD_BYTES
from opcodes import EXCEPTION_LINE_MASK, LINE_F

RECREATE = Path(__file__).resolve().parents[1]
KIT = RECREATE.parents[2] / "tools" / "recreate_kit"
sys.path.insert(0, str(RECREATE / "bench"))
import shipped_glue  # noqa: E402
import tier3  # noqa: E402
MAKE_LISTS = ("TRANSCRIBED_ENTRIES", "TRANSCRIBED_C_CORES", "TRANSCRIBED_SOURCES", "ALCYON_ENTRY_SOURCES")
# The GCC m68k ABI: D0/D1/A0/A1 are the callee's to change, and these the caller's to keep (A7 is SP) — the glue's own.
GCC_CALLEE_SAVED = shipped_glue.CALLEE_SAVED
# A register a row declares that its registered cases cannot show, and why. Only a routine whose cases
# must stand in for something the ROM does on target belongs here.
UNOBSERVED = {
    "vdi_rom_gemdos_call": ({"d2", "a2"}, "its cases take a RECORDING `trap #1` handler "
                                          "(`test_vdi_helpers_gemdos.py`); GEMDOS itself keeps only D3-D7/A3-A6"),
}
def _core(entry):
    return transcription.transcribed_core(entry)


@pytest.fixture(scope="module")
def make_lists():
    """`atari/target.mk`'s three lists, as make itself expands them."""
    probe = "".join(f"\t@echo {name}=$({name})\n" for name in MAKE_LISTS)
    makefile = f"RECREATE := {RECREATE}\nKIT := {KIT}\ninclude {RECREATE}/atari/target.mk\nall:\n{probe}"
    out = subprocess.run(["make", "-s", "-f", "-", "all"], input=makefile, capture_output=True, text=True,
                         check=True).stdout
    return {name: values.split() for name, _, values in (line.partition("=") for line in out.splitlines())}


def test_the_build_contract_is_the_table(make_lists):
    assert make_lists["TRANSCRIBED_ENTRIES"] == list(transcription.TRANSCRIBED), (
        "atari/target.mk's `sed` and test/transcription.py's parser read include/transcribed.h differently")
    assert make_lists["TRANSCRIBED_C_CORES"] == [_core(entry) for entry in transcription.TRANSCRIBED], (
        "the ROM build would exclude other C than the cores the table's entries are twins of")


def test_every_s_entry_is_a_row_and_every_row_an_s_entry(make_lists):
    defined = transcription.globl_entries(make_lists["TRANSCRIBED_SOURCES"])
    assert defined == set(transcription.TRANSCRIBED), (
        f"`.S` entries with no row (shipped with nothing gating them): {sorted(defined - set(transcription.TRANSCRIBED))}; "
        f"rows with no `.S` entry: {sorted(set(transcription.TRANSCRIBED) - defined)}")


def test_the_alcyon_entries_are_glue_tier3_counts(make_lists):
    """The target-only Alcyon entries (`src/aes/obdraw.S`, `src/aes/wmupdate.S`) are NOT transcriptions — no row, kept
    out of the `.S` list above — and their `.globl`s are exactly the glue Tier 3 counts as such (`bench/tier3.py`,
    ALCYON_ENTRIES) — which Tier 3 derives from the list as `test/transcription.py` reads the makefile's line, held here
    to make's own expansion."""
    sources = make_lists["ALCYON_ENTRY_SOURCES"]
    assert sources and not set(sources) & set(make_lists["TRANSCRIBED_SOURCES"])
    assert sources == transcription.alcyon_entry_sources(), "test/transcription.py reads ALCYON_ENTRY_SOURCES otherwise"
    entries = transcription.globl_entries(sources)
    assert entries == set(tier3.ALCYON_ENTRIES) and not entries & set(transcription.TRANSCRIBED)


@pytest.mark.parametrize("entry", list(transcription.TRANSCRIBED))
def test_each_row_names_a_rom_routine_a_c_core_and_both_blob_entries(entry):
    assert hasattr(addrs, transcription.transcription_routine(entry))
    assert hasattr(_lib, _core(entry)), f"the host build has no C core {_core(entry)} — Tier 1 proves nothing"
    assert transcription.bench().entry(entry) and transcription.bench().entry(_core(entry))


def _changed_callee_saved(entry):
    """The callee-saved registers the ROM routine leaves changed over the entry's registered `.S` rows."""
    changed = set()
    for _label, symbol, caller_at, regs, pokes, _cost, io_seed in transcription.TRANSCRIPTIONS:
        if symbol == entry:
            _final, _writes, left = emu.run(make_image(pokes), caller_at, regs, io_seed=io_seed)
            changed |= {name for name in GCC_CALLEE_SAVED if left[name] != regs[name]}
    return changed


@pytest.mark.parametrize("entry", list(transcription.TRANSCRIBED))
def test_each_row_declares_the_callee_saved_registers_the_rom_leaves_changed(entry):
    """Measured on the ROM routine rather than read off the `.S`: the transcription relation already
    holds the `.S` to the ROM's whole register file on these cases, so the ROM's run answers for both."""
    declared = set(transcription.TRANSCRIBED[entry])
    assert declared <= set(GCC_CALLEE_SAVED), f"{entry} declares a register the ABI already lets it change"
    unobserved, _why = UNOBSERVED.get(entry, (set(), ""))
    assert declared == _changed_callee_saved(entry) | unobserved, (
        f"{entry} declares {sorted(declared)}, but the ROM leaves {sorted(_changed_callee_saved(entry))} changed "
        f"over its registered cases{f' (and {sorted(unobserved)} unobservable here)' if unobserved else ''}")


def test_the_c_callers_of_a_transcribed_core_are_the_ones_the_door_names():
    """Read out of the m68k build, where the compiler has said which calls it made: every reference to a
    transcribed C core from a function outside the table — the list the shipped build's glue is made for."""
    graph = transcription.call_graph(transcription.BENCH_ELF)
    assert transcription.callers_of_transcribed_cores(graph) == transcription.C_CALLERS_OF_TRANSCRIBED_CORES


# Two `static` functions of ONE name in two files (and a split piece of one of them): the graph is keyed by name,
# so without the qualification their bodies would merge and each would appear to call what the other calls.
FIRST_AT, SECOND_AT, SPLIT_AT, CALLEE_AT, OTHER_AT = 0x40000, 0x40100, 0x40200, 0x40300, 0x40400
SHARED_NAME_LISTING = f"""
{FIRST_AT:08x} <outline>:
   {FIRST_AT:x}:\t6100 02fe      \tbsrw {CALLEE_AT:x} <callee>
{SECOND_AT:08x} <outline>:
   {SECOND_AT:x}:\t4eb9 0004 0200 \tjsr {SPLIT_AT:x} <outline.part.0>
{SPLIT_AT:08x} <outline.part.0>:
   {SPLIT_AT:x}:\t4eb9 0004 0404 \tjsr {OTHER_AT + 4:x} <other+0x4>
{CALLEE_AT:08x} <callee>:
   {CALLEE_AT:x}:\t4e75           \trts
{OTHER_AT:08x} <other>:
   {OTHER_AT:x}:\t4eb9 0004 0100 \tjsr {SECOND_AT:x} <outline>
"""


def test_the_call_graph_keeps_two_functions_of_one_name_apart():
    graph = transcription.graph_of_listing(SHARED_NAME_LISTING, {}, {})
    assert graph == {f"outline@{FIRST_AT:x}": {"callee"}, f"outline@{SECOND_AT:x}": {f"outline@{SPLIT_AT:x}"},
                     f"outline@{SPLIT_AT:x}": {"other"}, "callee": set(), "other": {f"outline@{SECOND_AT:x}"}}


# `TRANSCRIBED_CORE` on the line before a definition: the attribute, then the return type and the name.
_MARKED_DEFINITION = re.compile(r"^TRANSCRIBED_CORE\n[a-z][\w ]*?\b(\w+)\(", re.MULTILINE)


def test_every_transcribed_core_is_defined_as_one():
    """Without the attribute GCC may inline a core into its caller, where no link-time glue reaches it:
    the shipped build would go on running the C, and the caller pairs above would name the wrong call."""
    marked = {name for source in (RECREATE / "src").glob("*/*.c")
              for name in _MARKED_DEFINITION.findall(source.read_text())}
    assert marked == set(transcription.TRANSCRIBED_CORES), (
        f"cores defined without TRANSCRIBED_CORE: {sorted(set(transcription.TRANSCRIBED_CORES) - marked)}; "
        f"marked functions no row names: {sorted(marked - set(transcription.TRANSCRIBED_CORES))}")


def test_in_the_shipped_configuration_every_called_core_is_its_glue():
    """The shipped blob (`build/bench_shipped/`): each call a C caller makes of a core still names the core,
    and that name is now the GENERATED thunk, whose one reference is the core's `.S` entry — not the C body,
    which the weak attribute let the thunk displace."""
    graph = transcription.call_graph(transcription.SHIPPED_ELF)
    assert transcription.callers_of_transcribed_cores(graph) == transcription.C_CALLERS_OF_TRANSCRIBED_CORES
    for core in sorted({core for _caller, core in transcription.C_CALLERS_OF_TRANSCRIBED_CORES}):
        assert graph[core] == {transcription.TRANSCRIBED_CORES[core]}, (
            f"{core} in the shipped blob references {sorted(graph[core])}, not its `.S` entry alone — the "
            f"call links to the C body rather than to bench/shipped_glue.py's thunk")


def _table_row(monkeypatch, routine):
    """`routine` made a row of the table for this test alone: its `.S` entry, destroying nothing. Answers its core."""
    entry, core = transcription.transcription_symbol(routine), routines.core_symbol(routine)
    monkeypatch.setitem(transcription.TRANSCRIBED, entry, ())
    monkeypatch.setitem(transcription.TRANSCRIBED_CORES, core, entry)
    return core


def test_the_glue_refuses_an_aes_core_with_no_contract_rather_than_gluing_a_vdi_function(monkeypatch):
    """An AES routine has an `_OPCODE` sibling in `addrs.h` just as a VDI function does, and is no VDI function: a
    transcribed AES core no register contract or Alcyon signature declares is REFUSED, where the thunk shape keyed on
    the sibling alone would have entered its `.S` with nothing. A VDI function of the table is still glued as one."""
    uncontracted = next(name for name in sorted(dir(addrs))
                        if routines.prefix_of(name) == routines.AES_PREFIX and hasattr(addrs, name + "_OPCODE")
                        and name not in vdi.PRIMITIVES and name not in vdi.ALCYON)
    with pytest.raises(LookupError, match="declares no contract"):
        shipped_glue.thunk(_table_row(monkeypatch, uncontracted))
    assert "VDI function" in shipped_glue.thunk(_table_row(monkeypatch, "VDI_ROM_VS_COLOR"))[0]


def test_the_declarations_compile_and_refuse_a_plain_call():
    """The header declares each entry as a LABEL: its address is usable, a C call of it is not."""
    flags = ["m68k-elf-gcc", "-m68000", "-ffreestanding", "-fsyntax-only", "-Wall", "-Werror", "-x", "c", "-",
             f"-I{RECREATE / 'atari' / 'shim_include'}", f"-I{RECREATE / 'include'}", f"-I{KIT / 'include'}"]
    addresses = " + ".join(f"(unsigned long){entry}" for entry in transcription.TRANSCRIBED)
    source = f'#include "transcribed.h"\nunsigned long every_entry(void) {{ return {addresses}; }}\n'
    assert subprocess.run(flags, input=source, capture_output=True, text=True).returncode == 0
    call = f'#include "transcribed.h"\nvoid call(void) {{ {next(iter(transcription.TRANSCRIBED))}(); }}\n'
    assert subprocess.run(flags, input=call, capture_output=True, text=True).returncode != 0


def test_a_relocation_no_pinned_region_holds_is_refused():
    """A battery hands `assert_transcribed` its WHOLE relocation map and the comparator cuts it per region, so a
    relocation left over after a region moved — in no pinned region at all — is refused rather than filtered away."""
    region = transcription.every_pinned_region()[0]
    stray = {addrs.ROM_BASE: transcription.Relocated(transcription.PC_RELATIVE, region.anchor, "a region that moved")}
    assert not any(pinned.lo <= addrs.ROM_BASE < pinned.hi for pinned in transcription.every_pinned_region())
    with pytest.raises(AssertionError, match=f"relocation\\(s\\) at \\${addrs.ROM_BASE:x} lie in no pinned region"):
        transcription.assert_transcribed(region, relocated=stray)


@pytest.mark.parametrize("caller", transcription.CALLERS, ids=lambda caller: f"{caller.at:#x}")
def test_every_staged_caller_costs_what_both_columns_are_net_of(caller):
    transcription.assert_caller_cost(caller)


# ---- an AES row's two constraints (`include/transcribed.h`, "AN AES ROW") -------------------------------------------
# Both are about the ROM routine's EXECUTED PATH, read off the oracle's cycle-per-PC profile over the row's cases: a
# region may carry another routine's Line-F words as bytes (the span from rc_intersect to the tails holds four) so
# long as no path executes one — and an executed word is an instruction, so a Line-F word there is a call or a return,
# never an immediate that happens to read `$Fxxx` (`cmp.w #-1` at $fed04a).
# The optimize layer's shared return tails: every hand-68000 helper that answers a word leaves by a branch to one of
# them — the two answers, and the bare `rts` that answers D0 as left (strlen's `beq.w`).
AES_RETURN_TAILS = (addrs.AES_ROM_RC_RETURN_FALSE, addrs.AES_ROM_RC_RETURN_TRUE, addrs.AES_ROM_RC_RETURN_D0)
_AES_ENTRY_PREFIX = routines.AES_PREFIX.lower()
Run = namedtuple("Run", "entry regs pokes io_seed")


def _executed_rom_words(runs):
    """Every ROM word address the oracle executes an instruction at over `runs`, from its profile."""
    emu.prof_enable()
    emu.prof_reset()
    try:
        for run in runs:
            emu.run(make_image(run.pokes), run.entry, dict(run.regs), io_seed=run.io_seed)
        return {at for at in range(addrs.ROM_BASE, addrs.ROM_BASE + addrs.ROM_BYTES, WORD_BYTES)
                if emu.prof_cycles(at, at + WORD_BYTES)}
    finally:
        emu.prof_enable(False)


def assert_aes_row_path(entry, region, runs):
    """`entry`'s ROM path over `runs` executes no Line-F word — which would run the ROM's code through the handler's
    table from inside the blob — and every return tail it reaches lies in its pinned `region`."""
    executed = _executed_rom_words(runs)
    line_f = sorted(at for at in executed if case.word_in(BASE_IMAGE, at) & EXCEPTION_LINE_MASK == LINE_F)
    assert not line_f, f"{entry}'s path executes Line-F words at {', '.join(f'${at:x}' for at in line_f)}"
    stray = [tail for tail in AES_RETURN_TAILS if tail in executed and not region.lo <= tail < region.hi]
    assert not stray, (f"{entry} reaches the return tail(s) {', '.join(f'${tail:x}' for tail in stray)} outside its "
                       f"region ${region.lo:x}..${region.hi:x} — each branch there would be a relocation into bytes "
                       f"no battery pins")


def _transcription_runs(entry):
    """The ROM side of `entry`'s registered `.S` rows, entered at their staged caller."""
    return [Run(caller_at, regs, pokes, io_seed)
            for _label, symbol, caller_at, regs, pokes, _cost, io_seed in transcription.TRANSCRIPTIONS if symbol == entry]


def test_every_aes_row_executes_no_line_f_and_holds_the_return_tails_it_reaches():
    """Over the table's AES rows: every transcribed AES routine, over its registered `.S` rows. The tests below are
    the check's reds."""
    for entry in (entry for entry in transcription.TRANSCRIBED if entry.startswith(_AES_ENTRY_PREFIX)):
        routine = getattr(addrs, transcription.transcription_routine(entry))
        region, = (region for region in transcription.every_pinned_region() if region.lo <= routine < region.hi)
        assert_aes_row_path(entry, region, _transcription_runs(entry))


def _registered_runs(core):
    """The ROM side of the AES battery's priced rows of `core` — real routines over real cases, for the reds."""
    return [Run(entry, regs, pokes, io_seed)
            for name, entry, regs, pokes, _psg, io_seed, _schedule in aes.CASES if name.startswith(f"{core}, ")]


# The planned layout (`../README.md`, "An AES `.S`"): rc_intersect with the tails, four Line-F calls inside as bytes.
RC_INTERSECT_WITH_THE_TAILS = transcription.Region(addrs.AES_ROM_RC_INTERSECT, addrs.AES_ROM_RC_RETURN_TRUE + 6,
                                                   "aes_rom_rc_intersect")
RC_INTERSECT_ALONE = RC_INTERSECT_WITH_THE_TAILS._replace(hi=addrs.AES_ROM_RC_RETURN_FALSE)


def test_a_path_through_the_tails_pinned_with_them_is_accepted_and_one_pinned_apart_is_refused():
    runs = _registered_runs("aes_rc_intersect")
    assert_aes_row_path("aes_rom_rc_intersect", RC_INTERSECT_WITH_THE_TAILS, runs)
    with pytest.raises(AssertionError, match=r"return tail\(s\) \$fed066, \$fed06a, \$fed06e outside"):
        assert_aes_row_path("aes_rom_rc_intersect", RC_INTERSECT_ALONE, runs)


def test_an_alcyon_routine_s_path_is_refused_for_its_line_f_return():
    """get_par is Alcyon: it returns through a `$F001|m` word ($fed3bc), which no byte-pinned `.S` may execute."""
    get_par = transcription.Region(addrs.AES_ROM_GET_PAR, addrs.AES_ROM_GET_PAR + 0x40, "aes_rom_get_par")
    with pytest.raises(AssertionError, match=r"executes Line-F words at \$fed3bc"):
        assert_aes_row_path("aes_rom_get_par", get_par, _registered_runs("aes_get_par"))
