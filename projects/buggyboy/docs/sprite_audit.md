# GRAPHICS.GRA usage audit — what the game ships and never draws

Reproduce with `make audit AUDIT_ARGS='--out ../out/sprite_audit'` from `recreate/` (or directly:
`python3 tools/sprite_audit.py --out out/sprite_audit` under `recreate/.venv`, with
`recreate/build/libbuggyboy.so` already built — the script's `import harness` dlopens it before it
builds its own instrumented copy). Every number below comes from that run; the PNGs it writes are
not committed.

## What is in the file, and where it ends up

`GRAPHICS.GRA` is 182,428 bytes: a 3,328-byte (`0xd00`) header, then an RLE stream. `unpack_graphics
@0x10620` (reconstructed as `g_unpack_graphics`, verified byte-for-byte) turns those into the two
tables the game actually reads from:

| table | size | built from | read by |
|---|---|---|---|
| `buf_b` | `0xd000` = 208 × 16 pre-shifts × 16 B | the header, via `build_sprite_shifts` | `render_road` (road surface + edge textures) |
| `buf_c` | 240,000 B: page 0, page 1's two low planes, pages 2–7 | the RLE stream (255,992 B decoded) | every sprite blitter, the backdrop scroll, the HUD |

Two structural facts worth recording (both verified against the staged image, not inferred):

* **The header is 208 × 16-byte records, not 416 × 8.** `build_sprite_shifts` consumes 16 bytes per
  record (four plane accumulators, stored as four high words then four low words) and emits 16
  shifted copies of 16 bytes each. Header record *i* therefore owns exactly
  `buf_b[i * 0x100 … (i+1) * 0x100)` — a read in `buf_b` names the header record it came from, with
  no ambiguity. 208 × 0x100 = 0xd000 = `buf_c − buf_b` exactly.
* **Page 1 loses its two high planes by construction.** The compaction step keeps the first longword
  of each 8-byte interleaved group, i.e. planes 0 and 1. Planes 2 and 3 of page 1 are `0xff`
  throughout in the decoded stream, so nothing is lost — the region is 2-plane data stored in a
  4-plane container, and the RLE encodes those two constant planes as run markers.

## Method

**Dynamic read coverage.** `tools/sprite_audit.py` builds a second copy of the reconstruction with
`recreate/build/audit/machine.h` shadowing the kit's `machine.h` on the include path: it includes the
real header, then macro-wraps `be16`/`be32`/`wr16`/`wr32`/`memcpy`/`memset` so every access inside
`[buf_b, buf_c + 240000)` is recorded. It is built through the project's own Makefile (the kit's
`EXTRA_CFLAGS` / `EXTRA_SRC` hooks), so the flags are the candidate's; nothing else changes, and the
instrumented `.so` passes the whole differential suite unchanged (296 passed), so the thing being
measured is still the verified reconstruction.

A byte counts as **used** only if it was read *while still holding its unpacked value*, judged per
staged image. A byte the game overwrites before reading in a given image — the dashboard course map
that `init_leg_dash` builds over page 2 — carries no file content *there*, so its read is not
counted; whether the same byte is read pristine in some other scene is reported separately. The write
gate is cleared whenever a fresh image is bound, because the next image's atlas is pristine again; an
earlier version that kept it globally under-reported the leg-banner glyphs by 320 cells.

