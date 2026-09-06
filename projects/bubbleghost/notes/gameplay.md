# Bubble Ghost — the in-room simulation

Everything below was read from bodies in `decomp.c` / `out/prg_dis.txt` at the project's load
base `0x10000` (Ghidra address == run-time address; `a4 = 0x24f1a`). Every name used below is
the one in [`names.txt`](../names.txt), which is the source of truth for this project; the
proposals this pass generated are in `out/names_gameplay.txt` and have been merged.

Companion docs: [`anchors.md`](anchors.md) (memory map, traps, sound install),
[`assets_survey.md`](assets_survey.md) (GHOST.DAT / GHOST.PRE / GHOST.DEM formats).

---

## 0. Three corrections to the existing notes — all landed in `names.txt`

* **`0x10f20` is not the attract/menu.** `names.txt` used to carry `attract_and_menu # ctx`; the body is
  a straight-line block of ~180 constant stores that writes the "all candles lit" defaults into
  the live object/room tables **and into both players' 58-word world-save blocks**. It is
  `reset_world_state`. The real menu is `0x115d6` (it prints `Press [G] …`), which the front-end
  slice owns.
* **`0x16a06` is not `set_screen_mode`.** It builds VDI `contrl[0] = 3` and calls the VDI trap:
  it is `v_clrwk`. (See §7 — the whole `0x168d4 … 0x16b12` block is a hand-rolled VDI binding, so
  `anchors.md`'s "no VDI drawing" is wrong: *all* of the game's drawing that is not a raw
  `move.l` loop goes through `vro_cpyfm`, `vr_recfl` and `v_gtext`.)
* **`anchors.md`'s "graphics/tables `0x171d2`–`0x1e8ca`, 30 KB inside TEXT" is `init_globals`.**
  That region is 7,787 `move.w #imm,(a1)+` instructions plus nine `adda.w #n,a1` skips over the
  zero runs — one contiguous initialiser stream starting at `0x16d92` and ending `rts` at
  `0x1e8c8`. Replaying it reconstructs the whole initialised BSS image, which is how every table
  in this document was dumped.

---

## 1. Screen model

| global | address | meaning |
|---|---|---|
| `screen_phys` | `0x23148` | `Logbase()` — the **displayed** screen |
| `screen_back` | `0x2314c` | `Logbase() - 32000` — the offscreen **work buffer**, and the VDI *logical* screen |
| `screen_rez` | `0x23146` | `Getrez()` result |

`init_gem_and_screens` (`0x10118`) takes `Logbase()` three times: rez → `0x23146`, logbase−0x7d00
→ `screen_back`, logbase → `screen_phys`. `game_top_loop` then issues
`Setscreen(log = screen_back, phys = screen_phys, 0)`, so **the VDI draws into `screen_back` while
`screen_phys` is displayed**; MFDB address `0` ("the screen") therefore means `screen_back`.

Layout of a frame, 320×200 low-res, 160 bytes/row:

```
rows   0..159   = the room:  5 tile rows x 10 tile columns of 32x32 tiles   (25,600 bytes)
rows 160..191   = the HUD:   1 tile row of 10 tiles (GHOST.DAT tiles 350..359)
row  189        = the BONUS bar, drawn with vr_recfl, x in [35, 318]
rows 192..199   = unused
```

Staging area: `screen_back - 0x6400` (25,600 bytes below the work buffer) is where the *next*
room is composed before it is wiped in.

### Coordinate units

The ghost and the bubble are 32×32 sprites addressed by their **top-left pixel**:

* `bubble_x` ∈ `[0, 288]`, `bubble_y` ∈ `[0, 128]` — one past those bounds is a room exit.
* `ghost_x` ∈ `[0, 286]`, `ghost_y` ∈ `[0, 126]` — derived from the mouse, §3.

