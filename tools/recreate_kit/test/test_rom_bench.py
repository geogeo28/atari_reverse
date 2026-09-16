"""`rom_bench.py`'s decidable parts: where the blob may be declared, what it spans, and the
arithmetic every Tier 3 ratio is divided by.

The runner itself needs a bound ROM project — a real ROM, a captured snapshot and a cross-compiled
blob — and this directory deliberately binds none (`test_rom_binding.py`'s note). What CAN be pinned
here is everything that decides a number before a 68000 executes anything, and each of these is a
mistake that would otherwise be invisible: a `bench_base` read as a string, a span measured from the
flat binary so a core's `.bss` falls outside every check, a ratio that forgot to take the oracle's
entry overhead off both sides. The end-to-end proof is the project's own
(`projects/tos102us/recreate/test/test_tier3.py`), which runs both builds over a real case.
"""
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # reverse/tools, so `recreate_kit` imports
from recreate_kit import project, rom_bench   # noqa: E402  (only importable after the path insert)

KIT = Path(__file__).resolve().parents[1]
ENTRY_PROBE = KIT / "bench" / "entry_probe.c"

# A ROM project.toml's ROM keys, enough to write one out — the values are never dereferenced here,
# because `rom_bench.bench_base` reads ONE key and binds nothing.
ROM_KEYS = """name = "example"
names = "../names.txt"
lib = "build/libexample.so"
rom = "rom.img"
rom_base = 0xfc0000
snapshot = "build/boot_ram.bin"
stack_top = 0x80000
image_size = 0x1000000
"""


def _project_toml(tmp_path, bench_base=None):
    text = ROM_KEYS + ("" if bench_base is None else f"bench_base = {bench_base}\n")
    (tmp_path / project.CONFIG_NAME).write_text(text)
    return tmp_path


def test_a_project_without_the_key_builds_no_blob(tmp_path):
    """The empty string is what kit.mk tests: no `bench_base`, no rule, no prerequisite — exactly as
    a project without a `src/asm/` gets no twins."""
    assert rom_bench.bench_base(_project_toml(tmp_path)) == ""


def test_the_key_comes_back_as_the_hex_the_linker_takes(tmp_path):
    assert rom_bench.bench_base(_project_toml(tmp_path, "0x30000")) == "0x30000"


# A negative address is spelt in decimal because TOML has no negative hex literal — the
# refusal under test is `project._address`'s, not the parser's.
@pytest.mark.parametrize("value", ("\"0x30000\"", "0x30001", "0", "-196608", "true"))
def test_a_bench_base_that_is_not_a_positive_even_address_is_refused(tmp_path, value):
    """`project._address`'s rule, reached through this door too: a quoted address is the plausible
    hand-edit, and an odd one is an address a 68000 cannot fetch the blob's instructions from."""
    with pytest.raises((TypeError, ValueError), match="bench_base"):
        rom_bench.bench_base(_project_toml(tmp_path, value))


def test_it_reads_the_key_without_binding_the_project(tmp_path):
    """The reason it opens the file itself instead of asking `project.current()`: make evaluates this
    on every invocation, including the `make snapshot` that CAPTURES the snapshot a binding insists
    already exists. Neither the ROM nor the snapshot above is a real file."""
    assert not (tmp_path / "rom.img").exists()
    assert rom_bench.bench_base(_project_toml(tmp_path, "0x30000")) == "0x30000"


def test_a_prg_project_is_refused_by_name():
    """The mirror of `asm_twin._refuse_in_rom_mode`, and the message has to say where to go instead:
    a .PRG project HAS a numerator, it is just a different arrangement (the recon in its own memory
    with the game image beside it)."""
    with pytest.raises(RuntimeError, match="bench_tier"):
        rom_bench._refuse_off_rom_mode(SimpleNamespace(name="joust", rom=None))


def test_a_rom_project_is_not_refused():
    """The control: without it the case above would pass on a function that refused everything."""
    rom_bench._refuse_off_rom_mode(SimpleNamespace(name="tos102us", rom=Path("rom.img")))


# ---- the span the blob owns ---------------------------------------------------------------------

LINK_BASE = 0x30000
# A `.bss` big enough that measuring the span from the flat binary instead of the section map would
# be off by more than any rounding could excuse.
BSS_BYTES = 0x4000


