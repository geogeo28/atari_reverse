# BLACK ICE — levels 3 to 8

Authored against `design/DESIGN.md` §2 (sector identities), §8 (enemy sight and pack sizes),
§10 (doors and pickups), §11 (level format and legend) and §14 (the eight-level table).
Levels 1 and 2 are printed in DESIGN.md §12–13 and are owned elsewhere; they are listed in the
table below only because `validate_levels.py` was run over them read-only.

Every map is a `# key: value` header followed by the map block. Header keys are the binary field
names from §11 (`sector`, `palette_variant`, `texture_set`, `start_x/y`, `start_facing`,
`trace_base_rate`, `trace_start`, `trace_carry_cap`, `par_ticks`, `entity_count`) plus the three
roster counts (`watchdogs`, `sentries`, `tracers`) so the §14 table is checkable from the file, and
free-form `note` lines. `start_facing` is in brads with **0 = north**.

---

## 3 — NURSERY (40×40, DEGRADED, par 3:00)

The first sector that is visibly ill, and the first with real Tracer pressure. You arrive in a quiet
arrival chamber, walk a two-cell ingress north, and the level opens into one shape you will hold in
your head for the rest of the run.

**Landmark — the Fork Ring.** A 17×17 hall built as a three-cell-wide corridor around a solid glyph
core, with eight identical spurs radiating from it, two per side. Seven are dead. Walking the ring
is walking a loop with no landmarks except the spurs, which is the joke: the process spawner forked
eight times and only one child ever ran. Two Sentries are recessed into the core's north and west
faces, so each covers a fifteen-cell straight corridor — the ring punishes running the loop blind.
Corruption is in the geometry: the south-east spur's body is authored one cell east of its mouth, so
the corridor visibly jogs, and the north-east spur's mouth is a `~` door frozen at 3/8 — you can see
straight down a spur you will never walk. Noise texture (`?`) eats patches of the ring shell and the
heart of the core.

**Critical path.** Arrival chamber → ingress → ring south corridor → round the core → **ALPHA** in
the deep west spur → **BETA** in the deep east spur → door `1` at the ring's north live spur → the
Spawn Gallery (four Watchdogs and a wall Sentry in a 30×7 hall — the tension peak) → door `2` →
vestibule → exit. The first enemy is a Watchdog in the ring's *north* half; the south corridor is
deliberately empty, so the opening 20-odd cells are safe and the core blocks line of sight until you
commit to a side.

## 4 — BAD BLOCK (40×40, CORRUPT, par 3:00)

The first corrupt sector, and the level that teaches you to read corruption as information. It is
built as one long snake so that the set-piece is crossed twice, once from each side.

**Landmark — the Shear.** The page was written twice and the copies never merged. Copy A runs
east–west at y=18,19; copy B runs at y=15,16 and starts one cell further west — the drift is visible
the moment you enter. The seam between them carries five `~` doors frozen at 3/8: for twenty-four
cells you walk copy A looking through slits into copy B, which is the half that leads out, and you
cannot cross. The two copies join only at the far east, where the write finally caught up. Texture
mismatch runs the length of both faces (`=`, `%`, `?` alternating on a single wall run).

**Critical path.** Arrival chamber → east corridor → the Page Frame → the Duplicate (**ALPHA**) →
back west → supply vault → door `1` → copy A, east past the five frozen slits, watched from its far
cap by a Sentry with a twenty-four-cell sightline → the east riser → copy B, west, picking up
**BETA** → door `2` → the west spine → the North Hall, thirty-four cells of open room with four
Watchdogs and a wall Sentry between you and the gate → exit. The Page Frame pack is placed off the
entry corridor's sightline so the first ~26 cells are safe.

## 5 — THE CHOIR (40×40, DEGRADED, par 3:15)

The wide-room level. Rooms here are too big to underclock through: at render radius 6 the Sentries
in the far wall are simply not drawn, and they are still shooting. First GAMMA token.

