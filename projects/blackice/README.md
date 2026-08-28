# BLACK ICE — an original Wolfenstein-3D-class raycaster for the stock Atari STE

**Break into a dying mainframe, strip it for data, and get out before the trace finds your body.**
You are a repossession runner walking the memory map of HALCYON — a Frayne-Bellamy HX-9 that has
been failing for eleven months and whose owners have stopped paying for it — as physical space.
Eight named sectors (INGRESS, THE LEDGER, NURSERY, BAD BLOCK, THE CHOIR, DEAD LETTER, COLD STORE,
THE KERNEL), each with one landmark room a player can describe from memory. The machine's decay is
the visual premise: a healthy sector renders as clean architecture, a failing one renders *wrong* —
grid drift, mismatched textures, doors jammed at 3/8, one room stamped four times. The clock
throttle (UNDERCLOCK / NOMINAL / OVERCLOCK) trades render radius for speed and for how fast the
trace meter climbs, so the frame rate rises exactly when you choose to see less. At 100% trace the
palette hardens and the only way out is the arch you came in through. This is **not** a
reverse-engineering project like the rest of this workspace — it is an original game built on the
knowledge the workspace collected.

**It boots and plays.** `atari/disk/BLACKICE.PRG` runs on a stock STE under Hatari with joystick and
keyboard, the HUD, YM music, the three enemies, the Buster, doors, tokens, pickups and the trace
meter — and its rendered pixels are byte-identical to the portable C reference. It has not yet run
on iron.

---

## Target and honest performance

**Stock Atari STE**: 68000 @ 8 MHz, 1 MB RAM, blitter, DMA sound, 4096-colour palette, PAL 50 Hz.
320×200, 4 bitplanes, 16 colours. Budget: **160,000 CPU cycles per 50 Hz frame**. Single GEMDOS
`.PRG` in `AUTO/` on a 720 KB floppy, no copy protection, no hard-coded TOS internals.
Full constraint list: `design/BRIEF.md`.

The renderer has been measured three times — the Milestone 0 spike, the design's projection from it,
and now the **shipping target itself**. The target's numbers are the ones that count. Hatari 2.6.1,
`--machine ste`, bundled EmuTOS, 1 MB, 100 frames a pass, timed on the MFP's timer C
(`atari/README.md`):

| Pass | Columns | µs/frame | Work fps | **Delivered fps** |
|---|--:|--:|--:|--:|
| **WALK80** — the golden walk, shipping detail level | 80 | **105,650** | 9.46 | **8.33** |
| WALK160 | 160 | 190,691 | 5.24 | **5.00** |
| WCA80 — worst case, window completely full | 80 | 115,582 | 8.65 | 8.33 |
| WCA160 | 160 | 215,549 | 4.64 | 4.55 |
| WCS160 — three near billboards, 6,336 sprite px | 160 | 206,429 | 4.84 | 4.55 |

**Two frame rates, and the second is the one a player sees.** The loop waits for the vertical blank,
so the delivered rate is `50 / ceil(frame_us / 20000)` and nothing in between. WALK80 does 9.46 fps
of work and **delivers 8.33**. Quoting the work rate overstates every pass.

**The BRIEF's frame-rate gate is MISSED, at both column counts.** 80 columns is 3.1–3.2× its
320,000-cycle budget and 160 columns 3.7–4.1× its 480,000 — against a floor of ≥ 14 fps at 160
columns and ≥ 20 at 80. The gate's own conditional (80 becomes the default if 160 misses) has fired
and been taken — `DETAIL_DEFAULT` is `DETAIL_COLUMNS_80` — but 80 misses too, so the next decision
is a real one and `STATUS.md` carries the measured lever ladder it has to be made against. The
25 fps target was withdrawn earlier for a different reason: on a 50 Hz flip lock only 25 / 16.7 /
12.5 fps exist, so there is no 20 fps step to land on.

The hot loops are hand-written 68000 (`atari/render.S`, `atari/cast.S`). The asm cast pass made the
ray cast 22–28% cheaper and the column drawer 13–18%, taking the whole frame down 11–13% and gaining
two of the five passes a whole flip-lock step. Where the frame goes at 160 columns on the walk:
**columns 46%, cast 27%, c2p 24%, sim 2%.** Measured unit rates: wall loop **75.3** cyc/px, c2p
**5,398** cyc per view row, cast **2,540** cyc/ray. The planar band fill (ceiling and floor written
straight to the screen instead of through the chunky buffer) is a measured 40–42% saving on the
whole frame — the largest single lever the spike found, and it is built.

