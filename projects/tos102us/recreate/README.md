# The TOS 1.02 harness — how `tools/recreate_kit` binds to a ROM

The workspace's differential harness was built for a game: a `.PRG` loaded at `0x10000` into a 1 MB
image, surrounded by a *modelled* TOS. This project's target is that TOS, so none of the model
applies — the ROM **is** the operating system. What follows is how the kit is bound here, how to
write a case, and how a function gets its Tier 3 ratio.

The mode itself is documented kit-side: `tools/recreate_kit/README.md` ("ROM mode") and
`TRAP_MODEL.md` ("ROM mode — the model that is switched OFF"). This file is the project's half.

## The image in ROM mode

| region | what is there |
| --- | --- |
| `$000000..$0fffff` | the **post-boot RAM snapshot** — 1 MB of a real machine, `build/boot_ram.bin` |
| `$ff0000..$ffffff` | the I/O page: decoded by the oracle's memory callbacks, never served from the image |
| `$fc0000..$feffff` | the **ROM**, mapped at its own base and **read-only** — a store is dropped and counted |
| everything else | zero, and off-image: a read answers 0, a write is dropped |

`image_size = 0x1000000` — the whole 24-bit address space, as a 16 MB `bytearray`. The whole of it
except the oracle's stack band is compared byte for byte on every case, the ROM included.

There is no `prg`, no `load_base` and no relocation: a ROM is linked for the address it answers at,
so the addresses in `include/addrs.h` are simultaneously machine addresses, Ghidra addresses and
image offsets.

**The TOS trap model is not installed.** A `trap #13` inside a ROM function is taken through the
image's own vector table by Musashi's exception processing, into the ROM's real handler. That also
means the kit's poked-input block, its Malloc arena and its staged-file window cannot be reached by
anything — the claim is re-tested after every RUN against the total number of traps the model served
(`emu._vet_rom_mode_is_modelless`), and the builders that stage that state (`console_key`,
`psg_regs`, `stage_files`, …) are refused outright.

`image_size` is therefore free to be the whole address space, but **os.h's `OS_IMAGE_SIZE` must
equal this machine's RAM** — it is the bound the CANDIDATE's kit sources use for every image access,
so `0x100000` here is the 1 MB machine and not a coincidence. `harness._vet_rom_memory_map` refuses
a binding where the two disagree, and checks the `stack_top` band lies inside that RAM.

**An I/O byte no model serves REFUSES the case, and the remedy is a declaration the case writes
itself.** For a game the silent 0 an unmodelled I/O read answers was a small surface; for an
operating system it is a much larger hole, so the oracle counts such a read and
`harness._vet_rom_io_reads_are_modelled` refuses the differential by address. The declaration that
answers it is `io_seed={0xff8260: 0x02}` — the DECLARED I/O MAP (`TRAP_MODEL.md`, Phase 15), which
takes any byte of the page and routes the named models' own addresses to them — so `Getrez`
(`$ff8260`), `Physbase`
(`$ff8201`/`$ff8203`) and `Setcolor` (`$ff8240`+) are reachable by SAYING WHAT THE MACHINE HELD,
which is a claim in the case rather than a change to the kit.

**A register a routine WRITES and then READS BACK is declared `write_through`**, which is the same
kind of claim one step further: the case says the register latches what is stored and reads it back
unchanged, and both cores then serve the byte the run itself wrote. It is what makes `Mfpint` (whose
enable half re-reads the IERA and IMRA its disable half cleared a bit of), the MFP timer programmer
(`$fc260e`, which writes the reload byte and re-reads it until the 68901 agrees) and `Rsconf`'s baud
arm ordinary differentials rather than slices and halts. `test/mfp.py` carries the claim register by
register — including the two pairs where it holds only because every store these routines make is a
pure clear (`TRAP_MODEL.md`, Phase 15, "The honest limit of a write-through byte").

**A register whose two successive reads must DIFFER is declared as a LIST**, one byte per read —
`io_seed={0xfffa01: [0x00, 0xff]}`, the DECLARED SEQUENCE (`TRAP_MODEL.md`, Phase 16). That is what
makes the ACIA handler's TWO-PASS entry a case at all: its loop asks the MFP after every pass whether
either 6850 still wants service, and no constant can say "asserted, then idle". A read PAST THE END
of a list is refused on both shores rather than served the last byte again.

