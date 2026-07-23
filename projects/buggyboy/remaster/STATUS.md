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
| on-target full frame | build_geometry+render_road+blit_road_scroll+draw_game_objects+draw_hud | ✅ byte-identical on 68000 + **playable** | `render/atari/BUGGYBOY.PRG` is the playable game (boots the leg select, no sound). The golden-harness variant (`GOLDEN.PRG`, `-DGOLDEN_BOOT_LEG=0`, built by `run_golden.py`) starts leg 0 directly and its start frame MATCHes recreate's whole ported pipeline (road, ground, foreground sprite, roadside object list incl. the start gate, scaled object, buggy, HUD); the loop is then driven by `rm_player_update` with held-key input (own IKBD handler); `test/test_game_fixture.py` pins the fixture's buf_a window to the dispatcher's type-record reach |
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

`BUGGYBOY.PRG` loads both files over GEMDOS at boot, so **~413 KB of baked asset arrays are gone** from
the game (`game_fixture.h`: 28530 → ~2613 lines, after `rm_init_leg` dropped the baked leg-start
scalars; the .PRG's text is 68 KB) and the road texture, the
scroll playfield, the course stream, the object record arena and every sprite are read from the real
files. The disk ships `BUGGYBOY.PRG` + the two data files.

One honest consequence: the golden frame is now rendered from a *freshly loaded* arena
(`gen_game_fixture.staged_image` swaps one in), because that is what the game has at boot. Of the
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
| course-event engine (`rm_event_dispatch` / `rm_course_events` / `rm_course_probe`) | `g_game_update` §12 tail + the event jump table | ✅ ported (`src/events.c`) + wired | `test/test_events.py` — the jump table pinned against the image's own table at 0x11aa2; per-handler dispatch fuzzed over every idx × gate flags × collision_lock × curve sign; the composite §G/§H/§I tail vs `g_game_update_fx_and_events` over legs 0–4 × warmups (incl. the graphics arena); directed §I checkpoint/leg-end/leg-0-dashboard/collision/banner cases; the collision probe vs `g_probe_collision`; directed fx-slot-mapping + run-fill pins. **Wired** into `rm_player_update`'s §6 event path and the leg drive's wrap-frame tail (`test/test_leg_drive.py`), and into the game (on-target autodrive trace) |
| leg start (`rm_init_leg`) | `g_init_leg` @0x104b8 | ✅ ported + wired | `test/test_init_leg.py` — differential vs `g_init_leg` over ALL legs 0-4, FRESH (from scratch) + RE-INIT (warmed, non-zero preserved fields), every owned surface (the physics/course/event/pose/scroll scalar block, the ring band-by-band + its ST mirror, the buggy pose, the HUD-text region bytes, `obj_shade`, `screen_offset`), mutation-verified; plus `test/test_leg_drive.py::test_leg_drive_from_native_init` — a free-running drive whose candidate START comes from `rm_init_leg` (native init is drive-equivalent). Two `g_init_leg` phases are deliberately skipped, neither a compared surface: phase 3's checkpoint-banner draw (gfx-only, regenerated by `rm_course_events`) and phase 11's palette-staging record at image **0x17fb0**, whose only consumed output is `obj_shade` — the record itself feeds the unported record-driven **mode-2/4/6 palette / screen-offset event** (the `game_update` row's *What remains*, next), so 0x17fb0 is never staged. **Wired** into the game boot AND restart (`game_main.c` `start_leg`), replacing every baked `*_INIT` leg-start scalar |
| between-legs flow: **draw surfaces** (slice A) | `intermission_poll` / `draw_intermission` / `fade_step` (recreate intermission.c) + `draw_leg_results` (results.c) | ✅ ported (`src/intermission.c`, `src/results.c`; new `include/flow.h` structs + `include/fill.h` fill family) | `test/test_flow.py` — `rm_intermission_poll` and `rm_draw_leg_results` (all 5 legs) and `rm_fade_step` **whole draw-buffer byte-exact** vs recreate's g_* (both flip parities where the dst derives from `flip_idx`); `rm_draw_intermission` **100% footprint, 0 wrong pixels** over the full `A_int_scroll` sweep 0x63→0 (both the bottom-clip and top-clip/source-advance regimes). Mutation-verified: dropping section 1, off-by-one-ing the clip, a wrong result-col / poll-src stride, and transposing the per-leg palette cursor each fail. `highscore_table` is modelled as a persistent buffer (like `hud_text`), seeded here from `init_scoretable`'s output — the flow slice (B) owns updates. The flow that SEQUENCES these (attract phases A–D) is slice B; these are host-verified cores, no on-target wiring yet | `test/test_flow.py` |
| between-legs flow: **state machine** (slice B) | `intermission` (`int_stepA`/`phaseB_leg`/`stepD_counter` @0x127a0) / `check_abort` @0x128ea / `update_highscore` @0x1238e / `init_playfield` @0x12af6 (recreate intermission.c / input.c / highscore.c) | ✅ ported (`src/flow.c`; new `FlowState` in `include/flow.h`) | `test/test_flow_machine.py` — each piece differential vs recreate's g_*: `check_abort` return fuzz; the Phase-A/B/D counter arithmetic over the counter ranges (branch cases + gate/underflow sweep) with the 3-way return codes; `update_highscore`'s ranking / row-shift / insert vs the recreate prefix checkpoint (directed new-high / mid / miss / full-table + a **distinct-row shift**, and a 60-seed fuzz over all legs — the 0x280 table + the mutated score record + results_mode/hiscore_pos/countdown compared); `init_playfield` nav (leg × delays × dir × input-change refill) + the fire edge. **Composed**: an attract CYCLE where phases **A/B/D are oracle-lockstepped** (each rm phase step beside the matching g_int_* slice on a reference image, counters + return compared) and **Phase C is a boundary-count only** — a pure-Python mirror of `intermission`'s inline 0x96-frame count that cannot itself fail, guarded solely by the pinned `INT_C_FRAMES` constant (== the C #define, `test_python_constants_match_the_c`); the demo pipeline Phase C runs is pinned SEPARATELY by the leg drives. Plus an end-to-end GAME-FLOW drive (a leg times out → `update_highscore` → `game_over_flag`++ via `rm_flow_game_over_enter` → intermission entry) matching main's loop-break path (decomp.c main @0x10100:286-317), the run-up checked scalar-for-scalar against the oracle every frame. Mutation-verified (dropped timer-wrap reload, off-by-one dwell, skipped highscore shift, off-by-one nav clamp — each caught). Host-side (`FlowState` is the composition's owner, as `_Candidate` owns the leg-drive structs). **Slice C composed it on-target** — `game_main.c` is now the game shell (see the `game_update` row); a `Shell` struct owns the composition on the 68000 as `FlowState` owns the counters. **Slice D hoisted the composition DRIVER** (the prologue + phase A/B/C/D loop, the leg-select loop, the game-over bracket) into `src/flow.c` behind a minimal `FlowOps` callback table, so `make test` now runs the whole A→B→C→D→leg-select sequence host-side (`test_flow_driver_*`) with **two distinct guarantees**: every flow COUNTER at each callback routes through the verified in-image oracle slices (`g_int_stepA`/`g_int_phaseB_leg`/`g_int_stepD_counter`/`g_check_abort`/`g_init_playfield_*`), while the SEQUENCING (draw/palette/show order, loop structure, event emission) is pinned against a **hand-written Python structural mirror** (`_mirror_int_cycle`/`_mirror_leg_select`) — it catches a one-sided mutation but NOT an ordering error authored identically into both the C driver and the mirror, so it is a structural mirror, not a lockstep "against `g_intermission`"; `game_main.c` keeps only the 68000 callback implementations (see the "flow COMPOSITION" note below). The `update_highscore` interactive **name-entry tail** is ported + wired in **slice F** (below) | `test/test_flow_machine.py` |
| between-legs flow: **leg-name menu + get-ready** (slice E) | `draw_divider` / `draw_panel5` (recreate text.c) + `draw_leg_labels` (results.c) + `ip_start_leg` (intermission.c @0x2c96) | ✅ ported + wired (`src/results.c` divider/panel5; `src/events.c` exposes `rm_draw_leg_labels`; `src/flow.c` drives the leg-select redraw + fire-start "get ready"; `game_main.c` `op_draw_panel5`/`op_draw_leg_labels`/`op_flash_frame`) | `test/test_flow.py` — `rm_draw_divider` and `rm_draw_panel5` **whole draw-buffer byte-exact** vs recreate's `g_draw_divider` / `g_draw_panel5` (both flip parities). `rm_draw_leg_labels` is the existing folded-probe body exposed publicly (byte-exact vs `g_draw_leg_labels` via `test_events`' `checkpoint_leg0`) — its `probe_collision` only WALKS the dashboard marker (no crash arm), so it is safe in Phase B / fire-start exactly as the original runs it there. `test/test_flow_machine.py` — the leg-select redraw now draws `draw_panel5`, and the fire-start runs `ip_start_leg` (rebuild dash → results+menu ×2 → labels → the 121-frame `leg_start_palette` flash), locksteped vs the oracle mirror; `test_flow_driver_get_ready_flash` pins the panel5/label/flash counts. Mutation-verified: dropping a panel5 call, dropping a flash frame, and a wrong flash length each fail a driver test. The flash is an off-image palette animation (`op_flash_frame` reads the obj-low flash tables into a mutable `leg_start_pal`); the driver owns the frame COUNT (`FlowTuning.flash_frames`, pinned == the C `IP_FLASH_FRAMES` by `test_python_constants_match_the_c`), the palette itself is a Setpalette seam. On-target: `run_golden.py` MATCH (the golden's `BOOT_FAST_LEG` skips the menu, so unaffected) and the `GAME_FLOW_AUTO` trace is unchanged (the get-ready adds frames but no trace tags — loop still closes) | `test/test_flow.py` / `test/test_flow_machine.py` |
| between-legs flow: **high-score name entry** (slice F) | `draw_results_screen` @0x1225a (recreate text.c) + `hiscore_countdown` / `hiscore_charstep` / the name-entry loop + game-over tail (recreate highscore.c @0x12412) | ✅ ported + wired (`src/results.c` `rm_draw_results_screen`; `src/flow.c` `rm_hiscore_countdown` / `rm_hiscore_charstep` / `rm_flow_name_entry` / `rm_flow_game_over_tail`; `game_main.c` `op_draw_results_screen`/`op_name_flash` + the leg-end branch) | `test/test_flow.py` — `rm_draw_results_screen` **whole draw-buffer byte-exact** vs recreate's `g_draw_results_screen` over the MADE path (mode 0, ranks 1/5/9, legs 0/2/4) and the MISSED path (mode 2), both flip parities. `test/test_name_entry.py` — `rm_hiscore_countdown` / `rm_hiscore_charstep` differential vs recreate's `g_hiscore_*` (the sub/timer × tens/units × underflow grid; the char × delays × direction grid), exactly as `update_highscore` is sliced (the interactive loop never returns under the oracle); the loop itself is a `FlowOps` driver whose SEQUENCING (prime double-draw, per-frame draw/flash/show/poll, and the terminal fade → **121-frame hold** → **input-release wait**) is pinned STRUCTURALLY (a recording log) and whose bookkeeping (three initials written into row+8, confirm / **backspace** — a dedicated seed-0x60 delete-then-reconfirm case / timeout termination, the rank cleared) is pinned directly. The made/missed **dispatch is `rm_flow_score_tail`** in `src/flow.c` (not the shell), so `make test` drives BOTH branches (made → name entry, missed → game-over redraw). Mutation-verified: a wrong wrap bound, a dropped auto-repeat gate, a dropped fire edge, a timeout off-by-one, **a dropped terminal hold, a dropped input-release wait, a broken backspace `p -= 1`, and an inverted made/missed dispatch** each fail a test. New hand-copied constants pinned in `test_python_constants_match_the_c` (`HS_NAME_FIELD_OFF` vs flow.h, `HS_TIME_HI_OFF` vs flow.c + the score-line/time-digit addresses, `HS_HOLD_FRAMES` and the shared `HS_ROW` / `HS_LEG_STRIDE` geometry vs flow.h). The terminal tail's NON-sound steps are now REPRODUCED: the finished table is redrawn (the "fade" — draw + palette + flip ×2), held `FlowTuning.hold_frames` Vsyncs (default 121 == the C `HS_HOLD_FRAMES`, so the fast harness can shorten it, `op_hold_frame` = a plain `Vsync`), then the input-release wait polls until no bit is held. **Seams** (honest): ONLY the name-entry jingle + the terminal SOUND waits (mzflag / TURNOFF / the Crawio key-drain) remain off-image never-return SEAMS recreate marks — the game ships WITHOUT sound, so they resolve to nothing and control returns to the intermission; the colour-3 flash (`op_name_flash`) is an off-image `Setcolor` seam (like the get-ready flash) whose per-frame COUNT the driver owns and whose content — `A_name_anim_tbl[(anim_counter & 0xe)]` — is a documented seam. On-target: `run_golden.py` **MATCH** (unaffected — the golden's `BOOT_FAST_LEG` boots straight into a leg) and the `GAME_FLOW_AUTO` trace is **unchanged** (19 records, the documented sequence): the auto leg-end score misses the default table, so the game-over tail (two redraws, no new trace tags) runs, not the interactive screen | `test/test_flow.py` / `test/test_name_entry.py` |
| `game_update` (integration + sound) | `g_game_update` §1,2 + wiring | 🟨 events core WIRED end-to-end; the leg/game-flow CORE landed (slice 1, host-side): §1's marker gate + §2's input capture (`rm_player_update`), and the crash / end-of-race tally — HUD phase 8's timer decay + `draw_crash_fx`'s STATE side — as `rm_crash_fx_update` (`src/events.c`). A leg now **ENDS**: the tally arms `abort_flag` (0xffff game-over / 0x33 bonus-exhausted, decaying negative), which the frame loop reads as the leg end. Differential-pinned by `test/test_crash_fx.py` (every branch) and organically by `test/test_leg_drive.py`'s idle-to-time-out drives. **Slice 2 wired the tally on-target**, and the **leg START is now native too** (`rm_init_leg`, above): `game_main.c`'s `start_leg` resets every per-leg owner struct through `rm_init_leg` and derives the views, at boot AND on the `abort_flag < 0` / R restart — no baked leg-start state remains. Proven on the 68000 by the idle leg-end autodrive trace (arm 0x59 → negative → `abort_flag` 0xffff → restart through `start_leg`, clean). What remains: the sound path (INITTUNE/INITFX/TURNOFF, the VBL vector); and the record-driven mode-2/4/6 palette / screen-offset events (course_advance's tail). The intermission / results / highscore flow AROUND `init_leg` is ported host-side (**slice B**) and, **since slice C, composed on-target**: `game_main.c` is the whole game shell — `run_leg_select` (init_playfield) → `start_leg` (rm_init_leg) → the race loop → on the leg end `rm_update_highscore` → `rm_flow_game_over_enter` → `run_intermission` (the attract A→B→C→D cycle) → `rm_flow_game_over_exit` → back to the leg select. The leg-restart stand-in is **gone**; a `Shell` handle owns the composition. The shipping **BUGGYBOY.PRG** boots into the LEG SELECT first, exactly as the original game does — no boot fast path. The frame-0 golden harness (`run_golden.py`) builds a SEPARATE variant with `-DGOLDEN_BOOT_LEG=N` that DOES take the fast path (skip the leg select, start leg N, dump frame 0) so it can pin the boot frame; the `#ifdef BOOT_FAST_LEG` block compiles ONLY under `GOLDEN_BOOT_LEG` / `GAME_AUTODRIVE`. So the shipping cold-boot leg-select branch (that `#ifdef`'s `#else`) is exercised ONLY by the manual `GAME_FLOW_AUTO` flow-trace recipe — `make test` builds no `.PRG`, and `run_golden.py` compiles the `BOOT_FAST_LEG` branch. The leg-select fire can start any leg (`bind_leg` recomputes the per-leg stream/mask at runtime). Proven on the 68000 by the flow-trace run (leg select → fire → leg → time-out → highscore + intermission A→B→C→D → return to the leg select — the loop closes; PORTING "flow phase trace"). `run_golden.py` still **MATCH**es (leg-0 frame-0 golden; legs 1–4 are playable but only leg 0 has a golden — a per-leg golden is deferred). Seams the shell documents: **sound (the game ships WITHOUT sound — a documented seam)**, Vsync cadence, per-phase palettes (off-image), the attract input-replay (Phase C holds throttle); `init_scoretable`'s output is a baked seed (`fixture_highscore`) copied into RAM at boot. **The interactive high-score name-entry tail is now ported + wired** (slice F): a leg-end score that makes the table runs the initials screen, one that misses runs the short game-over screen, then the intermission. **The between-legs sub-draws are now ported + wired** (see the slice-E row): the leg-name menu (`rm_draw_panel5` + `rm_draw_divider`) draws over the leg-select / get-ready screens, `rm_draw_leg_labels` paints each leg's place-name labels onto the dashboard in Phase B + the fire-start, and the fire-start runs the real `ip_start_leg` "get ready" (results + menu ×2, then the 121-frame `leg_start_palette` flash — an off-image palette animation) | — |

**What the player-physics slice covers** (see `include/game.h` for the state model): the engine
rpm→speed model with its rev limiter, the road-scroll rate and the view advance whose wrap times the
course, the wheel position → body lean → road-curvature integrator, the road-edge clamp plus the
off-road push, and — since §6 landed — the crash / auto-steer script that takes the controls away
while a canned crash replays out of `crash_anim_tbl` and then hands them back.

The precondition on `rm_player_update` is gone: the course-event engine that **decides** to crash you
— §12's collision probe, the fx block rebuilt from `obj_flags`, and the horizon-event dispatch — is
now wired in end-to-end (slice 2). The §6 event path dispatches a pending event through it (a
bonus-display record even rebuilds the control table mid-dispatch), and the leg drive / game run the
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
  **Slice 2 wired that on-target**: `game_main.c`'s frame loop runs `rm_crash_fx_update` every frame at
  the per-frame tail (before `apply_player`, so the drawn HUD sees this frame's tally through the six
  `EventState`→`HudState` view fields), and on `abort_flag < 0` restarts the current leg. **The restart
  (and the boot) now run NATIVELY through `rm_init_leg`** (`game_main.c` `start_leg`), which resets every
  per-leg owner struct exactly as recreate's `init_leg` does — replacing the old baked `*_INIT` snapshot.
  It stands in only for the intermission / results / highscore flow AROUND `init_leg` (the
  `game_over_flag++` handoff), which is still unported.
  Verified on the 68000 by the idle leg-end autodrive trace (`GAME_AUTODRIVE`/`GAME_TRACE` with
  `AUTODRIVE_BASE_INPUT=0` + `GAME_TIME_LEFT`): `hud_crash_timer` arms 0x5b, decays negative, `abort_flag`
  arms 0xffff, and the leg restarts with every persistent field reset — the game survives its first leg
  end with no hang or corruption. The trace record grew a 9th word (`abort_flag`) for it.

- **The flow COMPOSITION now has host coverage (slice D — closes the slice-C gap).** The driver that
  SEQUENCES the between-legs pieces — the prologue, the Phase A/B/C/D loop, the draws/flips/palettes, the
  leg-select loop, the game-over enter/exit bracket, the quit unwind — is hoisted out of `game_main.c`
  into `src/flow.c` (`rm_flow_intermission_cycle` / `rm_flow_intermission` / `rm_flow_leg_select` /
  `rm_flow_game_over`, mirroring `g_intermission` / `g_init_playfield` structure-for-structure). It
  reaches the platform effects it orders — drawing into the back buffer, flipping, palettes, input, the
  demo-leg pipeline — through a minimal `FlowOps` callback table + a `FlowTuning` (the attract-timing
  knobs, the GAME_FLOW_FAST debug seeds promoted to data). `game_main.c` keeps ONLY the 68000
  implementations of those callbacks (`op_*` over the `Shell`) and calls the driver. `make test` now
  compiles and runs it host-side with **two distinct guarantees**: `test/test_flow_machine.py`'s
  `test_flow_driver_*` run the hoisted driver with recording callbacks and (1) compare every flow COUNTER
  at each callback against the verified in-image oracle slices (`g_int_stepA`/`g_int_phaseB_leg`/
  `g_int_stepD_counter`/`g_check_abort`/`g_init_playfield_*`), so a counter-arithmetic divergence fails
  hard; and (2) pin the SEQUENCING (draw/palette/show order, the phase-loop structure, event emission)
  against a **hand-written Python structural mirror** (`_mirror_int_cycle` / `_mirror_leg_select`) — the
  whole A→B→C→D→leg-select sequence (incl. the abort/quit unwind in every polling phase and the game-over
  bracket) with 0 divergences. This is a structural mirror, NOT a lockstep against `g_intermission`: it
  catches a ONE-SIDED mutation but would pass an ordering error authored identically into both the C
  driver and the mirror. Mutation-verified (one-sided): skipping a phase transition (drop the Phase-B leg
  advance), a wrong flip parity (drop the Phase-A flip), a dropped palette (drop the prologue INT_A
  palette), and an off-by-one dwell (INT_D_DWELL 0x1a→0x1b) each fail a driver test. Of the four
  correctness bugs that historically escaped, **only two live in this now-covered driver code**: the idle
  trace hanging past the leg end and Esc/Q unreachable from menus. The other two are NOT in the driver —
  the leg-start marker reseed lives in `start_leg` (reached via `op_start_demo_leg`, a host stub here) and
  the menu-race palette is set in `main()` after `rm_flow_leg_select` returns — so both remain guarded
  ONLY by the on-target `GAME_FLOW_AUTO` flow trace + the frame-0 golden `MATCH`, which also still guard
  the wiring the callbacks stand in for (the demo-leg render, the Vsync/palette seams).

- **The Phase-B / get-ready callback INTERIORS are exercised only ON-TARGET.** The host flow-driver test
  (`test_flow_driver_*`) stubs `start_demo_leg` / `flash_frame` (they only record that they fired), so the
  bodies of `op_start_demo_leg` (the `start_leg` → `op_rebuild_dash` → `op_draw_leg_labels` ORDER — the
  labels must come after the dash rebuild, which redraws the graphic and would otherwise wipe them) and
  `op_flash_frame` (the per-frame palette arithmetic) run only on the 68000, guarded by `run_golden.py`
  MATCH + the `GAME_FLOW_AUTO` trace. The get-ready flash's frame counter is the SHARED
  `GobjPrefixState.anim_counter` (`op_flash_frame` reads/increments it +1 per flash frame, exactly as
  recreate's `ip_start_leg` reads/writes `A_anim_counter` at intermission.c:406) — the race/demo bumps it
  +2/frame and the flash runs before `start_leg` re-zeroes the prefix, so the flash carries the preceding
  race's animation history like the arcade. This is an off-image (palette-only) seam: the byte-compare and
  the golden are palette-agnostic, so NO host test pins the counter value or the animated palette — only
  the flash frame COUNT is pinned (`FlowTuning.flash_frames == IP_FLASH_FRAMES`). The hand-copied flash
  ADDRESSES/masks/offsets ARE pinned equal to recreate's (`test_python_constants_match_the_c`).

- **`rev_reload` (§1's engine-idle poke) is invisible and skipped, verified not assumed.** §1 writes
  `rev_reload = 8` (0x18d12) when the buggy is stopped; it aliases `lean_frame`, which no compared
  surface reads, so it is omitted exactly as §6/§7 omit the same write. The idle time-out drives run at
  `speed == 0` — the very condition that triggers the reference's `rev_reload` write every frame — and
  pass with zero mismatches, so the skip is demonstrably invisible rather than merely presumed.

- **The draw-struct fan-out gap (dirt/wheel sprite stuck on the road during a jump) is fixed + host-
  tested.** The per-frame `apply_player` fan-out copied PlayerState → the draw structs but MISSED four
  fields the verified sprite draws READ: `sprite->anim_frame` (the fg frame the crash script picks —
  `sprite.c` reads `sx16(s->anim_frame)`, never written in the shell), `sprite->spin_state` (the fg
  spin-abort gate), and `sprite->spin_reset` + `sprite->collision_lock` (the lower-body suppressors
  during a crash/spin). Each is now fanned out reproducing recreate's exact aliasing (verified against
  `game_update.c`): `anim_frame = p->anim_frame_sel` (byte → word, hi 0 = image 0x18d0c/0x18d0d);
  `spin_state = (int8_t)(ev->spin_state >> 8)` (the fx<<8 word's hi byte, 0x18caa); `spin_reset =
  (p->spin_reset << 16) | p->spin_word2` (the 0x18cc8 long); `collision_lock = p->collision_lock`
  (0x18c84). The whole fan-out body was **hoisted** out of `game_main.c` into `rm_apply_player`
  (`src/gameplay.c`), which `make test` compiles — closing the coverage hole (the seam had no host
  test: `test_sprite` staged SpriteState straight from the image, and the leg drives never derived the
  sprite). `test/test_leg_drive.py` now runs the fan-out every frame and pins the four fields against
  recreate's image bytes over the crash/jump drives, asserting they go NONZERO
  (`test_fanout_tracks_recreate_and_reaches_nonzero`; `spin_reset` — reachable only via §10's spin
  override, like `test_spin_arming` — by `test_fanout_spin_reset_reaches_lower_body_suppress`, which
  seeds BOTH words of the long: the high word (0x18cc8, the `<<16` shift) and `spin_word2` (0x18cca,
  the `|` term). `spin_word2` is a real field the reference writes 0x19 into — §10's arming stores
  `GU_SPIN_HI` there when `obj_flag_b != 0` (`game_update.c` `gu_dispatch_event` idx 32/33) — but no
  leg/fuzz drive makes it nonzero at draw time, so it is staged directly (like `test_spin_arming`'s
  word2 cases); with `spin_reset` already nonzero the arming leaves the low word intact, so it rides
  the long to the fan-out.
  `test_sprite` gained an FG case at a real nonzero `anim_frame` (rec[5] ∈ {8,16}, from live drives).
  Mutation-verified: zeroing any of the four fan-out lines fails a fan-out test, and dropping either
  half of the `spin_reset` long (the `<<16` shift OR the `| spin_word2` term) diverges the compared
  long — both caught by the one directed spin-reset drive.

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

`tools/bench.py` measures the game's WHOLE frame per stage on the cycle-accurate Musashi 68000 —
remaster (native structs, via the `bench_*` wrappers, staged exactly as game_main.c's frame) vs
recreate's recon (flat image) where an image-arg-only recon entry has the same scope — on the same
staged leg-0 boot frame. Build first: `bash render/atari/bench_build.sh`. `tools/profile.py <bench_sym>`
breaks any stage down to cycles-per-function (and per-PC with `--lines`) via the oracle's
cycle histogram.

Current (8 MHz ST, 160000-cycle 50 Hz frame budget) — the game frame is **203 ms ≈ 4.9 fps** on the
staged frame. Caveat before reading the object rows: the staged frame is the game's BOOT frame — a
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
- **The game's per-frame `memset` was ~a third of the frame and redundant — now removed (free 96 ms).**
  recreate's own pipeline repaints every framebuffer byte (its captured frames are deterministic with
  no clear), and the shim memset was a byte loop besides. The game now clears both screen buffers once
  at boot and never again. Verified: `run_golden.py` still reports MATCH on the frame-0 golden, and the
  autodrive frame-2 and frame-61 dumps are byte-identical to a per-frame-clear build (proving the
  clear was redundant on both buffer parities, not just frame 0).
- **The two fine-x sprite blitters dominate the object tree** — `rm_blit_objshift`/
  `rm_blit_objshift2` are 99 ms of the gate frame's 117 ms tree (87%/97% of their passes). Their
  cell helpers mutate `col0/col1/sp` through pointers, so GCC keeps the loop state in memory: the
  profile shows ~16 k cycles of pure `movel %sp@(x),%sp@(y)` spill shuffling plus memory-RMW cursor
  updates per pass. Value-passing restructure (same bytes out, pinned by
  `test/test_blit_engines.py`) is the next win.
- **Do not collapse the wrap-frame's double `rm_build_road_geometry`.** On a view-wrap the game
  builds twice: once before `rm_course_events` (so `horizon_row` is fresh for the event tail), then
  again inside `draw_frame` (off the ring bands the tail pokes). Both are faithful — the original's
  own `g_draw_frame` (recreate gameplay.c:268) likewise rebuilds after the event pokes — so a future
  perf pass must not "dedupe" it: dropping either build renders stale-horizon / pre-poke geometry.
- **Where the fps can land (8 MHz ST, median frame ~180 ms recreate-parity):** dropping the memset
  puts the remaster game at ~155 ms ≈ 6.5 fps median. The full plan (blitters, road display list,
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
