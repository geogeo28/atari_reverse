# recreate_kit — the shared differential harness

The game-agnostic half of a `projects/<game>/recreate/` reconstruction: load a GEMDOS `.PRG`
into a flat image, run the original 68000 code under Musashi, run the reconstruction's C on the
same image, and diff. Every game-specific part (the `src/` cores, `include/addrs.h`, the
`test/test_*.py` battery) stays in the project. How the harness works — and why differential
testing rather than byte-matching — is documented in
[`projects/buggyboy/recreate/README.md`](../../projects/buggyboy/recreate/README.md), the
worked reference example.

```
tools/recreate_kit/
├── project.py        bind one recreate/ dir to the kit (reads its project.toml)
├── harness.py        the differential driver (differential/report/make_image/stage_files,
│                     plus the model-state pokes console_key/psg_regs)
├── os_map.py         the harness-poked input block, the staged-file table's base, and the overlap
│                     arithmetic the guards ask for (shared by harness.py and oracle/emu.py;
│                     importable with nothing built)
├── stubs.py          hand-assembled 68000 stubs (the GEMDOS Malloc probe) and the span seeder,
│                     shared by the kit's suite and the projects' — likewise needs nothing built
├── guarded_image.py  OPT-IN pytest plugin: run every candidate on an image with PROT_NONE either
│                     side, so a raw `image + <computed address>` that leaves the buffer FAULTS
├── kit.mk            shared make rules: candidate .so, Musashi oracle, `test`/`venv`/`oracle`/`clean`
├── include/          machine.h (big-endian image accessors)  os.h (deterministic TOS trap model)
│                     raster.h (the ST device-format raster the VDI opcodes draw through)
├── src/              C linked into EVERY candidate .so: dosound_log.c (the Dosound ledger below),
│                     os_heap.c (the Malloc arena) and os_fs.c (the staged-file window) — the two
│                     regions installed per project — os_log.c (the off-image OS event ledger), and
│                     gem.c + raster.c: the GEM/VDI model, the two files the ORACLE links too, so
│                     both sides draw the same pixels by construction
├── oracle/           loader.py (load+relocate PRG)  emu.py (Musashi runner)  shim.c (callbacks)
│                     isa_conformance.py  tos_probe.py   musashi/ + build/ (gitignored)
├── test/             the kit's own regression tests (`make test` here; no project needed)
├── TRAP_MODEL.md     what each modeled TOS trap does — and what it deliberately does NOT capture
└── Makefile          runs test/
```

## Adding a game

