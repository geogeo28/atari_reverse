"""Run a ROM project's CROSS-COMPILED C CORES under Musashi — the Tier 3 NUMERATOR, with a proof.

`oracle/emu.py:run()` executes the ORIGINAL ROM function in place, at its own `$fcxxxx` address, over
the post-boot RAM snapshot, and reports what it cost: the DENOMINATOR of the `recreate / original`
cycle ratio a component's row carries. This module is the other half. It takes the same C the shipped
ROM will carry — built by `m68k-elf-gcc` with the TARGET build's own flags (kit.mk's `$(BENCH_*)`
rules, `BENCH_CFLAGS` supplied by the project) — stages it in a free span of that same snapshot, and
enters one core through `emu.run_bench` over the same case. Two costs, one instrument, one image.

A COST WITHOUT A PROOF IS NOT A MEASUREMENT. A cross-compiled core is a *third* build of the
reconstruction — the host `.so` the Tier 1 differential proves, the target ROM, and this — and
`docs/on-target-execution.md`'s bug class 6 is target codegen going wrong where the host build is
right. So `measure()` is a SECOND DIFFERENTIAL as well as a stopwatch: over one case it runs the
original AND the m68k build, and requires

  * the whole image equal, byte for byte, outside the oracle's stack band and the blob's own span;
  * the RETURN VALUE equal at the width the C signature declares (see `returns` below);
  * every callee-saved register handed back (seeded per `asm_twin.CALLEE_SAVED_SEEDS`);
  * EVERY OFF-IMAGE STREAM equal, in order — the same four `harness.differential` compares: the
    ordered PSG accesses, the ordered reads of the modelled hardware set, the ordered reads the
    DECLARED I/O MAP served, and the ordered hardware writes. That is the ONLY surface a core whose
    whole effect is a chip has (XBIOS `Giaccess` is exactly that, and XBIOS `Getrez` is a single
    declared I/O read whose value it returns);
  * NO REFUSAL TALLY SET ON EITHER SIDE — every one the harness reads after a Tier 1 run
    (`_refusal_tallies`). Each says the run was served something the model invented, or that a
    ledger this file then compares was silently truncated, and either makes the row a number about
    a machine that does not exist.

THE COUNTERPART OF `asm_twin.py`, AND THE TWO ARE MUTUALLY EXCLUSIVE BY CONSTRUCTION. That module
runs a project's hand-written m68k TWINS and refuses a ROM project, because it stages the image at a
NON-ZERO base on purpose — so that a twin addressing the image absolutely is caught — and ROM code is
absolute by construction. This module is the mirror image of that argument and refuses everything but
a ROM project: here the image IS the machine's address space, so it is staged at 0, `arg0` is 0, and
a core's `be32(image + SYSVAR_HZ_200)` reads the machine's real `$4ba` exactly as the burnt ROM will.
A `.PRG` project's numerator is a different shape again — its recon runs in its own memory with the
game image at a separate address — and already has two worked examples:
`projects/zynaps/recreate/atari/bench_tier.py` and `projects/buggyboy/remaster/tools/bench.py`.
The CALL is one shape for both, and its shared half lives beside `asm_twin.CALLEE_SAVED_SEEDS`.

THE MEMORY LAYOUT, which is the project's own machine and not an arrangement of this module's:

    0                     the post-boot RAM snapshot — the machine's memory, and arg0 = 0
    bench_base            THE BLOB: the cross-compiled cores at their link addresses (project.toml)
    staging_base          the band a CASE stages buffers and stub routines in (project.toml)
    stack_top             the run's stack: the band the differential drops is
                          [stack_top - 0xf00, stack_top + SENTINEL_SLOT_BYTES + STACK_ARGS_BYTES)
                          (= stack_top + 0x1c), and EVERYTHING ABOVE IT IS COMPARED IMAGE
    $ff0000               the I/O page, decoded by the oracle (PSG, seeded reads, the write ledger)
    $fc0000               the ROM, read-only

Three tenants of one free window, declared in one file so that `_vet_tenancy` can refuse an overlap
between them: a blob over the staging band would be overwritten by a case's own buffer, and a blob
over live snapshot data would measure a core against a machine that never existed.

`bench_base` is RAM rather than ROM, and that costs nothing to the measurement: Musashi charges no
wait states, so a fetch from $30000 and one from $fc0000 cost the same 68000 cycles. What it buys is
that the blob is inside the image the differential already compares, so a core storing into its own
code is a visible divergence rather than a silent one.

Usage (see `projects/tos102us/recreate/bench/tier3.py` for the worked registry):

    bench = RomBench()                                  # loads bench.elf + bench.bin once
    m = bench.measure(addrs.XBIOS_RANDOM, "xbios_random", args=(0,), regs={"a5": 0})
    m.ratio                                             # recreate / original, net of the entry cost
"""
from pathlib import Path
import subprocess

