# Reconstruction status — TOS 1.02 US

**As of 2026-09-14.** Wave 1 is merged: the ROM is bootstrapped in Ghidra, the three evaluation tiers
each have a working instrument, and the first two XBIOS functions are verified with sharp differentials.
Read `../README.md` first for the three tiers a component is held to; `test/test_status.py` pins the
counts in this file against its rows.

## Components

| component | Tier 1 (functions verified) | Tier 2 (conformance ledger) | Tier 3 (cycle ratio) | state |
|---|---|---|---|---|
| boot | 0 | — | — | NOT STARTED |
| bios | 8 | — | 1.06–1.88x, all rows priced (`make bench`) | STARTED |
| xbios | 11 | — | 0.23–2.29x, all rows priced (`make bench`) | STARTED |
| gemdos | 0 | — | — | NOT STARTED |
| vdi + linea | 0 | — | — | NOT STARTED |
| aes | 0 | — | — | NOT STARTED |
| desk | 0 | — | — | NOT STARTED |
| data | — | — | — | NOT STARTED |

## Verified — xbios (11)

Each row is one function of the ORIGINAL ROM, run in place at its own address over the post-boot RAM
snapshot and compared byte-for-byte against the reconstruction (`../README.md`, Tier 1). The cost
column is the ORACLE's own count for one call — the instructions it executed and the 68000 cycles
they took — and the TIER 3 column is the same C cross-compiled by `m68k-elf-gcc` with the shipped
ROM's flags, run under the same oracle over the same case (`bench/tier3.py`; `make bench` prints the
table, `test/test_tier3.py` gates it at <= 1.10). Both are as the oracle reports them, including the
1 instruction / 40 cycles its reset charges before either entry; the ratio is net of that on both
sides. Each ratio is also a SECOND DIFFERENTIAL — the m68k build must leave the same image, return
value, callee-saved file and chip traffic as the ROM.

