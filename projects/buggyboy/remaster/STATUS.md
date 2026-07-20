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
| on-target road+HUD | build_geometry+render_road+draw_hud | ✅ byte-identical on 68000 + interactive | `render/atari/DEMO.PRG` — first frame MATCHes recreate's ported pipeline; arrow keys steer live |
| `render_road`      | `g_render_road`           | ✅ all 7 bands ported | `test/test_road.py` — **whole-framebuffer byte-exact** across legs 0–4 / warmup depths |
| `build_road_geometry` | `g_build_road_geometry` | ✅ all 5 stages ported | `test/test_geometry.py` — control table + rendered road byte-exact under arbitrary steering (curve/view/near-slope) |
| `blit_road_scroll` | `g_blit_road_scroll`      | ⬜ not started   | — |
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
| `game_update` | `g_game_update`    | ⬜ not started   | — |

## Perf target

Baseline gap to close (from `recreate/`'s perf analysis): recon ~2.1× the original on-target, worst
on the road copy (`blit_road_scroll` ~2.8×, the per-word variable-count `rol`). `tools/bench.py`
measures remaster vs both original and recon per frame.