from . import project
from .asm_twin import (CALLEE_SAVED_SEEDS, BLOB_ARG_BYTES, BLOB_FRAME_BYTES, blob_entry,
                       elf_symbols, require_built, stage_stack_args, vet_blob_intact,
                       vet_callee_saved)

# Where kit.mk puts the blob, relative to the project's `recreate/` directory. THE SAME THREE NAMES
# ARE SPELT IN kit.mk's `$(BENCH_DIR)` / `$(BENCH_ELF)` / `$(BENCH_BIN)`: the rule that writes the
# blob is make's and the loader that reads it is this module's, and neither can be asked of the
# other at the time the other needs it (make evaluates its variables before any project is bound).
# `test/test_rom_bench.py::test_the_makefile_writes_the_blob_where_this_module_looks_for_it` is what
# holds the two spellings together, so a rename in either file fails loudly instead of leaving
# `RomBench.require` reporting a blob nobody built.
BENCH_DIR = Path("build") / "bench"
BENCH_ELF = "bench.elf"
BENCH_BIN = "bench.bin"

# The empty C function kit.mk links into every blob (`bench/entry_probe.c`), and what its whole body
# costs a 68000. Together they are how the ENTRY OVERHEAD below is measured rather than assumed.
ENTRY_PROBE_SYMBOL = "rom_bench_entry_probe"
RTS_CYCLES = 16                      # 68000 `rts`: 16 cycles, 4 reads, no write
RTS_INSNS = 1                        # ...and it is ONE instruction, which is the other half of it
# What the probe run must therefore REPORT: Musashi's first `m68k_execute()` after a reset spends the
# reset exception and executes no instruction, and the probe's whole body is the `rts` above.
PROBE_INSNS = 1 + RTS_INSNS

# `nm`'s letters for a symbol that HAS an address — text, data and bss, global (upper) and file-local
# (lower). Deliberately NOT 'a': an absolute is a `.equ` VALUE, and one that happened to share a
# core's name would resolve a call to a number (`projects/zynaps/recreate/atari/bench_tier.py` says
# the same thing at its own copy of this filter).
NM_ADDRESS_TYPES = "TtDdBb"


def bench_base(recreate_dir="."):
    """project.toml's `bench_base` as a hex string for kit.mk, or "" when the project declares none.

    READ WITHOUT BINDING THE PROJECT, which is the whole reason this is not `project.current()`:
    make evaluates it on every invocation, including the `make snapshot` that CAPTURES the snapshot
    a binding insists already exists. The validation is `project.peek_bench_base`'s, so a malformed
    key is refused by one rule rather than two; this only formats the answer make wants.
    """
    value = project.peek_bench_base(recreate_dir)
    return "" if value is None else f"{value:#x}"


class Measurement:
    """One function, one case, on both sides: what each cost and what the ratio is.

    THE COSTS ARE AS THE ORACLE REPORTS THEM — including the one instruction and 40 cycles Musashi's
    reset spends before either entry point executes anything (`shim.c`'s run loop; the kit README's
    denominator table is quoted in the same units). THE RATIO IS NET OF IT, and that is not a
    cosmetic choice: a constant added to both sides drags every ratio towards 1.00, and all of the
    error is in the LENIENT direction. Measured on this project's own rows, the raw ratio overstates
    by 3% on XBIOS `Random`'s 810-cycle case and by 19% on `Giaccess`'s 260-cycle one — a bar can
    survive neither. `RomBench.overhead` measures the constant through BOTH doors rather than
    declaring it.
    """

    def __init__(self, original, recreate, overhead):
        self.original_insns, self.original_cycles = original
        self.recreate_insns, self.recreate_cycles = recreate
        # Only the CYCLES half is kept: the ratio is a cycle ratio, and the instruction counts are
        # printed raw on both sides rather than netted.
        self.overhead_cycles = overhead[1]

    @property
    def ratio(self):
        """recreate / original in CYCLES, each net of the shared entry observation."""
        return self._net(self.recreate_cycles) / self._net(self.original_cycles)

    def _net(self, cost):
        """`cost` with the entry observation removed, refusing a run that cannot have happened.

        A measured cost at or below the overhead is not a fast function, it is a run that executed
        nothing — a wrong entry symbol, a blob that was never staged — and dividing by it would
        report that as a ratio rather than as the mistake it is.
        """
        if cost <= self.overhead_cycles:
            raise AssertionError(
                f"a measured cost of {cost} is not above the {self.overhead_cycles} the entry "
                f"itself charges — the run executed nothing, which is an entry that is not where "
                f"the function is")
        return cost - self.overhead_cycles