| Addr (ROM) | Name | Cases | Cost (insns / cycles) | Tier 3 (recreate / original) | Status | Verification |
|---|---|---|---|---|---|---|
| `0xfc1510` | `Random` (XBIOS $11, `src/xbios/random.c`) | 19 | 44 / 810 seeding, 39 / 710 advance | **0.62** seeding (30 / 520), **0.67** advance (25 / 488) | ✅ verified | both branches of `tst.l random_seed`: the snapshot's own unseeded machine, and seven system-tick values through the `asl.l #16` / `or.l` seeding arm including ticks with the high word set; eight seeds across the SIGNED 32x32 helper's edges (either operand negative, both, and the two values `neg.l` leaves alone); the 24-bit projection asserted against the state the diff compares byte-for-byte; a 64-case fuzz over seed x tick. The ROM's call into Alcyon's `lmul` at `$fc4b28` executes in the ROM like any other instruction, so this is also the pin that ROM-internal calls work. Poison on every parametrized case |
| `0xfc2ea4` | `Giaccess` (XBIOS $1c, `src/xbios/giaccess.c`) | 49 | 17 / 260 read, 18 / 270 write | **0.60** read (14 / 172), **0.74** write (16 / 210) — incl. the IPL bracket (`ipl.h`) | ✅ verified | all sixteen registers the four-bit select latch can name, read and written, against a declared entry file with a distinct byte per register — so reading the WRONG register diverges on the value rather than by luck; the ordered PSG access ledger compared on every case (the chip is off-image, so nothing in the memory diff could see it); five data words proving only the low byte reaches the port; eleven `reg` words proving the direction bit and the register both come from the LOW byte alone. A decoy planted at `$ff8800` pins that the ports reach the seeded model rather than the image, which is the claim ROM mode has to get right. Poison on every case |
| `0xfc0aac` | `Getrez` (XBIOS $04, `src/xbios/getrez.c`) | 263 | 5 / 82 | **0.95** (4 / 80) | ✅ verified | the three ST resolutions the shifter really sits in, each declared with `io_seed`; a 256-case sweep of every byte the register could hold, pinning `and.b #3` against the `$07`/`$ff`/`== 2` variants; a decoy planted at `$ff8260` proving the register reaches the declared I/O map and not the 16 MB image; the declared/undeclared PAIR over one routine — undeclared it refuses by address and prescribes the `io_seed`; `hw_seed` refused by name as the wrong door. THE FIRST RECONSTRUCTION IN THIS PROJECT TO READ A HARDWARE REGISTER. Mutation 4/4. Poison on the parametrized cases |
| `0xfc0aa6` | `Logbase` (XBIOS $03, `src/xbios/logbase.c`) | 7 | 3 / 72 | **1.50** (4 / 88; +16 cyc = the image-pointer load, accepted) | ✅ verified | the snapshot's screen at `_memtop`; six bases incl. values no Setscreen would store — the routine reports, it does not validate |
| `0xfc28f6` | `Iorec` (XBIOS $0e, `src/xbios/iorec.c`) | 12 | 5 / 98 | **1.48** (9 / 126; accepted: image pointer) | ✅ verified | the three rings, asserted distinct and tied to the addresses Bconstat's drivers walk; devices 3-5 reading `Rsconf`'s opening instructions as addresses (unbounded, reproduced); the low-word index; and device `$2000`, whose `$8000` index SIGN-EXTENDS to `$fba902` below the table — the two candidate addresses asserted to differ |
| `0xfc302e` | `Keytbl` (XBIOS $10, `src/xbios/keytbl.c`) | 18 | 12 / 224 install | **0.99** (16 / 222) | ✅ verified | seven install/keep combinations over three INDEPENDENT arguments (the shape Kbrate does not have), each field read back from the oracle's ledger and each skip asserted as a non-write; `tst.l`/`bmi` only — 0 and $7fffffff install, every bit-31 pointer keeps; the struct address as a constant result |
| `0xfc15f8` | `Protobt` (XBIOS $12, `src/xbios/protobt.c`) | 41 | 2283 / 34224 format, 2328 / 35026 random serial | **0.23** format (954 / 8066), **0.25** random serial (990 / 8638) | ✅ verified | the 255-word final sum against the 256-word probe (two deliberately different loop lengths); the non-executable sector missing $1234 by exactly one; the three-byte serial low byte first with the frame slot read back from the ORACLE's ledger; a serial above $ffffff replaced through a real call into `Random`, over four ticks; the four BPB prototypes, a negative type, type 4 past the table, and disk type 1725 whose `muls.w #19` = `$8007` reads BELOW the table; the whole-Format composition; the buffer wherever the caller points |
| `0xfc4698` | `Cursconf` (XBIOS $15, `src/xbios/cursconf.c`) | 26 | 10 / 144 blink, 11 / 144 get rate | **0.90** get rate (10 / 134), **2.29** blink (26 / 278; accepted: arm selection vs `jmp TABLE(pc,d0.w)` — the first perf lever) | ✅ verified | the six RAM arms plus the out-of-range return, each at its truncation boundaries; what each arm leaves in D0 read OUT OF THE ROM's jump table rather than written down ($0010/$0016/$001c for the arms that set no result); the rate and the spare proved to be different bytes; and the WIDTH — the caller's high half surviving the `move.w` arms and cleared by the `moveq #0,d0` ones. Arms 0/1 (the cursor renderer) HALT rather than return (`recreate_not_reconstructed`) |
| `0xfc305a` | `Bioskeys` (XBIOS $18, `src/xbios/keytbl.c`) | 6 | 5 / 128 | **1.18** (6 / 144; accepted: image pointer) | ✅ verified | the three ROM tables identified independently by the keyboard row each spells at scancode $10; installed over three staged tables; each field cleared separately (three stores, not one copy); and all three stored even when already correct, attributed by the poison pass. `void`: the routine sets no result |
| `0xfc309a` | `Kbrate` (XBIOS $23, `src/xbios/kbrate.c`) | 16 | 5 / 90 read, 11 / 156 write | **1.80** read (9 / 130), **1.28** write (13 / 188; accepted: image pointer) | ✅ verified | the pair reported as one word in the ROM's order; six pairs storing both low bytes; a negative repeat leaving its byte alone; the COUPLING — three negative-delay pairs (incl. `$ff80`, whose low byte looks positive) skipping BOTH stores; the caller's high half of D0 surviving; and storing the pair already held |
| `0xfc097e` | `Supexec` (XBIOS $26, `src/xbios/supexec.c`) | 11 | 5 / 92 | **1.00** (5 / 92), both cases | ✅ verified | five results passed through untouched; the staged routine's writes passing through; a bare `rts` leaving the caller's D0 alone; the routine run being the one 4(sp) names, with a DECOY staged at a fixed address on both sides. The stack-frame claim (`jmp` not `jsr`) is the ORACLE's alone off target; on target the body IS the `jmp`, and Tier 3's second differential pins it once this has a bench row |

