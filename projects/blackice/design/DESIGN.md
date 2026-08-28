# BLACK ICE — Game Design Document

**Version: 2** (supersedes v1). Binding for implementation. Supersedes the BLACK ICE section of
`CONCEPTS.md`. All 8 BLOCKERs, 24 SHOULD-FIXes and 11 NITs raised in `DESIGN_REVIEW.md` are
resolved below; each resolution is listed in §19. Constraints come from `BRIEF.md` and are not
renegotiated here.

**The palette is the art pass's, not this document's.** `art/ART_DIRECTION.md` §3 holds the final
16 registers and **wins over any colour this document previously specified**; §3 below is a
restatement of it, and every register index in this document is the art pass's numbering. The
screen layout in `art/ART_DIRECTION.md` §5 and the HUD strip it describes are likewise the shipped
ones (§15.1, §17). Where the two documents disagree on colour, indices, contrast gates or HUD
geometry, `ART_DIRECTION.md` is the authority and this document is the defect.

**Unmeasured numbers.** The renderer spike (`scratchpad/spike/REPORT.md`) has not run. Every cycle
figure in **§17** is therefore **TBD — measured by the spike**. No cycle number in this document is
an estimate dressed as a measurement. RAM, projection, palette and trace figures *are* arithmetic
and are committed.

---

## 1. Pitch and tone

> *Break into a dying mainframe, strip it for data, and get out before the trace finds your body.*

You are a repossession runner. HALCYON is a Frayne-Bellamy HX-9 mainframe on Ossuary Row that has
been failing for eleven months, and its owners have stopped paying for it. You walk its memory map
as physical space, take what is still worth taking, and leave before the trace resolves your
physical address.

Tone: the mission text is dry corporate deadpan — a repossession order, an asset schedule, a
collections notice. The world itself is cold, silent and geometric. The joke is never in the world;
the world is played absolutely straight.

**The machine is dying, and that is the visual premise.** A healthy sector renders as clean
architecture. A failing sector renders wrong: the geometry itself is the symptom.

---

## 2. HALCYON — the named world

Eight sectors, addressed the way the machine addresses them. Each is a *place* with one landmark
room that a player can describe to another player from memory.

| # | Sector | What it was | Landmark room | Health |
|---|---|---|---|---|
| 0 | **INGRESS** | boot ROM and the cold-start gate | **The Cold Boot Gate** — the arch you come in through, and the only way out at 100% trace | CLEAN |
| 1 | **THE LEDGER** | the account store | **The Ledger Stack** — a hall of twenty-four glyph columns you weave through, watched from two recessed alcoves | CLEAN |
| 2 | **NURSERY** | the process spawner | **The Fork Ring** — a circular hall with eight identical spurs, seven of them dead | DEGRADED |
| 3 | **BAD BLOCK** | a failed page frame | **The Shear** — where the sector was written twice and the two copies do not line up | CORRUPT |
| 4 | **THE CHOIR** | the telecom exchange | **The Switchboard** — a two-storey-looking wall of dead lines (faked with texture, not geometry) | DEGRADED |
| 5 | **DEAD LETTER** | the mail spool | **The Undeliverable** — the same room stamped four times because the page is read back from one bad frame | CORRUPT |
| 6 | **COLD STORE** | the tape archive | **The Carousel** — a ring of tape bays around a central well | DEGRADED |
| 7 | **THE KERNEL** | the supervisor core | **The Anchor Chamber** — four pylons, and the thing that lives between them | CORRUPT (terminal) |

### How corruption shows — five devices, zero renderer cost

Every one of these is authoring or a palette word. None needs a new renderer feature.

1. **Grid drift.** A corrupted room is authored one cell off its corridor. Corridors mis-join and
   leave 1-cell dead stubs. It reads as geometry that did not survive a write.
2. **Texture mismatch.** Adjacent cells of the same wall run carry different texture ids — lattice,
   lattice, hex mesh, lattice. The corrupted-noise texture (id 6) appears in patches.
3. **Jammed doors.** Door variant 22 never opens and carries its own cracked texture: a doorway
   you can identify as a doorway and can never pass. (v1 renders doors 2-state, §10, so the door
   is opaque; the see-through slit arrives with the slide-offset polish, not before.)
4. **Repeated stamps.** DEAD LETTER stamps one 9x9 room four times with only the entity list
   differing. Deliberate, and named in the level's own text.
5. **Palette variant.** Header field `palette_variant`: 0 CLEAN, 1 DEGRADED, 2 CORRUPT, 3 KERNEL.
   **A variant may only touch the two wall ramps, registers 1–10** (§3) — one 16-word table swap
   that can never break the readability contract, because the registers the contrast gates bind on
   are outside it. `ART_DIRECTION.md` §2 rule 6 adds the same idea in texture space: *wrong ramp*,
   a band of a texture decoded through the magenta ramp so the cyan is simply not there.

---

## 3. Colour contract

**Owned by `art/ART_DIRECTION.md` §3.** 16 registers, fixed for the whole game, every channel a
multiple of `0x11` so nothing quantises. `palette.ste_colour_word` does the STE `$0RGB`
low-bit-is-MSB swizzle — never hand-encode it. Y = 0.299R + 0.587G + 0.114B on the 8-bit expansion;
every Y below is reproduced from `python palette.py`.

| Idx | Hex | STE | Y | Role | Walls may use |
|---:|---|---|--:|---|---|
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
| 12 | `#FFFFFF` | `$FFF` | 255.0 | **rim-light, muzzle flash, HUD text** | **NO — RESERVED** |
| 13 | `#FF7722` | `$FB1` | 150.0 | **enemy core / Sentry iris / trace danger** | **NO — RESERVED** |
| 14 | `#33CC66` | `$963` | 146.6 | integrity green — health, exit lamps, satisfied locks | yes |
| 15 | `#333355` | `$99A` | 54.9 | slate — structural shadow, HUD trim, **sprite transparency key** | yes |

**Exactly two registers are reserved: 12 (white) and 13 (orange).** Walls may not use those two and
may use every other register. Two *accents*, not five — which is what lets `circuit_lattice` have
live yellow vias, the door have hazard bands, and `exit_gate` be green. **Register 15 is legal in
walls and in the HUD as a colour, but it is the sprite transparency key**, so no sprite may use it
as a colour; a sprite's 15s are holes. Sprite shading must go through `drawlib.shade_sprite`, which
preserves the key — a plain `shade` would fog index 15 to void at band 3 and paint a far enemy's
transparent pixels black.

**The magenta-on-magenta hole is closed by the rim, not by taking magenta away from the walls.**
Both ramps are wall-legal and they interleave in luminance rather than being luminance twins:
cyan 199.3 / magenta 183.2 / cyan 162.1 / magenta 139.2 / cyan 123.2 / magenta 105.2 / cyan 80.5 /
magenta 64.2 / cyan 46.6 / magenta 23.0.

### The palette gate — measured thresholds, not a paragraph

Two committed harnesses run in the art pipeline (`make`, or `python build_art.py`) before any frame
ships, and **refuse the build** on failure. These thresholds replace the design's earlier ΔY ≥ 40
rule, which was written against a palette that no longer exists:

1. **`rimtest.py` — the rim gate. Threshold ≥ 24 Y.** It composites every rimmed sprite over every
   wall texture at every depth band — 8 × 10 × 5 = **400 combinations** — finds the wall pixels
   each rim pixel actually borders, and requires at least 24 Y between white (12) and all of them.
   **Failures: 0. Worst margin anywhere: 31.3 Y**, against a data-yellow via in `circuit_lattice`
   or `exit_gate` at band 0. **Worst margin with the rim deleted: 0.0 Y** — some sprite edge
   colours are *identical* to the wall colour they border. That 0.0 is the size of the hole the rim
   closes, measured rather than asserted, and it is why the 1-pixel white rim on every silhouette
   edge is non-negotiable.
2. **`palette.py` — the ramp gate. Threshold ≥ 16 Y and ≥ 40 chroma.** Minimum luminance gap
   between any cyan rung and any magenta rung, **in every depth band**: **16.0 Y**. Minimum chroma
   distance in the (Cb, Cr) plane: **41.5**. Infrastructure never reads as ICE at any distance.

White's headroom over the brightest colour a wall is allowed to contain — data yellow at
Y 223.7 — is **31.3 Y**, and that single number is why the rim works.

**What an enemy is made of:** the magenta ramp (6–10) for the body, register **13** for the live
core and the Sentry iris, register **11** or **14** for a data or integrity accent, register **15**
for the transparent surround, and a mandatory **1-pixel register-12 rim on every silhouette edge**.
Pickups follow the same rule and are covered by the same harness.

### The variant invariant

`palette_variant` and the trace thresholds (§9) may recolour **only registers 1–10, the two wall
ramps**. Registers 0, 11, 12, 13, 14 and 15 are identical in every variant. That is the whole
invariant, and it has three consequences worth stating:

- The rim gate's binding case is **data yellow (11)**, which no variant touches, so the **31.3 Y
  worst margin holds across all four variants by construction**.
- Register 15 keeps its value, so the sprite transparency key is never disturbed.
- Both harnesses are still run per variant — invariance is the reason they pass, not an excuse to
  skip them.

| Variant | What it loads into 1–10 |
|---|---|
| 0 CLEAN | the table above |
| 1 DEGRADED | registers 1–5 take the cyan mapping of `palette.shade_table(1)` — one rung darker, no new hex values at all |
| 2 CORRUPT | registers 1–5 take the **magenta** ramp's values (6–10): the infrastructure itself reads hostile, and the rim is what still separates ICE from wall |
| 3 KERNEL | a blue-white desaturation of the cyan ramp, authored by the art pass under both gates. This document states the constraint and does not hand-author the hexes |

**One honest gap.** Reserved orange (13, Y 150.0) sits 3.3 Y from wall-legal green (14, Y 146.6):
an enemy core against a green wall pixel is chroma-only. It is guaranteed by the white rim that
encloses the core, and green wall use is confined to exit lamps and satisfied locks, so the
adjacency is rare — but it is an argument, not a measurement, and `rimtest.py` does not cover it.

### Depth shading — an index remap, baked at load

Distance fog is a **table remap, never a new colour**: `palette.shade_table(band)` returns 16
entries and the shading term is `band = min(distance / BAND + is_north_south_face, 4)` — one add.
Band 3 is the two darkest rungs of each ramp; band 4 is the darkest rung and then void, so
far-clipping is diegetic. **Registers 12 and 13 never fog** — a rim-light that fades stops being a
guarantee, and a far enemy's live core is exactly the thing you must still see. Emissive accents
(11, 14) hold for three bands and then go to slate and void.

The renderer does not pay for the lookup: the loader applies `shade_table` once per band to produce
the baked bands in §17.4, so the inner loop stays a single fetch per texel. One authoring
consequence, from `ART_DIRECTION.md` §8: **green dies at band 3**, so an `exit_gate` past about 9
cells is not green — level design places exit gates inside band 2 or the landmark stops being one.

---

## 4. The player

Sim runs at a **fixed 25 Hz** (one tick per 2 VBLs) regardless of render rate. All numbers below
are per tick. Sim/render concurrency, input latching and determinism are specified in §4.1–§4.3.

