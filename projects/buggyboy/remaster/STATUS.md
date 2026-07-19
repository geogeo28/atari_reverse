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
| adapter            | flat image → structs      | ⬜ not started   | — |
| `render_road`      | `g_render_road`           | ⬜ not started   | — |
| `blit_road_scroll` | `g_blit_road_scroll`      | ⬜ not started   | — |
| `draw_game_objects`| `g_draw_game_objects`     | ⬜ not started   | — |
| `draw_hud`         | `g_draw_hud`              | ⬜ not started   | — |

## Phase B — gameplay (later)

| Subsystem     | recreate reference | remaster status | Equivalence |
|---------------|--------------------|-----------------|-------------|
| `game_update` | `g_game_update`    | ⬜ not started   | — |

## Perf target

Baseline gap to close (from `recreate/`'s perf analysis): recon ~2.1× the original on-target, worst
on the road copy (`blit_road_scroll` ~2.8×, the per-word variable-count `rol`). `tools/bench.py`
measures remaster vs both original and recon per frame.