What stays out of reach is the TRANSACTION: a register whose next answer depends on something the run
itself did — an FDC command written to `$ff8606` deciding what the next read of `$ff8604` means.
`test/test_boot_snapshot.py` drives both halves of the declared/undeclared pair
on a planted `move.b $ffff8260,d0`, and `test/test_xbios_getrez.py` is the first real function held
to it.

## The snapshot

```
make snapshot                       # capture build/boot_ram.bin (~15 s; emulation is real time)
python tools/boot_snapshot.py --twice   # capture twice and report exactly what differs
```

`tools/boot_snapshot.py` boots the **original** ROM in headless Hatari on a fixed machine —
`--machine st --memsize 1 --monitor rgb --sound off`, a blank 720 KB floppy built by
`tools/st_build.py` in drive A: — and dumps the first megabyte of RAM.

**The stop point** is the ROM's own vertical-blank handler (`$fc06de`, the `addq.l #1,_frclock` the
`$70` vector points at) at vertical blank 901, with the desktop up and idle. One exact instruction,
at a fixed count of vertical blanks from power-on; the tool reads the PC out of Hatari's register
dump and checks it against the vector table in the snapshot itself, so a capture that stopped
elsewhere fails rather than becoming a snapshot of an arbitrary instant.

*Why not the desktop's first `evnt_multi`*, which would be the natural anchor: Hatari's breakpoint
expressions dereference memory only one level deep, so `(pc).w = $4e42 && d0 = $c8` can say "an AES
call" but not *which* AES call — the opcode is two levels down, in `control[0]`. And, decisively,
once the desktop is up and nothing is typed it **blocks inside `evnt_multi` and makes no further AES
calls at all**: a breakpoint armed after any settling period never fires (measured — a 90-second idle
run of exactly that shape timed out at the desktop). The first `evnt_multi` is an instant *during*
start-up, not after it.

Hatari prints no warnings about this ROM; `log_faults()` is checked on every capture and the boot is
clean.

### What two captures disagree about — the MASK

Measured over three independent boots: **1,929 bytes of 1,048,576 (0.18%)**, and *not* the clocks.
`_hz_200`, `_vbclock` and `_frclock` are bit-identical — the stop is at a fixed vertical-blank count
and Hatari's timing is cycle-driven — and so are the whole screen, the 256-entry vector table, every
system variable, the GEMDOS buffers and the desktop's data.

What moves is the **phase of the AES's and the desktop's idle work** at the instant the vertical
blank interrupts it: the three boots stopped with different `D0/D7/A0/A6/A7`, and what differed was
the dead stack below each stack pointer plus the scratch those routines churn.

| region | what it is |
| --- | --- |
| `$0009ff` +5 | OS scratch below the Line-A variables |
| `$001464` +0x1ce | OS BSS scratch / a dead stack frame |
| `$0074c0` +0x54 | OS BSS scratch |
| `$008930` +0x2d0 | the supervisor stack, below ISP |
| `$009488`, `$009fa5`, `$00a19b`, `$00a771` | AES scratch (0xc4 / 0xcf / 0x79 / 0x6d bytes) |
| `$00c7e1` +7 | the AES process structure A5 points at |
| `$0f7fa2` +0x12 | the desktop's stack, below `_memtop` |

`MASK` in `tools/boot_snapshot.py` is the union over the three pairwise comparisons, coalesced across
gaps of 0x100 bytes — deliberately wider than any one pair's difference.

**No case may depend on a byte in there**, and that is a surface rather than a rule:
`test/test_boot_snapshot.py::test_no_verified_function_depends_on_a_byte_the_capture_does_not_reproduce`
fills every masked region with pseudo-random bytes and re-runs every verified function's
differential. **A function added to this project must be added to that case.**

## Writing a case

```python
from harness import addrs, differential, report

def _glue(lib, buf):
    return lib.xbios_random(buf)

diffs, info = differential(addrs.XBIOS_RANDOM, {"a5": 0, "_pokes": pokes}, _glue, poison=True)
assert not diffs, report(diffs)
assert info["ret"] == info["regs"]["d0"]
```

* **Addresses come from `include/addrs.h`**, through `tools/addrs.py`, which parses it. The C cores
  include the header and the cases read the same `#define`s, so an address cannot be right in the
  reconstruction and wrong in the case that proves it.
* **Enter a function the way the dispatcher does.** Both trap dispatchers (`$fc07fc`) pop the
  function number and `suba.l a5,a5`, so every BIOS/XBIOS routine runs with **A5 = 0** and reaches
  low RAM and the I/O page through 16-bit displacements off it. Pass `{"a5": 0}`.
