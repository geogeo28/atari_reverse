# `atari/` — the STE target

The platform seam: BLACK ICE's portable core (`../src/`) runs here on a stock Atari STE, with the
per-pixel work in hand-written 68000 and everything the machine owns — video, palette, the vertical
blank, the IKBD, GEMDOS — behind `os.S`.

Two programs come out of one source tree:

| | what it is |
|---|---|
| `disk/BLACKICE.PRG` | the game. Joystick and keyboard, the catch-up clock, the HUD, YM music. |
| `disk/BENCH.PRG` | the same code with `-DBLACKICE_BENCH`: a compiled-in input script, five fixture passes, a ledger and `BENCH.TXT`. |

They are built together and share every line except the input source and the pass driver, which is
the point: the thing measured is the thing that ships.

```sh
make            # both .PRG, BLACKICE.PAK, and floppy/ staged as the shipping disk
make bench      # headless Hatari -> the per-stage frame-time table below
make verify     # the rendered-pixels surface: target vs the portable C reference
```

---

## The frame

```
sim       game_step, once per two vertical blanks, catching up if the frame ran long (DESIGN 4.1)
cast      render_cast + sprite_build_list + the band          portable C, ../src/
columns   bi_draw_columns   -> the chunky pair-word buffer     render.S
sprites   bi_draw_sprites   -> the same buffer, over the walls render.S
fill      bi_fill           -> the void above and below the band, straight to the screen
c2p       bi_c2p_high/low   -> the band, chunky to planar, doubled both ways
hud       hud_draw          -> only the fields of the 40-line strip whose value changed
flip      the page swap, applied by the vertical blank
```

The band is `min(top)`..`max(top + rows)` over every column, widened to cover every projected
sprite. Outside it the view is `COLOUR_VOID` and is written by a ten-register `movem` at 2.7 cycles
a byte instead of the drawer's 70-plus a pixel and the c2p's 34; `../spike/REPORT.md` measured that
as a 40-42% saving on the whole frame, the largest single lever the feasibility spike found. It is
also why no drawer in `render.S` clips: every column's ceiling, wall and floor runs are
non-negative by construction and sum to exactly the band's height.

---

## Measured

Hatari 2.6.1, `--machine ste`, its own bundled EmuTOS, 1 MB, 100 frames a pass, timed on the MFP's
timer C (26.042 µs a unit) and cross-checked against the text the program itself writes through
GEMDOS. Microseconds per frame; the totals in 8 MHz cycles are what DESIGN 17.3's budget is stated
in.

```
pass       cols     sim     cast  columns  sprites    fill      c2p    hud       total    work   locked
--------------------------------------------------------------------------------------------------------
WCA160      160      31  39478.0 120510.0     92.0   109.0  53986.0 1339.0   215549   4.64     4.55
WCA80        80      30  20699.0  60390.0     91.0   112.0  34118.0  138.0   115582   8.65     8.33
WCS160      160      33  48606.0  75686.0  36491.0  1811.0  43664.0  133.0   206429   4.84     4.55
WALK80       80    4215  26584.0  43712.0    251.0  1487.0  28785.0  609.0   105650   9.46     8.33
WALK160     160    4208  50907.0  87265.0    391.0  1481.0  45677.0  755.0   190691   5.24     5.00
```

