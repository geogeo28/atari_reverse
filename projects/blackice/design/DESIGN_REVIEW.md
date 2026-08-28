# DESIGN_REVIEW — BLACK ICE GDD, hard read

Reviewed as engine lead / art director / level designer, against `BRIEF.md` and my own
`CRITIQUE.md`. This is the document engineers build from tonight, so every finding below is
either "this stops the build" or "this ships a defect".

**Credit first, and it is earned.** The RAM ledger *re-adds exactly*: 204,800 + 101,376 +
64,000 + 12,800 + 65,536 + 12,288 + 100,352 + 8,192 + 6,912 + 4,096 + 12,544 + 90,000 +
16,384 = **699,280**; +120,000 = **819,280**; 1,048,576 − 819,280 = **229,296**. Every row's
own arithmetic checks (10·64·64·5 = 204,800; 33·32·32·3 = 101,376). All 16 palette entries are
4-bit safe (every channel a multiple of `0x11`). The cyan ramp is monotone (Y 240 / 204 / 152 /
96 / 40). The SFX table sums to exactly 4.90 s. Par sums to exactly 24:45. Both map blocks are
32×32 rectangular with a sealed border, exactly one `@` each at (15,28), rosters that match
§13/§14 exactly (L1 w4/s1/t0, L2 w5/s2/t2), every non-terminal door correctly jambed, both
Sentries in each map on a wall cell with exactly one open face, and the exit reachable under a
lock-ordered BFS with legal token order in both. The designer did the work. The problems below
are what is left.

**Severity counts: 8 BLOCKER · 24 SHOULD-FIX · 11 NIT.**

---

## BLOCKERS

### 1. BLOCKER — Level 2 as printed cannot run under the first-playable feature set

§18: *"Levels 1 and 2, exactly as printed in §12–13. … Watchdog and Sentry only. … Doors: plain
(16) and ALPHA (17)."*

Level 2's map contains two Tracers (`t` at (12,10) and (23,20)), one BETA token (`q` at
(24,25)) and one BETA door (`2` at (15,18)). I flood-filled the map: **(15,18) is the only
connection between the southern half (start, Vault, `q`) and the northern half (the Ledger
Stack, `p` ALPHA, door `1`, and the exit).** Row 18 is `###############2################` —
solid wall except that one cell. With door variant 18 unimplemented, level 2 is a start room
and a vault, and the exit is unreachable. The two Tracers also spawn as unimplemented entity
types.

**Fix (pick one, tonight):** (a) add door variant 18 + token `q` to the first playable — it is
the same code path as 17, a one-line table entry; or (b) re-author level 2 for the shipped
feature set: retype (15,18) to `+`, delete the two `t`, move `q`'s contents to a `c`. I prefer
(a): it costs nothing and keeps §13's route intact.

### 2. BLOCKER — The field of view, the projection constant and the enemy world height are never stated

Grep the document: `FOV` 0 hits, `field of view` 0, `projection` 0, `aspect` 0. The DDA, the
column-height LUT (§17 ledger row "Trig / reciprocal / column-height LUTs"), the sprite scaler
and both worst-case fixtures all need them, and none can be inferred.

This is not pedantry — it produces a live contradiction. §17: *"WC-B 'Ambush' — three Watchdogs
at 2.5 cells (each ~64x64 projected)"*. In an **80-line** window where a 1-cell-tall wall fills
the window at 1.0 cells, a 1-cell-tall enemy at 2.5 cells projects to **32×32**, not 64×64. To
get 64×64 at 2.5 cells the Watchdog must be **2.0 cells tall** — a two-metre-tall dog whose head
is above the ceiling of a 1-cell-high world. So either WC-B overstates sprite area by 4× (3,072
px, not 12,288 — in which case it is not a worst case at all), or the enemy scale is wrong.

**Fix:** state, as named constants: `FOV_BRADS` (I would use 60° = 171 brads), `PROJ_PLANE_D`
(derived), `WALL_HEIGHT_CELLS = 1.0`, `ENEMY_HEIGHT_CELLS`, and the pixel aspect assumed by the
column-height table. Then recompute WC-B.

### 3. BLOCKER — The c2p fallback gate saves nothing; the whole risk plan rests on it

§17: *"if measured c2p at 160x80 exceeds **130,000 cycles**, **80 columns becomes the shipping
default** and 160 becomes the OVERCLOCK-only option."*

The RAM ledger books **one** chunky buffer, *"Chunky render buffer | 160 x 80 | 12,800"*. If the
buffer stays 160 wide in 80-column mode (each ray writing two adjacent chunky columns), the c2p
pass converts the identical 12,800 bytes and **the fallback saves exactly zero c2p cycles** — it
only halves the DDA and the wall fill, which is not the cost the gate names. `CRITIQUE.md`
called c2p *"the load-bearing lie … a fixed, content-independent cost that no far-clipping or
palette trick reduces by one cycle"*, and this gate is a far-clipping trick.

Same fault in §5: UNDERCLOCK promises *"Frame rate: highest"* via *"Columns 80"*, but the fixed
cost is unchanged, so the promised win is much smaller than the table implies.

