# Reconstruction status — TOS 1.02 US

**As of 2026-09-14.** Wave 1 is merged: the ROM is bootstrapped in Ghidra, the three evaluation tiers
each have a working instrument, and the first two XBIOS functions are verified with sharp differentials.
Read `../README.md` first for the three tiers a component is held to; `test/test_status.py` pins the
counts in this file against its rows.

## Components

| component | Tier 1 (functions verified) | Tier 2 (conformance ledger) | Tier 3 (cycle ratio) | state |
|---|---|---|---|---|
| boot | 0 | — | — | NOT STARTED |
| bios | 0 | — | — | NOT STARTED |
| xbios | 2 | — | — | STARTED |
| gemdos | 0 | — | — | NOT STARTED |
| vdi + linea | 0 | — | — | NOT STARTED |
| aes | 0 | — | — | NOT STARTED |
| desk | 0 | — | — | NOT STARTED |
| data | — | — | — | NOT STARTED |

## Verified — xbios (2)

Each row is one function of the ORIGINAL ROM, run in place at its own address over the post-boot RAM
snapshot and compared byte-for-byte against the reconstruction (`../README.md`, Tier 1). The cost
column is the ORACLE's own count for one call — the instructions it executed and the 68000 cycles
they took — which is the Tier 3 baseline a port is later measured against.

| Addr (ROM) | Name | Cases | Cost (insns / cycles) | Status | Verification |
|---|---|---|---|---|---|
| `0xfc1510` | `Random` (XBIOS $11, `src/xbios/random.c`) | 19 | 44 / 810 seeding, 39 / 710 advance | ✅ verified | both branches of `tst.l random_seed`: the snapshot's own unseeded machine, and seven system-tick values through the `asl.l #16` / `or.l` seeding arm including ticks with the high word set; eight seeds across the SIGNED 32x32 helper's edges (either operand negative, both, and the two values `neg.l` leaves alone); the 24-bit projection asserted against the state the diff compares byte-for-byte; a 64-case fuzz over seed x tick. The ROM's call into Alcyon's `lmul` at `$fc4b28` executes in the ROM like any other instruction, so this is also the pin that ROM-internal calls work. Poison on every parametrized case |
| `0xfc2ea4` | `Giaccess` (XBIOS $1c, `src/xbios/giaccess.c`) | 49 | 17 / 260 read, 18 / 270 write | ✅ verified | all sixteen registers the four-bit select latch can name, read and written, against a declared entry file with a distinct byte per register — so reading the WRONG register diverges on the value rather than by luck; the ordered PSG access ledger compared on every case (the chip is off-image, so nothing in the memory diff could see it); five data words proving only the low byte reaches the port; eleven `reg` words proving the direction bit and the register both come from the LOW byte alone. A decoy planted at `$ff8800` pins that the ports reach the seeded model rather than the image, which is the claim ROM mode has to get right. Poison on every case |

## Harness

| surface | state |
|---|---|
| Ghidra bootstrap of the ROM at `0xFC0000` | **DONE** 2026-09-13: `run.sh` + `reapply.sh` (≈4 min) → 1,292 functions, 1,219 decompiled, 137,555 of 196,608 B (70.0%) inside function bodies (the rest is the identified data: fonts, resources, the Line-F table); `names.txt` seeds 272 fn / 174 var / 44 cmt with zero apply failures; `a5` pinned to 0 over the BIOS/XBIOS (`unaff_A5` 308 → 107, none left in the pinned range); `COMPONENTS.md` maps every component but the aes/desk code boundary. Open: 73 functions fail to decompile (Alcyon's write-to-`(sp)` first-arg idiom, e.g. `Fread`, `Pexec`, `Setexc`) — listed in `COMPONENTS.md` |
| post-boot RAM snapshot (Tier 1 image) | **DONE** 2026-09-13: `make snapshot` → 1,048,576 B of a 1 MB ST's RAM, captured out of headless Hatari at the ROM's own VBL handler (`$fc06de`) on vertical blank 901, desktop up and idle; `tools/boot_snapshot.py --twice` measured the non-deterministic set over three boots — 1,929 B of AES/desktop idle scratch, recorded as its `MASK` — and `test/test_boot_snapshot.py` re-runs the ORACLE over noise-filled copies of every masked region, so no verified function may rest on a byte two boots disagree about |
| oracle ROM mode (`tools/recreate_kit`) | **DONE** 2026-09-13: the kit's ROM BINDING (`rom` / `rom_base` / `snapshot` / `stack_top` in `project.toml`) — the image is the 24-bit address space, the ROM read-only at `$fc0000`, no TOS trap model, and an I/O read no Phase-7 slot declares refuses the case by address. Pinned from C by `recreate_kit/test/test_rom_mode.py` (13 claims incl. the trap PAIR with and without the window) and from Python by `recreate_kit/test/test_rom_binding.py`; 825 kit tests green, and the six `.PRG` projects unchanged (zynaps 4,751 passed / 4 skipped) |
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
* **Next** — Tier 3's numerator (build the C with m68k-elf-gcc and run it under the oracle for the cycle
  ratio); the aes/desk code boundary; the 73 Alcyon write-to-(sp) decompile failures; then the BIOS
  leaf routines as the first component wave.

## Suite

`make test` — **91 passed**. `make guarded` — same count, 196 candidate runs guarded across 10
workers, no fault. The kit's own suite stands at **825 passed** with ROM mode in it.

## Not reconstructed, and why

(empty — filled per component)