* **Stack arguments** go at `emu.STACK_TOP + 4` (the sentinel return address occupies `+0`), poked
  through `_pokes`. That is inside the band the diff drops, which is where a caller's frame belongs.
* **Perturbing the snapshot** is an ordinary poke: `{addrs.RANDOM_SEED: seed.to_bytes(4, "big")}`
  proves a function over *inputs* rather than over the one machine that was captured.
* **Declare every hardware byte with `io_seed`.** `io_seed={addrs.SHIFTER_RESOLUTION: 0x02}` is the
  one door, and it is the one most BIOS/XBIOS routines need — the shifter, the video base, the
  palette, the MFP's interrupt registers. A byte read of an I/O address nothing declared **refuses
  the case**. The declared byte is served on every read of it, a wide read is N declared bytes and
  one ledger entry, and the whole ordered stream is compared, so a read whose result the routine
  DISCARDS (clearing a status flag by reading it) is still a compared fact. The reconstruction reads
  through `hw.h`'s `io_read8`/`io_read16`/`io_read32`, which the on-target build in
  `atari/shim_include/hw.h` supplies as the real volatile access.
  * **The models are two; the door is one.** A Phase-7 named slot (`emu.HW_ADDRS` — `$fffa01`,
    `$fffc00`, …) written into `io_seed` is ROUTED into that model, which keeps its own rules and
    its own ledger; `hw_seed={0xfffa01: 0xb0}` still works and is the same declaration. Declaring
    one address through both doors is a `ValueError`. See `TRAP_MODEL.md`, Phases 7 and 15.
  * **The YM2149 is the exception**, because Phase 6's file is keyed by REGISTER NUMBER and a read
    of `$ff8800` answers whatever was last latched there: `psg_seed={7: 0x3f}`, refused by name if
    written as an address.
  * **A byte the run itself STORES to and then reads back is refused**, and no bigger declaration
    fixes it: the declaration describes the machine on ENTRY. Run the case up to the write, or enter
    past it declaring what the write left. (Where the register really LATCHES the store, say so with
    `emu.write_through(byte)` — see above.)
  * **A routine whose successive reads of one address must DIFFER takes a LIST**:
    `io_seed={addrs.MFP_GPIP: [asserted, idle]}`. The Nth read is served the Nth byte, the list works
    on a named slot as readily as on any other address, and reading past its end is a refusal rather
    than a sticky last byte — so a list is also the case's statement of HOW MANY reads it describes.
    `test/test_bios_ikbd.py`'s two-pass case is the worked example.
* **Off-image effects are compared automatically**: the PSG access ledger and register file, the
  hardware read and write ledgers, the scheduled-write wait counts.

## A STAGED RAM DISK — the shape the file system needed

Every case above proves a routine over the captured machine's own RAM. The GEMDOS file system
cannot be proved that way: its whole subject is a medium, and the machine this snapshot came from
has a blank floppy in drive A: that no case may spin.

**What makes a disk stageable is where GEMDOS stops.** It makes no hardware access at all, and
reaches a disk through exactly three BIOS calls — `Rwabs`, `Getbpb`, `Mediach` — which are the
dispatch table's INDIRECT entries: entries 4, 7 and 9 of `$fc0846` have bit 31 set, and the
dispatcher's `movea.l (a0),a0` turns each into a jump through a RAM VECTOR (`hdv_rw` `$476`,
`hdv_bpb` `$472`, `hdv_mediach` `$47e`). Those three longwords are ordinary system variables, so a
case pokes them — and from that moment the ROM's own file system is running against a disk the case
built, with no hardware touched by either shore and no model of a floppy anywhere.

**It is the RAM-VECTOR PAIR one layer down** — the arrangement `test/isr.py` already makes for the
routines an interrupt handler calls, and `include/staged_call.h` for the handler's own side:

* for the ORACLE, three real 68000 stubs in the case's band, which copy sectors to and from an image
  poked into free RAM, answer a pointer to a staged BPB record, and answer the MEDIA-CHANGE LONGWORD
  the case poked — which is what makes all three arms of that protocol reachable, the ROM's own
  truncation of it to a word included. They
  are hand-built from named opcode words (`test/gemdos_fs.py`, the shape `gemdos.slice_trampoline`
  uses), assembled offline by `m68k-elf-as` to get them right, and pinned by EXECUTION: a stub
  reading `recno` or the buffer pointer from the wrong stack slot transfers the wrong sector, and
  the candidate — handed the same arguments by C — transfers the right one, so the byte diff reds;