**Fix:** decide now whether 80-column mode uses an **80×80 chunky buffer with a 4×-horizontal-
expand c2p** (a second c2p routine and possibly a second table — neither is in the ledger or the
scope ladder), or whether it does not. If it does, book it: a second table is up to +65,536 B and
a second hot loop. If it does not, delete the gate and replace it with the only lever that
actually cuts a fixed c2p cost: a smaller window (e.g. 160×64 → 20,480 planar bytes out).

### 4. BLOCKER — The Sentry is an entity inside a wall cell, and a billboard there cannot be drawn

§11 legend: *"`s` | Sentry (cell → wall 8, needs exactly one open face)"*. §8 budgets the Sentry
as **3 sprite frames** inside the *"33 sprite frames in the whole game"* total. §8 step 5 of the
sprite pass: *"Draw the survivors back-to-front, **column-clipped against the wall depth
array**."*

A billboard whose position is the centre of a wall cell is *behind* that wall at every column
that sees it. The column clip discards it entirely. **As specified, the Sentry is invisible** —
and it is one of only two enemies in the first playable, on the level whose stated lesson is
*"the Sentry embedded in the hall's north wall teaches you that walls shoot"* (§12). The anchor
(`*` → *"cell → wall 7 + anchor entity"*) is the same class of bug.

Also a straight contradiction inside the legend: `X` is *"8 exit plating"* **and** `s` is *"cell
→ wall 8"*. The Sentry panel and the exit plating are the same texture id.

