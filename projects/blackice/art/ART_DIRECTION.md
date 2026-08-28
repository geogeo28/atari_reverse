# BLACK ICE — Art Direction

Everything in `art/` is produced by committed Python (PIL + numpy, seeded, no hand-editing).
`make` (or `python build_art.py`) rebuilds every PNG and runs every gate.

## 1. The world

**HALCYON** — a Frayne-Bellamy HX-9 on Ossuary Row, eleven months into a failure its owners have
stopped paying to arrest. You are a repossession runner walking its memory map as physical space.
The premise is visual, not textual: **a healthy sector renders as clean architecture and a failing
sector renders wrong**. Corruption is never dirt or noise. It is *data damage* — geometry that
reads as a bad read.

Sector names are `design/DESIGN.md` §14; the art gloss is this document's.

| # | Sector | What it looks like |
|---|---|---|
| 1 | **INGRESS** | Clean. `bus_trunk` and `circuit_lattice`. The `door` and the `sector_key_panel` are taught here and never re-explained. |
| 2 | **THE LEDGER** | `circuit_lattice` walls with `glyph_column` running the long halls — records you can see and never read. Mockup 1. |
| 3 | **NURSERY** | The Fork Ring, walled in `hex_mesh`: load-bearing structure, no data on it. DEGRADED palette. |
| 4 | **BAD BLOCK** | First corrupt sector. `corrupted_sector` throughout, `firewall_chevron` on every frozen door. The Shear reads as one wall written twice. |
| 5 | **THE CHOIR** | The Switchboard: `glyph_column` at wall scale, an entire hall of dead lines, faked in texture alone. |
| 6 | **DEAD LETTER** | `corrupted_sector` over `circuit_lattice` bones. One room stamped four times; texture damage is the only tell. CORRUPT palette. |
| 7 | **COLD STORE** | Tape bays in `bus_trunk` and `hex_mesh` ringing a well fenced in `firewall_chevron`. |
| 8 | **THE KERNEL** | Terminal corruption. `corrupted_sector`, four `anchor_pylon` slabs, the `exit_gate` at the end. Mockup 2. |

## 2. Visual rules

1. **Floor and ceiling are index 0.** Not a compromise — the void is the point, and it is also the
   border colour, so overscan is the same nothing.
2. **Cyan is infrastructure you can use. Magenta is ICE that wants you dead.** Two ramps, one
   grammar, legible in a glance at 160x80.
3. **Yellow is data** (glyphs, vias, tokens, hazard bands). **Green is safe** (integrity, exit
   lamps, satisfied locks). **Orange is live and hostile.** **White means object, not world.**
4. **One light direction for the whole machine: top-left.** Every raised face is bevelled light on
   top/left and dark on bottom/right (`textures.panel`). Eight unrelated patterns still read as one
   building because they are all lit by the same lamp.
5. **Nothing thinner than 2 px, no isolated single pixels.** Structure is 4–8 px, because the
   renderer doubles 2x2 and then minifies with distance.
6. **Corruption is data damage, never noise.** Four named failures, all in `textures.corrupt`:
   *grid drift* (8-px row bands displaced sideways), *wrong ramp* (a band decoded through the
   magenta ramp — the cyan is simply not there), *stuck bits* (one row latched and repeated),
   *torn page* (a stepped hole, edged in slate, where the page is not mapped).
7. **Vertical period divides 64**, so a wall taller than one tile has no seam. Gated by
   `drawlib.vertical_seam_ok`; all ten textures pass.

## 3. The palette

16 registers, every channel a multiple of `0x11`, so nothing quantises into an STE colour word.
`palette.ste_colour_word` does the `$0RGB` low-bit-is-MSB swizzle; never hand-encode it.

