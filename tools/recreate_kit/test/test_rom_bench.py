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


def test_a_cost_at_or_below_the_entry_overhead_is_refused():
    """Not a fast function: a run that executed nothing — a wrong entry symbol, a blob that was never
    staged — and a ratio computed from it would report that as a number."""
    with pytest.raises(AssertionError, match="executed nothing"):
        rom_bench.Measurement((None, 840), (None, OVERHEAD[1]), OVERHEAD).ratio


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


class _QuietLib:
    """Every `osh_*` counter `_refusal_tallies` reads, all reporting nothing.

    A machine that refused nothing, so `measure` reaches the call this file is about rather than
    stopping at the vet — which is also the point: with the map installed, the real run is quiet
    here too, and without it the very first tally in that set fires.
    """

    def __getattr__(self, _name):
        return lambda *args: 0


def _fake_emu(calls):
    """An `emu` holding just the surface `RomBench.measure` touches, recording what each door was
    handed as its declared I/O map."""
    def run(image, entry, regs, psg_seed=None, hw_seed=None, io_seed=None):
        calls.append(("emu.run", io_seed))
        return image, [], {"d0": 2, "ninsns": 5, "cycles": 82,
                           "psg_events": [], "hw_events": [], "io_events": [], "hw_writes": []}

    # `io_seed` is KEYWORD-ONLY here because it is keyword-only on the real `run_bench`: a caller
    # that passed it positionally would take another parameter's meaning, and this mirror is what
    # makes that fail here rather than in a project's bench run.
    def run_bench(mem, entry, arg0, sp, sentinel, max_insns=None, door=None, seed_regs=None, *,
                  io_seed=None):
        calls.append(("emu.run_bench", io_seed))
        return {"d0": 2, "ninsns": 4, "cycles": 80, "regs": dict(rom_bench.CALLEE_SAVED_SEEDS)}

    return SimpleNamespace(run=run, run_bench=run_bench, STACK_TOP=FAKE_STACK_TOP, SENTINEL=2,
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
    assert calls == [("emu.run", io_seed), ("emu.run_bench", io_seed)]
