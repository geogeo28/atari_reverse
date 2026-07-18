# BuggyBoy course editor

A Python tool to **decode, edit, and re-pack** `COURSES.DAT` — the file that
defines all five legs of the BuggyBoy race. It is built on the verified C
reconstruction in [`../recreate`](../recreate): the format constants here mirror
the reconstructed cores (each tagged with its C source), and edits can be
**previewed by re-rendering** through the same `libbuggyboy.so` the differential
suite proves correct.

## What a course is (short version)

`COURSES.DAT` (0xF660 bytes) loads at `mem_base`; `buf_a = mem_base + 0x1900`.
The whole file *is* the course data, in three parts:

```
file 0x0000 ── 0x1900   5 dashboard track-map bitmaps      (mem_base + leg*0x500, 40 rows x 0x20)
file 0x1900 ── ...      buf_a tables: scroll (leg*0x10), obj/pal selectors (+0x50),
                        record table (+0xf2), label descriptors (+0x8c0), ...
per leg:  anchor = buf_a + leg*0x2000 + 0x5ce0   (file 0x75e0 + leg*0x2000)
          the course-record STREAM, read *backward* from the anchor
```

Each leg is a stream of **8-byte records**, pulled one at a time as the road
scrolls (a treadmill: `build_road_geometry` turns a sliding 12-segment window into
per-scanline perspective tables for `render_road`). Record layout:

| Bytes  | Field | Meaning |
|--------|-------|---------|
| `+0..1`| select mask (15 bits) | which slope/width/object slots update this row |
| `+2`   | control | `(b&0xf8)>>3` = rows this record is held; `(b&7)-3` = marker-decay seed |
| `+3..5`| payload | up to 3 bytes (sparse, gated by the mask; anim codes `0x0d/0x10/0x13/0x16` expand into 2-word runs) |
| `+6..7`| marker word | roadside object / event; **bit15 set = active**. Identical values across consecutive records = a *continuous* feature (wall / fence / tree-line) |