| Idx | Hex | STE | Y | Role | Walls may use |
|---:|---|---|---:|---|---|
| 0 | `#000000` | `$000` | 0.0 | void — floor, ceiling, far-fill, border | yes |
| 1 | `#66EEFF` | `$37F` | 199.3 | cyan 1 — lit trim | yes |
| 2 | `#33CCEE` | `$967` | 162.1 | cyan 2 — panel face | yes |
| 3 | `#2299CC` | `$1C6` | 123.2 | cyan 3 — panel body | yes |
| 4 | `#116688` | `$834` | 80.5 | cyan 4 — shadow side | yes |
| 5 | `#113366` | `$893` | 46.6 | cyan 5 — deep recess / fog | yes |
| 6 | `#FF88EE` | `$F47` | 183.2 | magenta 1 — ICE lit trim | yes |
| 7 | `#DD55CC` | `$EA6` | 139.2 | magenta 2 — ICE face | yes |
| 8 | `#BB33AA` | `$D95` | 105.2 | magenta 3 — ICE body | yes |
| 9 | `#881177` | `$48B` | 64.2 | magenta 4 — ICE shadow | yes |
| 10 | `#330044` | `$902` | 23.0 | magenta 5 — ICE recess / fog | yes |
| 11 | `#FFEE44` | `$F72` | 223.7 | data yellow — glyphs, vias, tokens, hazard | yes |
| 12 | `#FFFFFF` | `$FFF` | 255.0 | **rim-light, muzzle, HUD text** | **NO — RESERVED** |
| 13 | `#FF7722` | `$FB1` | 150.0 | **enemy core / iris / trace danger** | **NO — RESERVED** |
| 14 | `#33CC66` | `$963` | 146.6 | integrity green — health, exit lamps | yes |
| 15 | `#444466` | `$223` | 71.9 | slate — structural trim, HUD trim, **sprite transparency key** | yes |

**The two reserved colours are 12 (white) and 13 (orange), and only those two.** That is the
critique's demand #3 taken literally: two *accents*, not five. The magenta-on-magenta hole is
closed by the rim, not by taking bright magenta away from the walls — which is why
`firewall_chevron` can still be a genuinely bright magenta wall.

**Ramps that are not luminance twins.** The two ramps interleave in luminance: cyan 199 / magenta
183 / cyan 162 / magenta 139 / cyan 123 / magenta 105 / cyan 80 / magenta 64 / cyan 47 /
magenta 23. **Minimum gap between any cyan and any magenta: 16.0 Y**, and minimum chroma distance
**41.5** in the (Cb, Cr) plane — in *every* depth band, proved by `python palette.py`.

**White's headroom** over the brightest colour a wall is allowed to contain (data yellow, Y 223.7)
is **31.3 Y**. That number is the whole reason the rim works.

### Delta against `design/DESIGN.md` §3

The design doc's colour contract differs and should be corrected to this one. Its ramps contain a
luminance twin at the top (`#CCFFFF` Y 239.8 against white) leaving the rim-light only **15.2 Y** of
headroom, and it reserves five colours (6, 7, 11, 12, 13), which costs the walls yellow *and* green
— the two accents that let `circuit_lattice` have live vias, the `door` have hazard bands and the
`exit_gate` be green. Mapping: doc 12 (green) → **14**, doc 13 (white) → **12**, doc 14 (alarm) →
**13**, doc 15 (grid) → **15**. Ramp entries keep their positions; only their hex values move.

## 4. Depth bands

Distance fog is an **index remap**, never a new colour. `palette.shade_table(band)` returns 16
entries; the renderer's shading cost is `band = min(distance / BAND + is_north_south_face, 4)` —
one add, as the critique endorsed — followed by one table lookup per texel.

| band | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|
| 0 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
| 1 | 0 | 2 | 3 | 4 | 5 | 5 | 7 | 8 | 9 | 10 | 10 | 11 | 12 | 13 | 14 | 15 |
| 2 | 0 | 3 | 4 | 4 | 5 | 5 | 8 | 9 | 9 | 10 | 10 | 11 | 12 | 13 | 14 | 15 |
| 3 | 0 | 3 | 5 | 5 | 5 | 5 | 8 | 10 | 10 | 10 | 10 | 2 | 12 | 13 | 14 | 4 |
| 4 | 0 | 5 | 5 | 0 | 0 | 0 | 10 | 10 | 0 | 0 | 0 | 4 | 12 | 13 | 14 | 5 |

Band 3 keeps each ramp's **lit trim** plus its darkest rung; band 4 keeps the darkest rung and then
void, so far-clipping is diegetic. **Nothing fogs to void except a ramp rung** — a wall-legal colour
that fogged to black punched holes shaped exactly like authored damage (see Revision 2, fix 1).
Slate and data fog *up* into the cyan ramp instead, which is also what keeps a slate rib or a yellow
via column legible at ten rows. **Three colours never fog: 12, 13 and 14.** A rim-light that fades
stops being a guarantee, a far enemy's live core is the thing you must still see, and green is the
exit, which has to be a landmark from across the sector. The sprite transparency key must be shaded
with `drawlib.shade_sprite`, which preserves it: index 15 is a flag, not a colour.

