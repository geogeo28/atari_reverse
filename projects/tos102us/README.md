# TOS 1.02 US — a C recreate of the ROM, component by component

The other projects in this workspace turn a *game* `.PRG` back into source. This one turns the
**operating system ROM** the games run on — `TOS102US.img`, Atari TOS 1.02 (US), 192 KB, dated
1987-04-22 — into a structured C code base, one component at a time, with each component proved
equal to the original in behaviour *and* on par in speed before it counts.

**Not EmuTOS.** EmuTOS is a clean-room reimplementation of the API. This is a *recreate*: the C is
derived from the ROM's own decompiled code, keeps the ROM's own structure, data layouts and
algorithms, and is held to the ROM's own bytes by a differential oracle — the same standard every
game recreate here is held to. The public EmuTOS / DRI GEM sources may be *read* for names and
structure (they document the same design lineage) but no code is copied from them; every function
here is written from `decomp.c`.

**The ROM is not in the repo.** `tools/hatari/TOS102US.img` is Atari copyright and gitignored; the
scripts reference it in place, and any font or resource data the rebuilt ROM needs is extracted
from the user's own image at build time, never committed.

## The ROM, as parsed from its header

| field | value |
|---|---|
| version | `0x0102` |
| reset PC | `0xFC0030` |
| OS base / end of OS BSS in RAM | `0xFC0000` / `0x8900` |
| GEM memory-usage parameter block | `0xFEFFF4` |
| date | 1987-04-22 |
| size / text entropy | 196,608 B / 6.53 (plain code, nothing packed) |

Mixed authorship, and the decompile shows it: the BIOS/XBIOS and Line-A are hand asm (Atari),
GEMDOS, the AES and the desktop are Alcyon C (`link a6` frames, stack args — the "compiled C"
playbook applies), the VDI is DRI asm with C glue. Two easter-egg strings survive
(`Dave Staugas loves Bea Hablig`, `JIM LOVES JENEANE`).

## Components — the structure the C code base takes

The ROM is one flat image, but it has a real component structure: each `trap` and Line-A entry
dispatches through its own table, and the boot chain, the interrupt handlers and the desktop are
separable by their call graphs. The code base mirrors that structure, one directory per component:

| component | entry | what it is | authorship |
|---|---|---|---|
| `boot/` | reset vector `0xFC0030` | memory sizing, RAM test, vector table, hardware init, AUTO folder, desktop launch | asm |
| `bios/` | `trap #13`, VBL / MFP / IKBD ISRs | console, keyboard (IKBD/ACIA), screen, floppy + DMA, timers, `Getmpb`… | asm |
| `xbios/` | `trap #14` | `Setscreen`/`Setpalette`, `Floprd`/`Flopwr`/`Flopfmt`, `Giaccess`/`Dosound`, `Rsconf`, `Random`… | asm |
| `gemdos/` | `trap #1` | FAT12 file system, handles, processes (`Pexec`), memory (`Malloc`), console I/O, time | C |
| `vdi/` + `linea/` | `trap #2` (`d0 = 0x73`), `$A000`–`$A00F` | rasterizers: lines, fills, polygons, text, `vro_cpyfm`, workstation state | asm + C |
| `aes/` | `trap #2` (`d0 = 0xC8`) | objects, forms, windows, events, menus, dispatcher, shell, resource loader, file selector | C |
| `desk/` | launched by `boot/` | the desktop application and its embedded resource | C |
| `data/` | — | system fonts (6×6, 8×8, 8×16), keyboard tables, desktop `.RSC` — **extracted from the local ROM at build time** | data |

`COMPONENTS.md` is the evidence-backed map: each component's address ranges in the ROM, its dispatch
table, its function count, and how the boundary was established. It is written by the bootstrap and
kept current as the naming loop moves boundaries.

## How a component is evaluated — the three tiers

An OS has no frame loop to diff and no "playable" verdict to reach, so *what counts as verified* has
to be stated precisely. Every component is held to three tiers, and its `STATUS.md` row names the
tests in each tier that pin it — a row that names no surface is the finding.

### Tier 1 — function differential (correctness, per function)

The workspace's standard: `tools/recreate_kit`'s Musashi oracle runs the **original ROM function in
place** at its `0xFCxxxx` address, the C candidate runs over the **same image**, and the two must
agree **byte-for-byte over the whole image plus the full `D0–D7/A0–A6` register set**.

What is new for a ROM is the image: a TOS function's inputs are the machine's RAM state
(system variables at `$380`–`$8900`, the vector table, the GEMDOS buffers and process descriptors)
and the I/O page. So the image is

* a **post-boot RAM snapshot** of the original ROM, captured once from headless Hatari at a
  deterministic stop point, 1 MB, plus
* the **ROM** mapped at `0xFC0000`, plus
* the **seeded hardware read model** for the I/O page (`TRAP_MODEL.md`, Phase 7): a case declares
  the bytes it expects the MFP, shifter, PSG or ACIA to answer, and an undeclared read *refuses* the
  run rather than answering zero.

A case may perturb the snapshot (a different key pending, a different directory in the FAT buffer,
a different `_hz_200`) so a function is proved over inputs, not over one state. Functions that
never return (the boot chain, the desktop event loop) are proved as **slices** — `[start, end)`
ranges — exactly as Zynaps's `_start` was.

