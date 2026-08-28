# CRITIQUE — three concepts, hard read

Credit first, briefly, because it is deserved: **all 46 quoted colours are 4-bit-safe** (every
channel a multiple of `0x11` — nothing silently quantizes), the **cycle table sums exactly to
480,000 = 3 VBLs = 16.67 fps**, the **80-column fallback closes** (27,500+75,000+35,000+120,000+
60,000 = 317,500 <= 320,000), and the **sample claim is right**: 100 KB at 12,517 Hz 8-bit =
7.99 s (8.18 s for 1024-byte KB). This designer did the arithmetic. Now the problems.

## (a) Technical honesty

**The c2p budget is the load-bearing lie.** 120,000 cycles for 16,000 chunky bytes → 32,000 planar
bytes *plus* pixel-doubling is ~7.5 cycles/pixel including the double. A good table-driven 68000
8bpp→4bpl c2p is 6–8 cycles/pixel on its own, and the vertical line-double alone is 32,000 bytes of
`movem.l` traffic (~32–48k cycles). Realistic: **160,000–200,000**, 1.3–1.7x over — and it is a
*fixed*, content-independent cost that no far-clipping or palette trick reduces by one cycle.

**Every line is average-case; the game is played in the worst case.** 150,000 for 160 wall columns
= 937 cycles/column. Nose-to-wall in a corridor makes all 160 full height: 16,000 textured pixels
at a realistic 12–16 cycles = **~224,000**, 1.5x the line. Corridors are not an edge case in a grid
raycaster, they are the level. Same fault in sprites: "6 max on screen" budgets by *count*, but
cost scales with on-screen *area* — one near 60x60 sprite is ~3,600 masked pixels (~45k cycles),
and HADAL's "scuttlers arrive in threes" puts three of those in your face by design.

**Two unbudgeted costs.** 2,048 B/texture is 64x64 *nibbles*, so every column pixel costs a
shift+mask — or you store bytes and 3 texture sets go **245,760 B → 491,520 B**, which with 100 KB
samples, 64 KB screens, 64 KB c2p tables and code does not fit 1 MB under TOS. And nothing budgets
**depth-shaded sprite variants**: un-shaded billboards pop out of the fog at full brightness and
destroy the baked-shading illusion. Three variants each is a silent 3x on sprite memory.