Elsewhere: the audio VBL tick measures **2,962 cycles/frame** (demo tune) and **2,922** with the
game's own score at its fastest band, against a 3,000 budget — 1.9% of a frame. The BFS navigation
field costs **230,000 cycles a rebuild** on level 2 and rebuilds every 8 sim ticks, so **≈28,800
cycles a frame** amortised.

RAM: program + `.bss` **385,751 B**, plus ~89,000 for TOS/GEMDOS = **~473,000 of 1,048,576**, about
**550 KB spare** — the consequence of one texture set resident and of shading by per-pixel remap
instead of baked bands.

---

## Directory map — and the gate each one is held to

| Directory | What it is | Its gate |
|---|---|---|
| `design/` | `BRIEF.md` (constraints), `DESIGN.md` v2.1 (binding GDD), and the decision trail: `CONCEPTS.md` → `CRITIQUE.md` → `DESIGN_REVIEW.md` | review, not code: every BLOCKER/SHOULD-FIX/NIT answered in `DESIGN.md` §19, decisions D1–D4 |
| `pipeline/` | `stepix` — host Python that emits the exact bytes the 68000 reads (palette, planar, texture, sprite, font, `.PAK`/LZSS) plus `depack.c`, the one piece that ships to target | **584 pytest**, plus a Python-pack → C-depack identity cross-check and a 12/12 mutation sweep |
| `art/` | The 16-register palette (`palette.py` owns it), textures, sprites, HUD strip, title screen, key art — all authored as reproducible PIL scripts, no Aseprite | `build_art.py` **refuses the build** on palette / texture-seam / band-agreement / rim-light / HUD-overflow failure |
| `audio/` | YM2149 3-voice VBL replayer, STE DMA one-shot sample voice, the score (`songs/blackice.py`) and the ten cues | `make verify` (19 checks) and `make verify-blackice` (20 checks) — both run the `.PRG` headless in Hatari and analyse the **recorded audio**, not just the register trace |
| `spike/` | Milestone 0: the standalone feasibility raycaster that produced the first cycle figures | `make bench` (the timing table) and `make verify` (geometry + drawing vs a float DDA reference) |
| `include/` | The engine's contracts: `render.h` (chunky layout, `RenderColumn`), `sprite.h` (`RenderSprite`), `game.h` (all mutable sim state in one struct), `game_consts.h` | frozen record layouts, asserted by `test_abi.py` and `host/abi_m68k.c` under the *target* compiler |
| `src/` | The portable C simulation core — engine (raycast, draw, sprite, map, doors) plus the gameplay layer (`ai.c`, `weapons.c`, `pickups.c`, `trace.c`, `entities.c`, `sim.c`). No hardware access, no libc, no floats, no malloc | `make test` (host build + **442 pytest**), `make m68k`, and the **libgcc gate** (clean over 19 objects here, 25 in the target build) |
| `test/` | ctypes-driven pytest over the shared library, plus the pinned replay goldens and the golden walk | part of `make test`; `make goldens` diffs the rendered walk and writes nothing |
| `host/` | The host harness: `main_host` replays and hashes, `play_host` runs the game layer live and prints what it did, `c2p.c` + `render_png.c` turn a frame into a PNG | built by `make`, exercised by `make frames` / `make goldens` |
| `levels/` | The eight authored maps (`*.txt`) and their compiled `*.bil` | `python validate_levels.py` — the eight §11 compiler rules and the one remaining warning; **8/8 pass** |
| `tools/` | `mklevel.py` (level compiler), `mktables.py`, `mkassets.py`, `mkgolden.py` | their outputs are Make targets, so a stale generated source rebuilds rather than being compiled |
| `atari/` | **The STE target**: `main.c`, `render.S` + `cast.S` (the hot loops), `hud.c`, `os.S`, the `.PAK` binder, `tos.ld`/`mkprg.py`, `bench.py`, `verify.py` | `make` → `BLACKICE.PRG` + `BENCH.PRG` + `BLACKICE.PAK` + `floppy/`; `make bench`; `make verify` — the pixel, silhouette, teardown, machine-health, cast-self-check and ledger surfaces. **See `atari/README.md`** |

---

## Building and running

The Python everywhere in this project is the workspace conda env:

```sh
PYTHON=~/miniconda3/envs/atari_reverse/bin/python
```

**The engine core and its tests** (from this directory):

```sh
make                 # host binaries + libblackice.so + every levels/*.bil
make test            # builds, cross-compiles for m68k, runs the libgcc gate, then pytest test -q
make m68k            # the cross-compile gate on its own (with the libgcc arithmetic-helper check)
make frames          # render the golden walk to host/out/ as PNGs, for looking at
make goldens         # diff the rendered walk against test/golden/ — writes nothing
make bless           # accept that diff — only after LOOKING at the frames
```