**What was driven** (each scene's contribution is printed by the tool):

| scene | what it covers |
|---|---|
| 5 legs × 6,000 frames, throttle held | real driving: road, scroll, objects, buggy, HUD |
| 5 legs × 6,000 frames, forced course stream | one course section per frame, so a short run walks the whole leg |
| leg-select / leg-results screens, all 5 legs | banner, panels, dashboard map, leg labels |
| results / high-score, 5 legs × 3 modes × 4 ranks | results screen, score table, the full name-entry countdown |
| intermission scroller, scroll −160…+160 | the attract-mode credits/table/times scroller and its backdrop |
| HUD variants + crash effect | all 8 `dsp_variant_idx` dashboard sprites, 128 frames of `draw_crash_fx` |
| buggy poses | lean 0–49 × wheel 0–4, skid/pitch offsets, the `crash_anim_tbl` script, every `fg_anim_tbl` frame |
| road backdrop + checkpoint scroll | every band `set_screen_offset` can pick, every `hscroll_pos` the wrap allows, 5 checkpoint steps |
| roadside object sweep | object types 1–63 **and the special pass** × 12 slots × 6 views × 2 parities × 3 screen-x, all 5 legs |

The object sweep is the *reachability* pass: it draws each type straight from its record rather than
waiting for the course data to schedule it, so a sprite only one leg's traffic reaches still counts.
A flag word with bit 15 set selects `draw_object_list`'s SPECIAL record block at `buf_a + 0x21d0 +
slot`, which the sweep drives alongside the 63 ordinary types.

The name-entry countdown is driven over its whole range. `update_highscore` seeds
`countdown_timer` with `COUNTDOWN_START` (30) and `hiscore_countdown` drops it one every
`CD_SUB_PERIOD + 1` = 18 ticks, so the values the screen can show are exactly 30 down to 0. The audit
pokes the timer directly through those 31 values rather than spending 558 ticks per screen reaching
them — same digit pairs, including the `/` the tens digit becomes below 10 (`highscore.c:142`), an
eighteenth of the frames.

**Static cross-check.** The tool walks the object records the dispatcher resolves — `buf_a + 0x8a0 +
type*0xd0 + slot` for types 1–63 and `buf_a + 0x21d0 + slot` for the special pass, over all 12 slots
and all 5 legs — and the fixed source tables the program carries (`buggy_body_tbl @0x177b8`,
`hud_dsp_tbl @0x1854c`, `fg_anim_tbl @0x177a0`, and the four results-screen block constants). A slot
counts as a real sprite when its jump index lies inside `obj_type_jumptable`'s real extent (`0x13144`
up to the first handler at `0x131ac`, so 0x68 bytes) *and* resolves to one of the `OBJ_H_*` targets
`obj_dispatch` handles, other than the bare `rts`. There is deliberately no height heuristic: type
`0x36` slot 0 is 0x64 rows tall and a "plausible sprite height" bound dropped it. Each record's probe
covers its full source span — `rows` scanlines of 160 bytes walking *up* from `src` — because a
left-clipped sprite starts part-way into its first row and never touches `src` itself.

All **398** distinct object-record source spans (420 empty/malformed slots skipped) and all **57**
fixed pointers land inside territory the dynamic union read. Nothing points at a region the drive
missed.

**Poison proof.** Every never-read byte of the **whole** window — `buf_b` and `buf_c` alike — is
overwritten with `0x5a` and the *entire* scene list is re-driven; both drives digest every image they
touched (with the poisoned positions zeroed in both, so the poison itself cannot show up). The
digests match. The instrumentation only sees the accessors it wraps, so this is what turns "the
recorder saw no read" into "the picture does not depend on these bytes".

## Results

### Header / road-texture table: 200 of 208 records used

50,432 of 53,248 `buf_b` bytes are read. Eight records are never read: **128, 138, 148, 158, 168,
178, 188, 198** — file offsets `0x0800`, `0x08a0`, `0x0940`, `0x09e0`, `0x0a80`, `0x0b20`, `0x0bc0`,
`0x0c60`; `buf_b` blocks `0x8000`, `0x8a00`, `0x9400`, `0x9e00`, `0xa800`, `0xb200`, `0xbc00`,
`0xc600`. They are the 9th slot of each `0xa00` (ten-record) band from band 12 upward — the slots the
`+0x5800` and `+0xa800` source branches in `render_road` would select in the highest band groups.

**None of them is unique artwork.** Every one is byte-identical to a record that *is* read:

| unused record | bytes | 16-pixel pattern | identical used record(s) |
|---|---|---|---|
| 128, 138 | `ffffffffffffffff8000800080008000` | 16 px of colour 15 | 40, 50 |
| 148, 158 | `0001000100010001ffffffffffffffff` | 15 px blank + 1 px of colour 15 | 60, 70 |
| 168, 178 | `ffffffff000000008000800000000000` | 16 px of colour 3 | 85 |
| 188, 198 | `0001000100000000ffffffff00000000` | 15 px blank + 1 px of colour 3 | 87 |

So the header carries 198 distinct patterns in 208 slots; the eight unread slots are duplicate table
entries, not lost road textures. Every one of the 200 used records is read at all 16 of its
pre-shift positions.

### Atlas: 223,288 of 240,000 bytes read

16,712 bytes are never read (7.0 %). 1,130 never-read 16-pixel cells still hold ink — those are the
candidates below.

3,632 atlas bytes are *written* by the game (the per-leg course map `init_leg_dash` builds into page
2, and the labels `draw_leg_labels` stamps into page 1). **None of them is write-only**: every one of
those bytes is also read while pristine in a scene that does not build the map. This corrects an
earlier reading of this audit — the region is not scratch space that happens to ship with a fill
pattern, it is artwork the game draws from *and* reuses as a buffer. See "Page 2's shared panel"
below.

| page | cells read (of 4,000) | unread cells with ink | cells the game writes over |
|---|---|---|---|
| 0 | 4,000 | 0 | 0 |
| 1 | 3,733 | 0 | 268 |
| 2 | 3,764 | 236 | 320 |
| 3 | 3,937 | 63 | 0 |
| 4 | 3,967 | 33 | 0 |
| 5 | 2,723 | 768 | 0 |
| 6 | 3,992 | 8 | 0 |
| 7 | 3,978 | 22 | 0 |

#### The sprite character set — 24 of 37 characters drawn

`draw_num` (`@0x15a86`) is not a digit blitter: `num_glyph_tbl @0x17c5e` is a per-ASCII table of byte
offsets into a big blue-outlined character set at `buf_c + 0xbb80` (page 2 offset 0), covering `/`,
`0`–`9` and `A`–`Z`, each 15 scanlines of one 16-pixel cell. It is the font the leg-name banner
("OFFROAD" on the leg board) and the name-entry "TIME nn" are drawn in.

The characters laid out on page 2 are `0 1 2 / 3 4 5 / 6 7 8 / 9 A B` in a three-wide column at
x = 272…320, rows 49–108, then `C…J`, `K…R`, `S…Z` in eight-wide rows at x = 192…320, rows 109–123,
124–138 and 139–153. `/` is filed away on its own at page 3, row 50, cell 15 (x = 240):
`num_glyph_tbl['/'] = 0x9cb8`, so `buf_c + 0x15838`, and `0x15838 − 0x13880 = 50 × 160 + 120`. It is
a solid colour-1 bar — the blanked-leading-zero cell that turns "/28000" into " 28000".

* **Drawn (24):** `/ 0 1 2 3 4 5 6 7 8 9 A B D E F H N O R S T U W`
* **Never drawn (13):** `C G I J K L M P Q V X Y Z`

`/` and `1` are drawn by the name-entry countdown: `1` is the tens digit at TIME 19…10 and a units
digit at 21/11/1, and `/` is what `hiscore_countdown` writes for the tens digit once the timer drops
below 10. The other drawn letters are exactly the distinct letters of the five leg names (OFFROAD,
NORTH, EAST, WEST, SOUTH) plus `B`. Per-leg coverage confirms the mechanism: driving
`g_draw_leg_results` for one leg reads exactly that leg's name's glyph cells and no others.

Every one of these characters is **drawable by construction** — `num_glyph_tbl` maps it to a real
glyph and any string reaching `draw_num` that contains it renders it (checked directly: feeding
`draw_num` the string `1234567890ABCDEFGHIJ` reads all twenty of those cells). So this is unused
*data*, not unreachable art: the game ships a full alphanumeric sprite font and its own strings only
ever use 24 of the 37 characters. The high-score name column is drawn in the small program font
(`FONT_GLYPHS @0x176a8`), not this one, so player-entered initials do not reach it either.

Four of the unread page-2 regions the tool prints — `(272,109) 48×45`, `(192,109) 48×30`,
`(256,109) 16×15`, `(240,139) 16×15` — total 195 cells, which is exactly the 13 never-drawn glyphs at
15 cells each. The rest of page 2's 236 unread inked cells are a 48×4 sliver at `(272,45)` just above
the digit block (12 cells) and 29 cells in blobs too small to name.

#### Page 2's shared panel (320 cells, overwritten during a race)

Page 2 rows 154–193, x ≥ 192 is a solid blue panel in the file. `init_leg_dash` builds the per-leg
course map over it from `COURSES.DAT`, so during a race the packed content there is gone — but the
results screen, the HUD dashboard-variant sweep and the object sweep all read the *pristine* panel
(2,432 bytes each) in images where no map was built. The same holds for the 268 written cells
scattered over page 1 (rows 9–198, x 48–303), which `draw_leg_labels` stamps over. So this is a
region the game both draws from and reuses as a buffer, not dead fill.

#### Page 5: the largest block of never-drawn artwork

Page 5 is the worst-covered page (2,723 of 4,000 cells read). Its left 128 pixels are almost entirely
unread for rows 0–190, broken only by read bands at rows 8–11, 46–67 and 192–199. Two things live
there:

* **A 160×57 block at (0,135), 339 cells** — four pale-blue fan/spray sprites with orange-brown
  bases (two above, two below, mirrored left/right), and an orange-and-white plank or log below them,
  on a flat ground. They sit immediately left of the grey boulder sprites that *are* drawn, in the
  same style and at the same scale, so they read as finished roadside scenery — a splash, spray
  or bush object — that the shipped courses never place. No object record in any leg points at them,
  and the object sweep (every type × slot × view, special pass included) never touches them.
* **Sixteen smaller blobs (8–26 cells each) in the black field above**, which holds a pre-scaled
  sprite column: solid orange ladder/log shapes at the top shrinking to sparse diagonal dashes below.
  The unread blobs are interleaved with read cells, which is what an unused perspective *scale step*
  looks like rather than an unused object.

#### The remainder (pages 3, 4, 6, 7 — 126 cells total)

* Page 3: a 64×5 lilac bar at (128,60) and two solid-colour blocks beside the bonus-score plates
  (16×10 at (256,49), 16×15 at (240,65)). Flat fill, no discernible subject.
* Page 4: 33 isolated cells, no blob large enough to name.
* Page 6: 8 cells.
* Page 7: a 48×3 sliver at (192,33) of the buggy sprite sheet — three scanlines of one pose — plus a
  few isolated cells.

## What this audit does and does not establish

* **Established for the whole window.** The poison proof re-drove every scene with all 19,528
  never-read `buf_b` + `buf_c` bytes overwritten (2,816 in the shift tables, 16,712 in the atlas) and
  nothing the game drew changed. That covers read paths the instrumentation might have missed, not
  just the wrapped accessors — and it now covers the eight unread header records too, so their
  disuse is proved rather than merely unrecorded.
* **"Never drawn in these runs", not "unreachable".** The sprite font's 13 unused characters are
  reachable by construction; they are unused because no string the game renders contains them. The
  page-5 splash sprites are stronger: no object record in any leg names them, and the exhaustive
  type × slot × view sweep never reads them — but a record is per-leg data, so the claim is about the
  five shipped courses, not about the engine.
* **Two interactive tails were not executed.** `g_hiscore_name_entry` and `g_hiscore_gameover` are
  joystick/music spin loops that never return without hardware. The audit drives their drawing halves
  instead (the jingle seam, all 31 countdown renders, the results redraw those loops perform).
  Reading their bodies shows they compose only already-covered calls — `draw_results_screen`,
  `xbios_setpalette`, `flip_screen`, `play_event_tune` — so no additional atlas source is reachable
  through them.
* **The oracle's `init_leg` is outside the instrumentation.** `mid_race_state` runs the *original*
  68000 `init_leg` under Musashi to stage each race. Any atlas read that routine makes is invisible
  to the recorder. It runs before the poison is applied in both drives, so it cannot mask a
  divergence, but a source only `init_leg` ever reads would be mis-reported as unused. `init_leg`
  populates the per-leg object records rather than drawing, and the static pass covers every pointer
  it writes.
* **Collision/event-only draws.** Crash, spin and the flag-gate bonus window are driven from the
  game's own `crash_anim_tbl` — walked the way `game_update` walks it, by its `8 − rec[0]` step rule
  from every entry index the code writes into `collision_lock` — and from 6,000-frame drives per leg,
  but a rare event (a specific collision sprite in one leg) could in principle be missed. Any such
  sprite would have to be named by an object record, and every record pointer is accounted for.

## Suggested follow-ups

* The eight duplicate header records and the page-5 splash sprites are the two findings worth a
  `names.txt`/docs note. The header's record geometry (208 × 16 B, record *i* → `buf_b + i*0x100`)
  and `num_glyph_tbl`'s real role (a 37-character sprite font, not a digit table) are both worth
  recording as facts about the format.
* If the remaster ever needs space, page 5's left 128 pixels and the 13 unused font glyphs are the
  only sizeable regions that provably reach nothing.