**Smaller flags.** "200 columns" is not a thing — column width must divide 320, so 2px or 4px.
HADAL's "2-entry palette cycle on the ceiling" contradicts itself: the ceiling colour *is* the ramp
terminus *is* the far-fill, so cycling it cycles the fog. MISERERE's palette-animated window needs a
free register and all 16 are spoken for. All three treat the line-160 raster split as free — it fits
an HBL (~192 cycles) but it is Timer-B work the Musashi oracle cannot see (brief gotcha #5).

**Correct and worth keeping:** baked 5-band shading with `band + is_NS_face` as one add; flat-fill
beyond the last band; MISERERE's live 4096-gamut ramp interpolation, and its lantern-shortens-
draw-distance-so-frame-rate-rises, which is real rather than hand-waving.

## (b) 16-colour strategy

**HADAL** — 1 + 9 + 6 = exactly 16, with **zero left for sprites**. The ramp is good (luminance
237/204/176/151/131/109/92/55/16, monotone and evenly stepped — it will read), but enemies must be
built from the six accents, three already committed to keycards and alarms. The crab and the
anglerfish end up fighting the HUD icons for hue.

**BLACK ICE** — cleanest split on paper, but the concept's own language is the bug: magenta is the
ICE *and* the enemies, so hostile sprites sit on hostile walls with only white and yellow to
separate them. And 5 shades must serve both texture detail and 5 depth bands; by band 3 every wall
is one flat dark rectangle, which makes the tech-demo risk worse than admitted.

**MISERERE** — a measurable collision, fatal to the stated claim. Candle `#EE8822` = Y155 vs paper
`#AA9977` = Y154; candle `#BB4411` = Y98 vs paper `#776655` = Y105. Lit-vs-unlit is therefore
**chroma-only** — and chroma is what dies under 2x2 doubled pixels, hatching interference and a
mistuned SCART CRT. Worse, enemy outlines are `#000000`, which is also the far-fill: a
black-outlined figure in a dark corridor is invisible.

## (c) Readability at 160x100 doubled

BLACK ICE wins outright: hard edges, high chroma contrast, flat void, nothing to shimmer. HADAL is
fine — 4-px-and-up features. MISERERE is the risk: hatching at 2x2 doubled pixels is a moiré
generator, and confining it to the near bands does not help, because near textures are exactly the
ones resampled at varying scale as you walk. Needs a shimmer test, not a paragraph of confidence.

## (d) Art achievable by scripts, no human artist

This is where the ranking flips. **Geometric walls are what PIL is best at; figures are what it is
worst at.** MISERERE's defence — "hatching is line maths" — is true and irrelevant: procedural
hatching over a badly-drawn silhouette is a badly-drawn silhouette with hatching. It answers for the
textures and quietly skips the four enemy figures. HADAL has the same problem milder (hardsuit in 4
view angles, crab, anglerfish — all organic). BLACK ICE's enemies are turrets, lattices and
geometric drones: the only concept whose *sprites* are as scriptable as its walls.

## (e) Fun, honestly

**HADAL** — competent, atmospheric, familiar. The air timer is a proven spine and "the airlock is
your only checkpoint" is good tension design. But limited-air-in-a-flooded-facility is well-worn and
eight steel decks will blur; a per-act tint is a paint job, not level variety. Well-reviewed, not
remembered.

**BLACK ICE** — the most reliably fun and the least interesting to describe. The trace meter is a
real escalation system, tempo-stepping music *as* the timer is strong, piercing shots on a grid map
are genuinely tactical, and an anchor-shooting boss is a puzzle rather than a sponge. 22 minutes
with a route timer is a replayable shape. It is just the fourth-best Tron game you have played.

**MISERERE** — the only one that could be remembered, and the only one that could be tedious.
Optimal play is lantern-low: a near-black screen, slow movement, a 2-second reload between shots.
A screenshot problem and a pacing problem at once. Nobody should believe it before a prototype.

## (f) Sound

All three break the same rule: **the STE has one DMA channel and no mixing**, so any sustained
sample locks out every other sound for its duration. HADAL's "torch loop-cell" and "drowning
heartbeat" are continuous — firing the torch would silence the hit, the chitter and the hurt cue.
MISERERE is the best fit almost by accident: silence plus discrete one-shots is what one-shot DMA
wants. BLACK ICE is fine (ten short stingers), its YM bassline pure register work. DMA replay also
steals bus cycles — small at 12.5 kHz, but a line on the table, not zero.

## Scores

| | Technical fit | Art by scripts | Distinctiveness | Fun |
|---|---:|---:|---:|---:|
| HADAL | 7 | 6 | 7 | 7 |
| BLACK ICE | 9 | 9 | 4 | 8 |
| MISERERE | 7 | 5 | 9 | 7 |

## My ranking — I disagree with the designer

**1. BLACK ICE. 2. HADAL. 3. MISERERE.**

He ranked on ceiling; I rank on what kills projects. Distinctiveness is the *only* axis BLACK ICE
loses, and the only one fixable after the engine ships — you can re-theme art onto a working
renderer; you cannot re-hire a pixel artist you never had. MISERERE bets the whole game on the one
capability this team does not possess. It is the right *second* game, on BLACK ICE's engine, once
the renderer is known — which the designer half-says in his own caveat and should have followed.
His cross-pollination note is right: **the lantern is the best idea in the document** and it is not
theme-locked. In BLACK ICE it is a render-radius throttle — cut visibility to run silent past the
Sentries, and the frame rate rises exactly when the room gets busy. Take it.

## Biggest risk of the top pick, and week 1

**Not aesthetic — the c2p+pixel-double pass.** A fixed cost booked at 120,000 that I put at
160,000–200,000. If it lands at 190k the scene budget drops 360k → 290k and every other line
renegotiates at once, after the engine is written. **Week 1, before any art:** write c2p standalone,
cycle-count it on the Musashi oracle at 160x100 and 80x100, and Hatari-verify the line-160 raster
split on `--machine ste`. Pin both in STATUS.md. If c2p exceeds 150,000, 80 columns becomes the
*default* and 160 the option — decided in week 1, not month 3.

## Five changes demanded before greenlight

1. **Re-budget by worst case.** Replace the table with a measured nose-to-wall corridor frame and a
   three-near-sprites frame. Swap "6 sprites max" for a per-frame *sprite pixel* budget with
   priority-ordered dropping.
2. **Decide nibble-vs-byte texels and publish the RAM ledger** — 245,760 B vs 491,520 B is the
   difference between fitting 1 MB and not. Include the 3x depth-shaded sprite variants.
3. **Fix the magenta-on-magenta hole.** Reserve two accents as sprite-only colours no wall may use,
   and mandate a 1-px `#FFFFFF` rim-light on every enemy, tested against every wall at every band
   before art production starts.
4. **De-generic the theme.** As written it is Tron. The mainframe is *dying*: corrupted sectors are
   where the geometry itself is wrong — grid drift, mismatched textures, walls that read as damaged
   data. Landmark rooms and a named world, not a colour scheme.
5. **Delete the 200-column plan and the pad dependency**, and import the lantern as the
   render-radius throttle in the same commit. Controls complete on a standard joystick.