## Verified — bios (8)

The BIOS wave's first set: the trap #13 leaves that read and write RAM only (the drivers that poll
the MFP or an ACIA wait for the declared I/O map to reach them — `test_bios_bcostat.py` pins that
those table entries are still hardware routines). Every unreconstructed arm HALTS on both builds
(`recreate_not_reconstructed`: abort on the host, `trap #7` on the 68000) rather than returning a
plausible value. Cost as above (incl. the reset's 1 / 40); Tier 3 rows pending `bench/tier3.py`.

| Addr (ROM) | Name | Cases | Cost (insns / cycles) | Tier 3 (recreate / original) | Status | Verification |
|---|---|---|---|---|---|---|
| `0xfc0a46` | `Getmpb` (BIOS $00, `src/bios/getmpb.c`) | 13 | 13 / 254 | **1.14** (14 / 284; accepted: image pointer) | ✅ verified | both structures out of the oracle's write ledger; the descriptor rebuilt from `_membot`/`_memtop` over five TPAs incl. equal and INVERTED bounds (the `sub.l` is unchecked); the MPB written wherever the caller points; a second call rebuilding the first's descriptor; and the ORDER — an MPB laid at `_membot - 8` so `mp_rover` overwrites `_membot` before the routine reads it, which reds a hoisted read. Poison on every case |
| `0xfc0984` | `Bconstat` (BIOS $01, `src/bios/bcon.c`) | 29 | 15 / 178 empty, 14 / 176 ready, 8 / 126 no driver | **1.26** ring empty, **1.29** ring ready, **1.88** no driver (accepted: the driver dispatch is a compare chain vs the ROM's `jmp (a0)`) | ✅ verified | the table walk AND the driver it jumps into, per device: the snapshot's own drained rings; a head/tail sweep on the console's copy plus a pair on each of the other two (three separate ROM copies); equal head/tail whatever they hold; one ring filled at a time so a driver naming the wrong ring diverges; the five no-driver devices returning the dispatch's scratch through a marked D0; `lsl.w #2` proved by device `$4002` |
| `0xfc098c` | `Bconin` (BIOS $02, `src/bios/bcon.c`) | 30 | 30 / 376 console, 31 / 384 MIDI | **1.18** console, **1.16** MIDI (accepted: dispatch) | ✅ verified | the console's four-byte record and MIDI's one-byte one, each with its own head advance and its wrap-to-zero at the ring's size; MIDI's `$ffffff00 \| byte` over seven bytes; the two drivers reading their own ring; and the STORE ORDER — a ring whose buffer is pointed at itself, so the record read is the ring's own size and head words before the store changes them. Blocking is the ROM's real spin on both builds (a case stages the record; an empty ring runs the original to the oracle's cap) |
| `0xfc0994` | `Bcostat` (BIOS $08, `src/bios/bcon.c`) | 7 | 9 / 130 | **1.44** (14 / 170; accepted: dispatch) | ✅ verified | the console's `moveq #-1,d0` reached for device 2 and only device 2, with the four chip-polling drivers asserted still to be ROM routines (so the reason they are absent stays checkable); the three no-driver devices; `lsl.w #2` |
| `0xfc0a72` | `Setexc` (BIOS $05, `src/bios/setexc.c`) | 29 | 9 / 134 read, 10 / 144 install | **1.06** read, **1.06** install | ✅ verified | reconstructed from the DISASSEMBLY (one of COMPONENTS.md's 73 decompile failures): five OS vectors read back and asserted to be ROM addresses; every handler with bit 31 set a read; nine slots installed incl. vector 0; no bounds check ($400..$7ffc); the WORD index wrapping ($4000 is vector 0); and every slot the battery reaches declared as `CASE_SPANS` so the snapshot's mask is checked against them. Poison on every case |
| `0xfc0a8a` | `Tickcal` (BIOS $06, `src/bios/sysvars.c`) | 5 | 4 / 74 | **1.41** (5 / 88; accepted: image pointer) | ✅ verified | the snapshot's own calibration; the word read at the three boundaries a byte read or a sign-extending one would fail; the `clr.l` pinned against a caller that entered with a dirty D0 |
| `0xfc0a2e` | `Drvmap` (BIOS $0a, `src/bios/sysvars.c`) | 8 | 3 / 72 | **1.50** (4 / 88; +16 cyc = the image-pointer load, accepted) | ✅ verified | the snapshot's A:+B:; seven bitmaps separating a longword read from a word or a byte |
| `0xfc0a34` | `Kbshift` (BIOS $0b, `src/bios/kbshift.c`) | 21 | 6 / 94 read, 7 / 104 write | **1.48** read, **1.53** write (accepted: image pointer) | ✅ verified | the `bmi` on the WORD ($ff80 reads, $0080 STORES); the old state zero-extended over seven bytes; seven modes storing their low byte ($7fff stores $ff); and storing the value already held, attributed by the poison pass |

## Harness

| surface | state |
|---|---|
| Ghidra bootstrap of the ROM at `0xFC0000` | **DONE** 2026-09-13: `run.sh` + `reapply.sh` (≈4 min) → 1,292 functions, 1,219 decompiled, 137,555 of 196,608 B (70.0%) inside function bodies (the rest is the identified data: fonts, resources, the Line-F table); `names.txt` seeds 272 fn / 174 var / 44 cmt with zero apply failures; `a5` pinned to 0 over the BIOS/XBIOS (`unaff_A5` 308 → 107, none left in the pinned range); `COMPONENTS.md` maps every component but the aes/desk code boundary. Open: 73 functions fail to decompile (Alcyon's write-to-`(sp)` first-arg idiom, e.g. `Fread`, `Pexec`, `Setexc`) — listed in `COMPONENTS.md` |
| post-boot RAM snapshot (Tier 1 image) | **DONE** 2026-09-13: `make snapshot` → 1,048,576 B of a 1 MB ST's RAM, captured out of headless Hatari at the ROM's own VBL handler (`$fc06de`) on vertical blank 901, desktop up and idle; `tools/boot_snapshot.py --twice` measured the non-deterministic set over three boots — 1,929 B of AES/desktop idle scratch, recorded as its `MASK` — and `test/test_boot_snapshot.py` re-runs the ORACLE over noise-filled copies of every masked region, so no verified function may rest on a byte two boots disagree about |
| oracle ROM mode (`tools/recreate_kit`) | **DONE** 2026-09-13: the kit's ROM BINDING (`rom` / `rom_base` / `snapshot` / `stack_top` in `project.toml`) — the image is the 24-bit address space, the ROM read-only at `$fc0000`, no TOS trap model, and an I/O read no Phase-7 slot declares refuses the case by address. Pinned from C by `recreate_kit/test/test_rom_mode.py` (13 claims incl. the trap PAIR with and without the window) and from Python by `recreate_kit/test/test_rom_binding.py`; 825 kit tests green, and the six `.PRG` projects unchanged (zynaps 4,751 passed / 4 skipped) |
| Tier 3 numerator (`tools/recreate_kit/rom_bench.py`) | **DONE** 2026-09-14: the cores cross-compiled by `m68k-elf-gcc` with the SHIPPED ROM build's own flags (`atari/target.mk`, read by both makefiles), linked at `project.toml`'s `bench_base` = `$30000` and staged in the snapshot's free TPA, entered through `emu.run_bench` over the same case as the original — so every verified function carries a `recreate / original` ratio and not just a denominator. `make bench` prints the table; `test/test_tier3.py` gates it at <= 1.10 with an explicit `PERF_ACCEPTED` escape that goes stale loudly. Each row is a SECOND DIFFERENTIAL too (image, return value at the signature's width, callee-saved file, PSG/hardware ledgers, no unmodelled I/O read) — the surface for target-codegen defects, which Tier 1's host build cannot see (`docs/on-target-execution.md`, class 6). Measured sharp on three mutations: a core's `+1` → `+2` reds on the image, a target-only `psg.h` shadow selecting `reg + 1` reds on the return value, one reading `$ff8802` reds as an unmodelled I/O read. The entry overhead the ratio is net of (1 insn / 40 cycles, the 68000's reset) is measured on an empty function through BOTH oracle doors and required equal. **It couples the tree: the blob is ONE link over every `src/**/*.c`, so a core that does not compile for the 68000 now fails `make test` — which is the ROM's own constraint, arriving at the function rather than at the ROM build** |
| declared I/O map (`TRAP_MODEL.md` Phase 15) | **DONE** 2026-09-14: `io_seed={address: byte}` over any byte of the I/O page — the one door a case author uses (named Phase-7 slots are routed to their model, the YM2149 block refused by name); both cores serve and ledger it in order; an undeclared read still refuses by address; the six `.PRG` projects unchanged. First consumer: `Getrez` |
| rebuilt ROM boots in Hatari (`--tos`) | **DONE** 2026-09-13: `recreate/atari/` builds a 196,608-byte `TOS102RC.IMG` (header byte-identical to the original's, `checkrom.py` dereferences the MUPB; `.data`/`.bss` refused by the linker) whose boot stub paints 16 bands at the header-derived 60 Hz; Hatari runs it with `--patch-tos off` and a committed machine config |
| `TOSTEST.PRG` conformance ledger | **DONE** (seed) 2026-09-13: 14 call sites / 19 records + a screen CRC, ledger at $C0000, golden reproducible run-to-run; instrument identity (ROM/floppy/PRG sha256) pinned in every metrics file |
| `TOSBENCH.PRG` + boot-time surface | **DONE** (seed) 2026-09-13: boot surface = screenshot + 256 vectors + named sysvars ($000–$9FF pinned, clocks masked) at vblank 500 with a settle proof at 550 (boot metric 461 vbl / 1534 ticks); TOSBENCH times Bconout / Malloc / Fread on both clocks. **OPEN: Fread's own noise floor is 6.6 % (floppy rotational phase), wider than the 5 % bar — the floppy workload cannot be judged as designed; either sync to the index pulse, widen that row's bar to its measured floor, or move the read workload off the floppy** |

## Wave log

* **Wave 1 (2026-09-13/14)** — three agents on disjoint paths, each reviewed by eight finder angles + a
  verifier, fixed, and committed by the orchestrator: (1) Ghidra bootstrap + `COMPONENTS.md` (the
  Line-F call mechanism, the a5 pin, 1,292 functions); (2) the kit's ROM mode + the boot snapshot +
  `Random`/`Giaccess`; (3) the rebuilt ROM image, boot surface, TOSTEST and TOSBENCH. Review found
  real defects in all three (a mask test that could not detect what it claimed, an unguarded stack
  band, I/O reads answered 0 silently, a stub at 50 Hz on an NTSC ROM, a benchmark that graded a
  failed workload "within the bar"). Parked from review: the kit-wide `OS_IMAGE_SIZE` limit
  (TRAP_MODEL.md), extracting a shared engine for LineAResolve/LineFResolve, deriving `gen_seeds.py`'s
  tables from the dispatcher signatures, and `projects/flyingshark/tools/extract_audio.py:155`
  catching only `(OSError, ImportError)` around its kit import (its siblings also catch `RuntimeError`).
  Parked from wave 2: `tools/test_hw_portability.py` has three PRE-EXISTING reds at HEAD (stale published
  figures for Wonder Boy's committed portability scan: at_risk 22/3658 vs the asserted 23/3888, 1 vs 2
  seeded-hardware writes) — fixing them means re-running that scan and re-publishing its numbers with the
  record that accounts for the move; the PSG-block pin that this wave moved to `os.h` is fixed (53 of 56).
* **Wave 2 (2026-09-14)** — three agents in parallel, each through the eight-angle review + verifier +
  fix cycle: (1) **Tier 3's numerator** — `tools/recreate_kit/rom_bench.py` + kit.mk's `$(BENCH_*)` rules +
  `bench/tier3.py` + `test/test_tier3.py`; rows are DERIVED from `test_boot_snapshot.VERIFIED_CASES`, so a
  verified function with no row is red (`tier3.UNPRICED`), STATUS's cells are pinned to `build/bench/tier3.txt`
  by `test_status.py`, and the second differential compares all four off-image streams and every refusal
  tally. (2) **the declared I/O map** (Phase 15) with `Getrez` as its first consumer. (3) **BIOS wave 1** —
  16 RAM-only BIOS/XBIOS leaves (the `## Verified — bios` section and 8 xbios rows above). Review found:
  host-only asserts that compiled away into fabricated returns on target (now `recreate_not_reconstructed`
  halts on both builds), a Supexec signature that was not the ROM's frame, a Cursconf return type that
  could not express two arms' `moveq #0`, Giaccess's missing interrupt-mask bracket (88 % of its measured
  speed-up — now `ipl.h`, 0.39 → 0.60), a kit make rule that silently disabled the numerator, and the
  stack-band guard from befc249 breaking Bubble Ghost (Alcyon writes its arguments back) and Wonder Boy
  (blits to the image's last word) — fixed by one formula: the band ends at the frame area and everything
  above it is COMPARED.
* **The Tier 3 finding, and the decision.** 17 of 30 measured rows are over the 1.10 bar and none is a
  reconstruction defect. At leaf scale one instruction is the whole ratio (Drvmap: 32 → 48 cycles = 1.50x),
  and three mechanisms account for every acceptance, each recorded in `bench/tier3.py`'s `PERF_ACCEPTED`
  with its measured cycles: **(A)** the C ABI's `uint8_t *image` load (`movea.l 4(sp),a0`, 12–16 cycles)
  where the ROM's dispatcher zeroes a5 once for every routine — a lever for the SHIPPED build (cores
  compiled with the image base a link-time 0), not for the C; **(B)** the Bcon* device dispatch as a
  compare chain under `-fno-jump-tables` vs the ROM's `jmp (a0)`; **(C)** Cursconf's arm selection vs
  `jmp TABLE(pc,d0.w)` — 2.29x, 104 → 238 cycles, the first lever worth a wave. Decision: the bar stays
  at 1.10 as the *ratio* instrument; acceptances carry their cycle deltas; the bar's shape for leaves (an
  absolute slack beside the ratio) is decided when the dispatcher wave exists to price a whole trap call.
* **Next** — BIOS wave 2: the XBIOS screen/MFP/timer routines and the interrupt handlers, now that the
  declared I/O map reaches them; the trap #13/#14 dispatcher itself (which prices mechanism A honestly);
  the aes/desk code boundary; the 73 Alcyon write-to-(sp) decompile failures.

## Suite

`make test` — **442 passed** and `make guarded` the same count (783 candidate runs guarded across 10
workers, no fault), re-summed at the wave-2 merge on 2026-09-14 after a clean rebuild (`rm build/*.so build/bench`).
The kit's own suite: **961 passed**. The six `.PRG` projects unchanged (zynaps 4,751 / 4 skipped, bubbleghost 1,909,
wonderboy 6,465, joust 4,368, flyingshark 3,851, buggyboy 296).

## Not reconstructed, and why

(empty — filled per component)
