# render/atari — run the remaster HUD on a real 68000 (Hatari)

remaster renders only the HUD so far, so this cross-compiles `rm_draw_hud` to 68000 and runs it as
a GEMDOS `.PRG` under Hatari — proving the remaster C is correct not just on the host, but compiled
and executed on an independent 68000.

Because the HUD reads asset tables (font, colour-fill table, mask/cursor tables, the gauge string,
the dashboard graphic and the variant sprites from `buf_c`) that normally come from the recreate
loaders, we **capture them once on the host** (`gen_hud_fixture.py`, via the same `adapter.py` the
equivalence tests use), bake them + the `HudState` into `build/hud_fixture.h`, and draw the HUD over
a **blank screen** on-target — rendering only what remaster's C implements (no captured game frame).

## The proof

`gen_hud_fixture.py` also writes `build/golden.bin` — recreate's `g_draw_hud` on the same blank
screen. The demo dumps its painted framebuffer to `C:\SCREEN.BIN`; `run_hatari.py` byte-compares
that against `golden.bin`. A **MATCH** proves remaster's HUD, cross-compiled and run on a real 68000,
is pixel-identical to the verified recreate cores. (recreate's HUD is itself verified byte-for-byte
against the Musashi oracle, so this closes the loop end to end.)

## Pieces