| Property | Value |
|---|---|
| Position | 16.16 fixed point, 1.0 = one grid cell |
| Angle | 1024 brads = 360° (0.352°/unit); one 1024-entry sin/cos table |
| Forward speed | 0.150 cells/tick = 3.75 cells/s |
| Backward speed | 0.090 cells/tick = 2.25 cells/s |
| Strafe speed | 0.110 cells/tick = 2.75 cells/s |
| Turn rate | 24 brads/tick = 8.44°/tick = **211°/s** |
| Collision radius | 0.28 cells, axis-separated (test X, then Y — you slide along walls) |
| Integrity | 0–100. Starts 100. Carries between sectors; +25 (capped 100) at each sector start |
| Cycles (ammo) | 0–200. Starts 60 |
| Tokens | ALPHA / BETA / GAMMA, per-sector, discarded at the exit gate |
| Scrubbers | consumed on pickup: instant −20% trace. No inventory, no use button |

All speeds are scaled by the clock throttle (§5).

### 4.1 Sim/render concurrency — decided

The main loop is a **catch-up loop**, never a VBL-driven sim:

```
loop: while (vbl_counter - last_tick_vbl >= 2) { sim_tick(); last_tick_vbl += 2; }   /* 1–2 ticks */
      snapshot_render_state();      /* 64 entities x 8 B = 512 B, single copy */
      render_frame();               /* reads only the snapshot + the level grid */
      flip_on_next_locked_vbl();
```

The renderer never observes a half-applied tick. The snapshot is taken once per frame, before the
DDA, and holds position, angle, type, frame index, state and distance for each live entity.

### 4.2 Input latching — mandatory

A 3-VBL render period against a 2-VBL tick means ticks arrive 1-2-1-2 with ±1 VBL of jitter, so a
press-and-release inside one render period would be lost. The VBL ISR therefore latches, per input:
a sticky `pressed_since_last_tick`, a sticky `released_since_last_tick`, and a monotone
`held_vbls` counter. `sim_tick()` consumes and clears them. Fire is edge-triggered off the sticky
press, so a shot can never be dropped or doubled by render jitter — and this latch is the
prerequisite for the replay harness (§4.3).

### 4.3 Determinism contract

`BRIEF.md` makes replay-golden hashes the test suite, so the design names the mechanism:

- **One RNG:** a named 32-bit LCG (`rng_state = rng_state * 1664525 + 1013904223`), seeded from
  `level.rng_seed` in the level header. **All** AI randomness — Black ICE anchor choice, Tracer
  patrol targets, orbit jitter — draws from it and nothing else. No `rand()`, no VBL counter, no
  uninitialised memory.
- **Per-tick state hash:** FNV-1a over the packed player state + the live entity array + door
  states + trace, computed at the end of every `sim_tick()`.
- **Pinned goldens:** a recorded 600-tick input trace on level 1 and a 900-tick trace on level 2,
  each with its final hash and a per-100-tick checkpoint list, live in `test/` and gate every
  commit. This is the surface that catches a sim regression on an overnight build.

---

## 5. The clock throttle — one number, three effects

You underclock or overclock your interface. The render radius, your visibility to the ICE, and your
trace rate are **the same number**.

**The throttle does not choose the column count.** Detail level (160 vs 80 columns) is a separate
global setting owned by the perf gate and the options screen (§17). Tying them was v1's error: the
column count changes a fixed cost the throttle cannot touch.

| Level | Name | Render radius | Speed × | Enemy sight × | Trace rise × | In first playable |
|---|---|---|--:|--:|--:|---|
| 1 | **UNDERCLOCK** | 6 cells / 3 bands | 1.25 | 0.5 | 0.5 | **yes** |
| 2 | **NOMINAL** | 12 cells / 5 bands | 1.00 | 1.0 | 1.0 | **yes** |
| 3 | **OVERCLOCK** | 20 cells / 5 bands + far fill | 0.80 | 1.5 | 1.6 | no — arrives with 160-column mode |

**What each costs and gives, concretely:**

- **UNDERCLOCK** — you move fastest, you are hardest to see, and the trace crawls. The cost is real
  and it bites: enemies beyond 6 cells are **not drawn at all**. A Sentry at 9 cells will hitscan
  you out of an empty black corridor. Spike's range is the render radius, so your best weapon is
  nearly useless. Standing still at UNDERCLOCK is the only thing in the game that *lowers* trace
  passively: base 0.18 × 0.5 = +0.09 %/s against a −0.20 %/s credit = **net −0.11 %/s**.
  The frame-rate gain is real but **partial and honest**: the radius clamp cuts DDA far-fill,
  far-wall texel fetch and far-sprite work; it does not touch the fixed c2p cost (§17).
- **NOMINAL** — the default. Nothing special.
- **OVERCLOCK** — you see the whole room, tokens ping on the HUD compass at 20 cells, and Spike
  reaches 20 cells. The cost: enemies see you 50% further, the trace climbs 1.6×, you move 20%
  slower, and it carries the worst frame rate in the game.
  *Sentry state at range is a **colour**, not a shape*: at 20 cells a 1-cell billboard is 3.2
  chunky rows tall (§17.1), so the Sentry carries a **1-pixel state light** — register 14
  (integrity green) when the iris is closed, register 13 (orange, the reserved live-and-hostile
  accent) when it is charging or open. Neither register fogs (§3), so one pixel survives any
  distance and any downsampling.

**How it is shown:** a three-segment dial on the HUD; the horizon grid line is drawn in register 15
(slate) at UNDERCLOCK and NOMINAL and in register 13 `#FF7722` at OVERCLOCK — the line changes
*register*, never register 15's value, so the sprite transparency key is untouched; and the
far-fill boundary visibly moves.

The throttle is a *route* decision, not a combat toggle: underclock to move, nominal to fight,
overclock to find. Changing it costs 12 ticks (0.48 s) of locked input — **including** the direct
keys 7/8/9, so the keyboard is never mechanically better than the stick.

---

## 6. Controls

**There is no modifier layer.** v1's "hold fire, then direction" scheme bound strafe and weapon
swap to the two most common inputs in the game; it is deleted.

**Joystick port 1 (IKBD).** At boot the platform seam sends IKBD `$12` (mouse off) and `$14`
(joystick event reporting), per `BRIEF.md` — without both, fire lands in the mouse packet.

| Input | Action |
|---|---|
| Up / Down | walk forward / back |
| Left / Right | turn left / right |
| Left / Right **while Alt or Shift is held** | strafe left / right |
| Fire | shoot. Edge-triggered on press; **holding fire auto-repeats at the current weapon's rate of fire** (Buster 5 ticks, Spike 20 ticks) |

**Keyboard (always live alongside the stick):**

| Key | Action |
|---|---|
| ↑ / ↓ | forward / back |
| ← / → | turn |
| **Alt** or **Shift** (held) | turn becomes strafe — on the arrow keys *and* on the joystick |
| Z / X | strafe left / right |
| Space or Ctrl | fire |
| 1 / 2 | select Buster / Spike |
| 7 / 8 / 9 | set clock throttle directly to 1 / 2 / 3 (12-tick input lock, as §5) |
| P | pause |
| Esc | abort run (confirm) |

**The game is completable with joystick + Alt.** Alt held on the keyboard converts joystick
left/right into strafe — the standard ST convention — so circle-strafing is available with one
finger on one key and never costs a shot, a cycle, or a noise alert. The design **does not claim
stick-only completeness**: pause (P), abort (Esc), weapon select (1/2) and the throttle (7/8/9) are
keyboard-only, and a keyboard is in reach because Alt already is.

**Doors need no button.** Walking into a door cell opens it (§10). A locked door opens on contact
if you carry its token, otherwise it bump-refuses: a HUD line naming the token it wants, plus a
refusal tone. There is no use key and there are no switches — see §10.

---

## 7. Weapons

**Both weapons are hitscan. A decision, not an omission:** a projectile is a sprite, sprites are the
scarcest per-frame resource (§8), and a weapon that eats the budget you need for enemies makes the
game worse exactly when it matters. Feedback is a two-frame register-12 `#FFFFFF` muzzle flash plus a
hit spark, both budgeted as sprites of last priority.

| | **Buster** | **Spike** |
|---|---|---|
| Damage | 8 (4 beyond 8 cells) | 30 first target, then 20 / 14 / 10 |
| Rate | 5 ticks (0.20 s) | 20 ticks (0.80 s) |
| Range | 12 cells | = current render radius (6 / 12 / 20) |
| Cost | 1 cycle | 5 cycles |
| Type | hitscan, single target | hitscan, pierces up to 4 |
| Floor | at 0 cycles it still fires: 3 damage, 10-tick rate ("brownout") | unusable at < 5 cycles |

**How Spike pierces on the grid.** The shot walks the *same DDA the renderer uses*, from the player
along the current facing, cell by cell, until it hits a wall cell or a non-OPEN door or reaches
range. Each entity registers itself in **every cell its collision disc overlaps** (a 0.3-cell disc
touches at most 4 cells), so a body straddling a cell boundary is never walked past; hits are
de-duplicated by entity id during the walk. Damage falls 30 → 20 → 14 → 10 and stops after four.
This is why corridors are the tactical unit of the game: line them up.

---

## 8. Enemies

Sight rule, uniform: **grid line-of-sight** (a DDA cell walk from enemy to player that hits no wall
cell and no non-OPEN door) **AND** the player inside the enemy's facing cone **AND** within
`base_sight × throttle_emission` (0.5 / 1.0 / 1.5). Firing a weapon within an enemy's noise radius
alerts it regardless of cone.

| | **Watchdog** | **Sentry** | **Tracer** | **Black ICE** |
|---|---|---|---|---|
| HP | 20 | 35 | 25 | invulnerable (4 anchors, 60 HP each) |
| Speed | 0.18 c/tick | static (alcove-mounted) | 0.24 c/tick | mirrors the player's speed |
| Damage | 12 melee, contact ≤ 0.6 cells | 8 hitscan | 10 ranged | 25 contact / 15 sweep |
| Attack rate | 25 ticks | 12 ticks while iris open | 30 ticks | 40 ticks |
| Base sight | 8 cells, 120° cone | 14 cells, 90° cone | 12 cells, 150° cone | whole room |
| Noise radius | 5 cells | 8 cells | 10 cells | — |
| Pack size | 4 | 1 (never packs) | 2 | 1 |
| Sound cue | snarl on ALERT | charge whine on iris open | ping on ALERT, siren on FLEE | siren on teleport |
| Sprite frames | 5 | 3 | 5 | 6 (+3 shared anchor frames) |

**The Sentry is a floor entity, not a wall.** It stands in a **1-cell alcove recessed into a wall**
— three wall neighbours, one open side — and is drawn as an ordinary billboard against the alcove's
back wall. It never occupies a wall cell, so the sprite pass's column clip against the wall depth
array never discards it, and there is no depth bias and no z-fighting on the flank. The compiler
enforces the alcove shape (§11). The **anchor** (`*`) is the same class of object: a free-standing
floor entity with a **0.4-cell solid collision disc**, never a wall cell.

**Sprite frames, counted exactly.** Front view only — no rotation set. Watchdog: walk A, walk B,
attack, dissolve 1, dissolve 2 = **5**. Sentry: iris closed, iris open (also the attack frame),
destroyed = **3**. Tracer: walk A, walk B, attack, dissolve 1, dissolve 2 = **5** (FLEE reuses the
walk pair). Black ICE: idle A, idle B, attack, teleport flash, dissolve 1, dissolve 2 = **6**.
Anchor: intact, cracked, broken = **3**. Enemy/anchor total **22**, authored at **64×64**. Plus 9
pickup frames and 2 hit-spark frames = **11** authored at **32×32**. **33 sprite frames** in all.
*(Art-pass status, from `ART_DIRECTION.md` §8: the shipped pass delivers **one pose per enemy** and
no walk, attack or dissolve frames. That is outstanding art work against this spec, not a change to
it; the RAM ledger books all 33. It also delivers one view per enemy, so a strafing Tracer slides
sideways facing you — accepted, because a side view doubles the enemy budget.)*

