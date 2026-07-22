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
| on-target full frame | build_geometry+render_road+blit_road_scroll+draw_game_objects+draw_hud | ✅ byte-identical on 68000 + **playable** | `render/atari/DEMO.PRG` — the leg-0 start frame MATCHes recreate's whole ported pipeline (road, ground, foreground sprite, roadside object list incl. the start gate, scaled object, buggy, HUD); the loop is then driven by `rm_player_update` with held-key input (own IKBD handler); `test/test_demo_fixture.py` pins the fixture's buf_a window to the dispatcher's type-record reach |
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
| ring consumer views (dispatcher flag streams, sprite count, ground markers, sprite gates) | the original's aliases onto the ring's row grid | ✅ unified onto the live ring | `test/test_ring_consumers.py` — each `src/course.c` helper (incl. the full serialized ST mirror, byte-for-byte) pinned to the raw image bytes at the aliased addresses, 5 legs × 3 warmups, with real variety (sprite counts 0/11, a live gate-suppress case) |
| player physics (`rm_player_update`) | `g_game_update` §3,4,5,7,8,9,10 | ✅ ported | `test/test_player.py` — every physics scalar identical to recreate frame-for-frame over 8 scripted 240-frame drives × legs 0/1/4 (throttle/brake/slalom/both locks/recentre/fire/time-out) |
| crash / auto-steer script | `g_game_update` §6 (+ the §5/§7/§9/§10 crash branches) | ✅ ported | `test/test_leg_drive.py` — free-running 600-frame drives × 4 scripts × legs 0/1/4, every crash played out and handed the controls back under strict comparison (up to 204 crash frames / 20 handoffs per drive) |
| course-event engine (`rm_event_dispatch` / `rm_course_events` / `rm_course_probe`) | `g_game_update` §12 tail + the event jump table | ✅ ported (`src/events.c`) | `test/test_events.py` — the jump table pinned against the image's own table at 0x11aa2; per-handler dispatch fuzzed over every idx × gate flags × collision_lock × curve sign; the composite §G/§H/§I tail vs `g_game_update_fx_and_events` over legs 0–4 × warmups (incl. the graphics arena); directed §I checkpoint/leg-end/leg-0-dashboard/collision/banner cases; the collision probe vs `g_probe_collision`; directed fx-slot-mapping + run-fill pins added after mutation-testing |
| `game_update` (integration + sound) | `g_game_update` §1,2 + wiring | ⬜ the events core is not yet wired into `rm_player_update`'s §6 event path, the leg-drive handover isn't removed, the demo doesn't call it, and the sound path (INITTUNE/INITFX/TURNOFF, the VBL vector) is still unported | — |

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

In the event engine (`src/events.c`), the **single endpoint words** of the §G 0x3e run-fill (`fx+0x1a`
and `fx+0x2e`) are ported from the disassembly but not differentially observable. The fx block is
local scratch whose only output is which event §H dispatches, and the fill writes the uniform value
0x3e (→ idx 62, `disp_finish` — an idempotent record write). §H reads `fx[horizon_row+1]` and
`fx[horizon_row+3]`, and `horizon_row` is even in `[0, 0x2c]`, so each endpoint word's sole dispatch
route is shared with an adjacent filled word that fires the same idempotent record — dropping one
endpoint alone changes nothing. `test_fx_run_fills` pins the fill as a whole (disabling it, or shrinking
it by ≥2 words, is caught, mutation-verified) and the 0x3d fill's extent fully (its last word is
followed by unfilled space, so it dispatches alone); the 0x3e fill's two edge words are left honestly
unpinned. Mutation-testing this slice's coverage also drove three directed tests that plugged real
holes a warm-frame composite left dead: the fx-block slot→position map, the probe erase's y-offset
(caught only with the marker on a set track cell), and the run-fills (see the tests' rationale
comments).

## Perf

