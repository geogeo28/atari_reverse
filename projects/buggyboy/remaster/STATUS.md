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
| crash / auto-steer script | `g_game_update` §6 (+ the §5/§7/§9/§10 crash branches) | ✅ ported + wired | `test/test_leg_drive.py` — free-running 600-frame drives × 4 scripts × legs 0/1/4; the candidate now runs the real event engine, so it ARMS ITS OWN crashes (no handover — see below) and every crash plays out and hands the controls back under strict comparison (up to 213 crash frames / 20 handoffs per drive) |
| course-event engine (`rm_event_dispatch` / `rm_course_events` / `rm_course_probe`) | `g_game_update` §12 tail + the event jump table | ✅ ported (`src/events.c`) + wired | `test/test_events.py` — the jump table pinned against the image's own table at 0x11aa2; per-handler dispatch fuzzed over every idx × gate flags × collision_lock × curve sign; the composite §G/§H/§I tail vs `g_game_update_fx_and_events` over legs 0–4 × warmups (incl. the graphics arena); directed §I checkpoint/leg-end/leg-0-dashboard/collision/banner cases; the collision probe vs `g_probe_collision`; directed fx-slot-mapping + run-fill pins. **Wired** into `rm_player_update`'s §6 event path and the leg drive's wrap-frame tail (`test/test_leg_drive.py`), and into the demo (on-target autodrive trace) |
| `game_update` (integration + sound) | `g_game_update` §1,2 + wiring | 🟨 events core WIRED end-to-end; the leg/game-flow CORE now landed (slice 1, host-side): §1's marker gate + §2's input capture (`rm_player_update`), and the crash / end-of-race tally — HUD phase 8's timer decay + `draw_crash_fx`'s STATE side — as `rm_crash_fx_update` (`src/events.c`). A leg now **ENDS**: the tally arms `abort_flag` (0xffff game-over / 0x33 bonus-exhausted, decaying negative), which the frame loop reads as the leg end. Differential-pinned by `test/test_crash_fx.py` (every branch) and organically by `test/test_leg_drive.py`'s idle-to-time-out drives. **Slice 2 wired the tally on-target**: `demo_main.c` calls `rm_crash_fx_update` every frame at the per-frame tail (before `apply_player`, whose `EventState`→`HudState` copy the drawn HUD reads), and on `abort_flag < 0` restarts the current leg from its boot state — a documented stand-in for the unported intermission / `init_leg` handoff. Proven on the 68000 by the idle leg-end autodrive trace (arm 0x5b → negative → abort → restart). What remains: the sound path (INITTUNE/INITFX/TURNOFF, the VBL vector); the record-driven mode-2/4/6 palette / screen-offset events (course_advance's tail); and the real intermission / `init_leg` flow a finished leg hands off to — see below | — |

**What the player-physics slice covers** (see `include/game.h` for the state model): the engine
rpm→speed model with its rev limiter, the road-scroll rate and the view advance whose wrap times the
course, the wheel position → body lean → road-curvature integrator, the road-edge clamp plus the
off-road push, and — since §6 landed — the crash / auto-steer script that takes the controls away
while a canned crash replays out of `crash_anim_tbl` and then hands them back.

The precondition on `rm_player_update` is gone: the course-event engine that **decides** to crash you
— §12's collision probe, the fx block rebuilt from `obj_flags`, and the horizon-event dispatch — is
now wired in end-to-end (slice 2). The §6 event path dispatches a pending event through it (a
bonus-display record even rebuilds the control table mid-dispatch), and the leg drive / demo run the
probe + fx/horizon tail on every view-wrap. Consequences, all measured rather than assumed:

- **The leg-drive handover is gone (handoffs of the arming decision = 0).** The candidate runs the
  real event engine, so it arms its own crashes and delivers its own checkpoint / finish / bonus
  events; a divergence (the reference arming something the candidate did not, or vice versa) now fails
  the drive loudly as a strict mismatch in the event-owned PlayerState fields rather than being
  re-seeded away. Every frame is compared, free-running, never re-seeded.