### 8.1 Navigation — one BFS distance field

There is no straight-line chase rule. v1's "straight-line grid walk, re-path at cell centres" jams
on the first outer corner of every `######` block in both shipped maps, and the first playable's
whole AI rests on it.

- **The field.** A breadth-first flood from the player's cell over the walkable grid (4-neighbour;
  a non-OPEN door is a wall). **One byte per cell**, value = cell distance in steps, **radius
  limited to 20 cells**, `255` = out of range or unreachable. 48×48 = 2,304 B resident.
- **Cadence.** Recomputed **every 8 sim ticks** (3.125 Hz). Worst case visits ≤ π·20² ≈ 1,257 cells
  from a ring-buffer queue; amortised over 8 ticks this is the cheapest AI in the design. Cycle
  cost TBD by the spike, budgeted in §17's sim row.
- **Movement (Wolf3D style).** An enemy at a cell centre picks the neighbour with the **lowest
  field value** — best of 8, with a corner check (a diagonal is legal only if both orthogonal
  neighbours are open) — and **commits** to it, moving at its speed until it reaches that cell's
  centre. It re-picks only on arrival. Because the field is a true BFS, the chosen neighbour always
  exists and always reduces distance: **this cannot jam.** A stale field (up to 8 ticks / 0.32 s
  old) at worst makes an enemy overshoot by one cell.
- **Tracer** uses the same field, with a different objective: it prefers cells whose field value is
  **3–5 with line of sight** to the player, holding that ring and firing. **Strafing** is choosing
  the lateral neighbour — the legal neighbour most perpendicular to the player bearing — when the
  ring value is already satisfied. On FLEE it **ascends** the gradient (highest neighbour value)
  toward the sector edge.

### State machines

| State | Watchdog | Sentry | Tracer | Black ICE |
|---|---|---|---|---|
| IDLE | still; → ALERT on sight/noise | iris closed, invulnerable; → ALERT on sight | patrols its spawn room; → ALERT on sight/noise | dormant at anchor 0 until the player enters the chamber |
| ALERT | 8-tick tell + snarl → CHASE; wakes its pack within 6 cells | 20-tick charge whine → ATTACK | 8-tick tell + ping → CHASE | 20-tick rise → CHASE |
| CHASE | descends the distance field (§8.1) | n/a | holds field range 3–5 with LOS, strafing | mirrors the player's movement across the room's long axis |
| ATTACK | contact damage, then 25-tick cooldown → CHASE | iris open 30 ticks (vulnerable), fires every 12; then closed 40 ticks | fires at range, holds the ring | sweep at contact; teleports to a random other anchor every 90 ticks |
| FLEE | never | never | at HP < 40%: ascends the field to the nearest sector-edge cell. Arriving = **+15% trace** and it despawns | never |
| DEAD | 2-frame dissolve, 12 ticks, then removed | destroyed frame stays as scenery | 2-frame dissolve; killed before fleeing = **−8% trace** | when all 4 anchors are broken, it dissolves and the sector ends |

**Enemies and doors.** Watchdogs and Tracers in ALERT, CHASE or FLEE open variant 16 by contact,
using the identical predicate the player uses. Locked variants 17–19 and jammed 22 stay shut to
them. This closes the free-invulnerability cheese: you cannot retreat two cells through a plain
door and wait out a melee-only roster.

### 8.2 The per-frame sprite-pixel budget

Counting sprites is wrong — cost scales with on-screen *area*. The engine budgets **destination
chunky pixels**, `SPR_PX_BUDGET` (value TBD from the spike; provisionally **6,000** at 160 columns,
**3,000** at 80).

**What counts.** A sprite's contribution is the pixels it would actually write: **after** clipping
its projected rectangle to the 160×80 render window, and **after** the per-column depth test
against the wall depth array. A dog behind a wall costs nothing; a dog filling the window costs the
window.

Each frame:
1. Project every live entity from the render snapshot (§4.1); discard those beyond the render
   radius, fully off-window, or fully occluded.
2. Sort by distance, ascending.
3. **The nearest attacker is exempt** — the closest entity in ATTACK, or if none is attacking, the
   closest entity — and is always drawn. Every other entity is admitted in ascending-distance order
   while the accumulator stays under `SPR_PX_BUDGET`; the rest are **dropped farthest-first** for
   this frame (not this tick — the sim is unaffected; only the drawing is).
4. Draw the survivors back-to-front, column-clipped against the wall depth array.

**The budget is now bounded, and here is the bound.** The exempt sprite is itself window-clipped,
so it can cost at most 160 × 80 = **12,800** chunky pixels. Worst-case sprite cost per frame is
therefore `12,800 + SPR_PX_BUDGET` = **18,800** at 160 columns. In the real case that motivated the
rule — a four-Watchdog pack at contact range, 0.6 cells — the exempt dog projects 107 × 107 and
clips to **107 × 80 = 8,560 px**; the other three are admitted against the 6,000 budget and the
farthest of them may flicker out for a frame. **That flicker is the documented failure mode**, and
it is the correct thing to lose: the dog eating you is always drawn.

Consequence for authoring: pack sizes are a *design* limit, not a render limit.

---

## 9. The trace meter

0–100%, per sector.

**Start value — one rule, one authority.** `trace_carry_cap` in the level header is the single
authority; `trace_start` is the level's floor:

```
start = min(level.trace_carry_cap,
            level.trace_start + 5 * sectors_finished_over_par + 10 * deaths_this_sector)
```

`trace_carry_cap` ships at **25** on every level, so no amount of over-par running or dying can
start you above 25% — death stays a cost and never becomes a wall.

**Rise** (all scaled by the throttle multiplier 0.5 / 1.0 / 1.6):

| Event | Trace |
|---|---|
| Base, per second | `trace_base_rate` — **+0.18 %/s** on every shipped level |
| While any enemy has LOS on you | +0.6 %/s (additive) |
| Firing within an unalerted enemy's noise radius | +2 % |
| Opening a locked door — **once per door per sector** | +3 % |
| Taking a hit | +1 % |
| A Tracer reaching a sector edge | +15 % |

**Fall:** scrubber pickup −20% (consumed instantly), Tracer killed before it flees −8%, Sentry
destroyed −5%, standing still at UNDERCLOCK −0.20 %/s (net −0.11 %/s, see §5).

### 9.1 The reference run — how `trace_base_rate` was tuned

v1's flat +0.4 %/s drove every level from 5 on to HARDENED at par pace with zero enemy contact,
which made §14's par times unachievable by construction. The tuning target is: **a player at par
pace with average contact finishes levels 5–8 near 70%, not 100%.**