@pytest.fixture(scope="module")
def cross_elf(tmp_path_factory):
    """The kit's own entry probe plus a lump of `.bss`, linked at LINK_BASE.

    Skips rather than fails without the cross toolchain, which is `test_entry_state.py`'s convention
    for a tool a bare checkout need not have — but the PROJECT suite that uses this for real fails
    instead, because there a missing toolchain means a Tier 3 row nobody measured.
    """
    if not shutil.which("m68k-elf-gcc"):
        pytest.skip("m68k-elf-gcc is not installed; the cross build is what this pins")
    out = tmp_path_factory.mktemp("rom_bench") / "bench.elf"
    source = out.with_name("bss.c")
    source.write_text(f"unsigned char scratch[{BSS_BYTES}];\n"
                      f"unsigned char *rom_bench_scratch(void) {{ return scratch; }}\n")
    subprocess.run(["m68k-elf-gcc", "-m68000", "-O2", "-ffreestanding", "-nostdlib",
                    "-Wl,--build-id=none", "-Wl,-e0", f"-Wl,-Ttext={LINK_BASE:#x}",
                    str(ENTRY_PROBE), str(source), "-o", str(out)], check=True)
    return out


def test_the_span_starts_where_the_blob_is_linked(cross_elf):
    lo, _hi = rom_bench._allocated_span(cross_elf)
    assert lo == LINK_BASE


def test_the_span_covers_bss_which_the_flat_binary_does_not(cross_elf):
    """The case the section map exists for. `.bss` is ALLOCATED and carries no bytes, so a span
    measured from `objcopy`'s output would leave a core's zeroed statics outside the "is this RAM
    empty?" vet and INSIDE the image comparison, where they would read as the reconstruction
    diverging from the original."""
    lo, hi = rom_bench._allocated_span(cross_elf)
    flat_bin = cross_elf.with_suffix(".bin")
    subprocess.run(["m68k-elf-objcopy", "-O", "binary", str(cross_elf), str(flat_bin)], check=True)
    assert hi - lo >= BSS_BYTES
    assert hi - lo > flat_bin.stat().st_size, (
        "the flat binary is as long as the allocated span, so this ELF has no `.bss` and the case "
        "is vacuous")


def test_the_entry_probe_is_in_the_blob_under_the_name_rom_bench_asks_for(cross_elf):
    """Every ratio is net of an overhead measured on THIS symbol, so a rename that made it
    unreachable would leave the subtraction silently un-made."""
    symbols = rom_bench.elf_symbols(cross_elf)
    assert rom_bench.ENTRY_PROBE_SYMBOL in symbols, (
        f"{ENTRY_PROBE.name} does not define {rom_bench.ENTRY_PROBE_SYMBOL}; what it has: "
        f"{sorted(symbols)}")


# ---- the arithmetic every ratio is -------------------------------------------------------------

OVERHEAD = (1, 40)                     # the reset observation, as the project's suite pins it


def test_the_ratio_takes_the_entry_overhead_off_both_sides():
    """The whole reason the overhead is measured at all. Raw, these two are 540/840 = 0.643; net of
    the entry they are 500/800 = 0.625 — a 3% difference on one small routine, all of it in the
    lenient direction, which is how a bar stops being one."""
    measured = rom_bench.Measurement((None, 840), (None, 540), OVERHEAD)
    assert measured.ratio == pytest.approx(500 / 800)


def test_a_staged_entry_comes_off_the_original_s_column_alone():
    """What a case spent REACHING the routine is not what the routine cost.

    A handler the machine DISPATCHES cannot be entered by `emu.run` directly, so its case enters at
    a trampoline it staged; our build is entered at the symbol and pays none of it. Leaving the
    trampoline in the denominator flatters the row — here 840 raw against 540 is 0.625 net, and
    taking the entry's 24 cycles off the original alone gives 0.649 over the same measurement.
    """
    staged = (2, 24)
    measured = rom_bench.Measurement((10, 840), (8, 540), OVERHEAD, staged)
    assert (measured.original_insns, measured.original_cycles) == (8, 816)
    assert (measured.recreate_insns, measured.recreate_cycles) == (8, 540)
    assert measured.ratio == pytest.approx(500 / 776)


def test_no_staged_entry_leaves_a_measurement_exactly_as_it_was():
    """...so every row that is entered at its own address reads as it always did."""
    measured = rom_bench.Measurement((10, 840), (8, 540), OVERHEAD)
    assert (measured.original_insns, measured.original_cycles) == (10, 840)
    assert measured.ratio == pytest.approx(500 / 800)


def test_a_cost_at_or_below_the_entry_overhead_is_refused():
    """Not a fast function: a run that executed nothing — a wrong entry symbol, a blob that was never
    staged — and a ratio computed from it would report that as a number."""
    with pytest.raises(AssertionError, match="executed nothing"):
        rom_bench.Measurement((None, 840), (None, OVERHEAD[1]), OVERHEAD).ratio


