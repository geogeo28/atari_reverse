# Flying Shark — gameplay slice

Firebird 1988, hand-written 68000 by Prime Software / Images Design.
`FLYSHARK.PRG`, text 0x59f4, data 0x6442, bss 0x3f0a8, load base 0x10000.

This note covers **the per-frame loop and everything it calls**: scroll and tile
renderer, sprite blitters, the player plane, bullets/bombs, the enemy entity
system, the level spawn script, collision, score/HUD and level flow. Init, the
frontend, the file loader, the ACIA ISR and the sound module's internals belong
to the other agents; where this slice touches them there is a CROSS-SLICE note.

Proposed names: `projects/flyingshark/out/names_gameplay.txt`.

---

## 1. Memory map (Ghidra addresses)

Derived from the file-load table at `0x162ee` (8-byte header + `A\NAME` string
per entry), confirmed against every `lea` in the code.

| Range | Contents |
|---|---|
| `0x10000..0x159f4` | text |
| `0x159f4..0x1be36` | data (score, LUTs, level map, entity descriptors, pointer tables) |
| `0x15a00` | 7 bonus-life thresholds, 6 digit-ids each |
| `0x15a2a / 0x15a2d` | score / hi-score, 3 bytes packed BCD |
| `0x16432 / 0x16434 / 0x16436` | `LEVEL1.MAP` header (cols, rows) + cell array, loaded here (0x1388 max) |
| `0x177ce..0x17d08` | display list, 223 x 6 bytes |
| `0x17e0c` | tile repair grid |
| `0x18014..0x18814` | 4 sprite restore lists, 512 B each |
| `0x190a4` | player record |
| `0x19534..0x197f8` | enemy descriptors |
| `0x1be36..0x38928` | `SPRITES.cru` (117,490 B) — ends **exactly** where HSC_0 begins |
| `0x38928..0x58928` | `HSC_0..3.DAT`, one contiguous 128 KB / 256-tile atlas |
| `0x58928` | `MODULE.BAK` — a nested `.PRG`; **call base is `0x58944`** (+28 header) |
| `0x59984..0x5ae22` | entity arena, 91 x 58 B |
| `0x5ae22..0x5ae9a` | player bullet arena, 15 x 8 B |
| `0x5ae9a..0x5aede` | power-up items + the player's bomb, 7 x 10 B (BSS ends at 0x5aede) |
| video | one `0x1f900`-byte circular region below Physbase, four screens inside it |

---

## 2. The frame loop

`main` (0x15750) runs three init calls then **45** subsystem calls forever
(`bra.w $1575c`) — the table's row 46 is the loop's own `clr.w`, not a `bsr`, and
`recreate/test/test_init.py` reads the count off the loaded image rather than
trusting it. **The same body appears verbatim three more times**:
in `level_start` (0x14aa8), and in 0x10724 and 0x124ae — the game-over and
level-advance paths re-enter the loop rather than returning into it (0x124ae
does `addq.l #4,a7 / bra.w $15758`; the abort key does `adda.l #$40,a7 /
bra.w $10724`).