**Fix (my recommendation — it is cheaper and looks better):** the Sentry is **not a sprite**.
It is a per-cell wall-texture override with three states (iris closed / iris open / destroyed),
drawn by the wall path at full 64×64 texture resolution on its one open face, costing zero
sprite pixels and no depth bias. Consequences to fold in: sprite total 33 → **30**; three new
wall textures (+3 × 64 × 64 × 5 = **+61,440 B**); a per-cell texture-override array (2,304 B,
already inside the 6,912-B resident-level row's slack); `s` gets its own texture id, not 8; §8's
*"destroyed frame stays as scenery"* becomes a texture-id swap. The alternative — placing the
billboard at `cell_centre + 0.45 × face_normal` with a depth bias — works but re-introduces
z-fighting on the flank and burns sprite budget on a static object.

### 5. BLOCKER — The door plane is under-specified; as written a door is invisible from inside its own cell and stops nobody

§10: *"a ray entering a door cell hits the door if its `u` coordinate within the cell is
`< (64 - open_fraction)`, otherwise it passes through. One compare, on door cells only."*

Three holes, all of which an engineer hits in the first hour:

- **Which plane?** "u within the cell" on *entry* puts the door coplanar with the neighbouring
  wall faces — so a door has a *different* plane depending on which side you approach from, and
  once the player or a ray is inside the cell the entry face is behind them and is never tested
  again. The door is invisible from inside its own doorway and blocks nothing there. Wolf3D
  solved this by recessing the door to the **cell midline** and taking one extra half-step in
  the DDA. That is the decision, and it is not made.
- **Which axis?** `u` is the perpendicular coordinate, but the door's slide axis is fixed by its
  jambs (§11 validates *"wall jambs on exactly two opposite sides"*). A ray entering the door
  cell through a *jamb-parallel* face measures `u` along the wrong axis and the compare is
  meaningless. The rule must say: test only the crossing of the **jamb-normal** plane.
- **Collision.** Nothing states that the player/enemy collision test uses the same rule. It must,
  or you walk through a shut door.

**Fix:** specify "door plane at the cell midline on the jamb-normal axis; the DDA takes one extra
half-cell step inside door cells; the texture column is `u`, the door is hit iff
`u < 64 − open_fraction`; the collision test uses the identical predicate against the collision
radius." Then variant 22's *"frozen at 3/8 open … see through the slit"* works for free.

### 6. BLOCKER — The stated compiler rule rejects both shipped maps; the document claims they are validated

§11: the compiler *"validates and refuses … every door having wall jambs on exactly two opposite
sides"*. §13 closes with: *"(Both maps are machine-validated: sealed border, single start, every
cell and pickup reachable, every door jambed on two opposite sides, every Sentry with exactly one
open face.)"*

I ran that rule. It fails three cells:

| Map | Cell | Glyph | N | S | E | W | Fault |
|---|---|---|---|---|---|---|---|
| Level 1 | **(15,30)** | `S` | `.` | `#` (border) | `#` | `#` | jambs E/W ✓ but the through-axis is walled on the south |
| Level 2 | **(15,30)** | `S` | `.` | `#` (border) | `#` | `#` | same |
| Level 2 | **(27,1)** | `>` | `#` (border) | `.` | `#` | `#` | same, on the north side |

The rule is wrong, not the maps: variants 21 and 23 are **terminal** doors — §10 says *"23 `>`
sector exit gate: **entering** it ends the level"* and §9 says *"Reach the entry gate and you
escape"*. They are touched, not passed through.

**Fix:** exempt variants 21 and 23 from the through-passable half of the rule; require instead
"jambs on two opposite sides **and** at least one open face". Note the inconsistency this
exposes: level 1's `>` at (15,2) is a *passable* door that opens into a 4-cell pocket
(14,1)–(17,1) reachable only by ending the level, while level 2's `>` at (27,1) is terminal.
Pick one convention.

### 7. BLOCKER — The joystick modifier layer conflicts with the two most common inputs in the game

§6: *"Fire (press edge) | shoot the current weapon, immediately, exactly once"*, *"Fire held ≥ 6
ticks, then Up (edge) | swap weapon"*, *"Fire held ≥ 6 ticks, then Down (edge) | cycle the clock
throttle"*, *"Fire held ≥ 6 ticks, then Left / Right | strafe"*.

Walk it:

1. **Hold fire and walk forward swaps your weapon.** That is the single most natural input in a
   first-person shooter and it is bound to a destructive action. Hold fire and back away cycles
   the throttle — §5: *"Changing it costs 12 ticks (0.48 s) of locked input"* — i.e. backing off
   while holding fire freezes your controls for half a second **in combat**.
2. **You cannot strafe without shooting.** Fire is edge-triggered, so entering the modifier layer
   always fires first. Every strafe therefore costs a Buster cycle (or 5 for Spike, *"unusable at
   < 5 cycles"*) and rings the noise bell — §8: *"Firing a weapon within an enemy's noise radius
   alerts it regardless of cone"*, §9: *"Firing within an unalerted enemy's noise radius | +2 %"*.
   **Strafing alerts enemies and raises the trace.**
3. **You cannot strafe and shoot.** While fire is held it is the modifier; a second shot needs a
   release and a re-press, which drops the strafe. There is no circle-strafe — the one movement
   verb the genre is built on. Meanwhile §8 gives the Tracer *"orbits at 3–10 cells, strafing,
   keeping LOS"*: the enemy does the thing the player cannot.
4. **The threshold fights the fire rate.** Buster is *"Rate 5 ticks (0.20 s)"*; the modifier arms
   at 6 ticks. Maximum DPS is therefore a press-and-release every 5 ticks, one tick from silently
   entering the modifier layer. Any press held 1 tick too long stops being a shot.
5. **Not learnable without a manual.** Nothing on screen can teach a hidden hold-then-direction
   layer on a one-button stick, and there is no tutorial hook anywhere in §12 or §15.

**Fix:** put strafe on the stick *without* a shot. The cheapest correct version: **fire is
edge-triggered on RELEASE if no direction was pushed during the hold, and suppressed if one
was** — hold-then-left is a clean strafe with no shot, tap is a clean shot, and the 6-tick
threshold disappears. Move weapon swap and throttle off Up/Down: bind swap to **Fire + Up+Down
together** or, better, drop weapon swap from the stick entirely and make Spike an *automatic*
alternate fire at ≥ 8 cells. Keep 7/8/9 and Z/X on the keyboard as written — that mapping is
good.

### 8. BLOCKER — The Watchdog chase rule cannot navigate either shipped level

§8 CHASE: *"straight-line grid walk at the player; re-paths only at cell centres."*

I simulated it two ways. Strict greedy (step to the neighbour that reduces distance) and the
charitable reading (continuous move toward the player with the player's own axis-separated wall
slide, §4: *"axis-separated (test X, then Y — you slide along walls)"*, stuck = 60 ticks with
< 0.3 cells of progress). **Both jam on the first outer corner, in both maps.** Selected results
(true BFS path length in brackets):

| Level | Enemy spawn | Player at | Sticks at |
|---|---|---|---|
| 1 | Watchdog (24,19) | (15,28) | **(23.4, 22.7)** after 82 ticks [28] |
| 1 | Watchdog (27,20) | (15,14) | **(23.3, 17.3)** after 95 ticks [18] |
| 1 | Watchdog (4,21) | (15,28) | **(8.6, 22.7)** after 84 ticks [30] |
| 1 | Watchdog (22,14) | (5,18) | **(15.3, 18.4)** after 192 ticks [21] |
| 2 | Watchdog (13,16) | (24,25) | **(24.4, 17.6)** [20] |
| 2 | Tracer (23,20) | (15,10) | **(22.4, 19.4)** after 66 ticks [22] |

Every stick point is the outer corner of one of the `######` blocks the levels are built from.
The first playable is **Watchdog + Sentry only**; the Sentry does not move; so this rule is the
entire AI of the first playable and it does not work on the only two maps that exist.

**Fix, and it is small:** keep the straight-line walk as the fast path, but on a blocked axis
**keep the unblocked component** (wall-hug) and add a 12-tick stall detector that falls back to
"step to the 4-neighbour minimising a **flood-fill distance field** to the player's cell". One
BFS per second over a 32×32 grid is ~1,000 cells — trivially affordable at 25 Hz, and it is the
same distance field the Tracer's FLEE ("runs for the nearest sector-edge cell") needs.

---

## SHOULD-FIX

### 9. SHOULD-FIX — The sprite-pixel budget is unbounded in the exact case it exists for

§8: *"`SPR_PX_BUDGET` (value TBD from the spike; provisionally 6,000 at 160 columns, 3,000 at
80)"* and *"Two fairness contracts, both non-negotiable: **the nearest entity is never dropped**,
and **an entity in ATTACK is never dropped**."*

Watchdog pack size is 4 (§8) and level 1 ships four. Watchdog contact damage is *"12 melee,
contact ≤ 0.6 cells"*, so an attacking pack is at 0.6 cells, where a wall-height billboard
projects to ≥ 80 px tall (window-clipped) and ~80–133 px wide. Four exempt sprites ≥ **25,600
destination pixels** against a **6,000-px** budget and a **12,800-px** whole chunky buffer. The
budget is the design's answer to `CRITIQUE.md`'s *"cost scales with on-screen area"*, and the
exemptions void it precisely in the ambush it was written for.

**Fix:** cap the exemption — "the nearest **one** entity and at most **two** ATTACK entities are
exempt"; clamp each sprite's projected extent to the window before accumulating; and make
`SPR_PX_BUDGET` a hard stop with a documented visual failure mode (the 4th dog in your face
flickers) rather than an unbounded promise. Then rebuild WC-B around *this* case, not three dogs
at 2.5 cells.

### 10. SHOULD-FIX — The mandatory white rim does not separate enemies from the nearest wall band

§3: *"a mandatory **1-pixel `#FFFFFF` rim on every silhouette edge**"* and *"a Python contrast
harness … asserts a minimum luminance delta between the rim and the wall pixels it borders"*.

I computed the matrix (Y = 0.299R + 0.587G + 0.114B). Every pair below **ΔY 25**:

| Sprite colour | Wall colour | ΔY |
|---|---|---:|
| **11 `#FFFF66` data yellow (Y238)** | **1 `#CCFFFF` band 1 (Y240)** | **2** |
| 13 `#FFFFFF` **the rim** (Y255) | 1 `#CCFFFF` band 1 (Y240) | **15** |
| 6 `#FFCCFF` (Y225) | 1 `#CCFFFF` band 1 (Y240) | 15 |
| 7 `#FF77DD` (Y171) | 3 `#33BBEE` band 3 (Y152) | 19 |
| 6 `#FFCCFF` (Y225) | 2 `#77EEFF` band 2 (Y204) | 21 |
| 12 `#33FF66` (Y177) | 3 `#33BBEE` band 3 (Y152) | 24 |

Two of these are fatal. **Data yellow against band 1 is ΔY = 2** — every token, cycle pickup and
data cache is *chroma-only* against the brightest wall band, which is exactly the defect that
killed MISERERE in `CRITIQUE.md` (*"candle `#EE8822` = Y155 vs paper `#AA9977` = Y154 … lit-vs-
unlit is therefore chroma-only — and chroma is what dies under 2x2 doubled pixels"*). And the
**rim itself is ΔY = 15 (6%) against band 1** — the guaranteed separator has almost no contrast
against the nearest walls, which is where enemies are largest and overlap most.

**Fix:** (a) make the rim **two-tone — 1 px `#FFFFFF` outside, 1 px register 0 `#000000`
inside**. Against a bright near wall the black edge carries the silhouette (Δ240); against the
black far-fill the white edge does (Δ255). One extra source pixel, no new register. (b) Darken
band 1 from `#CCFFFF` (Y240) toward ~Y195 (e.g. `#88DDEE`) so band 1 stops colliding with white
and yellow; the ramp stays monotone. (c) Extend the harness assertion to *pickup* colours too —
§3 currently only promises it for "every enemy frame".

### 11. SHOULD-FIX — The palette variants re-open the wall-forbidden-accent hole the contract closes

§3: *"6–7 `#FFCCFF` `#FF77DD` bright magenta | **NO — sprite only**"* and *"The magenta-on-magenta
hole is closed by rule."*

§2 device 5: *"2 CORRUPT (cyan entries 1–2 replaced by magenta 6–7, so the infrastructure itself
reads hostile)"*. §9's 75% row: *"cyan 1–2 become magenta 6–7 — the infrastructure turns on you"*.
§9's 100% row: *"cyan ramp replaced entirely by magenta"*.

The rule constrains which *registers* walls use, but the variants load **the same RGB values as
registers 6–7 into registers 1–2**. A bright-magenta enemy body then sits on a bright-magenta
wall of identical colour, separated by the rim alone — see finding 10, where the rim against band
1 is ΔY 15. This fires in **sectors 3, 5 and 7** (CORRUPT), in **THE KERNEL**, and in **every
level above 75% trace** — and §18 puts *"Trace meter with all four thresholds — palette"* in the
first playable.

**Fix:** CORRUPT and HARDENED must recolour registers 1–2 with the **dark** magentas (8–10 range,
Y 115 / 69 / 28), never 6–7's values. And the §3 harness matrix must iterate `palette_variant` ×
trace threshold, not just texture × band — as written it validates one of eight palettes.

### 12. SHOULD-FIX — Par pace alone drives the back half of the game to HARDENED

§9: *"Base, per second | +0.4 %"*, plus *"Starts each sector at `5% x (sectors finished over par)`,
capped at 25%"*, plus *"While any enemy has LOS on you | +0.6 %/s (additive)"*.

At NOMINAL, with **zero** enemy contact, playing exactly to par:

| Level | Par | Trace at par | + max carry (25%) |
|---|---:|---:|---:|
| 1 | 2:00 | 48% | 73% |
| 2 | 2:30 | 60% | 85% |
| 3 | 3:00 | 72% | 97% |
| 4 | 3:00 | 72% | **97%** |
| 5 | 3:15 | 78% | **100%** |
| 6 | 3:30 | 84% | **100%** |
| 7 | 3:30 | 84% | **100%** |
| 8 | 4:00 | 96% | **100%** |

So from level 5 on, a player who hits par exactly and never gets seen still finishes HARDENED,
and §9's *"the sector scores **PARTIAL** (no token bonus, par forfeit)"* becomes the default
outcome for the back half — which makes the par times in §14 unachievable-by-construction and
guts *"The route timer is the whole scoreboard"* (§15). Any LOS contact at all (+0.6 %/s) halves
those times. One scrubber per level (−20%) buys back 50 seconds.

**Fix:** §11 already has the right mechanism — `trace_base_rate` **per level**. Scale it so that
par pace lands each sector around 55–65%: roughly 0.4 %/s at level 1 down to **0.16 %/s** at
level 8. Then say so in §9 instead of printing a single global +0.4 %/s that contradicts §11.

### 13. SHOULD-FIX — "Standing still at UNDERCLOCK lowers trace" is arithmetically a wash

§5: *"Standing still at UNDERCLOCK is the only thing in the game that *lowers* trace passively
(−0.2 %/s)."* §9 lists −0.2 %/s under **Fall**, and lists the throttle multiplier as **0.5** at
UNDERCLOCK.

Base rise at UNDERCLOCK = 0.4 × 0.5 = **+0.2 %/s**. Credit = **−0.2 %/s**. Net = **0.00**. It
pauses the trace; it never lowers it. **Fix:** make the credit −0.4 %/s (net −0.2), or state that
it *replaces* the base rate.

### 14. SHOULD-FIX — Trace start has two sources of truth, and the death penalty is uncapped

§9: *"Starts each sector at `5% x (sectors finished over par)`, capped at 25%"*. §11 header:
*"`trace_start` | 1 | percent"* and *"`trace_carry_cap` | 1 | percent"*. Which wins is never
stated. §15: *"each death adds **+30 s to the route timer and +10% starting trace**"* — with no
cap, and §15 also says *"Death is a cost, never a wall."* Seven deaths on level 8 start you at
70%+, i.e. a wall.

**Fix:** one rule — `start = min(trace_carry_cap, level.trace_start + 5·over_par + 10·deaths)`,
with `trace_carry_cap` the single authority, and print it.

### 15. SHOULD-FIX — The texture ledger books 10; the legend needs 15

§17: *"Wall/door/panel textures, resident set | 10 x 64x64 x 5 bands x 1 B | 204,800"*.

Count from §11's legend: **8 wall textures** (1 circuit lattice, 2 hex mesh, 3 glyph column,
4 bus trunk, 5 firewall chevron, 6 corrupted noise, 7 anchor pylon, 8 exit plating) plus **7 door
textures** (16 plain, 17/18/19 locked with *"1/2/3 pips in the texture"*, 21 sealed, 22 corrupted,
23 exit) = **15**. Deficit 5 × 64 × 64 × 5 = **+102,400 B**, taking headroom **229,296 →
126,896**. Add the three Sentry-panel states from finding 4 (+61,440) and it is **65,456**, which
is 6% of RAM — still a fit, but no longer the *"Comfortable"* the document claims, and the
program-text row is itself a *"(estimate)"* of 90,000.