class BenchResult:
    """One run of the cross-compiled cores: the memory it left, its return register, and its cost."""

    def __init__(self, image, d0, insns, cycles):
        self.image = image
        self.d0 = d0
        self.insns = insns
        self.cycles = cycles


def _refuse_off_rom_mode(cfg):
    """A .PRG project cannot use this runner, and the reason is the layout rather than a policy."""
    if cfg.rom is not None:
        return
    raise RuntimeError(
        f"{cfg.name} is not bound in ROM MODE (tools/recreate_kit/README.md, \"ROM mode\"), where "
        f"this runner belongs: it stages the cores INSIDE the image at absolute addresses and hands "
        f"them 0 as their image base, which is only the machine's own arrangement when image offset "
        f"IS machine address. A .PRG project's image is a program at a load base, so a blob staged "
        f"in it would overwrite the program and an image base of 0 would read the vector page. Its "
        f"numerator runs the recon in its OWN memory with the image beside it — see "
        f"projects/zynaps/recreate/atari/bench_tier.py.")


def _allocated_span(elf):
    """[lo, hi) over every ALLOCated section of `elf` — the addresses the blob OWNS.

    Not the flat binary's length: `.bss` is allocated and carries no bytes, so a span measured from
    the file would leave a core's zeroed statics outside everything this module checks — outside the
    "is it clear of the snapshot's own data" vet, and inside the image comparison, where they would
    read as the reconstruction diverging from the original.
    """
    lo, hi = None, None
    header = None
    for line in subprocess.check_output(["m68k-elf-objdump", "-h", str(elf)], text=True).splitlines():
        fields = line.split()
        # objdump prints a section as a pair of lines: `idx name size vma lma off algn`, then its
        # flags. So the flags line is read against the header line remembered from the pass before.
        if len(fields) == 7 and fields[0].isdigit():
            header = (int(fields[3], 16), int(fields[2], 16))
            continue
        if header is None or "ALLOC" not in line:
            header = None
            continue
        addr, size = header
        header = None
        lo = addr if lo is None else min(lo, addr)
        hi = addr + size if hi is None else max(hi, addr + size)
    if lo is None:
        raise AssertionError(f"{elf} has no allocated section — it holds no code to run")
    return lo, hi