1. Write `projects/<game>/recreate/project.toml`:

   ```toml
   name       = "<game>"
   prg        = "../bin/<GAME>.PRG"     # relative to recreate/
   names      = "../names.txt"
   lib        = "build/lib<game>.so"
   load_base  = 0x10000
   image_size = 0x100000
   # heap_base  = 0x30000               # only if the program covers the default 0x20000 arena
   # heap_limit = 0x90000               # ...and only if the free window ends below OS_FS_TABLE
   # fs_base    = 0xb7000               # only if the boot stages more than the default window holds
   ```

   `load_base` must clear the poked-input block (`OS_POKE_BLOCK_END`, `0x660`) and `image_size`
   must equal `os.h`'s
   `OS_IMAGE_SIZE`, which `os_fread`/`os_fwrite` bound their copies against — the harness checks
   both at import and names `project.toml` when they disagree. `heap_base` and `heap_limit` are
   optional and place the modeled Malloc arena; leave them out unless the program's text+bss reaches
   `0x20000` (see "The Malloc arena is the one region a project places"). `fs_base` is optional too
   and places the staged-file window; leave it out unless the files a case must stage do not fit the
   default 258,048-byte staging area (see "The staged-file window is the second region a project
   places").

2. `projects/<game>/recreate/Makefile`:

   ```make
   KIT  := ../../../tools/recreate_kit
   GAME := <game>
   include $(KIT)/kit.mk
   ```

3. `projects/<game>/recreate/test/harness.py` — a 16-line shim that binds the kit and
   star-re-exports it, so every test can keep saying `from harness import differential, report`.
   Copy it from `projects/buggyboy/recreate/test/harness.py`.

### What the candidate `.so` must export

`differential(entry, regs, glue, …)` only calls what the project's own `glue` callbacks name, so
there is no required symbol — with EIGHT groups the kit supplies for you, in the order below:

| symbol | signature | purpose |
| --- | --- | --- |
| `g_dosound_log_reset` | `void(void)` | clear the ledger before each candidate run |
| `g_dosound_log_count` | `uint32_t(void)` | number of `Dosound` calls logged |
| `g_dosound_log_args`  | `const uint32_t *(void)` | the ordered list pointers (image addresses) |
| `g_dosound`           | `void(uint8_t *, uint32_t)` | what a reconstruction calls at a `Dosound` site |

XBIOS `Dosound(A0)` writes the YM2149, not RAM, so a wrong or missing sound-command list is
**invisible to the image diff**. The harness diffs the candidate's ledger against the oracle's
ordered `Dosound` trap stream, catching exactly that. All four symbols come from `src/dosound_log.c`,
which `kit.mk` links into every candidate — the ledger is one implementation shared by every game
rather than a copy per project, and its cap is `os.h`'s `OS_DOSOUND_LOG_MAX`, the same one the
oracle's mirror ledger truncates at.

The Dosound ledger is one of the things the model keeps **off-image**, which is exactly what a
candidate has to mirror by hand — everything else the trap model touches is plain image state that
`include/os.h`'s `os_*` helpers write identically on both sides. The others are the direct
`$ff8800`/`$ff8802` PSG write stream and the register contents a read of that port returns, which are
the next group. See [`TRAP_MODEL.md`](TRAP_MODEL.md).

### The file-load seam (`disk_read_file`)

A game whose boot chain ends in a raw floppy controller cuts it at the lowest FILE-SHAPED routine and
calls `disk_read_file` (`include/disk.h`) across the cut. `src/disk.c` supplies it off target, over
`os_fopen`/`os_fread`/`os_fclose`; an on-target build defines its own with the real GEMDOS traps and
does not compile this file, exactly as it does not compile `src/hw.c`. It exports NO ledger — every
byte of the staged-file model lives in the image, so the ordinary diff already compares it. See
[`TRAP_MODEL.md`](TRAP_MODEL.md)'s Phase 9 for the boundary discipline the seam obliges, and
`projects/wonderboy/recreate/STATUS.md`'s batch 44 phase B for the first game to use it.

The harness still treats the group as *optional* at import (it probes the three accessors once), so
a candidate built outside `kit.mk` keeps working: it is then served without the ledger while the
oracle issues no `Dosound` at all, and `differential()` fails with that diagnostic the moment one
appears. A reconstruction built for the real Atari supplies its own `g_dosound` that issues the
real trap and does not compile this file — see `projects/buggyboy/recreate/render/atari/game_main.c`.

The SECOND group is the **refused-`os_*`-call tally**, from `src/os_refusal.c` (likewise linked into
every candidate by `kit.mk`). Unlike the ledger above it is **required**, not optional:

| symbol | signature | purpose |
| --- | --- | --- |
| `g_os_refusal_reset` | `void(void)` | clear the tally before each candidate run |
| `g_os_refusal_count` | `uint32_t(void)` | refused `os_*` calls the candidate made |
| `os_refused`         | `int32_t(int32_t)` | what `include/os.h`'s helpers route a refusal through |

`harness.differential()` clears the tally, runs the candidate, and **raises if it is non-zero** —
closing a false-green class in which a reconstruction could drop a guard the original has and stay
green, because the refusal rejected the oracle's run only. See [`TRAP_MODEL.md`](TRAP_MODEL.md),
"Refusing on ONE side is a false green".

Reconstruction code never calls `os_refused` itself — `os.h` does, at every point a helper answers
"the model cannot serve this". It is nonetheless part of the exported ABI: the tests that pin the
mechanism call it directly to stand in for a refusal, and `harness` probes all three at import.
Absence is a hard error there rather than a graceful degrade, because the tally has no oracle-side
witness the way the Dosound ledger does: the oracle's own count is zero by construction, so a
missing symbol would reopen the false-green class on a suite that stays entirely green.

The THIRD is a two-symbol group, the **Malloc arena's placement**, from `src/os_heap.c`:

| symbol | signature | purpose |
| --- | --- | --- |
| `os_set_heap_base` | `void(uint32_t)` | install `project.toml`'s `heap_base`, so `OS_HEAP_BASE` reads the same address the oracle allocates from |
| `os_set_heap_limit` | `void(uint32_t)` | ...and its `heap_limit`, the first address the arena may not reach |

`harness` calls each once at import, and requires it **only when the project set the key**: a
candidate predating the file already starts at `OS_HEAP_BASE_DEFAULT` and stops at
`OS_HEAP_LIMIT_DEFAULT`, which is right for a project that configured nothing and wrong — silently,
by a whole arena — for one that moved or narrowed its heap. See "The Malloc arena is the one region
a project places".

Its twin is the **staged-file window's placement**, one symbol, from `src/os_fs.c`:

| symbol | signature | purpose |
| --- | --- | --- |
| `os_set_fs_table` | `void(uint32_t)` | install `project.toml`'s `fs_base`, so every `os_fopen` resolves the same table the harness staged into (the staging area follows it) |

Required on the same terms and for the same failure: a candidate predating the file reads the table
at `OS_FS_TABLE_DEFAULT`, which is right for a project that configured nothing and wrong — every
file reported unstaged, on that side alone — for one that moved its window. See "The staged-file
window is the second region a project places".

Beside it sit two more **required** groups, from `src/os_log.c` and `src/os_heap.c`. The FOURTH is
the **off-image OS event ledger** — Dosound's ledger generalised to every other call that hands a
byte to a device instead of storing one:

| symbol | signature | purpose |
| --- | --- | --- |
| `g_os_event_reset` | `void(void)` | clear the ledger before each candidate run |
| `g_os_event_count` / `g_os_event_kinds` / `g_os_event_values` | | the ordered `(kind, value)` stream |
| `g_os_event` | `void(uint16_t, uint32_t)` | the recording side, which `os_cconout()` / `os_cauxout()` / `os_cprnout()` / `os_ikbd_out()` / `os_pterm()` and the four XBIOS video doors (`os_setscreen()` / `os_setpalette()` / `os_setcolor()` / `os_vsync()`) call |

GEMDOS `Cconout`/`Cconws`/`Crawio`'s write direction, `Cauxout`, `Cprnout`, BIOS `Bconout` to the
IKBD, AES `graf_mouse` and VDI `v_show_c`/`v_hide_c` touch no memory, and neither does GEMDOS
`Pterm` — so a reconstruction that prints nothing or leaves the GEM pointer showing is byte-identical
to one that gets them right, and this is the only thing that can tell them apart. Required
rather than probed, because every candidate links `src/os_log.c` and an absent ledger would be
compared against an oracle stream that does exist. An on-target build supplies its own `g_os_event`
and does not compile the file, exactly as it does for `g_dosound`.

**`os_pterm()` is the one whose contract is on its CALLER**: it cannot end anything from the
candidate side — it is a C call and the only way back to the harness is to return — so a
reconstruction must `return` immediately after it. `g_os_event` enforces the half it can, refusing
any further event once a `Pterm` is recorded; a continuation that stores into the image is caught by
the byte diff; one that does neither is unpinned. See `TRAP_MODEL.md`, "Phase 13".

The FIFTH is the **candidate's Malloc arena** itself:

| symbol | signature | purpose |
| --- | --- | --- |
| `os_malloc` | `uint32_t(uint32_t)` | what a reconstruction's `Malloc` wrapper calls; mirrors the shim's bump arena |
| `g_os_heap_reset` | `void(void)` | rewind it to the base before each candidate run |
| `g_os_heap_pointer` | `uint32_t(void)` | how far this run grew it, which `differential()` compares with the oracle's |

...so a reconstruction does not carry a private copy of the shim's arithmetic, which is what drifts
the day either changes. `Malloc(-1)` answers the free window's SIZE on both sides, and a request the
window cannot hold is refused rather than served over the staged-file table.

### The GEM/VDI model is the one thing compiled into BOTH sides

`src/gem.c` and `src/raster.c` are linked into every candidate **and** into `liboracle.so`
(`kit.mk`'s `$(ORACLE)` rule names them). A GEM application's `trap #2` is its output, not a call
whose effect can be a no-op, so the model draws real ST pixels — and having one implementation is
what makes "the oracle's trap and the reconstruction's `os_vdi()` draw the same thing" true by
construction. Both files are **stateless** (the workstation attributes live in the image) and
**refuse nothing themselves**, which is what lets one copy serve both objects safely and lets each
side keep its own refusal tally and its own ledger. The whole contract is
[`TRAP_MODEL.md`](TRAP_MODEL.md), Phases 11-13.

The SIXTH group is the **direct-PSG surfaces**, from `src/psg.c` + `include/psg.h` (likewise linked
into every candidate by `kit.mk`). Optional in the same way as the Dosound ledger, and for the same
reason — a game that never touches `$ff8800`/`$ff8802` has nothing to record, and the ORACLE's own
traffic is the witness that says when the group was needed:

| symbol | signature | purpose |
| --- | --- | --- |
| `psg_port_write` | `void(unsigned, uint8_t)` | what a reconstruction calls where the original writes a register |
| `psg_port_read`  | `uint8_t(unsigned)` | ...and where it reads one back (`move.b $ff8800,dn`) |
| `g_psg_reset`    | `void(const uint8_t *, uint32_t)` | seed the register file + clear the ledger, before each candidate run |
| `g_psg_log_count` / `g_psg_log_kinds` / `g_psg_log_regs` / `g_psg_log_vals` | | the ordered access stream: one `(kind, reg, value)` per write **and per read** |
| `g_psg_file` / `g_psg_file_known` | | the register contents those writes left, and which are known |

The ports are outside the image, so a missing, extra, reordered or wrong register access is invisible
to the byte diff — and so is the chip's own state, which every read-modify-write of it preserves bits
of. `harness.differential()` seeds both sides from the case's `psg_seed=` and compares both surfaces.

**Reads are in the ledger, not just writes**, because a reconstruction that reads the *wrong*
register still writes the right one: its write stream and the register file it leaves can be a
correct run's exactly, and only the read entry separates them. `emu.psg_writes()` is the write-only
projection of the same stream, with its contract unchanged.

A read of a register nothing declared or wrote — or of one the chip does not have — is refused on
**both** sides: the oracle's run is rejected, and `psg_port_read` routes its refusal through
`os_refused()` above. The whole contract, including the YM2149 edge semantics this models and those
it refuses, is [`TRAP_MODEL.md`](TRAP_MODEL.md), "Phase 6".

The SEVENTH group is the **seeded hardware reads**, from `src/hw.c` + `include/hw.h` (likewise linked
into every candidate by `kit.mk`, and optional in the same way, with the oracle's own reads as the
witness):

| symbol | signature | purpose |
| --- | --- | --- |
| `hw_read8` | `uint8_t(uint32_t)` | what a reconstruction calls where the original reads a modeled hardware byte |
| `g_hw_reset` | `void(const uint8_t *, uint32_t)` | install the declared bytes + clear the ledger, before each candidate run |
| `g_hw_log_count` / `g_hw_log_slots` / `g_hw_log_vals` | | the ordered read stream: one `(slot, value)` per read |
| `g_hw_file` / `g_hw_file_known` | | the declared bytes those reads are served from, and which are declared |
| `hw_write8` / `hw_write16` / `hw_write32` | `void(uint32_t, uint32_t)` | what a reconstruction calls where the original STORES to an I/O register |
| `hw_bset8` / `hw_bclr8` / `hw_and8` | `void(uint32_t, uint32_t)` | ...and where it READ-MODIFY-WRITES one — `bset #b,addr`, `bclr #b,addr`, `andi.b #m,addr`. Spelling one of these as a plain store of the byte the oracle's fabricated read produces is green off target and a DEFECT on the machine; `hw.h` and `TRAP_MODEL.md` Phase 10 have the contract |
| `g_hw_write_count` / `g_hw_write_addrs` / `g_hw_write_widths` / `g_hw_write_vals` | | the ordered store stream: one `(address, width, value)` per store (`g_hw_reset` clears it — one reset for both ledgers, so a path cannot refresh one and leave the other) |

The modeled READ set is exactly `$fffa01` (MFP GPIP), `$ff820a` (shifter sync), `$ff8207`/`$ff8209`
(the shifter's video-address counter, mid and low) and `$fffc00` (the IKBD ACIA's status) — `os.h`'s
`OS_HW_*` constants, which is what `hw_read8` takes. Three of them **steer a branch**; the counter
pair is an **arithmetic input** (a routine hashes it for entropy). Either way the `0` every other
off-image read answers is not merely incomplete: it makes the reconstruction and the original take
the same wrong path, or hash the same fabricated constant, and the diff agrees with itself. That is
the `$ffff820a` defect BuggyBoy shipped green.

The ACIA status is the ONE slot the model declares for itself, with TDRE set — a send loop leaves on
its first poll and serving `0` would hang both sides for ever. A case may override it like any other
(`hw_seed=`), and `TRAP_MODEL.md`, "Phase 7", argues why nothing else may have a default.

Each address is STATIC or **VOLATILE**: a volatile one (the counter pair) is a byte the machine
changes on its own, so one declaration describes exactly one read and a **second read of it in the
same run is refused**, while a static one may be re-read freely — the machine's answer is the same
every time, so one declaration describes every read of it.

`harness.differential(..., hw_seed={0xfffa01: 0xb0})` declares the bytes to both sides and compares
the read streams. **A differential whose oracle read one of them without a declaration is refused**,
naming the addresses — but a bare `emu.run` is served the `0` unchanged, because a bare run verifies
nothing and is how relocator/Copylock/bootstrap code is driven. The whole contract, including that
divergence, the audio-capture fold and the FDC non-goal, is
[`TRAP_MODEL.md`](TRAP_MODEL.md), "Phase 7".

**The WRITE half is compared for every case, by default**, and it covers the three blocks the ST
decodes (`$ff8000..$ff8fff`, `$fffa00..$fffaff`, `$fffc00..$fffcff`) rather than everything above the
image: a store past the image but below those is a runaway pointer, not a device, and stays dropped.
A missing, extra, reordered, mis-addressed, wrong-width or wrong-value store fails the case. An address that is
not one of those blocks — inside the image, a runaway, or the untranslated `$ffff8240` form — is a
REFUSAL rather than an entry. A case whose candidate models a routine's hardware half as a no-op
names those addresses in `hw_waiver={address: reason}`: the reason is required, the waiver covers
only the addresses it names (on both streams and both sides), it RETIRES ITSELF the day the
candidate starts accessing one of them, and each distinct waiver is recorded in
`harness.HW_WAIVERS`. The whole contract, including the read-modify-write residual and why the
default is ON, is [`TRAP_MODEL.md`](TRAP_MODEL.md), "Phase 10".

The **DECLARED I/O MAP** ships in the same two files, and is the rest of the same group:

| symbol | signature | purpose |
| --- | --- | --- |
| `io_read8` / `io_read16` / `io_read32` | `uint8_t(uint32_t)` / `uint16_t(uint32_t)` / `uint32_t(uint32_t)` | what a reconstruction calls where the original reads an I/O byte the CASE declares by address — one call per instruction, at the instruction's own width |
| `g_io_reset` | `void(const uint32_t *addrs, const uint8_t *values, const uint8_t *writeback, uint32_t n)` | install the case's map (`writeback` = os.h's `OS_IO_WRITE_THROUGH` per address) + clear the ledger, before each candidate run |
| `g_io_seed_count` / `g_io_log_count` / `g_io_log_addrs` / `g_io_log_widths` / `g_io_log_vals` | | the map's size, and the ordered SERVED-read stream: one `(address, width, value)` per read |
| `g_io_writeback_count` | `uint32_t(void)` | how many installed entries the case marked `OS_IO_WRITE_THROUGH` — the one surface that says the candidate built the writeback COLUMN and not just the addresses (it was the NEWEST name in the probed group when `g_io_reset` grew its fourth argument) |
| `g_io_seq_reset` | `void(const uint32_t *addrs, const uint32_t *offsets, const uint32_t *lengths, const uint8_t *pool, uint32_t n, uint32_t pool_len)` | install the case's DECLARED SEQUENCES (Phase 16) and rewind every cursor, before each candidate run. The wire form is a flat byte POOL plus one `(address, offset, length)` row per list, because a C ABI has no ragged arrays |
| `g_io_seq_count` | `uint32_t(void)` | rows `os.h`'s rule accepted — compared against the oracle's, exactly as `g_io_seed_count` is |
| `g_io_seq_spent` / `g_io_seq_spent_addr` / `g_io_seq_spent_index` | `uint32_t(void)` | this run's reads PAST THE END of a declared list, and the first one's address and read index — the candidate's mirror of the oracle's `osh_io_seq_spent*`, and what makes `harness.refusal_hints()` name the read rather than offer the shape. `g_io_seq_spent` is the NEWEST name in the probed group, so an `.so` predating it fails the probe instead of being driven as though it reported one |
| `hw_poll8` / `io_poll8` | `int(uint32_t addr, uint8_t *seen)` | ONE ITERATION of a poll loop at either door: the same read as `hw_read8`/`io_read8`, plus whether the model could still serve it (1 = go round again, 0 = refused). A refusal hands this shore `0`, which most poll loops read as "still busy" — so a core that spins on a status bit polls rather than reads, and the loop ends where the case's declaration runs out instead of hanging the worker (`sched.h`'s `sched_poll16` contract, at this door) |