*Reference run, per level:* finishes exactly at par · under enemy LOS for **20% of par** (average
+0.12 %/s) · opens every locked door once (+3 each) · fires within an unalerted enemy's noise
radius **3 times** (+6) · takes **4 hits** (+4) · kills **half** the level's Tracers before they
flee (−8 each) · collects no scrubber (a scrubber is the player's lever, not the baseline) ·
carry = 0, because at par pace `sectors_finished_over_par` = 0.

| Level | Par | base 0.18×par | LOS 0.12×par | doors | noise | hits | Tracer kills | **Net** |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 INGRESS | 2:00 | 21.6 | 14.4 | +3 | +6 | +4 | −0 | **49.0%** |
| 2 THE LEDGER | 2:30 | 27.0 | 18.0 | +6 | +6 | +4 | −8 | **53.0%** |
| 3 NURSERY | 3:00 | 32.4 | 21.6 | +6 | +6 | +4 | −8 | **62.0%** |
| 4 BAD BLOCK | 3:00 | 32.4 | 21.6 | +6 | +6 | +4 | −16 | **54.0%** |
| 5 THE CHOIR | 3:15 | 35.1 | 23.4 | +9 | +6 | +4 | −8 | **69.5%** |
| 6 DEAD LETTER | 3:30 | 37.8 | 25.2 | +9 | +6 | +4 | −16 | **66.0%** |
| 7 COLD STORE | 3:30 | 37.8 | 25.2 | +9 | +6 | +4 | −16 | **66.0%** |
| 8 THE KERNEL | 4:00 | 43.2 | 28.8 | +9 | +6 | +4 | −16 | **75.0%** |

Levels 5–8 land at 69.5 / 66.0 / 66.0 / 75.0 — a par run ends in the 75% band's shadow and rarely
inside it. `trace_base_rate` stays a **per-level** header field (§11) so a playtest can move one
level without touching the others; it ships at 0.18 %/s uniformly.

| Threshold | Palette (registers 1–10 only) | Music | Enemies |
|---|---|---|---|
| **25%** | the DEGRADED substitution — cyan ramp one rung darker | 140 → 152 BPM | Watchdog alert radius +2 cells |
| **50%** | the magenta ramp's two brightest rungs (6, 7) shift hot toward register 13's orange; art-pass authored, gated | 168 BPM | tier +1: Watchdogs respawn once per room, Tracers +25% speed |
| **75%** | the CORRUPT substitution — registers 1–5 take the magenta ramp, and the infrastructure turns on you | 184 BPM | Sentries fire 3-round bursts; a new Tracer spawns at a sector edge every 30 s |
| **100%** | **HARDENED** — CORRUPT, plus the horizon line drawn in register 13 | one 200 BPM pulse, no melody | exfil |

Every one of those touches registers 1–10 and nothing else, so §3's variant invariant holds and
both gates pass with the same 31.3 Y worst rim margin.

**The exfil rule at 100%.** All objectives void. Every door unlocks, the sealed entry gate (variant
21) opens, and a **Hunter** — a Black ICE fragment: no anchors, unkillable, stunned 3 s by Spike —
spawns at the far end and paths to you along the same distance field (§8.1). Reach the entry gate
and you escape with what you carry; the sector scores **PARTIAL** (no token bonus, par forfeit,
+5% carry). Die and the run is over. 100% is an escalation with a survivable bad outcome, not an
instant fail. *In the first playable, where the Hunter is deferred: 100% swaps to the HARDENED
palette and immediately runs the death path (§18).*

---

## 10. Doors, pickups

Doors are cell values 16..31; all runtime state lives in a parallel array, never in the level file.

### 10.1 The door plane — Wolf3D convention, stated exactly

**The door plane is at the cell midline, perpendicular to the door's axis.** A door's axis is the
line joining its two opposite open neighbours, which the compiler validates and stores (§11), so
the plane is never ambiguous and never depends on which side you approach from.

**DDA rule.** When the ray's cell walk enters a door cell, the caster **advances half a step along
the crossing axis** and tests whether the ray still lies within that cell. If it does, the door
plane is hit: the texture column is the perpendicular offset `u` (0..63) at the midline, and the
hit distance is the half-stepped distance. If it does not — the ray left through a side face before
reaching the midline — the walk continues past the cell. This is one extra half-step and one bounds
compare, on door cells only.

**Rendering is 2-state in v1.** A door is either drawn as a full closed slice (its texture) or is
not hit at all. The intermediate slide offset — the door visibly retracting into its jamb, and the
slit through jammed variant 22 — is **optional later polish**; when it lands, the hit test gains
`u < 64 − slide_offset` at the same plane and nothing else changes.

**Collision uses the same authority.** While a door is in any state other than OPEN, its cell is
solid to the player's 0.28-cell disc, to every enemy disc, and to the Spike DDA. When the slide
offset lands, collision refines to the midline half-plane; until then, whole-cell is both correct
and cheaper.

### 10.2 Door state machine

| State | Ticks | Blocks movement | Blocks LOS | Drawn |
|---|--:|---|---|---|
| CLOSED | — | yes | yes | closed texture |
| OPENING | 12 (0.48 s) | **yes** | yes | closed texture |
| OPEN | 75 (3.0 s) | no | no | not hit |
| CLOSING | 12 (0.48 s) | **yes** | yes | closed texture |

CLOSED → *(bump by any body permitted to open it)* → OPENING → OPEN → CLOSING → CLOSED.
**CLOSING reverts to OPENING if a body is inside the cell.** The OPEN timer resets while any body
is within 1.5 cells, so a door never shuts in your face on the way through.

**Locked doors latch.** A locked door (17/18/19) opened with its token **permanently becomes
variant 16** for the rest of the sector; the +3% trace charge fires **once per door per sector**.
Backtracking through the Bus Hall is free, as §12's route requires.

| Value | Glyph | Door |
|---|---|---|
| 16 | `+` | plain gate, opens on contact |
| 17 / 18 / 19 | `1` `2` `3` | ALPHA / BETA / GAMMA locked. **One shared texture** plus a 1/2/3-pip overlay decal in data yellow (11); magenta-ramp trim when locked, integrity green (14) when satisfied |
| 20 | — | reserved |
| 21 | `S` | sealed. Terminal (§11). Never opens except at 100% trace, when it becomes your exfil |
| 22 | `~` | **jammed** — never opens, own cracked texture, impassable |
| 23 | `>` | sector exit gate. Terminal (§11): entering the cell ends the level |
| 24–31 | — | reserved |

**No switches.** Every switch is a teaching problem plus a use button, and we have neither. Doors,
tokens and the boss anchors (which are *shot*, not switched) carry all the world state.

| Pickup | Glyph | Value | Sprite | Sound |
|---|---|---|---|---|
| Cycles, small | `c` | +10 cycles | yellow chip | token grab |
| Cycles, large | `C` | +25 cycles | yellow block | token grab |
| Integrity, small | `i` | +15 integrity | green wedge | token grab |
| Integrity, large | `I` | +40 integrity | green cube | token grab |
| Token ALPHA/BETA/GAMMA | `p` `q` `r` | opens door 17/18/19 | white key-form, 1/2/3 pips | token grab |
| Scrubber | `u` | −20% trace, instant | green/white spiral | token grab |
| Data cache | `d` | route score + 5 s off the results clock | yellow lattice | token grab |

Pickups are authored at 32×32 and occupy the **lower half** of the cell height (§17.1), so they
read as objects on the floor and never compete with an enemy silhouette for the same screen rows.

**Damage and pickup feedback — two palette writes.** Taking damage swaps the two wall ramps one
step toward register 13 `#FF7722` for 2 frames; a pickup swaps them one step toward register 12
for 2 frames. Both are a 16-word table write plus a counter, and both are in the first playable.
Neither touches registers 11–15, so §3's variant invariant holds and both gates still pass.

---

## 11. Level format contract

Implement exactly this.

**Grid:** 64x64 cells maximum, one byte per cell.
`0` = empty · `1..15` = wall texture id · `16..31` = door variant (all state stored separately)
· `32+` = reserved (must not appear in a shipped level; the compiler rejects it).

**Orientation, stated once:** brad 0 = **north** = −y. Brads increase **clockwise**: 256 = east =
+x, 512 = south = +y, 768 = west = −x. `start_facing` and every entity `facing` use this mapping.

**Binary level file** (`levels/*.bil`, big-endian, produced by the compiler — never hand-written):

| Field | Size | Note |
|---|---|---|
| `magic` | 4 | `'BIL0'` |
| `name` | 16 | NUL-padded ASCII, shown on the loading and results screens |
| `width`, `height` | 1 + 1 | ≤ 64 each |
| `sector_index` | 1 | 0..7 |
| `palette_variant` | 1 | 0 CLEAN / 1 DEGRADED / 2 CORRUPT / 3 KERNEL |
| `texture_set` | 1 | 0..2, which 13-texture set to load |
| `pad` | 1 | alignment |
| `start_x`, `start_y` | 1 + 1 | player start cell |
| `start_facing` | 2 | brads, 0..1023 |
| `rng_seed` | 4 | seeds the §4.3 LCG |
| `trace_base_rate` | 2 | thousandths of a percent per second (180 = 0.18 %/s) |
| `trace_start` | 1 | percent |
| `trace_carry_cap` | 1 | percent — the single authority on start value (§9) |
| `par_ticks` | 2 | par time at 25 Hz |
| `entity_count` | 2 | ≤ 64 |
| `cells[w*h]` | w·h | as above |
| `entities[n]` | 5 each | `type u8, x u8, y u8, facing u8 (brads >> 2), extra u8` |

Header = 42 B; a 48×48 level with 64 entities = 42 + 2,304 + 320 = **2,666 B (≈2.7 KB)**.

**Authoring:** levels are ASCII text in `levels/*.txt`, compiled by `tools/mklevel.py` — which is
the **first** item on the first-playable list (§18) and ships with its validator as unit tests over
both shipped maps. The text file is a `# key: value` header followed by the map block.

### Compiler rules — validates and refuses

1. Rectangular map, ≤ 64×64; exactly one `@`.
2. **Sealed border.** Every border cell is a wall **or a terminal door** (21, 23) — a terminal door
   seals the border, because it is touched, never passed through.
3. **Ordinary door jamb rule.** A door of variant 16, 17, 18, 19 or 22 must have **exactly two
   opposite open neighbours**. That pair is the door's **axis**, and it is written into the compiled
   level so the renderer and the collider agree (§10.1).
4. **Terminal door rule.** Variants 21 and 23 must lie **on the map border** and have **exactly one
   open neighbour**. They are exempt from rule 3. A variant-21 or -23 cell that is *not* on the
   border is an error, and any other door variant *on* the border is an error. This makes the two
   conventions one convention: **every `S` and every `>` is an arch in the outer wall.**
5. **Sentry alcove rule.** `s` compiles to an **empty cell plus a Sentry entity** and must have
   **exactly three wall neighbours and one open neighbour** (§8).
6. Entity count ≤ 64; no reserved cell value.
7. **Lock-ordered flood fill** proving every token, every pickup and the exit are reachable in a
   legal token order, and reporting that order.
8. **Warning (not a refusal):** any floor cell with fewer than two open neighbours that is not a
   Sentry alcove — the 1-cell pocket that reads as dead geometry and that a chase AI has no reason
   to enter. Both shipped maps are warning-free.
9. **Warning (not a refusal):** an `X` exit-plating run or a `>` gate whose nearest floor cell on
   the approach is beyond **band 2** (about 9 cells). Integrity green fogs to slate at band 3
   (§3), so a gate first seen from further than that is not green and stops reading as the
   landmark. Both shipped maps are warning-free.

### Legend (fixed; the compiler owns this table)

| Glyph | Cell | Glyph | Cell |
|---|---|---|---|
| `.` | 0 empty | `+` | 16 plain door |
| `#` | 1 circuit lattice | `1` `2` `3` | 17/18/19 locked doors |
| `=` | 2 hex mesh | `~` | 22 jammed door |
| `%` | 3 glyph column | `>` | 23 sector exit (terminal, border) |
| `\|` | 4 bus trunk | `S` | 21 sealed gate (terminal, border) |
| `^` | 5 firewall chevron | `@` | player start (facing from the header) |
| `?` | 6 corrupted noise | `w` `t` `B` | Watchdog / Tracer / Black ICE (cell → 0) |
| `A` | 7 anchor pylon (decorative wall) | `s` | **Sentry (cell → 0 + entity; alcove, rule 5)** |
| `X` | **8 exit plating** | `*` | live anchor (cell → **0** + solid anchor entity) |
| | | `p` `q` `r` | tokens ALPHA / BETA / GAMMA |
| | | `c` `C` `i` `I` `u` `d` | pickups per §10 |

The v1 legend collision is gone: `s` no longer compiles to wall 8, and `X` alone owns texture 8.

---

## 12. Level 1 — INGRESS (32x32)

Header: `sector 0 · palette 0 · texture_set 0 · start (15,28) facing north · par 3000 ticks (2:00)
· trace_base_rate 180 · trace_start 0 · trace_carry_cap 25`

You arrive through the Cold Boot Gate (`S`, the sealed arch in the south wall — remember it) into
the boot chamber, walk the spine north into the Bus Hall that spans the sector, and immediately
learn the two lessons the whole game is built on: the Sentry **recessed into an alcove** in the
hall's north wall teaches you that the architecture shoots, and the four Watchdogs teach you that
packs come down corridors. The ALPHA token is in the west cache alcove; the **east kennel holds all
four dogs in one 6-cell wake cluster**, and they come out through the row-16 gap in a line. The
token opens the north door into the Handshake Hall, a clean symmetrical room whose north wall opens
onto the exit arch. Nothing here is corrupt. This sector is what HALCYON is supposed to look like.

Roster: 4 Watchdogs, 1 Sentry, 0 Tracers (12 entities). Route: `@` → Bus Hall → west alcove
(`p` ALPHA) → door `1` → Handshake Hall → `>`.
Watchdogs at (26,17), (24,19), (27,20), (25,21); every pairwise distance is 2.24–4.12 cells, inside
the 6-cell pack-wake radius, so all four wake as one.

```
###############>################
###############.################
############===.====############
###########%........%###########
###########%........%###########
###########%........%###########
###########%........%###########
###########%.....d..%###########
###########%........%###########
###############1################
###############..###############
###############..###############
###|||||||s||||..||||||||||||###
###..........................###
###..........................###
###..........................###
###||..||||||||..||||||||..||###
###....c.######..######...w..###
###.p....######..######...c..###
###......######..######.w....###
###......######..######....w.###
###..i...######..######..w...###
###......######+#######....u.###
##########............##########
##########............##########
##########..C.........##########
##########............##########
##########............##########
##########.....@......##########
##########............##########
##########............##########
###############S################
```

## 13. Level 2 — THE LEDGER (32x32)

Header: `sector 1 · palette 0 · texture_set 0 · start (15,28) facing north · par 3750 ticks (2:30)
· trace_base_rate 180 · trace_start 0 · trace_carry_cap 25`

The ingress chamber opens onto a spine that forks east into the Vault — an open room with the BETA
token, one Tracer and the supplies — and north through the BETA door into **the Ledger Stack**, the
landmark: a 24×14 hall filled with **twenty-four** single-cell glyph columns on a regular 4×3
lattice that reaches the east wall, so there is no free lane down the flank. It is the first room
where sightlines are the puzzle. Two Sentries cover it from recessed alcoves, one in the north wall
and one in the west, and neither can be flanked without breaking the lattice's diagonals. The ALPHA
token is deep in the south-west of the stack; it opens the door in the north-east corner into the
exit throat. This is the level that teaches **range and cover**: the aisles are 3 cells wide and
2 cells tall, Watchdogs come down them in a line, and the Tracers hold the ring at 3–5 cells and
strafe while you deal with the dogs. (When Spike lands, this is the room it is tuned against.)

Roster: 5 Watchdogs, 2 Sentries, 2 Tracers (17 entities). Route: `@` → `+` → east to the Vault
(`q` BETA) → door `2` → the Stack (`p` ALPHA) → door `1` → exit throat → `>`.

```
###########################>####
###########################.####
##########################..####
#####==========s==========1#####
####........................####
###|.................d......|###
###|...%...%...%...%...%...%|###
###|....w...........w.......|###
###|........................|###
###|...%...%...%...%...%...%|###
###s........t...............|###
###|........................|###
###|...%...%...%.c.%...%...%|###
###|..p.................w...|###
###|........................|###
###|...%.u.%...%...%...%...%|###
###|.w.......w..............|###
####........................####
###############2################
###############..#####.......###
###############..#####.t.....###
###############..............###
###############..#####.c.....###
###############+######.......###
###########..........#.......###
###########..........#..q....###
###########.C........#.....i.###
###########..........#.......###
###########....@.....###########
###########..........###########
###########..........###########
###############S################
```

*(Both maps are machine-validated against **all eight** §11 rules: rectangular, sealed border with
terminal doors, one `@`, every ordinary door with exactly two opposite open neighbours, every
terminal door on the border with exactly one open face, every Sentry in a 3-wall alcove, entity
counts 12 and 17, and a lock-ordered flood fill returning `[p]` for level 1 and `[q]` then `[p]`
for level 2 with the exit reachable. Zero dead-end warnings in either map.)*

---

## 14. The eight levels

| # | Name | Size | W | S | T | Tokens | Par | `trace_base_rate` | Net trace at par (§9.1) |
|---|---|---:|--:|--:|--:|---|--:|--:|--:|
| 1 | INGRESS | 32x32 | 4 | 1 | 0 | A | 2:00 | 0.18 %/s | 49.0% |
| 2 | THE LEDGER | 32x32 | 5 | 2 | 2 | A, B | 2:30 | 0.18 %/s | 53.0% |
| 3 | NURSERY | 40x40 | 8 | 3 | 2 | A, B | 3:00 | 0.18 %/s | 62.0% |
| 4 | BAD BLOCK | 40x40 | 8 | 2 | 4 | A, B | 3:00 | 0.18 %/s | 54.0% |
| 5 | THE CHOIR | 40x40 | 10 | 4 | 3 | A, B, G | 3:15 | 0.18 %/s | 69.5% |
| 6 | DEAD LETTER | 48x48 | 12 | 3 | 4 | A, B, G | 3:30 | 0.18 %/s | 66.0% |
| 7 | COLD STORE | 48x48 | 12 | 5 | 4 | A, B, G | 3:30 | 0.18 %/s | 66.0% |
| 8 | THE KERNEL | 48x48 | 10 | 6 | 4 | A, B, G | 4:00 | 0.18 %/s | 75.0% |

Total par **24:45**; a known route runs under 20 minutes.

- **3 NURSERY** — the Fork Ring: a circular hall with eight spurs, seven ending in a one-cell stub
  (processes that never started). Two dead spurs hold the tokens, so you walk them all. Degraded
  palette; first level with real Tracer pressure. *(The stubs are the one place §11 rule 8's
  warning is expected and accepted — they are the room's premise; the compiler warns, the designer
  signs it off in the level header comment.)*
- **4 BAD BLOCK** — the first corrupt sector, and the set-piece is **the Shear**: a 20-cell-long
  double corridor where the sector was written twice, one copy offset a cell from the other, so the
  two halves never join and the connecting doors are all variant 22 — jammed. You can see the route
  you want for the whole level and never take it. Texture mismatch everywhere; noise texture in
  patches.
- **5 THE CHOIR** — the Switchboard: one enormous wall of dead lines, faked entirely in texture.
  Wide rooms, so the Sentry count jumps and UNDERCLOCK turns dangerous. First GAMMA token.
- **6 DEAD LETTER** — corrupt. **The Undeliverable** is one 9x9 room stamped four times; only the
  entity lists differ, and one of the four holds the exit. This is the level about which stamp you
  are standing in. Corrupt palette, jammed doors, grid drift on every junction.
- **7 COLD STORE** — the Carousel: a ring of tape bays around a central well, the densest Sentry
  layout in the game and the level where OVERCLOCK pays for itself.
- **8 THE KERNEL** — terminal corruption, KERNEL palette. Ends in the Anchor Chamber: four
  free-standing pylons (`*`, solid floor entities) and Black ICE, which mirrors your movement
  across the room's long axis and teleports between anchors every 90 ticks. It cannot be damaged.
  You break the four 60 HP anchors while it is not standing at them — a positioning puzzle, not a
  damage sponge.

---

## 15. Flow: title, win, lose, results

- **Title** → static planar screen, register-12 `#FFFFFF` logotype on void (0), YM theme. Fire/Space → **mission
  brief** (a repossession order, three lines of deadpan) → sector 1.
- **Pause** — `P` (keyboard). Dims the palette by one ramp step, overlays RESUME / ABORT RUN.
  Sim frozen, timer frozen.
- **Death** — integrity 0 → 2 s dissolve → `CONNECTION TERMINATED`. Retries are unlimited and
  restart the current sector, but each death adds **+30 s to the route timer and +10% starting
  trace**, both folded into §9's single start rule and capped by `trace_carry_cap`. Death is a cost,
  never a wall.
- **Sector clear** — entering `>` with objectives met = CLEAN; exfil at 100% trace = PARTIAL.
  Either way, a **SECTOR CLEAR** overlay: sector name, time, par delta, tokens, kills, peak trace.
- **Run complete** — after the last sector in the build, a **RUN COMPLETE** screen with the route
  time. In the first playable that is after level 2; in the full game it is after THE KERNEL.
- **Win** — all four anchors broken in THE KERNEL.
- **Results screen** — one row per sector: name, time, par delta (green under, magenta over),
  CLEAN/PARTIAL, tokens, data caches, peak trace, kills. Then the totals: **route time**, total par
  delta, and a grade letter derived from route time alone. The route timer is the whole scoreboard.

### 15.1 HUD — a first-playable deliverable, so it is specified

**The layout is `art/ART_DIRECTION.md` §5's and is shipped as drawn.** A **static 320×40 planar
strip on the bottom 40 scanlines** (screen lines 160–199), outside the c2p region, **drawn at
1:1** — which is why an 8×8 font is legible in it. The panel art (`hud.py`) is blitted **once** at
level load; the dynamic fields are dirty-rect planar glyph writes straight into those 40 lines,
each field on a 16-pixel horizontal boundary so a write is a whole number of planar words. Font:
**64 glyphs, 8×8**, register 12 on register 0.

**No Timer-B raster split in v1.** The HUD's four hues — white (12), orange (13), yellow (11),
green (14) — are colours the walls either cannot own or barely use, so a second palette buys
nothing yet. The strip keeps the split available later without needing it now.

| Field | x (screen px) | w | Content |
|---|--:|--:|---|
| INTEGRITY | 8 | 72 | 3-digit value + a 64×6 bar in register 14 (green) |
| CYCLES | 88 | 64 | 3-digit value in register 11 (data yellow) |
| TRACE | 160 | 80 | `NN%` + a 64×6 bar, register 14 → 13 (orange) as it climbs |
| TOKENS | 248 | 32 | up to 3 pip glyphs in register 11, lit when held |
| CLOCK dial | 284 | 28 | three segments in register 15 trim; the active one in register 12 |
| MESSAGE line | 8 | 304 | one 38-char line in register 12, 2 s timeout — door refusals ("BETA REQUIRED"), pickups, threshold crossings |
| COMPASS | 240 | 8 | at OVERCLOCK only: nearest-token bearing tick, register 11 |

Only fields whose value changed are redrawn. The whole HUD has its own row in §17's budget table;
it is not hidden inside "audio, HUD, input". Two `ART_DIRECTION.md` §8 caveats apply to the font
and must be fixed there, not worked around here: `@` renders as a 2×2 blob and `*` as an 8-arm
starburst.

---

## 16. Audio

**YM2149, VBL-tick driver, 3 channels:** bass line, arpeggio, lead/percussion. One module per act,
and the tempo *is* the trace meter — 140 BPM at 0%, then **152 / 168 / 184** at the thresholds, and
at 100% the melody drops out entirely, leaving a single 200 BPM pulse. Tempo change is a driver
counter, not a new module.

**The first playable is YM-only**, so every cue below also has a YM form: channel C is reserved as
an SFX slot that the music driver yields for the cue's duration (shot = a 2-frame noise burst,
snarl = a descending square sweep, token grab = a two-note arpeggio, refusal = a low buzz, hit = a
noise hit, gate = a rising sweep). The priority rule in this section governs the YM slot identically.