- **All 14 ring bands are now compared whole** — the old bands-12/13 exemption is closed, because the
  horizon dispatch pokes those bands' type codes on the candidate exactly as on the reference. The
  drive also now compares the event-owned surfaces per frame: EventState (crash_bars / crash_active /
  crash_lap / gauge_blink[_on] / ckpt_scroll / spin_state, the dashboard marker, the flag-bit cursor),
  the GobjPrefixState bonus / flag / marker-decay counters, and the score digits in the shared
  HUD-text window. (The leg-2 slalom skip `test_course_ring.py` used to carry — the case the old
  0 → nonzero arming detector could not see, since recreate's rpm-penalty handler arms nothing — is
  now removed: the horizon-event dispatch is ported and the case runs with 0 mismatches.)
- **A leg now ENDS (slice 1, host-side).** The leg/game-flow CORE is ported: `g_game_update` §1's
  marker gate (clearing the marker the crash script raised, closing the raise/consume loop) and §2's
  input capture sit at the head of `rm_player_update`; the crash / end-of-race tally — HUD phase 8's
  `hud_crash_timer` decay plus `draw_crash_fx`'s STATE side (`crash_frame++`, the bonus drain into the
  score, the `abort_flag` countdown) — is `rm_crash_fx_update` in `src/events.c`. `EventState` gained
  `crash_frame` / `abort_flag`. `hud.c`'s `hud_crash_fx` still DRAWS the tally off a throwaway HUD-text
  copy (pixel-verified by `test_hud`); this UPDATE owns the persistent mutations so a self-running leg
  advances. The two leg-end paths both fire and count negative under strict per-frame comparison: the
  free-running 600-frame drives still reach no checkpoint (`checkpoints` = 0), but a drive that idles
  until the bonus clock times out now arms `abort_flag` and ends the leg, matching recreate frame for
  frame (`test/test_leg_drive.py::test_leg_ends_on_timeout` / `test_leg_ends_via_bonus_tally`).
  **Slice 2 wired that on-target**: `demo_main.c`'s frame loop runs `rm_crash_fx_update` every frame at
  the per-frame tail (before `apply_player`, so the drawn HUD sees this frame's tally through the six
  `EventState`→`HudState` view fields), and on `abort_flag < 0` restarts the current leg from its boot
  state — the same reset `R` uses, re-seeding every persistent field (`abort_flag`, `crash_frame`,
  `hud_crash_timer`, `time_left`, `crash_lap`, the HUD-text score/rollover region, `marker_pending`).
  That leg restart is a documented stand-in for the still-unported intermission / `init_leg` flow the
  frame loop hands off to once `abort_flag` goes negative (`game_over_flag++` before the intermission).
  Verified on the 68000 by the idle leg-end autodrive trace (`DEMO_AUTODRIVE`/`DEMO_TRACE` with
  `AUTODRIVE_BASE_INPUT=0` + `DEMO_TIME_LEFT`): `hud_crash_timer` arms 0x5b, decays negative, `abort_flag`
  arms 0xffff, and the leg restarts with every persistent field reset — the demo survives its first leg
  end with no hang or corruption. The trace record grew a 9th word (`abort_flag`) for it.

- **`rev_reload` (§1's engine-idle poke) is invisible and skipped, verified not assumed.** §1 writes
  `rev_reload = 8` (0x18d12) when the buggy is stopped; it aliases `lean_frame`, which no compared
  surface reads, so it is omitted exactly as §6/§7 omit the same write. The idle time-out drives run at
  `speed == 0` — the very condition that triggers the reference's `rev_reload` write every frame — and
  pass with zero mismatches, so the skip is demonstrably invisible rather than merely presumed.

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
- **Do not collapse the wrap-frame's double `rm_build_road_geometry`.** On a view-wrap the demo
  builds twice: once before `rm_course_events` (so `horizon_row` is fresh for the event tail), then
  again inside `draw_frame` (off the ring bands the tail pokes). Both are faithful — the original's
  own `g_draw_frame` (recreate gameplay.c:268) likewise rebuilds after the event pokes — so a future
  perf pass must not "dedupe" it: dropping either build renders stale-horizon / pre-poke geometry.
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