# One exception handler's whole call, as the worked project measures it: a `Bios(Drvmap)` through the
# dispatcher costs the ORIGINAL 642 cycles, of which 40 are the reset observation and 106 are the
# CALLER the case had to stage — the same seven instructions on both sides, because a handler cannot
# be entered any other way. What is left, 496, is the dispatcher and the leaf it called.
SHARED_CALLER = (7, 106)
WHOLE_CALL_CYCLES = 642
DISPATCHER_CYCLES = WHOLE_CALL_CYCLES - OVERHEAD[1] - SHARED_CALLER[1]
# ...and a 12% regression in that dispatcher, which is the size of change this subtraction exists to
# make visible: rounded to whole cycles, as a 68000 counts them.
REGRESSION_FRACTION = 0.12
REGRESSED_CYCLES = WHOLE_CALL_CYCLES + round(REGRESSION_FRACTION * DISPATCHER_CYCLES)
PROJECT_BAR = 1.10                      # projects/tos102us/recreate: `tier3.TIER3_FUNCTION_BAR`


def test_a_shared_entry_comes_off_BOTH_columns():
    """The opposite subtraction to `staged_entry`, and the one a transcription's row needs.

    Both sides really do run the staged caller, so its cycles sit in both columns — and a constant
    in both columns drags the ratio towards 1.00 exactly as the entry overhead does. This is that
    with the numbers on it: a 12% regression inside the dispatcher itself measures UNDER the
    project's 1.10 bar while the caller is left in, and over it once the caller comes off.
    """
    left_in = rom_bench.Measurement((0, WHOLE_CALL_CYCLES), (0, REGRESSED_CYCLES), OVERHEAD)
    assert left_in.ratio <= PROJECT_BAR, (
        "the premise of this test has moved: with the shared caller left in both columns, a 12% "
        "dispatcher regression was supposed to hide under the bar")

    netted = rom_bench.Measurement((0, WHOLE_CALL_CYCLES), (0, REGRESSED_CYCLES), OVERHEAD,
                                   shared_entry=SHARED_CALLER)
    assert netted.original_net == DISPATCHER_CYCLES
    assert netted.ratio == pytest.approx(1 + REGRESSION_FRACTION, abs=0.005)
    assert netted.ratio > PROJECT_BAR, (
        f"a {REGRESSION_FRACTION:.0%} regression in the dispatcher measures {netted.ratio:.3f}x, "
        f"which is not over the {PROJECT_BAR} bar — the shared caller is not coming off both "
        f"columns, and every transcription row is being read as 1.01x whatever it costs")


def test_a_cost_at_or_below_the_shared_entry_is_refused_too():
    """A `shared_entry` naming a caller the case did not stage would make a run look like nothing,
    and the same refusal has to catch it: otherwise the ratio divides by a negative number."""
    with pytest.raises(AssertionError, match="executed nothing"):
        rom_bench.Measurement((0, 140), (0, 400), OVERHEAD, shared_entry=SHARED_CALLER).ratio


# ---- the two comparisons that have no image behind them -----------------------------------------

@pytest.mark.parametrize("returns, ours, original, differs", (
    (4, 0x0040_5AE3, 0x0040_5AE3, False),
    (4, 0x0040_5AE3, 0x0040_5AE2, True),
    # The measured shape: GCC returns a `uint8_t` in the low byte and leaves the caller's high word
    # alone, where the ROM's own `moveq #0,d0` cleared it. Comparing the whole register would red
    # every correct byte-returning core.
    (1, 0xCA11_0093, 0x0000_0093, False),
    (1, 0xCA11_0093, 0x0000_0094, True),
    # `void`: D0 is whatever the callee left on both sides, so there is nothing to compare.
    (0, 0xCA11_0093, 0x0000_0000, False),
))
def test_the_return_value_is_compared_at_the_width_the_signature_declares(returns, ours, original,
                                                                          differs):
    if not differs:
        rom_bench._vet_return_value("core", ours, original, returns)
        return
    with pytest.raises(AssertionError, match="returned"):
        rom_bench._vet_return_value("core", ours, original, returns)


def test_a_run_the_model_could_not_serve_is_refused_by_name_from_either_side():
    """Both sides make the access and only one of them is a surprise, so the refusal names the side.

    A run whose every tally is empty passes through, which is what keeps the check from being a
    constant — and EVERY tally that fired is named, because a run can trip several and a message
    naming one sends the reader off to fix it and hit the identical message again.
    """
    rom_bench._vet_no_refusals("the m68k build of core", {"read an I/O byte nothing serves": "",
                                                          "overflowed the PSG ledger": ""})
    with pytest.raises(AssertionError) as raised:
        rom_bench._vet_no_refusals("the ORIGINAL at 0xfc1510",
                                   {"read an I/O byte nothing serves": "1, the first at 0xff8260",
                                    "overflowed the PSG ledger": "7",
                                    "did not happen": ""})
    message = str(raised.value)
    assert "the ORIGINAL at 0xfc1510" in message and "0xff8260" in message and "7" in message
    assert "did not happen" not in message