## 5. Screen layout

**Render window 160x80 chunky, pixel-doubled to 320x160 on the top 160 scanlines; a static
320x40 planar HUD strip on the bottom 40.** (Set by `design/DESIGN.md` §13; the numbers below are
why it is the right call, and why the alternative — a framed window — was not needed.)

| layout | planar bytes emitted per frame by c2p | raycast texels | HUD |
|---|---:|---:|---|
| full screen 160x100 → 320x200 | 32,000 | 16,000 | nowhere to put it |
| **160x80 → 320x160 + 40-line strip** | **25,600** | **12,800** | free — a dirty-rect blit, not a redraw |
| framed 288x160 window (144 cols) | 23,040 | 11,520 | free, but only 144 columns and no raster split possible |

c2p plus the pixel-double is the one cost no level design or far-clip reduces, and the critique put
it at 160,000–200,000 cycles full-screen. Scaling by emitted bytes puts the chosen layout at
**128k–160k**, which keeps 160 columns inside the design's own 130,000-cycle gate at the optimistic
end and makes the decision measurable rather than arguable. The framed window is cheaper still but
buys 16 fewer columns and forecloses a bottom-strip raster split; the strip keeps that option open.

**No Timer-B raster split in v1.** The HUD's four hues — white, orange, yellow, green — are colours
the walls either cannot own (12, 13) or barely use (11, 14), so a second palette buys nothing yet.
The strip is drawn at 1:1, which is why the 8x8 font is legible in it.

## 6. Ledger (byte per texel, and packed to nibbles)

| Group | Count | Bytes | Nibble-packed |
|---|---:|---:|---:|
| wall textures + door + key panel, 64x64 | 10 | 40,960 | 20,480 |
| enemy billboards, 64x64 | 4 | 16,384 | 8,192 |
| pickups, 32x32 | 4 | 4,096 | 2,048 |
| weapon overlays, 96x48 | 4 | 18,432 | 9,216 |
| data particle, 16x16 | 1 | 256 | 128 |
| HUD strip 320x40 (already planar, 4 bitplanes) | 1 | 6,400 | 6,400 |
| 8x8 font — `pipeline/stepix`, 1 bit per pixel | 96 glyphs | 768 | 768 |
| **TOTAL** | | **87,296** | **47,232** |

Storage shape: textures and enemy billboards are 64 wide, so a column-major store is one 64-byte
column per texel column. The weapon overlays are 96 = 2 x 48 wide and hold their live art in the
lower 36 rows — the empty rows above are deliberate, because a weapon filling 48 of the window's
80 rows hides exactly the enemies you are shooting at.

`make ledger` reprints this from the assets themselves. The critique's demand #2 — publish the
nibble-vs-byte number — is the last column: **40 KB saved** by packing, which is the difference
between three texture sets fitting and not.  The font row is the engine's own table (Revision 3).

## 7. The rim-light gate

`rimtest.py` composites **every rimmed sprite over every wall texture at every depth band** —
8 x 10 x 5 = **400 combinations** — finds the wall pixels each rim pixel actually borders, and
requires ≥ 24 Y between white and all of them.

- **Failures: 0.** Worst rim margin anywhere: **31.3 Y** (any sprite over `circuit_lattice` or
  `exit_gate` at band 0, against a data-yellow via).
- **Worst margin with the rim deleted: 0.0 Y** — some sprite edge colours are *identical* to the
  wall colour they border. That number is the size of the hole the rim closes, measured rather than
  asserted.
- The grid is drawn in section 3 of `out/contact_sheet.png`, each cell rule-marked green for pass
  and orange for fail.

## 8. What I could not make work

1. **The weapon overlay has no rim** and is not covered by the harness. It is exempt on the grounds
   that it is a fixed screen element at the bottom centre, where the floor is void — but that is an
   argument, not a measurement, and a bright near wall could still eat its silhouette.