**Two frame rates, and the second is the one a player sees.** `work` is 1e6 / the mean frame; the
loop then waits for the vertical blank (DESIGN 17.3's flip lock), so the delivered rate is
`50 / ceil(frame_us / 20000)` and nothing between. WALK80 does 9.46 fps of work and delivers 8.33.
Quoting only the work rate overstates every pass, which the first version of this table did.

### Before and after the asm pass

Measured on the same fixtures, before `cast.S` existed and before the column runs were unrolled:

```
pass       cols        cast              columns             total          delivered fps
                    before   after      before   after     before   after     before  after
--------------------------------------------------------------------------------------------
WCA160      160     45289 -> 39478    142843 -> 120510    243701 -> 215549    4.55 -> 4.55
WCA80        80     23564 -> 20699     71191 ->  60390    129258 -> 115582    7.14 -> 8.33
WCS160      160     67204 -> 48606     85871 ->  75686    235481 -> 206429    4.17 -> 4.55
WALK80       80     33810 -> 26584     51948 ->  43712    120978 -> 105650    7.14 -> 8.33
WALK160     160     65436 -> 50907    103549 ->  87265    221657 -> 190691    4.55 -> 5.00
```

The cast is **22-28% cheaper** and the column drawer **13-18%**; the whole frame is **11-13%**
cheaper and two of the five passes gained a whole flip-lock step. The cast is 2,540 cycles a ray at
WALK160 against 3,270 before — short of `include/render.h`'s 730-1,150 model, and the remaining
cost is the per-ray setup and the emit, not the DDA: WCA160's one-step rays and WALK160's longer
ones differ by 572 cycles a ray, which is 7 more DDA steps at the 83 cycles the loop is counted at.

* **WCA** is DESIGN 17.3's **WC-A**, built from the map rather than from coordinates: the player is
  stood against the first wall face east of the start cell, facing it. Angle 0 is +x and the wall
  runs north-south, so the perpendicular distance is *constant across the field of view* — every
  one of the 160 columns is the full 80 rows and the window is completely full. 12,800 textured
  pixels, no sprites, the band is 0-80.
* **WCS** is the near-billboard fixture. It moves the level's OWN entities in front of the player
  rather than inventing any — a fabricated entity would measure a sprite the game cannot produce.
  It places three and draws **6,336 sprite pixels a frame**, against DESIGN 17.3's WC-C bound of
  14,560. The ledger reports what was actually drawn, so a fixture that found nothing to place says
  so rather than being taken on trust.
* **WALK** replays `../test/scripts/walk.txt`, the same 100 ticks the host reference runs. `sim` is
  non-zero only here, because the fixtures do not step the world.

**The DESIGN 17.3 gate: MISSED, at both column counts.** 160 columns is **4.1x** its 480,000-cycle
budget on WC-A and **3.7x** on the walk; 80 columns is **3.2x** its 320,000-cycle budget on WC-A and
**3.1x** on the walk. The gate says 80 columns becomes the shipping default if 160 misses — the
engine has since done that (`DETAIL_DEFAULT` is `DETAIL_COLUMNS_80`) — but 80 misses too, so the
next decision is a real one and these are the numbers it has to be made against.

**Where the frame goes, at 160 columns on the walk:** columns 46%, cast 27%, c2p 24%, sim 2%. The
levers left, in the order the measurement supports them:

1. **The wall loop is 75.3 measured cycles per pixel** (964,080 cycles for WC-A's 12,800 pixels),
   against 58 counted for the even column and 70 for the odd. The 1.17 ratio over the counted sum is
   bus and prefetch behaviour, a little worse than the 1.04-1.11 the spike's five loops averaged. It
   is still the largest stage, and what is left in it is the two indexed reads a shaded texel costs
   — which is the shading decision below, not a loop that can be tightened further.
2. **The cast's per-ray setup and emit, not its DDA.** 2,540 cycles a ray at WALK160. WCA160's rays
   take about one DDA step and WALK160's about eight, and the two passes differ by 572 cycles a ray
   — 7 steps at the 83 the loop is counted at, so the DDA is at its model and the other ~1,900 is
   the trig reads, the two `mulu` seeds, `project_slice` and `band_of`.
3. **The c2p is 5,398 cycles a view row** (431,878 for WC-A's 80), against the spike's 5,300 at the
   same column count — it is content-independent and already at its measured floor.
4. **The sprite stage is pixel-bound, not per-column-bound**, and the measurement says so: WCS160
   spends 36,491 us on 6,336 sprite pixels, which is 46 cycles a pixel against the 102 an opaque one
   is counted at — most of them are transparent or z-rejected. Replacing the per-column `muls` for
   the destination row with a table moved it 257 us. The per-column block is not where its time is.

### The stages that used to be the problem

The HUD stage measured **170,000 µs a frame** on the first working build — more than the raycast,
the wall drawer and the c2p together. Two faults, both in the C:

* the planar helpers recomputed `y * SCREEN_BYTES_PER_LINE` for every eight pixels (a `__mulsi3`
  call) and wrote `x / 16` on a signed int (two `__divsi3` calls). Hoisting the multiply to once a
  row and spelling the divisions as shifts: **170,000 -> 58,000 µs**.
* the strip redrew every field every frame. DESIGN 15.1's rule — only fields whose value changed —
  with one `shown` record per screen buffer, because the two buffers age independently:
  **58,000 -> 140-1,400 µs**, and the 1,400 is WC-A, whose frame-time readout changes every frame.

---

## The shading decision

**A per-pixel remap, not baked bands, and the arithmetic decided it.**

The engine shades through `g_shade_lut[band + side]`, six rows of sixteen entries. A pre-shaded,
pre-pair-scaled copy of one 64x64 texture is 8 KB per (level, parity), so all six levels of the ten
resident textures baked both ways would be **983,040 bytes on a 1 MB machine**. Baking only the two
or three nearest bands still costs 300-500 KB and buys nothing for the far columns, which in a
corridor are most of them.

So a texture is stored **once**, as 64x64 words holding `palette_index * 2`, and one 16-entry word
table per (shade level, parity) turns that into the pair-scaled chunky word:

```
tex[u][v]           = index * 2
shade[l][p][index]  = g_shade_lut[l][index] * (p ? PAIR_ODD_SCALE : PAIR_EVEN_SCALE)
```

The inner loop is one indexed read into the texture and one into a 32-byte table. Hand-counted that
is **70 cycles a pixel on the even column and 78 on the odd**, against the spike's pre-shaded
**56 and 64** — the remap costs **14 cycles a pixel** and saves **901,120 bytes**. Composing the
pair scaling into the same lookup is what makes it one extra read and not two: the parity the chunky
buffer needs and the shading the engine asks for arrive together.

The same table serves the sprite drawer, indexed by the band alone (`include/sprite.h`), so a sprite
pixel pays no more for its shading than a wall pixel does.

## The chunky buffer

One **word per pixel PAIR**, holding the c2p table's byte offset — lifted from `../spike/`, which
measured the alternatives. The even column of a pair writes the word and the odd column ORs into it,
so there is no clear pass and the c2p does one table lookup per two logical pixels. A byte-per-pixel
buffer costs the c2p four extra indexed longword reads per 16-pixel group (~156,000 cycles a frame
at 160 columns) to save 4 cycles on half the drawn pixels (~32,000); a 16-bit-index table is 512 KB
per plane pair.

**This is internal to the platform.** The engine's contract is the `RenderColumn` / `RenderSprite`
lists in and the planar picture out (`../include/render.h`), and its own column-major byte buffer
(`../src/draw.c`, `../src/sprite.c`) stays the host-side oracle `verify.py` compares against — which
is exactly why the two layouts may differ and the pixels may not.

A sprite pixel REPLACES a wall pixel rather than OR-ing into it, so its store is a read-modify-write
that keeps the other pen of the pair. That shape is identical for both parities, so unlike the wall
drawer the sprite loop exists once.

---

## Memory

Measured with `m68k-elf-size` and `m68k-elf-nm`, and against the running machine (EmuTOS 1 MB, TPA
`$15cf6`-`$f8000`, program text at `$15df6`, `.bss` ending near `$7337e`, stack at `$f7e7a`).

| | bytes |
|---|--:|
| `BLACKICE.PRG` on disk (text 40,112 + data 3 + the relocation table) | 41,002 |
| `BENCH.PRG` (the extra .bss is the cast self-check's shadow scratch) | 44,399 |
| `BLACKICE.PAK` | 13,394 |
| **resident `.bss`, game build** | **345,636** |
| — resource arena (105,728 in use: 10 textures at 8,192, 2 sprites at 8,320, HUD 6,400, font 768) | 196,608 |
| — two 320x200 screens, 256-aligned, plus a page of alignment slack | 64,256 |
| — `GameState` (the game layer's entity table, occupancy and nav field) | 16,786 |
| — the engine's two reciprocal tables (`g_slice_height`, `g_tex_step`) | 32,768 |
| — chunky pair-word buffer, 80 pairs x 80 rows | 12,800 |
| — c2p tables, 4 positions at 160 columns and 2 at 80 | 12,288 |
| — resident `Level` | 4,454 |
| — `RenderScratch` (the column list, the wall distances, the sprite list) | 3,074 |
| — PAK directory, `BiTables`, the pristine entity list, the cell-texture map | 1,792 |
| **program + `.bss`** | **385,751** |
| TOS/GEMDOS and its buffers, measured as the TPA's offset from 0 | ~89,000 |
| **total against 1,048,576** | **~473,000** |

Roughly **550 KB spare**, which is the honest consequence of one texture set resident (DESIGN 17.4's
rule) and of the shading remap: the ledger's 269,312-byte baked wall set is 81,920 bytes here.

**The arena is one block with two ends.** Resident assets grow up from the bottom; a member's packed
bytes and its expanded byte-per-texel image are temporaries taken from the top and released as soon
as it is converted, so the transient 60 KB never becomes 60 KB of permanent `.bss`.

**The ledger lives at `$c0000`,** a fixed absolute address so a Hatari debugger script can `savebin`
it without knowing where GEMDOS put us. `main.c` refuses to run if `.bss` has grown into it or if it
is inside the stack; both bounds are checked at boot rather than assumed.

---

## The iron list

BRIEF.md's hardware gotchas, each with the surface that now catches it or an honest "iron only":

* **TOS traps clobber d2/a2** — every wrapper in `os.S` saves the pair. *Iron only*: Hatari's TOS
  happens not to, so nothing here can go red on it.
* **Supervisor for `$ffff8xxx`** — the whole game loop runs inside one `Super(0)`. *Caught*: a
  privilege violation would be an exception in the machine-health scan.
* **IKBD `$12` and `$14` at boot** — sent, and `$1a`/`$08` on exit. *Iron only*, and worse than
  that: nothing headless presses a button, so the joystick path is installed and unexercised.
* **Joystick port 1 only.** Port 0 is the mouse port, and after `$14` the 6301 reports a mouse
  rolling on the desk as joystick 0 — an earlier version of `os.S` ORed that into the player's
  input word. *Iron only.*
* **The resolution is SET, not merely saved** — `Setscreen(..., REZ_ST_LOW)`, and the program
  refuses with a line of text on a monochrome monitor, which cannot show ST Low at all. *Caught*:
  the harness found the ordering bug this introduced (Setscreen clears the screen it is given, so
  the HUD backdrop has to be blitted after the mode switch, not before) as "the HUD's rules are not
  at lines 160 and 168".
* **The floppy is deselected after the load** — one read-modify-write of PSG port A under IPL 7,
  bits 1 and 2 set, active low (`projects/wonderboy/names.txt` is canonical for the bit map).
  *Iron only*: the load goes through GEMDOS, so nothing in Hatari depends on it.
* **The vertical blank has a fallback.** TOS's queue has `nvbls` slots and a machine with
  accessories can have none free; without a blank this program has no frame clock, no page flip and
  no music, which is a hang and not a degraded mode. The fallback chains the level-4 autovector,
  which is only safe because `set_video_base` writes `_v_bas_ad` too. *Iron only*: Hatari's EmuTOS
  always has slot 0 free, so the fallback path has never run.
* **`bi_fill` cannot run away.** It terminates on `bhi` rather than `bne`, so a byte count that is
  not a whole number of `FILL_CHUNK_BYTES` stops at the first chunk at or below the limit instead of
  writing backwards through the machine — and `main.c` pins the multiple and the alignment with
  `_Static_assert`s so the fail-safe is the second line of defence, not the argument.

## The surfaces

**rendered pixels** (`verify.py`) — the hand-written drawers, the c2p and the pixel doubling
disagreeing with the portable C reference.
**PASS: 0 of 51,200 pixels differ**, at BOTH column counts — WALK160 frame 99 through
`bi_c2p_high` and the 4-position table, and WALK80 frame 99 through `bi_c2p_low` and the
2-position one. `make verify` runs the bench first and then compares each in turn; comparing only
160 would have left the SHIPPING detail level (`DETAIL_DEFAULT` is 80 columns) untested.

**silhouette** (`verify.py`) — geometry alone, so a failure localises away from shading.
**PASS: 0 of 320 columns differ**, worst top and bottom delta 0.

**teardown** (`verify.py`) — a program that draws correctly and leaves the machine broken. The
video registers, `_v_bas_ad`, `nvbls` and the `_vblqueue` slots are compared before and after,
against a CONTROL boot with no program at all — without which the check measures the operating
system: EmuTOS itself moves palette pen 7 from `0555` to `0ddd` and installs its own routine in
`_vblqueue` slot 0 on the way to the desktop. **PASS.**

**machine health** (`verify.py`) — bus errors, address errors, illegal instructions, exit status.
**PASS**: EmuTOS's seven RAM-sizing probes at `PC=$e00d98` and nothing else.

**libgcc arithmetic helpers** (`make libgcc-gate`, part of `make all`) — a divide or a 32x32
multiply compiled into a subroutine call in a per-frame path, which is the fault class that cost
this directory 170 ms a frame once and then survived the fix to it. 24 objects, four exemptions
carrying the parent build's reasons. This gate is REPORTING A FAILURE as this is written, and the
failure is not the platform's: `src/sprite.c`'s `sprite_pixel_cost` calls `__mulsi3`, and the
parent's own `make m68k` fails on the same object for the same reason.

**ledger vs `BENCH.TXT`** (`bench.py`) — the timing table being read wrong out of RAM.
**PASS: five passes agree within 1.6 µs**, the program's own truncation.

**the cast self-check** (in the program, every frame of every pass) — `cast.S` disagreeing with
`src/raycast.c`. The bench runs BOTH, into two scratch buffers, and compares the RenderColumn list
and the wall distances byte for byte; the ledger publishes the count and `bench.py` refuses on a
non-zero one. This is stronger than the pixel comparison it sits behind: a wrong column can hide in
a band the drawer never reaches, and this cannot.
**PASS: 0 columns differ**, over 500 frames of five passes.

**timer-C probe** (in the program) — a TOS that programmed the 200 Hz timer differently, which
would make every microsecond in the ledger wrong by that ratio.
**PASS: the counter is never read above its 192 reload.**

**The pixel surface was mutation-tested, and so was the harness around it.** Shortening the wall
run by one row (`subq.w #1,%d4` -> `#2` in `render.S`'s DRAW_COLUMN) is caught: **564 of 51,200
pixels differ, 282 columns differ, worst bottom delta 2**, and `verify.py` exits non-zero. The first
attempt at this reported PASS on the mutated build, and the fault was in the sweep and not in the
gate: it left the previous run's `out/frame.png` in place while the engine tree happened to be
mid-edit, so `bench.py` never captured a new screenshot and the comparison ran against a stale one.
A mutation sweep has to delete the artefact and check that the rebuild and the capture both
succeeded, or it measures nothing and says PASS.

The pixel surface is the one that matters, and it is exact rather than tolerant: the target's
screenshot and the host's PNG are compared index for index over the whole 320x160 window. The bottom
40 lines are the platform's HUD, which the portable core never draws, and are excluded — said out
loud in the output rather than silently skipped.

**What makes that comparison honest** is that both sides draw the same art. `dumpassets.c` is a HOST
program that links the engine's own `g_wall_textures` / `g_entity_sprites` / `g_palette_rgb` and
writes them out; `mkpak.py` packs those dumps. The art could not drift between the two builds
without the archive changing.

---

## Faults found on the way

Nine. The first three were found by running the thing; the rest by the review gate reading it
against the engine it consumes.

1. **The palette landed one register high.** GCC 16 folds a copy between two addresses it knows at
   build time into `move.w (%a0)+,(d,%a0,%d0.l)`, and the 68000 post-increments `%a0` *before*
   computing the destination's effective address — so all sixteen colour words arrived at `$ffff8242`
   upward, pen 0 kept EmuTOS's white and every colour on screen was one pen out. This is the hazard
   `../spike/REPORT.md` measured on a ledger publish, met again on a different copy. `volatile` does
   not stop it; hiding the pointer behind an empty `asm` constraint does (`opaque_pointer`).
2. **An `AUTO` folder on Hatari's GEMDOS drive hijacks the boot.** EmuTOS runs it before `--auto` can
   run anything, so every `--auto C:\BENCH.PRG` silently ran the *game* — which never terminates —
   and the bench produced no ledger while looking, from outside, like a hang in the renderer. The
   floppy layout is staged in `floppy/` instead and the emulator's drive is kept free of `AUTO`.
3. **A fixture outlived its own pass.** The near-sprite fixture moves entities in the authored
   `Level`, because `entities_init` copies the runtime table from there — and the scripted walk that
   ran afterwards then collected different pickups from the host reference's. Every pixel of the
   comparison differed for a reason that had nothing to do with the drawers. The pristine entity list
   is now restored at the head of every pass.
4. **The page flip was asserted on one vertical blank in six to twelve.** TOS reloads the shifter
   from `_v_bas_ad` on *every* blank and then walks the queue this program flips from, so writing
   only the hardware registers meant TOS put the boot buffer back on every blank that did not carry
   a flip — at 4 to 8 fps, most of every frame showed the buffer being drawn into. `set_video_base`
   now writes `_v_bas_ad` as well. Nothing in the harness could see this: `hold_capture` redraws
   until both buffers are identical before the screenshot.
5. **The per-frame HUD path called libgcc.** `__udivsi3`, `__umodsi3` and `__divsi3`, verified in
   the objects — the same fault class as the 170 ms above, in the same file, surviving the fix to
   it. The parent build has gated `src/` on this since it was written; `atari/` was not gated, and
   now is (`make libgcc-gate`, 24 objects, four documented exemptions matching the parent's).
6. **The target and the host oracle seeded different generators.** `host/main_host.c` defaults to
   the level's own `rng_seed`; this build passed `RNG_DEFAULT_SEED` under a comment asserting they
   matched. They happen to render the same frame today, so the surface was green — and would have
   gone red, everywhere at once, the first time the sim drew a random number.
7. **A corrupt archive could write over the stack.** `read_member` bounded the member's RAW length
   against the destination and then copied its PACKED length; `load_palette`'s destination is a
   32-byte automatic array. Both lengths are checked now, and the two header maps that were read
   before anything bounded them are bounded.
8. **The integrity bar was 80 pixels wide in a 72-pixel field** and painted its last two segments
   into the cycles well, where they stayed until the cycle count next changed. The fields are
   rebalanced and `draw_bar` now derives its segment count from the width it was given, so the
   overflow is unrepresentable rather than merely absent.
9. **`make verify` did not run the bench**, so it compared whatever screenshot `out/` happened to
   hold. That is how the first mutation sweep of this gate came back green on a deliberately broken
   drawer. `verify` depends on `bench` now.

---

## What is NOT verified

* **Real hardware.** Every number here is Hatari's 68000 model. The bus and prefetch behaviour that
  puts the loops 17% over their instruction-table sums is Hatari's, and the ST's video DMA contention
  in particular is a model rather than a measurement.
* **The sprite drawer is only thinly covered by the pixel surface, and here is the number.** Every
  one of the golden walk's 100 frames was rendered on the host and its palette indices counted: the
  ONLY frame containing a single sprite pixel is frame 99, the one compared, and it contains **56
  screen pixels — 14 chunky pixels** of one distant pickup. So the comparison does exercise the
  texel fetch, the transparency key, the per-column depth test, the span lookup and both parities of
  the read-modify-write store, and it exercises them fourteen times. The wall drawer, by contrast,
  is compared over the other 51,144. The fixture that *does* load the sprite drawer properly
  (WCS160, 6,336 sprite pixels a frame) is measured but not compared, because it places the player
  from the map and `host/main_host.c` has no way to be told where to stand. Closing this needs
  either an input script that walks the player up to a pickup — the golden walk does not — or a host
  flag that accepts a placement; the first is the cheaper one and belongs with the next change to
  the sprite path.
* **The frame-shape counters are new and nothing has used them yet.** The ledger now carries
  `wall_rows_sum` and `clipped_columns_sum` per pass — WCA160 draws 12,800 wall rows with all 160
  columns clipped to the window, WALK160 draws 8,068 with 55 clipped — which is the data DESIGN
  17.1's "FOCAL_ROWS is the single knob" decision needs. Nobody has made that decision from them.
* **The joystick has not been exercised.** `bi_joy_entry` is installed on `KBDVECS.joyvec` and the
  IKBD is put in `$12`/`$14` at boot exactly as `BRIEF.md` requires, but the bench runs from a
  compiled-in script and nothing headless presses a fire button. The keyboard path *is* exercised
  only in the sense that it compiles.
* **Held keys are joystick-only.** `Bconin` delivers makes and repeats, never a release, so an arrow
  or Z/X held on the keyboard moves at the repeat rate. The joystick is the movement device, which
  is what DESIGN 6 claims ("completable with joystick plus Alt"), and Alt/Shift comes from `Kbshift`.
  A custom IKBD packet parser on `KBDVECS.ikbdsys` would fix it and would also take TOS's keyboard
  away from the clean exit; that trade has not been made.
* **`joyvec` restoration is by construction, not measured.** `main.c` saves and puts it back, but a
  debugger script cannot call `Kbdvbase` to find the slot, so `verify.py` checks the palette and the
  `_vblqueue` and says so about this one.
* **Three audio cues are silent.** `audio/blackice_sfx_ids.h` carries ten of DESIGN 16's thirteen;
  gate-close, the door refusal and the throttle change have no YM macro, so the event ring maps them
  to `SFX_SILENT` rather than borrowing a cue that means something else. DESIGN 16 makes the first
  playable YM-only, so the DMA sample path is not linked at all. The tempo escalation IS wired —
  `GameState.trace_band` drives `ym_music_set_speed(BLACKICE_BAND_SPEED[band])`, which is DESIGN
  16's "the tempo IS the trace meter" — but nothing here has listened to it.
* **The HUD's field rectangles cover the art's panel wells.** `art/hud.py`'s panels start at x = 2,
  130, 204, 258 and 286, none of them on an 8-pixel boundary, and every field here is drawn without a
  shift. Snapping out leaves slivers of the backdrop's *demo values* showing (a stray "T", a stray
  "KAB"); covering them loses the recessed borders in those rows. Covering won. Restoring the wells
  needs the art redrawn on 8-pixel boundaries or a shifting blitter.
* **WC-B and WC-C are not measured as DESIGN 17.3 states them.** `level1`'s geometry gives the sprite
  fixture one free cell of the three it asks for.
* **The weapon icon and the token pips are drawn but not driven.** DESIGN 18 defers the Spike, so
  there is one weapon; the pips read `GameState.tokens`, which is real.

---

## Files

```
plat.h          every constant the C and the asm share: hardware addresses, the chunky layout,
                the c2p table shape, and the RenderColumn / RenderSprite field offsets, each
                pinned to include/'s own value by a _Static_assert in main.c
os.S            _start, the TOS trap wrappers (they save d2/a2 around every trap), the two vertical
                blank entries and the joystick one, the floppy deselect, the 200 Hz clock,
                memcpy and memset
cast.S          src/raycast.c's render_cast, per ray, in 68000: the DDA, the projection and the
                depth band, byte-identical to the C and checked against it on every frame
render.S        the five hot loops: bi_draw_columns, bi_draw_sprites, bi_c2p_high/low, bi_fill
main.c          boot, the resource load, the frame, the catch-up clock, the input, the bench
assets.c/.h     the resource arena, the BiTables the asm indexes, and the BLACKICE.PAK loader
hud.c/.h        the live fields of the 320x40 strip, drawn straight into planar memory
tos.h           the TOS traps and the asm routines, declared once
dumpassets.c    HOST: dumps the engine's own asset arrays, so the PAK cannot drift from them
mkpak.py        HOST: packs those dumps plus the HUD, the font and the compiled levels
mkscript.py     HOST: compiles ../test/scripts/walk.txt into the bench's input array
bench.py        two headless Hatari runs -> the screenshot, the ledger, the table above
verify.py       the rendered-pixels surface, the silhouette, teardown and machine health
test_plat_pins.py  a pytest that parses plat.h and asserts every constant bench.py and verify.py
                re-typed still equals the C's — it caught the ledger header changing under them
tos.ld          copied from ../spike/, itself from projects/wonderboy/recreate/atari/
mkprg.py        copied unchanged from the same place
out/frame.png           the captured frame, with Hatari's borders
out/frame_screen.png    the same frame cropped to the 320x200 screen
out/diff.png            written by verify.py when the pixels disagree
disk/                   the Hatari GEMDOS drive: both .PRG and the .PAK, and no AUTO folder
floppy/                 the shipping layout: AUTO/BLACKICE.PRG and BLACKICE.PAK
```