**Where "booted" is, measured.** The obvious anchor — the desktop's first `evnt_multi` — does not
exist on this ROM: the desktop is in the same image and calls the AES dispatcher directly, so no
`trap #2` with `d0 = $c8` ever fires after boot, and once idle the desktop blocks inside its event
wait. Both stop rules in this project are therefore vertical-blank counts under one fixed machine
config, each with its own proof: the Tier 1 snapshot stops in the ROM's own VBL handler at vblank 901
(`recreate/tools/boot_snapshot.py`; three boots agree on every byte outside a documented 1,929-byte
mask of AES/desktop idle scratch), and the Tier 2 boot surface stops at vblank 500 with a settle
proof, a second capture 50 vblanks later that must be identical (`recreate/atari/boot_surface.py`).
They differ because they answer different questions — "an idle machine to run one function over"
versus "the earliest point at which the desktop is fully drawn" — and a function verified over the
901 snapshot is not thereby proved over the 500 state; a case that needs the earlier state perturbs
the snapshot rather than re-capturing.

### Tier 2 — conformance on target (correctness, at the trap surface)

The rebuilt ROM boots in Hatari via `--tos`. Two programs written for this project run under **both**
the original and the rebuilt ROM, headless, and the artefacts they leave must be identical:

* **`TOSTEST.PRG`** — a conformance ledger: calls every BIOS / XBIOS / GEMDOS / VDI / AES function
  a component implements with fixed arguments and writes the results (return values, buffers, a CRC of
  the screen after each drawing call, a snapshot of the system variables) to a ledger block in RAM
  that the driver `savebin`s and diffs.
* **the boot surface** — the desktop screenshot (pixel diff), the system-variable block with its
  time-varying fields masked, the 256-entry vector table, and the low-RAM layout (`_membot`, `_memtop`,
  `_phystop`, the AES's and desktop's allocations).

Tier 1 says a function equals the original; Tier 2 says the *composition* does — that the vectors,
the sysvars and the dispatch tables the components share are wired the same way.

### Tier 3 — performance (on par with the original)

"On par" is a measured ratio, not an impression, measured two ways:

* **per function** — the C compiled with `m68k-elf-gcc` for the target, with the **shipped ROM
  build's own flags**, staged in a free span of the same post-boot snapshot and run under the same
  Musashi oracle as the original (`recreate_kit/rom_bench.py`, which is ROM mode's counterpart of
  `asm_twin.py` — that one refuses a ROM project and says why). So every verified function carries a
  **cycle ratio** `recreate / original`, net of the entry overhead both sides are charged. Bar:
  **≤ 1.10** per function; a function over the bar is a perf item, not a verified row, until it is
  either brought under by the levers the games used (a hand-asm twin pinned to the C core by the twin
  differential) or explicitly accepted, with the measured cost, in `bench/tier3.py`'s `PERF_ACCEPTED`
  and `STATUS.md`. `make bench` prints the table; `test/test_tier3.py` is the gate, and every row is
  also a **second differential** — the target build must leave the same image, return value,
  callee-saved file and chip traffic as the ROM, which is the only place a target-codegen defect
  (`docs/on-target-execution.md`, class 6) would surface.
* **on target** — **`TOSBENCH.PRG`** times workloads with `_hz_200` under both ROMs: boot-to-desktop
  (vblanks), console output, `Fread`/`Fwrite` on a floppy image, `Malloc`/`Mfree` churn, VDI text /
  lines / fills / raster copies, AES `objc_draw` / `form_do` / window operations, `Pexec` of a
  trivial program. Bar: **≤ 1.05** per workload over the whole rebuilt ROM. Hatari's CPU profiler
  attributes the difference per symbol when a workload misses (the recipe is
  `projects/wonderboy/recreate/atari/profile.py`).

Performance is evaluated per component as it lands, not at the end: a component's row is not
**DONE** until its Tier 3 numbers are in the table.

## Process — waves of agents, one component each

The session model is the orchestrator: it scopes a wave, launches independent agents on disjoint
paths, reviews each result through an independent reviewer agent, integrates and commits. Agents
never commit. The gates are the workspace's (`CLAUDE.md`): `make test` green, the review sweep,
the docs surfaces (`names.txt`, `recreate/STATUS.md`, `COMPONENTS.md`, this file) in the same commit.

The order of attack follows the dependency graph, not the address order: the harness and the boot
snapshot first (nothing can be proved without them), then the BIOS's leaf routines (the anchors every
other component calls), then GEMDOS, the VDI, the AES and the desktop. Within a component, the
"compiled C" playbook applies to the DRI/Atari C and the hand-asm playbook to the rest.

The reverse-engineering record — what was tried, what a differential found, which name was wrong
until the body was read — lives in `recreate/STATUS.md` per component and in `docs/` once a
mechanism turns out to be transferable.

## Layout

```
projects/tos102us/
├── README.md            this file: goal, components, the three evaluation tiers, process
├── COMPONENTS.md        the evidence-backed address map of the ROM's components
├── names.txt            the name map (source of truth), Ghidra addresses = ROM addresses
├── run.sh / reapply.sh  Ghidra bootstrap (ROM at 0xFC0000, no relocation) / name re-apply
├── decomp.c, ghidra_proj/, out/     generated, gitignored
└── recreate/
    ├── README.md        the harness as bound to a ROM: snapshot, image layout, how to write a case
    ├── STATUS.md        per-component progress: verified rows, tier-2 ledgers, tier-3 ratios
    ├── project.toml, Makefile, include/, src/<component>/, test/
    └── atari/           the rebuilt ROM image, TOSTEST.PRG, TOSBENCH.PRG, the headless drivers
```

The `recreate/` entries are the **target** layout, not an inventory: each one lands with the wave
that needs it, and `recreate/STATUS.md`'s Harness table is the list of what is actually in.
