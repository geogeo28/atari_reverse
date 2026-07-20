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

## Interactive road + HUD demo (`DEMO.PRG`)

Now that `render_road`, `build_road_geometry` and `blit_road_scroll` are ported, a second demo drives
remaster's **whole road + HUD pipeline** on the 68000 and lets you **steer the road live**. Each frame
runs `rm_build_road_geometry` (from the current pose) → `rm_render_road` → `rm_blit_road_scroll` (the
scrolling near-road band + sky) → `rm_draw_hud` and blits.

```bash
bash render/atari/build_demo.sh            # -> build/DEMO.PRG + disk/DEMO.PRG
python render/atari/run_demo.py            # headless: prints MATCH, writes out/render/remaster_road_hud_hatari.png
hatari --memsize 4 --tos-res low --harddrive render/atari/disk --auto 'C:\DEMO.PRG'   # play it
```

Controls: **←/→** steer (road curvature), **↑/↓** crest/dip the near slope, **Space** cycles the view
bank, **R** resets, **Esc/Q** quits. `gen_demo_fixture.py` bakes the render_road static tables
(param/edge/texture), the geometry const sources, the initial pose and the HUD assets into
`build/demo_fixture.h`, plus `golden.bin` (recreate's `g_build_road_geometry` + `g_render_road` +
`g_blit_road_scroll` + `g_draw_hud` for the same pose). `run_demo.py` byte-compares the demo's first
frame (before any key) against it — a **MATCH** proves the whole ported pipeline is pixel-identical on
a real 68000. The steering itself is validated on the host (`test/test_geometry.py`) for arbitrary
curve/view/slope.

The alignment gotcha: the cores read the baked tables with `be16`/`be32` (word/long moves), which
fault on an odd address on the 68000, so the fixture arrays and the BSS scratch are `aligned(2)`.

## Scope

Only remaster's own rendering is drawn, over a **blank screen** — no captured game frame. The HUD
demo (`HUD.PRG`) is HUD-only; the road demo (`DEMO.PRG`) adds the road surface and live steering.
As more of the pipeline is ported (road scroll, objects), this harness extends toward whole frames.