**Fix:** re-book the row at 15 (or 18 with the Sentry) and restate the headroom. If it needs
buying back: the locked doors 17/18/19 can share one texture with the pip count drawn as an
overlay, saving 2 × 20,480.

### 16. SHOULD-FIX — Doors + auto-close + a melee-only roster = free invulnerability

§6: *"Walking into a door cell opens it."* §10: *"Doors auto-close 100 ticks after the last body
left the cell."* §8 sight rule: *"a DDA cell walk from enemy to player that hits no wall cell
**and no closed door**"*.

Nothing says whether **enemies** open doors. If they do not: the player retreats two cells
through any `+`, waits 4 seconds, and the entire Watchdog roster — melee-only, *"Damage 12 melee,
contact ≤ 0.6 cells"* — is permanently locked out, with trace rise dropping to base because LOS
is broken too. Level 1 has a `+` at (15,22) on the main spine; level 2 at (15,23). That is a
one-move cheese of the whole first playable.

**Fix:** state it. Watchdogs and Tracers in ALERT/CHASE open variant 16 on contact (the same
predicate as the player); locked variants 17–19 stay shut to them. And do not auto-close a door
while any body is within 1.5 cells of it.

### 17. SHOULD-FIX — Locked doors have no latch rule

§9: *"Opening a locked door | +5 %"*. §10: doors auto-close after 100 ticks. Nothing says a
locked door **stays unlocked** once opened. As written, re-crossing an ALPHA door 4 seconds later
either re-charges +5% trace (a punishment for backtracking, and §12's route requires backtracking
through the Bus Hall) or silently does not. **Fix:** a locked door latches to variant 16 on first
open; the +5% fires once per door per sector.