def test_the_refusal_set_is_every_tally_the_harness_reads_after_a_run():
    """The shim's tallies, by NAME, against the set `_refusal_tallies` gathers.

    It cannot be driven without a machine — the counters are the oracle's, and this directory binds
    no project — so what is pinned is the set of `osh_*` counters the reader asks for: a shim that
    gains a refusal nobody reads here would leave a Tier 3 row measured over a run the model could
    not serve, and the row would be printed. This reddens when the two drift, which is the moment to
    decide rather than the moment to discover.
    """
    source = (KIT / "rom_bench.py").read_text()
    shim = (KIT / "oracle" / "shim.c").read_text()
    for counter in ("osh_psg_unseeded", "osh_psg_no_select", "osh_psg_unmodeled",
                    "osh_psg_mixed_paths", "osh_psg_dropped", "osh_hw_stale", "osh_hw_wide",
                    "osh_hw_reread", "osh_hw_dropped", "osh_hw_write_dropped",
                    "osh_io_unmodeled_reads", "osh_io_stale_reads", "osh_io_dropped"):
        assert counter in shim, f"{counter} is no longer a shim counter; this list has gone stale"
        assert counter in source, (
            f"rom_bench.py reads no {counter}, so a bench row can be measured over a run the model "
            f"could not serve — `harness.differential` refuses a Tier 1 case on exactly that tally")


# ---- where the blob may sit: the three refusals, and the tenancy ---------------------------------

STACK_BAND = ("the oracle's stack band", 0x7F100, 0x80100)
STAGING_BAND = ("the case staging band (`staging_base`)", 0x60000, 0x61000)
RAM_END = 0x100000


def test_a_blob_linked_somewhere_else_than_the_key_says_is_refused():
    """kit.mk passes `bench_base` to the linker, so a blob that came out elsewhere was built from
    another configuration — and the comparison would exclude a span the code is not in."""
    rom_bench._vet_link_address(LINK_BASE, LINK_BASE)
    with pytest.raises(AssertionError, match="bench_base"):
        rom_bench._vet_link_address(LINK_BASE, LINK_BASE + 2)


@pytest.mark.parametrize("blob", ((LINK_BASE, LINK_BASE + 0x1000),      # clear of both
                                  (0x20000, 0x30000)))                  # ...and right up to one
def test_bands_that_do_not_overlap_are_allowed(blob):
    """The control. Without it every case below would pass on a function that refused everything."""
    rom_bench._vet_bands([("the blob", *blob), STACK_BAND, STAGING_BAND], RAM_END)


@pytest.mark.parametrize("blob, overlaps", (
    ((0x7F000, 0x7F200), "stack"),          # into the stack band, where the run's frame lands
    ((0x5F000, 0x60800), "staging"),        # ...and into the band a case stages its buffers in
    ((0x30000, 0x70000), "staging"),        # ...and a blob that grew across both
))
def test_a_blob_that_overlaps_another_tenant_of_the_window_is_refused(blob, overlaps):
    """Whichever band is written second wins and neither says so: the run's own frame over the
    blob's code, or a case's buffer over it."""
    with pytest.raises(AssertionError, match="overlaps") as raised:
        rom_bench._vet_bands([("the blob", *blob), STACK_BAND, STAGING_BAND], RAM_END)
    assert overlaps in str(raised.value)


def test_a_band_past_the_end_of_ram_is_refused():
    """A 68000 has nothing to fetch there, and the oracle serves an off-image read as 0."""
    with pytest.raises(AssertionError, match="RAM"):
        rom_bench._vet_bands([("the blob", RAM_END - 0x100, RAM_END + 0x100)], RAM_END)


def test_a_blob_over_bytes_the_snapshot_holds_is_refused_and_names_the_first():
    """Staging code over the machine's own data measures a core against a machine that never
    existed, and those bytes are excluded from the comparison — so nothing else could see it."""
    snapshot = bytearray(0x100)
    rom_bench._vet_snapshot_is_empty(0x10, 0x40, snapshot)
    snapshot[0x21] = 0x4E
    with pytest.raises(AssertionError, match="0x21"):
        rom_bench._vet_snapshot_is_empty(0x10, 0x40, snapshot)


def test_an_entry_probe_with_a_prologue_is_refused_by_the_flag_that_would_cause_it():
    """Every ratio is net of an overhead measured on that function, so an empty function that cost
    more than its `rts` would hand every reconstruction the difference."""
    rom_bench._vet_probe_is_a_bare_rts("bench.elf", rom_bench.PROBE_INSNS, 56)
    with pytest.raises(AssertionError, match="fno-omit-frame-pointer"):
        rom_bench._vet_probe_is_a_bare_rts("bench.elf", rom_bench.PROBE_INSNS + 2, 84)


