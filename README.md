# Atari ST — from binary to remaster

Recovering lost 1980s Atari ST games from their shipped executables: disassemble one, name every
function, rewrite it as readable C **proven byte-for-byte against the original machine code**, and
run that C back on a 68000. The tooling and the [documentation](docs/README.md) are game-agnostic —
point them at any GEMDOS `.PRG`. **Three games are solved with them.**

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

**Wonder Boy in Monsterland** (Activision/Sega, 1989) is the third, and the first taken from
original, uncracked disks rather than from a release someone had already stripped: **330 functions
verified** · **41,652 bytes of the original's machine code** · **6462 differential tests** · and a
`.PRG` that is the first thing in this repository to leave the emulator entirely. It boots a **real
4 MB STE from its own 720 KB floppy**, through TOS's `AUTO` folder, with no host in the machine —
and three sessions at that machine found two defects every emulated surface here had been green on.
See [The third game — Wonder Boy in Monsterland](#the-third-game--wonder-boy-in-monsterland).

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
— no stage 3. Wonder Boy takes the same two stages and then carries the `.PRG` one rung further
than either: not just onto the 68000 under an emulator, but onto a **real Atari STE, booted from a
720 KB floppy the build writes itself**, which is where the last two bugs were found.

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
with the game's own palette words. Every picture is a function of the binary alone — the
high-score record staged is the blank one the `.PRG` itself carries, not the save file next to it
— so the whole set is byte-identical every run.

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

## The third game — Wonder Boy in Monsterland

[`projects/wonderboy/`](projects/wonderboy/) is the same pipeline pointed at a game that never
reaches an operating system. `AUTO/SWB.PRG` makes **one trap instruction in 136 KB** — a `Super` —
and drives the WD1772 floppy controller and the DMA chip itself, with its own FAT12 layer, because
the copy protection lives in sectors numbered outside the standard range that no OS call can
address. It also copies itself to the absolute address `$400` and lives there, so Ghidra recovers
57 functions at the workspace's default load base and 186 at the right one. Two original Pasti
`.stx` images go in; a solved resource cruncher, a decoded FAT12 filesystem and a named 68000
program come out.

**Four things had to move in the tooling, and three of them are now shared.** The kit gained a
**file-load seam**: a game whose boot chain bottoms out in a sector driver cuts it at the lowest
routine whose inputs are *file-shaped* — a name and a destination — and calls `disk_read_file`
across the cut, which is the staged-file model off target and real GEMDOS on it
([`TRAP_MODEL.md`](tools/recreate_kit/TRAP_MODEL.md)'s Phase 9). The **boot chain is composed from
slices** rather than ported as one routine, because the original cuts itself into four with fire
waits only an IKBD interrupt can end: `boot_title_screen`, `boot_credits_screen`, `boot_load_stage`
and `boot_prompt_screen`, each verified whole against the oracle across the seam. The port has
**one shifter sink** (`src/shifter.c`) — the screen base and the sixteen colour registers are off
the 68000's 24-bit bus as far as the loaded image goes, so every write to them meets in one file
with one on-target arm, and a build gate refuses a second copy of it. And `atari/mkprg.py`,
`tools/st_build.py`, [`atari/HARDWARE.md`](projects/wonderboy/recreate/atari/HARDWARE.md) and
`tools/assert_trap_registers.sh` are what turn the cross-compiled cores into a **bootable 720 KB
FAT12 floppy** and keep them safe on the way — that last one because TOS preserves fewer registers
across a trap than GCC's m68k ABI believes are callee-saved, which was three bombs in Buggy Boy.

**Status: 330 functions verified · 41,652 bytes of the original's machine code · 6462 differential
tests** (plus 392 in the shared kit), and the per-function table, every boundary and every limit
that is disclosed rather than closed are in
[`recreate/STATUS.md`](projects/wonderboy/recreate/STATUS.md). What the harness can and cannot see
is measured rather than asserted:
[`recreate/PORTABILITY.md`](projects/wonderboy/recreate/PORTABILITY.md) reports that **80.7 % of
the program's believed code is now inside the measurement**, and that only 226 bytes of it remain
genuinely unknown.

**On target the ladder runs to ten rungs.**
[`recreate/atari/`](projects/wonderboy/recreate/atari/README.md) cross-compiles the same verified
cores to m68k and climbs from "a real machine drives the reconstruction" (M1: `vbl_handler` runs on
the level-4 autovector fifty times a second, and its own word has to agree with the shim's
independent tick count) to "the reconstruction boots itself off a floppy" (M10). In between: at four
anchored frames of real play the **32000 framebuffer bytes**, the **sixteen hardware pens** and
Hatari's own **rendered picture** are identical to the shipped 1989 binary's, on EmuTOS and on TOS
1.04 (M2/M5); the screen-base publications match flip for flip, and the shipped binary's 1,155 PSG
writes over the window are an exact prefix of ours (M6); the boot chain then **recomputes** the
post-boot RAM those rungs had staged from a dump of the original — **~522,500 of 523,272 bytes
identical, the rest inside ten named bands and nothing unnamed left over** (M8); and M9 wires every
one of `game_main_loop`'s five endings back into the boot chain, so `atari/run.sh` opens a build
that boots its own title screen, reloads on a round end and restarts on ESC. M10 puts all forty
resources and the 144,831-byte `WB-ownrun.PRG` on one 720 KB disk — **689,152 bytes in 673 clusters,
38,912 free of 728,064** — booted by TOS's own `AUTO` loader with no host directory behind it.

**Then somebody switched an Atari on, and it said two things nothing here could.** The disk booted
a 4 MB STE (TOS 1.62) **to the desktop**: our own `vbl_handler` was counting down an idle fuse that
expired one vblank into the first GEMDOS sector read, dropped the drive-select lines mid-transfer,
and the ROM's retry did not re-select. The protocol that arms and disarms that fuse lives in two
instructions *below* the declared seam, so the substitution had dropped it — and because the arm
overwrites the disarm, a final-memory differential sees the same bytes either way and cannot ask
the question at all. Fixed, and the disk came back with **the title screen up and fire doing
nothing**. The boot's eight-byte `init_ikbd` sends the only IKBD command in the whole binary —
`$12`, *disable mouse* — and the port had not reproduced it; on a real ST joystick 1's fire line
and the mouse's right button are the same wire, so the 6301 was reporting every press as a mouse
packet the game does not read. The machine's own record showed 35 IKBD bytes delivered and not one
of them a joystick report. Both fixed, and the third run played: title, fire, credits, fire, stage
1's overlay, tiles and sprites, and the frame loop — on the machine. The two shapes are entries
**11** and **12** of [`docs/on-target-execution.md`](docs/on-target-execution.md)'s twelve-entry
taxonomy — *a live interrupt handler reading state whose protocol lives below a declared seam*, and
*a gate crossed by a poke is a gate whose input path never ran* — and they are Wonder Boy's own two
contributions to it from the machine. It is not the first: entry 3's register half is Buggy Boy's
three-bombs-on-the-STE crash, found the same way.

### Gallery — Wonder Boy

Rendered **host-side by the reconstruction**, with no emulator and no TOS ROM in the loop:
`projects/wonderboy/gen_readme_assets.py` loads your own `SWB.PRG` through the kit, serves the
game's own resource files across the file-load seam, and drives the same entry points the tests
drive — the four composed boot slices and `game_main_loop` itself — then de-interleaves the
framebuffer they paint with the game's own palette words. One thing the seam cannot do:
`SPRITES.CRU` is 279,034 bytes and the kit's whole staging area is 258,048, so the file is placed
at the address the boot's own load lands on and the stage's sprite install is redone over it whole
— with every marked sprite's installed cells then checked byte for byte against the file, because
without that check 28 of stage 1's 143 sprites quietly installed depacked tile data instead. The
two vertical-blank waits inside `flip_screen` are answered by the kit's scheduled-write model and
the play frames come from one fixed joystick script. The game's only entropy is the shifter's
video address counter at `$ff8207`/`$ff8209`, which `rng_next` and `bcd_add_random_1_to_4` read
and which the kit's seeded-hardware model answers with whatever the run declares: on a machine
that counter is a clock, so each play frame here declares the next byte of **one fixed
pseudo-random sequence keyed by the frame index** rather than a single constant for the whole run.
The whole set is therefore a function of the binary, the game's own files, that joystick script
and that sequence — which the script asserts by rendering it twice and comparing.

Every play picture is drawn on a screen the **whole boot chain** built, in the boot's own order —
the prologue's clears, then the title, credits and stage slices — because the status panel's
artwork is drawn by no routine at all: it is part of the CREDITS picture, which
`boot_credits_screen` copies down onto the buffer the shifter is showing, and the play window is
then painted over the middle of it. That is checked rather than assumed: at the instant
`boot_load_stage` returns, **both 32000-byte screen buffers are byte-identical to the original
1989 binary's own post-boot RAM** — `atari/build/ORIGRAM.BIN`, dumped off the shipped game under
Hatari at `$f8b4`, the same anchor the on-target rungs use — and the script fails if one byte of
either differs.

| Title | Credits | The data-disk prompt |
|:---:|:---:|:---:|
| ![](assets/wonderboy/title.png) | ![](assets/wonderboy/credits.png) | ![](assets/wonderboy/prompt.png) |

`boot_title_screen` ($e512..$e550) arms the protection, asks `load_resource_by_index` for
`TITLESCR.RAD` across the seam, inflates it with `rad_depack` straight onto the screen buffer and
hands its palette row to `set_palette`. `boot_credits_screen` does the same for `CREDITS.RAD`,
copies the result down onto the buffer the shifter is showing, and then runs `game_restart_reset`
over it — a new game, which is what draws the status panel's lives over the picture. The third is
`boot_prompt_screen` ($e494..$e4d4), the slice all three of the game's `jmp $e494.l`
endings land in: ESC, the game-over box expiring, and the message terminator the protection's own
failure path also reaches.

| Stage 1 begins | …and is played | The cast |
|:---:|:---:|:---:|
| ![](assets/wonderboy/stage1-start.png) | ![](assets/wonderboy/stage1-walk.png) | ![](assets/wonderboy/sprites.png) |

`boot_load_stage` ($e5ba..$f8b4) is the fourth slice and the longest: the level-sequence row, its
overlay, `TILEDATA.RAD` through `bg_tile_install`, `SPRITES.CRU` through `sprites_cru_install`,
the actor tables, and `stage_load_window`, which fills the scroll engine's **eight pre-shifted
copies** of the visible window. Everything after that is the frame loop's own fifteen calls, run
whole and in its order: the two keyboard ones, then the round bonus, then `panel_refresh_frame`
over `hud_draw_lives`, `hud_draw_meter` and the rest, the scene driver, and
`game_latch_input_and_step_actors` — which is where the joystick edge and every actor's behaviour
happen. Then the drawing: `project_followed_actor`, `bg_scroll_run_queue`, `project_actor_list`,
`bg_scroll_blit` — whose sixteen straight-line bodies, `bg_scroll_copy_x0` through `_x15`, differ
only in where each splits its thirty `move.l`s about the source row's 128-byte ring seam —
`game_snap_follow_cursor`, `sprite_draw_pass` and the twelve blitters it dispatches into
(`blit_sprite_w2`..`w5` and their left- and right-clipping siblings), `actor_spawn_pass`,
`text_run_message_box`, and `flip_screen` last. The middle frame is lap 157 of a fixed joystick
script — walk held, jump on a beat, fire on another — and it is **not a lap number chosen here**:
the run stops at the first frame that draws at least three sprites whole inside the play window,
and fails if none does, so a caption naming what is in a picture cannot go stale under a fix that
shifts the run. What that frame has is the hero in the air between a spinning gold coin and the
tree stump with the shop's door in it, with a red cobra on the ledge ahead beside the arrow sign.
The sheet beside it is the game's own bitmaps at their own addresses, drawn by `sprite_draw_pass`
onto the screen `clear_both_screens` left behind; only the destinations are ours. Which twenty are
shown is not a list chosen here either — it is every sprite that same run actually put into a
screen record, so the sheet is this stage's cast rather than a selection: four green snakes, two
red cobras, four frames of the hero's own walk, the seven-frame spin of a gold coin, and three
boulders.

| Round 4 — over the brick platforms | Round 5 — the wood | Round 5 — the vine shaft |
|:---:|:---:|:---:|
| ![](assets/wonderboy/stage4-sky.png) | ![](assets/wonderboy/stage5-woods.png) | ![](assets/wonderboy/stage5-cave.png) |

The later rounds are reached through **the game's own level-skip cheat**, typed rather than poked:
`game_key_actions`' walk at $5a8 steps a cursor along the four scancodes the binary carries at
$608 — `$61 $30 $13 $1e`, which are UNDO, B, R and A — and raises the cheat word when the cursor
meets its terminator. With that word up, N takes the arm at $556, which pops the frame loop's
return address and `jmp`s to $e5ba: `boot_load_stage` again, one sequence row further on. The
reconstruction cannot make that transfer, so it reports `WB_KEY_ACTIONS_LEVEL_SKIP` and the caller
runs the slice — which is exactly the wiring the on-target build uses for the same ending. One
thing here is this script's own and not the game's: the sequence cursor is put at the row before
the one being shown, because the honest route to round eight — playing there — is not something a
fixed joystick script can do. Everything either side of that is the boot's.

Two things about **which** rounds these are came out of getting the pictures wrong first, and both
are now checks rather than choices. The script takes the walk direction from the loaded row's own
start record: `boot_load_stage` drops the hero at `WB_START_FOLLOW_X`, and two of these rows start
him at 1928 and 1432 — the far end of a map he is meant to walk *back* along, with an arrow tile on
the ground saying so. Holding right there pinned him against a wall for 1400 frames with every
creature off the left edge, which is what the first published desert and castle pictures were. And
`sprites_cru_install` writes an UNMARKED sentinel into every descriptor the **round's** mask does
not mark, wholesale — rounds 2, 3, 10 and 11 do not mark the frames of a hero who has not picked up
the armour of the rounds before him, and arriving with a round-1 hero is exactly what the cheat
does, so in those rounds he was drawn as a band of scrambled bytes at his own position. The town of
round 2 and the golden keep of round 11 were in this gallery until that was found; the set is now
chosen among the rounds the skip can honestly show, and the script refuses a picture whose hero has
no cells.

| Round 6 — the spiked corridor | Round 8 — over the lava |
|:---:|:---:|
| ![](assets/wonderboy/stage6-dungeon.png) | ![](assets/wonderboy/stage8-lava.png) |

Each is a different overlay file, and each frame was chosen the same way stage 1's was — the first
frames 100…800 with at least a stated number of sprites whole inside the window, asserted before
the PNG is written. So the wood really does have three monkeys in its trees with gold hanging
between them — and a `GOLD` counter reading 16 beside a `SCORE` of 20, both earned by that run —
the vine shaft really has a blue flier, a falling boulder and thrown blades around a helmeted hero
with his sword out, and the lava has three creatures and two more pieces of gold. The message box
every stage entry posts — the frame loop's fourteenth call, `text_run_message_box`, composing the
first entry of the message table at `$a09c` — is long gone by then, so it is checked on the way
past at frame 30 instead of photographed, and checked in both directions: three of these five rows
hold it over frames 0…49 exactly, and two — the vine shaft and the lava — post no message at all.

The panel is the same one in all seven play pictures, and reading it is the quickest way to see
that the boot chain did its work: `LIFE`, `SCORE`, `HIGH`, `GOLD` and the slot frames are the
credits picture's own artwork, while the hearts, the digits and the `RND:` number are what
`game_restart_reset`, `panel_refresh_frame` and the `hud_draw_*` routines paint over it. `RND:` is
also the quickest check on a figure this README once had wrong: `WB_STAGE_NUMBER` is packed BCD, so
`$11` is round eleven and not seventeen, and the panel spells the digits out. Four of the data
disk's overlays are damaged on the pressed original — `OVALAY4B`, `OVALAY5B`, `OVALAY6A` and
`OVALAY9A`, the only files this project keeps two corpora of — and every picture here is rendered
from the **authentic** `bin/disk2/` dump, with the script refusing to load one of those four, so
no stage that needs them is shown.

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

# 4. ...or the Wonder Boy one (needs your own bin/disk1/ and bin/disk2/ under projects/wonderboy/)
cd ../../wonderboy/recreate
make venv && make test                       # the shared kit + the C cores, the differential suite
./.venv/bin/python ../gen_readme_assets.py   # re-render this README's Wonder Boy images, host-side
bash atari/build.sh ownrun && bash atari/run.sh   # ...or play it on a 68000, under Hatari
python3 atari/smoke.py floppy                # ...or build atari/out/WBOOT.ST — a bootable 720 KB
                                             # FAT12 floppy carrying the build and all 40 resources.
                                             # gw/write_disk.sh puts it on real media; see
                                             # atari/HARDWARE.md for the STE runbook.
```

## Repo layout

```
reverse/
├── docs/                     transferable knowledge, one file per expertise domain
├── tools/                    game-agnostic tooling
│   ├── prg_dis.py            GEMDOS .PRG analyzer + 68000 first-pass disassembler
│   ├── extract_graphics.py   ST 4-plane / RLE graphics → PNG
│   ├── depack_gamex.py       static depacker for the Gamex/"PP" LZSS cruncher
│   ├── depack_lsd.py         static depacker for the "LSD!" backwards-LZ cruncher
│   ├── ghidra_scripts/       PrgLoader · AtariOsTrapAnnotate · ExportDecompC · ApplyNames · …
│   ├── hw_portability.py     how much of a game a memory-only differential can verify
│   ├── headless.sh           bootstrap: import → load → analyze → annotate → export
│   ├── reapply.sh            fast naming loop: apply names.txt → re-export
│   ├── hw_scan.sh            dump bodies + call graph + hardware accesses → TSV
│   ├── hatari_run.sh         run a game in Hatari (unpack in-place, then dump memory)
│   ├── new_project.sh        scaffold projects/<name>/
│   └── recreate_kit/         shared differential harness: PRG loader, Musashi oracle,
│                             TOS traps — bound to a game by its recreate/project.toml
└── projects/                 one directory per game, scaffolded by new_project.sh
    ├── buggyboy/             names.txt · decomp.c · recreate/ · remaster/ · docs/
    ├── joust/                names.txt · decomp.c · recreate/ (+ atari/ — the playable PRG)
    └── wonderboy/            names.txt · decomp.c · recreate/ (+ atari/ — the PRG, and the
                              720 KB floppy it boots a real STE from) · notes/ · tools/
```

## Documentation

Thirteen domain guides, each grounded in real evidence from the three solved games but written as
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

Nothing above is game specific except the three directories under `projects/`. `new_project.sh`
scaffolds a new target, the Ghidra scripts and the naming loop work on any GEMDOS executable, and
the differential harness is now a shared component rather than a pattern to copy — `recreate_kit`
takes the entry addresses and the memory image from a `project.toml`, as Joust's second use of it
showed. A game binds the kit's optional capabilities the same way: Joust needed none of them,
Wonder Boy needed two — the **file-load seam** (`disk_read_file`, for a boot chain that ends in a
raw sector driver) and the **scheduled-write model** (for a routine that busy-waits on a byte only
an interrupt ever stores). If the entry point disassembles to garbage the binary is packed;
`prg_dis.py` prints entropy, and [`docs/packed-executables.md`](docs/packed-executables.md) covers
unpacking it — live in Hatari and analyzing the memory dump, or statically once the packer is
understood. And if it barely uses the OS at all, check where it really runs: a `.PRG` with almost no
relocations is position-dependent, and Wonder Boy's own README has how that was found.

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

**Wonder Boy in Monsterland** for the Atari ST — the binary carries no copyright string at all, so
the credit reproduced here is the game's own credits screen, drawn by the reconstruction above and
transcribed verbatim: *"WONDERBOY IN MONSTERLAND / 1987 SEGA / WESTONE. / ALL RIGHTS RESERVED. /
ACTIVISION.AUTHORISED USER. / CONVERSION BY IMAGES DESIGN. / GRAPHICS - JASON LIHOU, ANDREW PANG /
MUSIC - DAVID WHITTAKER / PROGRAM - LAURA.P.PAUL."*, over the SEGA and ActiVision logos and the line
*"A SOFTWARE STUDIOS PRODUCTION"*. `names.txt`'s own header dates the release to Activision/Sega,
1989. The arcade original is Westone and Sega's 1987 *Wonder Boy in Monster Land*, of which this is
a licensed home conversion. All rights in the game and in the arcade original belong to their
respective owners.

This repository contains **no game code or data** — no executable, no `COURSES.DAT`, no
`GRAPHICS.GRA`, no `JOUST.PRG`, no `JOUSTS.CTE`, no `HIGH.SCO`, no `SWB.PRG`, none of the `.RAD`
resources (`TITLESCR`, `CREDITS`, `DATADISK`, `TILEDATA` and the thirty-seven `OVALAY*` overlays),
no `SPRITES.CRU`, no disk image of any kind, and no TOS ROM image. It holds analysis,
documentation, tooling, and independently written C. The images in this README are output of that
reconstruction, included to document what it produces; reproducing them at all requires the game
files this repository does not ship. Running any of it requires a copy of the game you already own.

Reverse engineering here is for interoperability, preservation and study.

**License.** The work in this repository — the tooling, the documentation and the reconstructed C —
is Copyright © 2026 Geoffrey Anneheim and released under the **GNU General Public License, version
2** ([`LICENSE`](LICENSE)). That covers this repository's own contents only; it grants no rights in
Buggy Boy, Joust or Wonder Boy in Monsterland, all of which remain the property of their owners.