### 18. SHOULD-FIX — Spike's per-cell occupancy list will miss enemies straddling a cell boundary

§7: *"Enemies register in a per-cell occupancy list; the shot tests only the enemies in the cells
it walks"*, with *"0.3-cell collision disc"*.

A 0.3-radius disc overlaps up to **four** cells. If an entity registers only in the cell holding
its centre, a Spike walking the adjacent cell passes clean through 60% of a body — non-
deterministically, since the enemy moves 0.18–0.30 cells per tick. On the level whose whole point
is *"This is why corridors are the tactical unit of the game: line them up"* (§7), the pierce
will feel broken.

**Fix:** register each entity in every cell its disc overlaps (≤ 4), and de-duplicate hits by
entity id during the walk.

### 19. SHOULD-FIX — Input is never latched, and the entire modifier layer is edge- and duration-based

§4: *"Sim runs at a **fixed 25 Hz** (one tick per 2 VBLs) regardless of render rate."* §17 budgets
the frame against *"480,000 (3 VBLs)"*. §6 is built on *"fire is edge-triggered"* and *"Fire held
≥ 6 ticks"*.

A 3-VBL render period against a 2-VBL tick means ticks arrive in a 1-2-1-2 pattern with ±1 VBL of
jitter, and **any press-and-release that begins and ends inside one render period is lost** unless
something latches it. Nothing in the document does. With the modifier layer keyed off press
duration, a dropped or stretched edge does not just lose a shot — it silently swaps your weapon.

