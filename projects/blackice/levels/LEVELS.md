# BLACK ICE — levels 3 to 8

Authored against **`design/DESIGN.md` v2**: §2 (sector identities), §8/§8.1 (enemy sight, pack
sizes, the BFS distance field), §9/§9.1 (the trace meter and its reference-run tuning), §10
(doors and pickups), §11 (level format, the eight compiler rules, the legend) and §14 (the
eight-level table). Levels 1 and 2 are printed in §12–13 and are owned by the engine agent; they
appear in the table below only because `validate_levels.py` was run over them read-only.

Every map is a `# key: value` header followed by the map block. Header keys are the §11 binary
field names — `sector`, `palette_variant`, `texture_set`, `start_x/y`, `start_facing`, `rng_seed`,
`trace_base_rate`, `trace_start`, `trace_carry_cap`, `par_ticks`, `entity_count` — plus the three
§14 roster counts (`watchdogs`, `sentries`, `tracers`) so the roster is checkable from the file,
plus free-form `note` lines. Per §11: **brad 0 = north**, increasing clockwise (256 east, 512
south, 768 west); `trace_base_rate` is **thousandths of a percent per second** and ships at **180**
(0.18 %/s) on every level per §9.1; `trace_carry_cap` is 25 on every level per §9.

Per §11 rule 4, **every `S` and every `>` is an arch in the outer wall** — on the border, with
exactly one open neighbour — and every ordinary door has exactly two opposite open neighbours.

---

## 3 — NURSERY (40×40, DEGRADED, par 3:00, seed 3003)

The first sector that is visibly ill, and the first with real Tracer pressure. You arrive through
the cold-boot arch in the south wall, walk a two-cell ingress north, and the level opens into one
shape you will hold in your head for the rest of the run.

**Landmark — the Fork Ring.** A 17×17 hall built as a three-cell-wide corridor around a solid glyph
core, with eight identical spurs radiating from it, two per side. Seven are dead, and each dead spur
is a two-cell-wide run that **narrows to a single cell at its end** — the process that never
started. §14 names those stubs as the accepted case of §11 warning 8 and asks the designer to sign
them off in the header; the six that trip the warning are signed off in `level03.txt`'s `note`
lines, and §8.1's BFS distance field cannot jam in one. Two Sentries sit in alcoves recessed into
the core's north and west faces, each covering a fifteen-cell straight corridor. Corruption is
geometry: the south-east spur's body is authored one cell east of its mouth and its stub drifts
again, so the corridor visibly staircases; the north-east spur's mouth is a `~` jammed at 3/8 —
you see straight down a spur you will never walk. Noise texture eats the ring shell and the core's
heart.

**Critical path.** Arrival chamber → ingress → ring south corridor → round the core → **ALPHA** in
the deep west spur → **BETA** in the deep east spur → door `1` at the ring's north live spur → the
Spawn Gallery (four Watchdogs and an alcove Sentry in a 30×7 hall — the tension peak) → door `2` →
throat → exit arch. The first enemy is in the ring's *north* half; the south corridor is
deliberately empty and the core blocks line of sight until you commit to a side.

## 4 — BAD BLOCK (40×40, CORRUPT, par 3:00, seed 4004)

The first corrupt sector, and the level that teaches you to read corruption as information. Built as
one long snake so the set-piece is crossed twice, once from each side.

**Landmark — the Shear.** The page was written twice and the copies never merged. Copy A runs
east–west at y=18,19; copy B runs at y=15,16 and starts one cell further west — the drift is visible
the moment you enter. The seam carries five `~` doors jammed at 3/8: for twenty-four cells you walk
copy A looking through slits into copy B, the half that leads out, and you cannot cross. The copies
join only at the far east, where the write finally caught up. Texture mismatch runs the length of
both faces.

**Critical path.** Arrival chamber → east corridor → the Page Frame → the Duplicate (**ALPHA**) →
back west → supply vault → door `1` → copy A, east past the five jammed slits, watched from its far
cap by a Sentry with a twenty-four-cell sightline → the east riser → copy B, west, picking up
**BETA** → door `2` → the west spine → the North Hall, thirty-four cells of open room with four
Watchdogs and an alcove Sentry between you and the arch → exit. The Page Frame pack sits off the
entry corridor's sightline, so the first ~26 cells are safe.

## 5 — THE CHOIR (40×40, DEGRADED, par 3:15, seed 5005)

The wide-room level. Rooms here are too big to underclock through: at render radius 6 the Sentries
in the far wall are simply not drawn, and they are still shooting. First GAMMA token.