* for the CANDIDATE, a hook the case binds to `recreate_call_disk_vector` (`include/gemdos_fs.h`),
  with the same three effects in Python over the same image bytes.

**The disk is COMPARED IMAGE, and that is the whole of why this works.** The sectors, the buffer
control blocks, their 512-byte buffers, the drive media descriptor and the staged BPB are all
ordinary RAM inside the differential's byte compare — so "the ROM wrote this sector and we did not",
"we wrote it to the wrong record", "we kept a buffer the ROM invalidated" are all ordinary red
diffs. Nothing is excluded, nothing is waived, and the harness needed no new door.

**What it costs is a fourth tenant of the free window.** `project.toml` declares three
(`stack_top`, `bench_base`, `staging_base`) and `RomBench._vet_tenancy` refuses an overlap between
them. A FAT12 floppy does not fit in the 4 KB case band, so the disk takes 44 KB at `$68000` and
says so by arithmetic instead: `test_gemdos_fs_disk.py` asserts the span is clear of all three and
that the captured snapshot leaves every byte of it zero. Growing `staging_bytes` so the kit's own
vet covers it is the tidier answer and is not an agent's edit to make.

**Inside the 4 KB case band, a battery that needs several buffers at once CLAIMS a band**, through
`test/staging.py`'s `band(offset, size, owner)` — which refuses an overlap with every band already
claimed, whoever claimed it, and answers the address. Six modules claim one and the 4 KB is now full,
so a new one takes its span out of a declared tenant instead (the 8.3 name battery's is
`gemdos_fs.NAMES_AT`, inside the RAM disk's). The registry replaced a hand-written assertion per
module against the ONE neighbour its author knew about: under that arrangement two batteries' bands
sat on top of each other with every assertion still passing.

**The disk itself is small enough to read whole in a failure message** — 512-byte sectors, two per
cluster, two sectors per FAT, two of root directory, 32 data clusters, 71 sectors in all — and both
FAT and root directory are two sectors DELIBERATELY: a region whose length is not a whole number of
clusters leaves pseudo-records inside its own cluster span that map onto the region above it, which
is legal (an OFD's length stops the ROM reaching them) and a needless trap for a case that spells a
record by hand. The root holds a subdirectory, a file inside one cluster, a file spanning three, an
empty file, a deleted entry and a volume label, and each file's body is a ramp keyed on the file, so
a read landing on the wrong cluster is a wrong BYTE rather than a plausible one.

**A case here does not poison.** `case.run`'s attribution pass pre-inverts every byte the oracle
wrote, and the oracle writes `savptr` itself on every `trap #13`; what stands in for it is staging —
every buffer starts full of `$a5` and every sector holds its own ramp, so a byte the reconstruction
did not write reads as something no arm of these routines produces. That is the
character-device group's rule (`test/gemdos_console.py`) applied one layer down.

## Verified functions, and what they cost on each side

The oracle reports `ninsns` and `cycles` for every run (`out_regs`), so the ORIGINAL's cost per
function is a measurement rather than an estimate — that is the **denominator**. The **numerator** is
the same C compiled by `m68k-elf-gcc` with the shipped ROM build's own flags, staged in free RAM
inside the same snapshot and entered through `emu.run_bench` over the same case:

```
make bench          # build the cores for the 68000, measure every row, print the table
```

**The table is not restated here.** `make bench` writes it to `build/bench/tier3.txt` and prints it,
one row per verified case — function, ROM address, case, both sides' instructions and cycles, and the
ratio. A copy in this file would be a second set of numbers nobody re-derives; `STATUS.md`'s Tier 3
column is the ledger's summary of the same file, and `test/test_status.py` pins it to that file
ratio by ratio so the prose cannot drift from the measurement.

Both cost columns are as the oracle reports them, which includes the **1 instruction and 40 cycles**
Musashi's reset exception charges before either entry executes anything (`shim.c`'s run loop). The
RATIO is net of that on both sides: a constant added to a numerator and a denominator pulls the ratio
towards 1.00, which on a routine this small is 3% of pure leniency.

**What the spread says**, since the table changes and this does not. The two routines with real work
in them come out well ahead of the ROM — `Protobt` at 0.23x-0.25x and `Random` at 0.62x-0.67x —
and the reason is the 1987 toolchain rather than anything clever here: `Random` pushes two longwords
and calls Alcyon's SIGNED `lmul`, which tracks both operands' signs around three 16x16 multiplies,
where GCC's `__mulsi3` does the three and stops. The LEAF routines come out behind, and the reason is
structural: every core takes `uint8_t *image` and loads it out of the frame, where the ROM reaches
the same memory through the trap dispatcher's own `suba.l a5,a5` at no cost — on a routine whose
whole body is `move.l _drvbits,d0 / rts` that one instruction is +16 cycles and reads as 1.50x.
`bench/tier3.py`'s `PERF_ACCEPTED` records every such row with its measured cost and which of three
mechanisms it is. Being faster is not a licence and being slower is not a defect: the reconstruction
is held to the ROM's BEHAVIOUR, and the ratio is what says how a 2020s compiler prices the same
algorithm.

### How a row is made, and what makes it honest

`bench/tier3.py` is the registry and `test/test_tier3.py` is the gate. **The registry is not a list
anybody typed**: its rows ARE `test/test_boot_snapshot.py`'s `VERIFIED_CASES` — this project's
register of every case a battery has verified, built from each battery's own case constructors — run
again with a cost attached, and even the C argument VALUES are decoded out of the frame the case
poked. A second hand-written list of entries, registers and pokes is exactly how a ratio comes to be
a number about a case nobody proved, and it drifts silently because both lists keep working. What
the registry adds is the one thing that list cannot carry: a `CALL` entry per ROM routine saying how
our C is called (its arguments and the width its signature returns).

The gate then holds three things: every row at or under **1.10** unless `PERF_ACCEPTED` carries it
with its measured cost and a reason; every PINNED row still measuring what it was pinned at, within
0.02; and **every verified case having a row at all** — a function reconstructed without one carries
no ratio and no second differential, and before this nothing said so.

A pin does double duty. Over the bar it is an ACCEPTANCE. Under it, it is how a cost the Tier 1
differential *cannot see* is held in place: XBIOS `Giaccess`'s interrupt bracket (`ipl.h`) is a no-op
off target — the oracle enters at IPL 7, takes no interrupts and reports no SR — so deleting it
leaves every differential green, and the 46 cycles it costs are the whole of its surface.

Each row is also a **second differential**, and that is the larger half of what it buys. The cross
build is a third build of the reconstruction — the host `.so` Tier 1 proves, the shipped ROM, and
this one — so `RomBench.measure` requires the m68k build to leave the same image, the same return
value (at the width the C signature declares), the same callee-saved registers and the same chip
traffic as the ROM did, and refuses a run that read an I/O byte no seeded model serves.
`tools/recreate_kit/README.md`, "Tier 3's numerator", has the mechanism and the measured sharpness.

Two things a target build needs that the host build does not, both in `atari/`: `target.mk`, the one
definition of the flags **and of the include paths** (the ROM build and this one read it, so a ratio
cannot be measured under flags nobody ships, and neither can compile a core against a different set
of headers), and `shim_include/`, where the headers the kit declares "off-target only" have their
target halves — `psg.h` writes the real `$ff8800`/`$ff8802` and `hw.h` reads the real `$ff8260`,
which under the oracle are decoded into the same seeded models and the same ordered ledgers the ROM's
own `move.b` reaches, and `ipl.h` is the real `move.w sr,d0` / `ori.w #$700,sr` pair.

## Layout

```
recreate/
├── project.toml        the ROM binding: rom / rom_base / snapshot / image_size, plus the THREE
│                       tenants of the machine's free window — stack_top (the run's stack),
│                       bench_base (Tier 3's cross-compiled blob) and staging_base/staging_bytes
│                       (the band a case stages buffers and stub routines in). One file, so
│                       `RomBench` can refuse an overlap between them
├── Makefile            the kit's lines, the snapshot rule, and Tier 3's BENCH_CFLAGS + table
├── include/addrs.h     every ROM and system address this project names — the source of truth
├── src/<component>/    the reconstruction, one directory per ROM component
├── atari/              what SHIPS: target.mk (the flags and include paths EVERY 68000 build uses),
│                       shim_include/ (the target halves of the kit's off-target headers), the
│                       rebuilt ROM image and the two measurement programs
├── bench/              tier3.py: Tier 3's registry, its bar, its pins, and the table `make bench`
│                       writes to build/bench/tier3.txt
├── test/               the differentials; `harness.py` is the kit shim plus `addrs`
├── tools/              boot_snapshot.py (the snapshot), addrs.py (addrs.h as Python)
└── build/              gitignored: the candidate .so, the RAM snapshot (the ROM's own data), and
                        bench/ — the cross-compiled blob and the Tier 3 table
```