**Fix:** the VBL ISR latches a sticky `pressed_since_last_tick` / `released_since_last_tick` pair
and a per-tick hold counter; the sim consumes and clears it. State it in §6 — it is also the
prerequisite for the BRIEF's replay tests (finding 26).

### 20. SHOULD-FIX — Sim/render concurrency is unspecified

§4: *"Render draws the latest sim state and may lag it; a 16.7 fps render simply skips."*

Two implementations follow from that sentence and they behave differently: (a) a catch-up loop
that runs 1–2 ticks **between** frames, or (b) sim ticks driven from the VBL interrupt, which
mutates entity positions **while the renderer is halfway through projecting them** — half the
sprites at tick N, half at N+1, with the wall depth array from neither.

**Fix:** mandate (a), plus a single-copy snapshot of the render-visible entity list taken at the
start of the frame. Costs ~64 × 8 B.

### 21. SHOULD-FIX — The audio priority rule makes firing silence the kill

§16: *"A new one-shot **preempts** a playing one only if its priority is **≥** the playing one's;
otherwise it is **dropped, never queued**"*, with Buster shot **0.20 s / priority 1**, Watchdog
snarl **priority 0**, Token grab **1**, Enemy dissolve **1**.

Buster's rate is *"5 ticks (0.20 s)"* — exactly its sample length. Sustained fire therefore holds
the single DMA channel **100% of the time** at priority 1, which drops the snarl (0) outright and
drops token grab and enemy dissolve (1 vs 1 — dropped, since a *new* sound needs ≥ and the
*playing* sound is not replaced by an equal that arrives... and if ≥ does let equals through, the
dissolve is then cut off 0.02 s in by the next shot). Either way, **killing something while
shooting is silent**, which is the one cue the player most needs.

**Fix:** enemy dissolve → priority 2, token grab → 2, Watchdog snarl → 1; shorten the Buster
sample to 0.10 s so it does not own the channel.

### 22. SHOULD-FIX — Two sounds the design mandates are missing from the sample table

§6: a locked door *"reports the token it wants (a HUD line and **a refusal tone**)"*. §5: the
throttle has a *"three-segment dial"* and four channels of feedback, none audible. Neither is in
§16's table. §16 also has *"Gate open"* but no *door close*, and the first playable is **YM-only**,
so *every* sample cue is absent on night one.

**Fix:** add refusal tone (0.15 s, priority 2) and throttle-change (0.20 s, priority 1) to the
table — the reserve is 3.1 s — and specify the YM equivalents for the first playable.

### 23. SHOULD-FIX — The HUD is a first-playable deliverable and is never specified

§18 lists *"HUD, title screen, death and retry"*. §17 says *"a **static** planar HUD on the bottom
40 scanlines"*. But the document requires it to show, at minimum: integrity, cycles, trace %, held
tokens, the *"three-segment dial"* (§5), a *"HUD compass"* (§5 — mentioned once, defined nowhere),
and a *"HUD line"* for door refusals (§6). None of that is static.

**Fix:** enumerate the fields and their cell positions; say that the panel is blitted once and the
dynamic fields are dirty-rect planar text writes into the bottom 40 lines (outside the c2p
region), and put a cycle line for it in §17's table — it currently hides inside *"Audio, HUD,
input"*.

### 24. SHOULD-FIX — No determinism contract, though the BRIEF names it as the test suite

`BRIEF.md`: *"Fixed timestep, seeded RNG, input recording -> replay golden hashes are the test
suite."* DESIGN.md: `seed` 0 hits, `RNG` 0 hits, `random` 1 hit — §8's *"teleports to a **random**
other anchor every 90 ticks"*, plus implicit randomness in *"patrols its spawn room"* and *"orbits
at 3–10 cells"*.