**Landmark — the Switchboard.** A thirty-one-cell run of dead lines forming the north wall of a
30×14 hall, faked entirely in texture (bus-trunk `|` with mismatched `=` and `?` runs, no geometry
cost). Three Sentries are recessed into its face, spaced eight cells apart so no two can be silenced
from one position, and the hall is broken by a 5×3 lattice of single-cell glyph columns that gives
you cover without giving you a corridor. A `~` in the hall's south wall opens onto a sealed void —
a line that terminates nowhere — and the east riser jogs one cell where it climbs past the
Switchboard.

**Critical path.** Arrival chamber → junction → West Sub-hall (**ALPHA**, guarded by a fourth Sentry
niched into its long west wall) → up into the hall, across the Switchboard's face → door `1` in the
hall's east wall → the riser → the Exchange (**BETA**) → door `2` through the north band divider →
the Line Vault (**GAMMA**) → door `3` → vestibule → exit. The East Sub-hall is pure exploration:
supplies, a Tracer and two Watchdogs, never on the path.

## 6 — DEAD LETTER (48×48, CORRUPT, par 3:30)

The level about *which stamp you are standing in*. It is the densest Watchdog count in the game and
the one place where reading the room wrong costs you a whole lap.

**Landmark — the Undeliverable.** One 9×9 room stamped four times in a 2×2 block. Each stamp is
geometrically identical: the same shell, the same bad texture run, a wall gap at the centre of each
of its four walls, and the same single-cell alcove two cells in from the north-west corner. Only the
contents differ — one alcove still holds its Sentry, two hold caches, one is empty. Six of the eight
outward gaps open onto `~` doors frozen over sealed voids; one is the way in and one is the way out.
From stamp C you can see straight up the frozen link into stamp A and the exit gate behind it, for
the whole time you are walking the long way round. Both junctions into the quad drift a cell.

**Critical path.** Arrival chamber → west corridor → the West Wing (**ALPHA**) → back → the Spool
Hall (four Watchdogs, a Sentry in its north bulkhead) → the drifted approach → door `1` → **stamp C**
→ the free east link → **stamp D** (**BETA**) → door `2` north → **stamp B** (**GAMMA**, and the one
Sentry still in its alcove) → door `3` west → **stamp A** → exit. The East Vault and the Postmark
Room up the riser are optional and hold the best supplies.

## 7 — COLD STORE (48×48, DEGRADED, par 3:30)

The densest Sentry layout in the game, and the level where OVERCLOCK pays for itself: at radius 20
you can read every iris state around the ring before you step into it, and at radius 6 you cannot.

**Landmark — the Carousel.** A four-cell-wide ring corridor around a central well, with eleven 3×3
tape bays opening off it — three north, three each side, two south — plus the one you arrive
through. The well is a two-cell-thick casing around a 4×4 chamber holding the level's best supplies,
entered through a single plain door and a one-cell throat. Four Sentries are recessed into the four
faces of that casing, one down each ring corridor, so there is no lap of the ring that is not
covered by something. Frost damage (`?`) has eaten the run above the carousel.

**Critical path.** Arrival chamber → the south entry bay → the ring → the middle west bay opens into
the **West Annex** (**ALPHA**) on a seventeen-cell straight sightline that ends at the well's west
Sentry → back around the ring → door `1` off the middle east bay → the **East Annex** (**BETA**) →
door `2` above the middle north bay → the **North Annex** (**GAMMA**, four Watchdogs and a fifth
Sentry covering its length) → door `3` → exit chamber → exit. The well is optional and expensive.

## 8 — THE KERNEL (48×48, KERNEL palette, par 4:00)

Terminal corruption. You start at the top for the only time in the game and descend, and the level
narrows the whole way: a hall, a ring, a table, a chamber.

**Landmark — the Anchor Chamber.** A 22×12 room whose long axis is east–west, which is the axis the
Black ICE mirrors you across. Four anchor pylons (`*`, 60 HP each) stand as mirrored pairs, and two
decorative pylons (`A`) sit on the same mirror line, so the room states its own rule in geometry.
Two Sentries are recessed into its north and south walls. Elsewhere the sector is failing openly:
three `~` doors frozen over sealed voids, noise texture on every seam, and the wing that runs down
the west edge separated from the chamber by a single corrupted column.