`make m68k` exists because the host compiler will happily accept code the 68000 cannot afford. The
**libgcc gate** is the sharp end of it: an undefined reference to `__mulsi3` / `__divsi3` and friends
is a *build failure*, because a 32×32 multiply or any divide in a per-column loop is a subroutine
call costing tens of thousands of cycles a frame. It cost `atari/` 170 ms a frame once. Exemptions
are named in each Makefile with their reason (`hash.o`, `rng.o`, `tables.o` — cold, and the 32-bit
arithmetic *is* the algorithm).

**The STE target:**

```sh
cd atari && make            # disk/BLACKICE.PRG, disk/BENCH.PRG, disk/BLACKICE.PAK, floppy/ staged
cd atari && make bench      # BENCH.PRG headless in Hatari, prints the per-stage frame-time table
cd atari && make verify     # the target's rendered pixels against the portable C reference
```

`BENCH.PRG` is `BLACKICE.PRG` built with `-DBLACKICE_BENCH`: the joystick is replaced by a
compiled-in copy of the *same* script the host reference replays, so the thing measured is the thing
that ships. `atari/README.md` is that directory's full report — the measured table, the shading
decision, the memory ledger, the iron list, the surfaces and what is not verified.

**Playing a level on the host** (the eyes-on harness, as opposed to the blind replay):

```sh
build/blackice_play --level levels/level1.txt --frames 300 --out host/out --png 0,100,200
```

**The asset pipeline:**

```sh
cd pipeline && $PYTHON -m pytest tests/ -q          # 584 tests
cd pipeline && $PYTHON -m stepix.demo_assets out    # rebuild the demo blobs + PNG previews
```

**The art:**

```sh
cd art && make            # regenerate every PNG and run every gate (python build_art.py)
cd art && make check      # the individual gates: palette, textures, sprites, rimtest
cd art && make ledger     # the byte ledger, packed and unpacked
```

**The audio** (needs Hatari and `m68k-elf-gcc`):

```sh
cd audio && make                   # disk/AUDIOTEST.PRG and disk/BICETEST.PRG
cd audio && make verify            # the demo harness in Hatari: 19 checks
cd audio && make verify-blackice   # the game's own score and cues: 20 checks
```

**The spike and the levels:**

```sh
cd spike  && make && make bench && make verify
cd levels && $PYTHON validate_levels.py
```

---

## How this was built — the agent-wave workflow

Two chains, run per wave, per the workspace `CLAUDE.md` (the Fable 5 orchestrator scopes, reviews
and integrates; it never writes the code, and only it commits):

**Design waves — designer → critic → orchestrator decision.** A designer agent wrote three concepts
across the risk curve (`design/CONCEPTS.md`); an independent critic agent scored and re-derived
every number in them (`design/CRITIQUE.md`) and *disagreed with the designer's ranking*; the
orchestrator took the decision. The same shape ran again over the GDD: `design/DESIGN_REVIEW.md`
raised 8 BLOCKERs, 24 SHOULD-FIXes and 11 NITs, and every one is answered by name in `DESIGN.md`
§19. `art/ART_REVIEW.md` is the art-director pass that forced Revisions 2 and 3.

**Build waves — author → independent reviewer → fixer → commit.** No agent reviews its own work.
The reviewer re-derives numbers off the artefacts rather than trusting the report: the art review
re-rendered every texture through `shade_table` and counted pixel agreement; the code review found
four art gates that *could not fail by construction* and were reporting green over broken art; the
target's own mutation sweep found that the first attempt at it had measured a stale screenshot and
reported PASS on a deliberately broken build. Every deliverable ends in a short REPORT that states
what was measured **and what is unverified** — `pipeline/REPORT.md`, `audio/REPORT.md`,
`spike/REPORT.md`, `atari/README.md`, `art/ART_DIRECTION.md`'s revision logs. The pre-commit gates
are the workspace's: `my-code-review` at `high`, then the docs gate, then the orchestrator commits.

---

## The decisions that shaped everything, and why

- **BLACK ICE over MISERERE and HADAL.** The designer ranked on ceiling; the critic ranked on what
  kills projects and put BLACK ICE first (technical fit 9, art-by-scripts 9). Distinctiveness was
  the *only* axis it lost, and the only one fixable after the engine ships — you can re-theme art
  onto a working renderer, you cannot hire a pixel artist you never had. MISERERE bet the whole game
  on lit-vs-unlit chroma separation that measured as a Y collision. The de-generic-ing demanded at
  greenlight became HALCYON: the mainframe is *dying*, and corruption is geometry, not a filter.