The named set above is one `os.h` slot per address, which is the right shape for a game and a
bottleneck for an operating system — TOS's BIOS and XBIOS touch most of the machine. So a case may
declare ANY byte of the I/O page the named models do not own:
`harness.differential(..., io_seed={0xff8260: 0x02})`, served on every read of it, ledgered, and
compared. A declaration may also be a **LIST** — `io_seed={0xfffa01: [0x00, 0xff]}` — for a register
whose successive reads must DIFFER before the run can proceed: the Nth read is served the Nth byte,
a read past the end is a refusal on both shores, and the list may be declared on a Phase-7 NAMED
SLOT too ([`TRAP_MODEL.md`](TRAP_MODEL.md), "Phase 16"). A wide read is N DECLARED BYTES and one
entry, so declaring both halves of a palette word
is served where Phase 7 would have had to refuse. An UNDECLARED byte is unchanged — the silent `0`
it has always been, counted, and refused in ROM mode.

**The models stay two; the door is one.** `io_seed` accepts every I/O byte, and a Phase-7 named slot
written there is ROUTED into that model's own installer (`emu.seed_split`, called by both shores) —
so the two models keep their separate rules and ledgers while the declaration a case writes is one
dict. Only the YM2149's block is refused instead of routed, because Phase 6's file is keyed by
register number rather than by address; so is the untranslated `$ffff8260` form, and so is one
address declared through both doors at once. An on-target build supplies all three doors as the real
volatile access and compiles no map at all. The whole contract, including the staleness rule and the
deliberate absence of a volatile rule, is [`TRAP_MODEL.md`](TRAP_MODEL.md), "Phase 15".

The EIGHTH group is the **scheduled writes**, from `src/sched.c` + `include/sched.h` (likewise linked
into every candidate by `kit.mk`, and optional in the same way, with the case's own `schedule=` as
the witness — a case that declares one against a candidate lacking the group is refused by name):

| symbol | signature | purpose |
| --- | --- | --- |
| `sched_poll8` | `uint8_t(uint8_t *, uint32_t addr, uint32_t site_pc)` | one iteration of a busy-wait AT `site_pc`: count the poll against that site, apply any store it brings due, then read the byte |
| `sched_poll16` | `int(uint8_t *, uint32_t addr, uint32_t site_pc, uint16_t *seen)` | one iteration of a CAPPED WORD wait: the poll above plus a full-width read; 0 once the site has spent `OS_SCHED_POLL_MAX` |
| `sched_poll32` | `int(uint8_t *, uint32_t addr, uint32_t site_pc, uint32_t *seen)` | ...and of a CAPPED LONGWORD wait, the same contract four bytes wide. The two share one clock, so a width cannot drift |
| `g_sched_reset` | `void(const uint32_t *entries, uint32_t n, const uint32_t *sites, uint32_t site_n)` | install the run's schedule AND its wait sites + clear the counters, before each candidate run |
| `g_sched_count` / `g_sched_polls` / `g_sched_applied` / `g_sched_refused` | | entries carried, polls made, stores made, stores refused |
| `g_sched_site_count` / `g_sched_site_polls` / `g_sched_undeclared` | | sites declared, polls at the ith, and polls naming no declared site (each a refusal) |

This is the only group that is not about a value a run READS. A routine that busy-waits on a byte
**no instruction in its own body writes** — Wonder Boy's pause wait spinning on the scancode the IKBD
interrupt will store — cannot be run by a differential at all: nothing changes memory while a run is
in flight, so the loop is infinite on both sides. The case declares the store instead, with
`differential(..., schedule=[{"pc": 0x64e, "nth": 3, "addr": 0x879, "width": 1, "value": 0x99}])`,
and the SAME list is installed on both sides.

The store alone would be a false-green machine, since it lands on both sides whatever the
reconstruction's loop does. What makes it a test is the **count**: the oracle counts arrivals and the
candidate counts polls, and `harness.differential` compares them — so a port that spins a different
number of times, or not at all, fails. Poll only the byte the wait is ON, once per iteration; an
ordinary field read stays a plain guarded read.

**A CASE MAY DECLARE A SITE WITH NO SCHEDULE AT ALL**, and that is an ordinary shape rather than a
degenerate one: "the key is never pressed", or any loop that re-reads a byte a bounded number of
times and gives up. The counting is armed by the **site** declaration, not by the schedule's length
— gated on the latter, such a case compared the candidate's real polls against zero arrivals, and
the workaround was a dummy entry that could never come due.