def test_the_makefile_writes_the_blob_where_this_module_looks_for_it():
    """kit.mk's `$(BENCH_DIR)`/`$(BENCH_ELF)`/`$(BENCH_BIN)` and this module's constants are two
    spellings of one arrangement — make cannot ask Python at the time it needs them, and Python
    cannot ask make — so a rename in either file has to fail HERE rather than leave `RomBench.require`
    reporting a blob nobody built."""
    makefile = (KIT / "kit.mk").read_text()
    for spelt in (f"BENCH_DIR := {rom_bench.BENCH_DIR.as_posix()}",
                  f"BENCH_ELF := $(BENCH_DIR)/{rom_bench.BENCH_ELF}",
                  f"BENCH_BIN := $(BENCH_DIR)/{rom_bench.BENCH_BIN}"):
        assert spelt in makefile, (
            f"kit.mk does not spell `{spelt}`, so it writes the blob somewhere rom_bench.py does "
            f"not read it — or reads it from somewhere make does not write")


# ---- TRANSCRIPTIONS: the `.S` cores, and the relation they are held to --------------------------
# A ROM project has routines that cannot be C on the target — an exception handler is entered with a
# 68000 exception frame and owes its caller a register file no compiler can promise — so it carries
# the original's own instruction sequence under `src/<component>/*.S`, and `measure_transcription`
# is how that is proved. What is decidable here is the build sweep that reaches such a file and the
# two refusals the stronger relation rests on; the end-to-end proof is the project's
# (`projects/tos102us/recreate/test/test_bios_trap.py`).

# The symbol the fixture's hand-written `.S` defines, and what its whole body is.
ASM_SYMBOL = "rom_bench_asm_probe"


def test_the_blob_build_sweeps_a_projects_assembly_beside_its_c(tmp_path):
    """One `m68k-elf-gcc` invocation over a `.c` and a `.S` together, which is what kit.mk's
    `$(BENCH_ELF)` rule is.

    The point is that the two land in ONE blob with one symbol table, because `RomBench.entry`
    resolves a transcription's entry out of the same table a C core's comes from — and that a `.S`
    (capital S) is preprocessed, so it may include the project's own `addrs.h` and name the ROM
    addresses it transcribes rather than spelling them twice.
    """
    if not shutil.which("m68k-elf-gcc"):
        pytest.skip("m68k-elf-gcc is not installed; the cross build is what this pins")
    asm = tmp_path / "probe.S"
    asm.write_text(f"#define PROBE_SYMBOL {ASM_SYMBOL}\n"
                   f"    .text\n    .globl PROBE_SYMBOL\nPROBE_SYMBOL:\n    rts\n")
    out = tmp_path / "bench.elf"
    subprocess.run(["m68k-elf-gcc", "-m68000", "-O2", "-ffreestanding", "-nostdlib",
                    "-Wl,--build-id=none", "-Wl,-e0", f"-Wl,-Ttext={LINK_BASE:#x}",
                    str(ENTRY_PROBE), str(asm), "-o", str(out)], check=True)
    symbols = rom_bench.elf_symbols(out)
    assert ASM_SYMBOL in symbols and rom_bench.ENTRY_PROBE_SYMBOL in symbols, (
        f"a `.S` and a `.c` did not link into one blob; what is there: {sorted(symbols)}")


def test_the_makefile_sweeps_assembly_into_the_blob():
    """...and that kit.mk actually makes that sweep, which is the half this file can only read.

    A project whose `.S` the wildcard missed fails at `RomBench.entry`, naming every symbol the blob
    DOES hold — so the behavioural half is the project's suite. This is here because the wildcard is
    one character away from being right and silently empty.
    """
    makefile = (KIT / "kit.mk").read_text()
    # BOTH DEPTHS, mirroring the `.c` sweep beside it: a project that keeps its cores at the top of
    # `src/` keeps its transcriptions there too, and either wildcard on its own is silently empty
    # for half the projects rather than an error for any of them.
    for sweep in ("$(wildcard src/*.S)", "$(wildcard src/*/*.S)"):
        assert sweep in makefile, (
            f"kit.mk's BENCH_SRC does not sweep `{sweep}`, so a ROM project's transcriptions at "
            f"that depth would be left out of the blob and every one of their rows would fail as a "
            f"missing symbol")


# The register file the two vets below are driven over: the 68000's, as the oracle reports it. It is
# NOT `CALLEE_SAVED_SEEDS`' names, and that is the whole point — those are d2-d7/a2-a6, and the
# registers this relation adds over `measure`'s are exactly the four outside them.
FAKE_REPORTED_REGS = tuple(f"d{number}" for number in range(8)) + \
                     tuple(f"a{number}" for number in range(7))


def _reported_regs_only():
    """An `emu` holding the one attribute the two register vets read (they `import emu` inside)."""
    return SimpleNamespace(REPORTED_REGS=FAKE_REPORTED_REGS)


def _entered_with():
    """...and a distinct value per register, so a failure names the one that moved."""
    return {name: 0x1000 + index for index, name in enumerate(FAKE_REPORTED_REGS)}