2. **Pickups hover.** With a void floor there is no ground plane to stand on, so a floor-anchored
   32x32 pickup reads as floating. On theme, but unresolved; a 2-px under-glow would need a colour
   the floor does not have.
3. **One view per enemy.** A Tracer that strafes will slide sideways still facing you. A side view
   would double the enemy budget to 32,768 bytes.
4. **No animation.** One pose per enemy, no walk cycle, no death frames, no door-opening frames.
5. **Only one corrupted wall ships.** `textures.corrupt(array, seed)` will damage any texture
   deterministically, but the ledger carries a single `corrupted_sector`; per-sector corrupted
   variants are unbudgeted.
6. ~~**Green dies at band 3.**~~ Closed in Revision 2: index 14 no longer fogs at all, so an exit
   gate is green from any distance.
7. **Only vertical seamlessness is proven.** Walls are one tile wide by design, so horizontal tiling
   was never tested.
8. **Font gaps** (reported by the font pass): `@` has a 2x2 blob where its counter should be, and
   `*` is an 8-arm starburst because five columns will not hold a real asterisk.

---

# Revision 2 — answering `ART_REVIEW.md`

All eight fixes applied, in the review's impact order. Every number below comes from the scripts'
own gates (`make` prints all of them); nothing here is an estimate.

## Fix 1 — the band-3 slate inversion, and the pair the gate never measured

`shade_table(3)` used to send slate (15) to void, so 10–16% of five *clean* textures turned into
black holes shaped exactly like `textures.corrupt`'s torn page: distance manufactured corruption.
Now **no wall-legal colour fogs to void before band 4** (`palette.py` asserts it by name), and slate
and data fog *up* into the cyan ramp: `15 → cyan 4 → cyan 5`, `11 → cyan 2 → cyan 4`.

Slate also moved, `#333355 → #444466` (Y 54.9 → 71.9), and lost two of its five jobs: it is no
longer a `recess` shadow (the lip is a ramp colour now) and the substrate-dot field is gone. It
sat 8.2 Y from cyan 5 with both on the same panel; the two are now 25.2 Y apart.

The proof was extended from "cyan vs magenta" to **every wall-legal pair that can share a wall in a
band** — the axis on which slate was invisible. Rule: dY ≥ 12 **or** dChroma ≥ 40.

| band | tightest wall-legal pair | dY | dChroma | margin |
|---|---|---:|---:|---:|
| 0 | CYAN_4 vs GRID | 8.6 | 44.9 | 1.12 |
| 1 | CYAN_4 vs GRID | 8.6 | 44.9 | 1.12 |
| 2 | CYAN_4 vs GRID | 8.6 | 44.9 | 1.12 |
| 3 | CYAN_2 vs INTEGRITY | 15.5 | 68.9 | 1.72 |
| 4 | CYAN_5 vs MAG_5 | 23.6 | 41.5 | 1.97 |

The tightest pair in the palette is slate against cyan 4 — carried by hue, not luminance, and now
stated rather than unmeasured. Cyan-vs-magenta is unchanged: worst dY 16.0, dChroma 41.5.

## Fix 2 — the weapon overlays

Redrawn as a **held, asymmetric gun**: the wrist enters at the overlay's bottom-right corner and
the frame angles up and to the left along one axis (`_slab`, `_rail`, `_fin`), with a fist on the
grip, a stepped receiver-to-barrel profile, cooling fins across the barrel, and an emitter ring at
the muzzle. It is no longer a symmetric podium with an oval inlay.

`sprites.weapon_footprints()` is now a gate, not a paragraph:

| overlay | ink rows | rows | first row must be ≥ | |
|---|---|---:|---:|---|
| `buster_idle` | 13–47 | 35 | 12 | ok |
| `buster_firing` | 9–47 | 39 | 0 | ok |
| `spike_idle` | 14–47 | 34 | 12 | ok |
| `spike_firing` | 7–47 | 41 | 0 | ok |

Idle art is inside the window's bottom 36 rows; a burst climbs at most 12 rows further (measured:
4 and 7). Horizontally the ink now spans window columns 73–126 (idle) and 66–127 (firing) of 160,
so the left 40% of the window is clear — the old overlay ran the full width.

## Fix 3 — band agreement, and fix 4 — the key panel

Each of the four cyan structural walls was given a signature that survives ten rows, exploiting the
only marks that stay bright at band 3 (cyan 1 → cyan 3, slate → cyan 4, data → cyan 2):