class RomBench:
    """The cross-compiled cores of one ROM project, loaded once and callable with the C ABI.

    `bench_dir` holds `bench.elf` (the symbol table and the section map) and `bench.bin` (the flat
    blob), both built by kit.mk's `$(BENCH_BIN)` rule from the project's `src/**/*.c` with the
    TARGET build's flags. It defaults to the bound project's `build/bench/`.

    The entry overhead is measured EAGERLY, in the constructor, and the ordering is the reason: the
    measurement is two oracle runs, and `emu.run` installs the PSG seed it was given — so measuring
    it lazily from inside `measure()` would wipe that case's declared chip contents between the
    original's run and ours, and the two would be measured over different machines.
    """

    def __init__(self, bench_dir=None):
        self.cfg = project.current()
        _refuse_off_rom_mode(self.cfg)
        bench_dir = Path(bench_dir) if bench_dir else self.cfg.dir / BENCH_DIR
        self.elf = bench_dir / BENCH_ELF
        self.bin = bench_dir / BENCH_BIN
        self.require()
        self.symbols = {name: value for name, (value, kind) in elf_symbols(self.elf).items()
                        if kind in NM_ADDRESS_TYPES}
        self.blob = self.bin.read_bytes()
        self.base, self.end = _allocated_span(self.elf)
        _vet_tenancy(self.cfg, self.base, self.end)
        self.overhead = self._measure_overhead()

    def require(self):
        """FAIL LOUDLY if the blob was never built. A skip would hide a broken target build: the
        suite would go green having measured nothing, and "no Tier 3 row" is exactly the state the
        numerator exists to leave behind."""
        require_built((self.elf, self.bin), "the cross-compiled cores",
                      "build them with `make bench` (or `make test`, which depends on them), which "
                      "compiles src/**/*.c with m68k-elf-gcc")

    def entry(self, symbol):
        """A core's link address, or a listing of what the blob DOES hold — a renamed or dropped
        core must name itself rather than surface as a wild jump into the snapshot."""
        return blob_entry(self.symbols, symbol, "the cross-compiled cores")

    def measure(self, entry, symbol, args=(), regs=None, pokes=None, psg_seed=None, hw_seed=None,
                io_seed=None, returns=4):
        """One case on both sides: the ORIGINAL at `entry`, then our `symbol`, over the same image.

        Returns a `Measurement`. `entry`/`regs`/`pokes`/`psg_seed`/`hw_seed`/`io_seed` are the oracle
        case exactly as `harness.differential` takes it — the same seed set, so a case that is
        runnable there is runnable here — and `args` are the C arguments our build is called with.
        `returns` is how many bytes of D0 the C signature declares: 4 for a `uint32_t`, 1 for a
        `uint8_t`, 0 for `void`.

        ONE IMAGE IS BUILT, AND OURS IS A COPY OF IT — `harness.candidate_image`'s arrangement for a
        Tier 1 case, for its reason: the two sides must start from the same bytes, and a second
        `make_image` would re-read a base image an autouse fixture could have moved in between.

        THE ORDER OF THE TWO RUNS IS LOAD-BEARING, for the half of the machine a bench run does
        not declare. `io_seed` — the DECLARED I/O MAP — is handed to `run_bench` per run, exactly as
        `emu.run` takes it, so our build is served the bytes THIS case declared rather than whatever
        map the run before left installed. The PSG and the Phase-7 named set are the other way
        round: their declaration persists between runs and a bench run deliberately leaves it alone
        (TRAP_MODEL.md, "The BENCH door in ROM mode"), so the original — which `emu.run` seeds — has
        to go first, and our build then runs over the chip the case declared. Everything the run
        leaves off-image is read the instant each run ends, because the shim keeps one set of
        ledgers and clears them per run.

        WHY THE RETURN VALUE IS COMPARED AT THAT WIDTH AND THE REGISTER FILE IS NOT. The m68k SysV
        ABI promises a `uint8_t` result in the low BYTE of D0 and nothing above it: measured on
        `xbios_giaccess`, GCC emits `move.b $ff8800,%d0` and leaves the caller's high word in place,
        where the ROM's own `moveq #0,d0` first clears it. The same holds for D1/A0/A1, which are
        scratch: a C compiler owes them nothing, and requiring them to match the original's would be
        requiring the reconstruction to be a transcription — which is what `asm_twin.py` is for. What
        IS required of every other register is that it comes back untouched, and `_call` checks that.
        """
        import emu
        import harness

        self._vet_pokes_are_clear_of_the_blob(symbol, pokes)
        image = harness.make_image(pokes or {})
        o_final, _o_writes, o_regs = emu.run(image, entry, dict(regs or {}), psg_seed=psg_seed,
                                             hw_seed=hw_seed, io_seed=io_seed)
        # The denominator gets the same refusals as the numerator. `harness.differential` makes them
        # for a Tier 1 case, but a bench row is a case of its own — and an original measured while
        # reading a fabricated byte is measuring a machine that does not exist, whichever side did it.
        _vet_no_refusals(f"the ORIGINAL at {entry:#x}", _refusal_tallies())
        original_streams = {key: o_regs[key] for key in _STREAMS}

        ours = self._call(bytearray(image), symbol, args, io_seed=io_seed)

        self._vet_image(entry, symbol, o_final, ours.image)
        _vet_return_value(symbol, ours.d0, o_regs["d0"], returns)
        for key, original in original_streams.items():
            _vet_ledger(symbol, _STREAMS[key], getattr(emu, key)(), original)
        return Measurement((o_regs["ninsns"], o_regs["cycles"]), (ours.insns, ours.cycles),
                           self.overhead)

    def _call(self, image, symbol, args=(), io_seed=None):
        """Run `symbol` over `image` with the C ABI: `args` as 32-bit stack words, in order.

        `io_seed` is the case's DECLARED I/O MAP, installed for THIS run — an empty declaration
        included, so a core that reads the shifter is served the byte its differential was rather
        than the previous case's map, or the fabricated 0 no map at all answers with.

        PRIVATE TO `measure`, and it has to be: the map above is the only half of the machine a
        bench run declares, and the PSG and the named hardware set are still the ones the run BEFORE
        it left installed (see `measure`). Called on its own it would measure this case's C over the
        previous case's chip.

        `image` is the run's MEMORY and is mutated. The blob is staged into it here rather than by
        the caller, so the span that is staged and the span that is excluded from the comparison are
        one fact.

        THE FIRST ARGUMENT IS THE CALLER'S, not an image base forced on it. Nearly every core in this
        workspace takes `uint8_t *image` first and in ROM mode that pointer is 0 — but a core whose
        whole effect is a chip has no image argument at all (`xbios_giaccess(data, reg)`), and
        substituting one over its first word would corrupt exactly the value it needs.
        """
        import emu

        if len(image) != self.cfg.image_size:
            raise ValueError(f"image is {len(image)} bytes, expected {self.cfg.image_size}")
        image[self.base:self.base + len(self.blob)] = self.blob
        # `run_bench` writes the return address at sp and the first argument at sp+4; the m68k SysV
        # ABI puts every further argument in the longwords above it — the same staging
        # `asm_twin.AsmTwins.call` does, and the same place the oracle's own case pokes a ROM
        # function's arguments (`abi.FIRST_ARG`), which is inside the band the diff drops.
        _vet_stack_args_fit(symbol, args)
        stage_stack_args(image, emu.STACK_TOP, args[1:])

        entry = self.entry(symbol)
        seed = [CALLEE_SAVED_SEEDS.get(name, 0) for name in emu.REPORTED_REGS]
        result = emu.run_bench(image, entry, arg0=(int(args[0]) & 0xFFFFFFFF) if args else 0,
                               sp=emu.STACK_TOP, sentinel=emu.SENTINEL, seed_regs=seed,
                               io_seed=io_seed)
        # Read the instant the run ends, before anything else can run over the shim's one set of
        # counters: `emu` publishes these only through `run()`'s own report, and a bench run needs
        # the same refusals (`osh_run_bench` clears them per run, as `osh_run` does).
        _vet_no_refusals(f"the m68k build of {symbol}", _refusal_tallies())
        vet_callee_saved(symbol, result["regs"])
        vet_blob_intact(symbol, image, (self.base, self.base + len(self.blob)), self.blob)
        return BenchResult(image, result["d0"], result["ninsns"], result["cycles"])

    # ---- what the blob's placement has to be true of ---------------------------------------------

    def _vet_pokes_are_clear_of_the_blob(self, symbol, pokes):
        """A case may not poke inside the blob's span — the bytes would be overwritten by the code.

        The original's run would see the case's bytes and ours would see the blob, and the span is
        excluded from the comparison, so the two would be measured over different machines with
        nothing here able to say so. It is checked against the poke DICT rather than caught after
        the fact, because after the fact there is nothing left to catch.
        """
        for address, data in (pokes or {}).items():
            if address < self.end and self.base < address + len(data):
                raise AssertionError(
                    f"{symbol}'s case pokes {len(data)} byte(s) at {address:#x}, inside the blob's "
                    f"span [{self.base:#x}, {self.end:#x}) — our run would see the cross-compiled "
                    f"cores there and the original would see the poke, and the span is excluded "
                    f"from the comparison. Stage it in the band `staging_base` declares")

    def _vet_image(self, entry, symbol, original, ours):
        """The second differential's memory half: equal everywhere the comparison reaches.

        The excluded regions are exactly two, and both are excluded on the ORIGINAL's account rather
        than ours: the oracle's stack band, which `harness.diff_spans()` already drops because a
        machine stack is not output, and the blob's span, which holds our code where the original's
        image holds the snapshot's zeroes. THAT SECOND CLAIM IS CHECKED HERE rather than assumed —
        the snapshot is empty over the span at construction, but a run of the ORIGINAL that stored
        there would make the exclusion hide real output, and only the run itself can say.

        THE EXCLUSION COVERS A CORE'S OWN STATICS, since `.bss` is inside the blob's span — and that
        is the right answer rather than a hole, because a static has no counterpart in the original's
        image to be compared against. What such a core's statics DO reach, and what is compared, is
        its return value and its off-image traffic.
        """
        import harness

        blob = bytes(original[self.base:self.end])
        if blob.count(0) != len(blob):
            live = [self.base + i for i, byte in enumerate(blob) if byte]
            raise AssertionError(
                f"the ORIGINAL at {entry:#x} left {len(live)} non-zero byte(s) in the blob's span "
                f"[{self.base:#x}, {self.end:#x}), the first at {live[0]:#x} — it stores where our "
                f"code is staged, so excluding the span hides output this comparison is for. Move "
                f"`bench_base` in project.toml")

        def excluded(address):
            return self.base <= address < self.end

        differing = harness.differing_addresses(memoryview(original), memoryview(bytes(ours)),
                                                harness.diff_spans(), excluded)
        if differing:
            shown = ", ".join(f"{addr:#x} ({original[addr]:#04x} -> {ours[addr]:#04x})"
                              for addr in differing[:8])
            raise AssertionError(
                f"the m68k build of {symbol} left different memory than the original at "
                f"{entry:#x}: {len(differing)} byte(s), first {shown}. The HOST build of this core "
                f"is verified, so this is the target build — the codegen, the flags, or a "
                f"target-only header shadow (docs/on-target-execution.md, bug class 6)")

    def _measure_overhead(self):
        """What an entry itself charges, measured through BOTH doors on the same empty function.

        `emu.run` and `emu.run_bench` both enter from a CPU reset, and Musashi's first
        `m68k_execute()` after one spends the reset's cycles and executes no instruction — so every
        cost either reports is one instruction and one reset high. Both halves of a ratio carry it,
        which is precisely why it must come out of both: a constant added to a numerator and a
        denominator pulls the ratio towards 1.00 and makes a bar lenient.

        Measured on `bench/entry_probe.c`, whose whole body is the `rts`, and REQUIRED EQUAL through
        the two entry points — that equality is the premise the subtraction rests on, and it is the
        kind of thing a change to one entry point could break silently. What the probe EXECUTED is
        required too: an empty function that cost more than its `rts` was compiled with a prologue,
        and the difference would be charged to every reconstruction as entry overhead.
        """
        import emu
        import harness

        image = harness.make_image()
        image[self.base:self.base + len(self.blob)] = self.blob
        entry = self.entry(ENTRY_PROBE_SYMBOL)
        _final, _writes, o_regs = emu.run(image, entry, {})
        bench = emu.run_bench(image, entry, arg0=0, sp=emu.STACK_TOP, sentinel=emu.SENTINEL)
        through = {"emu.run": (o_regs["ninsns"], o_regs["cycles"]),
                   "emu.run_bench": (bench["ninsns"], bench["cycles"])}
        if o_regs["ninsns"] != bench["ninsns"] or o_regs["cycles"] != bench["cycles"]:
            raise AssertionError(
                f"the oracle's two entry points charge DIFFERENT entry overheads for the same "
                f"`rts` ({through}) — a Tier 3 ratio divides one by the other, so the difference "
                f"would be charged to the reconstruction")
        insns, cycles = through["emu.run"]
        _vet_probe_is_a_bare_rts(self.elf, insns, cycles)
        return insns - RTS_INSNS, cycles - RTS_CYCLES