For a build that runs overnight with no human watching, the replay-golden harness **is** the
acceptance criterion, and it is absent from the design and from §18's scope ladder.

**Fix:** one named LCG seeded from the level header, all AI randomness drawn from it, sim state
hashed per tick, and "record a 600-tick input trace on level 1 and pin its hash" added to the
first playable.

### 25. SHOULD-FIX — The first playable has no defined ending

§18's list ends at *"HUD, title screen, death and retry"*. The results screen is **last** in the
*"Then, in order"* queue. So: what happens when the player enters `>` on level 2? Undefined. What
happens at 100% trace, when *"the sealed entry gate (variant 21) opens"* and a **Hunter** spawns —
both explicitly deferred? Undefined. Per finding 12, level 1 at NOMINAL reaches 100% in 250 s,
which a first-time player will absolutely do.

**Fix:** add to the first playable (a) a "SECTOR CLEAR — time / par" text overlay, (b) a "RUN
COMPLETE" screen after level 2, (c) a placeholder 100% behaviour: HARDENED palette + immediate
`CONNECTION TERMINATED`, same path as death.

### 26. SHOULD-FIX — The first playable has no hit or pickup feedback at all

§18: *"YM audio only; no DMA samples."* The only damage feedback specified anywhere is an HUD
number, and the only pickup feedback is §10's *"Sound | token grab"* — a DMA sample that does not
exist yet. §15's dissolve is for death, not damage.

**Fix, and it is nearly free:** a 2-frame full-screen flash — one palette write swapping the ramp
toward register 14 `#FF4400` on damage and toward 13 `#FFFFFF` on pickup. Two palette writes and a
counter. This is the single largest feel-per-byte item on the list.

### 27. SHOULD-FIX — `tools/mklevel.py` is a prerequisite and is not in the scope ladder

§11: *"levels are ASCII text in `levels/*.txt`, compiled by `tools/mklevel.py`"*, and the binary is
*"produced by the compiler — never hand-written"*. §18 never mentions it. It gates both first-
playable levels and carries eight validation rules (one of which is wrong — finding 6).

**Fix:** put the compiler at the head of the first-playable list, and ship its validator as unit
tests over the two maps.

### 28. SHOULD-FIX — §17's single 480,000-cycle column cannot serve the BRIEF's two frame-rate targets

`BRIEF.md`: *">= 14 fps at 160 columns, >= 20 fps at 80 columns"*. That is **571,000** cycles and
**400,000** cycles per frame respectively. §17's table has one column: *"Total vs 480,000 (3
VBLs)"* — too generous for the 80-column target and too tight for the 160-column one.

**Fix:** two budget columns, 400,000 (80 col, 2 VBLs… strictly 2.5) and 571,000 (160 col), and say
which VBL count each mode locks to. Frame-flip cadence matters: 2 VBLs = 25 fps, 3 = 16.7, 4 =
12.5. There is no 20 fps on a 50 Hz PAL flip lock, so *"≥ 20 fps at 80 columns"* means locking to
**2 VBLs / 25 fps** — which halves the budget to 320,000, not 400,000.

### 29. SHOULD-FIX — OVERCLOCK's stated payoff is not visible at 20 cells

§5: *"OVERCLOCK — you see the whole room, **Sentry iris state is readable at range**, tokens ping
on the HUD compass at 20 cells"*.

In an 80-line window, an object at 20 cells is **4 chunky pixels tall** (8 screen pixels after
doubling). An iris is not readable on a 4×4 sprite, and a 32×32 source frame downsampled 8× will
alias to noise.

**Fix:** either drop the iris claim and sell OVERCLOCK on the compass + Spike range alone, or give
the Sentry a **1-pixel state light** in register 14/12 that survives downsampling — one pixel,
readable at any range because it is a colour, not a shape.

### 30. SHOULD-FIX — 32×32 sprite source is under-resolved for the window

§17: *"Sprite frames | 33 x 32x32 x 3 shade variants"*. At 1.0 cells a wall-height enemy fills the
80-line window, so a 32-px source is upscaled **2.5×** and then pixel-doubled **2×** — a **5×5
screen-pixel block** per source texel on the enemy you are shooting. At 0.6 cells (contact range,
§8) it is worse.

**Fix:** either author enemies at 48×48 (33 × 48 × 48 × 3 = 228,096 B, +126,720 — affordable only
if finding 15 is also solved) or accept it explicitly and design silhouettes that read at 5×5
blocks. Decide before art, not after — this is exactly `CRITIQUE.md` item (d).

### 31. SHOULD-FIX — Level 1 does not deliver the lesson §12 says it teaches

§12: *"the four Watchdogs teach you that packs come down corridors"*, *"the east kennel holds the
pack"*. §8: *"Pack size | 4"* and ALERT *"wakes its pack within 6 cells"*.

The map's Watchdogs are at **(22,14), (24,19), (27,20), (4,21)**. (4,21) is ~20 cells from the
others, on the far side of the map; (22,14) is in the Bus Hall, 5+ cells from the kennel pair.
Under the 6-cell wake rule the largest group that can ever activate together is **two** —
(24,19)+(27,20). The level teaches "dogs come at you one at a time".