**Landmark — the Switchboard.** A thirty-one-cell run of dead lines forming the north wall of a
30×14 hall, faked entirely in texture (bus trunk with mismatched hex-mesh and noise runs, no
geometry cost). Three Sentries sit in alcoves recessed into its face, spaced eight cells apart so no
two can be silenced from one position, and a 5×3 lattice of single-cell glyph columns gives cover
without giving a corridor. A `~` in the hall's south wall opens onto a sealed void — a line that
terminates nowhere — and the east riser jogs one cell as it climbs past the Switchboard.

**Critical path.** Arrival chamber → junction → West Sub-hall (**ALPHA**, guarded by a fourth Sentry
alcoved into its long west wall) → up into the hall, across the Switchboard's face → door `1` in the
hall's east wall → the riser → the Exchange (**BETA**) → door `2` through the north band divider →
the Line Vault (**GAMMA**) → door `3` → vestibule → exit arch. The East Sub-hall is pure
exploration: supplies, a Tracer and two Watchdogs, never on the path.

## 6 — DEAD LETTER (48×48, CORRUPT, par 3:30, seed 6006)

The level about *which stamp you are standing in*. The densest Watchdog count in the game, and the
one place where reading the room wrong costs a whole lap.

**Landmark — the Undeliverable.** One 9×9 room stamped four times in a 2×2 block. Each stamp is
geometrically identical: the same shell, the same bad texture run, a wall gap at the centre of each
of its four walls, and the same single-cell alcove two cells in from the north-west corner. Only the
contents differ — **three of the four alcoves hold a Sentry, and stamp A's, the exit stamp's, stands
empty with a cache in it**. Six of the eight outward gaps open onto `~` doors jammed over sealed
voids. From stamp C you look straight up the jammed link into stamp A and out through its north
gap — onto another jammed door: the way out is A's *west* gap, and it is bent so the arch is first
seen from three cells (§11 warning 9). Both junctions into the quad drift a cell. Six warning-8
pockets, signed off in the header: three sealed voids, the empty alcove, two drifted stubs.

**Critical path.** Arrival chamber → west corridor → the West Wing (**ALPHA**) → back → the Spool
Hall (four Watchdogs) → the drifted approach → door `1` → **stamp C** → the free east link →
**stamp D** (**BETA**) → door `2` north → **stamp B** (**GAMMA**) → door `3` west → **stamp A** →
the bent west throat → exit arch. The East Vault and the Postmark Room up the riser are optional and
hold the best supplies.

## 7 — COLD STORE (48×48, DEGRADED, par 3:30, seed 7007)

The densest Sentry layout in the game, and the level where OVERCLOCK pays for itself: at radius 20
you read every iris state around the ring before you step into it, and at radius 6 you cannot.

**Landmark — the Carousel.** A four-cell-wide ring corridor around a central well, with eleven 3×3
tape bays opening off it — three north, three each side, two south — plus the one you arrive
through. The well is a two-cell-thick casing around a 4×4 chamber holding the level's best supplies,
entered through a single plain door and a one-cell throat. Four Sentries sit in alcoves cut into the
four faces of that casing, one down each ring corridor, so no lap of the ring is uncovered. Frost
damage has eaten the run above the carousel.

**Critical path.** Arrival chamber → the south entry bay → the ring → the middle west bay opens into
the **West Annex** (**ALPHA**) on a seventeen-cell straight sightline ending at the well's west
Sentry → back around the ring → door `1` off the middle east bay → the **East Annex** (**BETA**) →
door `2` above the middle north bay → the **North Annex** (**GAMMA**, four Watchdogs and a fifth
Sentry covering its length) → door `3` → exit chamber, whose single glyph column stands in the
gate's line so the arch is first seen from six cells → exit. The well is optional and expensive.

## 8 — THE KERNEL (48×48, KERNEL palette, par 4:00, seed 8008)

Terminal corruption. You start at the top for the only time in the game — the arch is in the north
wall and `start_facing` is 512, south — and descend, and the level narrows the whole way: a hall, a
ring, a table, a chamber.

**Landmark — the Anchor Chamber.** A 22×12 room whose long axis is east–west, which is the axis the
Black ICE mirrors you across. Four anchors (`*`, free-standing floor entities with a 0.4-cell solid
disc, 60 HP each) stand as mirrored pairs, and two decorative pylons (`A`, wall texture 7) sit on
the same mirror line, so the room states its own rule in geometry. Two Sentries are alcoved into its
north and south walls; the southern one flanks the exit throat. Elsewhere the sector fails openly:
three `~` doors jammed over sealed voids, noise texture on every seam, and the west wing separated
from the chamber by a single corrupted column.

**Critical path.** Arrival chamber → the bent approach corridor (long, so the first room is earned)
→ the Supervisor Hall, watched from its west wall by a Sentry looking straight down eighteen cells
at door `1` → the west wing (**ALPHA**) → door `1` → the Scheduler Ring (**BETA**, two Sentries) →
door `2` → the Page Table (**GAMMA**) → door `3` → the Anchor Chamber → break four anchors while the
ICE is not standing at them → the south throat → exit arch.