Marker classification (mirrors `game_update`'s mask tests): `&0xf01e==0xf012`
checkpoint-ish, `==0xf000` collision-ish, `&0x6000==0` score/message. See
`docs/` in the parent workspace and `../recreate/src/game_update.c` for ground truth.

> **Known quirk.** A popcount-4 record's 4th payload byte lands on the `+6` marker
> word; the engine reads it as a marker but zeroes it because it's positive. So the
> `+6` field is only a *real* event when bit15 is set. The editor treats it as such.

## Architecture

Three small modules + a safety test. No third-party deps (stdlib only).

```
editor/
├── course_format.py   constants (mirrored from the C, each tagged) + pure decoder
├── course_file.py     mutable CourseFile: patch-in-place edits + backup-on-save
├── mapview.py         decode a leg's dashboard bitmap -> ASCII track-map preview
├── roadprofile.py     decode the road elevation profile + object slots from the stream
├── roadview.py        draw the road via the VERIFIED render_road (-> PNG/ASCII) + GameSession
├── roadwin.py         playable graphical window: drive the game through the verified code
├── course3d.py        build a 3D course model (track-map path + elevation + objects) for the web UI
├── web/               Flask + three.js interactive 3D editor (server.py + static/)
├── decode_course.py   CLI: dump a leg's stream, scroll table, markers
├── tui.py             curses UI: records + live map paint + road profile + PNG render
├── test_roundtrip.py  safety: identity round-trip + reversible edits + map decode
└── README.md          this file
```

**Patch-in-place, never re-serialize.** The format is reverse-engineered and has
quirks, so `CourseFile` keeps the original bytes and mutates only the fields you
edit, at their known offsets. Consequences:
- an unedited load→save is **byte-identical by construction** (pinned by
  `test_identity_roundtrip`);
- every edit is a small, auditable byte patch;
- we never risk corrupting the file by mis-packing a field we don't fully understand.

**Single source of truth.** Every offset/stride in `course_format.py` is copied
from a verified C symbol and commented with it (`src/game_update.c`, `src/road.c`,
`src/gameplay.c`, `src/results.c`, `src/os.c`). If the C changes, these must be
updated in lockstep — a future test could pin them equal by parsing `addrs.h`.

## Use

```bash
mlenv python web/server.py                            # 3D web editor -> http://127.0.0.1:5000
cd editor
python tui.py                                         # terminal editor: records + live map + road
mlenv python roadwin.py --leg 0                       # playable window (drive the verified game)
python decode_course.py --leg 0 --records 40 --raw    # inspect leg 0 (non-interactive)
python roadview.py --leg 0 --seg 40 --ascii           # third-person road (terminal)
python test_roundtrip.py                              # or: pytest test_roundtrip.py
```

### 3D web editor (`web/`, Flask + three.js)

The main interactive editor: a browser 3D view of a leg's course, built from the decoded data
and editable live.

```bash
mlenv python web/server.py      # needs flask; open http://127.0.0.1:5000
```

- **The road** is a 3D ribbon whose horizontal PATH is traced from the leg's dashboard track-map
  bitmap (largest connected component, longest path via double-BFS), whose HILLS come from the
  record stream's segment slopes (elevation profile), with roadside-object markers from the
  stream's object slots.
- **Orbit** to inspect the whole course, or switch to **drive** (`M`) and follow it: `W`/`S`
  throttle, `A`/`D` steer the view.
- **Edit segment slopes** in the side panel — the 3D road re-renders live (POST `/api/edit` →
  refetch the model). **Save** writes `COURSES.DAT` (a `.bak` first).
- **▶ play (real game)** — switches to the **authentic** render: the browser streams the verified
  `GameSession` framebuffer (verified `game_update` + `draw_frame`), so you drive the actual game
  — real pseudo-3D road, real object **sprites**, buggy and HUD — with arrows/WASD + space. It
  stages the current (edited) `COURSES.DAT` bytes, so your edits are driven. Needs the built `.so`.

The 3D scene is a reconstruction of the course *data* (traced path + hills + object markers); the
**play** mode is the game's own pixels. Two honest views of the same leg — the 3D to see the whole
course shape and edit it, the play mode to see exactly how it renders.

### Interactive UI (`tui.py`)

A two-pane curses editor with two modes.

**Record mode** — the left pane is the selected leg's scrollable course-record stream;
the right pane is a live ASCII render of that leg's course line (plane1/`w1`).

```
 ↑/↓ or j/k   move selection       [ / ] or Tab   change leg (0..4)
 m  set marker word (hex)   r  set rows (1..31)   t  toggle event bit (0x8000)
 g  -> paint mode           w  save (.bak first)  q  quit (confirms if unsaved)
```

**Paint mode** (`g`) — redraw the leg's course *shape* directly and see it live. A pixel
cursor moves over the 128×40 track bitmap (the pane scrolls to follow it); painting
toggles the track plane (`w1`) only, leaving the scenery plane untouched, so the map
marker's path always matches what you draw.

```
 ↑↓←→ or hjkl   move cursor        space  toggle the pixel under the cursor
 p  draw-pen (movement paints)     e  erase-pen (movement clears)   [ / ]  change leg
 g  -> record mode                 w  save (.bak first)             q  quit
```

**Road mode** (`d`) — the road geometry we drive: a side-view **elevation profile** of the
leg (the hills/crests/dips), decoded from the record stream. The selected segment is
shared with the record browser, so `[` `]`/nav line up. Raise/lower a segment's slope live,
or render the third-person view:

```
 ←→ or hl   select segment        + / -   raise / lower that segment's slope (-3..+4)
 P  render the third-person road (current leg+segment) to a PNG via the verified renderer
 [ / ]  change leg                g map / d records                 w save   q quit
```

See **Road geometry** and **Third-person view** below.

The map is decoded from the file bytes every frame, so edits render instantly. For a
pixel-accurate render through the real rasterizer, save and run
`render_screen.py --screen map --leg N` (below).

## Third-person view (`roadview.py`)

Draws the road the way the game does — through the **verified** `render_road`. It stages the
reconstruction's image, feeds the leg's real elevation slopes into `road_seg_data`, sets the
curve/view/horizon, then calls `g_build_road_geometry` + `g_render_road` and de-interleaves the
ST framebuffer to a PNG (or ASCII). Needs the built `recreate/build/libbuggyboy.so`.

```bash
python roadview.py --leg 0 --seg 40                  # -> out/render/road_leg0_seg40.png
python roadview.py --leg 2 --seg 80 --curve 0x120    # gentle right bend
python roadview.py --leg 0 --seg 40 --ascii          # terminal preview
```

What's authentic vs. supplied:
- the **rasterizer** is the verified `render_road` (byte-for-byte vs the 68000) — the perspective,
  edges and shoulders are the game's own;
- the **hills** come from the leg's stream (segment slope, decoded by `roadprofile`);
- the **curve** is a parameter (steering state, not in the file), default straight;
- the road-**width taper** is a supplied default (`road_width_src` is runtime state, zero in a
  cold image), so the road has a sensible near→far taper to render into.

In the TUI, `P` in road mode renders the current leg+segment (using the *edited* in-memory bytes,
so slope edits show up) to `out/render/`.

### Live 3rd-person view in the terminal (`v`)

Press `v` for a **live** third-person render, drawn as ASCII straight from `render_road` and
re-rendered every keystroke (~0.4 ms/frame, so it's smooth):

```
 ←→ or hl   move along the leg     + / -   steer the curve     space  auto-drive (animates)
 P  save the current view to PNG   [ / ]  change leg           d  records   q  quit
```

`space` toggles auto-drive: the position advances down the leg on a timer so you drive through
it, hills and all. Steering (`+`/`-`) bends the road live. Uses the edited bytes, so slope edits
in road mode show up here immediately. Falls back to a message if the `.so` isn't built.

### Playable graphical window (`roadwin.py`, pygame)

For a **real pixel** view (not ASCII), `roadwin.py` opens a scaled window that **drives the whole
game through the verified reconstruction**: each frame injects your held keys as `input_state`,
calls the verified `g_game_update` + `g_draw_frame`, and blits the ST framebuffer (game palette).
The road, the roadside object **sprites**, the buggy and the HUD are all the game's own verified
rendering — nothing is faked or overlaid.

```bash
mlenv python roadwin.py --leg 0      # needs pygame + numpy + the built .so
```

```
 arrows / WASD  accelerate / brake / steer     space  fire
 [ / ]  previous / next leg (restart)          r  restart leg
 p  save a PNG of the current frame            esc / q  quit
```

The engine is `roadview.GameSession`: it stages the image once, calls the verified `g_init_leg`,
then `step(input_bits)` runs one `g_game_update` + `g_draw_frame` per frame (~sub-ms). Because it's
the real game logic, the buggy accelerates/steers, the course scrolls, roadside objects stream past
as sprites, and the HUD updates — all byte-for-byte the reconstructed code.

## Road geometry (what's in the file)

Established empirically (see `roadprofile.py`; validated by `test_road_profile_matches_control_bytes`):

- **Elevation is in the file.** Each 8-byte record sets a segment slope = `(control & 7) - 3`
  (−3..+4), held for `rows = (control & 0xf8) >> 3` scanlines. `game_update` writes that slope
  to `road_seg_data[12]` — the new far segment — and the **verified** `build_road_geometry`
  turns the 12-segment window into the per-scanline perspective the rasterizer draws.
  Accumulating slope×rows down the leg is the hill profile (road mode plots exactly this).
- **The roadside-object layout is in the file** — the 15 mask-gated payload slots hold
  object-type codes (0 = empty).
- **The horizontal curve is *not* in the file.** `road_curve` is runtime steering state, so
  the editor does not fabricate a curve plot; it decodes only what the stream actually encodes.

Editing a segment's slope is `set_control(leg, k, rows, slope)` (the slope is that call's
`decay` argument), so road-mode edits persist to `COURSES.DAT`.

Editing, programmatically:

```python
from course_file import CourseFile
c = CourseFile.load("../bin/COURSES.DAT")
c.paint_marker_run(leg=0, k0=20, length=8, word=0x8800)  # add a continuous roadside feature
c.set_scroll(leg=0, frame=2, band=4)                     # tweak the road-band scroll cycle
c.save("../out/COURSES.DAT")                              # writes a .bak first, never clobbers blind
```

## Preview (the payoff of building on the verified cores)

Because the reconstruction links into `libbuggyboy.so`, an edited course can be
*rendered* without an emulator, using the parent's existing tool:

```bash
# after saving an edited COURSES.DAT where render_screen.py can find it:
python ../recreate/render/render_screen.py --screen map --leg 0   # per-leg track map + marker
```

`render_screen.py` stages `COURSES.DAT` at its real address and calls the verified
`g_init_leg_dash` / `g_draw_dashboard`, so the track-map preview reflects your edit.
A fuller in-race preview would drive `g_game_update` + `g_draw_frame` — deferred
until `game_update` is verified (it's the current work-front in `recreate/`).

## Roadmap

1. **Decode — done.** Records, scroll table, markers, marker classification.
2. **Edit — done (field-level).** Marker/mask/control/payload/scroll + marker runs,
   with a lossless round-trip guarantee.
3. **Semantics — in progress.** Elevation (segment slope) and the roadside-object slot
   layout are decoded (`roadprofile.py`); the horizontal curve is runtime steering, not
   file data. Still to name: the object-type codes (via `game_update`'s jump table) and
   the `+0xf2` object/palette records. The dashboard bitmap is editable as pixels (paint
   mode); `w1` is the track line the marker walks, `w0` the scenery fill.
4. **Validation.** Road-mode slope decode is pinned to the control byte by test; the deeper
   win is to drive the (in-progress) verified `game_update` from a leg start and diff the
   reconstructed road geometry against this stream decode.
5. **UI — done (v1).** `tui.py`: record browser, live map paint, road elevation profile with
   live slope editing, third-person PNG render + live in-terminal view; plus `roadwin.py`, a
   **playable** pygame window that drives the whole verified game (real road, object sprites,
   buggy and HUD). Next: name the object-type codes inline, and feed edited `COURSES.DAT` into a
   live session so course edits are drivable end to end.

## Open questions (tracked, not yet resolved)

- The unpack ORs `coll_mask_hi << 16` into the select mask but the loop only tests
  bits 14..0 — so `coll_mask_hi` looks unused in the payload expansion. Confirm
  against the disassembly whether a wider loop exists on some path.
- Exact slot semantics of the 15 mask bits (which are road slope, which width,
  which object type) — decode by cross-referencing `road_seg_data` /
  `road_width_src` consumers.
- Whether records are ever pulled at a non-8 stride (they are not in the current
  reading; `read_pos += 8` per pull is fixed).