**BOTH COUNTS ARE PER WAIT SITE**, keyed by the address at which the ORIGINAL re-reads the byte,
which the candidate names at every poll and the case declares with `wait_sites=` (defaulting to the
schedule's trigger PCs). A run TOTAL cannot carry two waits: they balance by cancellation, and a port
that deleted one of them passes. A poll naming a site the run did not declare is refused rather than
served. The whole contract, including the `insn` trigger a differential refuses and the aliasing hole
the kit suite measures, is [`TRAP_MODEL.md`](TRAP_MODEL.md), "Phase 8".

### The modeled TOS traps

Which GEMDOS/BIOS/XBIOS calls are serviced, with what semantics, and — just as important — what
each model deliberately does not capture, is written up in **[`TRAP_MODEL.md`](TRAP_MODEL.md)**.
Read it before reconstructing any function that traps. The one rule that outranks the rest: an
unmodeled call sets `modeled = 0` and `emu.run` **raises**, because a partially-modeled call that
returns a plausible-looking wrong value turns a loud failure into a silent one.

### Opt-in: audio capture

A mode for a **different job** than the differential: driving a game's music replayer tick by tick
and reading the YM2149 register stream out of `psg_writes()`, so an asset extractor can dump its
songs. It serves a few hardware reads the oracle otherwise refuses or answers as 0 — the `$ff8800`
register read-back a mixer read-modify-write needs, and the two bits of the 50 Hz colour-ST tempo
profile (`$fffa01` bit 7, `$ff820a` bit 1) — each of which is the model's invention rather than the
game's data. So it is **off by default, and `harness.differential()` refuses to run while it is
armed**: a reconstruction verified against one of those answers would be verified against `shim.c`.

| call | what it does |
|---|---|
| `emu.audio_capture(on)` | arm/disarm. Re-arming an *armed* capture keeps it; arming from *off* clears (the chip state is shared with the differential's model). The argument is required. |
| `emu.audio_reset()` | clear the modeled register file **and the select latch**. Nothing clears them mid-capture but this — a `run()` under the mode included. |
| `emu.audio_capturing()` | context manager: arm + reset on entry, disarm on exit. **Required**, not merely advised — `emu.run()` refuses a run made under the mode outside one, since the mode is process-global and `-n auto` makes a leak unreproducible. |
| `emu.audio_capture_on()` | is it armed? (What `differential()` vets.) |
| `emu.psg_file()` | the modeled register file, for diagnostics. The data feed is `psg_writes()`. |

Since the seeded read model landed (`TRAP_MODEL.md`, "Phase 6") the mode is a **relaxation** of it
rather than a model of its own: it shares the one register file and select latch, and what it adds is
answering an *undeclared* register (or an *unselected* latch) as `0`, which a differential refuses,
and letting both span runs, which a differential re-seeds per run. That is why it stays opt-in,
vetted off by `differential()`, and refused by `run()` unless the run says it meant to be there.

The two tempo bytes are the same story one model over: since "Phase 7" the mode serves them by
**installing a seed** over the seeded hardware read model — `emu.hw_capture_profile()` is that seed —
rather than by a switch of its own. It is installed per run, so disarming the mode is enough to get
the case's own declaration back; while armed the profile wins, which is why `emu.run` refuses a
`hw_seed` passed under the mode instead of silently ignoring it.

The full contract — exactly which reads are served and which stay refused, why the register file and
select latch span runs, and why none of it narrows the differential's guarantee — is in
[`TRAP_MODEL.md`](TRAP_MODEL.md). Pinned by
`projects/wonderboy/recreate/test/test_audio_capture.py` (the kit's own suite binds no project, so it
has no 68000 code to run the mode against) plus one case in
`projects/joust/recreate/test/test_os_traps.py` for the mixed-path guard.

Three regions of the image are **harness-poked inputs** rather than program memory, so that
hardware whose real value is time-varying still reaches both cores identically:
`OS_CON_PENDING`/`OS_CON_CHAR` (the pending console keystroke — `harness.console_key()`),
`OS_RANDOM_VALUE` (what XBIOS `Random` returns), and `OS_PSG_REGS` (the YM2149 register file XBIOS
`Giaccess` reads and writes — `harness.psg_regs()`).

### The shared TOS memory map

`include/os.h` fixes the modeled Malloc heap (`OS_HEAP_BASE`), the staged-file window
(`OS_FS_TABLE` / `OS_FS_STAGING`, `OS_FS_SLOTS` entries — 32 of them, sized by the longest boot the
workspace has met, Zynaps's ~30 opens) and the poked-input block above at kit-wide addresses, mirrored
in Python by `harness.py` — except the three PER-PROJECT addresses (`OS_HEAP_BASE`, `OS_FS_TABLE`,
`OS_FS_STAGING`), which sit in `oracle/emu.py` where the per-run guards below need them, and the
poked-input block plus the window's own default place, which sit in `os_map.py` because `harness.py`
and `emu.py` both guard those. All are re-exported (`harness.OS_HEAP_BASE`, `harness.OS_FS_TABLE`,
`harness.OS_CON_PENDING`, …). `test/test_os_memory_map.py` pins every constant equal to `os.h` and
refuses a second Python copy. The kit-wide ones are **not** derived from `project.toml`, so the
harness checks at import that they clear the bound project's program, stay below the stack guard,
sit below its `load_base`, and that `OS_IMAGE_SIZE` matches its `image_size` — failing with a
diagnostic naming `project.toml` when they do not.

**Two regions of the map a project PLACES**, because a kit-wide constant cannot answer for every
game: the Malloc arena (`heap_base` / `heap_limit`) and the staged-file window (`fs_base`). Each has
its own section below, and the two mechanisms are built the same way — an optional `project.toml`
key, defaulting to the kit's own address; resolved in `oracle/emu.py`; installed into **both** shared
objects at import, since `os.h` is compiled into `liboracle.so` (shared by every project) and into
the game's candidate.

#### The Malloc arena is the one region a project places

**This is the one place the heap mechanism is written out.** Every other mention of it — `os.h`,
`shim.c`, `src/os_heap.c`, `emu.py`, `harness.py`, `TRAP_MODEL.md`, and a project's own
`project.toml` — is a pointer here plus the one fact a reader of that file needs.

The heap is the exception to a kit-wide map, because a program can simply *be* where the default
arena is — Bubble Ghost's runs to `0x2520e`, over `0x20000` — and `os.h` is compiled into two
**shared objects** (`liboracle.so`, which every project links, and the game's candidate), so a
`#define` cannot answer "where" per project. Both ends of the arena are therefore installed or
resolved **at run time**:

| | |
|---|---|
| `heap_base = 0x30000` | optional key in `project.toml`; absent = `os.h`'s `OS_HEAP_BASE_DEFAULT` (`0x20000`), so every project that does not set it is unchanged |
| `heap_limit = 0x90000` | optional too: the first address the arena may **not** reach. Absent = `OS_FS_TABLE`, and a project may only LOWER it (`emu.resolve_heap_limit` clamps) — raising it would grant exactly what the kit-wide ceiling refuses |
| `emu.OS_HEAP_BASE` / `emu.HEAP_LIMIT` | the resolved values every Python guard and diagnostic reads. `harness.OS_HEAP_BASE` serves the base back live, through a module `__getattr__`, so the two modules cannot disagree; it is in `harness.__all__` so a project's `from recreate_kit.harness import *` shim still carries it |
| `osh_set_heap_base()` | the oracle's entry point (`oracle/shim.c`), called once by `emu` at import |
| `os_set_heap_base()` | the candidate's (`src/os_heap.c`, swept into every candidate by `kit.mk`), called once by `harness` at import |
| `emu.install_heap_base()` | the one implementation of "tell one `.so`", used by both sides — each supplies its own refusal, since they name different files and different rebuilds |
| `OS_HEAP_BASE` | unchanged in C, but now a **variable read** rather than a constant — usable in an expression, not in a case label, an array bound or a static initialiser |

Both entry points are **required ABI only when the key is set**: a `.so` predating them already
starts its arena at the default, so a default project is served correctly by an old build, while a
project that moved its heap and was silently served the old base would allocate over its own
program. That is refused by name, naming the rebuild.

Because the base is a project's choice, `_vet_os_memory_map()` checks it against the rest of the map
as well as against the program. The arena grows **upward without bound**, so a base at or above
`OS_FS_TABLE` overwrites the staged-file table; one below `OS_POKE_BLOCK_END` hands out a block
covering the model's own console/`Random`/PSG state; one inside the framebuffer
(`OS_SCREEN_BASE`..`+0x7d00`) hands out memory a game redraws every frame; and a ceiling at or below
the base leaves no window at all. Every refusal names the value's source — `heap_base` in
`project.toml`, or `OS_HEAP_BASE_DEFAULT` in `os.h` when the project set no key, since there is no
line to go and edit in that case.

**Where it starts is all placement can ask.** How far the arena GROWS is not a configuration, and a
base that is legal at import says nothing about the seventh allocation — so `emu.run()` refuses, per
run, a bump pointer that finished past the ceiling (`_vet_heap_within_bounds`). Until that existed
nothing looked at the pointer: a block handed out over the staged-file table or over a project's own
scratch map is a plain image write served identically to both sides, so the two corrupted runs
compared equal and the case reported green.

`test/test_heap_base.py` pins the keys, every refusal, both installers' missing-ABI errors, the
ceiling in both directions, and — through the miniature project — that a served `Malloc` really
lands at the configured base on **both** sides.

One waiver exists for the heap: only a GEMDOS `Malloc` ever writes at `OS_HEAP_BASE`, so a game
that issues none can set `tos_malloc_unused = true` in its `project.toml` (justifying it there) and
let its program cover that region — `projects/joust/recreate/project.toml` is the worked example. A
game that *does* allocate moves the arena with `heap_base` instead; the waiver is not a substitute
for it.
`OS_FS_TABLE` has no waiver: the harness stages files itself, so an overlap there is always live.

The waiver is a claim about the *game*, so it is not taken on trust. `emu.run()` calls
`_vet_no_malloc_over_program()` after every oracle run and fails if the run served a GEMDOS `Malloc`
while `OS_HEAP_BASE` lies inside the loaded program — the one case where a green diff means
nothing, since the candidate mirrors the same `OS_HEAP_BASE` and would scribble the identical bytes
over the identical program area. Two details make it hold:

* it counts **serviced `Malloc` traps** (`osh_malloc_count`), not movement of the bump pointer. A
  `Malloc` whose size rounds to zero — canonically `Malloc(-1)`, GEMDOS's "how big is the largest
  free block?" query — is fully served and returns a block at `OS_HEAP_BASE` without moving the
  pointer, so a pointer test would wave exactly that case through;
* it lives in `emu.run()` rather than in `differential()`, so an oracle-only run and the poison
  re-run inside `_attribution_check` are covered by the same check.

It keys on the *overlap*, never on the flag, so it stays correct if `heap_base` or a project's
`load_base` moves, and setting the flag on a game that does allocate does not buy a green run. The
flag itself must be a real TOML boolean (`project.py` rejects anything else: a quoted `"false"` is
truthy in Python and would silently waive the check). What it does *not* cover: a program that
reaches `OS_HEAP_BASE` through some other route than the modeled `Malloc` — nothing here watches
plain writes into that region. `projects/joust/recreate/test/test_heap_guard.py` exercises the whole
guard, since Joust is the only project it is armed for.

A **second waiver**, `tos_poked_input_unused`, exists for the poked-input block and is built the
same way. `load_base >= OS_POKE_BLOCK_END` (`0x660`) is impossible for a program that runs at a
fixed low address — `projects/wonderboy/` loads at `0x3f8`, because its `.PRG` relocates itself to
absolute `0x400` and there is nothing below that but the 68000 vector page. A game that reads
**none** of the poked state (no `Bconstat`/`Bconin`/`Crawio`, no `Random`, no `Giaccess`, no
`Kbdvbase`, no `trap #2`) can declare the flag and let its program cover the block.

**WIDENING THE BLOCK IS A CHANGE TO EVERY DECLARING PROJECT'S WAIVER.** `OS_POKE_BLOCK_END` is the
top of the block, and it has moved twice (the VDI state block took it to `0x644`, the console key
queue to `0x660`) — each time swallowing more of a low-loading program. Before moving it again:
re-read every `project.toml` whose `poked_input_overlaps_program` is true (`tos_poked_input_unused`
names them), check the new span against the game's own map, and update the waiver's prose — it
states which of the game's bytes the block now covers, and a stale one describes a smaller region
than the code enforces. Wonder Boy's waiver names `fn 0x638 game_unpause_on_key_release`, which the
block reached only when it grew past `0x620`.

Like the heap waiver it buys a layout and not a green run, and for the same reason: the claim is
about the *game*, so it is re-tested rather than trusted. Two guards, covering the two directions
the hazard has, both keyed on the **overlap** and never on the flag:

* **`emu.run()`** refuses any run in which a trap reached the block — `_vet_no_poked_input_read()`,
  keyed on the shim's `osh_poked_input_calls` tally exactly as the heap guard is keyed on
  `osh_malloc_count` (and oracle-side only, unlike the refusal tally: see
  [`TRAP_MODEL.md`](TRAP_MODEL.md) for the two limits that carries).
  This is the direct sibling of the Malloc re-check, and the half that matters:
  the dangerous reader is the game, not the test. A `Bconin` in code that only exists after a depack
  reads the program's own (nonzero) instruction bytes, is told a keystroke is pending, gets four
  bytes of code back as the key, and has four more bytes of code **zeroed** — identically on both
  sides, since both run the same `os.h`, so the diff comes back clean.
* **`harness.make_image()`** refuses a poke whose byte range lands in the block, unless the project
  has DECLARED that span to be its own program's data (below). It sits where
  pokes are *applied*, which is the layer nothing can go round: the block holds three kinds of state
  and the kit ships two builders, so hand-writing `{OS_RANDOM_VALUE: …}` into a poke dict is the
  only way any project stages an XBIOS `Random` — an idiom already in use in Joust's suite — and it
  is seen exactly like a `console_key()` one.
* **`project.toml`'s `poked_input_program_data`** is the one way past it, and only for a project
  whose program covers the block: a list of `[address, length]` spans that are the GAME's own
  variables at an address the model also names. A poke lying WHOLLY inside a declared span is served;
  one that straddles the boundary is not. It permits the SEEDING and nothing else — the hazard is a
  TRAP serving one of those bytes back as model state, and that stays refused per run by
  `emu._vet_no_poked_input_read`, declaration or no declaration. Wonder Boy declares `[[0x604, 4]]`,
  which is `OS_CON_CHAR` in full, and its `project.toml` carries the evidence.

`console_key()` / `psg_regs()` refuse as well (`_vet_poked_input_available()`), but only as a
friendlier early error naming what was staged; they are not the guard. A project whose `load_base`
already clears the block keeps both builders however its `project.toml` is written, because the
overlap, not the flag, is what decides.

The block's Python mirror lives in **`os_map.py`**, its own module: `harness.py` and `oracle/emu.py`
both guard it and neither can import the other, and it must stay importable with nothing built so
that the kit's own suite can pin the geometry (`test/test_os_map.py`). What that suite still cannot
reach is the *wiring* — both guards live in modules that load a compiled `.so` at import — so that
half stays pinned in `projects/wonderboy/recreate/test/test_poked_input_guard.py`, the only project
the overlap exists for.

#### The staged-file window is the second region a project places

**This is the one place the staged-file window's placement is written out.** Every other mention of
it — `os.h`, `shim.c`, `src/os_fs.c`, `emu.py`, `harness.py`, `TRAP_MODEL.md`, and a project's own
`project.toml` — is a pointer here plus the one fact a reader of that file needs.

The window is the arena's twin, for the same structural reason and a different practical one: a
program's **boot** can simply need more staging space than the default place leaves. The table at
`OS_FS_TABLE_DEFAULT` (`0xbf000`) puts the raw file bytes at `0xc0000`, which leaves
`STACK_GUARD_LO - 0xc0000` = **258,048 bytes**; Flying Shark's `init_load_assets` opens eight files
totalling **288,551**, so its boot slice could not be staged at all. `fs_base = 0xb7000` moves the
table below its program's scratch map and buys 290,816.

| | |
|---|---|
| `fs_base = 0xb7000` | optional key in `project.toml`; absent = `os.h`'s `OS_FS_TABLE_DEFAULT` (`0xbf000`), so every project that does not set it is byte-for-byte unchanged |
| `OS_FS_STAGING_OFFSET` | the **distance** from the table to the raw bytes (`0x1000`), never a second address — one key places both halves, and the table can never be put over its own staging area (`os.h` asserts the 32 entries fit inside the gap at compile time) |
| `emu.OS_FS_TABLE` / `emu.OS_FS_STAGING` | the resolved addresses every Python guard, diagnostic and `stage_files()` call reads. `harness.OS_FS_TABLE` / `harness.OS_FS_STAGING` serve them back live, through the same module `__getattr__` that serves `OS_HEAP_BASE`, and are in `harness.__all__` so a project's `from recreate_kit.harness import *` shim still carries them |
| `osh_set_fs_table()` | the oracle's entry point (`oracle/shim.c`), called once by `emu` at import |
| `os_set_fs_table()` | the candidate's (`src/os_fs.c`, swept into every candidate by `kit.mk`), called once by `harness` at import |
| `emu.install_fs_table()` | "tell one `.so`", the twin of `install_heap_base()` — each side supplies its own refusal, since they name different files and different rebuilds |
| `OS_FS_TABLE` / `OS_FS_STAGING` | unchanged in C, but **variable reads** off target rather than constant expressions — usable in an expression, not in a case label, an array bound or a static initialiser |

**Off target only, and that is deliberate.** `os.h` makes the two a variable *only* under
`-DOS_FS_TABLE_RUNTIME`, which `kit.mk` passes on both off-target builds (the candidate `.so` and
`liboracle.so`) and no project's own `.PRG` build passes at all. A target build links none of the
kit's `src/`, so an unconditional `extern` would fail at link for the one project that keeps this
model on target (`projects/joust`) — and on target there is nothing to place: real RAM, one program,
and no shared `liboracle.so`. `test/probe_build.py` and `test/kit_smoke_project.py` pass the same
`-D`, so every off-target build compiles the same `os.h`.

**Both entry points are required ABI only when the key is set**, exactly as the heap's are: an `.so`
predating them already reads the table at the default, so a default project is served correctly by
an old build, while a project that moved its window and was silently served the old address would
have every `os_fopen` look at a table the harness never wrote — on that side alone — and report
every file unstaged.

**Moving the window moves the arena's ceiling with it.** `emu.resolve_heap_limit()` clamps to the
*resolved* `OS_FS_TABLE`, not to `os.h`'s default, so a project that lowers `fs_base` and sets no
`heap_limit` cannot have its arena grow into the moved table; the other direction is
`_vet_os_memory_map`'s existing `heap_base >= OS_FS_TABLE` refusal. That is why the window needs no
arena clause of its own, and it is also why `install_heap_limit()` decides "is this the default?"
against what an `.so` already **carries** rather than against this project's resolved ceiling.

`harness._vet_staged_file_window()` checks the four collisions left, every one of them silent
otherwise (a staged file is a plain image write on both sides, so two corrupted runs compare equal):
the **poked-input block** below, the **framebuffer** (`OS_SCREEN_BASE`..`+0x7d00`), the **program**,
and the **stack guard** above — staging at or past which puts file bytes in the band the differential
drops. Every refusal names the value's source: `fs_base` in `project.toml`, or `OS_FS_TABLE_DEFAULT`
in `os.h` when the project set no key.

`test/test_fs_window.py` pins the key, every refusal, both installers' missing-ABI errors, the
ceiling interaction, and — through the miniature project — that a set of files the DEFAULT window
cannot hold is staged, opened and read back identically by the oracle's `Fopen`/`Fread` traps and by
the candidate's `os_fopen`/`os_fread`.

## Binding

`loader`/`emu` are plain top-level modules (so `import emu` keeps working everywhere), but they
hold **no** game constants: `project.load(<recreate dir>)` reads `project.toml`, puts
`recreate_kit/oracle/` on `sys.path`, and rebinds `loader.LOAD_BASE` / `loader.IMAGE_SIZE`
**before** `emu` is first imported — `emu.STACK_TOP` / `STACK_GUARD_LO` are derived from
`IMAGE_SIZE` at import time. Any standalone script that imports the oracle directly must
therefore bind first:

```python
sys.path.insert(0, str(REC.parents[2] / "tools"))   # reverse/tools
from recreate_kit import project
project.load(REC)                                   # REC = the project's recreate/ dir
import emu
```

`load()` is idempotent, and refuses to rebind to a *second* project inside one process.

### The image a differential starts from

`harness.make_image()` copies a base image and writes a case's pokes into it, and
`harness.differential()` is built on that copy — so the base is what every case in a project is
verified against. It is `harness.BASE_IMAGE`, the `.PRG` loaded and relocated, by default.

**That default is wrong for a program whose own startup writes state before its functions run.**
Bubble Ghost's crt0 ends by calling `init_globals`, which writes some 15,700 bytes of non-zero
initialisers into a bss the loaded image holds as ZEROES — so a case staged on `BASE_IMAGE` runs
against a program whose tables are all zero. It comes back green, about a machine that never exists
at run time.

`harness.set_base_image(image)` is the one way to change it. It validates the length against
`OS_IMAGE_SIZE`, stores a `bytes` copy (the image is shared by every case in the session), and
returns the previous one so a fixture can restore it:

```python
@pytest.fixture(scope="session", autouse=True)
def _differential_base_image(post_init_image):
    previous = harness.set_base_image(post_init_image)
    yield
    harness.set_base_image(previous)
```

**Autouse is the point, not a convenience.** A per-case argument is a thing a battery can forget,
and forgetting it does not fail — it silently runs the case against zeroed state, which is exactly
the false green the mechanism exists to close. One mechanism, so there is one place to look and no
second route with different behaviour. `harness.BASE_IMAGE` keeps its meaning either way: the `.PRG`
as loaded, which is what a battery reads when it wants the ORIGINAL's own bytes (an entry
prologue, a shipped table). `test/test_base_image.py` pins it.

## ROM mode: when the target is the operating system, not a program

The kit's default shape is a game: a `.PRG` loaded at `load_base` into a 1 MB image, with a MODELLED
TOS around it — trap callbacks, a poked-input block at `$600..$660`, a Malloc arena, a staged-file
window. None of that applies when the binary under test **is** TOS. A ROM function's inputs are the
machine's own RAM, its `trap #13` must be taken through the image's real vector table, and its code
lives at `$fcxxxx`, far above any `image_size` a game ever used.

A project turns that on by declaring the **ROM binding** in its `project.toml` — four keys, all or
none (`project._rom_binding` refuses three out of four, because a partial one would bind the project
as an ordinary `.PRG` project with a missing file):

```toml
name       = "tos102us"
names      = "../names.txt"
lib        = "build/libtos102us.so"
rom        = "../../../tools/hatari/TOS102US.img"   # referenced in place; never copied
rom_base   = 0xfc0000
snapshot   = "build/boot_ram.bin"                   # a post-boot RAM image, captured once
stack_top  = 0x80000                                # a guarded band inside the machine's own RAM
image_size = 0x1000000                              # the whole 24-bit address space
```

There is no `prg` and no `load_base`: the image starts at address 0, which is the machine's RAM.

### What the image is, and how it is decoded

`loader.load_rom_image()` builds it: the RAM snapshot at 0, the ROM at `rom_base`, zeros between.
Byte `i` is still exactly what the 68000 sees at address `i` — but "inside the image" stops meaning
"memory", because the I/O page at `$ff0000` is numerically inside it. `emu` installs the map into
the oracle (`osh_rom_window`) and `shim.c` decodes in this order:

| address | served by |
| --- | --- |
| `< ram_end` (the snapshot's length) | the image, exactly as a `.PRG` project's RAM is |
| the PSG ports, then os.h's `OS_HW_*` slots, then the `OS_HW_IO_*` blocks | the seeded PSG / hardware read models and the hardware WRITE ledger |
| `[rom_base, rom_base + rom size)` | the image, **read-only** — a store is dropped and counted |
| anything else | off-image: 0 on a read, dropped on a write — and a READ of the I/O page is counted, which is what the refusal below is built on |

Off ROM mode the window is empty and `ram_end` is the image's length, so every one of those paths is
byte-for-byte the path it always was. `test/test_rom_mode.py` pins both directions from C.

**The CANDIDATE's buffer holds the ROM too, and the diff covers it.** The oracle drops a store into
the window, so nothing the oracle does can differ there — but the candidate is C over a plain
bytearray, where a stray store lands and stays, and that difference is visible only if the ROM is
both in its image and inside the compared spans. It is also what a core READS: the ROM's own tables
(the BIOS/XBIOS dispatch tables, the fonts) are data a reconstruction is entitled to walk, exactly as
the original does.

### What is NOT modelled, and why that is the point

**No TOS trap model.** `shim.c` neither patches the vector table nor dispatches on its magic PCs, so
a `trap #13` is taken by Musashi's own exception processing into whatever the image's vector table
names — the ROM's real handler. That is the whole reason to run a ROM function in place. It also
means the poked-input block, the Malloc arena and the staged-file window cannot be reached by
anything, which is why `harness._vet_os_memory_map` hands over to `_vet_rom_memory_map` here. The
claim is re-tested rather than trusted: `emu._vet_rom_mode_is_modelless` refuses any RUN whose
oracle served ANY modelled trap — a bare `emu.run` included, since a run through the model describes
nothing about the ROM whoever made it — and the builders that stage that state (`console_key`,
`psg_regs`, `stage_files`, …) are refused outright.

`image_size` is free to be the whole address space — but **os.h's `OS_IMAGE_SIZE` must equal the
machine's RAM**, i.e. the snapshot's length, because it is the bound the CANDIDATE's kit sources use
for every image access (`os_in_image`, `os_sched_store`). `_vet_rom_memory_map` refuses a binding
where it does not, and checks that the declared `stack_top` band lies inside that RAM.

**The seeded models stay, and an I/O byte outside them is REFUSED rather than answered.** A case
declares the bytes it expects exactly as a game case does, an undeclared modelled read still refuses
the run in `differential()`, and hardware writes are still ledgered and compared. What is new is the
rest of the page: a read of an I/O address no model serves is counted by the shim and refused by
`harness._vet_rom_io_reads_are_modelled`, naming the address. It has to be — a game touches few
registers, but an operating system touches the whole machine, and the silent 0 those reads used to
answer is the same 0 on both sides, so a `Getrez` reading `$ff8260` would verify green against a
byte the model invented.

**The remedy is a case's, not a model change: `io_seed={0xff8260: 0x02}`.** Phase 7's named set is
one `os.h` slot per address, which is the right shape for a game and a bottleneck for an operating
system — so the DECLARED I/O MAP (TRAP_MODEL.md, "Phase 15") lets a case declare ANY byte of the
page, routing the named models' own addresses to them, and both cores serve exactly those bytes on
every read. A reconstruction reads them through `hw.h`'s `io_read8`/`io_read16`/`io_read32`, which a
target build supplies as the real volatile access; the served reads land in an ordered ledger the harness compares, so a read
whose result the routine discards is still a compared fact. The refusal above and the declaration
that answers it cover the SAME set of addresses, deliberately — a refusal whose remedy does not
exist would be worse than the silent 0 it replaced.

### The stack, and the region the diff drops

`STACK_TOP` is `image_size - 0x100` for a `.PRG` project, which in ROM mode would be the I/O page —
so a ROM project declares `stack_top` instead, a band inside the machine's real RAM. The kit reserves
`[stack_top - 0xf00, stack_top + SENTINEL_SLOT_BYTES + STACK_ARGS_BYTES)` around it and drops that
band from the diff — ONE formula in both modes, because the machine stack grows DOWN and the only
thing ever written above `stack_top` is the harness's own sentinel and a case's staged frame.
`harness.diff_spans()` is therefore two spans in either mode: a `.PRG` project's image continues for
228 bytes above the band, and those bytes are compared like any others.

Pick a band the snapshot leaves empty, and pin that it is empty — the oracle writes a machine stack
there and the candidate does not, so anything live in it would be invisible on one side.

**Dropping the band is only sound while the oracle uses it purely as a stack**, so `differential`
reports every write inside it that the run's own frame does not explain
(`harness._stray_stack_writes`). The frame is the scratch below `STACK_TOP`, the sentinel return
slot at it, the `STACK_ARGS_BYTES` of CALLER FRAME AREA above that — which belongs to the callee,
since an Alcyon/DRI C routine writes its own arguments back into it and a case entering a routine
mid-body puts its synthetic frame base there, neither of which the candidate can reproduce through
the image — and whatever else the case itself poked. A write ABOVE the frame area is ordinary
program output in COMPARED image, so it reds as a byte difference naming both sides' values rather
than through this guard at all. `STACK_ARGS_BYTES` is a MEASUREMENT pinned in BOTH directions
(`test/test_stack_band.py`): the deepest write no case stages, which is also where the dropped band
now ends — too small and a callee's own frame locals red as masked output, too large and that many
bytes of real image stop being compared at all.

### Capturing the snapshot

That is the project's job, not the kit's: it is one headless Hatari boot of the original ROM, stopped
at a documented instant, `savebin`ned. `projects/tos102us/recreate/tools/boot_snapshot.py` is the
worked example, including the part that matters — capturing TWICE and recording exactly which bytes
two boots disagree about, so no case can rest on one.

## Building, and what `clean` owns

`liboracle.so` and Musashi's generated opcode tables (`oracle/build/`) are **shared**: every
project's `make test` links the same file. So the two `clean` targets are deliberately split —

| command | removes |
| --- | --- |
| `make clean` in `projects/<game>/recreate/` | that project's `build/` only |
| `make -C tools/recreate_kit clean` | the shared `oracle/build/` (affects every project) |

`make oracle` from a project rebuilds the shared oracle without running the suite. The oracle is
compiled **without** the project's `include/` on the header path, so a stray include can never make
the shared artifact game-specific — make's timestamps could not detect that across projects.

**Every `.c` under `src/` is linked into the candidate**, one directory deep: `src/*.c` and
`src/*/*.c`. A small project keeps its cores in `src/` alone; one big enough to have COMPONENTS
keeps one directory per component (`projects/tos102us` has `src/xbios/`, and will have `src/bios/`,
`src/gemdos/`, …), and either shape builds with no rule of its own. A component nested deeper than
that is not compiled — and would surface at `dlsym` as the candidate's ABI error rather than as the
missing source, so keep the layout flat.

## Beyond the differential: running the cores on target

The differential proves the cores produce the original's **memory image**. It cannot prove the game
runs, because everything the oracle models as a no-op — the palette, the shifter, the PSG, the IKBD,
TOS's own variables — leaves no image bytes to compare, and a reconstruction can be byte-perfect
under `make test` while displaying nothing. Building the verified cores into a real GEMDOS `.PRG`
and running it under Hatari is a separate discipline with its own failure modes, and both worked
examples (`projects/buggyboy/recreate/render/atari/`, `projects/joust/recreate/atari/`) are on the
kit. Read [`docs/on-target-execution.md`](../../docs/on-target-execution.md) before starting one —
in particular "The observable surfaces", which enumerates the six things an on-target run can be
watched on and states the rule this workspace's pre-commit gate now carries: every on-target change
names the surface that would catch its failure, and a change that names none has found something.

## Asm twins: the original's own instructions, diffed against the C

A project whose port is correct but too slow has one lever nothing else reaches. Its C cores are
already proven equal to the original, and the original's instructions are in its `out/prg_dis.txt` —
so the fast version of a hot core is not something to invent, it is something to COPY, and **a
faithful transcription is 1.00x by construction**.

The kit carries the game-agnostic half of that:

| | |
|---|---|
| `asm_twin.py` | loads a project's assembled twins and runs one under Musashi over the same image its C cores use, with the C ABI: `AsmTwins.call(image, symbol, *args)`. Also the CALLBACK DOOR (below), the callee-saved check, and `elf_symbols()`, the one parse of `nm`'s output |
| `kit.mk`'s `$(ASM_OBJ)` / `$(ASM_ELF)` / `$(ASM_BIN)` | assembles `src/asm/*.S` — one object per source, then one blob — and makes `test` and `guarded` depend on the blob, so a suite can never run against a stale one |

The per-source objects are kept rather than assembled straight to the blob, and that is not tidiness:
a test that asks what one `.S` defines has to ask **its own object**. The linked blob is one flat
symbol table, so two files that both `.equ SCREEN_ROW_BYTES` collapse into whichever the linker
emitted last — measured, with a wrong value in one file vouched for by its neighbour's correct one.

A project acquires the whole machinery by creating a `src/asm/` and writing a `.S` in it; `ASM_SRC`
is a wildcard, so a project without one gets no rule and no prerequisite. Neither file names a game.

The comparison is **twin against C core over the whole image**, not against a second oracle run: the
C is already known equal to the original on those cases, so the chain is `original == C == twin` with
both links byte-exact. Two things the runner does that a plain image compare would not:

* **the image is staged at a NON-ZERO base.** A twin that ignored its image-base argument and
  addressed the game's globals absolutely — which is the shape the original itself uses, since the
  original IS the image — would pass at base 0 and fault the moment the target handed it a pointer;
* **zeroed bands on BOTH sides of the image are checked after every call.** The comparison against
  the C stops at the image's last byte, so a span one row too generous — forwards or backwards —
  writes where there is nothing to differ. This is the twin-side stand-in for the guarded sweep
  below, which reaches only the C; it is two-sided for the same reason that one is, and everything
  from the call frame to the sentinel is covered bar the image itself, so an overrun wider than a
  band does not sail past it either.

Two more things the runner does, both because a twin has no other surface for them:

* **a twin that CALLS a verified C core reaches it through the CALLBACK DOOR.** Off target those
  cores are host code in the candidate `.so`, and two of the seams they sit on are modelled
  host-side, so linking them into the m68k blob cannot work either. So a call site traps out of the
  emulator at a fixed address band and the harness services it by calling the host function. The
  project supplies the table — `AsmTwins(asm_dir, image_size, callbacks={id: DoorCallback(name,
  nargs)}, lib=harness._lib)` — and the kit half names no game. It is a **plain C call**, including
  what a C call wrecks: the declared arguments off the emulated stack, a host pointer substituted for
  the image base, the result in D0, the caller-saved file and the condition codes destroyed as the
  real core destroys them (**bar X, which ALTERNATES per callback** — `TRAP_MODEL.md` says why), and
  the stub's `rts`. An unregistered slot **refuses**. See
  `TRAP_MODEL.md`, "The callback door", for the band, the stub shape and why the door charges no
  cycles;
* **the callee-saved file is seeded and required back.** `%d2`-`%d7`/`%a2`-`%a6` enter with a
  distinctive value per register and a twin that loses one fails by NAME. Nothing else off target
  could see it — the image, the return value and the cost are all a correct twin's — and on the
  machine the caller's register is simply gone (`TRAP_MODEL.md`, "The callee-saved file").

`projects/zynaps/recreate/src/asm/` is the worked example, and its `README.md` is the recipe: where
the seam goes (a `ZY_SCROLL()`-style macro at the CALL SITE, so the C reference stays compiled), how
the build gate proves the twins are what the game actually calls, and the four checks a new twin
needs. Zynaps' scroll path came out at 1.002x-1.014x of the original's per-call cycles.

## Tier 3's numerator: the cores cross-compiled, measured, and proved again

`emu.run` reports what the ORIGINAL cost — instructions and 68000 cycles for one call — so a
project's denominator is a measurement rather than an estimate. `rom_bench.py` is the other half for
a **ROM project**: it builds the same C the shipped ROM will carry (`m68k-elf-gcc`, the target
build's own flags), stages it in a free span of the same post-boot snapshot, and enters one core
through `emu.run_bench` over the same case. Two costs, one instrument, one image.

| | |
|---|---|
| `rom_bench.py` | loads a project's cross-compiled blob and runs one core: `RomBench().measure(entry, symbol, args=…, regs=…, pokes=…, psg_seed=…, hw_seed=…, io_seed=…, returns=…, schedule=…)` → a `Measurement` whose `.ratio` is `recreate / original`. The seed set is `harness.differential`'s, so a case runnable there is runnable here. `measure_transcription(caller, symbol, regs, …)` is the same for a `src/**/*.S` routine, held to the WHOLE register file instead of a return value: both sides are entered at a CALLER the case staged, and each reaches its own handler through `abi.FIRST_ARG` — `staged_entry` comes off the ORIGINAL's column (what its run spends getting there and ours never pays) and `shared_entry` off BOTH (the staged caller they run identically). `_bench_io_seed` is how one `io_seed` reaches two models: the Phase-7 NAMED half is already armed by the ORIGINAL's `emu.run` and persists, so our run is handed only the rest — without the split a core that reads a named slot could not be measured at all |
| `kit.mk`'s `$(BENCH_ELF)` / `$(BENCH_BIN)` | compiles `src/**/*.c` **and `src/**/*.S`** (both depths, the same sweep) plus `bench/entry_probe.c` with `m68k-elf-gcc`, linked at `bench_base`, and makes `test` and `guarded` depend on the blob so a gate cannot run against a stale one |
| `bench/entry_probe.c` | one empty function, so the oracle's own entry overhead is MEASURED rather than declared |

Opt-in with **two** things, neither defaulted: `bench_base` in `project.toml` (where the blob goes
inside the machine's RAM — the rules exist only for a project that declares one) and `BENCH_CFLAGS`
in the project Makefile, set before including `kit.mk`. The flags are the project's because they must
be the **shipped build's own**: a numerator measured under flags nobody ships is a number about a
program nobody runs. `projects/tos102us/recreate` is the worked example — its `atari/target.mk` holds
one definition of those flags *and of the include paths*, which the ROM build and this one both read.

**The opt-in is decided by a `grep` and only its VALUE by the Python probe**, and that split is
load-bearing: the probe prints nothing for a project with no `bench_base`, and it also prints nothing
when it cannot run at all (no venv yet, `PY` overridden), which is the same output for "no numerator
wanted" and "the numerator is broken". Deciding the block on the probe alone silently dropped the
blob, the `test:` prerequisite and the gate together; `make -n test PY=/nonexistent/python` is the
repro, and it is now a `$(error)`.

**Three tenants share one free window, and they are declared in one file so a vet can compare them**:
the run's stack (`stack_top`), the blob (`bench_base`), and the band a CASE stages buffers and stub
routines in (`staging_base` / `staging_bytes`, read by the project's `test/staging.py` rather than
spelt there a second time). `RomBench` refuses any overlap, any band past the end of RAM, a blob
linked somewhere other than the key says, a snapshot that is not empty where the blob goes, and a
case that pokes inside the blob's span — each on every construction, because every one of them is
invisible when it is wrong.

**A cost without a proof is not a measurement**, so every row is also a SECOND DIFFERENTIAL. The
cross build is a *third* build of the reconstruction — the host `.so` Tier 1 proves, the shipped ROM,
and this — and [`docs/on-target-execution.md`](../../docs/on-target-execution.md)'s bug class 6 is
target codegen going wrong where the host build is right. So `measure()` runs the original and our
build over one case and requires: the whole image equal outside the oracle's stack band and the
blob's own span; the return value equal **at the width the C signature declares**; every
callee-saved register handed back (`asm_twin`'s seeds, for `asm_twin`'s reason); **all four
off-image streams** equal in order — the ordered PSG accesses, the ordered modelled-hardware reads,
the ordered reads the declared I/O map served, and the ordered hardware writes, which is the same set
`harness.differential` compares; and **no refusal tally set on either side** — again the same set,
so a row is never measured over a run the model answered with something it invented, nor over a
ledger that silently truncated. Measured sharp: a one-line mutation of a core reddens on the image, a
target-only mutation of a `psg.h` shadow reddens on the return value, and a shadow reading the wrong
port reddens as an unmodelled I/O read naming `$ff8802`.

**A ROUTINE THAT BUSY-WAITS IS MEASURABLE, and its row has a cross-check of its own.** `schedule=`
carries the SCHEDULED WRITE model (Phase 8) to both doors of one case — the agent's store is what
ends the wait, and without it neither the ROM's loop nor the cross-compiled build's would return. Its
entries must be **READ triggers**, keyed to the ADDRESS the wait spins on rather than to a PC:
`$fc07dc` is an instruction in the ROM and the blob's own spin is wherever the compiler put it, while
`_frclock` is the machine's and identical on both sides. `run_bench` refuses a `pc` or `insn` entry by
name, and an entry that never comes due raises naming the reads each side made rather than spending
`max_insns`. The row's own honesty is `_vet_same_wait`: the store lands from one list at both doors,
so a build that spun a different number of times leaves the same image, return value, register file
and streams — the READ COUNT at each site is what separates them, and it is Tier 1's arrivals-against-
polls comparison in the one shape a compiled build can be held to. Measured: with a target-only
`sched.h` shadow reading twice per iteration, the row at an ODD arrival count is caught by that count
alone (4 reads against 5) with the ratio under the bar, and the row at an EVEN one survives
everything — which is Phase 8's documented aliasing hole, and why a wait is priced at more than one
`nth`.

**The entry overhead is measured AND the probe is checked**: the empty function must have executed
the reset's phantom instruction and its own `rts` and nothing else, or the overhead every ratio is
net of would be carrying a prologue — the refusal names the flag (`-O0`, `-fno-omit-frame-pointer`)
that would cause it.

**The CALL is one shape for this runner and for `asm_twin.py`**, so its shared half lives beside
`asm_twin.CALLEE_SAVED_SEEDS`: `require_built`, `blob_entry`, `stage_stack_args`,
`vet_callee_saved`, `vet_blob_intact`. A check tightened for one runner is tightened for both.

**The register FILE is not compared for a C core, and that is a decision.** The m68k SysV ABI
promises a `uint8_t` result in the low byte of D0 and nothing above it — measured: GCC emits `move.b
$ff8800,%d0` for `xbios_giaccess` and leaves the caller's high word there, where the ROM's own
`moveq #0,d0` cleared it — and D1/A0/A1 are scratch a C compiler owes nobody. Requiring the
original's whole file back would be requiring a TRANSCRIPTION.

**...which is `measure_transcription`, for the routines that cannot be C.** An exception handler is
entered with a 68000 exception frame, moves the stack pointer between the supervisor and user
stacks, and owes its caller a register file — including the registers it does NOT preserve, which is
the d2/a2 class in `docs/on-target-execution.md`. `asm_twin.py` cannot run such a routine (it stages
the image at a non-zero base on purpose, and ROM code is absolute), so a ROM project carries its
transcriptions as `src/<component>/*.S` in the same blob and proves them through this door instead:
both sides entered with the SAME register file, which the case must name in full, and the WHOLE of
`D0-D7/A0-A6` required back equal, alongside the same image, streams and refusals every row gets.
The handler each side reaches is the longword at the first argument slot — poked for the original,
written as `arg0` for ours, and inside the band the diff drops, which is how ONE image serves two
handlers. `TRAP_MODEL.md`, "The BENCH door as a TRANSCRIPTION differential", has the whole
arrangement and why a real `trap` cannot be used for it.

**It is `asm_twin.py`'s mirror image, and the two are mutually exclusive by construction.** That
module stages the image at a NON-ZERO base so a twin addressing it absolutely is caught, and
therefore refuses a ROM project, whose code is absolute by construction; this one stages the image at
0 because in ROM mode that IS the machine, hands the cores 0 as their image base, and refuses
everything but a ROM project. A `.PRG` project's numerator is a third arrangement again — the recon
in its own memory with the game image beside it — and has two worked examples,
`projects/zynaps/recreate/atari/bench_tier.py` and `projects/buggyboy/remaster/tools/bench.py`.

**Rebuild before you trust a mutation.** The blob is one `make` rule over a handful of sources, so a
mutation and its re-link inside the same filesystem second leave the PREVIOUS blob on disk and the
suite measuring it (`docs/agent-playbook.md` §10 — it happened while this was being built). Delete
`build/bench/` and rebuild before reading any mutation's verdict.

## The guarded-image sweep, and the seam it hangs on

The oracle puts every address on the 68000's 24-bit bus and then bounds it against the image: an
access outside reads as zero and a write is dropped (`oracle/shim.c`). A reconstruction that indexes
its `uint8_t *image` directly does **neither**, so an address the game computed out of its own
memory — a record pointer, a descriptor, a map cell — reaches the HOST HEAP. The two cores then agree
only while whatever is next to the buffer happens to hold what the image would have. That is
invisible to the differential in both directions: it passes when the heap is quiet, and it kills the
pytest worker when the page is not mapped.

```bash
make guarded    # from any projects/<game>/recreate — kit.mk's target, so every project has it
# ...which is this, and `kit.mk` is where the incantation lives rather than here:
PYTHONPATH=<reverse>/tools .venv/bin/python -m pytest -q -n auto -p recreate_kit.guarded_image test
```

**Not part of any `make test`**, and `make guarded` is deliberately its own target rather than a
step of that one, because a fault is a dead worker and not a named assertion. Under
`-n auto` xdist names the test that was running and carries on, which makes the run a CENSUS of the
class rather than a gate; what it finds gets pinned afterwards by an ordinary differential case. It
cannot see a raw access that stays INSIDE the buffer. Darwin/BSD only — it refuses at
`pytest_configure` elsewhere rather than failing on the first differential, and the docstring says
why. First use: Wonder Boy batch 43 phase C, 5 crashing cases of 6,140 before the fix and 0 after.

**`harness.candidate_image` EXISTS FOR IT, and that is the point of the seam.** It is the one place a
candidate's mutable image is allocated — `differential`, its attribution pass and a project's own
candidate-only runner all go through it — so the plugin replaces one function instead of wrapping
every glue and every runner. A project's shim does `from recreate_kit.harness import *`, which
*copies* the name, so the plugin rebinds every module holding the original and **counts** the guarded
calls: a sweep that guarded nothing, or almost nothing, refuses to exit 0. Both halves of that
sentence are scar tissue from its own first run.

## The kit's own tests

`make test` in this directory runs `test/` — checks that belong to `tools/` rather than to any
one game: the cross-language pin between `prg_dis.py`'s and `AtariOsTrapAnnotate.java`'s XBIOS
trap tables, `prg_dis`'s 68000 decoder (reference encodings + an opcode-space sweep for
impossible instruction forms), the C-vs-Python pin on the TOS memory map above,
`project._bool_flag`'s refusal of a non-boolean waiver flag (for **every** waiver flag, checked
against `project.load` itself so a new one cannot ship untested), `rom_bench`'s decidable parts (what
a `bench_base` may be, that a blob's span covers the `.bss` its flat binary does not, that a ratio
comes out net of the entry overhead, and every refusal that decides WHERE a blob may sit — the link
address, the three bands' tenancy, an occupied snapshot — plus the pin that keeps kit.mk's blob paths
and `rom_bench.py`'s the same three names; the end-to-end proof is the project's own
`test_tier3.py`, since this directory binds no project), `os_map`'s overlap geometry, and
`stubs.py`'s shared building blocks — the GEMDOS `Malloc` probe's *encoding* (a stub with the wrong
selector is still a serviced trap, so the run goes green having asked a different question) and the
span seeder's merge (two pokes over one byte look like two seeded regions and are one).

Four of them pin the **oracle's own behaviour** and so need its sources, which a bare checkout does
not have (`oracle/musashi/` is a gitignored clone): `test_entry_state.py`, `test_reported_regs.py`,
`test_psg_model.py` and `test_hw_model.py` compile `shim.c` themselves and drive `osh_run` from C —
`harness`/`emu` bind a project's candidate `.so` at import, and this directory binds no project, so
the oracle is unreachable from Python here. All **skip** rather than fail when those sources are
absent, and all compile the shim rather than link the shared `liboracle.so` so that a reverted
decision cannot hide behind a stale artifact — one build, in `test/probe_build.py`, so the four
cannot disagree about the flags. What they pin is in [`TRAP_MODEL.md`](TRAP_MODEL.md): the forced
entry SR; the register set every run reports back (`D0..D7`/`A0..A6` — the observability window a
differential sees through); and the two seeded read models, whose probes also link `src/psg.c` /
`src/hw.c` so they can run the **candidate** side against the oracle's — a miniature differential,
with mutant reconstructions as its negative control.

Four more — `test_psg_differential.py`, `test_hw_differential.py`, `test_write_ledger.py` and
`test_base_image.py` — go one step further and run the **real harness**: `test/kit_smoke_project.py` builds a throwaway project in a temp directory — a
hand-assembled `.PRG`, and a candidate `.so` from `test/kit_candidate.c` plus `src/` — binds the kit
to it, and both suites make actual `harness.differential()` calls through it. That is the only way to
exercise the code that *compares* the two sides, since it lives in `harness`. They **skip** without
the shared `liboracle.so` or a C compiler, and they share ONE binding: `project.load` freezes it
process-wide, so `kit_smoke_project.bind()` is memoized and whichever suite asks first builds it —
which is also why this directory's `make test` runs serially.

`test_write_ledger.py` is the newest of the three and pins a SPLIT rather than a model. `shim.c`'s
write ledger saturates at `MAX_WRITES` and counts nothing past it, so a run that overflows reports a
truncated write set as a complete one; `emu.run` therefore REPORTS the saturation
(`out_regs["writes_truncated"]`) without refusing — the run's memory and registers are exact, and a
bare caller that never spends the write set is entitled to it — while `harness.differential`
REFUSES, because a differential is where a write set becomes a claim. Both arms are cases, because a
"fix" in either direction reads as tidying. The cap itself is exported (`osh_max_writes`) so
`emu.py`'s mirror is checked at import rather than kept by hand: it is sized from the largest real
run in the workspace (BuggyBoy's `unpack_graphics`, 1,315,224 events), which overflowed the previous
cap by a quarter and had been comparing against a truncated set unnoticed until this guard landed.

Everything else must keep running in a bare checkout — no oracle build, no candidate `.so` — which is
why the poked-input geometry was moved into `os_map.py` to be tested here at all.

They need only pytest — but the kit has no venv of its own, so **`PY` defaults to BuggyBoy's**
(`../../projects/buggyboy/recreate/.venv/bin/python`). That is a known wart: the game-agnostic kit
points at one game to find an interpreter. Any pytest works — `make test PY=/path/to/python`.