| # | addr | what it does | state touched |
|---|---|---|---|
| 1 | 0x11654 | `frame_counter_tick` — long++ | `0x17764` |
| 2 | 0x119fc | recompute the cycling sprite ids from the frame counter | `0x19518,1951c,19520,19525,1952a,1952f` |
| 3 | 0x13a20 | scripted player movement (take-off / fly-off / demo) | player `+6` mode -1/1/2, `shadow_offset` |
| 4 | 0x124ae | end-of-level trigger, level advance, boss trigger | `level_complete`, `level_index`, player mode |
| 5 | 0x1259c | restart the level tune if the module reports idle | `snd 1256(a0)` |
| 6 | 0x14354 | joystick/keys → move, fire, bomb, pause, abort | player x/y, `player_bank`, shot slots |
| 7 | 0x13c96 | publish player + shadow display records; drive death / game over | `dl_player`, `dl_player_shadow` |
| 8 | 0x13baa | bank index drifts back to centre (7) when not turning | `player_bank` |
| 9 | 0x12fc4 | **level spawn script**: fire one record when `scroll_pos` reaches it | `spawn_script_cursor`, entity arena |
| 10 | 0x12d5c | update all 91 entity slots (`entity_move` per slot) | entity arena |
| 11 | 0x117f4 | big-object depth flag vs two other groups | entity `+28` |
| 12 | 0x1175c | hide entities that overlap the big object | entity `+48` |
| 13 | 0x1187a | move the power-up items (path + fall) | `0x5ae9a..` |
| 14 | 0x1184e | enemy dropped bombs fall 2 px/frame, die past y=199 | display records 0..15 |
| 15 | 0x1165c | item pickup test → weapon / bomb / life | `weapon_level`, `bombs`, `lives` |
| 16 | 0x129b2 | rotate turrets toward the player (12 facings) | entity `+26`, `+24` |
| 17 | 0x12a60 | publish the turret barrel sub-sprites | `dl_turret_t0..t7` |
| 18 | 0x141b4 | free a player shot slot once all 5 of its bullets are gone | `shot_slot_*_busy` |
| 19 | 0x12602 | enemy firing: countdown `+30`, reload `+32`, 1-3 aimed shots | `enemy_bullets` |
| 20 | 0x12964 | move enemy bullets, kill them off-screen | `enemy_bullets` |
| 21 | 0x1101c | **player vs enemy bullets** → player mode 3 | player `+6` |
| 22 | 0x125bc | publish enemy bullets (frame 0x80) | `dl_enemy_bullets` |
| 23 | 0x10f26 | **player vs entities** (28x24 box) | player `+6` |
| 24 | 0x140cc | move player bullets: `x += dx`, `y -= 0x13` | `player_bullet_arena` |
| 25 | 0x1361c | publish every entity group to the display list | display list |
| 26 | 0x102de | publish the big object's three extra parts (frames 0x4f/0x4a/0x4b) | `0x179f4/0x179fa/0x17a00` |
| 27 | 0x11de6 | **player bullets vs entities** → `bullet_hit_handler_tbl` | entity `+22` hp, score |
| 28 | 0x14118 | publish player bullets (frame 0x7f, impact 0xe5) | `0x17b6a/0x17b88/0x17ba6` |
| 29 | 0x10e7c | bomb flight along `bomb_fall_path` | `bomb_falling`, `0x5aed6..` |
| 30 | 0x10ee2 | publish the falling bomb | `dl_bomb` |
| 31 | 0x10c8c | blast animation, 15 steps of 4 offsets | `blast_step`, `0x5aec2..` |
| 32 | 0x10d20 | publish the 4 blast sprites (frame 0xd2) | `dl_blast` |
| 33 | 0x11a82 | **blast vs entities** → `blast_hit_handler_tbl` | entity hp, score |
| 34 | 0x1191c | publish the power-up items | `dl_item_0..3` |
| 35 | 0x1227c | publish muzzle-flash / rotor pairs `# ctx` | `0x17b3a`, `0x179c6..` |
| 36 | 0x123d8 | HUD: bomb icons (frame 0x81) and life icons (frame 0x82) | `dl_bomb_icons`, `dl_life_icons` |
| 37 | 0x10a2a | score > hi-score? | `hiscore_beaten` |
| 38 | 0x10a50 | publish two 5-digit rows + a literal '0' | `0x17cb4`, `0x17cd8` |
| 39 | 0x110d4 | bonus life at the next threshold | `lives`, `bonus_life_awarded_*` |
| 40 | 0x10ae4 | score/hi-score BCD → digit ids | `score_digits`, `hiscore_digits` |
| 41 | 0x10ab4 | blank leading '0' glyphs | digit display records |
| 42 | 0x10a02 | publish the two fixed HUD labels (frames 0xd0/0xd1 at y=2) | `dl_hud_labels` |
| 43 | 0x111ee | `scroll_pos += 2`; `level_distance = (scroll_pos - 0x2e)/2 + 1` | `0x17758`, `0x1779a` |
| 44 | 0x10bc8 | level-2-only scenery animation gate | `0x17798/0x1779e/0x177a0` |
| 45 | 0x14446 | **render_frame** (see §5) | screens, restore lists |
| 46 | — | `clr.w level_just_started` | `0x17696` |

Ordering notes worth keeping: the HUD digits are published (38) **before** the
score is converted (40), so the displayed score is one frame stale; and
`scroll_advance` (43) runs after every collision and spawn test, so the whole
frame sees one consistent `scroll_pos`.

---

## 3. Records

### 3.1 Display record — 6 bytes (223 of them, `0x177ce..0x17d08`)

```
+0 x.w   +2 y.w   +4 frame.b   +5 active.b
```
`active = 0` hidden; `0xff` drawn in render pass A (then the scenery overlay is
repainted over it, so it appears *under* bridges/trees); `1..0x7f` drawn in pass
B, on top of everything. Subsystems own fixed sub-ranges; the first 16 records
double as the enemy dropped-bomb array (`enemy_bombs_move` walks exactly those),
and the last two are the player's shadow (`0x17cfc`) and plane (`0x17d02`).

### 3.2 Sprite header — 20 bytes, at the head of `SPRITES.cru` (`0x1be36`)

Indexed by the byte frame id, so at most 256 records = 5120 B.

```
+0  .l  pointer to the pixel data
+4  .w  width class 0..3   (source row = (class+1) * 10 bytes)
+6  .w  height in rows
+8  .w  draw x offset      (added to the display record's x)
+10 .w  draw y offset
+12 .w  hitbox near corner x
+14 .w  hitbox near corner y
+16 .w  hitbox far corner x
+18 .w  hitbox far corner y
```

Pixel data is **masked**: each 16-px column group is 5 words — mask first, then
planes 0..3 — so 10 bytes per group, `(class+1)*10` per row. A set mask bit is
transparent (`AND mask / OR data`), matching `docs/graphics.md`.

