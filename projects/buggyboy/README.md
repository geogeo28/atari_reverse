# Buggy Boy (Atari ST) — the worked reference project

Elite's **Buggy Boy** (pseudo-3D racer, Elite Systems, 1988), **coded by Martin W. Ward** (string at
`0x7e20`; the `"MARTIN"` in the score display is his name), is this workspace's worked reference:
solved end to end — loader, road data, graphics, sound driver, **91/91 functions named** — and then
taken one stage further than any other project here, into a free, optimized remaster that is
**pixel-identical** to what the original drew. **91/91 functions verified** · **~20 000 lines of
reconstructed C** · **81 test modules** · **driveable on a 68000**. Use it as a template for how a
solved project looks.

> **No game data is distributed here.** No `.PRG`, no `COURSES.DAT`, no `GRAPHICS.GRA`. Bring your
> own copy; see [Credits & legal](../../README.md#credits--legal).

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
against stage 2's verified cores. Buggy Boy is the one project in this workspace that went through
all three.

## Files

```
bin/        START.PRG (loader) · BUGGYBOY.PRG (game) · COURSES.DAT · GRAPHICS.GRA · BUGBFALC.S (Falcon launcher src)
names.txt   the full name map (fn/var/cmt) — source of truth
decomp.c    decompiled C for all 91 functions (regenerate: reapply.sh)
ghidra_proj Ghidra DB (open: ghidraRun → open this dir)
out/        gfx/ (colour sprite screens) · courses_bitmap.png · dis.txt (first-pass 68k)
            sprite_audit/ — per-page PNGs + coverage.bin (sprite_audit.py --out; not committed)
run.sh      bootstrap (re-import — wipes names) ; reapply.sh  apply names.txt + re-export
recreate/   the proven C reconstruction + its differential harness (STATUS.md, per function)
remaster/   the free re-implementation and the playable PRG (STATUS.md, per subsystem)
tools/      sprite_audit.py — GRAPHICS.GRA read-coverage audit (run it with `make audit` in recreate/)
docs/       function_graph.html — interactive d3 call-graph explorer (regenerate: gen_graph.py)
            sprite_audit.md — what the game ships and never draws (regenerate: tools/sprite_audit.py)
            docs/assets/ — the media set gen_assets.py produces, manifest.json links each to its functions
```

## Gallery

Everything below was **rendered by the reconstruction**, then decoded from the Atari's 4-plane
framebuffer with the game's own palettes. Regenerate the whole set — byte-identical every run — with
`gen_readme_assets.py`, run under `recreate/`'s venv.

### In-race frames — three courses, driven for real

Staged from the real course data, driven with the throttle held through the verified `game_update`,
then drawn by the verified render pipeline (road → scroll → objects → HUD).

| `OFFROAD` | `NORTH` | `SOUTH` |
|:---:|:---:|:---:|
| ![](../../assets/buggyboy/race-leg0.png) | ![](../../assets/buggyboy/race-leg1.png) | ![](../../assets/buggyboy/race-leg4.png) |

The course map in the top-left corner is built per leg by `init_leg_dash` out of `COURSES.DAT` and
blitted every frame by `draw_dashboard`; the trace along it is the player's live progress.

### Screens

| Credits | Leg board | High scores |
|:---:|:---:|:---:|
| ![](../../assets/buggyboy/screen-credits.png) | ![](../../assets/buggyboy/screen-leg-select.png) | ![](../../assets/buggyboy/screen-highscore.png) |

### Course data and sprites

`COURSES.DAT` turned out not to be a script but road-slice **bitmap** data, streamed eight bytes at a
time through a circular buffer. Walking it recovers each leg's shape:

| `OFFROAD` | `WEST` |
|:---:|:---:|
| ![](../../assets/buggyboy/course-legmap-0.png) | ![](../../assets/buggyboy/course-legmap-3.png) |

`GRAPHICS.GRA` is a sprite table plus an RLE stream that unpacks to eight 320×200 four-plane atlases:

| Gates & score markers | Roadside scenery |
|:---:|:---:|
| ![](../../assets/buggyboy/sprites-page3.png) | ![](../../assets/buggyboy/sprites-page4.png) |

[`docs/function_graph.html`](docs/function_graph.html) is a standalone call-graph explorer covering
all 117 functions — open it in a browser, no server needed. With your own copy of the game you can
go further: `gen_assets.py` regenerates the full media set (every sprite page, per-object roadside
crops sliced by driving the real blitter, buggy animations as GIFs, and the soundtrack re-rendered
through the reconstructed YM2149 driver), and re-running `gen_graph.py` attaches all of it to the
functions that produce it. Generated media is not stored in this repository.

## Stage 1 — Disassemble & name

Load the `.PRG` at load base `0x10000`, let Ghidra analyze, then iterate a plain-text name map until
the decompilation reads like source. `names.txt` is the source of truth — one directive per line,
addressed as Ghidra sees them (image offset + load base):

```
fn   0x1555e draw_hud
var  0x18c38 leg_index
cmt  0x1110e game_update: input, integrate throttle->speed, steering->road_curve, stream course…
```

The method is **anchors outward**: start from ground truth an emulator cannot dispute — GEMDOS/BIOS
trap numbers, DRI symbols, hardware register addresses, string literals — and propagate along the
call graph. Then *verify by reading the body*; several confident first guesses in this project were
wrong until someone actually read the code ([`docs/methodology.md`](../../docs/methodology.md)).

**Result: 335 name directives, all 91 functions named**, plus a decoded loader, course format,
sprite format, event jump table and sound driver:

- **START.PRG** — a custom loader (not the game): sets low-res, LZ-unpacks a title
  bitmap, prints a machine/TOS/RAM banner, then `Fopen`/`Fread`s `BUGGYBOY.PRG`, applies
  its DRI relocations by hand, fabricates a basepage, and `jmp`s in. →
  [`tos-os-calls.md`](../../docs/tos-os-calls.md).
- **BUGGYBOY.PRG** — `main` (never returns): GEM `appl_init → graf_handle → v_opnvwk`, Malloc
  buffers, install sound `REFRESH` on the VBL, then attract/gameplay loops. Frame =
  `game_update → draw_frame[build_road_geometry → render_road → blit_road_scroll →
  draw_game_objects → draw_hud]`. → [`methodology.md`](../../docs/methodology.md).
- **Controls**: joystick (IKBD interrogate `$fffffc00`) then keyboard fallback (arrows +
  space) → `input_state`. Physics: input → `engine_rpm` → `speed`; steering → `road_curve`.
- **COURSES.DAT** — *not* a script: road-slice **bitmap** data, streamed 8 bytes at a time
  through a `0x2000` circular buffer and shifted to draw the curving road. →
  [`graphics.md`](../../docs/graphics.md).
- **GRAPHICS.GRA** — a 0xd00-byte sprite table + RLE-compressed (`0x1234`/`0x5678` runs) →
  8× 320×200 4-plane sprite atlases (logo, buggies, scenery, HUD, font). Extracted to
  `out/gfx/` with palette `0x7f9e` (skip `0xd00` to clear the leading table). →
  [`graphics.md`](../../docs/graphics.md).
- **Course-event engine** — an offset **jump table at `0x11aa2`** (129 entries) dispatches
  course-script opcodes → `evt_flag_gate` / `evt_collision` / `evt_score_msg` → `add_score`
  (BCD) + `play_event_tune`. A second table at `0x13144` dispatches roadside-object sprites.
- **Sound** — driver at `0x1b2xx` (`snd_voice_a/b`, `snd_cmd_handler`), the DRI-symbol
  `INITTUNE`/`EG*`/`REFRESH` family, run from the VBL. → [`sound.md`](../../docs/sound.md).

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

**Status: 91/91 verified.** See [`recreate/STATUS.md`](recreate/STATUS.md) for the per-function table
and how each one was pinned.

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
- **Phase B — gameplay: complete.** Course streaming, the object ring, player physics, the
  crash/auto-steer script, collision probing, event dispatch and the sound driver are ported and
  frame-exact; the shipping `BUGGYBOY.PRG` plays end-to-end.
- **On target:** `BUGGYBOY.PRG` — the playable game, with sound — cross-compiles back to m68k and
  runs under Hatari and on a real ST/STE, loading the unmodified `COURSES.DAT` and `GRAPHICS.GRA` at
  boot. It boots into the leg select; each leg's start frame is byte-identical to the
  reconstruction's (`run_golden.py`, all five legs), and it is driveable.

See [`remaster/STATUS.md`](remaster/STATUS.md) for the per-subsystem table.

## Play it

`remaster/` is a free, playable re-implementation of the game (pixel-identical to the original's
renderer, verified per frame). It runs on a real ST/STE and in Hatari.

```bash
cd remaster
bash render/atari/build_game.sh          # -> render/atari/disk/{BUGGYBOY.PRG, COURSES.DAT, GRAPHICS.GRA}
bash render/atari/game_run.sh            # play the remaster in Hatari
bash render/atari/game_run.sh original   # play the ORIGINAL binary, same emulator setup, for comparison
```

On real hardware, copy the whole `render/atari/disk/` folder to a floppy or hard-disk partition and run
`BUGGYBOY.PRG` — it loads `COURSES.DAT` and `GRAPHICS.GRA` from the directory it was started in. The
game needs **low resolution** (320x200, 16 colours) and about 1 MB of RAM; it binds the STE blitter
automatically when it finds one.

### How the game goes

**Leg select** → pick one of five legs → **get ready** (the countdown) → **drive the leg** → the leg
ends on the timer or a crash tally → if you made the leg's high-score table, **enter your initials** →
the **attract/demo** cycle plays → back to the leg select. That whole outer loop is the original's.

You are driving a buggy over a course of five legs; steer between the gates and flags, avoid the
scenery, and reach the checkpoints before the clock runs out.

### Controls

Arrows steer and accelerate, **Space** is fire/gear, **F1**–**F5** jump straight into a leg, **Esc**
aborts a leg and **Q** quits to the desktop. A joystick in port 1 has priority over the keyboard.

**The full key table** — every key across the race, leg-select and name-entry screens, with the
joystick rule and the two fidelity notes — is in
[`remaster/README.md`](remaster/README.md#controls), next to the game it describes.

### Hidden features, text and cheats — audited

There are none to find: **no cheat codes and no debug mode**. Every scancode compare in the binary was
mapped to its function, every string in the data segment was decoded with the game's own glyph font and
cross-referenced, and every byte of the text segment between named functions was accounted for (data
tables, blit tails, a two-entry `Setscreen` helper). The complete key surface of the original is the
table above plus the `remaster/README.md` one — arrows, Space, F1–F5, F6, F10 + Return, G, Help, Esc —
and no other key is ever compared. `START.PRG` reads no key at all. The only unreachable code is
`evt_collision` @ `0x11c2c`, a dead event handler that would have cut the revs on a collision.

Two things the audit did turn up:

- **F10 is a disk-swap prompt, not a "reload".** `draw_panel3` prints
  `INSERT 'TRAK-PAK' OR 'BUGGY BOY' DISK THEN PRESS RETURN`, then `load_graphics` re-reads
  `COURSES.DAT` (a fixed 63,072 bytes) and `GRAPHICS.GRA` and the score table is rebuilt — so this
  build was prepared for Elite's **Trak Pak** compilation release (the publisher's box-set line), whose
  disk carries the same two files. It is not the Super Off Road "Track-Pak" expansion, and it cannot
  add courses to this game: the leg index is clamped to 0–4 everywhere (F1–F5, the joystick nav, the
  attract cycle) and every per-leg table has five entries.
- **The author signed the HUD buffers.** The score string at `0x18230` ships as `/1//MARTIN` and the
  speed-text field at `0x1823c` as `WARD`. `init_leg` copies the `/1///////0` template over the score
  string before the first frame, and `draw_hud` rewrites `0x1823c` with the speed digits every frame
  into a string nothing ever blits (that write is the binary's only reference to it), so neither is shown.
  The visible credits (`PROGRAM AND GRAPHICS BY MARTIN W.WARD`, `SONICS BY JAS.C.BROOKE`,
  `© ELITE SYSTEMS INTERNATIONAL 1988`) are drawn by `draw_intermission` and `fade_step` in the attract
  cycle. The `=` glyph seen in `TIM=` / `NAM=` / `W=ST` is a narrow alternate `E`, not a typo.

Unused artwork in `GRAPHICS.GRA`: see [`docs/sprite_audit.md`](docs/sprite_audit.md)
(`tools/sprite_audit.py` regenerates it).

## Regenerate

Everything below needs your own game files in `bin/`.

```bash
# stage 1 — the naming loop
bash reapply.sh    # names.txt -> ghidra_proj + decomp.c (fast)
bash run.sh        # full re-import + analysis (only if starting over; wipes names)
python3 ../../tools/extract_graphics.py bin/GRAPHICS.GRA out/gfx \
        --pal-file bin/BUGGYBOY.PRG --pal-off 0x7f9e --skip 0xd00   # colour sprites

# stage 2 — the differential
cd recreate
make venv && make test          # builds the Musashi oracle + the C cores, runs the differential suite
make bench                      # per-frame cost: original 68000 vs the reconstruction
./.venv/bin/python ../gen_readme_assets.py   # re-render this README's images, host-side

# stage 3 — the remaster
cd ../remaster
make test                       # pixel-equivalence against the verified cores
```

## Open threads (optional)

- Finer names for the leaf draw/HUD helpers still carrying a `# ctx` tag in `names.txt` — named from
  call-context, refinable by reading their bodies.