**Critical path.** Arrival chamber → the bent approach corridor (long, so the first room is earned)
→ the Supervisor Hall, watched from its west wall by a Sentry looking straight down eighteen cells
at door `1` → the west wing (**ALPHA**) → door `1` → the Scheduler Ring (**BETA**, two Sentries) →
door `2` → the Page Table (**GAMMA**) → door `3` → the Anchor Chamber → break four anchors while the
ICE is not standing at them → exit.

---

## Validator summary

`python3 validate_levels.py` — run from this directory; it checks every `*.txt` here.

```
file          name           size     floor   walls   W    S    T    enemy   pick   tok   door   path 
------------------------------------------------------------------------------------------------------
level03.txt   NURSERY        40x40    488     1107    8    3    2    13      8      2     5      57   
level04.txt   BAD BLOCK      40x40    745     845     8    2    4    14      7      2     10     119  
level05.txt   THE CHOIR      40x40    964     629     10   4    3    17      6      3     7      85   
level06.txt   DEAD LETTER    48x48    937     1354    12   3    4    19      6      3     13     84   
level07.txt   COLD STORE     48x48    1023    1274    12   5    4    21      6      3     7      65   
level08.txt   THE KERNEL     48x48    1128    1167    10   6    4    25      6      3     9      74   
level1.txt    INGRESS        32x32    309     711     4    1    0    5       6      1     4      26   
level2.txt    THE LEDGER     32x32    458     561     5    2    2    9       6      2     5      39   

floor/walls = cells; W/S/T = Watchdog/Sentry/Tracer; enemy includes anchors and Black ICE;
path = shortest start->exit walk once the gates you earn are open (token detours not counted).

8 level(s) checked, 8 passed, 0 failed
```

## Notes on the legend, and how ambiguities were resolved

- **`s` Sentry.** DESIGN.md §11 says the cell becomes wall 8. Per the orchestrator's design-review
  correction, a Sentry is instead an **entity on an empty floor cell**, placed in a one-cell alcove
  recessed into a wall (three wall neighbours, one open side). The validator enforces exactly that.
  `X` (8, exit plating) stays a wall texture.
- **Door jambs.** §11 says "wall jambs on exactly two opposite sides". Read as: exactly one of the
  two axes has both neighbours solid, and the other axis has both neighbours open. The sector exit
  and the sealed arch are exempt on the side that abuts the outer border, which is how both shipped
  maps in §12–13 are drawn.
- **`>` and `S` on the border.** Neither is placed *in* the border in DESIGN.md's own maps, so the
  border here is solid wall everywhere and terminal gates sit one cell inside it.
- **`start_facing`.** §11 gives brads 0..1023 but never fixes north. **0 = north** throughout;
  level 8 starts facing south (512).
- **One-cell dead stubs.** The general rule is to avoid pockets that trap enemies. DESIGN.md §2
  device 1 explicitly *requires* them in corrupted sectors ("corridors mis-join and leave 1-cell
  dead stubs"), so levels 4, 6 and 8 carry them deliberately: the drifted junctions in DEAD LETTER
  and the stamp gaps that back onto frozen doors. They are wall recesses, never corridor ends, so a
  chasing Watchdog re-pathing at a cell centre cannot jam in one. Levels 3, 5 and 7 have none except
  the ends of the exit vestibule, which matches the shape used in §12–13.
- **`entity_count`.** §11 counts entities as the 5-byte records after the grid, so pickups, tokens,
  anchors and the Black ICE are counted alongside enemies. `watchdogs`/`sentries`/`tracers` are
  extra header keys so the §14 roster can be checked mechanically; they are optional to the parser.
- **`trace_base_rate`.** §9's "+0.4 %/s" at the 25 Hz sim tick is 16 thousandths of a percent per
  tick, so every level ships `trace_base_rate: 16`. `trace_start` is 0 (the carry-over in §9 is
  applied at runtime) and `trace_carry_cap` is 25, the §9 cap.