def test_a_transcriptions_case_must_name_every_register_it_enters_with(monkeypatch):
    """The whole-file comparison is only worth anything if both sides were entered the same way.

    A register the case left out enters as 0 on the original's side and as 0 on ours, agrees for
    that reason, and pins nothing — which is exactly the register a dropped `movem` entry hides in.
    """
    monkeypatch.setitem(sys.modules, "emu", _reported_regs_only())
    regs = _entered_with()
    rom_bench._vet_seeds_the_whole_file("bios_trap13", regs)      # a complete file is accepted
    del regs["d2"]
    with pytest.raises(AssertionError, match="d2"):
        rom_bench._vet_seeds_the_whole_file("bios_trap13", regs)


@pytest.mark.parametrize("register", ("d1", "d2", "a1", "a5"))
def test_a_transcription_is_held_to_the_whole_register_file(monkeypatch, register):
    """Including the ones a C core owes nobody. D1 and A1 are scratch under the m68k SysV ABI, so
    `measure`'s callee-saved check passes a build that leaves either of them elsewhere — and a
    dispatcher that did would hand its caller a different machine than the ROM does.
    """
    monkeypatch.setitem(sys.modules, "emu", _reported_regs_only())
    original = _entered_with()
    rom_bench._vet_register_file("bios_trap13", dict(original), original)
    ours = dict(original, **{register: original[register] ^ 1})
    with pytest.raises(AssertionError, match=register):
        rom_bench._vet_register_file("bios_trap13", ours, original)


def test_an_off_image_ledger_is_compared_in_order():
    """The only surface a core whose whole effect is a chip has: the same accesses in the wrong
    order is a different program, and both images are identical either way."""
    events = [(0, 7, 0x3F), (1, 7, 0x3F)]
    rom_bench._vet_ledger("core", "the ordered PSG accesses", list(events), events)
    with pytest.raises(AssertionError, match="ordered PSG accesses"):
        rom_bench._vet_ledger("core", "the ordered PSG accesses", list(reversed(events)), events)


# ---- the machine the m68k build is measured over -------------------------------------------------

# A machine small enough to hand a FAKE ORACLE: the blob low, the run's stack above it, and no ROM.
# The runner itself needs a bound ROM project and a built blob (see the module docstring), and what
# is under test below is one argument of one call — so the two oracle entry points are stood in for
# rather than driven, and `test_tier3.py` is what runs the real pair over a real case.
FAKE_IMAGE_BYTES = 0x1000
FAKE_BLOB_AT = 0x100
FAKE_BLOB = b"\x4e\x75"                 # `rts`: the bytes staged are a routine, so `vet_blob_intact`
FAKE_STACK_TOP = 0x800                  # ...has something to compare and the frame lands in RAM
FAKE_ENTRY = 0xFC0AAC                   # XBIOS Getrez, the row this case is about
# What that row's case DECLARES: the shifter byte Getrez reads and returns, in the 24-bit bus form
# `io_seed` is spelt in (TRAP_MODEL.md, Phase 15). Nothing serves it unless the run installs it, and
# an undeclared I/O read is answered a fabricated 0 — on both sides, so the second differential
# would compare two runs of a machine that does not exist.
FAKE_IO_SEED = {0xFF8260: 2}
# ...and one a case may declare through the SAME door that the Phase-7 NAMED SET owns: the MFP's
# GPIP, which an interrupt handler tests for the monitor and the ACIA line. `emu.seed_split` routes
# it into the hardware model, where the ORIGINAL's run installs it and it PERSISTS — so `run_bench`
# has no door for it and refuses one, and `rom_bench` has to hand our side only the other half.
FAKE_NAMED_ADDRESS = 0xFFFA01


class _QuietLib:
    """Every `osh_*` counter `_refusal_tallies` reads, all reporting nothing.

    A machine that refused nothing, so `measure` reaches the call this file is about rather than
    stopping at the vet — which is also the point: with the map installed, the real run is quiet
    here too, and without it the very first tally in that set fires.
    """

    def __getattr__(self, _name):
        return lambda *args: 0


# A wait the fake machine reports, in the shape both doors report one: the address the routine spins
# on and the reads each run made at it (os.h, "READ TRIGGERS"). A run with no schedule declares no
# read site at all, which is every row but the one that waits.
FAKE_WAIT_ADDRESS = 0x466
FAKE_WAIT_READS = 4


def _fake_wait(schedule):
    """`(the read sites, the reads at each)` a run of this fake machine reports for `schedule`."""
    if not schedule:
        return (), ()
    return (FAKE_WAIT_ADDRESS,), (FAKE_WAIT_READS,)


