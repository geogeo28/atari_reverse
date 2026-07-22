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
| on-target full frame | build_geometry+render_road+blit_road_scroll+draw_game_objects+draw_hud | ✅ byte-identical on 68000 + **playable** | `render/atari/DEMO.PRG` — first frame MATCHes recreate's whole ported pipeline (road, ground, foreground sprite, roadside object list, scaled object, buggy, HUD); the loop is then driven by `rm_player_update` with held-key input (own IKBD handler) |
| `render_road`      | `g_render_road`           | ✅ all 7 bands ported | `test/test_road.py` — **whole-framebuffer byte-exact** across legs 0–4 / warmup depths |
| `build_road_geometry` | `g_build_road_geometry` | ✅ all 5 stages ported | `test/test_geometry.py` — control table + rendered road byte-exact under arbitrary steering (curve/view/near-slope) |
| `blit_road_scroll` | `g_blit_road_scroll`      | ✅ ported | `test/test_scroll.py` — whole-framebuffer + scroll-state byte-exact under arbitrary scroll (speed/pos/wrap) |
| buggy/fg sprites (`draw_fg_sprite`, `draw_buggy`) | `g_draw_fg_sprite` / `g_draw_buggy` | ✅ ported | `test/test_sprite.py` — whole-framebuffer byte-exact across body/leaning frames, spin aborts, lean overlay, lower body |
| ground / horizon (`draw_ground`) | `g_draw_ground` | ✅ ported | `test/test_ground.py` — whole-framebuffer byte-exact across gradient (band-clamp buckets) + solid (lit/near) markers |
| scaled object (`draw_object`) | `g_draw_object` | ✅ ported | `test/test_object.py` — whole-framebuffer byte-exact across LEFT/RIGHT/FAR/SCALE2 flag combos, all shade signs, pre-scan clear |
| fine-x blit engines (`blit_objshift`, `blit_objshift2`, objsprite) | `g_blit_objshift` / `_w2` / `g_blit_objshift2` / `g_objsprite_t*` | ✅ ported | `test/test_blit_engines.py` — byte-exact fuzz across every fine-x, dispatch case (clip/edge/base/wide), colours, strides, all width families |
| object-list dispatcher (`draw_object_list` + obj_dispatch + handlers) | `g_draw_object_list` | ✅ ported | `test/test_object_list_rm.py` — whole-framebuffer byte-exact across the real per-frame passes, legs 0–4 |
| `draw_game_objects` (prefix + orchestrator) | `g_draw_game_objects` / `g_draw_game_objects_prefix` | ✅ ported | `test/test_game_objects_rm.py` — whole-frame composite byte-exact; `test/test_gobj_prefix.py` — prefix state byte-exact (marker/anim/bonus) |
| asset loading (`rm_assets_unpack`) | `g_unpack_graphics` | ✅ ported | `test/test_assets.py` — the **whole 0x5ee08 arena** byte-identical, loaded from the unmodified `COURSES.DAT` + `GRAPHICS.GRA`; `test/test_assets_bounds.py` — malformed/truncated input refused with the arena intact |


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

### Assets

The remaster reads the game's own `COURSES.DAT` and `GRAPHICS.GRA`, unmodified, at boot —
`src/assets.c` ports the RLE decode, screen de-interleave, compaction and the two sprite pre-shift
table builds into one arena (`include/assets.h`). The arena's internal offsets are the data files'
own address space, not a choice: a course record's sprite pointer is a byte offset into the graphics
region. What the loader does *not* own is the original program's data segment (fonts, colour pairs,
perspective/edge tables, the object jump table) — those are program constants, not file content, and
are still supplied by the adapter/fixture.

