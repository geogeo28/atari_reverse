# BLACK ICE — STATUS

**As of 2026-08-28**, at `ad0cf83` (*"the STE target — BLACKICE.PRG boots and plays, pixel-exact vs
the host, cast in asm"*). Every number below comes from a committed REPORT or was re-derived from
the tree on that date. Anything that could not be confirmed from the files is marked
**unconfirmed**.

**The first playable exists and runs.** `atari/disk/BLACKICE.PRG` boots on a stock STE under Hatari,
plays levels 1 and 2 with all three enemies, the Buster, doors and tokens, pickups, the trace meter
and the death / sector-clear paths, and renders pixels identical to the portable C reference. The
one thing standing between it and "done" is the frame rate, and the one thing standing between it
and a verdict is real hardware.

## Subsystems

| Subsystem | State | Verified numbers |
|---|---|---|
| `design/` — brief, GDD v2.1, decision trail | **DONE** | 8 BLOCKER / 24 SHOULD-FIX / 11 NIT answered by name; 4 v2.1 decisions: D1 `FOCAL_ROWS` 115, D2 `COLOUR_FAR_FILL` 5, D3 palette regenerated from `art/palette.py`, D4 door axis derived at load |
| `pipeline/` — `stepix` + `depack.c` | **DONE** | **584 pytest**; demo `.PAK` 70,516 → 11,910 B (0.169); pack→depack identity on 8 synthetic + 8 fuzzed corpora + the real blobs; 12/12 mutation sweep, no survivors; byte-identical rebuild |
| `art/` — palette, textures, sprites, HUD, key art | **DONE** (Revision 3) | 13 gates green: 4-bit gamut 16/16; cyan-vs-magenta all 5 bands (worst dY 16.0 / dChroma 41.5); every wall-legal pair (worst dY 8.6 / dC 44.9); seam 10/10; band agreement 45/45; unrimmed halo px 0/8; painted key px 0/13; weapon footprints 4/4; HUD overflow none; rim harness COVERAGE 0/400, MARGIN 0/400, LOAD 321/400. Ledger **87,296 B** (**47,232** packed) |
| `audio/` — YM2149 music + STE DMA SFX | **DONE** | Tick **2,962 cyc/frame** (demo tune) and **2,922** with the game's score at its fastest band, against a 3,000 budget = 1.9% of a 160,000-cycle frame. `AUDIOTEST.PRG` 19/19 checks PASS; `BICETEST.PRG` 20/20 PASS. Score 5 songs, 3,978 B of 8,192; bank 10 cues, 4.80 s, 60,176 B of 102,400. Tempo bands 4/4 read back off the recorded audio; pitch 18/18 within 0.68%; samples 10/10 cross-correlated |
| `spike/` — Milestone 0 feasibility | **DONE** (superseded by the target's own numbers) | Unit rates that seeded the whole budget: c2p 33.1 / 41.6 cyc per logical px, wall texel 66.6, planar fill 2.71 cyc/B, cast 2,530 cyc/ray; band fill = 40–42% of the frame |
| `levels/` — the eight maps | **DONE** | `validate_levels.py`: **8 checked, 8 passed, 0 failed**. Warning 9 withdrawn by D3; the compiler carries eight rules and one warning |
| `include/` + `src/` + `test/` — portable core and gameplay layer | **DONE** for the first-playable scope | **442 pytest**. `FOCAL_ROWS` = 115, `DETAIL_DEFAULT` = `DETAIL_COLUMNS_80`. libgcc arithmetic-helper gate **clean over 19 objects** here and **25** in the target build (`hash`/`rng`/`tables` exempt with reasons, plus `bench_main` there). §18 items implemented: Watchdog / Sentry / Tracer on one BFS distance field, the Buster, door variants 16–19 with the token latch, the trace meter and its four bands, pickups, death and retry, sector clear. BFS rebuild **230,000 cycles** on level 2 every 8 sim ticks = **≈28,800 cycles/frame** amortised |
| `atari/` — the STE target | **DONE** | `BLACKICE.PRG` 41,002 B on disk, `BENCH.PRG` 44,399 B, `BLACKICE.PAK` 13,394 B, `floppy/` staged as the shipping 720 KB disk. Resident `.bss` 345,636 B; program + `.bss` 385,751; **~473,000 of 1,048,576 with TOS, ~550 KB spare**. Surfaces: rendered pixels **PASS, 0 of 51,200 differ at BOTH detail levels**; silhouette **PASS, 0 of 320 columns**; teardown **PASS** (against a control boot, so it measures us and not EmuTOS); machine health **PASS**; cast self-check **PASS, 0 columns differ over 500 frames**; ledger vs `BENCH.TXT` agree within 1.6 µs; timer-C probe PASS. Pixel surface mutation-tested: a one-row-short wall run is caught (564 px, 282 columns) |
| **Frame-rate gate** | **MISSED** | Delivered (flip-locked) **8.33 fps at 80 columns** on the golden walk — 105,650 µs, 9.46 fps of work — and **5.00 at 160**. Against the BRIEF's ≥ 14 fps at 160 / ≥ 20 at 80: **3.1–3.2× over** the 320,000-cycle budget at 80 columns and **3.7–4.1×** over 480,000 at 160. Frame split at 160 on the walk: columns 46%, cast 27%, c2p 24%, sim 2% |
| **Real hardware** | **NOT STARTED** | Nothing in this project has ever run on an STE. `atari/floppy/` is staged and ready |
| QA play-test | **PLAYED headless** (`atari/QA.md`, `atari/play_headless.py` presses keys into a live Hatari over `--cmd-fifo`, screenshots, reads `GameState` from RAM) | Boot, movement (no tearing), token refusal + gate, Esc exit PASS on the first pass; death/retry, sector clear → level 2, palette bands, fire/damage flash, title screen, kills (4 of 6 shots) FAIL then **FIXED and re-proven on build C** (QA.md's re-test table). Joystick still BLOCKED by Hatari's dummy-video keyboard emulation, not the game |

## The perf decision, and the levers measured for it

The gate is missed at both column counts, so the next change is a real decision rather than a
tuning pass. In the order the measurement supports them, from the ledger's frame-shape counters
(`wall_rows_sum`, `clipped_columns_sum` — new, and this is their first use):

1. **A 40-row detail level — ≈33% of the frame.** The c2p and the fill are exactly linear in view
   rows and the drawer is linear in band rows; at 80 columns those three stages are 70% of the
   frame, so halving the rows is the largest lever left. It is also a visible change to the game's
   look, which is why it is a decision and not a fix.
2. **`FOCAL_ROWS` = 96 — ≈9%.** Fewer wall rows at a given distance, and fewer columns clipped to
   the window (WCA160 clips all 160 today; WALK160 clips 55 of 160). It costs the 1.004:1 square
   cell face that decision D1 bought, so it trades a measured look against a measured 9%.
3. **The sprite budget.** `SPR_PX_BUDGET` = 6,000 was set before any rate existed. The target now
   measures the sprite stage at **46 cycles a pixel** (WCS160: 36,491 µs for 6,336 sprite px), not
   the 102 an opaque pixel is counted at — most pixels are transparent or z-rejected — so the budget
   can finally be set from a measurement instead of being carried as provisional.

*The two percentages above are the orchestrator's reading of the frame-shape counters; they are not
yet pinned in a committed REPORT.* Beyond them, `DESIGN.md` §17.3's ladder still holds per-group
bands as unattempted, and the wall loop's remaining cost is the second indexed read a remapped texel
pays — which is the shading decision, not a loop that can be tightened.

## Open items and known gaps

**Real hardware is the big one.** Every measurement in this project is Hatari 2.6.1's 68000 model.
The bus and prefetch behaviour that puts the loops 17% over their instruction-table sums is
Hatari's, and the ST's video DMA contention in particular is a model rather than a measurement.
`atari/README.md`'s iron list names, one by one, the BRIEF gotchas that are handled but that
**nothing headless can go red on**: the d2/a2 trap clobber, the IKBD `$12`/`$14` boot sequence, the
joystick-port-1-only rule, the post-load floppy deselect, and the vertical-blank fallback for a
machine with no free `_vblqueue` slot.

- **IKBD and PSG teardown are not traced.** `joyvec` restoration is by construction rather than
  measured — a Hatari debugger script cannot call `Kbdvbase` to find the slot, so `verify.py` checks
  the palette, the video registers and `_vblqueue` and says so about this one. The PSG port-A floppy
  deselect is likewise unobserved, because the load goes through GEMDOS and nothing in Hatari
  depends on it. Both want a register trace or an iron run.
- **HUD panel labels — FIXED.** `hud.c`'s field redraw painted over the art's label row; each field now draws label / value / bar in three rows, pinned by 11 `_Static_assert`s (the strip is outside the pixel surface). `atari/game_hatari.png` and `atari/near_wall_hatari.png` show TRACE / INTEGRITY / CYC / KEY / CLK. Remaining gap vs the mockup: the bevelled well borders are covered, TRACE is single-height, KEY shows `ABC` glyphs.
- **Near-wall evidence — DONE:** `atari/near_wall_hatari.png` (the sector-key panel at one cell, 148 ms = the nose-to-wall worst case). **The game now ships the REAL art**: `tools/mkassets.py --art` converts `art/out/native/*.png` through stepix into `src/assets_data.c` (10 textures, 9 sprites, 78,976 B; PAK 17,130 B), pinned by `test/test_art_assets.py` (60 cases). **Wall handedness fixed**: every face rendered mirrored (invisible with the symmetric placeholders); the rule was inverted in `src/raycast.c`, `atari/cast.S` and `test/test_raycast.py` together, checked from all four facings, goldens re-blessed (state hash unchanged).
- **The joystick path is installed and unexercised.** Nothing headless presses a fire button; the
  bench runs from a compiled-in script. The keyboard path is exercised only in the sense that it
  compiles, and held keys are joystick-only (`Bconin` delivers makes and repeats, never a release).
- **The sprite drawer is thinly covered by the pixel surface**, and the number is known: of the
  golden walk's 100 frames only frame 99 contains any sprite pixel at all, and it contains 14 chunky
  pixels of one distant pickup. The fixture that loads the drawer properly (WCS160, 6,336 sprite px)
  is measured but not compared, because `host/main_host.c` has no way to be told where to stand.
  Closing it needs an input script that walks the player up to a pickup.
- **WC-B and WC-C are not measured as `DESIGN.md` §17.3 states them** — `level1`'s geometry gives the
  sprite fixture one free cell of the three it asks for.
- **Three audio cues are silent.** Ten of §16's thirteen have YM macros; gate-close, door refusal and
  throttle change map to `SFX_SILENT` rather than borrowing a cue that means something else. The
  tempo escalation *is* wired (`GameState.trace_band` → `ym_music_set_speed`), but nothing has
  listened to it.
- **Nobody has listened to any of the audio.** `out/audio.wav` and `out/audio-blackice.wav` exist;
  every claim about them is a measurement, not a hearing.
- **60 Hz.** The driver is vblank-rate agnostic but the *tempo* assumes 50 Hz — on a 60 Hz machine
  the score plays 20% fast, which makes band 0 sound like band 2. Fixing it needs a rate divisor in
  `BAND_SPEEDS`; that decision has not been taken.
- **The HUD's field rectangles cover the art's panel wells.** `art/hud.py`'s panels start on x
  positions that are not 8-pixel boundaries and the fields are drawn unshifted; covering the wells
  beat leaving slivers of the backdrop's demo values showing. Restoring them needs the art redrawn
  on 8-pixel boundaries or a shifting blitter.
- **The recorded-WAV sample path is unexercised** (`--wav-dir` has only ever run against files this
  repo does not have), the **`.PI1` palette convention has never been opened in a real ST paint
  tool**, and the **GCC 16 `move.l` post-increment hazard was never cross-checked against the
  Musashi oracle** — the fix removes the aliasing entirely and is emulator-independent, but which of
  GCC and Hatari is right about the semantics is unsettled.
- Still open in the art after Revision 3: the weapon overlay carries no rim and sits outside the rim
  harness; pickups hover over a void floor; one view and one pose per enemy; `circuit_lattice` /
  `corrupted_sector` sits 0.3 points inside the band-agreement gate; Sentry and Black ICE are both a
  blob at 16 rows; `hex_mesh` reads as braced mesh rather than hex at close range.
- `atari/README.md`'s surfaces section says the libgcc gate "is REPORTING A FAILURE as this is
  written" over `src/sprite.c`'s `sprite_pixel_cost`. **That has since been fixed** — the gate is
  clean over 19 and 25 objects as of 2026-08-28 — so that paragraph is stale and is the one known
  inaccuracy in an otherwise current report.

## Deferred by the scope ladder — not gaps

`DESIGN.md` §18 defers these deliberately, and they are not defects: the **Spike** weapon,
**OVERCLOCK** (the throttle ships as a two-state UNDERCLOCK ↔ NOMINAL toggle), **160-column mode as
a supported mode** rather than an options-screen setting, the **DMA sample path** (the first playable
is YM-only), **levels 3–8 in the build**, the **Hunter** and the 100% exfil, **THE KERNEL and the
Black ICE anchor boss**, the **results screen and grades**, and the **door slide offset** — with
which variant 22's see-through slit arrives. The weapon icon and token pips are drawn but only the
pips are driven, because there is one weapon.

## Review findings deliberately left unfixed

- **The `.PAK` carries no checksum.** Content hashing would cost the 68000 time for nothing. The
  depacker still refuses a truncated stream and a match reaching before `dst`, and clamps an
  overshoot, so a malformed stream can produce wrong pixels but never a write outside the buffer.
- **`render_text` is uppercase only** — fine for the HUD vocabulary.
- **A stolen SFX channel does not restore a held note**; the music resumes at the next row carrying
  one. Classic behaviour, deliberate.
- **`blackice_title`, `blackice_death` and `blackice_clear` carry no SFX macro table**, so every cue
  is silently refused while one of them is bound. Intended — but a cue added to any of them needs
  the macros added too.
- **The reference C column drawer keeps the shade LUT inside the loop.** It must stay the
  byte-for-byte oracle for both the shaded and the remapped variants.
- **Levels 3 and 6 carry six one-cell pockets each**, signed off in their `note` lines: dead spurs,
  sealed voids behind jammed doors, drifted junctions, one empty stamp alcove. §2's corruption
  devices ask for exactly these.
- **Every cycle count in `include/render.h`'s cost model is read off the 68000 timing tables**, not
  measured; the header says so itself, and `atari/README.md` now carries the measured replacements.

## Next session, in priority order

1. **Run it on the user's STE.** `atari/floppy/` is staged as the shipping 720 KB disk. Every
   unverified item above except the design ones collapses into that one session, and this workspace
   has been bitten repeatedly by exactly the class of bug an emulator cannot see (TOS traps
   clobbering d2/a2, hardware reads the oracle returns 0 for, the IKBD routing fire into the mouse
   packet). Take a photo of the frame rate and the HUD; try the joystick, which nothing has pressed.
2. **Take the row-halving decision** — a 40-row detail level is ≈33% of the frame and the only lever
   that can move the delivered rate a whole flip-lock step or two. It changes how the game looks, so
   it wants eyes on `make frames` output before and after, not just a number.
3. **Decide `FOCAL_ROWS` 96 vs 115** from the frame-shape counters, and record it as a design
   decision either way — it trades D1's square cell face for ≈9%.
4. **Set `SPR_PX_BUDGET` from the measured 46 cyc/px** and retire the provisional 6,000.
5. **HUD polish** — restore the bevelled well borders under the fields (8-px alignment trade), the 2x TRACE readout and key pips as in `art/out/mockup_the_ledger.png`; pack the art title screen into the PAK (the title is font-drawn today).
6. **Fix `atari/README.md`'s stale libgcc-gate paragraph** and note the fix to `sprite_pixel_cost`.
7. **Close the sprite pixel surface** with an input script that walks the player onto a pickup, so
   the drawer is compared over more than 14 chunky pixels.
8. **Trace the IKBD and PSG teardown**, or accept them as iron-only and say so in one place.
9. **Take the 60 Hz decision** (a rate divisor in `BAND_SPEEDS`, or ship the score 20% fast off PAL).
10. **Run a QA play-test wave** with `build/blackice_play` and write `atari/QA.md` — a scenario table
   and ranked defects. Nothing has yet checked that the *game* is any good, only that it is correct.
11. **Then the scope ladder**: 160-column mode, OVERCLOCK, the Spike, DMA samples, levels 3–8.