`GHOST.DEM`'s six-byte record stores these divided down: **`(ghost_x/3, ghost_y/2, ghost_tile,
bubble_x/3, bubble_y/2, bubble_frame)`**, read back in the demo player at `0x119ee` as
`ghost_x = rec[0]*3`, `ghost_y = rec[1]*2`, `bubble_x = rec[3]*3`, `bubble_y = rec[4]*2`.
That closes `assets_survey.md`'s open question 4 (the file is played one record per drawn frame,
980 of the 1,000 records, with no `Vsync`).

---

## 2. The frame loop

`game_top_loop` (`0x101e6`) is: menu → per-turn setup → **room loop** → per-room loop → frame.

```
per room (0x106a0):
    room_number   = room_grid[grid_row][grid_col]         (§4)
    bubble_x      = room[room_number].entry[dir].x * 32
    bubble_y      = room[room_number].entry[dir].y * 32
    draw_room_to_stage()      0x13a08   compose the new room at screen_back-0x6400
    room_wipe_in()            0x13b1e   slide it down into screen_back, 4 rows x 40 steps
    draw_hud_row_tiles()      0x13712   HUD tiles 350..359 -> screen_back+0x6400
    hud_draw_counters()       0x113d2
    present_hud_row()         0x13224   work -> screen, 5,120 bytes at +0x6400
    ... new-room bonus, bar refill ...

    while (in_room && lives >= 0):
        game_frame_update()          0x12322   input, ghost, blow, bubble, collisions
        [every 20..69 frames: start the room's ambient sfx]
        save_sprite_backgrounds()    0x1342e   32x32 under ghost, 32x32 under bubble
        draw_sprites()               0x134f6   OR the ghost and bubble tiles in
        present_room()               0x13286   work -> screen, 25,600 bytes
        restore_sprite_backgrounds() 0x135d2   put the two 32x32 patches back
        objects_animate_and_draw()   0x1376e   tick + redraw the room's 10 object slots
```

So there is **one** composed background (the work buffer) and **no** double buffering of the
room: the two moving sprites are punched in, the whole room is copied to the visible screen,
and the punch is undone. The bonus bar and the counters are copied to the screen on their own,
row-scoped (`present_score_strip` `0x131f0` = 4,096 bytes at +0x6540; the bar copy is 160 bytes
at +0x7620 = row 189).

### `game_frame_update` (`0x12322`) in order

1. `bubble_frame`: `+1`, wrapping `12 → 4` (nine bubble frames).
2. `vq_mouse` → `mouse_buttons`, `mouse_x`, `mouse_y`; `vq_key_s` → `key_shift_state`.
3. `Crawio(0xff)` — a non-blocking key poll, and the only key reader in the play loop:
   `^P` = pause (loop on `Cconis` until `^P` again), `^S` = toggle `sound_enabled` (at `0x123ea`),
   `^R` = end the GAME (not the turn): it clears `level_complete`, sets `lives := −1` and zeroes
   `score`, `p1_score`, `p2_score`, `p1_playing` and `p2_playing`.
4. Ghost position from the mouse (§3).
5. Blow / idle (§3), including `Setcolor(15, …)`.
6. Ghost facing from the mouse buttons; `ghost_tile = facing*5 + anim_step`.
7. Fan check on object slots 3 and 4 (§5).
8. If the bubble is alive: `bubble_collision_probe()` (§6), then integrate
   `bubble_x += x_impulse + drift_vel_x/100`, `bubble_y += drift_vel_y/100`.
   If it is dead: the pop/respawn sequence.
9. Drift pulse: `drift_vel_x = drift_dir_x * drift_speed`, `drift_vel_y = drift_dir_y *
   drift_speed`, once every `drift_pulse` frames, with the speed decaying and `drift_interval`
   growing (§3).

---

## 3. The ghost, the blow and the bubble's motion

### Ghost position — the mouse, scaled by an FP divide

`game_frame_update` runs the Alcyon C float package on the raw `vq_mouse` output:

```
ghost_x = (int)( mouse_x / 1.115 )      normal rooms   (const at 0x2518a)
ghost_x = (int)( mouse_x / 1.684 )      room 35        (const at 0x25182)
ghost_y = (int)( mouse_y / 1.577 )                     (const at 0x25192)
```

`fp_acc_load_long` (`0x154b0`) pushes an int, `fp_dispatch(op, &fp_acc, &operand)` (`0x153fe`)
applies one operation and `fp_acc_to_long` (`0x154c0`) pops an int. The three opcodes the game
uses are **`0x803` = divide, `0x802` = multiply, `0x800` = add** — pinned by the attract mode's
own `Random()/16794009*34 + 1` and `Random()/16794009*11 + 5`, and by the ambient-sound
countdown `Random()*2.977e-6 + 20`. (The float package itself belongs to the C-library slice;
the opcode meanings are recorded here because the gameplay numbers depend on them.)

**What those three expressions actually range over**, because every one of them is truncated,
not rounded: XBIOS `Random` returns 24 bits, so its largest value is `0xffffff` = 16,777,215,
and `16777215 / 16794009 = 0.99900…` — strictly less than 1. `fp_acc_to_long` (`0x154c0`) calls
`fp_double_to_long` (`0x1550a`), whose only conversion step is `lsr.l d0,d1` on the mantissa:
a logical shift with no rounding term, so the fraction is **discarded toward zero**. Hence

| expression | real-valued range | after truncation |
|---|---|---|
| `Random()/16794009 * 11 + 5` | `[5, 15.989…]` | **5..15** slideshow rooms |
| `Random()/16794009 * 34 + 1` | `[1, 34.966…]` | **1..34** — the attract mode can never show room 35 |
| `Random() * 2.977e-6 + 20` | `[20, 69.945…]` | **20..69** frames of ambient-sfx countdown |

(The three doubles read out of DATA are `2.977e-06` at `const_random_scale`, `16794009.0` at
`const_random_range`/`const_random_range2` and the plain `11.0`/`34.0`/`5.0`/`1.0`/`20.0`
constants beside them, so nothing here turns on FP precision.)

Mouse `[0,319] × [0,199]` therefore maps onto exactly the room area, `[0,286] × [0,126]`.

### Facing and animation

`ghost_facing` ∈ 0..7 is stepped by the **mouse buttons**, one step per press
(edge-latched in `btn_left_ready` / `btn_right_ready`): status `1` (left button) → `+1`,
status `2` (right button) → `−1`, both wrapping mod 8.

`ghost_tile = ghost_facing*5 + ghost_anim` indexes GHOST.DAT tiles 0..39; the remaining ghost
tiles 40..46 are used directly by the death (40..43) and ending (45/46) sequences.
`ghost_anim` cycles 0,1,2,3 while idle and is pinned to **4** while blowing.

| facing | direction | blow impulse (dir_x, dir_y) | speed |
|---:|---|---|---:|
| 0 | left | (−1, 0) | 300 |
| 1 | down-left | (−1, +1) | 250 |
| 2 | down | (0, +1) | 300 |
| 3 | down-right | (+1, +1) | 250 |
| 4 | right | (+1, 0) | 300 |
| 5 | up-right | (+1, −1) | 250 |
| 6 | up | (0, −1) | 300 |
| 7 | up-left | (−1, −1) | 250 |

### Blowing

Blow is on while `key_shift_state` is neither `0` nor `4` — i.e. **any modifier except Ctrl
alone**; in practice, hold either Shift.

`breath` (`0x22fca`) is the air gauge: `+3`/frame up to `35` while idle, `−1`/frame while
blowing. It starts at 35, so ~35 frames of continuous blow and ~12 frames to refill.
**The two `Setcolor` calls belong to the arms the other way round from how this note first read
them**, and the reconstruction's differential is what says so (`recreate/STATUS.md`, gameplay):
every *idle* frame issues `Setcolor(15, 0x777)` (@ `0x1254a`), and `Setcolor(15, 0x733)` — the
ghost goes pink — is issued only on the frame the gauge goes negative (@ `0x124f2`), when the blow
also stops. A blowing frame with air left issues no `Setcolor` at all, so the ghost simply keeps
the white the last idle frame set.

`ghost_blow` (`0x129b4`) fires once per blowing frame. With `dx = bubble_x − ghost_x`,
`dy = bubble_y − ghost_y` it requires `|dx| < 50` **and** `|dy| < 50`, then one direction test:

| facing | condition | note |
|---:|---|---|
| 0 (left) | `dx < −1`, `−5 < dy < 15` | |
| 2 (down) | `dy > 1`, `−5 < dx < 15` | |
| 4 (right) | `dx > 3`, `−15 < dy < 5` | |
| 6 (up) | `dy < −1`, `−15 < dx < 5` | |
| 1 (down-left) | `dx < −5`, `dy > 5`, `|2·dy + 4·dx| < 40` | cone test |
| 3 (down-right) | `dx > 5`, `dy > 5`, `|2·dx − 3·dy| < 40` | cone test |
| 5 (up-right) | `dx > 5`, `dy < −5`, `|2·dy + 3·dx| < 40` | cone test |
| 7 (up-left) | `dx < −5`, `dy < −5`, `|2·dx − 4·dy| < 40` | cone test |

The multipliers really do differ between the four diagonals (4/3/3/4) — that asymmetry is in
the image, not a transcription slip.

A hit sets `(drift_dir_x, drift_dir_y)`, `drift_speed` to the speed above, and resets
`drift_interval = 0`, `drift_pulse = 0` — plus the velocity on **each axis the direction moves
on**: an orthogonal hit writes one of `drift_vel_x`/`drift_vel_y` (±300) and leaves the other
alone, a diagonal writes both (±250). Invisible in play, because the frame's tail zeroes both
anyway; visible to a differential, and pinned by
`recreate/test/test_gameplay.py::test_ghost_blow_arms_every_facing`.

### Drift

The bubble does **not** integrate a velocity every frame. `drift_vel_x`/`drift_vel_y` are
zeroed at the end of every frame, and re-armed only on a *pulse*:

```
if (drift_pulse-- == 0):
    drift_vel_x = drift_dir_x * drift_speed    # applied next frame as vel/100 pixels
    drift_vel_y = drift_dir_y * drift_speed
    drift_speed  = max(drift_speed - 50, 100)  # 300 -> 250 -> 200 -> 150 -> 100 (floor)
    drift_interval = min(drift_interval + 1, 200)
    drift_pulse  = drift_interval / 10         # 0 -> 20 frames between pulses
```

So a blow gives 3 px, then 2.5, 2, 1.5, 1 px steps, and the steps get further and further
apart (up to one every 20 frames) — the bubble visibly coasts and stalls. **There is no
gravity term and no wall bounce**: the bubble drifts in a straight line until it is blown
again, leaves the room, or pops.

`x_impulse` (`0x22fc6`) is a separate one-frame additive term used only by the fan (§5).

---

## 4. The castle: room grid and room record

### `room_grid` — `0x2328e`, 6 rows × 6 words (stride `0xc`)

```
row 0:  30 31 32 33 34 35
row 1:  29 28 27 26 25 24
row 2:  18 19 20 21 22 23
row 3:  17 16 15 14 13 12
row 4:   6  7  8  9 10 11
row 5:   5  4  3  2  1  0
```

A boustrophedon 6×6. `room_number = room_grid[grid_row][grid_col]`; the game starts at
`grid_row = 5, grid_col = 4` → room 1 and progresses left along row 5, then up.

Exits, tested after every frame in the room loop:

| test | effect | `entry_dir` |
|---|---|---:|
| `bubble_x > 288` | `grid_col++` | 0 (enter from the left) |
| `bubble_x < 0` | `grid_col--` | 2 (enter from the right) |
| `bubble_y > 128` | `grid_row++` | 3 (enter from the top) |
| `bubble_y < 0` | `grid_row--` | 1 (enter from the bottom) |
| `room == 35 && bubble_x > 195` | **level complete** | — |

**Room 0 (`grid[5][5]`) looks unreachable in play.** Its entry table is all zeros and its map is
a sealed box of border tiles; the only way in is a right exit from room 1, whose right edge at
`y = 2` carries object tile 264. Room 0 is used as the *hall-of-fame backdrop* (`0x11cd8` sets
`room_number = 0` before the object loop). Stated as a reading of the data, not a proof — the
exit is blocked by a pixel test, so a real reachability claim needs the room rendered.

### `room_table` — `0x21a4a`, 36 records × `0x78` (120) bytes

| offset | size | field |
|---:|---|---|
| `+0x00`..`+0x63` | 5 × 10 words | **tile map**: row-major, `map[y][x]` at `+ y*20 + x*2`, a GHOST.DAT tile index |
| `+0x64`..`+0x73` | 4 × (word,word) | **entry points** `(x, y)` in *tile* units, indexed by `entry_dir` 0..3; multiplied by 32 to give the bubble's pixel spawn |
| `+0x74` | word | **candle sfx index**, −1 = none (see §5); selects `sfx[41 + n]` |
| `+0x76` | word | unused in every record (always 0) |

Room 1's map, for reference (tile 50 is the all-colour-0 empty tile):

```
187 188 188 188 188 188 194 195 188 189
197  50  50  50  50  50 199 274  50 199
 50  50  50  50  50  50  50  50  50 264
197  50  50  50  50  50 199 274  50 199
207 208 208 315 208 208 204 205 208 209
```

### `object_table` — `0x2069a`, 36 rooms × `0x8c` (140) bytes = 10 slots × `0xe` (14)

| offset | field |
|---:|---|
| `+0x0` | **base tile** in GHOST.DAT; `-1` = empty slot |
| `+0x2` | animation countdown (decremented each frame; on reaching 0 the frame advances) |
| `+0x4` | countdown reload — 0 = advance every frame |
| `+0x6` | **x** in tile units (0..9) |
| `+0x8` | **y** in tile units (0..4) |
| `+0xa` | current animation frame; the drawn tile is `base + frame` |
| `+0xc` | frame count; `frame` wraps to 0 when it reaches `count - 1` |

Slots are drawn *after* the room has been presented, straight into the work buffer, so an
object is a permanent part of the background that the sprite save/restore preserves.
The animation phase is per-slot, which is how room 22's ten candles (tile 73, count 6) flicker
out of step: their `+0xa` values are 0,1,1,2,2,3,3,4,4 as shipped.

Tiles seen in the table: 220 = **fan** (8 frames, the only type the code special-cases),
73/63/83 = candle families, 211/241/253/264/274 = pipes and valves, 150/171 = spikes,
334/335 = the two tiles the ending pokes into room 35 slots 3/4.

### `candle_table` — `0x22b2a`, 36 rooms × `0xc` (12) bytes = 6 words

The one *scripted* interaction in the game: blowing out a candle.

| word | meaning |
|---:|---|
| `[0]` | object slot of lit-flame part A — **`-1` = this room has no candle** |
| `[1]` | object slot of lit-flame part B |
| `[2]` | tile to put in slot `[3]` when the candle goes out |
| `[3]` | destination slot for tile `[2]` |
| `[4]` | tile to put in slot `[5]` |
| `[5]` | destination slot for tile `[4]` |

Ten rooms have one: 3, 4, 5, 8, 9, 13, 14, 16, 19 and 25. Room 3 reads
`[4, 6, 166, 5, 50, 7]` — object slot 4 (tile 162, animated, at tile (5,3)) and slot 6
(tile 167 at (5,2)) are the lit candle; blowing it out sets slot 4 and slot 6 to −1, slot 5 to
tile 166 (the unlit candle) and slot 7 to tile 50 (empty).

The routine also patches the **room's tile map** at the two cells the flames occupied, so the
change survives a re-entry into the room:

```
room[r].map[obj[c0].y][obj[c0].x] = c2      # 166
room[r].map[obj[c1].y][obj[c1].x] = c4      # 50
candle_table[r][0] = -1                     # once only
score += 5000
```

Blowing a candle out requires facing 0 (left) and the candle 12..45 px to the ghost's left,
3..20 px below it (`ghost_blow`, second half).

---

## 5. The fan

The only object type with hard-coded behaviour, and it is hard-coded to **object slots 3 and 4**
of the current room:

```
if (object[room][3].tile == 220):
    dx = object[room][3].x*32 - bubble_x
    dy = object[room][3].y*32 - bubble_y
    if (5 < dx < 60) and (-15 < dy < 15):
        drift_dir_x = -1;  x_impulse = -2;  drift_vel_x = -1
    ... identically for slot 4
```

So a fan pushes the bubble **left**, over a 55 px × 30 px region to its left, at a constant
2 px/frame (`x_impulse`) plus a −1/100 px trickle. Tile 220 appears at slot 3 in rooms 5, 8, 26,
29 and at slot 4 in rooms 26, 29 — exactly the two slots the code reads, so no fan is missed by
the hard-coding as shipped. A recreate that reorders the object slots breaks the fans.

---

## 6. Collision: eight probes, read off the composed screen

`bubble_collision_probe` (`0x13004`) is the whole hazard model. There is **no geometry**:

```
previous    = probe_phase
probe_phase = previous + 1
if previous == 5: probe_phase = 0                  # the test is on the value it ARRIVED with
for i in 0..7:
    if get_pixel(bubble_x + probe[probe_phase][i].dx,
                 bubble_y + probe[probe_phase][i].dy) != 0:
        bubble_frame = 0;  bubble_alive = 0        # POP, and the scan stops
```

So the phases actually probed run 1, 2, 3, 4, 5, 0 — the *stepped* value, not the one the frame
began with — and a phase outside 0..5 keeps counting up rather than being clamped.

`get_pixel` (`0x13bea`) reads the four plane words at `screen_back + y*160 + (x/16)*8` and
assembles the 0..15 colour index. The work buffer at that moment holds the room background and
the objects, but **not** the ghost or the bubble (they were restored away at the end of the
previous frame) — so the bubble pops on any non-background pixel: wall, candle flame, spike,
fan blade, picture frame. That is why the empty cells of a room are tile 50, the all-colour-0
tile, and it settles `assets_survey.md`'s question 2 from the other side (§7).

`probe_table` — `0x1f14a`, 6 phases × 8 `(dx, dy)` word pairs, stride `0x20`:

```
phase 0  (15,7) (21,9) (24,15) (22,20) (16,23) (10,21) (7,15) (9,10)
phase 1  (16,7) (22,10) (24,16) (21,21) (15,23) (9,20) (7,14) (10,9)
phase 2  (17,7) (23,11) (24,17) (20,22) (14,23) (8,19) (7,13) (11,8)
phase 3  (18,7) (23,12) (23,18) (19,22) (13,23) (8,18) (8,12) (12,8)
phase 4  (19,8) (24,13) (23,19) (18,23) (12,22) (7,17) (8,11) (13,7)
phase 5  (20,8) (24,14) (22,20) (17,23) (11,22) (7,16) (9,10) (14,7)
```

An octagon of radius ≈ 8.5 about the sprite centre (15.5, 15.5), rotated 7.5° per phase — 48
distinct rim positions sampled 8 at a time, so a full sweep takes 6 frames. **The ghost is
never tested against anything**: it passes through walls freely, which is exactly how the game
plays.

---

## 7. The blitters

Two families. The raw ones are unrolled `move.l` loops over the work buffer; the sprite ones go
through the game's own VDI binding.

### Raw copies

| routine | bytes | from → to | when |
|---|---:|---|---|
| `draw_tile_bank_screen` `0x1369a` | 60 tiles | bank `bank_index` → `screen_back`, 10 across × 6 down | title / sprite-bank build |
| `draw_room_to_stage` `0x13a08` | 50 tiles | room map → `screen_back − 0x6400` | room entry |
| `draw_hud_row_tiles` `0x13712` | 10 tiles | bank 5 at +0x6400 (tiles 350..359) → `screen_back + 0x6400` | room entry |
| `objects_animate_and_draw` `0x1376e` | ≤10 tiles | bank[base/60] → `screen_back` | every frame |
| `stage_to_work` `0x13258` | 25,600 | `screen_back − 0x6400` → `screen_back` | demo / hall of fame (no wipe) |
| `room_wipe_in` `0x13b1e` | 40 × 25,600 | staged room slid **down** 640 B (4 rows) per step, then the top `(i+1)*640` B copied to the screen | room entry |
| `present_room` `0x13286` | 25,600 | `screen_back` → `screen_phys` | every frame |
| `present_hud_row` `0x13224` | 5,120 | at +0x6400 | room entry |
| `present_score_strip` `0x131f0` | 4,096 | at +0x6540 | after a score change |
| `clear_physical_screen` `0x10efe` | 30,720 | zero `screen_phys` | before a picture |

The tile blit is always the same inner loop: 32 iterations of four `move.l`s (16 bytes = one
32-pixel 4-plane row), source advancing 16 bytes, destination advancing 160.
Tile *n* lives at `dat_bank[n / 60] + (n % 60) * 512` — the six 30,720-byte GHOST.DAT buffers
in `dat_bank[0..5]`, with `dat_bank[6]` holding the GHOST.PRE picture.

### VDI binding — `0x168d4 … 0x16b12`

`vdi_call` (`0x168d4`) is `trap #2` with `d0 = 0x73` and the parameter block at `0x1e8ca`
(`contrl 0x236f0`, `intin 0x235f0`, `ptsin 0x234f0`, `intout 0x233f0`, `ptsout 0x232f0`).

| routine | `contrl[0]` | VDI call |
|---|---:|---|
| `0x168fc` | 12 | `vst_height` |
| `0x16948` | 22 | `vst_color` |
| `0x16974` | 25 | `vsf_color` |
| `0x169a0` | 100 | `v_opnvwk` (fills `vdi_handle` at `0x232ee`) |
| `0x16a06` | 3 | `v_clrwk` |
| `0x16a26` | 124 | `vq_mouse` → `mouse_buttons`, `mouse_x`, `mouse_y` |
| `0x16a5e` | 128 | `vq_key_s` → `key_shift_state` |
| `0x16a86` | 8 | `v_gtext` |
| `0x16ae2` | 114 | `vr_recfl` |
| `0x16b12` | 109 | `vro_cpyfm` |

Sprite drawing (`0x1342e` / `0x134f6` / `0x135d2`) is three `vro_cpyfm` pairs per frame:

```
save:    mode 3 (S_ONLY)  screen(x,y,+31,+31)     -> ghost_bg / bubble_bg
draw:    mode 7 (S_OR_D)  ghost_sprite[tile]      -> screen(x,y,+31,+31)
restore: mode 3 (S_ONLY)  ghost_bg / bubble_bg    -> screen(x,y,+31,+31)
```

**Mode 7 is the answer to "how is transparency done".** There is no mask: the ghost and bubble
tiles use only colour 0 and colour 15, so ORing them onto the background sets all four planes
where the sprite is white and leaves the background elsewhere. `vro_cpyfm` also does the
clipping, which is why the ending can walk the bubble to `y = −30`.

The sprite bitmaps themselves are **grabbed from the screen at start-up**: `build_sprite_bank`
(`0x132ec`) draws GHOST.DAT bank 0 (tiles 0..59) as a 10×6 grid with `draw_tile_bank_screen`,
then `vro_cpyfm`s each 32×32 cell into its own `malloc`ed buffer:

* `ghost_sprite[0..46]` — pointer array at `0x23028`, GHOST.DAT tiles 0..46
* `bubble_sprite[0..12]` — pointer array at `0x22ff4`, GHOST.DAT tiles 47..59
  (0..2 = the sparkle, 3 = the empty tile, 4..12 = the nine bubble frames)
* `bubble_bg` `0x230e4`, `ghost_bg` `0x230e8` — the two 32×32 save patches

`bubble_frame` is exactly the DEM file's field 5, and `bubble_sprite[f] = tile 47 + f`.

---

## 8. Scoring, lives, bonus

| global | address | width | role |
|---|---|---|---|
| `hud_room_number` | `0x22fa4` | long | copy of `room_number` for the `HALL:` field |
| `lives` | `0x22fa8` | long | `BUBBLE:`; 5 at the start of a turn, turn ends at −1 |
| `hi_score` | `0x22fac` | long | `HI-SCORE:`; seeded from the top hall-of-fame entry |
| `score` | `0x22fb0` | long | `SCORE:` |
| `bonus_bar` | `0x22fb4` | word | the bar's right end, 318 down to 35 |
| `max_room_reached` | `0x22f74` | word | starts at 1 |
| `deaths_in_room` | `0x22f62` | word | reset on each new room |

* `bonus_bar` starts at `318` on entering a *new* room and ticks down by 1 every **3** frames,
  floored at 35 — `bonus_tick` (`0x22f76`) is reloaded with 2 and the bar steps on the frame
  whose pre-decrement value is already 0, so the sequence is 2, 1, 0 → step. The bar itself is
  a one-pixel `vr_recfl` line at `y = 189`, colour 11, erased in colour 0, and each step is
  followed by a **160-byte** copy of row 189 (offset `0x7620`) from `screen_back` to
  `screen_phys` — `moveq #$27` + `dbf` over `move.l`, i.e. 40 longs.
* Reaching a room with a number above `max_room_reached` refills the bar and, **if the entry
  direction was 1 (came up from the row below)**, awards one extra bubble (capped at 9).
* Leaving a room forward: `score += 5000 − 500 * deaths_in_room`, then the bar is cashed in
  5 units at a time at `+50` per step.
* The ending (room 35, `bubble_x > 195`) cashes the bar at `+100` per step.
* Popping: `lives--`, `deaths_in_room++`.

`hud_draw_counters` (`0x113d2`) sets `vst_height(4)`, `vst_color(5)` and `v_gtext`s four
strings built by `itoa_padded` (`0x114ee`, zero-padded then reversed):
score at (230,173) width 6, hi-score at (230,183) width 6, room at (307,173) width 2,
lives at (313,183) width 1 (a negative `lives` prints as 0).

---

## 9. Two players

Two independent worlds. `player_count` `0x2316c` is 1 or 2; `p1_turn` `0x2316a` and `p2_turn`
`0x23168` are mutually exclusive and are swapped at the top of each turn (which is why
`init_globals` leaves `p1_turn = 0, p2_turn = 1` — the first swap hands the turn to player 1).

Per-player context, restored/saved around the swap. `names.txt` names these `p1_*` / `p2_*`
after the column they sit in here, and the columns are what the code does: the player-1 arm of
the save (`0x12914`) and of the restore (`0x10542`) name the left column, the player-2 arms
(`0x1294a` / `0x1059e`) the right, and `0x2316a` (`p1_turn`) non-zero is what prints
`P L A Y E R    O N E`.

| | player 1 | player 2 |
|---|---|---|
| still playing | `0x2319a` | `0x23198` |
| max room | `0x23196` | `0x23194` |
| lives (long) | `0x2318e` | `0x2318a` |
| score (long) | `0x23186` | `0x23182` |
| bonus bar | `0x2317c` | `0x2317a` |
| grid col | `0x23178` | `0x23176` |
| grid row | `0x23174` | `0x23172` |
| deaths in room | `0x2319e` | `0x2319c` |
| entry dir | `0x231a4` | `0x231a2` |
| **world block** | `0x2321a`..`0x2328d` | `0x231a6`..`0x23219` |

The "world block" is exactly 58 words: every table cell a blown-out candle mutates, over the ten
candle rooms. Rooms 3, 4, 5, 8, 9 and 19 contribute 7 words each (four object `tile` fields, two
room-map cells, the `candle_table[r][0]` sentinel); rooms 13, 14, 16 and 25 contribute 4 each,
because their candle record names the same slot twice and so touches two object tiles and one map
cell. 6x7 + 4x4 = 58. Room 35's two ending slots (`0x219e8` / `0x219f6`) are **not** in the block —
they are poked and un-poked inside one ending sequence.


`save_world_p1` `0x13ff4` / `save_world_p2` `0x14158` copy live → block;
`restore_world_p1` `0x13d2c` / `restore_world_p2` `0x13e90` copy block → live;
`reset_world_state` `0x10f20` writes the lit-candle defaults to the live tables *and* both
blocks in one pass.

---

## 10. Open questions

1. **`room_table + 0x76`** (`0x21ac0 + r*0x78`, i.e. `-13914(a4)` for room 0) is zero in all 36
   records and no instruction in the image was seen to name it. Padding, or a field the shipped
   data never uses? A two-encoding operand census would settle it; not run.
2. **Room 0's reachability.** Argued from the tile map and object 264 above; a rendered room 1
   with the bubble driven right would prove it. Recorded as unproven.
3. **Object tile → semantic type.** Only tile 220 (fan) is behavioural; every other object is
   just pixels the collision probe reads. So "which tile is a spike" is a *rendering* question,
   not a code one — but a recreate that wants named hazards needs the tile→name map, and that
   has to come from the rendered sheet, not from `GHOST.PRG`.
4. **`x_impulse` (`0x22fc6`) is set by nothing but the fan** and cleared every frame. Whether
   any other writer exists is a two-encoding operand scan away; not run.
5. **`0x22fe2`** is a scratch counter shared by the death animation, the ending walk and the
   ambient-sound countdown reload. It is one global doing three jobs; a recreate should keep it
   one global, because the ending sequence *reads* the value the death sequence left.
6. **The demo's frame pacing.** The demo player calls no `Vsync` in the record loop, so it runs
   at whatever the blit costs. The play loop does not `Vsync` either — the ambient-sound
   countdown is the only timebase. A recreate that adds `Vsync` will run the game slower than
   the original.