# The four off-image streams a Tier 1 differential compares, as {the name: what a message calls it}.
# The NAME is `emu`'s for both halves at once — the key `emu.run` reports the ORIGINAL's under, and
# the getter that reads OURS off the shim after a bench run (`emu.psg_events()` and the rest, cleared
# by the same per-run reset; TRAP_MODEL.md, "The BENCH door in ROM mode"). One spelling, so the two
# sides cannot come to be read from different ledgers, and a stream nobody compares is the surface a
# core whose whole effect is off-image has nothing else on.
_STREAMS = {"psg_events": "the ordered PSG accesses",
            "hw_events": "the ordered modelled-hardware reads",
            "io_events": "the ordered declared-I/O reads",
            "hw_writes": "the ordered hardware writes"}


def _refusal_tallies():
    """Every refusal the shim tallied for the run that has JUST ended, as {what it was: the detail}.

    Read the instant a run ends, because the shim keeps ONE set of counters and clears them per run.
    An entry with an empty detail did not happen; `_vet_no_refusals` refuses the rest by name.

    THE SET IS THE ONE `harness.differential` READS AFTER A TIER 1 RUN, and it is the whole set on
    purpose. Two kinds are in it and both make a row meaningless: a read the model could not serve —
    answered a fabricated 0 on BOTH sides, so the comparison above would vouch for it — and a ledger
    that overflowed, which truncates a stream `_vet_ledger` then compares as though it were whole.
    """
    import emu

    lib = emu._LIB
    unseeded_psg = lib.osh_psg_unseeded()
    return {
        "read PSG register(s) whose contents nothing declared":
            ", ".join(str(reg) for reg in range(emu.PSG_NREGS) if unseeded_psg & (1 << reg)),
        "read a PSG register back before anything selected one":
            _count(lib.osh_psg_no_select()),
        "accessed the PSG ports in a way the model cannot serve":
            _count(lib.osh_psg_unmodeled()),
        "used XBIOS Giaccess and the PSG ports directly in one run, so the modelled register file "
        "may be stale": "yes" if lib.osh_psg_mixed_paths() else "",
        "overflowed the PSG access ledger": _count(lib.osh_psg_dropped()),
        "read modelled hardware byte(s) nothing declared": _addrs(emu.hw_unseeded_addrs()),
        "wrote modelled hardware byte(s) and then read them back":
            _addrs(emu._hw_addrs_of(lib.osh_hw_stale())),
        "took modelled hardware byte(s) in by a 16- or 32-bit read":
            _addrs(emu._hw_addrs_of(lib.osh_hw_wide())),
        "read VOLATILE modelled hardware byte(s) twice, which one per-run constant cannot describe":
            _addrs(emu._hw_addrs_of(lib.osh_hw_reread())),
        "overflowed the modelled-hardware read ledger": _count(lib.osh_hw_dropped()),
        "overflowed the hardware write ledger": _count(lib.osh_hw_write_dropped()),
        "read I/O byte(s) no seeded model serves — answered 0, on both sides, so nothing here could "
        "tell that answer from the machine's; declare them (TRAP_MODEL.md, Phase 15) with "
        "`io_seed={<address>: <byte>}` before measuring this core":
            _first(lib.osh_io_unmodeled_reads(), lib.osh_io_unmodeled_first()),
        "read I/O byte(s) THIS run stored to, which a declaration of the machine on ENTRY cannot "
        "describe": _first(lib.osh_io_stale_reads(), lib.osh_io_stale_first()),
        "overflowed the declared-I/O read ledger": _count(lib.osh_io_dropped()),
    }