Both collision routines index this table with `frame * 20` (`0x1be3e` = `+8`,
`0x1be42` = `+12`, `0x1be46` = `+16` … as they appear in the decompile).

### 3.3 Entity record — 58 bytes, 91 slots at `0x59984`

```
+0  x.w                    +2  y.w
+4  frame offset.w         +6  draw flags.w (high byte -> display active byte)
+8  dx.w                   +10 dy.w
+12 step countdown.w       +14 active.w
+16 dying.w                +18 dropped item kind.w (descriptor +6)
+20 base frame.w (descriptor +4)
+22 hit points.w (descriptor +24; -4 per bullet hit)
+24 aim-changed.b          +26 facing 0..11.w
+28 depth/table select.w   +30 fire countdown.w
+32 fire reload.w (descriptor +8)
+34 path table selector.w  +36 path cursor.w
+38 firing.w               +42 anim timer.w
+44 kind.w (== 4 drops bombs)   +46 has-dropped.w
+48 hidden-under-bigobj.w
+50 movement script base.l +54 movement script cursor.l
```

The published sprite frame is `+20 + +4` (base + offset), or `+26 + +20` for
turrets, so one descriptor covers a whole animation and a whole facing set.

Slots are addressed only through the **pointer tables** at `0x19246..0x1946e`:
four groups of 7, eight groups of 4 (each followed by 4 display-record pointers
for its turret barrels), a big-object group of 4, five more groups of 4, a pair,
and a last group of 4. Every per-frame pass walks the same tables.

### 3.4 Enemy descriptor — 26..30 bytes, `0x19534..0x197f8`

```
+0  .l  pointer to this group's slot-pointer array
+4  .w  base sprite frame
+6  .w  item kind dropped when the whole formation is cleared
        (also copied to entity +18)
+8  .w  fire reload period       (rewritten per level by 0x12cc8: 10/12/7/18)
+14 .w  entity count - 1
+16 .w  hit-handler index (indexes BOTH hit tables)
+18/+20 .w death sprite offset
+24 .w  initial hit points
+28/+30/+34 .w muzzle/rotor offsets
```

### 3.5 Player record — 7 bytes at `0x190a4`

```
+0 x.w   +2 y.w   +4 frame.b   +5 shadow frame.b   +6 control mode.b
```
Mode 0 = joystick; 1 = landing script; 2 = level-clear fly-off; 3 = dying
(frames from `player_death_frames` at `0x19210`, y += 2 per frame); 4 = game
over; 0xff = take-off script. `player_reset_to_start` (0x13d24) copies the
7-byte template at `0x1909c` over it. x is clamped to `0..0x121`, y to
`0x0b..0xbb`, both in 6-px steps.

`player_bank` (`0x17742`) is the tilt index; `player_frame_from_bank` reads the
frame out of the byte table at `0x17744`, whose ends are marked with a negative
sentinel that `player_move_left`/`right` test before stepping the index.
`player_bank_recentre` walks the index back toward 7 whenever the player is not
turning.

### 3.6 Player bullets — 15 x 8 bytes at `0x5ae22`

```
+0 x.w   +2 y.w   +4 dx.w   +6 state.w   (0 free, 1 flying, 2 hit)
```
Grouped as three shots of five slots (`0x19422/0x19436/0x1944a`). `player_fire`
allocates a whole shot at a time via `shot_slot_0..2_busy`; the pattern routine
selected by `weapon_fire_tbl[weapon_level]` decides which of the five slots are
activated and with what `dx` — that is the whole power-up progression. Bullets
move 19 px up per frame.

### 3.7 Enemy bullets — 16 x 10 bytes at `0x1946e` + a 999 terminator

```
+0 x.w   +2 y.w   +4 dx.w   +6 dy.w   +8 active.w
```

### 3.8 Power-up items — 7 x 10 bytes at `0x5ae9a`

```
+0 x.w   +2 y.w   +4 path cursor.l   +8 active.w
```
`item_path_step` walks the 4-byte (dx, dy) path at `0x1b02a` (999-terminated,
restarts at the beginning), `item_fall_step` just drops. `items_pickup_check`
passes the kind in d6: 0 = weapon (`0x5ae9a`, max level 4), 1 = bomb
(`0x5aeae`, max 6), 2 = life (`0x5aea4`, max 7). The last record, `0x5aed6`, is
the player's own bomb: x, start y, current y, frame.

---

## 4. Scroll model

**Nothing is copied to scroll.** The game allocates one `0x1f900`-byte region
below Physbase (`screen_region_base` = `Physbase - 0x1f800` rounded down to a
256-byte boundary) and puts **four** screens in it at `+0x7800`, `+0xfa00`,
`+0x17700`, `+0x1f400`.

Every frame `render_frame` calls XBIOS `Setscreen` with `screen_draw`, then:

