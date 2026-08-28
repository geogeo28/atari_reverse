# Milestone 0 — raycast feasibility spike on a stock Atari STE

**What was built.** `SPIKE.PRG` (18,688 bytes text, 172,564 bytes BSS): a standalone GEMDOS program
that renders a Wolfenstein-style textured raycast frame **to the visible screen** and times its four
stages with the MFP's own clock. Eight passes — {160, 80 columns} x {fixed, rotating 2.11 deg/frame}
x {ceiling/floor as a planar band fill, ceiling/floor drawn into the chunky buffer} — 32 frames each.
`bench.py` runs it headless in Hatari 2.6.1 (`--machine ste`, Hatari's bundled EmuTOS 1.0.6, 1 MB),
captures a screenshot and the ledger out of RAM, and prints the table below. `verify.py` proves the
picture.

Everything below is **measured on the run**, from the ledger at `$80000`, cross-checked against
`RESULT.TXT` that the program itself wrote through GEMDOS (largest disagreement 24.7 us, the
program's own integer rounding). Clock: MFP timer C, `_hz_200` for the coarse part and the timer's
down-counter for the fine part, 26.042 us (208 CPU cycles) per unit. The program's own probe read
the counter to a maximum of 192, confirming the 192 reload the arithmetic assumes.

---

## Results

Microseconds per frame, and the implied frame rate:

```
 cols      view  ceil/floor    raycast   columns      fill       c2p     total     fps       band
-------------------------------------------------------------------------------------------------
  160     fixed   band fill    55958.6   35116.8    7827.2   18589.1  117491.7   8.51      36-64
  160  rotating   band fill    50569.5   37306.0    7822.4   18572.8  114270.7   8.75      36-64
  160     fixed   in chunky    53760.5   79582.7     141.6   66039.3  199524.0   5.01      0-100
  160  rotating   in chunky    48344.5   81650.6     155.4   66107.6  196258.2   5.10      0-100
   80     fixed   band fill    28135.9   17609.3    7859.0   11714.0   65318.2  15.31      36-64
   80  rotating   band fill    25509.8   18714.4    7818.3   11717.3   63759.8  15.68      36-64
   80     fixed   in chunky    27036.5   39841.0     146.5   41530.5  108554.4   9.21      0-100
   80  rotating   in chunky    24354.2   40929.1     140.8   41515.8  106939.8   9.35      0-100
```

The same frames in 8 MHz CPU cycles (**the 50 Hz frame budget is 160,000**):

```
 cols      view  ceil/floor    raycast   columns      fill       c2p     total
------------------------------------------------------------------------------
  160     fixed   band fill     447668    280935     62618    148713    939934
  160  rotating   band fill     404556    298448     62579    148583    914165
  160     fixed   in chunky     430084    636662      1133    528314   1596192
  160  rotating   in chunky     386756    653205      1244    528861   1570066
   80     fixed   band fill     225088    140874     62872     93712    522546
   80  rotating   band fill     204078    149715     62546     93738    510078
   80     fixed   in chunky     216292    318728      1172    332244    868436
   80  rotating   in chunky     194833    327433      1126    332127    855519
```

The fixed viewpoint looks straight down a line of aligned doorways, so its rays travel further and
its raycast stage is the more expensive of the two — that is the map, not the renderer.

### Unit rates, derived from the two band sizes in the table

| loop | measured | hand-counted from the 68000 timing tables | ratio |
|---|---|---|---|
| c2p, 160 columns | **33.1 cycles / logical pixel** (5,300 cycles per view row) | 30.75 | 1.08 |
| c2p, 80 columns | **41.6 cycles / logical pixel** (3,330 per row) | 37.5 | 1.11 |
| column loop, wall pixels | **66.6 cycles / pixel** | 64.3 (60 in the loop + 4.3 per-column setup) | 1.04 |
| column loop, ceiling/floor pixels | **30.8 cycles / pixel** | 28 | 1.10 |
| planar solid fill | **2.71 cycles / byte** | 2.6 | 1.04 |
| raycast (C, per ray) | **2,530 cycles** rotating, **2,800** down the long corridor | — | — |

The 4-11% the loops run over their instruction-table sums is prefetch and bus behaviour that a naive
cycle sum does not model; it is consistent across five independent loops, which is the useful part.
c2p and the fill are exactly linear in view rows (5,289 vs 5,307 cycles/row at 100 and 28 rows).

---

## Verification of the picture

`out/frame.png` — the screenshot, taken by a Hatari debugger script at the instant the program
publishes its ledger magic. `out/frame_screen.png` is the same frame cropped to the 320x200 screen.

`verify.py` splits the check in two so a failure is locatable:

```
GEOMETRY (target rays vs float reference): 160 columns, worst top delta 6, worst bottom delta 7,
                                           3 outside +/-1
    column 18: expected (45, 54), got (39, 61)
    column 19: expected (45, 54), got (39, 61)
    column 49: expected (47, 52), got (46, 54)
  PASS
DRAWING  (rendered frame vs target rays): 160 columns, worst top delta 0, worst bottom delta 0,
                                          0 outside +/-0
  PASS
```

* **Geometry** — the target publishes its whole `SpikeRay` array beside the ledger; that is compared
  against a textbook Lodev DDA in Python floats over the same map, viewpoint and field of view.
  157 of 160 columns land within one row (the target truncates its distance to 8.8 and its wall
  height to an integer). Three columns differ by 6-7 rows: all three are rays grazing a wall corner,
  where the last bit of a fixed-point comparison decides which cell is entered. **This is a real
  divergence, not rounding** — see "What is not verified".
* **Drawing** — the wall silhouette read back out of the rendered PNG against those same published
  rays: **exact, all 160 columns, both edges**. The asm column drawer, the c2p, the pixel doubling
  and the palette draw precisely the rows the raycast asked for.

---

## The design that was picked, and why

### Chunky buffer: one **word per pixel PAIR**, holding the c2p table's byte offset

Not a byte per pixel. Two logical pixels are packed into one word as
`even * 128 + odd * 8 == (even * 16 + odd) * 8`, which **is** the byte offset of that pair's entry in
the c2p table. Three things follow:

* the c2p does **one** table lookup per **two** logical pixels instead of one per pixel — the single
  biggest lever on it, since an indexed longword read costs 18-20 cycles and there are eight of them
  per 16-pixel group as it stands;
* the drawer never shifts or packs, because the textures are stored **twice**, pre-scaled by 128 and
  by 8 (128 KB of RAM for four 64x64 materials in two shades — generated at boot, not shipped);
* no clear pass is needed: the even column of a pair `move.w`s the word and the odd column `or.w`s
  into it, and the two runs together cover every row of the band.

The cost is the odd column's read-modify-write: `or.w` is 12 cycles against `move.w`'s 8, so the odd
column's wall pixel costs 64 cycles and the even one 56. That +4 on half the pixels (about 32,000
cycles a frame at 160 columns) buys the c2p's other four lookups per group, which would have cost
about 156,000.

Byte-per-pixel chunky was rejected on that arithmetic. A 16-bit-index table (four logical pixels per
lookup) was rejected on memory: the entries needed are 8 bytes wide, so it is 512 KB per plane pair.

### c2p: four pre-shifted tables, two accumulators, four stores

A 16-screen-pixel group is four interleaved plane words == **two longwords**, so the loop builds
`(plane0 << 16) | plane1` and `(plane2 << 16) | plane3` and stores each with one `move.l`. Each pair
position has **its own table**, entries already in their final bit positions, so the loop never
shifts:

```
    move.w  (%a0)+,%d0  x4                          |  32   the four pair indices
    move.l  (%a1,%d0.w),%d4  /  4(%a1,%d0.w),%d5    |  36   position 0, both longwords
    or.l    (%a4,%d1.w),%d4  /  ... a5, a6          | 120   positions 1..3
    move.l  %d4,(%a2)+ / %d5,(%a2)+                 |  24   the line
    move.l  %d4,(%a3)+ / %d5,(%a3)+                 |  24   ...and the line below it
    dbra                                            |  10
                                                      246 cycles / 8 logical pixels
```

Four table bases live in `%a1/%a4/%a5/%a6` and the two longwords of an entry are `+0` and `+4` of the
same indexed EA, which is why four positions need four registers rather than eight. Tables total
8 KB (high detail) + 4 KB (low), built at boot.

**Line doubling is the second store pair through `%a3 == %a2 + 160`**: 24 cycles per group. The
alternative — a separate `movem` copy pass over the finished line — measures 2.71 cycles/byte on this
machine (the fill loop is exactly that code), i.e. 33 cycles for the same 8 bytes plus a second walk
over the image. The inline write is cheaper and needs no second pass.

`.bss` is capped at `SUBALIGN(4)` rather than the inherited `SUBALIGN(2)`: a longword read from a
merely word-aligned address is legal on the 68000 and costs four extra cycles, eight times per group.

### Ceiling and floor: measured **both** ways, and the answer is not close

* **In the chunky buffer** (`in chunky` rows): the drawer writes them at ~31 cycles/pixel and the c2p
  then converts all 100 view rows.
* **As a planar band fill** (`band fill` rows): the frame's wall band is `min(top)`..`max(bottom)`
  over all columns; outside it the view is two flat colours, written straight to the screen by a
  10-register `movem.l` at 2.71 cycles/byte, and only the band goes through the chunky buffer.

At 160 columns that is **1,570,066 -> 914,165 cycles, a 42% saving on the whole frame**; at 80
columns 855,519 -> 510,078, 40%. The band in this scene averages 28 of 100 rows.

Because the band is `min`/`max` over the columns, **no clipping is needed anywhere** in the asm
drawer: each column's ceiling, wall and floor runs are non-negative by construction and sum to the
band's height exactly.

### Raycast

Fixed point 16.16 throughout, a grid DDA walking a **map pointer** (`+/-1`, `+/-MAP_SIZE`) so the
loop never recomputes `y * MAP_SIZE`. `sin` and a reciprocal table are generated at build time by
`gen_tables.py`; there is no `tan` table because the only tangent in the program is `tan(FOV/2)`, a
single build-time constant that the generator *checks* against `spike.h` rather than restating.

Three optimisations mattered, measured end to end: the raycast stage went **122.5 ms -> 50.6 ms per
frame** at 160 columns.

1. **The ray directions are an arithmetic progression.** `ray = dir + plane * camera(x)` is linear in
   `x`, so the sweep is one add per column, not two multiplies.
2. **Every remaining product is 16x16.** Two of them were still reaching libgcc's 32x32 `__mulsi3`
   (about 250 cycles plus the call) because GCC could not prove the narrowing; naming `mulu.w` /
   `muls.w` in inline asm makes all of them the 68000's own ~70-cycle instruction. The one division
   (the wall's pixel height) is a `divu.w` helper for the same reason.
3. **The map is a room grid, not an open field.** The DDA steps once per grid line crossed, so an
   open map measures the map rather than the renderer.

### The per-column loop is in asm, and that was worth 20 ms

The first build called a per-column asm routine from C with a parameter block. With the band
optimisation a column is about a dozen pixels tall, and that call measured **1,680 cycles to draw 13
pixels** — the block, the push and the prologue, ten times the pixels. Moving the whole loop into
`spike_draw_columns`, walking the `SpikeRay` array itself, brought the per-column cost to about 120
cycles.

---

## A 68000 hazard found on the way (worth carrying into the game)

GCC 16 compiles a copy between two arrays whose addresses are both known at build time into a single
address register:

```
    move.l (%a0)+,(d,%a0,%d0.l)          | d == destination - source
```

On the 68000 the source operand is fetched and `%a0` post-incremented **before** the destination's
effective address is calculated, so every longword lands four bytes too high and the whole copied
block is shifted by one slot. It was found because the published ledger's magic was at the right
address and every field after it one late — a corruption that reads as a struct-layout disagreement,
not as a code generation fault. `volatile` on the destination does **not** stop it (the fold is a
choice of addressing mode, and GCC still emits exactly one store); hiding the destination pointer
from the optimiser with an empty `__asm__` constraint does.

This is a **platform-seam finding**: anything in the game that copies between two fixed addresses —
a screen swap, a resource unpack into a fixed buffer, any hardware shadow — can be compiled into it.

---

## What is **not** verified

* **Real hardware.** Every number is Hatari 2.6.1's 68000 model on `--machine ste` with EmuTOS 1.0.6
  and 1 MB. The bus and prefetch behaviour that produces the 4-11% over the instruction-table sums is
  Hatari's; the ST's video DMA contention in particular is a model, not a measurement.
* **The 68000 MOVE aliasing hazard above** is measured only under Hatari. It was **not**
  cross-checked against the Musashi oracle (`tools/recreate_kit/oracle/emu.py`): that oracle binds to
  a project through `recreate_kit.project.load()` and needs a project image and loader, which this
  standalone spike does not have — building that scaffolding was out of proportion to the check. The
  *fix* is emulator-independent (it removes the aliasing entirely), but *which* of GCC and Hatari is
  wrong about the semantics is open, and worth settling before the game relies on either.
* **Three of 160 columns** disagree with the float reference by 6-7 rows. All three are grazing rays
  at a wall corner. The spike does not prove they are only that; a fixed-point DDA can legitimately
  enter a different cell there, but so can an off-by-one in the seed distances, and nothing here
  distinguishes the two.
* **Interrupts were left enabled** during timing, because the clock being read is TOS's own 200 Hz
  timer. EmuTOS's 200 Hz and VBL handlers are therefore inside every number, unquantified (expected
  well under 1%).
* **The CPU is taken as exactly 8.000 MHz** for the cycle columns. A PAL ST runs at 8.0106 MHz, so
  the cycle figures are 0.13% low.
* **Sound, input, HUD, sprites, double buffering and the blitter** are all absent. A real frame adds
  a HUD, an object pass and a screen flip on top of everything above.
* **The 80-column mode is 4 px wide by 2 lines tall**, an aspect ratio that has not been looked at as
  a picture, only as a number.

---

## Recommendation

**Do not ship 160x100 full-screen as the default.** Measured, the best 160-column frame is 914,165
cycles — **5.7 times the 50 Hz budget, 8.75 fps** — against the brief's 14 fps target. The 80-column
fallback reaches **15.7 fps** (510,078 cycles) against its 20 fps target. Neither target is met by
this architecture at a full-screen view, and the gap is not in any one loop: the three real stages are
within 4-11% of their hand-counted best, so there is no factor of two hiding in the code.

What to do about it, in the order the measurements support:

1. **Default to 80 columns and adopt the band fill.** That is 510,078 cycles today, and the band fill
   is a measured 40-42% of the whole frame — the single largest lever in the spike, and it is already
   built.
2. **Shrink the view window.** c2p and the fill are exactly linear in view rows (5,289 and 5,307
   cycles per row at 100 and 28 rows), and the drawer is linear in band rows. A 160x64 window under a
   HUD removes 36% of every per-row cost. This is the cheapest remaining win and it is what a
   Wolfenstein-style HUD wants anyway.
3. **Put the raycast in asm.** It is 40-49% of the frame at both column counts and 2,530 cycles a ray;
   its DDA step is 82 cycles of compiled C where hand-written would be near 50. Halving the stage is
   worth ~200,000 cycles at 160 columns, ~100,000 at 80.
4. **Make the band per-group instead of per-frame.** The band is currently `min`/`max` over *all*
   columns; per 8-column group it would be much tighter in any view with mixed depth. The measured
   cost is a restructured c2p inner loop (reads at a row stride, +17% per group by instruction count)
   against a large cut in rows converted.
5. **Consider 8 colours (3 planes) in the 3D view.** The c2p's stores and one of its two accumulators
   go away — about a quarter of 148,583 cycles at 160 columns. This is a design decision about the
   look, not a code change, and it should be made before the art is authored.

Two things explicitly **not** recommended: a 16-bit-index c2p table (512 KB per plane pair, and this
is a 1 MB machine), and per-column planar writes (the brief's own ~80 cycles/pixel, against the
33 cycles/logical pixel the table c2p measures).

---

## Files

```
spike.h        every constant the C and the asm share; render.S is a .S so cpp includes it
main.c         the driver: world, raycast, timing, ledger, report
render.S       the four hot loops: spike_draw_columns, spike_c2p_high/low, spike_fill, and the clock
os.S           _start and the TOS trap wrappers (they save d2/a2 around every trap)
gen_tables.py  build-time sin and reciprocal tables -> tables.c
tos.ld         copied from projects/wonderboy/recreate/atari/, SUBALIGN raised to 4 (see its header)
mkprg.py       copied unchanged from the same place
bench.py       two headless Hatari runs -> screenshot, ledger, this table
verify.py      the geometry and drawing checks above
out/frame.png          the captured frame (with Hatari's borders)
out/frame_screen.png   the same frame cropped to the 320x200 screen
out/ledger.bin         the ledger and the showcase frame's SpikeRay array, straight out of RAM
out/table.txt          this run's table
disk/RESULT.TXT        what the program itself wrote through GEMDOS
```

`make` builds `disk/SPIKE.PRG`; `make bench` runs it and prints the table; `make verify` checks the
picture.