def _count(n):
    """A tally as a detail string, or "" for the run that did not do it."""
    return str(n) if n else ""


def _addrs(addresses):
    """...and a set of addresses, which is how the modelled-hardware tallies report themselves."""
    return ", ".join(f"{addr:#x}" for addr in addresses)


def _first(n, first):
    """...and a tally that also names the first offending address."""
    return f"{n}, the first at {first:#x}" if n else ""


def _vet_no_refusals(who, tallies):
    """Refuse a run the model could not honestly serve, naming every tally that fired.

    `who` names the side, because both make the access and only one of them is a surprise: the
    ORIGINAL doing it means the function is out of reach until the case declares the byte, while OUR
    build doing it where the original did not means the target-side code reached a port the
    reconstruction does not go through.

    Every tally that fired, rather than the first: a run can trip several, and naming one sends the
    reader off to fix it and hit the identical message again (`emu.run`'s own causes list says the
    same thing at its own).
    """
    fired = [f"{what} ({detail})" for what, detail in tallies.items() if detail]
    if not fired:
        return
    raise AssertionError(f"{who} " + "; and ".join(fired))


def _vet_return_value(symbol, ours, original, returns):
    """D0 equal at the width the C signature declares — see `RomBench.measure`."""
    if not returns:
        return
    mask = (1 << (8 * returns)) - 1
    if (ours & mask) != (original & mask):
        raise AssertionError(
            f"the m68k build of {symbol} returned {ours & mask:#x} where the original left "
            f"{original & mask:#x} in D0 (compared over {returns} byte(s), the width the C "
            f"signature declares)")