**STE DMA sound, one 8-bit channel at 12,517 Hz, no CPU mixing.** Bank 7.0 s = 87,619 B, buffer
booked at **87,808 B (85.75 KiB)**.

| Sample | Length | Priority |
|---|--:|--:|
| Buster shot | 0.10 s | 1 |
| Spike shot | 0.35 s | 2 |
| Watchdog snarl | 0.30 s | 1 |
| Sentry charge | 0.45 s | 2 |
| Gate open | 0.55 s | 2 |
| Gate close | 0.30 s | 1 |
| Token grab | 0.25 s | 2 |
| Door refusal tone | 0.15 s | 2 |
| Throttle change | 0.20 s | 1 |
| Trace threshold alarm | 0.90 s | 3 |
| Player hit | 0.30 s | 3 |
| Enemy dissolve | 0.40 s | 2 |
| Exfil siren | 1.20 s | 3 |
| **Total** | **5.45 s** | 1.55 s reserved for boss and title stings |

**The no-mixing priority rule, stated without ambiguity.** One channel. A new one-shot **preempts**
the playing one **iff `new_priority >= playing_priority`**; otherwise it is **dropped, never
queued** — a queued sound in a game with a 0.2 s weapon plays after the thing it describes. No
sample ever loops: a sustained sample locks out every other cue for its duration.

That rule plus these numbers means **killing something while shooting is audible**: the Buster
sample is 0.10 s against a 0.20 s rate of fire, so the channel is idle half the time even under
sustained fire, and enemy dissolve (2) and token grab (2) preempt an in-flight Buster shot (1)
outright. The snarl at 1 preempts an equal-priority shot rather than being silently dropped.

---

## 17. Budget and RAM ledger

### 17.1 Projection — the constants, stated once

| Constant | Value | Meaning |
|---|--:|---|
| `FOV_DEG` | **60°** | horizontal field of view (`FOV_BRADS` = 171) |
| `COLS` | **160** (80 in low detail) | ray columns across the window |
| `FOCAL_COLS` | **138.6** = 80 / tan(30°) | horizontal focal length in columns; `atan(80 / 138.6)` = 30.0° ✓ |
| `FOCAL_ROWS` | **64** | vertical focal length in rows |
| `WALL_HEIGHT_CELLS` | **1.0** | a wall is exactly one cell tall |
| `ENEMY_HEIGHT_CELLS` | **1.0** | **Wolf3D convention: an enemy billboard is one cell tall — the same height as a wall at the same distance** |
| `PICKUP_HEIGHT_CELLS` | **0.5** | 32×32 pickups occupy the **lower half** of the cell height |
| `WINDOW` | **160 × 80** chunky | pixel-doubled to 320 × 160 |

**The two projection identities everything derives from:**

```
wall_rows(d)    = FOCAL_ROWS / d          =  64   / d      (d = perpendicular distance, cells)
sprite_rows(d)  = FOCAL_ROWS * h / d      =  64*h / d       (h = ENEMY/PICKUP_HEIGHT_CELLS)
sprite_cols(d)  = sprite_rows(d)          (square source, drawn square in chunky space)
```

A wall fills the 80-row window at **d = 0.8 cells** (64 / 0.8 = 80). At d = 1.0 it is 64 rows, so
a corridor at one cell leaves 8 rows of ceiling and 8 of floor. A 64×64 enemy sprite is scaled to
`64/d` rows — identically to a wall — so an enemy standing against a wall is exactly as tall as it.