`DEMO.PRG` loads both files over GEMDOS at boot, so **~413 KB of baked asset arrays are gone** from
the demo (`demo_fixture.h`: 28530 → 2702 lines; the .PRG's text is 68 KB) and the road texture, the
scroll playfield, the course stream, the object record arena and every sprite are read from the real
files. The disk ships `DEMO.PRG` + the two data files.

One honest consequence: the demo's golden frame is now rendered from a *freshly loaded* arena
(`gen_demo_fixture.staged_image` swaps one in), because that is what the demo has at boot. Of the
arena's 388616 bytes, 347 differ after 60 staged frames — all in the graphics region — and exactly
one of them reaches the framebuffer: the 4th byte of the dashboard graphic, in which the running
game clears a bit. That bit returns on its own once the system that writes it is ported.

## Phase B — gameplay (later)

| Subsystem     | recreate reference | remaster status | Equivalence |
|---------------|--------------------|-----------------|-------------|
| course advance (road geometry) | `g_game_update` §12 | ✅ segment scroll + record pull ported | `test/test_course.py` — seg_data / row_ctr / read_pos byte-exact over 40-frame drives, legs 0/1/2/4 |
| course object/marker ring | `g_game_update` §12 (ring shuffle + record unpack) | ✅ ported | `test/test_course_ring.py` — bands 0–11 byte-exact vs recreate over free-running 600-frame drives × 3 scripts × legs 0–4 (bands 12/13: marker only — see below), plus the control table the marker column feeds, plus directed drives for the two branches a leg start cannot reach |
| player physics (`rm_player_update`) | `g_game_update` §3,4,5,7,8,9,10 | ✅ ported | `test/test_player.py` — every physics scalar identical to recreate frame-for-frame over 8 scripted 240-frame drives × legs 0/1/4 (throttle/brake/slalom/both locks/recentre/fire/time-out) |
| crash / auto-steer script | `g_game_update` §6 (+ the §5/§7/§9/§10 crash branches) | ✅ ported | `test/test_leg_drive.py` — free-running 600-frame drives × 4 scripts × legs 0/1/4, every crash played out and handed the controls back under strict comparison (up to 204 crash frames / 20 handoffs per drive) |
| `game_update` (rest) | `g_game_update` §1,2,12-tail | ⬜ sound, collision probe, fx block / event dispatch, score not started | — |

**What the player-physics slice covers** (see `include/game.h` for the state model): the engine
rpm→speed model with its rev limiter, the road-scroll rate and the view advance whose wrap times the
course, the wheel position → body lean → road-curvature integrator, the road-edge clamp plus the
off-road push, and — since §6 landed — the crash / auto-steer script that takes the controls away
while a canned crash replays out of `crash_anim_tbl` and then hands them back.

The precondition is now *no event pending*. What is still missing is the system that **decides** to
crash you: §12's collision probe, the fx block rebuilt from `obj_flags`, and the horizon-event
dispatch (which also delivers the checkpoint and finish-line events that would end a leg). Three
consequences, all measured rather than assumed:

- A leg drive still cannot *finish* a leg — nothing signals the end of one.
- `test/test_leg_drive.py` now hands over exactly **one** thing and counts it: the single frame where
  recreate arms a crash (detected as an event-owned global going 0 → nonzero). The road control table
  used to be handed over too; since the ring landed it is a compared **result**. Everything else —
  including every frame of every crash playout — is compared strictly, free-running, never re-seeded.
- Two exclusions remain, both bounded and counted rather than silent: bands 12/13's type codes are
  exempt from the ring comparison (the dispatch clears bytes that land there — see
  `equiv.RING_EVENT_OWNED_BANDS` for the derived footprint, which is *not* `obj_flags`), and leg 2's
  slalom drive is skipped because recreate's rpm-penalty handler arms nothing, so the 0 → nonzero
  detector cannot see it.

**Ported faithfully but not pinned:** `marker_unpack`'s "both shoulders" fixup
(`MARKER_KIND_SIDES`) fires for **0 of the 5120** course records across all five legs, so this game's
data cannot exercise it at all. It is transcribed from the disassembly and left honestly unpinned
rather than pinned against a fabricated record; a mutation to it survives the whole suite.

## Perf

`tools/bench.py` measures each render core's per-frame cost on the cycle-accurate Musashi 68000 —
remaster (native structs, via the `bench_*` wrappers) vs recreate's recon (flat image) — on the same
staged leg-1 frame. Build first: `bash render/atari/bench_build.sh`.

Current (8 MHz ST, 160000-cycle frame budget), remaster **0.76× the recon** overall:

| stage | remaster ms | recon ms | rm/rec |
|-------|-------------|----------|--------|
| build_road_geometry | 3.87 | 3.91 | 0.99× |
| render_road | 49.84 | 54.86 | **0.91×** |
| blit_road_scroll | **11.98** | 33.55 | **0.36×** |
| draw_hud | 18.53 | 18.27 | 1.01× |

`render_road` also beats the byte-exact **machine model** (`g_render_road_machine`, 56.18 ms → 0.89×):
GCC optimises the idiomatic/native-pointer C better than the hand-threaded register/goto transcription.

**Optimization — `blit_road_scroll`** (was the worst C-vs-asm ratio, 2.84× the original → now ~1.02×,
matching the hand-asm): two changes, both byte-identical to the verified core (`test/test_scroll.py`,
all 5 legs):
1. *Pre-rotated playfield* — recreate rotates every plane-word every frame (1600 variable-count
   `rol`s). `rm_scroll_prebuild` builds the 16 fine-shift pre-rotated copies once per leg; the blit
   then plain-copies contiguous columns from copy[`shift`] (33.55 → 19.33 ms). Copy 0 is the raw
   playfield, which the edge seam reuses.
2. *Fast top fill* — the 13 KB constant fill above the band was ~78% of the remaining cost; unrolling
   8× + laundering the constant into a register (so stores are `move.l dN,(a0)`, not the 20-cyc
   `move.l #imm,(a0)`) took it 19.33 → **11.98 ms**.

Key gotcha: the cores **must be built `-O2`, not `-Os`** — at `-Os` GCC won't inline the hot blit
primitives (`rr_copy_long`/`rr_fill_pair`), and the per-column call overhead ~doubles the render cost
(measured 1.94× the recon before the flag was fixed). The on-target builds now use `-O2`.

The full pipeline is now ~84 ms/frame. Next target is `render_road` (49.8 ms) — a precomputed road
display list would cut the per-scanline dispatch. See [[buggyboy-perf-fast-track]].