**Fix:** move (4,21) → about (25,21) and (22,14) → about (26,17) so all four sit inside one 6-cell
wake radius in the east kennel, and let them come out through the row-16 gap at cols 25–26 as a
line. Replace the west room's dog with the `i` pickup guard role it currently plays.

### 32. SHOULD-FIX — Joystick-only players cannot pause or abort

§15: *"**Pause** — `P` only (keyboard)."* §6 sells the stick as *"complete on its own"*.

**Fix:** Fire + Up + Down (or a 2-second all-directions-neutral fire hold) opens the pause overlay,
or accept the contradiction and stop claiming joystick completeness.

---

## NITS

33. **NIT** — Front matter: *"Every cycle figure in **§16** is therefore TBD"*. §16 is Audio; the
    cycle table is **§17**.
34. **NIT** — Sample bank: 8.0 s × 12,517 Hz = **100,136 B**; the ledger books **100,352** (98 KiB).
    216 bytes; say "98 KiB" or fix the seconds.
35. **NIT** — §13: *"the stack's aisles are **four cells wide**"*. Measured: glyph columns sit at
    x = 7, 11, 15, 19, 23 and y = 6, 9, 12, 15, so the aisles are **3 cells wide and 2 cells tall**.
    The lattice is also not centred — there is a clear 4-wide unobstructed margin at x = 24–27 that
    a Watchdog line will simply run down, defeating the room's premise.
36. **NIT** — Level 1's exit `>` (15,2) opens into a 4-cell pocket (14,1)–(17,1) that is reachable
    only by ending the level, with dead ends at **(14,1)** and **(17,1)**. Pure dead geometry the
    renderer will draw through the open door.
37. **NIT** — Level 2 dead-end cells at **(25,2)** and **(28,2)** in the exit alcove. Harmless (no
    enemy spawns there) but they are the exact 1-cell pockets a stalled chase AI will die in once
    finding 8 is fixed with a wall-hug.
38. **NIT** — Cyan ramp steps are 35 / 52 / 56 / 57 luminance. Bands 1→2 are 35% closer together
    than the rest, and §9's 25% threshold *"cyan ramp desaturates one step"* compresses them
    further. Re-space toward 240 / 195 / 150 / 100 / 45.
39. **NIT** — Both level headers say *"facing north"* but the brad-to-compass mapping (which brad
    value is north, and whether +y is south) is never stated. One sentence in §11.
40. **NIT** — §6's keyboard *"7 / 8 / 9 | set clock throttle directly"* — unstated whether §5's
    *"12 ticks (0.48 s) of locked input"* applies to the direct keys. It must, or the keyboard is
    strictly better than the stick.
41. **NIT** — §17 disk: *"8 compiled levels (≤ 4.6 KB each)"*. A 48×48 level computes to header 38 +
    2,304 cells + 320 entities ≈ **2.7 KB**.
42. **NIT** — §2 describes the Ledger Stack as *"watched from the north wall"* (singular); §13 and
    the map have **two** Sentries, at (15,3) north and (3,10) west.
43. **NIT** — §6 specifies the joystick in full but never names the BRIEF's paid-for IKBD boot
    sequence (*"send $12 (mouse off) and $14 (joystick event reporting) at boot, or fire lands in
    the mouse packet"*). Cheap insurance to name it where the controls live.

---

## What I would change in the first playable

Ship less of it and make what ships have a verb. Drop the title screen, drop the 75% and 100%
palette thresholds (they collide with the readability contract — finding 11 — and 100% has no
defined behaviour without the Hunter), and re-author level 2 or open door 18 so it actually runs
(finding 1). Spend what that frees on the four things that decide whether the build is a game or a
tech demo: a chase AI that gets round a corner (finding 8), a Sentry that can be drawn (finding 4),
a door plane that is specified (finding 5), and two palette writes of damage/pickup flash (finding
26) so hits register at all. Add a "SECTOR CLEAR — time / par" overlay so the thing has an ending,
and pin one recorded input replay hash so the overnight build can tell you it still works.

Then the **one addition**, and it is not a new enemy: **bring the clock throttle forward, in its
UNDERCLOCK↔NOMINAL two-state form, columns locked at 80 for both.** It costs no art, no sprites and
no second renderer — it is a render-radius clamp (6 vs 12 cells) and four multipliers that §5
already tabulates (speed 1.25/1.0, enemy sight 0.5/1.0, trace 0.5/1.0). It is worth more than any
third enemy because it answers the honest question in the brief: a straight-walking melee dog and a
static turret are *not* fun on their own — back-pedal-and-tap beats the dog, and hugging the
mounting wall at >45° puts you outside the Sentry's 90° cone forever, after which it is scenery.
What makes them fun is a decision the player makes *about* them: underclock to slip past the
turret blind and fast, at the price of a 6-cell world where a pack can be on you before it is
drawn; or nominal, and fight. That single toggle turns the trace meter from a countdown into a
resource, gives the Sentry a counterplay that isn't an exploit, exercises both render radii on
night one, and it is the only idea in this document that the fourth-best Tron game does not
already have.