def _vet_ledger(symbol, what, ours, original):
    """An off-image ledger equal on both sides, in ORDER.

    It is the only surface a core whose whole effect is off-image has: XBIOS `Giaccess` writes no
    image byte at all, so without this its second differential would compare two identical images
    and vouch for a build that selected the wrong register.
    """
    if list(ours) != list(original):
        raise AssertionError(
            f"the m68k build of {symbol} left different {what} than the original:\n"
            f"  original: {list(original)}\n  ours:     {list(ours)}")


def _vet_probe_is_a_bare_rts(elf, insns, cycles):
    """The entry probe must have executed the reset's phantom instruction and its `rts`, and nothing
    else.

    The subtraction rests on it: what is left after a 68000's one-instruction, 16-cycle `rts` is
    taken as the oracle's entry overhead and removed from BOTH sides of every ratio. An empty
    function compiled with a prologue — a frame pointer, a `movem` of a register file it does not
    use — would put its own cost into that constant and hand every reconstruction the difference,
    and nothing downstream could tell it from the oracle's own.
    """
    if insns == PROBE_INSNS and cycles > RTS_CYCLES:
        return
    raise AssertionError(
        f"{ENTRY_PROBE_SYMBOL} in {elf} executed {insns} instruction(s) for {cycles} cycles, not "
        f"the {PROBE_INSNS} the reset's phantom instruction and the {RTS_INSNS}-instruction, "
        f"{RTS_CYCLES}-cycle `rts` that is its whole body come to — it was built with a prologue, "
        f"and the entry overhead every Tier 3 ratio is net of would carry it. Check the project's "
        f"BENCH_CFLAGS for -O0 or -fno-omit-frame-pointer")