`tools/bench.py` measures the demo's WHOLE frame per stage on the cycle-accurate Musashi 68000 —
remaster (native structs, via the `bench_*` wrappers, staged exactly as demo_main.c's frame) vs
recreate's recon (flat image) where an image-arg-only recon entry has the same scope — on the same
staged leg-1 frame. Build first: `bash render/atari/bench_build.sh`. `tools/profile.py <bench_sym>`
breaks any stage down to cycles-per-function (and per-PC with `--lines`) via the oracle's
cycle histogram.

Current (8 MHz ST, 160000-cycle 50 Hz frame budget) — the demo frame is **203 ms ≈ 4.9 fps** on the
staged frame. Caveat before reading the object rows: the staged frame is the demo's BOOT frame — a
leg start, with the start gate spanning the road — which is close to the object tree's worst case
(see the frame-cost distribution below the table):

| stage | remaster ms | recon ms | rm/rec | notes |
|-------|-------------|----------|--------|-------|
| player_update + course + views + prefix | 2.01 | — | | scalar state, noise |
| build_road_geometry | 3.87 | 3.91 | 0.99× | |
| render_road | 50.68 | 55.47 | 0.91× | 67% in the per-scanline core, 33% in bands B/D |
| blit_road_scroll | 11.98 | 33.55 | 0.36× | pre-rotated copies + unrolled fill |
| draw_ground | 1.16 | — | | |
| draw_fg_sprite | 2.40 | 2.39 | 1.00× | |
| **objlist pass 1 (sprites)** | **51.50** | — | | 87% inside `rm_blit_objshift` |
| draw_object | 0.89 | — | | |
| objlist pass 2 | 0.09 | — | | empty on this frame |
| **objlist fixed pass** | **55.99** | — | | 97% inside `rm_blit_objshift2` |
| draw_buggy | 5.16 | 5.22 | 0.99× | |
| draw_hud | 17.44 | 17.20 | 1.01× | 10.6 in the phases (dashboard masked blit), 6.0 in glyph_run |
| **TOTAL (frame)** | **203.2** | | | recreate-parity would be ~240 ms — the original is this slow on this scene, and remaster now beats it on this frame (the scroll-blit win) |

Whole-tree check: `object_tree` (prefix→buggy, recreate's `g_draw_game_objects` scope) is 117.2 ms
vs the recon's 130.3 ms (**0.90×**). `render_road` also beats the byte-exact **machine model**
(`g_render_road_machine`, 56.65 ms → 0.89×): GCC optimises the idiomatic/native-pointer C better
than the hand-threaded register/goto transcription.

**Frame-cost distribution** (recon `g_draw_frame` over legs 0/1/4 × warmups 0..600 step 30, 63
frames): median **180 ms (5.6 fps)**, min 138 ms, p90 221 ms, max 315 ms. A median frame's object
tree is ~46 ms — the staged bench frame's 117 ms is the start gate, near the tail of the
distribution. Use the median for planning and the gate frame as the worst-case check.

The headline findings (2026-07-22 profile):
- **The demo's per-frame `memset` was ~a third of the frame and redundant — now removed (free 96 ms).**
  recreate's own pipeline repaints every framebuffer byte (its captured frames are deterministic with
  no clear), and the shim memset was a byte loop besides. The demo now clears both screen buffers once
  at boot and never again. Verified: `run_demo.py` still reports MATCH on the frame-0 golden, and the
  autodrive frame-2 and frame-61 dumps are byte-identical to a per-frame-clear build (proving the
  clear was redundant on both buffer parities, not just frame 0).
- **The two fine-x sprite blitters dominate the object tree** — `rm_blit_objshift`/
  `rm_blit_objshift2` are 99 ms of the gate frame's 117 ms tree (87%/97% of their passes). Their
  cell helpers mutate `col0/col1/sp` through pointers, so GCC keeps the loop state in memory: the
  profile shows ~16 k cycles of pure `movel %sp@(x),%sp@(y)` spill shuffling plus memory-RMW cursor
  updates per pass. Value-passing restructure (same bytes out, pinned by
  `test/test_blit_engines.py`) is the next win.
- **Where the fps can land (8 MHz ST, median frame ~180 ms recreate-parity):** dropping the memset
  puts the remaster demo at ~155 ms ≈ 6.5 fps median. The full plan (blitters, road display list,
  HUD static/dynamic split, scroll fill tracking — PORTING.md "Perf plan") projects a median around
  **60–75 ms ≈ 13–17 fps**, with gate/tunnel frames at ~8–10 fps. 20 fps median is the stretch
  ceiling if every item lands (likely needing hand-asm blitter cores); 30 fps is out of reach on a
  stock ST while staying pixel-faithful.

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

(The "~84 ms/frame" this section used to claim was the sum of the four stages benched at the time,
not the frame: the 2026-07-22 full-frame bench above put the real figure at 203 ms — 299 ms before
the per-frame clear was dropped.)