| d (cells) | wall / enemy rows | enemy cols | 1-cell wall face, cols |
|--:|--:|--:|--:|
| 0.6 | 106.7 (clipped 80) | 106.7 | 231.0 |
| 0.8 | 80.0 | 80.0 | 173.2 |
| 1.0 | 64.0 | 64.0 | 138.6 |
| 2.0 | 32.0 | 32.0 | 69.3 |
| 2.5 | **25.6** | 25.6 | 55.4 |
| 6 (UNDERCLOCK radius) | 10.7 | 10.7 | 23.1 |
| 12 (NOMINAL radius) | 5.3 | 5.3 | 11.5 |
| 20 (OVERCLOCK radius) | **3.2** | 3.2 | 6.9 |

**Aspect, owned rather than discovered.** `FOCAL_ROWS` (64) and `FOCAL_COLS` (138.6) are
independent, and a chunky pixel is 2×2 screen pixels on a 320×200 display whose pixel is 0.833 as
wide as it is tall on a 4:3 monitor. A 1×1 wall face therefore reads **1.81× wider than tall** —
Wolf3D's own figure is about 1.44, so this is the same family, one notch wider. It is deliberate:
corridors read low and broad, which suits a machine interior, and it keeps `FOCAL_ROWS` a power of
two so the column-height LUT is a shift. **`FOCAL_ROWS` is the single knob** if playtest says the
world is too squashed; nothing else in this document depends on its value except the table above
and the WC fixtures below.

### 17.2 Detail levels — what 80 columns actually saves

**80-column mode halves the column-draw stage. It does not touch the c2p.** The chunky buffer stays
160×80 either way; the engine picks whichever of the two implementations the spike measures cheaper:

- **(a) Double-write.** Cast 80 rays; each writes its 4-pixel-wide column into two adjacent chunky
  columns. Buffer stays 160×80, c2p unchanged, one c2p table.
- **(b) Narrow buffer.** Cast 80 rays into an 80×80 chunky buffer; the c2p pass doubles 4× on the
  way out. Buffer 6,400 B, **a second c2p routine** (not a second table — the same 8bpp→4bpl table
  is indexed twice per source byte).

Either way the saving is **the DDA (halved), the wall column fill (halved), and the sprite budget
(halved)** — never the fixed planar output. v1's claim that the fallback saved c2p cycles was false
and the gate built on it is replaced below.

### 17.3 Cycle budget — worst case, all TBD

The spike measures **three canonical worst-case frames**, which then become permanent replay-golden
fixtures in `test/` and gate every renderer commit:

- **WC-A "Corridor"** — nose-to-wall at d = 0.8, all 160 columns at the full 80-row window height,
  zero sprites: **12,800** textured pixels.
- **WC-B "Ambush"** — 160 columns of wall at d = 2.0 (32 rows each = 5,120 textured px) plus
  **three Watchdogs at 2.5 cells, 25.6 rows and 25.6 columns each = 655 px each, 1,966 px total**.
  (v1 claimed 64×64 per dog here; under the stated projection that would need a 2-cell-tall dog
  whose head is through the ceiling. This is the corrected fixture.)
- **WC-C "Contact"** — the sprite worst case: four Watchdogs at 0.6 cells with 160 columns of wall
  behind them. The exempt nearest attacker clips to **107 × 80 = 8,560 px**; the rest are admitted
  against `SPR_PX_BUDGET` = 6,000, giving the hard bound of **14,560 sprite px** (and an absolute
  ceiling of 12,800 + 6,000 = 18,800 if a sprite fills the window).

| Stage | WC-A | WC-B | WC-C | Note |
|---|---|---|---|---|
| c2p + pixel double, 160x80 → 320x160 | TBD | TBD | TBD | **fixed, content-independent**, 25,600 planar bytes out. `ART_DIRECTION.md` §5 scales the critique's full-screen figure to **128k–160k cycles** for this layout — an *estimate*, carried here as the number the spike must confirm or kill |
| DDA cast, 160 rays | TBD | TBD | TBD | reciprocal LUT, no per-ray divide; +½ step in door cells |
| Wall columns → chunky buffer | TBD | TBD | TBD | unrolled height classes |
| Sprites, budgeted (§8.2) | 0 | TBD | TBD | 1,966 px (WC-B) / ≤14,560 px (WC-C) |
| Sim tick incl. BFS field (§8.1), amortised | TBD | TBD | TBD | BFS ≤ 1,257 cells every 8 ticks |
| HUD dirty-rect writes (§15.1) | TBD | TBD | TBD | its own row, not folded into "misc" |
| Audio + input | TBD | TBD | TBD | DMA replay steals bus cycles — measure, do not assume zero |
| **Total, 160 columns — budget 480,000** | TBD | TBD | TBD | 3 VBLs = 16.7 fps ≥ the BRIEF's 14 |
| **Total, 80 columns — budget 320,000** | TBD | TBD | TBD | 2 VBLs = 25 fps ≥ the BRIEF's 20 |

**Two budgets, because there are two flip locks.** On a 50 Hz PAL flip lock the only frame rates
available are 25 (2 VBLs), 16.7 (3) and 12.5 (4). There is no 20 fps, so the BRIEF's *"≥ 20 fps at
80 columns"* means **2 VBLs = 320,000 cycles**, and *"≥ 14 fps at 160 columns"* means **3 VBLs =
480,000 cycles**. Each mode locks to its own cadence; the engine does not free-run.

**Gate, decided now so it is not decided in month 3 — and stated on the total frame, not on c2p:**
if the **measured total frame** at 160 columns exceeds **480,000 cycles** on WC-A, WC-B or WC-C,
then **80 columns becomes the shipping default** and 160 becomes an options-screen setting.
Pin all three measurements in `STATUS.md` before any further art is produced.
*(`ART_DIRECTION.md` §5 still cites v1's 130,000-cycle **c2p-only** gate. That gate is superseded
by this one — finding 3 showed a c2p-only gate measures a cost the fallback cannot change.)*

### 17.4 RAM ledger — committed arithmetic

**Texel format: one byte per texel. Decided.** The inner loop needs it; a nibble costs a shift and a
mask on every column pixel, which is the hottest loop in the program. The 1 MB fit is bought instead
by **one texture set resident at a time** (three exist on disk, one is in RAM) and by baking shading
at load.

**Depth shading, decided:** wall textures ship on disk as **one** 64×64 band and are expanded to
**5** baked bands at level load by applying `palette.shade_table(band)` (§3). Sprites ship as one
frame and are expanded to **2** baked depth variants (near / far, bands 0 and 2) through
`drawlib.shade_sprite`, which preserves the register-15 transparency key — two variants, not v1's
three, because a sprite's read comes from its rim and its two reserved accents, none of which fog,
while the 5-band ramp is carried by the walls behind it. Nothing is authored twice, and nothing
costs a remap lookup in the inner loop.

Disk form may be **nibble-packed** — `ART_DIRECTION.md` §6 measures 40 KB saved across the shipped
assets, which is the difference between three texture sets fitting on the floppy and not. RAM stays
byte-per-texel; the loader unpacks.

**Texture count, corrected.** 8 wall textures (1 lattice, 2 hex mesh, 3 glyph column, 4 bus trunk,
5 firewall chevron, 6 corrupted noise, 7 anchor pylon, 8 exit plating) + 5 door textures (16 plain,
**one shared** locked texture for 17/18/19, 21 sealed, 22 jammed, 23 exit) = **13**, plus a
3 × 16×64 pip-overlay strip that gives the locked door its 1/2/3 identity. The Sentry needs no wall
texture at all — it is a sprite again (§8).

| Item | Arithmetic | Bytes |
|---|---|--:|
| Wall/door textures, resident set | 13 × 64×64 × 5 bands × 1 B + 3 × 16×64 pips | 269,312 |
| Enemy + anchor sprite frames | 22 × 64×64 × 2 shade variants | 180,224 |
| Pickup + spark sprite frames | 11 × 32×32 × 2 shade variants | 22,528 |
| Screen buffers | 2 × 32,000 | 64,000 |
| Chunky render buffer | 160 × 80 | 12,800 |
| c2p tables | table-driven 8bpp → 4bpl | 65,536 |
| Trig / reciprocal / column-height LUTs | 1024 sin/cos + 2048 recip + heights | 12,288 |
| BFS distance field + entity cell occupancy | 2 × 48×48 | 4,608 |
| DMA sample bank | 7.0 s @ 12,517 Hz = 87,619, buffer 85.75 KiB | 87,808 |
| YM modules + driver | 8 acts | 8,192 |
| Resident level | 48×48 cells + door state + axes + 64 entities + header | 6,912 |
| Entity/AI runtime + game state | | 4,096 |
| Render snapshot (§4.1) | 64 × 8 | 512 |
| HUD strip + font | 320×40 planar (6,400) + 64 glyphs 8×8 (512) | 6,912 |
| Program text + data (estimate) | | 90,000 |
| bss scratch + stack | | 16,384 |
| **Subtotal** | | **852,112** |
| TOS/GEMDOS + FS buffers (estimate) | | 120,000 |
| **Total** | | **972,112** |
| **Headroom vs 1,048,576** | | **76,464 (~75 KB)** |

Headroom is **7.3%**, not v1's claimed comfort — the honest consequence of 15 textures' worth of
content, 64×64 enemies and a Sentry that can actually be drawn. It is a fit with margin for the
90,000-byte program estimate to be wrong by 85%. If it needs buying back, in order: nibble-pack the
resident textures as well as the disk copy (−134,656), drop the DMA bank to 5.5 s (−18,800), fold
the anchor's 3 frames into the Black ICE set (−24,576), drop wall bands from 5 to 4 (−53,248).

Disk (720 KB floppy): the .PRG, three texture sets at one band each RLE-packed (geometric art
compresses to a few KB per set), 33 sprite frames, 8 compiled levels (≈2.7 KB each), the sample
bank (~86 KB, the dominant term) and the YM modules. Comfortable.

---

## 18. Scope ladder

**Solid first playable — this is the milestone that proves the game exists:**

0. **`tools/mklevel.py`** and its validator, shipped with unit tests over both maps. It gates
   everything below it and it carries all eight §11 rules.
1. Levels 1 and 2, exactly as printed in §12–13.
2. **Watchdog, Sentry and Tracer**, all three on the §8.1 distance field. (Black ICE and the
   Hunter stay deferred.)