def _vet_tenancy(cfg, base, end):
    """The blob must lie in RAM the snapshot leaves EMPTY, clear of the window's other two tenants.

    Checked here rather than declared in the project.toml comment, because every part of it is
    invisible when it is wrong: a blob over live snapshot data measures a core against a machine the
    original never ran on; a blob over the stack band is overwritten by the run's own frame; a blob
    over the CASE STAGING band is overwritten by a case's own buffer, or overwrites it; and a blob
    that is not where `bench_base` says would make the comparison exclude a span the code is not in.

    Three refusals, each its own function below so that each can be driven on its own: the runner
    needs a bound project, a real ROM and a built blob, and the kit's own suite has none of those
    (`test/test_rom_bench.py`).
    """
    import emu
    import harness

    _vet_link_address(base, cfg.bench_base)
    bands = [("the blob", base, end),
             ("the oracle's stack band", emu.STACK_GUARD_LO, emu.STACK_BAND_HI)]
    if cfg.staging_base is not None:
        bands.append(("the case staging band (`staging_base`)", cfg.staging_base,
                      cfg.staging_base + cfg.staging_bytes))
    _vet_bands(bands, emu.RAM_END)
    # `harness.BASE_IMAGE` is the snapshot as captured, which is what the claim is about — a poked
    # case is a perturbation of it and cannot move the blob.
    _vet_snapshot_is_empty(base, end, harness.BASE_IMAGE)


def _vet_link_address(base, declared):
    """The blob must be linked where project.toml says, because kit.mk passes that key to the
    linker: the two disagreeing means the blob on disk was built from a different configuration, and
    the comparison would then exclude a span the code is not in."""
    if base == declared:
        return
    raise AssertionError(
        f"the cores are linked at {base:#x} but project.toml declares bench_base = {declared:#x} — "
        f"kit.mk passes that key to the linker, so the two disagreeing means the blob was built "
        f"from a different configuration")


def _vet_bands(bands, ram_end):
    """The free window's tenants — `(name, lo, hi)` — pairwise disjoint and inside the machine's RAM.

    THE GEOMETRY ALONE, so that it can be driven without a machine. Whichever band is written second
    wins and neither says so: a blob under the stack band is overwritten by the run's own frame, and
    one under the case staging band is overwritten by a case's buffer or overwrites it. They are
    declared in ONE file (project.toml) precisely so that one rule can compare them.
    """
    for i, (name, lo, hi) in enumerate(bands):
        if hi > ram_end:
            raise AssertionError(f"{name} spans [{lo:#x}, {hi:#x}), past the machine's "
                                 f"{ram_end:#x} bytes of RAM — a 68000 has nothing to fetch there")
        for other, other_lo, other_hi in bands[i + 1:]:
            if lo < other_hi and other_lo < hi:
                raise AssertionError(
                    f"{name} [{lo:#x}, {hi:#x}) overlaps {other} [{other_lo:#x}, {other_hi:#x}) — "
                    f"the tenants of the free window are declared in project.toml precisely so that "
                    f"this cannot happen silently, and whichever is written second wins")


def _vet_snapshot_is_empty(base, end, snapshot):
    """The captured snapshot must hold nothing where the blob goes.

    Staging code over the machine's own data measures a core against a machine that never existed,
    and the bytes it overwrote are excluded from the comparison, so nothing downstream could see it.

    `count(0)` first and the Python walk only if that fails, for `harness.differing_addresses`'
    reason: the count runs in C, and a blob is free to grow to any size a project's cores need.
    """
    span = bytes(snapshot[base:end])
    if span.count(0) == len(span):
        return
    live = [base + i for i, byte in enumerate(span) if byte]
    raise AssertionError(
        f"the snapshot is not empty where the blob goes: {len(live)} non-zero byte(s) in "
        f"[{base:#x}, {end:#x}), the first at {live[0]:#x}. Move `bench_base` — staging code over "
        f"the machine's own data measures a core against a machine that never existed, and the "
        f"bytes it overwrote are excluded from the comparison")


def _vet_stack_args_fit(symbol, args):
    """The C arguments must fit the ARGUMENT AREA the harness reserves above the sentinel slot.

    `harness.STACK_ARGS_BYTES` is that area, measured across every project: everything above it is
    ordinary image the differential compares, so a wider argument list would be staged where a Tier 1
    case's stray-write guard reports real output — our side only, since the ORIGINAL reads its
    arguments from the frame the case poked and never sees these words at all.
    """
    import harness

    written = BLOB_FRAME_BYTES + BLOB_ARG_BYTES * max(len(args) - 1, 0)
    room = harness.SENTINEL_SLOT_BYTES + harness.STACK_ARGS_BYTES
    if written > room:
        raise AssertionError(
            f"{symbol} is called with {len(args)} C argument(s), which reach {written} bytes above "
            f"the run's stack pointer — past the {room}-byte argument area the harness reserves "
            f"(harness.STACK_ARGS_BYTES). Beyond it the words land in image the comparison reads")
