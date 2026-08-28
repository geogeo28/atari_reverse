# ART_REVIEW — BLACK ICE concept-art package (art-director pass)

Every number below was re-derived off `out/native/*.png` against `palette.py`'s own tables, not
taken from ART_DIRECTION.md.

| # | Axis | Score | One line |
|---|---|---:|---|
| 1 | Reads as a real ST game | **7** | The Ledger is a 1991 ST game; the Kernel is a tech demo — 46% of it is pure index 0 (Ledger: 25%). |
| 2 | Readability at 160x80 doubled | **5** | Four textures become one material by band 3, and the weapon eats 45–60% of the window's height. |
| 3 | Palette | **7** | The cyan/magenta claim holds; the *slate* it never measured is the tightest pair in the set. |
| 4 | HUD strip | **6** | Legible and coherent, and pointed at the wrong number. |
| 5 | Title screen | **7** | The wordmark earns a box front; the legless figure and two empty corners do not. |
| 6 | Honesty of the mockups | **9** | Verified achievable — zero cheats found. Two deductions, both named. |

## 2 — Readability, measured

I re-rendered all ten textures through `shade_table(band)` at the size a wall actually occupies
(32 cols x 15 rows at band 2, x10 rows at band 3) and counted identical-pixel agreement:

| pair | band 2 | band 3 |
|---|---:|---:|
| `bus_trunk` / `hex_mesh` | 39% | **89.1%** |
| `bus_trunk` / `circuit_lattice` | **60.2%** | **87.5%** |
| `circuit_lattice` / `hex_mesh` | 48.5% | **85.3%** |
| `sector_key_panel` / `door` | **51.9%** | 63% |
| `circuit_lattice` / `corrupted_sector` | 59.2% | 66% |

`bus_trunk`, `circuit_lattice`, `hex_mesh` and `anchor_pylon` are one material at band 2–3 — dark
navy with cyan crossbars. The only tell is `circuit_lattice`'s vias, 1.8% of its area, which may not
fall in the visible slice. `door` and `sector_key_panel` both read "cyan panel, yellow horizontals"
(13.3% / 7.6% yellow) — a *functional* confusion between what you walk through and what needs a key.

**The band-3 slate inversion is the worst defect in the package.** Band 3 sends yellow(11)→15 and
green(14)→15, but sends **slate(15)→0**. Every texture's structural shadow punches through to void:
`sector_key_panel` loses **16.1%** of its area to black holes, `door` 14.2%, `glyph_column` 11.5%,
`exit_gate` 10.4%. A *healthy* wall at nine cells grows exactly the stepped black holes that
`textures.corrupt`'s "torn page" uses to mean damage. Distance manufactures corruption, inverting
the premise of the world.

`tex_corrupted_sector.png` is genuine data damage at bands 0–1 — the wrong-ramp stripe and stepped
hole read as a bad decode, not dirt — but at band 2–3 it is 59–66% identical to `circuit_lattice`,
so the damage stops being legible exactly where the slate bug starts faking it.

**Enemies.** Downsampled to 25 rows, all four silhouettes are distinguishable: Watchdog (two-legged
arch), Sentry (octagon), Tracer (winged delta), Black Ice (shouldered humanoid). That passes. Two
problems: at 16 rows Sentry and Black Ice are both a blob, and **`spr_sentry` and
`spr_integrity_patch` share the same octagon-with-a-bright-centre silhouette** — and since green
dies to slate at band 3, a distant heal and a distant Sentry are the same shape at the same value.
All four enemies also carry the orange core in the same place, so index 13 says only "alive".

**Pickups.** `cycles_cell` and `integrity_patch` read instantly; `access_token` reads as a tag.
**`spr_trace_scrubber` does not read** — a slanted cyan/magenta "7" with a torn-quadrilateral
silhouette; nothing in it says "scrubber".

**Weapon overlay, measured.** Template-matching the assets into the mockups gives **100% pixel
agreement** at x32,y32, so these are the shipped overlays. `spr_buster_idle`: **36 ink rows = 45% of
the 80-row window**, 73 of 160 columns. `spr_spike_firing`: **48 ink rows = 60% of window height**,
81 columns — directly violating §6's own rule that live art stays in the lower 36 rows because
"a weapon filling 48 of the window's 80 rows hides exactly the enemies you are shooting at". A
25-row enemy centred on the horizon spans rows 28–52: the idle buster covers 9 of those 25 rows
(36% of the target), the firing spike covers 21 of 25 — **84%**.