def _fake_emu(calls, bench_reads=None):
    """An `emu` holding just the surface `RomBench.measure` touches, recording what each door was
    handed as its declared I/O map and its schedule.

    `bench_reads` overrides what OUR side reports having read at the wait address — the shape of a
    target build whose loop ran a different number of times, which is the one thing a row over a
    wait has to be able to fail on.
    """
    def run(image, entry, regs, psg_seed=None, hw_seed=None, io_seed=None, schedule=None):
        calls.append(("emu.run", io_seed, schedule))
        sites, reads = _fake_wait(schedule)
        return image, [], {"d0": 2, "ninsns": 5, "cycles": 82,
                           "psg_events": [], "hw_events": [], "io_events": [], "hw_writes": [],
                           "sched_read_sites": sites, "sched_read_arrivals": reads}

    # `io_seed` and `schedule` are KEYWORD-ONLY here because they are keyword-only on the real
    # `run_bench`: a caller that passed one positionally would take another parameter's meaning, and
    # this mirror is what makes that fail here rather than in a project's bench run.
    def run_bench(mem, entry, arg0, sp, sentinel, max_insns=None, door=None, seed_regs=None, *,
                  io_seed=None, schedule=None):
        calls.append(("emu.run_bench", io_seed, schedule))
        sites, reads = _fake_wait(schedule)
        return {"d0": 2, "ninsns": 4, "cycles": 80, "regs": dict(rom_bench.CALLEE_SAVED_SEEDS),
                "sched_applied": len(schedule or ()),
                "sched_read_sites": sites, "sched_read_arrivals": bench_reads or reads}

    def seed_split(hw_seed, io_seed):
        """The real routing's contract, over a named set of one: `(named half, the rest)`."""
        named = {a: v for a, v in (io_seed or {}).items() if a == FAKE_NAMED_ADDRESS}
        if not named:
            return hw_seed, io_seed
        return {**(hw_seed or {}), **named}, {a: v for a, v in io_seed.items() if a not in named}

    return SimpleNamespace(run=run, run_bench=run_bench, seed_split=seed_split,
                           STACK_TOP=FAKE_STACK_TOP, SENTINEL=2,
                           REPORTED_REGS=tuple(rom_bench.CALLEE_SAVED_SEEDS), PSG_NREGS=16,
                           _LIB=_QuietLib(), hw_unseeded_addrs=lambda: (), _hw_addrs_of=lambda _m: (),
                           psg_events=lambda: [], hw_events=lambda: [], io_events=lambda: [],
                           hw_writes=lambda: [])


def _fake_harness():
    """...and the `harness` half: an empty image, and a comparison that finds nothing.

    The two byte counts are the kit's own (`emu.SENTINEL_SLOT_BYTES` + `STACK_ARGS_BYTES`), spelt
    here only so `_vet_stack_args_fit` has an argument area to measure against; what they bound is
    pinned where they are defined.
    """
    def make_image(pokes=None):
        image = bytearray(FAKE_IMAGE_BYTES)
        for addr, data in (pokes or {}).items():
            image[addr:addr + len(data)] = data
        return image

    return SimpleNamespace(make_image=make_image, diff_spans=lambda: ((0, FAKE_IMAGE_BYTES),),
                           differing_addresses=lambda left, right, spans, excluded: [],
                           SENTINEL_SLOT_BYTES=4, STACK_ARGS_BYTES=24)


def _unbound_bench():
    """A `RomBench` with the constructor skipped — it would want a project, a ROM and a built blob,
    and every field it sets that `measure` reads is set by hand here instead."""
    bench = rom_bench.RomBench.__new__(rom_bench.RomBench)
    bench.cfg = SimpleNamespace(image_size=FAKE_IMAGE_BYTES)
    bench.symbols = {"xbios_getrez": FAKE_ENTRY}
    bench.blob = FAKE_BLOB
    bench.base, bench.end = FAKE_BLOB_AT, FAKE_BLOB_AT + len(FAKE_BLOB)
    bench.overhead = OVERHEAD
    return bench


@pytest.mark.parametrize("io_seed", (FAKE_IO_SEED, None))
def test_both_sides_of_a_row_are_run_over_the_cases_own_declared_io_map(monkeypatch, io_seed):
    """The m68k build is served what the CASE declared, not what the run before it left installed.

    `emu.run_bench` takes the map per run, an empty declaration included, so a row measured under
    `-n auto` cannot read through another row's map either. Without this the XBIOS Getrez row is
    measured over a machine whose shifter answers the fabricated 0 that an undeclared I/O read gets
    — on both sides, which is why the image comparison and the return value would both vouch for it,
    and only the refusal tally says otherwise.
    """
    calls = []
    monkeypatch.setitem(sys.modules, "emu", _fake_emu(calls))
    monkeypatch.setitem(sys.modules, "harness", _fake_harness())
    _unbound_bench().measure(FAKE_ENTRY, "xbios_getrez", args=(0,), io_seed=io_seed, returns=1)
    assert calls == [("emu.run", io_seed, None), ("emu.run_bench", io_seed, None)]