* `scroll_fine += 2`, masked to `0x1f` — the sub-tile scroll, 2 px/frame;
* `screen_index = (screen_index + 1) & 3`, and **that buffer's** pointer is
  decremented by `0x500` (8 scanlines = 4 frames x 2 px), wrapping by `+0x1f900`
  when it passes `screen_region_base`;
* `screen_prev2 <- screen_prev <- screen_draw <- the new pointer`.

So the visible base creeps up 320 bytes per frame and the picture scrolls
smoothly downward; each buffer is reused every 4th frame, 8 scanlines further
up. When the draw pointer sits in the low `0x7d00` of the region, the first
thing `render_frame` does is copy the `0x500` bytes at the pointer to
`pointer + 0x1f900` (four calls to `scroll_wrap_copy_1280`), which is the
circular seam the video shifter reads across.

**New tile rows.** After the flip, the loop at `0x1483a` draws the freshly
exposed 8-scanline band across the 10 columns: for each column it takes the last
`d3` rows of the tile named by the current map row and the first `d4` rows of
the one below, `(d4, d3)` coming from `scroll_band_split_tbl` indexed by
`scroll_fine`. `map_row_ptr` steps up 20 bytes each time `scroll_fine` wraps.
**Its reset arm is dead**: `0x147da` is a `nop` where the bound test used to be,
and the store it guarded at `0x147dc` is immediately overwritten at `0x147e6`,
so the map pointer simply keeps walking upward.

**Map format** (as the renderer reads it): `LEVEL1.MAP` is `cols.w, rows.w`
then `rows * cols` words; `cols` is 10, so the row stride is 20 bytes. The even
byte of each word is the **opaque base tile**, the odd byte the **overlay tile**
(0 = none), drawn with colour 0 transparent. `map_row_ptr` starts at the *end*
of the array and walks up. A 0x1388-byte file is at most 250 rows = 8000 px of
level.

**Repairing the sprites.** Each drawn sprite appends `(screen offset, width
class, row count)` to `sprite_restore_lists[screen_index]`. Two frames later,
`render_frame` replays that list and copies clean background over the dirt in
the buffer that is about to come round again — source `screen_draw + offset +
0x280`, destination `screen_prev2 + offset`. The `0x280` is exactly the 4
scanlines of scroll that separate the two buffers, so the same world content
lands in the same place.

---

## 5. Renderer and blitters

`render_frame` (0x14446), in order:

1. circular-seam copy (above);
2. **pass A** — display records with `active < 0`: draw the sprite, append to
   the restore list, and copy the *overlay* tile ids of the up-to-4 grid cells
   the sprite touches from `map_row_ptr` into `tile_repair_grid`;
3. **overlay repaint** — drain `tile_repair_grid` (10 words per row, cleared as
   it goes) and blit each named tile with `d6 = ~(p0|p1|p2|p3)`, i.e. colour 0
   transparent. This is what puts pass-A sprites *behind* the scenery;
4. **pass B** — display records with `1 <= active < 0x80`, drawn opaque on top;
5. `Setscreen` + `Vsync` (or a spin on `vbl_counter >= 3`, then zero it — a
   3-VBL frame budget, i.e. 50/3 ≈ 16.7 fps nominal);
6. scroll/rotate (§4), new tile band, restore-list replay.

`prescroll_flag` (`0x1642c`) short-circuits steps 2-5 so `level_start` can fill
a whole screen of tiles with no sprites (it calls `render_frame`
`prescroll_frames + 1` times).

### Sprite blitter contract

Chosen from three tables of four longwords — `sprite_blit_tbl` (0x16396),
`..._clip_left_tbl` (0x163a6, when the final x is negative),
`..._clip_right_tbl` (0x163b6, x >= 0x110 in pass A / > 0xf0 in pass B) —
indexed by the header's width class.

```
a0 = sprite pixel data (already advanced past any rows clipped at the top)
a1 = screen_draw + (x & ~0xf)/2 + y*160
d6 = x & 0xf          sub-word shift, 0..15
d7 = row count        already clipped against y<0 and y>199
0x16426               clip mask byte, consulted by the clipped variants
```

The width-class-0 body is the model: load mask + 4 plane words into `d1..d5`
(`d1` pre-loaded `0xffff0000`), `ror.l d6` on all five, `AND mask / OR plane`
into four consecutive screen words, `swap`, repeat for the overflow group, then
`lea 146(a1),a1` to finish a 160-byte row. Class *n* spans *n+2* 16-px groups.

Top clipping subtracts `(class+1) * 10 * -y` from `a0`, which is the cleanest
statement of the source row stride there is.

### Restore blitters

`restore_blit_tbl` (0x163c6) holds 4 unrolled `move.l (a0)+,(a1)+` loops of
16/24/32/40 bytes per row (32/48/64/80 px) with the matching row-stride `lea`;
`restore_blit_w16` at `0x14d58` sits just before the table and is not reached
through it.

### Dead code