## 3 — Palette

The advertised separation is real: worst cyan-vs-magenta in any band is dY 16.3 with **dChroma
96.5** (band 2/3, idx 4 vs 9); band 4 is dY 23.6 / dC 41.5. On a mistuned CRT 16 Y is thin, but 96.5
across the cyan/magenta axis is the widest hue split available — it holds.

**The gate never measures slate, and slate is wall-legal.** Index 15 (Y 54.9) sits **8.2 Y and 23.3
chroma from cyan 5** (Y 46.6) — the tightest pair in the palette, both on the same wall at bands
2–3, and absent from the "minimum gap 16.0" claim. **Index 15 does five jobs**: structural shadow,
HUD trim, transparency key, band-3 fogged yellow, band-3 fogged green — then fogs to void itself.
Two jobs too many.

**Yellow is over-used.** Index 11 is in six of ten textures, two of four pickups, and four HUD
elements (CYCLES digits, TRACE percentage, TRACE segments, KEYS). It has stopped meaning "data" and
now means "look here", which is not a category.

## 4 — HUD strip

The 8x8 font (5x7 ink, 7px advance) is legible at 1:1 in both native mockups — that call was right,
as was skipping the Timer-B split. Only 3 of 40 rows are blank, so rows are not wasted, they are
*misallocated*: **CYCLES is drawn at 2x and is the loudest thing on the strip**, while TRACE gets an
82px panel (INTEGRITY gets 88), the same 12-row ten-segment bar, and its percentage in 8px yellow.
The core escalation mechanic is the third-most prominent readout. The title bar spends 10 rows —
25% of the strip — on a sector name that never changes mid-sector.

## 6 — Honesty

Verified rather than trusted: **zero off-palette pixels** in any native PNG or the contact sheet;
**every 2x2 block in the 320x160 window is uniform**, so the mockups really are 160x80 logical;
floor and ceiling are strictly index 0; no gradient, dither-blend or anti-aliasing anywhere;
sprites composited unmodified. This package could be re-rendered by the engine. Deductions:
`spr_spike_firing` breaks §6's own rule, and **the Kernel does not deliver "the DYING mainframe as
broken geometry"** — its dramatic V is ordinary near-wall perspective, the only damage present is
one corrupt texture, and the Shear ("one wall written twice") is described in §1 and drawn nowhere.

## Eight fixes, by impact

1. **`palette.py`, `shade_table(3)`** — stop mapping slate(15)→0; send it to cyan-5 or magenta-5.
   *Why:* it punches 10–16% void holes into five clean textures, so distance fakes corruption.
2. **`sprites.py`, `spike_firing` / `buster_firing`** — clip live art to the lower 36 rows, cut the
   muzzle burst to ~12 rows. *Why:* firing hides 84% of a 2.5-cell enemy.
3. **`textures.py`, `bus_trunk` / `hex_mesh` / `circuit_lattice`** — give each a signature that
   survives 10 rows: a full-height 6px slate rib, an unbroken 4px diagonal, a 4px yellow via
   *column*. *Why:* 85–89% identical at band 3 means three sectors are one place.
4. **`textures.py`, `sector_key_panel`** — move its yellow to a single vertical 4px keyway and put
   lock state in green. *Why:* 51.9% identical to `door` at band 2 is a navigation bug.
5. **`sprites.py`, `integrity_patch`** — square the outline, drop the octagon. *Why:* it shares the
   Sentry's silhouette, and at band 3 its value too.
6. **`hud.py`** — swap the scales: TRACE at BIG_SCALE with a 16-row bar, CYCLES at 1x, rows stolen
   from the title bar. *Why:* the trace meter is the game and is presently third.
7. **`sprites.py`, `trace_scrubber`** — redraw as a cut cable / broken link, cyan on slate.
   *Why:* a pickup that needs a legend is not a pickup.
8. **`keyart.py`** — add a publisher/year line and fill the empty lower corners with two receding
   pylon silhouettes. *Why:* the cheapest available increment of "product, not demo".

## The single change that most raises the "real game" feeling

**Fix 2 — redesign the weapon overlays.** A first-person game is sold by the object in the player's
hands, and BLACK ICE's reads as a cyan podium with an oval inlay: the largest element in every
screenshot, furniture rather than a weapon, and it covers the target when it fires. A silhouette
that reads as *held* — asymmetric, angled up from the lower right, ink confined to the bottom 36
rows — converts both mockups from renderer output into a game, at zero engine cost.