3. Buster only. *(Spike is the next thing in; §13's stack is where it will be tuned.)*
4. **All door variants that share the one mechanism: 16 plain, 17 ALPHA, 18 BETA, 19 GAMMA** — one
   code path and one table, so 19 is free even though levels 1–2 do not use it. Bump-to-open, the
   latch rule, the 2-state render, and the §10.1 midline plane.
5. Trace meter with all four thresholds — palette and music tempo, no tier-up behaviour. At 100%:
   HARDENED palette + the death path (§9), because the Hunter is deferred.
6. **Clock throttle as a two-state UNDERCLOCK ↔ NOMINAL toggle** (keys 7/8), full dial on the HUD.
   OVERCLOCK arrives with 160-column mode. This is the addition the review argued for and it is
   accepted: it costs no art, no sprites and no second renderer — a render-radius clamp (6 vs 12
   cells) and three multipliers §5 already tabulates — and it is what turns a straight-walking dog
   and a static turret into a decision. Underclock to slip past the turret blind and fast, at the
   price of a 6-cell world where a pack can be on you before it is drawn; or nominal, and fight.
7. HUD per §15.1, title screen, death and retry, **SECTOR CLEAR overlay**, **RUN COMPLETE screen**
   after level 2, and the **damage / pickup palette flash** (§10).
8. One texture set. **80-column mode as the shipping default** until §17.3's gate says otherwise;
   both column modes exercised by the spike fixtures.
9. YM audio only, with the YM forms of every §16 cue.
10. **Determinism: the seeded LCG, the per-tick hash, and the pinned 600-tick level-1 replay** —
    the surface that lets an overnight build tell you it still works.

Everything there is on the renderer's critical path and none of it is art-heavy.

**Then, in order:** 160-column mode → OVERCLOCK → Spike → DMA samples → levels 3–7 → the Hunter and
the 100% exfil → THE KERNEL and the anchor boss → results screen and grades → the door slide offset
(and with it variant 22's see-through slit).

**Cut order, first to go:**

1. The Black ICE anchor boss → THE KERNEL ends with a scripted three-Tracer-plus-two-Sentry final
   room instead. Saves 9 sprite frames and the mirroring AI.
2. Levels 5 and 7 → a 6-level game. The corrupted sectors (4, 6) stay; they are the identity.
3. DMA samples → YM-only SFX. Frees ~86 KB of disk and 88 KB of RAM.
4. 160-column mode → the game ships at 80 columns, which the BRIEF already blesses at 25 fps.
5. The Tracer. **Moved down from third**: it is now in the first playable, it shares the Watchdog's
   distance field so it costs no new AI, and cutting it turns the trace meter from a resource into
   a pure timer. It goes last because it is the cheapest thing in the build with a real verb.

**Never cut, at any scope:** the trace meter, bump-to-open doors, the sprite-pixel budget with
priority dropping, §3's two measured palette gates and its variant invariant (with the white
rim-light they exist to protect), and the BFS distance
field. Those five are the difference between this game and a raycaster tech demo.

---

## 19. Changelog — v1 → v2

Every finding in `DESIGN_REVIEW.md`, with its resolution. Section references are to v2.

### BLOCKERs

| # | Finding | Resolution |
|---|---|---|
| 1 | Level 2 cannot run under the first-playable feature set | **ACCEPTED, option (a) plus more.** §18 ships **all** door variants sharing the one mechanism — 16, 17, 18 and 19 — and **the Tracer is in the first playable**. Level 2 stands as drawn (with §12–13's independent corrections from finding 6 and NITs 35/37). |
| 2 | FOV, projection constant and enemy world height never stated | **ACCEPTED.** New §17.1 names `FOV_DEG` 60, `COLS` 160/80, `FOCAL_COLS` = 80/tan 30° = **138.6**, `FOCAL_ROWS` = **64**, `WALL_HEIGHT_CELLS` = `ENEMY_HEIGHT_CELLS` = **1.0** (Wolf3D convention), `PICKUP_HEIGHT_CELLS` = 0.5, plus a distance table and an owned aspect figure (1.81× wider than tall). WC-B recomputed: **three Watchdogs at 2.5 cells = 25.6 rows / 655 px each, 1,966 px total** — not 64×64. |
| 3 | The c2p fallback gate saves nothing | **ACCEPTED.** §17.2: 80-column mode halves the **column-draw** stage, never the c2p; the chunky buffer stays 160×80 and the engine picks the cheaper of double-write (a) or narrow-buffer + 4× expand (b). §17.3's gate is re-stated on the **measured total frame**: ship 80 columns as default if the 160-column frame exceeds **480,000 cycles (3 VBLs)** on WC-A/B/C. §5's UNDERCLOCK claim is corrected to "partial and honest". |
| 4 | The Sentry is an entity inside a wall cell | **ACCEPTED, with the orchestrator's variant rather than the reviewer's.** §8: the Sentry is a **floor entity in a 1-cell alcove** (three wall neighbours, one open side), drawn as an ordinary billboard against the alcove's back wall — no wall-texture override, no depth bias, no z-fight, sprite total stays 33. §11 rule 5 enforces the alcove; the legend collision is fixed (`s` → cell 0 + entity; `X` alone owns texture 8). The anchor `*` gets the same treatment: a free-standing floor entity with a 0.4-cell solid disc. All three shipped Sentry positions already satisfy the alcove rule unchanged. |
| 5 | The door plane is under-specified | **ACCEPTED.** §10.1: plane at the **cell midline perpendicular to the door's axis**; the axis is the compiler-validated open-neighbour pair and is stored in the level; the DDA **advances half a step on entering a door cell** and checks the ray is still inside before accepting the hit. §10.2 gives the state machine CLOSED → OPENING (12 ticks, blocks) → OPEN (75) → CLOSING (12, reverts to OPENING if a body is in the cell) → CLOSED. **v1 renders 2-state**; the slide offset is later polish. Collision treats any non-OPEN door cell as solid, and the Spike DDA uses the same predicate. |
| 6 | The stated jamb rule rejects both shipped maps | **ACCEPTED, with the maps corrected rather than the rule bent twice.** §11 rule 3: an ordinary door has **exactly two opposite open neighbours** (that pair is its axis). Rule 4: a **terminal** door (21, 23) must be **on the map border** with exactly one open neighbour, and seals the border. Both maps were re-validated and all three named cells failed, so all three moved: level 1's `S` → **(15,31)** and its `>` → **(15,0)**; level 2's `S` → **(15,31)** and its `>` → **(27,0)**. The convention inconsistency the reviewer flagged is now one convention: *every `S` and every `>` is an arch in the outer wall*. Re-run: 0 errors, 0 dead-end warnings, lock order `[p]` / `[q],[p]`, exit reachable in both. |
| 7 | The joystick modifier layer conflicts with the two commonest inputs | **ACCEPTED — layer deleted entirely.** §6: joystick up/down = move, left/right = turn, fire = shoot (edge-triggered, **auto-repeating at the weapon's rate of fire** while held). Keyboard Z/X strafe; **holding Alt or Shift turns left/right into strafe on the stick as well as the arrows** — the ST convention. 1/2 weapon, 7/8/9 throttle direct, Space/Ctrl fire, P pause, Esc abort. Doors open on contact. **The game is completable with joystick + Alt**, and the document no longer claims stick-only completeness. |
| 8 | The Watchdog chase rule cannot navigate either shipped level | **ACCEPTED.** New §8.1: a **BFS distance field** from the player over the walkable grid — one byte per cell, radius-limited to **20 cells**, recomputed every **8 sim ticks** (≤ 1,257 cells visited), 2,304 B resident. Enemies move **cell-to-cell**: pick the lowest-valued neighbour (best of 8 with a corner check), commit until the cell centre, re-pick on arrival. Because the field is a true BFS this **cannot jam**. The Tracer uses the same field for its 3–5 ring, its strafe (lateral neighbour) and its FLEE (ascend the gradient); so does the Hunter. |

### SHOULD-FIX

| # | Finding | Resolution |
|---|---|---|
| 9 | Sprite budget unbounded in the case it exists for | **ACCEPTED, per the orchestrator's exemption rule.** §8.2: pixels are counted **after** window clipping and **after** the per-column depth test; **only the nearest attacker is exempt**; everything else is dropped **farthest-first**. Hard bound = `12,800 + SPR_PX_BUDGET` = 18,800 at 160 columns; the four-dogs-at-0.6-cells case costs 8,560 (exempt) + 6,000 and the farthest dog flickers — the documented failure mode. Fixture **WC-C "Contact"** added for exactly this case, alongside the corrected WC-B. |
| 10 | The white rim does not separate enemies from band 1 | **ACCEPTED, and then superseded by the art pass — which measured it rather than asserting it.** The finding is real and the mechanism is now `art/rimtest.py`: every rimmed sprite over every wall texture at every band, **400 combinations**, threshold **≥ 24 Y**, **0 failures, worst margin 31.3 Y**, and **0.0 Y with the rim deleted**. The palette that produced those numbers is `ART_DIRECTION.md` §3's, restated in §3 here; the design's own ΔY ≥ 40 rule and its interim palette are withdrawn, because 40 was a guess and 24/31.3 is a measurement over the art that actually ships. v1's fatal case — data yellow at ΔY 2 from band 1 — is gone: the brightest wall-legal colour is data yellow at Y 223.7 and the rim clears it by 31.3. The reviewer's two-tone rim is **not adopted**: `rimtest.py` passes with a single white rim, and the 0.0 Y number shows exactly what that rim is buying. |
| 11 | Palette variants re-open the wall-forbidden-accent hole | **ACCEPTED, in the final palette's terms.** §3's variant invariant: a `palette_variant` or trace threshold may recolour **only registers 1–10, the two wall ramps**; registers 0, 11, 12, 13, 14 and 15 are byte-identical in every variant. Reserved 12 and 13 therefore stay reserved, register 15 stays a usable transparency key, and — the load-bearing consequence — the rim gate's binding case is **data yellow (11)**, which no variant touches, so **31.3 Y is the worst margin in all four variants by construction**. CORRUPT loads the magenta ramp into 1–5 (both ramps magenta, the rim carrying the separation, exactly as `ART_DIRECTION.md` §3 argues for `firewall_chevron`); DEGRADED is `shade_table(1)` with no new hexes; KERNEL is art-pass authored under both gates. Both harnesses are still run per variant. |
| 12 | Par pace alone drives the back half to HARDENED | **ACCEPTED, retuned with the arithmetic shown.** §9.1 defines a **reference run** (par pace, LOS 20% of par, every locked door once, 3 noise shots, 4 hits, half the Tracers killed, no scrubber) and tunes `trace_base_rate` to **0.18 %/s** on every level. Nets: 49.0 / 53.0 / 62.0 / 54.0 / **69.5 / 66.0 / 66.0 / 75.0** — levels 5–8 land near 70%, the orchestrator's target. Locked-door cost dropped 5% → **3%** and now fires **once per door per sector** (finding 17). `trace_base_rate` stays per-level in the header and is printed in §14. |
| 13 | "Standing still at UNDERCLOCK lowers trace" is a wash | **ACCEPTED.** With base 0.18 %/s: 0.18 × 0.5 = +0.09 against a −0.20 credit = **net −0.11 %/s**. Stated with the arithmetic in both §5 and §9. |
| 14 | Trace start has two sources of truth; death penalty uncapped | **ACCEPTED verbatim.** §9: `start = min(trace_carry_cap, trace_start + 5·over_par + 10·deaths)`, `trace_carry_cap` the single authority, shipping at 25 on every level. |
| 15 | The ledger books 10 textures; the legend needs 15 | **ACCEPTED, and bought back.** §17.4 books **13** + a pip-overlay strip = 269,312 B: 17/18/19 share one texture with the pip count as a decal (the reviewer's own saving), and the Sentry needs **no** wall texture because finding 4 kept it a sprite. Headroom is restated honestly at **76,464 B (~75 KB, 7.3%)** (after the art pass's 6,912-byte HUD row), with a named buy-back order, and the word "Comfortable" is removed from the RAM paragraph. |
| 16 | Doors + auto-close + melee roster = free invulnerability | **ACCEPTED verbatim.** §8: Watchdogs and Tracers in ALERT/CHASE/FLEE open variant 16 by contact with the player's predicate; 17–19 and 22 stay shut to them. §10.2: the OPEN timer resets while any body is within 1.5 cells. |
| 17 | Locked doors have no latch rule | **ACCEPTED verbatim.** §10.2: a locked door opened with its token **latches to variant 16** for the sector; the trace charge fires once per door per sector. |
| 18 | Spike's per-cell occupancy misses straddling enemies | **ACCEPTED verbatim.** §7: each entity registers in **every cell its 0.3-cell disc overlaps** (≤ 4), hits de-duplicated by entity id along the walk. |
| 19 | Input is never latched | **ACCEPTED.** New §4.2: the VBL ISR latches sticky `pressed_since_last_tick` / `released_since_last_tick` plus a `held_vbls` counter; the sim consumes and clears them. (The risk shrank when finding 7 deleted the duration-keyed modifier layer, but the latch is still required for edge-triggered fire and is the prerequisite for §4.3's replay goldens.) |
| 20 | Sim/render concurrency unspecified | **ACCEPTED verbatim.** New §4.1 mandates a catch-up loop (1–2 ticks between frames) plus a single-copy 512-byte render snapshot taken before the DDA; the renderer never reads live entity state. |
| 21 | The audio priority rule makes firing silence the kill | **ACCEPTED.** §16: Buster sample **0.10 s** (half its 0.20 s rate, so the channel idles), snarl → priority **1**, token grab → **2**, enemy dissolve → **2**. The `>=` semantics are stated without ambiguity: an equal-priority newcomer **does** preempt. |
| 22 | Two mandated sounds missing from the table | **ACCEPTED, plus a third.** §16 adds **door refusal tone** (0.15 s, pri 2), **throttle change** (0.20 s, pri 1) and **gate close** (0.30 s, pri 1); the table sums to **5.45 s** in a 7.0 s bank. The YM forms of every cue are specified for the YM-only first playable. |
| 23 | The HUD is a first-playable deliverable and unspecified | **ACCEPTED verbatim.** New §15.1 enumerates all seven fields with screen x/width, defines the compass and the message line, mandates a blit-once panel with dirty-rect planar writes on 16-pixel boundaries outside the c2p region, and gives the HUD **its own row** in §17.3's budget table. |
| 24 | No determinism contract | **ACCEPTED verbatim.** New §4.3: one named LCG seeded from a new `rng_seed` header field, all AI randomness from it, an FNV-1a per-tick state hash, and pinned 600-tick (level 1) and 900-tick (level 2) replays in `test/`. Item 10 of §18's first-playable list. |
| 25 | The first playable has no defined ending | **ACCEPTED verbatim.** §15 adds the **SECTOR CLEAR** overlay and the **RUN COMPLETE** screen (after level 2 in the first playable); §9 defines the deferred-Hunter 100% behaviour as HARDENED palette + the death path. All three are in §18. |
| 26 | No hit or pickup feedback at all | **ACCEPTED.** §10: a 2-frame full-screen palette flash — one 16-word write shifting both wall ramps toward register **13** (orange) on damage and toward register **12** (white) on pickup — in the first playable. It touches only registers 1–10, so §3's variant invariant holds and both gates still pass. |
| 27 | `tools/mklevel.py` is a prerequisite and not in the ladder | **ACCEPTED verbatim.** It is **item 0** of §18, shipping with its validator as unit tests over both maps. |
| 28 | One 480,000-cycle column cannot serve two frame-rate targets | **ACCEPTED, including the PAL correction.** §17.3 carries **two** budget rows: 160 columns → 3 VBLs → **480,000** → 16.7 fps (≥ 14 ✓); 80 columns → 2 VBLs → **320,000** → 25 fps (≥ 20 ✓). The reviewer's point that there is no 20 fps on a 50 Hz flip lock is adopted, so the 80-column budget is 320,000, not 400,000. |
| 29 | OVERCLOCK's payoff is not visible at 20 cells | **ACCEPTED, reviewer's second option.** §17.1's table makes it arithmetic: at 20 cells a 1-cell billboard is **3.2 chunky rows**. §5 drops the "iris readable at range" claim and gives the Sentry a **1-pixel state light** — register **14** (green) when the iris is closed, register **13** (orange) when charging or open. A colour, not a shape; and because §3 exempts 12 and 13 from fogging, the light does not dim with distance either. |
| 30 | 32×32 sprite source under-resolved | **ACCEPTED, and settled before art.** §8 / §17.4: enemies and anchors are authored at **64×64** (1:1 with a wall face at d = 1.0, never upscaled beyond 1.7× at contact range); pickups stay 32×32 at half cell height, where they are never large. Cost is booked: 180,224 + 22,528 B. |
| 31 | Level 1 does not deliver the lesson §12 claims | **ACCEPTED verbatim.** Watchdogs moved from (22,14), (24,19), (27,20), (4,21) to **(26,17), (24,19), (27,20), (25,21)** — every pairwise distance 2.24–4.12 cells, inside one 6-cell wake cluster in the east kennel, exiting through the row-16 gap in a line. The west room's dog is deleted; the `i` pickup it guarded stays. §12's prose is updated to match. |
| 32 | Joystick-only players cannot pause or abort | **ACCEPTED by removing the claim, not by adding a gesture.** Finding 7 already requires Alt on the keyboard for strafe, so a keyboard is in hand. §6 states plainly that P, Esc, 1/2 and 7/8/9 are keyboard-only and that the game is completable with **joystick + Alt** — no hidden stick chord is added, because a hidden chord is what finding 7 was about. |

### NITs

| # | Finding | Resolution |
|---|---|---|
| 33 | Front matter says §16 for the cycle table | **FIXED** — front matter now says §17. |
| 34 | Sample bank arithmetic off by 216 B | **FIXED** — §16/§17.4 book **7.0 s × 12,517 Hz = 87,619 B**, buffer **87,808 B (85.75 KiB)**, with the arithmetic printed. |
| 35 | Stack aisles are 3 wide, and there is a free 4-wide flank lane | **FIXED** — a sixth column run added at x = 27 in rows 6, 9, 12, 15, so the lattice reaches the east wall and the flank margin is 3 cells like every other aisle. §13 now says "3 cells wide and 2 cells tall", §2 and §13 say **twenty-four** columns. |
| 36 | Level 1's exit opens into a 4-cell dead pocket | **FIXED** — the exit moved to the border at **(15,0)** (finding 6) and the pocket collapsed to a single 1-cell throat at (15,1) with a gap at (15,2). No dead ends; validator reports zero warnings. |
| 37 | Level 2 dead-end cells at (25,2) and (28,2) | **FIXED** — the exit alcove narrowed to (26,2)–(27,2) with the exit at the border **(27,0)**. Both dead ends gone. |
| 38 | Cyan ramp steps 35/52/56/57 are unevenly spaced | **FIXED by the art pass's ramp.** Cyan is Y 199.3 / 162.1 / 123.2 / 80.5 / 46.6 — steps **37 / 39 / 43 / 34** — and it interleaves with the magenta ramp rather than running beside it, with a **minimum cyan-to-magenta gap of 16.0 Y in every band** and a minimum chroma distance of 41.5. The 25% threshold's "one rung darker" is `shade_table(1)`, a remap of the same ramp, so it cannot compress it further. |
| 39 | Brad-to-compass mapping never stated | **FIXED** — §11: brad 0 = north = −y, increasing clockwise (256 east, 512 south, 768 west); +y is south. |
| 40 | Unstated whether 7/8/9 incur the throttle input lock | **FIXED** — §5 and §6 both state the 12-tick lock applies to the direct keys, so the keyboard is never mechanically better than the stick. |
| 41 | "8 compiled levels (≤ 4.6 KB each)" | **FIXED** — §11 computes 42 + 2,304 + 320 = **2,666 B ≈ 2.7 KB** for a 48×48 level; §17.4's disk paragraph agrees. |
| 42 | §2 says the Stack is watched from the north wall (singular) | **FIXED** — §2 now reads "watched from two recessed alcoves", matching §13 and the map. |
| 43 | The IKBD boot sequence is not named where the controls live | **FIXED** — §6 opens by naming `$12` (mouse off) and `$14` (joystick event reporting), per `BRIEF.md`. |

### Palette addendum — the art pass supersedes §3 as first drafted

While v2 was being written, the concept-art pass shipped `art/ART_DIRECTION.md` with a **final,
measured palette**, and the orchestrator ruled it authoritative. It wins, and every register index
in this document is now its numbering. What changed against the palette v2 first drafted:

- **Two reserved registers, not five.** Only **12 (white)** and **13 (orange)** are wall-forbidden.
  Data yellow (11), integrity green (14) and both magenta rungs return to the walls — which is what
  lets `circuit_lattice` carry live vias, the door carry hazard bands and `exit_gate` be green.
- **Index mapping applied throughout:** old 12 green → **14**; old 13 white → **12**; old 14 alarm
  → **13**; old 15 grid → **15** (now slate `#333355`, and also the **sprite transparency key**).
  Both ramps have new hex values; §3 carries the table verbatim from `ART_DIRECTION.md` §3.
- **The gate is measured, not asserted.** The design's `MIN_ACCENT_DELTA_Y = 40` is withdrawn in
  favour of `rimtest.py`'s **≥ 24 Y over 400 sprite × wall × band combinations (worst measured
  31.3 Y, 0 failures, 0.0 Y with the rim deleted)** and `palette.py`'s **≥ 16 Y / ≥ 40 chroma**
  ramp separation (measured 16.0 Y / 41.5). The actual thresholds are stated in §3; where the art's
  numbers are below 40, the art's numbers are the gate, because they are measured over the art that
  ships.
- **Register 15 is legal in walls and the HUD but never a sprite colour** — sprites' 15s are holes,
  and sprite shading goes through `drawlib.shade_sprite`, which preserves the key.
- **Depth fog is `palette.shade_table(band)`**, an index remap, baked into §17.4's bands by the
  loader so the inner loop still pays one fetch. 12 and 13 never fog; 11 and 14 hold three bands.
- **HUD** — `ART_DIRECTION.md` §5's layout is the shipped one (§15.1): a 320×40 planar strip at
  1:1 on the bottom 40 lines, **64-glyph** 8×8 font in register 12, no raster split. The ledger row
  drops from 12,544 to **6,912 B** and headroom rises to **76,464 B (~75 KB)**.
- **One honest gap carried forward:** reserved orange (13, Y 150.0) is only 3.3 Y from wall-legal
  green (14, Y 146.6), and `rimtest.py` does not cover core-against-wall adjacency. Named in §3.
- **One authoring constraint carried forward:** green fogs out at band 3, so exit gates must be
  placed inside band 2 — now compiler warning 9 (§11).

### Reviewer suggestions considered and **not** adopted

- **Two-tone (white + black) rim** (finding 10a). Rejected: the rebuilt palette guarantees ΔY ≥ 40
  against every wall register, so the inner black edge buys nothing and costs a source pixel on
  every silhouette at 64×64.
- **Sentry as a wall-texture override** (finding 4, reviewer's recommendation). Rejected in favour
  of the orchestrator's alcove entity: it keeps the sprite count at 33, avoids +61,440 B of panel
  textures the ledger cannot now afford, and needs no change to the shipped Sentry positions.
- **Drop the 75% and 100% palette thresholds from the first playable** (reviewer's closing note).
  Rejected: finding 11's fixed-luminance rule removes the readability objection, and finding 25
  gives 100% a defined behaviour. Both stay in.
- **Drop the title screen** (reviewer's closing note). Rejected: it is one static planar screen and
  it is where the mission brief — the entire tone of the game — is delivered.
- **Make Spike an automatic alternate fire ≥ 8 cells** (finding 7's second half). Rejected: Spike
  is deferred past the first playable, and an automatic weapon swap is the same class of surprise
  as the modifier layer this finding deleted. Keyboard 1/2 stays explicit.