def test_only_the_original_is_handed_the_part_of_the_map_the_named_set_owns(monkeypatch):
    """ONE DOOR, TWO MODELS, and the second model is installed on one side only.

    A case declares `$fffa01` and `$ff8260` in one `io_seed` — which of them Phase 7 happens to name
    is the kit's bookkeeping, not the case's. The named half belongs to the hardware model, which
    the ORIGINAL's `emu.run` arms and which persists between runs deliberately (a bench run clearing
    it would disarm an asm twin's), so `run_bench` refuses one outright rather than dropping it
    silently. Without the split here, a core that reads a named slot — an interrupt handler testing
    the MFP's GPIP is the first — could not be MEASURED at all: the row would die in the refusal
    instead of reporting a ratio.
    """
    calls = []
    monkeypatch.setitem(sys.modules, "emu", _fake_emu(calls))
    monkeypatch.setitem(sys.modules, "harness", _fake_harness())
    whole = {**FAKE_IO_SEED, FAKE_NAMED_ADDRESS: 0x80}
    _unbound_bench().measure(FAKE_ENTRY, "xbios_getrez", args=(0,), io_seed=whole, returns=1)
    assert calls == [("emu.run", whole, None), ("emu.run_bench", FAKE_IO_SEED, None)]


# ---- a row over a routine that WAITS: one list, both doors, and the count that separates them ----

# The case's own schedule, in the shape a bench row's must be: a READ trigger, because the address is
# the machine's while a PC belongs to one build (os.h, "READ TRIGGERS").
FAKE_SCHEDULE = ({"read": FAKE_WAIT_ADDRESS, "nth": FAKE_WAIT_READS,
                  "addr": FAKE_WAIT_ADDRESS, "width": 4, "value": 0x35E},)


def test_both_doors_are_handed_the_same_schedule():
    """The one declaration both runs take unchanged, and the reason it can be: an entry keyed to a
    READ of an address fires at the same moment in the ROM's instructions and in the compiled
    build's, where a PC would name one of them and nothing in the other."""
    calls = []
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(sys.modules, "emu", _fake_emu(calls))
        patch.setitem(sys.modules, "harness", _fake_harness())
        _unbound_bench().measure(FAKE_ENTRY, "xbios_getrez", args=(0,), returns=1,
                                 schedule=FAKE_SCHEDULE)
    assert calls == [("emu.run", None, FAKE_SCHEDULE), ("emu.run_bench", None, FAKE_SCHEDULE)]


def test_a_build_that_ran_a_different_wait_sinks_the_row(monkeypatch):
    """THE CROSS-CHECK, driven: our build reads the wait's address one time fewer than the ORIGINAL.

    Everything else about the two runs is identical here, which is not a convenience of the fake —
    it is the real situation. The agent's store is applied from the same list at both doors, so a
    build that spun a different number of times leaves the same image, the same return value, the
    same register file and the same streams. Without this comparison the row would be a cycle count
    with a second differential that could not fail.
    """
    monkeypatch.setitem(sys.modules, "emu", _fake_emu([], bench_reads=(FAKE_WAIT_READS - 1,)))
    monkeypatch.setitem(sys.modules, "harness", _fake_harness())
    with pytest.raises(AssertionError, match="did not run the original's wait") as raised:
        _unbound_bench().measure(FAKE_ENTRY, "xbios_getrez", args=(0,), returns=1,
                                 schedule=FAKE_SCHEDULE)
    assert f"{FAKE_WAIT_ADDRESS:#x}" in str(raised.value), (
        "the refusal does not name the address the two sides disagreed about")


def test_a_row_that_schedules_nothing_has_no_wait_to_compare(monkeypatch):
    """The control, and why the comparison costs the other rows nothing: a run with no schedule
    derives no read site, so both sides report nothing and the two agree by having nothing."""
    monkeypatch.setitem(sys.modules, "emu", _fake_emu([]))
    monkeypatch.setitem(sys.modules, "harness", _fake_harness())
    _unbound_bench().measure(FAKE_ENTRY, "xbios_getrez", args=(0,), returns=1)


@pytest.mark.parametrize("original, ours, differs", (
    ({0x466: 4}, {0x466: 4}, False),
    ({0x466: 4}, {0x466: 8}, True),          # the double-poller: two reads per iteration
    ({0x466: 4}, {}, True),                  # ...and a build that never read it at all
    ({}, {}, False),
))
def test_the_wait_comparison_is_per_address(original, ours, differs):
    """`_vet_same_wait` on its own, over the shapes a target build can have. Keyed by ADDRESS, so a
    run with two waits in it cannot balance one against the other."""
    o_regs = {"sched_read_sites": tuple(original), "sched_read_arrivals": tuple(original.values())}
    if not differs:
        rom_bench._vet_same_wait("core", o_regs, ours)
        return
    with pytest.raises(AssertionError, match="wait"):
        rom_bench._vet_same_wait("core", o_regs, ours)