`0x1581a` is a complete standalone 32x32 tile blitter with top/bottom clipping
jump tables, sitting after `main` at the end of the text segment. **Nothing in
the image names its entry**, and its clipping arithmetic scales `d1` by 10 bytes
per row while the unrolled block it jumps into is 12 bytes per row (4 x
`move.l` + `lea 144(a0),a0`, 32 rows + `rts` = the last 386 bytes of the text
segment) — so either clipped entry lands mid-instruction. It is both unreachable
and broken; the live tile drawing is the inline loop inside `render_frame`.

---

## 6. Collision model

Everything is an axis-aligned box test; there is no mask-level collision.

* **Player vs enemy bullets** (0x1101c): player box from
  `sprite_header_tbl[player frame]` fields `+8/+10/+16/+18`, bullet treated as a
  point + 0x10. Skipped entirely when the `0x177c6` cheat is set.
* **Player vs entities** (0x10f26 → 0x10fa0): a fixed 0x1c x 0x18 box around the
  player against each active, non-dying entity of four groups; skipped in player
  modes 3/4.
* **Player bullets vs entities** (0x11de6 → 0x11f0c): 3 shot groups x 22 entity
  groups; on a hit, dispatch `bullet_hit_handler_tbl[descriptor +16]`.
* **Bomb blast vs entities** (0x11a82 → 0x11bb6): the same 22 groups against the
  blast quad, dispatching `blast_hit_handler_tbl[descriptor +16]`.
* **Item pickup** (0x11698): player box vs the 10-byte item record + 0x10.

Both hit tables have 19 entries and share the descriptor's handler index, so an
enemy class always reacts the same way to bullets and to bombs — only the score
and the damage differ. The handler families are: award score and mark dying
(`st 16(a3)`); award score, mark dying and call
`item_drop_if_formation_cleared` (0x121fe), which drops a power-up **only once
every slot of the formation is dead** — the classic "shoot the whole squadron"
rule; award score only if visible; subtract 4 hit points from `+22` and explode
at zero; and a bare `rts` for indestructible classes (`0x11d06`, `0x12084`).

The item kind comes from the descriptor's `+6`: 0 = weapon power-up (and it
raises `item_pickup_pending`, which makes the spawn script stop offering
another), 1 = bonus item worth 1000 points, anything else = extra life.

Turret aiming (0x12c04) is the other geometric routine: the wanted facing comes
straight out of `turret_facing_lut` at
`((y - player_y) >> 5) * 0x17 + ((x - (player_x + 4)) >> 5)` — a 23-column
direction grid — and the entity rotates one of 12 steps per frame toward it.
Enemy aiming (0x128ce) uses a second, 21-column grid at `enemy_aim_dir_lut`,
then reads `(dx, dy)` from `enemy_bullet_velocity_tbl` (4 bytes per direction).

---

## 7. Spawn / level script

`spawn_script_ptr` (`0x17770`) points at the level's script; `spawn_script_step`
fires **one record per frame** while `scroll_pos` has reached its trigger.

```
record = 10 bytes
+0 .w trigger scroll position   (0xa3a1 = end of script)
+2 .w spawn handler index       -> spawn_handler_tbl (0x190c0)
+4 .w x
+6 .w y
+8 .w formation index
```

Two type substitutions happen before the dispatch: type 1 becomes type 2 when
`weapon_level == 4` or `item_pickup_pending` is set (so the weapon power-up is
not dropped twice), and type 3 becomes 2 unless `item_bomb_spawned_flag` is
still clear (one bomb item per level).

Each handler is a 16-byte stub: `a5 = enemy descriptor`, `a1 = formation table`
(`0x1ae0c`, `0x1af80` or, for the single-entity variant, `0x19a54`), then a
`bra` into the shared body.

`spawn_formation_common` (0x130aa): `a1 = *(formation_table + 4*formation)`
selects a formation record —

```
+0..+15   four (dx, dy) word pairs, one per slot (0x63 in either word = unused)
+16..+31  four movement-script offsets (longwords)
+32       movement-script base pointer (longword)
```

— and fills the descriptor's four slots. `spawn_single_common` (0x131a4) is the
one-entity version with 8-byte records `{dx, dy, script offset.l}` and the base
at `+8`.

**Movement scripts** are 8-byte records `{dx.w, dy.w, duration.w, frame.w}`
terminated by 999 (`0x3e7`); `entity_move` advances `+54` by 8 whenever `+12`
hits zero, and deactivates the entity at the terminator. The alternate mode
(`+16` non-zero) walks a word table from `entity_path_tbl_ptrs` instead, taking
the frame from the table (minus the base at `+20`) and descending 2 px/frame;
kind `+44 == 4` drops one enemy bomb along the way.

`level_start` (0x14aa8) rewinds both the scroll position and
`spawn_script_cursor` when a life is lost: it walks a 6-byte checkpoint table
(`*(0x15ab0 + level_index*4) + 0x26`, backwards) for the last checkpoint at or
before `scroll_pos - 0xd8`, then skips the script forward 10 bytes per record
already triggered.

