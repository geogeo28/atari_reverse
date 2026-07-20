# Remaster status — BuggyBoy

A free, optimized, human-readable re-implementation, validated **pixel-identical** to the verified
`recreate/` cores per frame (see [`README.md`](README.md)). This tracks per-subsystem progress; a
subsystem is "green" when its framebuffer matches `recreate/`'s over the equivalence harness.

## Phase A — render pipeline (current)

Validate each render stage against a captured `recreate/` snapshot (adapter → remaster structs →
framebuffer → diff). Order follows the in-race draw order.

| Subsystem          | recreate reference        | remaster status | Equivalence |
|--------------------|---------------------------|-----------------|-------------|
| reference capture  | render pipeline @ `bench_frame` staging | ✅ deterministic | `test/capture_ref.py` — 4 golden frames, byte-stable |
| adapter            | flat image → structs      | ✅ HUD scalars + assets | `test/adapter.py` — `HudState`/`HudAssets`/`Framebuffer` |
| equivalence driver | per-subsystem framebuffer diff | ✅ footprint coverage + no-wrong-pixel | `test/equiv.py` |
| glyph blitter (`text_body`) | `g_draw_hud_bar` / `g_draw_hud_gauge0` | ✅ verified | `test/test_text.py` — 960 fuzz cases, **byte-exact** (whole framebuffer) |
| `draw_hud`         | `g_draw_hud`              | ✅ all 8 phases ported | `test/test_hud.py` — **100% footprint, 0 wrong pixels** across HUD configs, all 8 dsp variants, 6b blink phases, and the crash-fx drain paths |
| on-target (Hatari) | `g_draw_hud` frame        | ✅ byte-identical on 68000 | `render/atari/` — HUD-only PRG dump MATCHes recreate's g_draw_hud (blank screen) |
| on-target road+HUD | build_geometry+render_road+blit_road_scroll+draw_hud | ✅ byte-identical on 68000 + interactive | `render/atari/DEMO.PRG` — first frame MATCHes recreate's ported pipeline; arrow keys steer live |
| `render_road`      | `g_render_road`           | ✅ all 7 bands ported | `test/test_road.py` — **whole-framebuffer byte-exact** across legs 0–4 / warmup depths |
| `build_road_geometry` | `g_build_road_geometry` | ✅ all 5 stages ported | `test/test_geometry.py` — control table + rendered road byte-exact under arbitrary steering (curve/view/near-slope) |
| `blit_road_scroll` | `g_blit_road_scroll`      | ✅ ported | `test/test_scroll.py` — whole-framebuffer + scroll-state byte-exact under arbitrary scroll (speed/pos/wrap) |
| `draw_game_objects`| `g_draw_game_objects`     | ⬜ not started   | — |

### `draw_hud` phase ledger

recreate only exports the whole `g_draw_hud`, so equivalence is measured as **footprint coverage**
(fraction of the bytes `draw_hud` changes that the candidate reproduces) under a **no-wrong-pixel**
invariant (every byte the candidate paints matches recreate). Coverage → 100% as phases land.

| Phase | What | Status | Needs |
|-------|------|--------|-------|
| 1–2 | speed/time digit strings | ✅ | feed phase 7's string (the text buffers overlap the gauge string) |
| 3 | dashboard-variant sprite | ✅ | `dsp_table` record + `buf_c` sprite (masked word/long blit) |
| 4 | flag-sequence bars | ✅ | scalar only |
| 5 | colour-tinted bars | ✅ | `color_pairs` + mask/ink + cidx tables |
| 6a | fuel/tacho gauge | ✅ | fuel-mask table |
| 6b | blinking small gauge | ✅ | glyph blitter + `small_gauge_str` (runs only when `crash_lap` == 0) |
| 7 | main gauge cluster + dashboard | ✅ | glyph blitter + dashboard masked-blit |
| 8 | crash fx | ✅ | num blitter + score_add (BCD) + drain/rollover over the shared HUD-text buffer |

## Phase B — gameplay (later)

| Subsystem     | recreate reference | remaster status | Equivalence |
|---------------|--------------------|-----------------|-------------|
| course advance (road geometry) | `g_game_update` §12 | ✅ segment scroll + record pull ported | `test/test_course.py` — seg_data / row_ctr / read_pos byte-exact over 40-frame drives, legs 0/1/2/4 |
| `game_update` (rest) | `g_game_update` | ⬜ objects/events/collision/score not started | — |

## Perf

`tools/bench.py` measures each render core's per-frame cost on the cycle-accurate Musashi 68000 —
remaster (native structs, via the `bench_*` wrappers) vs recreate's recon (flat image) — on the same
staged leg-1 frame. Build first: `bash render/atari/bench_build.sh`.

Current (8 MHz ST, 160000-cycle frame budget), remaster **0.83× the recon** overall:

| stage | remaster ms | recon ms | rm/rec |
|-------|-------------|----------|--------|
| build_road_geometry | 3.87 | 3.91 | 0.99× |
| render_road | 49.84 | 54.86 | **0.91×** |
| blit_road_scroll | **19.33** | 33.55 | **0.58×** |
| draw_hud | 18.53 | 18.27 | 1.01× |

`render_road` also beats the byte-exact **machine model** (`g_render_road_machine`, 56.18 ms → 0.89×):
GCC optimises the idiomatic/native-pointer C better than the hand-threaded register/goto transcription.

**Optimization — `blit_road_scroll`** (was the worst C-vs-asm ratio, 2.84× the original): recreate
rotates every plane-word every frame (1600 variable-count `rol`s). `rm_scroll_prebuild` instead builds,
once per leg, the 16 fine-shift pre-rotated copies of the playfield; the per-frame blit is then a plain
column copy from copy[`shift`] — **33.55 → 19.33 ms** (0.58× recon, ~1.64× the original), byte-identical
to the verified core. Copy 0 is the raw playfield, which the edge seam reuses.

Key gotcha: the cores **must be built `-O2`, not `-Os`** — at `-Os` GCC won't inline the hot blit
primitives (`rr_copy_long`/`rr_fill_pair`), and the per-column call overhead ~doubles the render cost
(measured 1.94× the recon before the flag was fixed). The on-target builds now use `-O2`.

The full pipeline is now ~92 ms/frame. Next target is `render_road` (49.8 ms) — a precomputed road
display list would cut the per-scanline dispatch. See [[buggyboy-perf-fast-track]].