* `circuit_lattice` — a slate substrate (the only mid-value etched wall) plus a full-height **4 px
  yellow via column** and lit trace trim
* `bus_trunk` — three unbroken full-height **slate ribs** over the straps, and nothing bright
  horizontal
* `glyph_column` — **lit rails at the tile edges** with a dark centre channel: bus_trunk inverted
* `hex_mesh` — unbroken **6 px 45° braces**, the only diagonals in the set
* `sector_key_panel` — a **lit reader plate** with one *vertical* keyway and green/magenta lock
  lamps, deliberately the inverse of `door`'s two *horizontal* hazard bands
* `corrupted_sector` — the wrong-ramp bands now decode slate and data too, so a corrupt wall can
  never collide with its clean parent at distance

Measured on the five pairs the review named (its figures → this revision's):

| pair | band 2 | band 3 |
|---|---|---|
| `bus_trunk` / `hex_mesh` | 39% → 27.9% | **89.1% → 38.1%** |
| `bus_trunk` / `circuit_lattice` | **60.2% → 16.2%** | **87.5% → 25.0%** |
| `circuit_lattice` / `hex_mesh` | 48.5% → 24.8% | **85.3% → 38.8%** |
| `sector_key_panel` / `door` | **51.9% → 16.5%** | 63% → 18.8% |
| `circuit_lattice` / `corrupted_sector` | 59.2% → 57.5% | 66% → 59.7% |

**All 45 pairs are now below the 60% gate at both bands** (`textures.agreement_pairs`, printed by
`make` and drawn on the contact sheet). Worst remaining: `circuit_lattice` / `corrupted_sector` at
59.7%, which *should* be the closest pair in the set — it is the same wall, rotted.

## Fixes 5 and 7 — sprites and the yellow budget

* `integrity_patch` is a **square** plate with a white cross; the Sentry gained top and bottom
  **mounting lugs** that break its octagon. A distant heal and a distant turret are no longer the
  same shape, and green no longer dies at range to make it worse.
* `trace_scrubber` is a **cut cable**: two sheared ends pulled out of line, a white spark across the
  break, and the magenta trace it was carrying stopping dead at the cut.
* **Index 11 now appears only where it means DATA**: 5 textures (vias, glyph records, the corrupt
  wall's inheritance, door hazard glyphs, the keyway), 2 sprites (`access_token`, `data_particle`)
  and 2 HUD elements (trace segments, key pips) — down from 6 / 2 / 4. Cycles became a cyan energy
  cell, enemy lenses took the rim white they already own, and each gun's muzzle flash takes its own
  energy colour.

## Fix 6 — the HUD points at the mechanic

TRACE moved to the leftmost and widest panel (126 px), and is now the only 2x readout, with a
**16-row** segmented bar, white threshold ticks at 25/50/75 and a percentage that takes the colour
of the band it stands in. CYCLES dropped to 1x cyan in a 52 px panel. The two rows came from the
title bar, which spent 25% of the strip on a name that never changes mid-sector.

## Fix 8 and the Kernel mockup

The title screen gained a **publisher line** (`OSSUARY ROW SOFTWARE (C) 1987`) and two receding
**anchor pylons** filling the dead lower corners, and the figure now stands whole above the bottom
block instead of being cut off at the shins.

`mockup_the_kernel` was rebuilt as a **single-cell corridor** whose north and south walls carry the
same pylon/firewall rhythm one cell out of step — **the Shear, drawn rather than described**. Void
in the render window: **46% → 32.9%**, against 32.7% for The Ledger. (The Ledger rose from 25%
because the weapon that used to fill the frame no longer does.)

## Ledger and gates after Revision 2

Byte ledger is unchanged: **87,040 bytes** byte-per-texel, **46,976** packed. Gates, all green:

* palette: cyan-vs-magenta separation in all five bands; every wall-legal pair in every band;
  rim headroom 31.3 Y; no wall-legal colour fogging to void before band 4
* textures: 10/10 vertically seamless, 0 reserved-colour violations, 45/45 pairs under the
  agreement gate at bands 2 and 3
* sprites: every enemy silhouette fully rimmed, all four overlay footprints inside their limits
* rim-light harness: **400 combinations, 0 failures**, worst margin 31.3 Y, worst margin with the
  rim deleted 0.0 Y

## Still open after Revision 2

1. The weapon overlay still carries **no rim** and is still outside the harness — argued, not
   measured. It now occupies the right half of the window only, which narrows the exposure.
2. Pickups still hover; a void floor has no ground plane.
3. One view, one pose per enemy. No animation.
4. `circuit_lattice` / `corrupted_sector` at 59.7% is inside the gate by 0.3 points. It is the one
   pair that *should* be close, but it has no headroom.
5. At 16 rows the Sentry and Black ICE are still both a blob; the lugs help at 25 rows, not at 16.

---

# Revision 3 — answering the code review

Seven verified defects, all fixed. Four of them were **gates that could not fail**, which is
why Revisions 1 and 2 reported green while shipping broken art. Every gate below has been
checked against the defect it exists to catch.

## 1. Two pickups shipped with no rim, and the gate could not see it

`integrity_patch()` and `trace_scrubber()` returned `canvas.array` instead of
`_finish_pickup(canvas)` — 100 of 164 and 148 of 172 halo pixels unpainted. The old check only
inspected the sprite's four border rows, so it was blind to it.

Now `sprites.unrimmed_halo_pixels` asserts the halo itself, over **every rimmed sprite**, not
just the enemies. `cycles_cell` failed it too on a third count (10 px): its contact cap touched
row 0, leaving no halo row for the rim. All three fixed; the gate reads 0 for all eight.

## 2. Sprites painted the transparency key as if it were slate

Index 15 is both the slate trim colour and the sprite transparency key. Four sprite bodies
reached for `palette.GRID`: `trace_scrubber` lost **277 of 672 plate pixels**, `buster_idle`
47 and `spike_idle` 40 — the glove ring and the wrist slab were holes on target, invisible in
a PNG where the key is drawn as slate anyway. Repainted in cyan 5.

New gate `sprites.key_leaks()`: every sprite is rebuilt on a VOID ground (`probe_ground`), so
any pixel still equal to the key was *painted* there. **0 for all 13 sprites.**

## 3. The rim harness could not fail by construction

It compared white against wall colours only. White never fogs, and `textures` separately
forbids walls from containing it, so the margin could not come out below `rim_headroom()` —
**the "31.3 Y" headline was `palette.rim_headroom()` re-derived, not a measurement of the
art**, and the docstring now says so. `default=float("inf")` also meant a sprite with no rim
at all scored infinity. Three gates now, only the first of which measures the art:

| gate | rule | result |
|---|---|---|
| COVERAGE | every silhouette edge pixel has a RIM neighbour, on every wall at every band | **0 / 400 failures** |
| MARGIN | white vs the wall colours the rim borders, ≥ 24 Y | 0 / 400 failures |
| LOAD | at least one combination must be invisible without its rim, or the harness proves nothing | **321 / 400** |

Negative control, run: stripping `integrity_patch`'s rim takes coverage **100% → 0.0%** and the
margin **31.3 → 0.0**. The worst body-to-wall margin is **0.0 Y** (`watchdog` on
`circuit_lattice` at band 4; `cycles_cell`'s cyan 2 on `anchor_pylon`'s cyan 2 at band 0 is the
same story). The rule is deliberately *not* "bodies must contrast with walls" — in a 16-colour
palette where sprites and walls share a ramp they cannot. The rim is the answer to that, and
LOAD asserts the question was real.

## 4. The seam test passed everything

`vertical_seam_ok` compared the wrap-row change count against the **worst** internal row
change, which every texture clears by construction. Replaced with the property itself —
`vertical_period`, the smallest proper divisor of the height at which the tile repeats — plus
two honest alternatives for tiles that have no repeat to be periodic about:

| clause | means | textures |
|---|---|---|
| `period p` | the tile repeats at a pitch dividing its height | 7 (all at period 32) |
| `joint k` | it opens and closes on the same *k* uniform trim rows | `exit_gate`, `door`, `sector_key_panel` |
| `wrap-band` | top and bottom 8 rows byte-identical to a periodic reference tile | `corrupted_sector` |

Pinned by `drawlib.main()`: a pitch-16 striped tile reports `period 16`, a **pitch-24 tile
(24 does not divide 64) reports False** and satisfies no clause.

The real test failed **five of ten textures** that the old one passed. Fixed: `hex_mesh`'s 45°
braces were clipped at the corner (a brace entering bottom-left starts a whole tile off the
left edge — the offsets now run two pitches past the tile, closing a 12-pixel miss);
`glyph_column`'s four independently-seeded records had no pitch at all (now two records
repeated, one live data mark each, so the yellow budget is designed rather than rolled);
`sector_key_panel` gained a slate trim joint and a scan pitch of 16 instead of 12, which does
not divide 64.

## 5. The 4-bit gamut was never checked

`CHANNEL_LEVELS` was declared and unused. `palette.in_gamut` / `out_of_gamut_entries` now gate
all 16 entries at import, and `ste_colour_word` **raises** on a channel that is not a multiple
of `CHANNEL_STEP` rather than truncating it — a silent truncation is a colour that looks right
in the PNG and wrong on the machine. Verified by injection: a `0x67` channel raises.

## 6. Two fonts existed; the engine's one won

`art/font.py` carried 64 hand-drawn glyphs on a 7-px advance while `pipeline/stepix/font.py`
carries 96 (ASCII 32–127) and is what the 68000 build actually loads as 768 bytes. Concept art
measuring its layouts against a font the machine will never load lies about how much room the
HUD has. `art/font.py` is now a thin adapter over stepix's table, taking its metrics unchanged:
an 8×8 cell, 5×7 art inside it, and an advance of a **full cell** — the step
`stepix.font.render_text` uses.

**Every string is 14% wider.** The HUD was re-laid to match, and the overflow is now a gate
(`hud.label_overflows`, reads "none"):

| panel | Revision 2 | Revision 3 | why |
|---|---|---|---|
| TRACE | 2–127 | **2–137** | "88%" at 2× is 48 px, not 42; the bar keeps 7-px segments |
| INTEGRITY | 130–201 | **140–219** | "INTEGRITY" is 72 px and overflowed a 72-px panel |
| CYCLES | 204–255 | **222–255**, label `CYC` | "CYCLES" is 48 px; abbreviating the label beat starving the trace bar |
| KEY | 258–283 | **258–287** | "KEY" is 24 px and overflowed by 1 |
| weapon icon | 286–317 | **290–317** | |

On the title screen the wordmark grew from 252 to **288 px** — near edge-to-edge, and better
for it — so the machine and strapline lines moved up 2 rows to clear its glow. Ledger row
corrected: **768 B**, total **87,296 / 47,232 packed**.

## 7. A stale docstring

`drawlib.shade_sprite` still said slate fogs to void at band 3, which Revision 2 changed. It
now names the real reason the key must be preserved, and points at `sprites.key_leaks`.

## Gate results after Revision 3

| gate | result |
|---|---|
| drawlib self-test (pitch 16 True / pitch 24 False) | 0 failures |
| palette: 4-bit gamut, all 16 entries | PASS |
| palette: cyan vs magenta, all 5 bands | PASS (worst dY 16.0, dChroma 41.5) |
| palette: every wall-legal pair, all 5 bands | PASS (worst CYAN_4/GRID, dY 8.6, dChroma 44.9) |
| palette: nothing fogs to void before band 4 | none (correct) |
| textures: vertical seam, real property | 10/10 (7 periodic, 3 joint, 1 wrap-band) |
| textures: no reserved colour on a wall | 10/10 clean |
| textures: band agreement ≤ 60% | 45/45 pairs at bands 2 and 3 |
| sprites: unrimmed halo pixels | 0 across all 8 rimmed sprites |
| sprites: key pixels painted | 0 across all 13 sprites |
| sprites: weapon overlay footprint | 4/4 inside their row limits |
| HUD: panel label overflow | none |
| rim harness: COVERAGE / MARGIN / LOAD | 0 / 0 / 321-of-400 |

## Still open

Unchanged from Revision 2 except where noted: the weapon overlay carries no rim and is outside
the harness; pickups hover; one view and one pose per enemy; `circuit_lattice` /
`corrupted_sector` sits 0.3 points inside the agreement gate; Sentry and Black ICE are both a
blob at 16 rows. New: **`hex_mesh` lost two ramp entries** (it now uses 1, 3, 5, 15) because the
widened braces cover the ring shading — it reads as braced mesh rather than as hex mesh at
close range.