---

## 8. Score, HUD, lives

Score and hi-score are 3 bytes packed BCD at `0x15a2a` / `0x15a2d`, added to by
`abcd` in `score_add_bcd` (0x10bec); the nine wrappers hold the point values as
BCD constants at `0x15a30..0x15a4a`: **50, 100, 200, 250, 500, 1000, 3000,
5000, 10000**. `bcd3_to_digits` expands them to glyph ids `0xc5 + digit`, and
the HUD prints five digits plus a hardcoded `'0'` glyph, so the low BCD digit is
always zero.

Bonus lives: seven 6-digit thresholds at `0x15a00` — 50000, 200000, 350000,
500000, 650000, 800000, 950000 — each with a one-shot flag in
`bonus_life_awarded_0..6`. `digits6_compare` (0x108f8) is shared with the
hi-score table (where it adds 16 to reach the score field of a 22-byte entry;
`bonus_life_check` pre-subtracts 16 to cancel that).

HUD display records: labels (frames 0xd0/0xd1) at y = 2, the two score rows,
bomb icons (frame 0x81) right-to-left from x = 0x130 in steps of 0x10 at
y = 0xbf, life icons (frame 0x82) left-to-right from x = 2 in steps of 12 at
y = 0xbe. Lives are capped at 7 and bombs at 6.

---

## 9. Sound (caller side only)

Module base **`0x58944`**, 12 `lea` sites. Entries used from this slice:

| call | argument | meaning |
|---|---|---|
| `jsr 38(a0)` | — | per-VBL tick, from `vbl_handler` |
| `jsr 434(a0)` | d0 = tune | start music (`snd_music_start_current`) |
| `jsr 1196(a0)` | d0 = sfx id | play effect |
| `jsr 1256(a0)` | d0 = tune | start music (used by the level-clear and restart paths) |
| `tst.b 30(a0)` | — | music busy |
| `tst.b 31(a0)` | — | sfx busy (guards several effect calls) |
| `(*0x58df0)()` | — | an indirect entry used by `player_fire` and `enemy_bullet_spawn_aimed` |

Effect ids seen: 2 (pickup / bomb), 5 (enemy shot), 6 (player death), 0xa (bomb
blast), 0xb (a `player_fire` variant).

`vbl_handler` (0x11636) is installed at `$70`: it bumps `vbl_counter`, ticks the
module, and chains to the saved TOS vector through the `jmp` operand at
`0x11650` that `_start` patches — the `jmp $1164e` in a linear disassembly is
that unpatched placeholder, not an infinite loop.

---

## 10. Globals census

Only globals this slice reads or writes. W = writers, R = readers (function
entry addresses).