---

## Validator summary

`python3 validate_levels.py` — run from this directory; it checks every `*.txt` here against the
eight §11 rules and the two §11 warnings.

```
file          name          size     floor   walls   W    S    T    enemy   pick   tok   door   path   warn   lock order            
------------------------------------------------------------------------------------------------------------------------------------
level03.txt   NURSERY       40x40    480     1115    8    3    2    13      8      2     5      58     6      [ALPHA,BETA]
level04.txt   BAD BLOCK     40x40    747     843     8    2    4    14      7      2     10     120    0      [ALPHA] [BETA]
level05.txt   THE CHOIR     40x40    966     627     10   4    3    17      6      3     7      86     0      [ALPHA] [BETA] [GAMMA]
level06.txt   DEAD LETTER   48x48    926     1365    12   3    4    19      6      3     13     90     6      [ALPHA] [BETA] [GAMMA]
level07.txt   COLD STORE    48x48    1020    1277    12   5    4    21      6      3     7      67     0      [ALPHA] [BETA] [GAMMA]
level08.txt   THE KERNEL    48x48    1131    1164    10   6    4    25      6      3     9      77     0      [ALPHA] [BETA] [GAMMA]
level1.txt    INGRESS       32x32    309     711     4    1    0    5       6      1     4      26     2      [ALPHA]
level2.txt    THE LEDGER    32x32    458     561     5    2    2    9       6      2     5      39     2      [BETA] [ALPHA]

floor/walls = cells; W/S/T = Watchdog/Sentry/Tracer; enemy includes anchors and Black ICE;
path = shortest start->exit walk once the gates you earn are open (token detours not counted);
warn = rule 8 one-cell pockets; lock order = the token order the flood fill proved.

8 level(s) checked, 8 passed, 0 failed  (level1/level2 re-authored from DESIGN v2 §12-13 in the gameplay wave)
```

`level1.txt` / `level2.txt` were re-authored glyph-for-glyph from DESIGN v2 §12–13 after this table was first written; they now pass every rule.

## Notes on the legend, and how ambiguities were resolved

- **`s` Sentry (v2 §11 rule 5).** A Sentry compiles to an empty cell plus an entity and must sit in
  a one-cell alcove with **exactly three wall neighbours and one open neighbour**. `X` alone owns
  texture 8. Enforced literally, counting only true wall glyphs toward the three.
- **`*` anchor (v2).** No longer wall texture 7: a free-standing floor entity with a 0.4-cell solid
  disc. It is placed on floor and validated as a floor entity. `A` remains the decorative pylon wall.
- **Terminal doors (rule 4).** `S` and `>` must lie on the border with exactly one open neighbour;
  no other variant may sit on the border. All twelve gates across levels 3–8 were moved onto the
  border, each behind a one-to-three-cell throat, which also collapsed the old exit vestibules that
  would otherwise trip warning 8.
- **Ordinary doors (rule 3).** Exactly two opposite open neighbours. A closed door is not a gap, so
  a door never counts as another door's open neighbour.
- **Warning 8 (one-cell pockets).** Counted with doors treated as passable — that is the reading
  under which §12–13's own maps report zero warnings. Levels 4, 5, 7 and 8 are warning-free. Levels
  3 (6) and 6 (6) carry deliberate pockets that §2 device 1 and §14 explicitly ask for: dead-spur
  stubs, sealed voids behind jammed doors, drifted junctions, and one empty stamp alcove. Each is
  signed off in that level's `note` lines, per §14's instruction.
- **Warning 9 (gate seen past band 2) — WITHDRAWN in DESIGN v2.1** (integrity green no longer fogs at band 3, so
  the premise is gone; the validator no longer emits it). Kept for the record of what shaped levels 6 and 7: the
  straight unobstructed run of open cells out of the gate must be ≤ 9 cells, so the green arch is
  first seen inside band 2. Both §12–13 maps pass it (runs of 8 and 2), and it is what drove level
  6's exit to a bent west throat and put a glyph column in level 7's exit chamber.
- **Header keys.** §11 fixes the field names but not the text keys; the binary field names are used
  verbatim. Every key is range-checked against its §11 field width, and a `trace_base_rate` or
  `trace_carry_cap` away from the §9/§14 shipped value raises a warning rather than an error,
  because §9.1 keeps the rate per-level precisely so a playtest can move one level.
- **`entity_count`.** The count of 5-byte entity records: enemies, Sentries, anchors, Black ICE,
  tokens and pickups. `@` is not an entity.
- **`rng_seed`.** New in v2 (§4.3, finding 24). Distinct per level (3003 … 8008); the LCG is
  `x = x*1664525 + 1013904223`, so any non-zero seed is legal and the value is only a label.
