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
| `draw_hud`         | `g_draw_hud`              | 🟡 phases 4/5/6a ported | `test/test_hud.py` — 5 cfgs, **0 wrong pixels**, ~18–48% footprint coverage |
| `render_road`      | `g_render_road`           | ⬜ not started   | — |
| `blit_road_scroll` | `g_blit_road_scroll`      | ⬜ not started   | — |
| `draw_game_objects`| `g_draw_game_objects`     | ⬜ not started   | — |

### `draw_hud` phase ledger

recreate only exports the whole `g_draw_hud`, so equivalence is measured as **footprint coverage**
(fraction of the bytes `draw_hud` changes that the candidate reproduces) under a **no-wrong-pixel**
invariant (every byte the candidate paints matches recreate). Coverage → 100% as phases land.

| Phase | What | Status | Needs |
|-------|------|--------|-------|
| 1–2 | speed/time digit strings | n/a for framebuffer | writes text buffers, not the screen (drawn by phase 7) |
| 3 | dashboard-variant sprite | ⬜ | `buf_c` sprite data |
| 4 | flag-sequence bars | ✅ | scalar only |
| 5 | colour-tinted bars | ✅ | `color_pairs` + mask/ink + cidx tables |
| 6a | fuel/tacho gauge | ✅ | fuel-mask table |
| 6b | blinking small gauge | ⬜ | glyph helper ✅ (`rm_glyph_run`) — ready to wire |
| 7 | main gauge cluster + dashboard | ⬜ | glyph helper ✅; still needs cursor chaining + `draw_dashboard` + `buf_c` |
| 8 | crash fx | ⬜ | `draw_num` + `add_score` + bars |

## Phase B — gameplay (later)

| Subsystem     | recreate reference | remaster status | Equivalence |
|---------------|--------------------|-----------------|-------------|
| `game_update` | `g_game_update`    | ⬜ not started   | — |

## Perf target

Baseline gap to close (from `recreate/`'s perf analysis): recon ~2.1× the original on-target, worst
on the road copy (`blit_road_scroll` ~2.8×, the per-word variable-count `rol`). `tools/bench.py`
measures remaster vs both original and recon per frame.