| file | role |
|------|------|
| `gen_hud_fixture.py` | capture background + assets + `HudState` + golden + palette from the host harness |
| `main.c`             | TOS shim: build the structs from the fixture, `rm_draw_hud`, dump `SCREEN.BIN`, set palette, blit, wait for a key |
| `os.s` / `tos.ld` / `mkprg.py` | GEMDOS entry + trap wrappers, link script, `.PRG` wrapper (copied from recreate's harness) |
| `shim_include/string.h` | minimal freestanding `<string.h>` (bare-metal GCC ships no libc) |
| `build.sh`           | generate fixture → cross-compile `hud.c`+`text.c`+shim → `.PRG` → stage `disk/` |
| `run_hatari.py`      | headless: run the `.PRG`, byte-compare `SCREEN.BIN` vs `golden.bin`, write a PNG |
| `run.sh`             | interactive: watch it in the Hatari GUI |
| `gen_demo_fixture.py` / `demo_main.c` | the interactive road + HUD demo (below): fixture + TOS shim with the steer loop |
| `build_demo.sh` / `run_demo.py` | build/verify `DEMO.PRG` (geometry + road + HUD cores) |

## Use

```bash
cd projects/buggyboy/recreate && make build/libbuggyboy.so   # once: the fixture generator drives it
cd ../remaster
bash render/atari/build.sh                 # -> build/HUD.PRG + disk/HUD.PRG
python render/atari/run_hatari.py          # headless: prints MATCH, writes out/render/remaster_hud_hatari.png
bash render/atari/run.sh                   # watch it in Hatari (press a key in the ST to exit)
```

Hatari needs a 4 MiB machine (`--memsize 4`); `build/` and `disk/` are gitignored build artifacts.

## Playable demo (`DEMO.PRG`)

The whole Phase-A render pipeline, driven by the ported **player physics** — you drive the buggy.
Each frame is game_update-then-draw, as the original orders it:

1. `rm_player_update` (`src/player.c`) — the driving model: throttle → engine rpm → speed, speed →
   the road-scroll rate and the **view advance whose wrap advances the course**, steering → wheel
   position → body lean and road curvature, and the road-edge clamp / off-road push. Its outputs are
   fanned out to the render structs (`apply_player`), which is all the game loop is beyond this.
2. `rm_gobj_prefix` (off-frame state) → `rm_build_road_geometry` (from the current pose) →
   `rm_render_road` → `rm_blit_road_scroll` (the scrolling near-road band + sky) → the
   `draw_game_objects` tree (`rm_draw_ground`, `rm_draw_fg_sprite`, the two roadside
   `rm_draw_object_list` passes split around the scaled `rm_draw_object`, and `rm_draw_buggy` ordered
   against the fixed pass by the view) → `rm_draw_hud`, and flips.

```bash
bash render/atari/build_demo.sh            # -> build/DEMO.PRG + disk/DEMO.PRG
python render/atari/run_demo.py            # headless: prints MATCH, writes out/render/remaster_road_hud_hatari.png
hatari --memsize 4 --tos-res low --harddrive render/atari/disk --auto 'C:\DEMO.PRG'   # play it
```

Controls (**held** keys — see below): **↑/↓** throttle / brake, **←/→** steer, **Space** fire (cycles
the dashboard variant, as in the original), **R** restarts the leg, **Esc/Q** quits.
`gen_demo_fixture.py` bakes the render_road static
tables (param/edge/texture), the geometry const sources, the scroll playfield, the leg-1 packed
course stream, the initial pose/scroll/course state, the HUD assets, and the object arenas (the `buf_a`
record arena, the `buf_c` sprite/graphics arena, and the STATIC+bss table blob the object dispatcher
reads) into `build/demo_fixture.h`, plus `golden.bin` (recreate's `g_build_road_geometry` +
`g_render_road` + `g_blit_road_scroll` + `g_draw_game_objects` + `g_draw_hud` for the same pose).
`run_demo.py` byte-compares the demo's first frame — drawn *before* any physics runs — against it; a
**MATCH** proves the whole ported pipeline is pixel-identical on a real 68000. The physics driving it
is validated on the host against recreate's `g_game_update` (`test/test_player.py`), as are the
geometry and course advance (`test/test_geometry.py`, `test/test_course.py`).

### Held keys: the demo takes the IKBD interrupt

GEMDOS reports key *presses*; driving needs to know which keys are *held*, and several at once
(throttle plus steering). So the demo installs its own handler on the IKBD ACIA interrupt (MFP
channel 6, vector `0x46` @ `0x118`) after switching mouse and joystick reporting off — which is what
leaves the ACIA delivering nothing but keyboard make/break scancodes, so the handler in `os.s` is
just "bit 7 clear → down, set → up" into a 128-byte `key_down[]` table the C polls once a frame. The
old vector and the mouse mode are restored on exit. The first-frame dump happens *before* the install,
so the headless MATCH run never depends on it.

### Aliased globals the demo has to model

recreate threads one flat image, so several logically-separate tables share an address. The demo keeps
them separate and must reproduce the aliasing explicitly — each of these caused a real on-target diff:

| Alias | Effect |
|-------|--------|
| `anim_color` == `fuel_mask` (`0x17f08`) | the prefix's animated colour **is** the HUD's phase-6a fuel mask, so both point at one mutable buffer |
| `obj_xoff_tbl` == `road_width_tbl + 2` (`0x18f26`) | the object dispatcher's x-offset table is the freshly built control table, so it is rebound to `ctrl` each frame |
| `ground_view_off` == `obj_scan_off` (`0x18c58`) | the ground's view column and the object list's scan offset are one value (`view_flags * 0xdd`) |

`draw_game_objects` also writes off-screen sprite fragments well past the visible 32000 bytes, so each
screen buffer carries a `SCREEN_OVERDRAW` tail (in the original the draw buffer is followed by ample
RAM). Two debug build flags: `DEMO_EXTRA_CFLAGS=-DDEMO_DUMP_STAGE=N` cuts the frame short after stage
N (0 road, 1 ground, 2 foreground, 3 pass 1), so the dump holds a partial frame — that is how an
on-target divergence gets bisected to a single stage. `-DDEMO_AUTODRIVE=N` replaces the keyboard with
a fixed input script and dumps the frame after N frames, which is how the *loop* (physics → course
advance → render, on the 68000) gets checked headlessly rather than only frame 0.

Scope note: the throttle scrolls the course's authored **segment slopes** (`seg_data`) through the
geometry builder, and `build_road_geometry` integrates them into the per-row road offset — so the
road's hills and left/right curvature stream from the leg's packed course as you drive, on top of the
player's own `road_curve`. Not modelled yet, because they live in the unported parts of
`game_update`: the crash / auto-steer script, object collision, the horizon-event dispatch (including
its discrete `road_curve += ±0x3c` bonus/spin kicks), and section 12's object ring — so the roadside
object list does not stream along the course the way the road surface does, and nothing can crash you.

The alignment gotcha: the cores read the baked tables with `be16`/`be32` (word/long moves), which
fault on an odd address on the 68000, so the fixture arrays and the BSS scratch are `aligned(2)`.

## Scope

Only remaster's own rendering is drawn, over a **blank screen** — no captured game frame. The HUD
demo (`HUD.PRG`) is HUD-only; the road demo (`DEMO.PRG`) adds the road surface and live steering.
As more of the pipeline is ported (road scroll, objects), this harness extends toward whole frames.