- **A 160×80 logical window under a 320×40 HUD strip.** The HUD is a static planar panel on screen
  lines 160–199, **outside the c2p region and drawn 1:1**, which is what makes an 8×8 font legible;
  it is blitted once at level load and only changed fields are redrawn. That last rule is not
  cosmetic — redrawing every field every frame cost 58 ms, and the whole HUD stage now runs in
  0.1–1.4 ms. Shrinking the window is the cheapest remaining cycle win, because the c2p and the fill
  are exactly linear in view rows.
- **80 columns is the shipping default** (`DETAIL_DEFAULT = DETAIL_COLUMNS_80`). 80-column mode
  narrows the chunky buffer to 80 and lets the c2p expand 4× on the way out; the alternative —
  double-writing into a 160-wide buffer — gives the c2p saving straight back and is withdrawn.
- **`FOCAL_ROWS` = 115, not 64** (decision D1, and now what the engine compiles). 64 is a power of
  two but renders a 1×1 wall face 1.81× wider than tall — a doorway nearly twice as wide as it is
  tall, in a game about corridors. 115 makes it 1.004:1, square to within 0.5%, and the power-of-two
  argument was never load-bearing because the column height comes off the reciprocal LUT the raycast
  already carries.
- **The palette is `art/palette.py`'s, not the design document's** (decision D3). 16 registers, every
  channel a multiple of `0x11`, two reserved (12 white = rim-light/muzzle/HUD text, 13 orange =
  enemy core/trace danger) that no wall may use, and index 15 doubling as the sprite transparency
  key. `DESIGN.md` §3's table is a *generated mirror* pinned equal by a test, because it drifted
  once already and nothing caught it.
- **Shading is a per-pixel remap on target, not baked bands.** The arithmetic decided it: baking
  five depth bands into the resident wall set costs 269,312 bytes, the remap costs 81,920 — and the
  remap's second indexed read is what is left in the wall loop's 75.3 cyc/px.
- **The door axis is derived at load, never stored** (decision D4). §11 rule 3 guarantees exactly two
  opposite open neighbours, so the axis is a property of the map; a stored byte could disagree with
  the map it was compiled from, and §10.1's door plane is the one place the renderer and the
  collider must not disagree.
- **`RenderColumn` and `RenderSprite` are frozen contracts.** 12 bytes and 26 bytes on the 68000,
  every 16-bit field on an even offset, everything **pre-clipped** so the asm drawer has no clipping
  work and no divides. The chunky buffer is **column major** (`chunky[x * RENDER_H + y]`) because a
  raycaster emits vertical slices and column major makes a slice a contiguous `(a0)+` run. Both are
  asserted under the target compiler by `host/abi_m68k.c`, not extrapolated from host pointer sizes.
  Holding them frozen is what let `cast.S` be written against `src/raycast.c` and then checked
  against it byte for byte, every frame of every bench pass.

---

## Where the concept art lives

Everything under `art/out/`, regenerated by `cd art && make`:

- `art/out/mockup_the_ledger.png`, `art/out/mockup_the_kernel.png` — the two in-game mockups, at
  320×200 with the HUD strip. Verified honest: zero off-palette pixels, every 2×2 block in the
  render window uniform (so they really are 160×80 logical), floor and ceiling strictly index 0, no
  gradients or anti-aliasing anywhere. `mockup_the_kernel` draws the Shear — one corridor's north
  and south walls carrying the same rhythm a cell out of step.
- `art/out/title_screen.png` — the wordmark, at 288 px near edge-to-edge.
- `art/out/contact_sheet.png` — every texture and sprite on one sheet.
- `art/out/tex_*.png`, `art/out/spr_*.png`, `art/out/hud_strip.png` — the individual assets;
  `art/out/native/` holds them at native size for re-derivation.

## What it looks like

Two screenshots of the real thing sit beside the target:

- **`atari/game_hatari.png`** — `BLACKICE.PRG` playing under Hatari on a stock STE: level 1 INGRESS,
  the 40-line HUD strip live, 00:19 on the clock, 76 ms a frame, 3% trace, 100% integrity, 60
  cycles, the A/B/C key slots and the weapon icon.
- **`atari/bench_frame.png`** — the bench's captured frame, which is the image `verify.py` compares
  against the host reference.

Frames from the running game are also in `atari/out/` and `host/out/` — and they agree pixel for
pixel. `atari/near_wall_hatari.png` shows the real art at one cell (the sector-key panel, the nose-to-wall
worst case at 148 ms); `game_hatari.png` is a distant corridor, band-3 fogged. The HUD labels
are drawn (fixed 2026-08-28); the strip still covers the mockup's bevelled well borders.