| addr | name | width | role | W / R |
|---|---|---|---|---|
| 0x159f4 | `score_digits` | 6 B | glyph ids for the score | W 0x10b04 / R 0x10a2a 0x10a50 0x108f8 |
| 0x159fa | `hiscore_digits` | 6 B | glyph ids for the hi-score | W 0x10b04 / R 0x10a2a 0x10a50 |
| 0x15a00 | `bonus_life_thresholds` | 7x6 B | extra-life scores | R 0x110d4 |
| 0x15a2a | `score_bcd` | 3 B | score | W 0x10bec 0x11616 / R 0x10ae4 0x110d4 0x10724 |
| 0x15a2d | `hiscore_bcd` | 3 B | hi-score, default 250000 | R 0x10ae4 |
| 0x15ce6 | `bomb_fall_path` | 4 B/step | bomb trajectory, 999-terminated | R 0x10e7c |
| 0x15dc3 | `turret_facing_lut` | 23 cols | facing toward the player | R 0x12c04 |
| 0x15f3a | `enemy_aim_dir_lut` | 21 cols | shot direction toward the player | R 0x128ce |
| 0x15fee | `enemy_bullet_velocity_tbl` | 4 B/dir | (dx, dy) per direction | R 0x128ce |
| 0x1606e | `blast_offset_tbl` | 8 B/step | 4 offsets per blast step | R 0x10c8c |
| 0x16396/a6/b6 | sprite blit tables | 4 x .l | blitter per width class | R 0x14446 |
| 0x163c6 | `restore_blit_tbl` | 4 x .l | restore blitter per width class | R 0x14446 |
| 0x163da | `scroll_band_split_tbl` | 16 x 2 B | rows from tile above / below | R 0x14446 |
| 0x163fe | `map_row_ptr_reset` | .l | map pointer reset value (arm is dead) | W 0x11440 / R 0x14446 |
| 0x16402 | `map_row_ptr` | .l | current map row (walks upward, -20) | W 0x11440 0x14446 / R 0x14446 |
| 0x16406..0x16412 | `screen_ptr_0..3` | 4 x .l | the four rotating screens | W/R 0x14446 |
| 0x16416/1a/1e | `screen_draw/prev/prev2` | .l | 3-deep pointer history | W/R 0x14446 |
| 0x16422 | `screen_region_base` | .l | bottom of the circular region | R 0x14446 |
| 0x16426 | `blit_clip_mask` | .b | clip gate for the edge blitters | W/R 0x14dda.. |
| 0x1642a | `level_index` | .w | 0..4 | W 0x124ae 0x1139a / R 0x10bc8 0x14aa8 |
| 0x1642c | `prescroll_flag` | .b | render tiles only | W 0x11440 0x14aa8 / R 0x14446 |
| 0x1642e | `screen_index` | .w | 0..3 | W/R 0x14446 |
| 0x16430 | `scroll_fine` | .w | 0..30 step 2 | W 0x14446 / R 0x14446 |
| 0x16432/34/36 | map header + cells | | cols, rows, cell array | R 0x11440 0x14446 |
| 0x17696 | `level_just_started` | .w | suppresses pause/abort for one frame | W 0x14aa8 0x15750 / R 0x14354 |
| 0x1769a | `game_over_flag` | .w | | W 0x13c96 / R 0x124ae |
| 0x176a4 | `music_suspend_flag` | .w | set on death | W 0x1101c / R 0x1259c |
| 0x176a6 | `item_bomb_spawned_flag` | .w | one bomb item per level | W/R 0x12fc4 |
| 0x176aa | `game_over_delay` | .w | 0x50 frames | W 0x1139a / R 0x13c96 |
| 0x176ac/ae | `start_bombs` / `start_lives` | .w | per-level reset values | R 0x13c96 0x14aa8 |
| 0x176c0 | `weapon_decay_timer` | .w | 10 frames per step during the fly-off | W/R 0x13a20 |
| 0x176c2 | `item_pickup_pending` | .w | forces spawn type 1 -> 2 | W 0x121fe / R 0x12fc4 |
| 0x176c4 | `player_script_timer` | .w | auto-fire delay in mode 2 | W/R 0x13a20 |
| 0x176c6..d2 | `bonus_life_awarded_0..6` | 7 x .w | one-shot flags | W 0x110d4 |
| 0x176e4 | `hiscore_beaten` | .w | | W 0x10a2a |
| 0x176ec | `blast_step` | .w | 0..14 | W/R 0x10c8c |
| 0x176ee | `bomb_falling` | .w | | W 0x13d5c 0x10e7c / R 0x10e7c 0x10ee2 |
| 0x176f0 | `bomb_exploding` | .w | | W 0x10e7c 0x10c8c / R 0x10c8c 0x10d20 0x11b90 0x13d5c |
| 0x176f2 | `bomb_path_cursor` | .l | | W/R 0x10e7c |
| 0x176f6 | `death_anim_cursor` | .w | into `player_death_frames` | W/R 0x13c96 0x13bd6 |
| 0x1770a | `boss_scroll_pos` | .w | second level trigger | R 0x124ae |
| 0x1770c | `player_script_fire_enable` | .w | | W/R 0x13a20 |
| 0x17710 | `bombs` | .w | max 6 | W 0x13d5c 0x11698 0x13a20 / R 0x123d8 |
| 0x17712 | `lives` | .w | max 7 | W 0x110d4 0x11698 0x13c96 / R 0x123d8 |
| 0x17714 | `weapon_level` | .w | 0..4 | W 0x11698 0x13ebc / R 0x12fc4 0x13ebc |
| 0x17716/18/1a | `shot_slot_*_busy` | 3 x .w | one per 5-bullet shot | W 0x13e4e 0x141e4 |
| 0x1771c | `level_end_scroll_pos` | .w | | R 0x124ae |
| 0x17720 | `vbl_counter` | .l | frame budget | W 0x11636 0x14446 / R 0x14446 |
| 0x17724/26 | take-off script + cursor | | 4 B/step | W/R 0x13a20 |
| 0x17730/3a | landing script + cursor | | 4 B/step | W/R 0x13a20 |
| 0x1773c | `shadow_offset` | .w | plane/shadow separation = altitude | W 0x13a20 / R 0x13c96 |
| 0x17742 | `player_bank` | .w | tilt index | W 0x13baa 0x13dc2 0x13de8 / R 0x13d12 |
| 0x17744 | `player_bank_frames` | bytes | frame per bank, sentinel-bounded | R 0x13d12 0x13d24 |
| 0x17752 | `prescroll_frames` | .w | | R 0x11440 0x14aa8 |
| 0x17754 | `spawn_script_cursor` | .l | byte offset, +10 per record | W 0x14aa8 / R 0x12fc4 |
| 0x17758 | `scroll_pos` | .w | +2 per frame; the world clock | W 0x111ee 0x14aa8 / R 0x12fc4 0x124ae 0x14aa8 |
| 0x1775a | `level_complete` | .w | | W 0x13a20 / R 0x124ae |
| 0x1775c | `player_turning` | .w | left/right held this frame | W 0x14354 / R 0x13baa |
| 0x1775e | `player_input_locked` | .w | during scripts | W 0x13a20 / R 0x14354 |
| 0x17760 | `fire_held` | .w | edge-detects the fire button | W 0x14354 0x13e12 |
| 0x17762 | `shot_slots_full` | .w | | W 0x13e4e / R 0x13e12 |
| 0x17764 | `frame_counter` | .l | | W 0x11654 / R 0x119fc |
| 0x1776e | `level_tune_id` | .w | | R 0x12192 0x1259c |
| 0x17770 | `spawn_script_ptr` | .l | | R 0x12fc4 0x14aa8 |
| 0x1777e/7f/80 | input bytes | .b | **CROSS-SLICE**, written by the ACIA ISR | R 0x14354 and others |
| 0x1779a | `level_distance` | .w | `(scroll_pos-0x2e)/2+1` | W 0x111ee / R 0x1003c |
| 0x177c6..cd | cheat flags | .b | **CROSS-SLICE**, written by 0x10e30.. | R throughout |
| 0x177ce | `display_list` | 223x6 B | see §3.1 | W many / R 0x14446 |
| 0x17e0c | `tile_repair_grid` | 10 w/row | overlay repaint queue | W/R 0x14446 |
| 0x18014 | `sprite_restore_lists` | 4x512 B | dirty rects per buffer | W/R 0x14446 |
| 0x190a4 | `player` | 7 B | see §3.5 | W/R many |
| 0x190c0 | `spawn_handler_tbl` | .l x N | | R 0x12fc4 |
| 0x19128 | `entity_path_tbl_ptrs` | 3 x .l | | R 0x12e9e |
| 0x19134/0x19180 | hit-handler tables | 19 x .l | | R 0x11f0c / 0x11bb6 |
| 0x19210 | `player_death_frames` | words | -1 terminated | R 0x13c96 0x13bd6 |
| 0x19232 | `weapon_fire_tbl` | 5 x .l | | R 0x13ebc |
| 0x19246..0x1946e | entity group tables | .l arrays | see §3.3 | R every per-frame pass |
| 0x19422/36/4a | `player_shot_slot_0..2` | 5 x .l | | R 0x140cc 0x14118 0x141b4 0x13ebc |
| 0x1946e | `enemy_bullets` | 16x10 B | | W 0x128ce / R 0x12964 0x1101c 0x125bc |
| 0x19518..0x1952f | `anim_frame_*` | 6 x .b | cycling frame ids | W 0x119fc / R 0x1184e 0x1191c 0x12b40 0x12f2e 0x12348 |
| 0x19534..0x197f8 | enemy descriptors | | see §3.4 | W 0x12cc8 / R many |
| 0x1ae0c/0x1af80/0x19a54 | formation tables | .l arrays | | R 0x130aa 0x131a4 |
| 0x1b02a | `item_flight_path` | 4 B/step | 999-terminated, loops | R 0x118da |
| 0x5ae9a..0x5aede | items + player bomb | 7x10 B | see §3.8 | W/R 0x1165c 0x1187a 0x1191c 0x13d5c 0x10e7c |
| 0x5aec2 | `blast_state` | | impact point + 4 sprite positions | W 0x10e7c 0x10c8c / R 0x10d20 |

