# Atari ST — from binary to remaster

Recovering lost 1980s Atari ST games from their shipped executables: disassemble one, name every
function, rewrite it as readable C **proven byte-for-byte against the original machine code**, and
run that C back on a 68000. The tooling and the [documentation](docs/README.md) are game-agnostic —
point them at any GEMDOS `.PRG`. **Two games are solved with them.**

<p align="center">
  <img src="assets/buggyboy/race-leg1.png" width="640" alt="Buggy Boy in-race frame rendered by the C reconstruction">
</p>

<p align="center"><em>Not a screenshot of the original program — this frame was drawn by the
reconstruction: its road rasterizer, scroll blitter, object dispatcher and HUD, over the game's own
<code>COURSES.DAT</code>.</em></p>

**Buggy Boy** (Elite Systems, 1988) is the worked reference, solved end to end and taken one stage
further into a free, optimized remaster that is **pixel-identical** to what the original drew:
**91/91 functions verified** · **~20 000 lines of reconstructed C** · **69 test modules** ·
**driveable on a 68000**.

**Joust** (published for the ST by Atari Corporation) is the second game, and the proof the method
is not shaped around the first: **75/75 functions verified** · **4368 differential tests** · a
playable `JOUST.PRG` cross-compiled back to m68k and pinned against the shipped binary frame by
frame. It stops at the proving stage — there is **no Joust remaster**. See
[The second game — Joust](#the-second-game--joust).

> **No game data is distributed here.** No `.PRG`, no `COURSES.DAT`, no `GRAPHICS.GRA`, no
> `HIGH.SCO`, no TOS ROM. Bring your own copy; see [Credits & legal](#credits--legal).

---

## The three stages

```
   BUGGYBOY.PRG                              ── the shipped 1988 binary (you supply it)
        │
        │  tools/prg_dis.py · Ghidra headless · names.txt naming loop
        ▼
1. DISASSEMBLE & NAME     decomp.c — 91 named functions, anchored on OS traps + hardware regs
        │
        │  rewrite as idiomatic C, then diff every function against a cycle-accurate 68000
        ▼
2. RECREATE               recreate/ — readable C, each function byte-for-byte == the original
        │                            (oracle: Musashi running the real machine code)
        │  rewrite freely for speed and clarity; the only rule is the frame must not change
        ▼
3. REMASTER               remaster/ — native structs, faster algorithms, pixel-identical output
        │
        ▼
   BUGGYBOY.PRG on a 68000                    ── cross-compiled back to m68k, runs under Hatari
```

Each stage is refereed by the one above it, so nothing can go wrong quietly. Stage 2 is judged by a
cycle-accurate emulator running the original machine code; stage 3 is judged, frame by frame,
against stage 2's verified cores.

Buggy Boy went through all three. Joust goes through the first two and then straight onto the
68000: same disassemble-and-name loop, same differential proof, same cross-compile back to a `.PRG`
— no stage 3.

---

## Gallery — Buggy Boy

Everything below was **rendered by the reconstruction**, then decoded from the Atari's 4-plane
framebuffer with the game's own palettes. Regenerate the whole set — byte-identical every run — with
`projects/buggyboy/gen_readme_assets.py`, run under `recreate/`'s venv.

### In-race frames — three courses, driven for real

Staged from the real course data, driven with the throttle held through the verified `game_update`,
then drawn by the verified render pipeline (road → scroll → objects → HUD).

| `OFFROAD` | `NORTH` | `SOUTH` |
|:---:|:---:|:---:|
| ![](assets/buggyboy/race-leg0.png) | ![](assets/buggyboy/race-leg1.png) | ![](assets/buggyboy/race-leg4.png) |

The course map in the top-left corner is built per leg by `init_leg_dash` out of `COURSES.DAT` and
blitted every frame by `draw_dashboard`; the trace along it is the player's live progress.

### Screens

| Credits | Leg board | High scores |
|:---:|:---:|:---:|
| ![](assets/buggyboy/screen-credits.png) | ![](assets/buggyboy/screen-leg-select.png) | ![](assets/buggyboy/screen-highscore.png) |

### Course data and sprites

`COURSES.DAT` turned out not to be a script but road-slice **bitmap** data, streamed eight bytes at a
time through a circular buffer. Walking it recovers each leg's shape:

| `OFFROAD` | `WEST` |
|:---:|:---:|
| ![](assets/buggyboy/course-legmap-0.png) | ![](assets/buggyboy/course-legmap-3.png) |

`GRAPHICS.GRA` is a sprite table plus an RLE stream that unpacks to eight 320×200 four-plane atlases:

| Gates & score markers | Roadside scenery |
|:---:|:---:|
| ![](assets/buggyboy/sprites-page3.png) | ![](assets/buggyboy/sprites-page4.png) |

[`projects/buggyboy/docs/function_graph.html`](projects/buggyboy/docs/function_graph.html) is a
standalone call-graph explorer covering all 117 functions — open it in a browser, no server needed.
With your own copy of the game you can go further: `gen_assets.py` regenerates the full media set
(every sprite page, per-object crops sliced by driving the real blitter, buggy animations as GIFs,
and the soundtrack re-rendered through the reconstructed YM2149 driver), and re-running
`gen_graph.py` attaches all of it to the functions that produce it. Generated media is not stored
in this repository.

---

## Stage 1 — Disassemble & name

Load the `.PRG` at a known base, let Ghidra analyze, then iterate a plain-text name map until the
decompilation reads like source.

```bash
bash tools/new_project.sh mygame path/to/GAME.PRG   # scaffold projects/mygame/
bash projects/mygame/run.sh                         # import → analyze → annotate → decomp.c
#  read decomp.c → append to names.txt → reapply → re-read
bash projects/mygame/reapply.sh
```

`names.txt` is the source of truth — one directive per line, addressed as Ghidra sees them
(image offset + load base):

```
fn   0x1555e draw_hud
var  0x18c38 leg_index
cmt  0x1110e game_update: input, integrate throttle->speed, steering->road_curve, stream course…
```

The method is **anchors outward**: start from ground truth an emulator cannot dispute — GEMDOS/BIOS
trap numbers, DRI symbols, hardware register addresses, string literals — and propagate along the
call graph. Then *verify by reading the body*; several confident first guesses in this project were
wrong until someone actually read the code ([`docs/methodology.md`](docs/methodology.md)).

**Result for Buggy Boy:** 335 name directives, all 91 functions named, plus a decoded loader,
course format, sprite format, event jump table and sound driver.

## Stage 2 — Recreate: prove it

Buggy Boy was hand-written assembly, so there is no original source to recompile and byte-match
against. Instead we prove **behavioural equivalence**: run the real machine code and the
reconstruction on identical memory, then diff.

```
          initial memory image + registers
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
  ORACLE (real 68k)          CANDIDATE (our C)
  Musashi via liboracle.so   libbuggyboy.so via ctypes
        │                          │
        ▼                          ▼
  final memory + write-set   final memory
        └──────────► diff ◄────────┘   green = byte-for-byte identical
```

Both sides share one flat big-endian image whose indices are the game's real addresses. The harness
diffs the *whole* image, so a byte the original writes that the reconstruction misses fails the test.
Leaf functions can additionally opt into an attribution pass that poisons oracle-written bytes first,
so a candidate that matches *coincidentally* is caught rather than passing.

Functions that never return (`_start`, the interactive loops) are verified at a checkpoint PC, with
any excluded stack band vetted against the oracle's deepest stack pointer so an exclusion cannot hide
a divergence.

**Status: 91/91 verified.** See [`recreate/STATUS.md`](projects/buggyboy/recreate/STATUS.md) for the
per-function table and how each one was pinned.

## Stage 3 — Remaster: free it

`recreate/` proves what the original does. `remaster/` is free to look nothing like 68000 assembly —
native structs instead of a flat image, real types, precomputed tables, better algorithms — subject
to exactly one rule:

> For any given input, the remaster must produce a **pixel-identical framebuffer** to the verified
> `recreate/` cores, every frame.

The two use deliberately different memory layouts, so their internal state cannot be diffed. The one
surface they share is the thing the player sees, and that is the comparison surface. An optimization
that moves a single pixel fails.

- **Phase A — render pipeline: green.** Road geometry, rasterizer, scroll blitter, ground/horizon,
  sprites, scaled objects, the fine-x blit engines, the object-list dispatcher and all eight HUD
  phases are ported and byte-exact over the whole framebuffer.
- **Phase B — gameplay: in progress.** Course streaming, the object ring, player physics and the
  crash/auto-steer script are ported and frame-exact; sound, collision probing and event dispatch
  are not started.
- **On target:** `BUGGYBOY.PRG` — the playable game (no sound) — cross-compiles back to m68k and runs
  under Hatari, loading the unmodified `COURSES.DAT` and `GRAPHICS.GRA` at boot. It boots into the leg
  select; its leg-0 start frame is byte-identical to the reconstruction's, and it is driveable.

See [`remaster/STATUS.md`](projects/buggyboy/remaster/STATUS.md) for the per-subsystem table.

---

## The second game — Joust

Everything above is Buggy Boy. [`projects/joust/`](projects/joust/) is the same pipeline pointed at
a different binary — a different publisher, a different decade of tooling, and a compiler rather
than a human writing the assembly — and the point of it is how little had to move.

It starts one step earlier, because the game ships **packed**: `JOUSTS.CTE` has 6.95 bits of
entropy, no relocations and an entry that disassembles to garbage. `tools/depack_gamex.py` unpacks
it statically — the Gamex/"PP" LZSS algorithm read out of the release's own `START.TOS`, and
validated by self-depacking that loader — into an ordinary GEMDOS `bin/JOUST.PRG`: 114 KB, entropy
4.01, 1227 relocations, and from there the normal naming loop. That is the capability
[`docs/packed-executables.md`](docs/packed-executables.md) was written from.

The harness is now **shared**. [`tools/recreate_kit/`](tools/recreate_kit/README.md) owns the PRG
loader, the Musashi oracle and the TOS trap model; a game binds to it with a small `project.toml`
naming its binary, load base and image size, and everything else in `recreate/` is game-specific.

**Status: 75/75 functions verified · 4368 differential tests · no `# ctx` names left.** Being
compiled C rather than hand-written assembly cost one thing Buggy Boy never needed: most of Joust's
routines take their arguments on the **caller's stack**, and the differential deliberately stops
comparing at the stack. `recreate/test/abi.py` fixes that by poking a two-instruction 68000 stub
into free image space and entering the oracle there, so every argument block lands in ordinary,
fully diffed memory. Per-function notes, and every limit that is disclosed rather than closed, are
in [`recreate/STATUS.md`](projects/joust/recreate/STATUS.md).

**On target, three surfaces are compared rather than one.**
[`recreate/atari/`](projects/joust/recreate/atari/README.md) cross-compiles the same verified cores
to m68k and runs the result under Hatari **beside the shipped binary, on one emulator**. At six
sampled frames of real play — each chosen because its neighbour differs, so a one-frame mis-anchor
is detectable — the **32000 framebuffer bytes** are identical, and so are the **sixteen hardware
palette pens read back off the shifter**. Once more, at a frame from the static band, so is the
**rendered picture**: the emulator's own video output, the one artefact there that is not a memory
dump, and the only one that sees what the player sees. On EmuTOS and on TOS 1.04. The palette and
the picture each get their own injected-fault control, because the frame anchors structurally
cannot exercise either — that README is careful about what each check can and cannot see, and it
also records the three bugs that appear only on real hardware and the one fidelity gap (a register
hand-off no C `_start` can make) that is disclosed rather than papered over.

### Gallery — Joust

Rendered **host-side by the reconstruction**, with no emulator and no TOS ROM in the loop:
`projects/joust/gen_readme_assets.py` loads your own `JOUST.PRG` through the kit, drives the
verified cores over ctypes exactly as the tests do, and de-interleaves the framebuffer they paint
with the game's own palette words. Every picture is a function of the binary alone — the high-score
record staged is the blank one the `.PRG` itself carries, not the save file next to it — so the
whole set is byte-identical every run.

| Title screen | Wave 1 begins | A joust, and a loose egg |
|:---:|:---:|:---:|
| ![](assets/joust/title.png) | ![](assets/joust/wave1.png) | ![](assets/joust/eggs.png) |

`init_system` takes the machine over and loads `HIGH.SCO`; `title_screen` then paints the picture
the `.PRG` itself carries, draws its three lines through `draw_string` — the middle one is the
`HIGH SCORE:` line the loaded record is spliced into, blank here because nobody has set one — and
runs one attract pass, which is what `cycle_palette` and the six-pen ring rotate the shown palette
by.

The two frames beside it are the game **playing itself**. `_start`'s init chain runs
(`init_game`, `init_video`), then laps of its frame loop, each lap driven through the two verified
rotated entries either side of the IKBD wait no run can cross — with the joysticks fed from a
seeded generator, because random input is what makes riders fight and eggs exist. Everything drawn
is the loop's own seventeen calls: `draw_platforms`, `render_objects`, `update_eggs`,
`draw_messages`, `collision_check`, `wave_manager` and the rest.

| The pterodactyl arrives | A new record, being typed | The cast |
|:---:|:---:|:---:|
| ![](assets/joust/pterodactyl.png) | ![](assets/joust/hiscore.png) | ![](assets/joust/sprites.png) |

On lap 1850 of that same self-played game `update_pterodactyl` has the bird over the middle of the
playfield, drawn by `blit_mask_wide` and `blit_sprite_planes`. The middle picture ends the same
kind of run: the score it really earned beats the blank record, which is what `check_highscore`
reports when it puts the entry screen up, and `hiscore_key_input` then types the name one console
key per call. The one thing staged there is the last-life flag itself — bounded self-play cannot
reach a real game over, because the frame loop's own glue refuses a lap once the game is finished
and the record taken.

The last is a sheet of the game's own bitmaps, at their own addresses, drawn by the five routines
that draw them in play — only the destination is ours, plus one row count: the lava flames take
theirs from a ground-burn block that only a later wave ever arms, so a cold image has nothing to
read and the sheet supplies the height instead. `draw_object_data` lays out the five rider
sets in three poses plus the three unseated ones, `draw_egg_sprite` the three egg poses,
`blit_sprite_planes` the pterodactyl's four wing beats out of `ptero_frame_table`,
`troll_draw_hand` the lava troll's hand frames out of `troll_sprite_table`, and `blit_sprite` the
four lava flames. No two of them describe a sprite the same way — the rider and egg blitters take
an absolute destination and read `draw_shift`/`draw_rows` as **bytes**, the bird and the hand take
an offset from `screen_base` and read the same two addresses as **words** — which is a width clash
in the original, reproduced rather than tidied.

---

## Quick start

**Prerequisites:** Ghidra 12 (scripts are Java — Ghidra 12 dropped Jython), JDK 21, Python 3.10+,
a C compiler, and the Hatari emulator plus your own TOS ROM for on-target runs.

```bash
# 1. reverse a binary of your own
bash tools/new_project.sh mygame path/to/GAME.PRG
bash projects/mygame/run.sh

# 2. reproduce the Buggy Boy reconstruction (needs your own game files in projects/buggyboy/bin/)
cd projects/buggyboy/recreate
make venv && make test          # builds the Musashi oracle + the C cores, runs the differential suite
make bench                      # per-frame cost: original 68000 vs the reconstruction

cd ../remaster
make test                       # pixel-equivalence against the verified cores

# 3. ...or the Joust one (needs your own bin/JOUST.PRG under projects/joust/)
cd ../../joust/recreate
make venv && make test          # the shared kit's oracle + the C cores, the differential suite
./.venv/bin/python ../gen_readme_assets.py   # re-render this README's Joust images, host-side
bash atari/build.sh && bash atari/run.sh     # ...or play it on a 68000, under Hatari
```

## Repo layout

```
reverse/
├── docs/                     transferable knowledge, one file per expertise domain
├── tools/                    game-agnostic tooling
│   ├── prg_dis.py            GEMDOS .PRG analyzer + 68000 first-pass disassembler
│   ├── extract_graphics.py   ST 4-plane / RLE graphics → PNG
│   ├── depack_gamex.py       static depacker for the Gamex/"PP" LZSS cruncher
│   ├── ghidra_scripts/       PrgLoader · AtariOsTrapAnnotate · ExportDecompC · ApplyNames · …
│   ├── headless.sh           bootstrap: import → load → analyze → annotate → export
│   ├── reapply.sh            fast naming loop: apply names.txt → re-export
│   ├── hatari_run.sh         run a game in Hatari (unpack in-place, then dump memory)
│   ├── new_project.sh        scaffold projects/<name>/
│   └── recreate_kit/         shared differential harness: PRG loader, Musashi oracle,
│                             TOS traps — bound to a game by its recreate/project.toml
└── projects/                 one directory per game, scaffolded by new_project.sh
    ├── buggyboy/             names.txt · decomp.c · recreate/ · remaster/ · docs/
    └── joust/                names.txt · decomp.c · recreate/ (+ atari/ — the playable PRG)
```

## Documentation

Thirteen domain guides, each grounded in real evidence from the two solved games but written as
general procedure.
Start with [`docs/00-overview.md`](docs/00-overview.md) for the end-to-end workflow and a "what kind
of file is this?" decision tree, then [`docs/agent-playbook.md`](docs/agent-playbook.md) for the
verification loop that ties the rest together. Full index: [`docs/README.md`](docs/README.md).

| | |
|---|---|
| [binary-formats](docs/binary-formats.md) | parse a `.PRG`/`.TOS`/`.TTP`, its header, symbols, relocations |
| [packed-executables](docs/packed-executables.md) | the entry is garbage — depack via Hatari before analyzing |
| [m68k-disassembly](docs/m68k-disassembly.md) | read 68000 asm, avoid sweep desync, spot jump tables |
| [ghidra-pipeline](docs/ghidra-pipeline.md) · [ghidra-gui](docs/ghidra-gui.md) | drive Ghidra headless, then explore interactively |
| [tos-os-calls](docs/tos-os-calls.md) | GEMDOS/BIOS/XBIOS/GEM calls, basepage, loaders |
| [hardware-map](docs/hardware-map.md) | video/sound/MFP/IKBD registers, interrupts, Line-A |
| [graphics](docs/graphics.md) · [sound](docs/sound.md) | planar bitmaps, palettes, RLE; the YM2149 driver |
| [on-target-execution](docs/on-target-execution.md) | run the verified reconstruction on real hardware |
| [methodology](docs/methodology.md) | actually name things: anchors → outward, verify, iterate |

## Use it on another binary

Nothing above is game specific except the two directories under `projects/`. `new_project.sh`
scaffolds a new target, the Ghidra scripts and the naming loop work on any GEMDOS executable, and
the differential harness is now a shared component rather than a pattern to copy — `recreate_kit`
takes the entry addresses and the memory image from a `project.toml`, as Joust's second use of it
showed. If the entry point disassembles to garbage the binary is packed; `prg_dis.py` prints
entropy, and [`docs/packed-executables.md`](docs/packed-executables.md) covers unpacking it — live
in Hatari and analyzing the memory dump, or statically once the packer is understood.

## Credits & legal

**Buggy Boy** for the Atari ST — *program and graphics by Martin W. Ward, sonics by Jas. C. Brooke*
(both credited on the game's own intermission screen, reproduced above), published by Elite Systems
International, 1988 (per the copyright string in the binary itself). All rights in the game belong
to their respective owners.

**Joust** for the Atari ST — the title screen the reconstruction draws above is the binary's own
credit, verbatim: *"PRESENTED BY ATARI CORPORATION"* and *"COPYRIGHT 1985 BY THE RUGBY CIRCLE,
INC."*, the two strings `title_screen` reads out of the program image at `0x183d5`. Joust itself is
Williams Electronics' 1982 coin-op, of which this is a licensed home conversion; the copy analysed
here is the later Gamex release, whose own `README.TXT` is signed "PP". All rights in the game and
in the arcade original belong to their respective owners.

This repository contains **no game code or data** — no executable, no `COURSES.DAT`, no
`GRAPHICS.GRA`, no `JOUST.PRG`, no `JOUSTS.CTE`, no `HIGH.SCO`, no TOS ROM image. It holds analysis,
documentation, tooling, and independently written C. The images in this README are output of that
reconstruction, included to document what it produces; reproducing them at all requires the game
files this repository does not ship. Running any of it requires a copy of the game you already own.

Reverse engineering here is for interoperability, preservation and study.

**License.** The work in this repository — the tooling, the documentation and the reconstructed C —
is Copyright © 2026 Geoffrey Anneheim and released under the **GNU General Public License, version
2** ([`LICENSE`](LICENSE)). That covers this repository's own contents only; it grants no rights in
Buggy Boy or Joust, both of which remain the property of their owners.