---

## 11. Open questions

1. **`0x17706`** is set when the player dies (0x1101c) and when `scroll_pos`
   passes `boss_scroll_pos` (0x124ae), cleared at level start unless the
   `0x177cb` cheat is set, and tested by the stub at `0x12856`. Two very
   different triggers for one flag; I have not found a reading that covers both,
   so it is left unnamed.
2. **`entity_group_bigobj` (0x193b6)** is clearly a large multi-part object —
   `0x102de` publishes three extra parts with frames 0x4f/0x4a/0x4b when its
   first entity's `+22` is 999, `0x1179a` hides anything inside a 0x40x0x40 box
   around it, and `0x11820` flips a depth flag on it by comparing y. Whether it
   is the end-of-level boss, the aircraft carrier or a cloud bank needs a run
   under Hatari or the sprite art extracted.
3. **`0x1227c`/`0x122c0`/`0x12348`** publish pairs of sprites at fixed offsets
   using `anim_frame_a` and gated on entity `+38`. Helicopter rotors and muzzle
   flashes both fit; the names carry `# ctx`.
4. The **`0x1003c` level-2 scenery effect** is fully decoded mechanically (it
   blits tiles out of the third HSC bank into a band that grows from
   `level_distance` 0x8a2 and shrinks after 0x96e) but what it depicts is not
   established.
5. **Enemy descriptor fields `+10`/`+12`/`+26`** are read by `0x128ce` and
   `0x1387a` but their per-type values have not been tabulated; a dump of all 25
   descriptors would settle the remaining offsets and name the enemy types.
6. The **`0x1581a` dead blitter's** 10-vs-12 byte discrepancy suggests it is a
   stale copy from a version where the tile row was 10 bytes wide (i.e. a
   different tile geometry). Worth a look if an earlier build turns up.
