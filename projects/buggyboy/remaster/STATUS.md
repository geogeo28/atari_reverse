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
| on-target full frame | build_geometry+render_road+blit_road_scroll+draw_game_objects+draw_hud | ✅ byte-identical on 68000, **all legs 0–4** + **playable** | `render/atari/BUGGYBOY.PRG` is the playable game (boots the leg select, WITH sound — slice 3). The golden-harness variant (`GOLDEN.PRG`, `-DGOLDEN_BOOT_LEG=N`, built by `run_golden.py`) starts leg N directly and its start frame MATCHes recreate's whole ported pipeline (road, ground, foreground sprite, roadside object list incl. the start gate, scaled object, buggy, HUD); `run_golden.py` loops **all five legs 0–4** — each leg builds its own `GOLDEN.PRG` (the leg is one source: the loop var → `GOLDEN_LEG=N` for the reference render + `-DGOLDEN_BOOT_LEG=N` for the boot) and byte-compares against its own `golden_leg<N>.bin`; **five MATCHes** (the per-leg goldens genuinely differ, 1624–5002 bytes vs leg 0, so this is a real per-leg proof, not five identical frames). ~16 s for the set (~3 s/leg, sequential); the loop is then driven by `rm_player_update` with held-key **or joystick** input (own IKBD handler; joystick in port 1 has priority, keyboard is the fallback — `read_input @0x120b0`); `test/test_game_fixture.py` pins the fixture's buf_a window to the dispatcher's type-record reach. **Joystick verification (honest):** the ACIA packet parser + interrogate live in `os.s`/`game_main.c`, an on-target path `make test` cannot reach. The `GAME_FLOW_AUTO` trace (**unchanged at 19 records**) proves only that the per-frame `Ikbdws` interrogate + `kbd_isr` packet parse **run without hanging, bus-erroring, or corrupting the keyboard/flow** — under headless Hatari no stick is attached, so the interrogate reply is all-zeros and the trace is byte-identical whether the joystick STORE/decode is right or broken; it does NOT exercise the decode. `run_golden.py` MATCH is likewise silent on it (the interrogate never fires before the frame-0 dump). So the joystick STORE path is pinned ONLY by the **manual stick-in-hand run** (headless Hatari cannot inject key/joystick events): `hatari --memsize 4 --tos-res low --joy1 keys --harddrive render/atari/disk --auto 'C:\BUGGYBOY.PRG'` then drive with the arrow keys + a joystick-fire key — the buggy steers/accelerates and the parser keeps scancodes clean (the pre-joystick build mis-read `0xFD` reports as scancodes) |
| `render_road`      | `g_render_road`           | ✅ all 7 bands ported | `test/test_road.py` — **whole-framebuffer byte-exact** across legs 0–4 / warmup depths |
| `build_road_geometry` | `g_build_road_geometry` | ✅ all 5 stages ported | `test/test_geometry.py` — control table + rendered road byte-exact under arbitrary steering (curve/view/near-slope) |
| `blit_road_scroll` | `g_blit_road_scroll`      | ✅ ported | `test/test_scroll.py` — whole-framebuffer + scroll-state byte-exact under arbitrary scroll (speed/pos/wrap) |
| buggy/fg sprites (`draw_fg_sprite`, `draw_buggy`) | `g_draw_fg_sprite` / `g_draw_buggy` | ✅ ported | `test/test_sprite.py` — whole-framebuffer byte-exact across body/leaning frames, spin aborts, lean overlay, lower body |
| ground / horizon (`draw_ground`) | `g_draw_ground` | ✅ ported | `test/test_ground.py` — whole-framebuffer byte-exact across gradient (band-clamp buckets) + solid (lit/near) markers |
| scaled object (`draw_object`) | `g_draw_object` | ✅ ported | `test/test_object.py` — whole-framebuffer byte-exact across LEFT/RIGHT/FAR/SCALE2 flag combos, all shade signs, pre-scan clear |
| fine-x blit engines (`blit_objshift`, `blit_objshift2`, objsprite) | `g_blit_objshift` / `_w2` / `g_blit_objshift2` / `g_objsprite_t*` | ✅ ported (C reference; **both hot engines `blit_objshift` + `blit_objshift2` also have shipped hand-asm cores, PERF30 A3 phase 1+2**; objsprite stays C) | `test/test_blit_engines.py` — byte-exact fuzz across every fine-x, dispatch case (clip/edge/base/wide), colours, strides, all width families; `test/test_asm_blit.py` — Musashi C-vs-asm differential for BOTH hand-asm cores (`src/asm/objshift2.S`, `src/asm/objshift.S`), 1740 + 1560 cases |
| object-list dispatcher (`draw_object_list` + obj_dispatch + handlers) | `g_draw_object_list` | ✅ ported | `test/test_object_list_rm.py` — whole-framebuffer byte-exact across the real per-frame passes, legs 0–4 |
| `draw_game_objects` (prefix + orchestrator) | `g_draw_game_objects` / `g_draw_game_objects_prefix` | ✅ ported | `test/test_game_objects_rm.py` — whole-frame composite byte-exact; `test/test_gobj_prefix.py` — prefix state byte-exact (marker/anim/bonus) |
| whole-frame composition (`draw_frame`) | `g_draw_frame` | ✅ hoisted (`src/frame.c`, `rm_draw_frame`) — the shell calls ONE composition (the bench deliberately mirrors it with staged HUD scalars); the shell keeps only buffer selection + `Setscreen` | `test/test_composed_frame.py` — the **composed-frame differential**: the candidate's OWN full per-frame composition (the `apply_player`/`gobj_hud_view` fan-outs → `rm_draw_frame`, from its live owned state) is byte-identical to recreate's `g_draw_frame` on sampled event/cadence frames of the free + directed drives (all legs, incl. real crash + flag-capture + leg-end frames); **strict, no allowlist**; mutation-verified (the two escaped fan-out bugs + a dropped stage + a swapped stage each fail). Backstops the fan-out coverage hole the per-stage tests leave — see the coverage-audit note |
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
| leg start (`rm_init_leg`) | `g_init_leg` @0x104b8 | ✅ ported + wired | `test/test_init_leg.py` — differential vs `g_init_leg` over ALL legs 0-4, FRESH (from scratch) + RE-INIT (warmed, non-zero preserved fields), every owned surface (the physics/course/event/pose/scroll scalar block, the ring band-by-band + its ST mirror, the buggy pose, the HUD-text region bytes, `obj_shade`, `screen_offset`, and phase 11's **staged palette record**), mutation-verified; plus `test/test_leg_drive.py::test_leg_drive_from_native_init` — a free-running drive whose candidate START comes from `rm_init_leg` (native init is drive-equivalent). Only ONE `g_init_leg` phase is now deliberately skipped (not a compared surface): phase 3's checkpoint-banner draw (gfx-only, regenerated by `rm_course_events`). **Phase 11 is fully ported** — it stages the object-display / palette record (image **0x17fac..0x17fb9**, the same record the mode-4 event re-stages) into a native `race_pal` buffer AND derives `obj_shade`; the four staged palette pieces are a compared surface. The palette itself is an off-image Setpalette seam (the game ships without exact colours mattering to the byte-compare / golden), but the staged BYTES are pinned. **Wired** into the game boot AND restart (`game_main.c` `start_leg`), replacing every baked `*_INIT` leg-start scalar |
| between-legs flow: **draw surfaces** (slice A) | `intermission_poll` / `draw_intermission` / `fade_step` (recreate intermission.c) + `draw_leg_results` (results.c) | ✅ ported (`src/intermission.c`, `src/results.c`; new `include/flow.h` structs + `include/fill.h` fill family) | `test/test_flow.py` — `rm_intermission_poll` and `rm_draw_leg_results` (all 5 legs) and `rm_fade_step` **whole draw-buffer byte-exact** vs recreate's g_* (both flip parities where the dst derives from `flip_idx`); `rm_draw_intermission` **100% footprint, 0 wrong pixels** over the full `A_int_scroll` sweep 0x63→0 (both the bottom-clip and top-clip/source-advance regimes). Mutation-verified: dropping section 1, off-by-one-ing the clip, a wrong result-col / poll-src stride, and transposing the per-leg palette cursor each fail. `highscore_table` is modelled as a persistent buffer (like `hud_text`), seeded here from `init_scoretable`'s output — the flow slice (B) owns updates. The flow that SEQUENCES these (attract phases A–D) is slice B; these are host-verified cores, no on-target wiring yet | `test/test_flow.py` |
| between-legs flow: **state machine** (slice B) | `intermission` (`int_stepA`/`phaseB_leg`/`stepD_counter` @0x127a0) / `check_abort` @0x128ea / `update_highscore` @0x1238e / `init_playfield` @0x12af6 (recreate intermission.c / input.c / highscore.c) | ✅ ported (`src/flow.c`; new `FlowState` in `include/flow.h`) | `test/test_flow_machine.py` — each piece differential vs recreate's g_*: `check_abort` return fuzz; the Phase-A/B/D counter arithmetic over the counter ranges (branch cases + gate/underflow sweep) with the 3-way return codes; `update_highscore`'s ranking / row-shift / insert vs the recreate prefix checkpoint (directed new-high / mid / miss / full-table + a **distinct-row shift**, and a 60-seed fuzz over all legs — the 0x280 table + the mutated score record + results_mode/hiscore_pos/countdown compared); `init_playfield` nav (leg × delays × dir × input-change refill) + the fire edge. **Composed**: an attract CYCLE where phases **A/B/D are oracle-lockstepped** (each rm phase step beside the matching g_int_* slice on a reference image, counters + return compared) and **Phase C is a boundary-count only** — a pure-Python mirror of `intermission`'s inline 0x96-frame count that cannot itself fail, guarded solely by the pinned `INT_C_FRAMES` constant (== the C #define, `test_python_constants_match_the_c`); the demo pipeline Phase C runs is pinned SEPARATELY by the leg drives. Plus an end-to-end GAME-FLOW drive (a leg times out → `update_highscore` → `game_over_flag`++ via `rm_flow_game_over_enter` → intermission entry) matching main's loop-break path (decomp.c main @0x10100:286-317), the run-up checked scalar-for-scalar against the oracle every frame. Mutation-verified (dropped timer-wrap reload, off-by-one dwell, skipped highscore shift, off-by-one nav clamp — each caught). Host-side (`FlowState` is the composition's owner, as `_Candidate` owns the leg-drive structs). **Slice C composed it on-target** — `game_main.c` is now the game shell (see the `game_update` row); a `Shell` struct owns the composition on the 68000 as `FlowState` owns the counters. **Slice D hoisted the composition DRIVER** (the prologue + phase A/B/C/D loop, the leg-select loop, the game-over bracket) into `src/flow.c` behind a minimal `FlowOps` callback table, so `make test` now runs the whole A→B→C→D→leg-select sequence host-side (`test_flow_driver_*`) with **two distinct guarantees**: every flow COUNTER at each callback routes through the verified in-image oracle slices (`g_int_stepA`/`g_int_phaseB_leg`/`g_int_stepD_counter`/`g_check_abort`/`g_init_playfield_*`), while the SEQUENCING (draw/palette/show order, loop structure, event emission) is pinned against a **hand-written Python structural mirror** (`_mirror_int_cycle`/`_mirror_leg_select`) — it catches a one-sided mutation but NOT an ordering error authored identically into both the C driver and the mirror, so it is a structural mirror, not a lockstep "against `g_intermission`"; `game_main.c` keeps only the 68000 callback implementations (see the "flow COMPOSITION" note below). The `update_highscore` interactive **name-entry tail** is ported + wired in **slice F** (below) | `test/test_flow_machine.py` |
| between-legs flow: **leg-name menu + get-ready** (slice E) | `draw_divider` / `draw_panel5` (recreate text.c) + `draw_leg_labels` (results.c) + `ip_start_leg` (intermission.c @0x2c96) | ✅ ported + wired (`src/results.c` divider/panel5; `src/events.c` exposes `rm_draw_leg_labels`; `src/flow.c` drives the leg-select redraw + fire-start "get ready"; `game_main.c` `op_draw_panel5`/`op_draw_leg_labels`/`op_flash_frame`) | `test/test_flow.py` — `rm_draw_divider` and `rm_draw_panel5` **whole draw-buffer byte-exact** vs recreate's `g_draw_divider` / `g_draw_panel5` (both flip parities). `rm_draw_leg_labels` is the existing folded-probe body exposed publicly (byte-exact vs `g_draw_leg_labels` via `test_events`' `checkpoint_leg0`) — its `probe_collision` only WALKS the dashboard marker (no crash arm), so it is safe in Phase B / fire-start exactly as the original runs it there. `test/test_flow_machine.py` — the leg-select redraw now draws `draw_panel5`, and the fire-start runs `ip_start_leg` (rebuild dash → results+menu ×2 → labels → the 121-frame `leg_start_palette` flash), locksteped vs the oracle mirror; `test_flow_driver_get_ready_flash` pins the panel5/label/flash counts. Mutation-verified: dropping a panel5 call, dropping a flash frame, and a wrong flash length each fail a driver test. The flash is an off-image palette animation (`op_flash_frame` reads the obj-low flash tables into a mutable `leg_start_pal`); the driver owns the frame COUNT (`FlowTuning.flash_frames`, pinned == the C `IP_FLASH_FRAMES` by `test_python_constants_match_the_c`), the palette itself is a Setpalette seam. On-target: `run_golden.py` MATCH (the golden's `BOOT_FAST_LEG` skips the menu, so unaffected) and the `GAME_FLOW_AUTO` trace is unchanged (the get-ready adds frames but no trace tags — loop still closes) | `test/test_flow.py` / `test/test_flow_machine.py` |
| between-legs flow: **high-score name entry** (slice F) | `draw_results_screen` @0x1225a (recreate text.c) + `hiscore_countdown` / `hiscore_charstep` / the name-entry loop + game-over tail (recreate highscore.c @0x12412) | ✅ ported + wired (`src/results.c` `rm_draw_results_screen`; `src/flow.c` `rm_hiscore_countdown` / `rm_hiscore_charstep` / `rm_flow_name_entry` / `rm_flow_game_over_tail`; `game_main.c` `op_draw_results_screen`/`op_name_flash` + the leg-end branch) | `test/test_flow.py` — `rm_draw_results_screen` **whole draw-buffer byte-exact** vs recreate's `g_draw_results_screen` over the MADE path (mode 0, ranks 1/5/9, legs 0/2/4) and the MISSED path (mode 2), both flip parities. `test/test_name_entry.py` — `rm_hiscore_countdown` / `rm_hiscore_charstep` differential vs recreate's `g_hiscore_*` (the sub/timer × tens/units × underflow grid; the char × delays × direction grid), exactly as `update_highscore` is sliced (the interactive loop never returns under the oracle); the loop itself is a `FlowOps` driver whose SEQUENCING (prime double-draw, per-frame draw/flash/show/poll, and the terminal fade → **121-frame hold** → **input-release wait**) is pinned STRUCTURALLY (a recording log) and whose bookkeeping (three initials written into row+8, confirm / **backspace** — a dedicated seed-0x60 delete-then-reconfirm case / timeout termination, the rank cleared) is pinned directly. The made/missed **dispatch is `rm_flow_score_tail`** in `src/flow.c` (not the shell), so `make test` drives BOTH branches (made → name entry, missed → game-over redraw). Mutation-verified: a wrong wrap bound, a dropped auto-repeat gate, a dropped fire edge, a timeout off-by-one, **a dropped terminal hold, a dropped input-release wait, a broken backspace `p -= 1`, and an inverted made/missed dispatch** each fail a test. New hand-copied constants pinned in `test_python_constants_match_the_c` (`HS_NAME_FIELD_OFF` vs flow.h, `HS_TIME_HI_OFF` vs flow.c + the score-line/time-digit addresses, `HS_HOLD_FRAMES` and the shared `HS_ROW` / `HS_LEG_STRIDE` geometry vs flow.h). The terminal tail's NON-sound steps are now REPRODUCED: the finished table is redrawn (the "fade" — draw + palette + flip ×2), held `FlowTuning.hold_frames` Vsyncs (default 121 == the C `HS_HOLD_FRAMES`, so the fast harness can shorten it, `op_hold_frame` = a plain `Vsync`), then the terminal `wait_music_off` op runs BEFORE `rm_turnoff` (so the shell's slice-3 mzflag spin can still read the not-yet-cleared flag), then the input-release wait polls until no bit is held. **Sound is now WIRED (slice 2)**: the name-entry jingle (tune 4 rank-1 / else 3) + the terminal TURNOFF + fxflag clear drive the `SoundDriver`; only the tune-end WAIT (the `wait_music_off` op — a shell Vsync + `rm_sound_music_on` spin, slice 3) and the Crawio key-drain stay off-image seams. The colour-3 flash (`op_name_flash`) is an off-image `Setcolor` seam (like the get-ready flash) whose per-frame COUNT the driver owns and whose content — `A_name_anim_tbl[(anim_counter & 0xe)]` — is a documented seam. A dropped `wait_music_off` op fails `test_name_entry_full` (the jingle would be cut). On-target: `run_golden.py` **MATCH** (unaffected — the golden's `BOOT_FAST_LEG` boots straight into a leg) and the `GAME_FLOW_AUTO` trace is **unchanged** (19 records, the documented sequence): the auto leg-end score misses the default table, so the game-over tail (two redraws, no new trace tags) runs, not the interactive screen | `test/test_flow.py` / `test/test_name_entry.py` |
| `game_update` (integration + sound) | `g_game_update` §1,2 + wiring | 🟨 events core WIRED end-to-end; the leg/game-flow CORE landed (slice 1, host-side): §1's marker gate + §2's input capture (`rm_player_update`), and the crash / end-of-race tally — HUD phase 8's timer decay + `draw_crash_fx`'s STATE side — as `rm_crash_fx_update` (`src/events.c`). A leg now **ENDS**: the tally arms `abort_flag` (0xffff game-over / 0x33 bonus-exhausted, decaying negative), which the frame loop reads as the leg end. Differential-pinned by `test/test_crash_fx.py` (every branch) and organically by `test/test_leg_drive.py`'s idle-to-time-out drives. **Slice 2 wired the tally on-target**, and the **leg START is now native too** (`rm_init_leg`, above): `game_main.c`'s `start_leg` resets every per-leg owner struct through `rm_init_leg` and derives the views, at boot, on the leg-select fire AND the attract Phase-B warm-up — no baked leg-start state remains. Proven on the 68000 by the idle leg-end autodrive trace (arm 0x59 → negative → `abort_flag` 0xffff → restart through `start_leg`, clean). **The sound TRIGGERS are now wired (slice 2, see the sound rows below)** — §1's marker gate + engine-sound enable + §7 engfreq (`rm_player_update`), every event handler's play_event_tune / handle_marker / stop_music, the crash-drain stop_music_chk, and the flow's EGOFF / jingles / TURNOFF all drive the ctx/shell `SoundDriver`, compared against recreate (SND_STATE + voices + the VBL enable + cur_tune + the Dosound ledger) in the leg / dispatch / crash / §I drives. **Slice 3 made it AUDIBLE (DONE)** — the game now ships WITH sound: (a) a 50 Hz VBL pump (`game_main.c` `vbl_sound`, spliced into `_vblqueue[0]` preserving the TOS entries via a brief `Supexec`) writes `rm_refresh`'s YM2149 stream to the chip whenever the driver is RUNNING, and `rm_dosound` is the real XBIOS Dosound over the baked `SND_DOSOUND` blob (`sound_dosound.h`); (b) the terminal `wait_music_off` op is now the real Vsync + `rm_sound_music_on` spin (breaks on a fresh key) + the Crawio key-drain; (c) the leg-start "3-2-1-GO" countdown (`race_start_countdown`) fires `stop_music(BEEP)` ×3 + `stop_music(GO)` with the original's Vsync pacing (`main` @0x10226). VBL reentrancy is handled by `RM_SOUND_LOCK`/`UNLOCK` (a nesting counter the pump respects; no-ops on the host build so the differential is unchanged). **Proof:** Hatari `--trace psg_write` on the `GAME_FLOW_AUTO` build shows the documented signatures — countdown = `reg 13 = 0x00` ×4 (ROM/Dosound, once per leg start), engine idle = `reg 13 = 0x0e` repeating (ROM/Dosound), and full reg 0–0xc activity from the REFRESH pump (music); `run_golden.py` still MATCHes all 5 legs and the `GAME_FLOW_AUTO` flow trace still closes at **19 records** (the countdown adds frames, no tags). **The record-driven mode-2/4/6 palette / screen-offset events (course_advance's tail) are now ported + wired** (`rm_course_mode_event`, `src/events.c`): when a course record is pulled, its control word (ring row 0's marker high byte `& 6`) selects mode 2 (advance `scroll_frame` → re-pick `screen_offset`, a compared render surface), mode 4 (advance `palette_cursor` → stage the palette record + `obj_shade`), or mode 6 (per-register tunnel colour poke, flipping `palette_toggle`). `scroll_frame` / `palette_cursor` / `palette_toggle` are new `EventState` fields; the actual palette WRITE (Setpalette for mode 4 / `Setcolor` for mode 6, the register byte-address folded to an index in `game_main.c`) is an off-image seam the shell owns, its content documented but structure/count pinned. Differentially pinned by the leg drives (mode 4/6 fire organically on legs 0/1/4; mode 2 by directed drives on legs 3/4 — `test_course_mode_event_matches_recreate`) + `test_init_leg`'s staged-palette surface; mutation-verified (a dropped screen_offset write, an un-advanced cursor, an un-flipped toggle, an unstaged record, a wrong obj_shade bias each fail a test). Mode 2's re-prebuilt scroll PIXELS (the shell re-runs `rm_scroll_prebuild` from the moved `screen_offset`) are pinned byte-exact too, not just the scalar — `test_mode2_scroll_prebuild_matches_recreate` drives to a mode-2 event then compares the re-prebuilt+blitted framebuffer vs recreate's `g_blit_road_scroll` (mutation: prebuild from the pre-event offset → caught). The intermission / results / highscore flow AROUND `init_leg` is ported host-side (**slice B**) and, **since slice C, composed on-target**: `game_main.c` is the whole game shell — `run_leg_select` (init_playfield) → `start_leg` (rm_init_leg) → the race loop → on the leg end `rm_update_highscore` → `rm_flow_game_over_enter` → `run_intermission` (the attract A→B→C→D cycle) → `rm_flow_game_over_exit` → back to the leg select. The leg-restart stand-in is **gone**; a `Shell` handle owns the composition. The shipping **BUGGYBOY.PRG** boots into the LEG SELECT first, exactly as the original game does — no boot fast path. The frame-0 golden harness (`run_golden.py`) builds a SEPARATE variant with `-DGOLDEN_BOOT_LEG=N` that DOES take the fast path (skip the leg select, start leg N, dump frame 0) so it can pin the boot frame; the `#ifdef BOOT_FAST_LEG` block compiles ONLY under `GOLDEN_BOOT_LEG` / `GAME_AUTODRIVE`. So the shipping cold-boot leg-select branch (that `#ifdef`'s `#else`) is exercised ONLY by the manual `GAME_FLOW_AUTO` flow-trace recipe — `make test` builds no `.PRG`, and `run_golden.py` compiles the `BOOT_FAST_LEG` branch. The leg-select fire can start any leg (`bind_leg` recomputes the per-leg stream/mask at runtime). Proven on the 68000 by the flow-trace run (leg select → fire → leg → time-out → highscore + intermission A→B→C→D → return to the leg select — the loop closes; PORTING "flow phase trace"). `run_golden.py` **MATCH**es on **all five legs 0–4** (each leg's frame-0 golden; the per-leg golden deferral is closed — the harness loops the legs, one golden per leg). Seams the shell documents: **sound (the trigger STATE is wired + verified host-side; only the audible pump — the VBL `rm_refresh` + XBIOS Dosound — is now WIRED (slice 3), so the game plays sound on target)**, Vsync cadence, per-phase palettes (off-image); `init_scoretable`'s output is a baked seed (`fixture_highscore`) copied into RAM at boot. **The attract demo's input is NOT a seam** — scouted 2026-07-23: the original does NOT replay a recorded ghost. It runs the demo with `game_over_flag != 0` (main @0x10100:314 and init_playfield:3946 both bracket `intermission()` with `game_over_flag++`/`= 0`; `init_leg` preserves the flag — its clear starts at 0x18c42, `game_over_flag` at 0x18c34 is below the range), and `game_update` forces the player input to a constant throttle in that state (`uVar11 = input_state & 0xff8f; if (game_over_flag != 0) uVar11 = 1`). Phase C feeds `ATTRACT_DEMO_INPUT = RM_IN_ACCEL` — the identical constant `0x01`. Slice 2 made the demo's game_over FAITHFUL: `op_start_demo_leg` RAISES the demo player's `game_over` (both mirrors — the physics' `p->game_over` and the event ctx's `game_over`) right after `start_leg`, exactly as the original brackets the intermission with `game_over_flag != 0`. So the demo now drives on accel via the §6 forcing (`rm_player_update` reproduces `if (p->game_over) in = RM_IN_ACCEL`) AND runs SILENT with its scoring suppressed — every sound trigger bails on game_over and §1 goes to EGOFF (no EG, no idle Dosound, no INITFX on a demo crash), and `rm_score_add` early-returns. Pinned host-side by `test_leg_drive.py::test_attract_demo_is_silent` (game_over staged both sides → the drive stays strictly compared and both Dosound ledgers stay empty; a re-zeroed demo game_over diverges it). The constant is still fed to `game_update_step` (belt-and-suspenders; §2 zeroes the raw input and §6 forces accel anyway). **The interactive high-score name-entry tail is now ported + wired** (slice F): a leg-end score that makes the table runs the initials screen, one that misses runs the short game-over screen, then the intermission. **The between-legs sub-draws are now ported + wired** (see the slice-E row): the leg-name menu (`rm_draw_panel5` + `rm_draw_divider`) draws over the leg-select / get-ready screens, `rm_draw_leg_labels` paints each leg's place-name labels onto the dashboard in Phase B + the fire-start, and the fire-start runs the real `ip_start_leg` "get ready" (results + menu ×2, then the 121-frame `leg_start_palette` flash — an off-image palette animation) | — |
| REFRESH sound driver **core** (slice 1) | `g_REFRESH` @0x1b086 + `g_INITTUNE`/`g_INITFX`/`g_TURNOFF`/`g_EGOFF` (recreate sound.c) | ✅ ported (`src/sound.c`, `include/sound.h` — a native `SoundState` owner struct; `rm_refresh`/`rm_inittune`/`rm_initfx`/`rm_turnoff`/`rm_egoff`/`rm_sound_reset`). The driver owns its state instead of the flat image and reads the const tables + tune note streams from a baked blob (`render/atari/build/sound_data.h` `SND_CONST`, generated by `render/atari/gen_sound_fixture.py` from the real image into the shared fixture home; the five TOS Dosound lists baked as `SND_DOSOUND` into the separate `render/atari/build/sound_dosound.h` for slices 2/3). REFRESH keeps recreate's exact seam — it touches no hardware, it appends the frame's YM2149 (reg,val) writes to caller buffers and returns the count | `test/test_sound_rm.py` — differential vs recreate's verified cores (byte-exact vs the 68000): **every valid tune id (0–10) and fx id (0–9)**, INITTUNE/INITFX seed then REFRESH stepped frame-by-frame (300 frames/tune — loop-point + end-tune reached), comparing **both the PSG stream AND the whole driver state** each frame (SoundState's byte layout is kept identical to SND_STATE / SND_VOICE_CTRL, so the state compares directly). Also the engine-EG path (EGFLAG + engfreq sweep) alone + over music, TURNOFF/EGOFF mid-tune, and fx-over-music. Mutation-verified (a perturbed `SND_CONST` stream byte and a tempo-reload off-by-one each diverge). ~0.5 s. **Core only** — the triggers/wiring (play_event_tune, handle_marker, stop_music) are slice 2 (below); the on-target VBL pump is slice 3 (DONE) | `test/test_sound_rm.py` |
| sound **triggers + wiring** (slice 2) | `g_play_event_tune`/`g_handle_marker` (recreate events.c) + `g_stop_music`/`g_stop_music_chk` (sound.c) + game_update §1 engine-sound + the flow jingles/EGOFF | ✅ ported + wired (`src/sound_trig.c`; `SoundDriver` = the slice-1 `SoundState` + the two trigger-owned globals — the VBL enable @0x18c0c and cur_tune_id @0x18cfa — appended AFTER the byte-compared state so the slice-1 compare is untouched). The trigger layer (`rm_play_event_tune`/`rm_handle_marker`/`rm_stop_music`/`rm_stop_music_chk`/`rm_sound_engine_update`/`rm_dosound` ledger/`rm_sound_music_on` query) drives the slice-1 REFRESH cores; the game-over guard is threaded as a parameter. **Wired at every skip site**: `src/events.c` (all handler tunes/markers + the §I checkpoint/leg-end/collision jingles + disp_finish stop_music + the crash-drain stop_music_chk), `src/player.c` (§1 marker gate → handle_marker, the engine-sound enable block, §6 terminal VBL restore, §7 engfreq into the driver), `src/flow.c` (update_highscore EGOFF, the name-entry rank-1/other jingle + terminal TURNOFF, the game-over jingle, the get-ready tune). The Dosound seam is a resettable host ledger (mirrors recreate's `g_dosound_log`); the terminal mzflag/tune-end WAITS are now the slice-3 `wait_music_off` shell op (`rm_sound_music_on` is what the shell polls). `game_main.c` holds the shell `SoundDriver` and threads it through the flow calls (compiles on the m68k target; the VBL/XBIOS pump is slice 3, now DONE) | `test/test_sound_trig.py` — the trigger leaves vs recreate's `g_*` over the full GUARD MATRIX the drives can't reach (game-over, the priority tune, handle_marker's cur_tune<7 guard, stop_music_chk's mzflag bail) + the Dosound ledger's SENSITIVITY (a wrong list id diverges the ledger though the image is identical); `test_python_constants_match_the_c` pins the hand-copied layout/addresses/tune ids to sound.h + recreate's addrs.h/events.c/game_update.c/highscore.c. **Compared as a live surface in the drives**: `test/test_leg_drive.py` + `test_flag_capture.py` + `compare_game_flow` diff the SND_STATE header + voices + VBL enable + cur_tune + the ordered Dosound ledger every frame (idle drives log Dosound(idle) each frame; flag captures fire tune 7/6; crashes fire handle_marker/INITFX; the leg-end tally fires stop_music_chk(crash)); `test/test_events.py` diffs sound over the whole dispatch fuzz + the directed §I jingles (tune 5/1/6 — the fuzz-unreached sites the recreate SOUND_VERIFY_HANDOFF called out, now diff-verified); `test/test_crash_fx.py` diffs the crash-drain Dosound. Mutation-verified by hand: a wrong §I tune id (5→4) fails `test_section_i_directed`, a wrong idle Dosound list fails the leg-end ledger diff, and dropping the play_event_tune priority guard fails `test_play_event_tune` | `test/test_sound_trig.py` |
| sound **on-target pump** (slice 3) | the 50 Hz VBL `REFRESH` pump + real XBIOS `Dosound` + the leg-start countdown (recreate `game_main.c` / original `main` @0x101b8 install + @0x10226 countdown) | ✅ done — the game ships WITH sound. `render/atari/game_main.c` adds `vbl_sound` (spliced into `_vblqueue[0]` via a brief `Supexec`, PRESERVING the displaced TOS entries so TOS's per-VBL Dosound stepper keeps running) which writes `rm_refresh`'s YM2149 (reg,val) stream to the PSG whenever `snd.vbl_enable == RM_VBL_RUNNING` and no trigger mutation is in flight; `rm_dosound` becomes the real `Dosound(SND_DOSOUND + off)` over the baked blob (`sound_dosound.h`, split out of `sound_data.h`), replacing `sound_trig.c`'s host ledger under `-DRM_SOUND_TARGET`; `race_start_countdown` fires `stop_music(BEEP)` ×3 + `stop_music(GO)` with the original's Vsync pacing; `op_wait_music_off` is the real jingle-end spin + Crawio key-drain; conterm cleared at install (the TOS key-click). The shell stays USER mode (the install/conterm/PSG touch supervisor only via the VBL interrupt + the one `Supexec`), so the golden/flow GEMDOS dumps are unaffected. **VBL reentrancy**: `RM_SOUND_LOCK`/`RM_SOUND_UNLOCK` (sound.h) bracket each `sound_trig.c` leaf's SoundState mutation; on target they are a nesting counter (`snd_lock_depth`) the pump skips a frame on, no-ops on the host/bench builds (differential unchanged). **Proof:** `make test` 690 green; `run_golden.py` MATCH all 5 legs; Hatari `--trace psg_write` on the `GAME_FLOW_AUTO` build shows countdown `reg 13 = 0x00` ×4 (Dosound, per leg start), engine idle `reg 13 = 0x0e` repeating (Dosound), regs 0–0xc from the REFRESH pump (music); the `GAME_FLOW_AUTO` flow trace still closes at 19 records (countdown adds frames, no tags). **Honest scope (cf. the joystick row):** the `psg_write` trace proves only that the RIGHT registers get the RIGHT values — the (reg,val) stream `rm_refresh` returns is byte-verified host-side and reaches the chip. Audio QUALITY — timbre / pitch / tempo as it actually SOUNDS — is verified only BY EAR on real hardware or a sound-enabled Hatari, and that listening pass is deferred (no differential can hear the YM2149). The terminal `wait_music_off` skippable/not-skippable split is pinned by `test_name_entry.py` but the audible skip itself is a manual, stick-in-hand check | on-target only (`make test` never builds the shell); pinned by `run_golden.py` + the manual `psg_write` trace |

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

- **Controls are now IDENTICAL to the original arcade port** (2026-07-23). The shell's earlier invented
  bindings are gone: `Esc`/`Q` no longer quit, and the `R`-restart key is removed. The original scheme
  (read from the decomp): **ESC** during a race aborts the leg back to the intermission — `main
  @0x10100:286` `cmpi.b #$1b,d0 / beq $1e6` breaks the race loop straight into `update_highscore` →
  `intermission` → the leg select (score ranked, no bonus tally); **G** (scancode `0x22`, `0x296 not.w`)
  toggles `dsp_toggle` (hide/show the dashboard variant); **F1..F5** select+start a leg in the leg select
  (`init_playfield`'s function-key menu); arrows/space + the port-1 joystick drive, as before. The
  original is a coin-op whose `main` is an infinite loop — it has **no** quit and **no** restart key. The
  **single deliberate deviation** is **Q = quit to the desktop** (a GEMDOS `.PRG` needs a way back that a
  coin-op does not; Q is a key the original never reads); `quit_requested()` is Q-only, and a stray leg-
  select ESC is drained at race entry so it never aborts frame 0. This is a `game_main.c` shell change
  (`make test` never compiles it): the ESC-abort merges into the natural-leg-end path the `GAME_FLOW_AUTO`
  trace already exercises, so it is pinned by the decomp quote + that trace (**unchanged at 19 records** —
  the auto keyboard is dead, so ESC/G/Q never fire and the leg ends via time-out) + `run_golden.py`
  **MATCH** (frame 0 dumps before the keyboard is taken). See PORTING "Controls are now identical".

- **The three remaining `ip_menu` / `main` keyboard features are now implemented** (2026-07-24): the
  leg-select **F6 results-screen preview** and **F10 + Return graphics/score reload**, and the race
  **Help-key pause**. F6/F10 belong in the FLOW so `make test` pins them: `rm_flow_leg_select`
  (`src/flow.c`) grew a `flow_fkey_menu` mirroring recreate's `ip_menu` (intermission.c @0x2b24) — F6
  (@0x2b86) sets `results_mode = 0`, draws the race-end results screen under the RESULTS palette,
  delegates the F6-release + fresh-key busy-wait to a new **shell op** (`preview_wait`), redraws the
  leg-select screen and skips that frame's default redraw (→ the nav tail); F10 (@0x2b36) draws the
  reload prompt (`draw_panel3`), takes a **blocking** confirm op (`reload_confirm`, returning an
  op-provided **code** — `RM_FKEY_RETURN` / another F-key code — not a raw scancode), and on RETURN draws
  `draw_panel2` ×2 + a shell **reload op** (`reload_assets`), else falls through to the F-key test (so F10
  then F3 starts leg 2). The `fkey_leg` seam's contract is extended to `RM_FKEY_*` codes, which — with the
  shared leg count `IP_LEG_COUNT` — now live in **`include/flow.h`** as the one source of truth (F6 =
  `IP_LEG_COUNT`, F10 = +1, RETURN = +2, laid out above the leg range so a pick and a debug key can't
  collide); `game_main.c` / `flow.c` / `adapter.py` all read it, pinned by
  `test_game_fixture::test_fkey_codes_match_the_header`. New draws `rm_draw_panel3` / `rm_draw_panel2`
  (`src/results.c`) mirror `rm_draw_panel5` (recreate `g_draw_panel3` / `g_draw_panel2`), fed the
  `panel3_str` / `panel2_str` program-data strings (`OBJ_LOW_PANEL3_STR` / `_PANEL2_STR`, both already
  inside `fixture_obj_low`) and now **byte-exact pixel-pinned** vs recreate (`test_flow::test_reload_panels_match`).
  The FLOW is pinned by `test/test_flow_machine.py::test_flow_driver_leg_select_f6_preview` / `_f10_reload` /
  `_f10_declined_falls_through_to_fkey`, each locksteped vs the extended oracle mirror (`_mirror_fkey_menu`
  / `_mirror_preview`); the per-frame dash rebuild is recorded BEFORE the menu (matching intermission.c:504's
  `g_init_leg_dash` before `ip_menu`) so the F10/F6 overlays composite over a fresh dash, and a confirmed
  reload re-arms the only-on-change rebuild (`FLOW_MENU_RELOAD`) for the live selection. The **Help-key
  pause** (SCAN_HELP 0x62, main @0x10100:293) is **shell-only** in `game_main.c`'s race-loop poll
  (`pause_race` — `make test` never compiles it): it silences the driver via a new `rm_pause_silence` trigger
  (`src/sound_trig.c` — TURNOFF + EGOFF + `fxflag = 0`, `RM_SOUND_LOCK`-bracketed, KEEPING the VBL pump
  RUNNING so it plays silence rather than parking), waits — via a shared `wait_key_release_then_fresh`
  helper, also used by the F6 preview — for the Help auto-repeat to end then any fresh key, captures a
  Q-to-resume into `s->quit` (so a quit during the pause isn't swallowed), then drains the resume key so it
  can't leak into the race loop's edge-triggered keys (ESC/G/Help/Q; steering reads `key_down` levels, not
  latches). The silence is now **partially tested**: `test_sound_trig::test_pause_silence` (+ `_lock_balanced`)
  pins mzflag/music/fx/EG cleared, the pump left RUNNING, and the lock bracket balanced — the surrounding
  `pause_race` busy-wait stays shell-only. `op_reload_confirm` drains stale latches but PRESERVES a
  RETURN/F-key **typed ahead** during the prompt draw, so the fast F10+RETURN chord isn't lost;
  `op_reload_assets` **bails** on a failed `load_graphics` (a truncated read has clobbered the arena — it
  sets `s->quit`, which `op_quit_requested` honours, so the flow unwinds to main's restore + exit rather
  than rendering on). On-target: `make prg` (build_game.sh) compiles clean and `run_golden.py` leg 0 still
  **MATCH**es (frame 0 is unaffected). **One deviation**: F10's `xbios_setscreen` is subsumed by the shell's
  own double-buffer flip (there is no separate screen re-establish); noted at `op_reload_assets`. `make
  test` = **700 passed**.

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

- **The flag-sequence HUD fan-out gap (capturing a flag looked like it did nothing) is fixed + host-
  tested.** The flag STATE path was correct all along — the §H horizon dispatch fires a `flag_gate`
  event (jump-table idx 1-12) whose flag colour is the fx-overlay byte at `fx[horizon_row+1/+3]`, the
  order-match reads `flag_seq_table[flag_seq_off + flag_seq_count]`, the score is added and the
  object's `obj_active` byte cleared — and the leg drives already tracked it wherever a flag fired
  (leg 3 captures one by frame ~129, all compared strictly). But the SHELL never fanned the three
  fields `GobjPrefixState` OWNS into the per-frame `HudState` the draw reads: `flag_seq_count`
  (phase-4 bars), `flag_seq_off` + `dsp_color_scroll` (phase-5 colour cursor). `rm_apply_player` fans
  the physics + `EventState` scalars but has no `gobj` param, so the flag-sequence bars **never drew** —
  the capture was invisible (the score ticks every wrap frame from the distance award, so only the bars
  are the flag's feedback). Same class as the draw-struct fan-out bug above: a shell view field with no
  host test, invisible to the golden (frame 0, `flag_seq_count == 0`) and to the leg drives (they
  compare the raw `gobj` state, not the HUD render). Fixed by `rm_gobj_hud_view` (`src/gameplay.c`), a
  fan the shell's `draw_frame` runs **after `rm_gobj_prefix`, before `rm_draw_hud`** — the original's
  `g_draw_game_objects`-then-`g_draw_hud` order, so it reads the post-prefix values (it can't fold into
  `rm_apply_player`, which runs before the prefix). Pinned by `test/test_flag_capture.py`:
  `test_hud_flag_bars_are_fanned_in` renders the HUD from a HudState whose flag fields come ONLY from
  the fan (zeroed first) and matches recreate's `g_draw_hud` byte-exact (dropping the fan makes the bars
  vanish — mutation-verified); `test_directed_flag_capture_drive` captures flags in order on a leg-2
  drive, strict per-frame vs the oracle, asserting a capture happened on BOTH sides; and
  `test_flag_gate_branches_match_recreate` stages `flag_seq_count` at the window boundaries to reach the
  branches the dispatch fuzz (which only sees `flag_seq_count == 0`) never does — the 5-in-a-row bonus
  (seq 4→5 arms `bonus_timer` 0x3c), the wrap past the window (seq ≥5 →1), the `bonus_timer`
  forced-match, and the out-of-order miss — each compared to recreate and asserted non-vacuous.
  Mutation-verified (drop the fan; invert the order-match; drop the `obj_active` consumption — each
  fails a test). On-target: `run_golden.py` MATCH (frame 0 fans 0→0) and the `GAME_FLOW_AUTO` trace
  unchanged at 19 records (an additive draw-time HUD fan, no flow tags).

- **The COMPOSED-FRAME differential is the new backstop for both fan-out classes above (and any
  future one).** Both bugs shipped GREEN because the scalar coverage model has a structural hole: the
  leg drive verifies every STATE transition differentially and every DRAW STAGE byte-exact, but with
  the draw inputs staged FROM the reference image — it never runs the shell's actual per-frame
  COMPOSITION (state → the `rm_apply_player`/`rm_gobj_hud_view` fan-outs → the `draw_frame` stage
  sequence) end-to-end, so a missing wire BETWEEN two individually-verified pieces is invisible. Closed
  by hoisting the composition into **`rm_draw_frame` (`src/frame.c`)** — the shell's `draw_frame` and
  the shell now calls ONE composition (the bench deliberately mirrors it) (the shell keeps only buffer selection + `Setscreen`) — and by the
  composed-frame differential in **`test/test_composed_frame.py`**: on sampled frames of each drive the
  candidate runs its OWN full composition (`rm_apply_player` → `rm_draw_frame`, from its live owned
  state, via `equiv._ComposedScene`) into its own framebuffer while the reference runs recreate's
  `g_draw_frame` on the image, and the two framebuffers are **byte-compared, strict (no persistent-diff
  allowlist)**. **Sampling rule** (a full frame pair is ~1.7 ms host-side, too much for every frame of
  every 600-frame drive): compose on every EVENT frame (a view-wrap, a crash arm, or a leg-end frame —
  where fan/composition wiring bugs bite) PLUS every 15th frame. **Drives**: a free flat-out per leg
  0–4 (crashes fire on every leg → the crash-script `anim_frame`/spin fan is exercised on real crash
  frames), plus directed slalom (leg 2/4), a flag capture (leg 2 → the flag-sequence HUD fan), and the
  bonus-clock time-out that ends a leg (legs 0/1). **Mutation-verified** — re-introducing each escaped
  class fails a composed drive: dropping the `anim_frame` fan (28 diffs on crash frames), dropping
  `rm_gobj_hud_view` (111 of 127 composed frames diff on the flag-capture drive), dropping a stage (the fg sprite, 482
  diffs), and swapping two ordered stages (fg sprite vs ground, 17 diffs). It found **no** pre-existing
  divergence: the composed frame is byte-identical to `g_draw_frame` across all five legs and every
  sampled crash frame, so the shell's composition — including the `objlist.bonus_timer`/`p24_flag` that
  `start_leg` seeds once and never refreshes — is faithful on this game's data. Suite cost: +10 tests,
  suite time unchanged (~15 s under `-n auto`; each drive is its own xdist work unit). On-target
  unaffected: `run_golden.py` MATCH on all 5 legs (the hoist is byte-preserving) and the `GAME_FLOW_AUTO`
  trace unchanged at 19 records.

### Play-test bugs — four SHELL-BINDING defects, fixed (2026-07-24)

A play-test reported two visible faults ("no animation when the buggy kicks a roadside object"; "a
black box for the character during high-score name entry"). Both traced to the same class, and the
sweep for that class found two more. **None was in `src/`** — every ported core is still byte-exact.
They were all in the layer `make test` does not compile (`render/atari/game_main.c`) or in the fixture
windows it consumes, where the harness builds its own bindings instead of the shell's. The lesson and
the generalised rules are written up in `PORTING.md` ("The shell-binding trap").

| # | Defect | Effect in the game | Fix | Pinned by |
|---|--------|--------------------|-----|-----------|
| 1 | `GobjPrefixAssets.marker_recs` bound to a private BSS block, while the object dispatcher reads `ring_st`. In the original both are the one grid at `A_obj_markers` (decay base = grid − 8) | The marker-decay animation (idx 30/60: a kicked roadside object flying away — the prefix walks a `0xff` through the grid one band nearer per frame, which the dispatcher's SPECIAL pass draws) wrote to a dead buffer. The object still vanished and still scored, so it read as "the animation is missing" | `ring_st` is now a padded block (`RM_RING_DECAY_BIAS` below, `RM_RING_DECAY_SPILL` above, both in `game.h`) and the prefix gets the biased base | **Reading + the on-target run only** — the binding lives in `game_main.c`, which `make test` does not compile. Honestly unpinned host-side; harness gap #1 |
| 2 | `FONT_BYTES = 0x600` ("all the gauge string uses"), one glyph short of `'`'` (0x60), the name-entry delete sentinel | On target the blitter read the array declared after `fixture_font` as glyph pixels; an all-zero `(mask, ink)` row *replaces* the cell with colour 0 — a black box mid-name-entry. Invisible host-side, where the tests hand the C code a slice of the live image and the bytes past the window are the real font | One derived `FONT_BYTES = (FONT_MAX_GLYPH + 1) * FONT_GLYPH_STRIDE`; the duplicate `FONT_GLYPH_BYTES` is gone | `test_game_fixture::test_font_window_covers_the_name_entry_character_range` (bound derived from `flow.c`'s `HS_CHAR_DEL`, stride cross-checked against `text.h`, shipped fixture length checked) + `test_text` now fuzzes up to the top glyph. Mutation-verified |
| 3 | `objlist.bonus_timer` / `p24_flag` derived once in `start_leg`; the original's dispatcher reloads both every frame | The 5-flag bonus window never clamped a low object type (the roadside scenery never changed for the window), and the p24 gate never re-read the score digit §I bumps at each checkpoint | Both refreshed in `rm_draw_frame`, where the original reads them; `start_leg` derives neither | `test_composed_frame::test_composed_bonus_window_clamps_low_object_types` (directed — no free drive opens the window; seeds it into the leg-start image so both sides open it). Mutation-verified: freezing either fails. **Two limits:** the seeded window never CLOSES during the drive (only the prefix decrements it, and the compose that runs the prefix is discarded on both sides — measured: still `0x3c` at frame 90), so this pins the clamp-open path only; and `p24_flag` is pinned against *not reading it*, not against a stale-but-plausible value, which needs a checkpoint no composed drive reaches |
| 4 | The `rev_reload` poke (§1 engine idle, §6 script rpm override) was skipped, justified as "it aliases `lean_frame`, which no compared surface reads" — false: `draw_buggy_hi` reads `lean_frame` every frame | `0x18d12` is ONE word under two names, so in the original every rpm override restarts the lean-overlay animation. The port let it free-run | `PlayerState.lean_frame_reload` (per-frame out-field) → `rm_apply_player` → `SpriteState.lean_frame`, conditional because that field is in/out | `test_player::test_rev_reload_poke_restarts_the_lean_overlay` — **both** poke sites × legs 0/1/4 (§6 reached by arming the crash script on `crash_anim_tbl + 0x90`, whose rpm byte is non-negative). Nothing else can see it: the composed differential re-seeds the sprite's draw-internal cursors from the reference by design. Mutation-verified per site: dropping either raise reddens only its own cases, and dropping the fan passed the whole suite before this test existed |

**Harness gap #1 closed (2026-07-24).** #1's binding lived in `game_main.c`, which `make test` does not
compile, so it shipped pinned only by reading. Rather than compile the shell host-side, the *opportunity
to disagree* was removed: the aliasing geometry (`RM_RING_DECAY_BIAS`, `RM_RING_ST_BLOCK_BYTES`,
`rm_ring_decay_base()`) moved into `include/game.h`, and `equiv._ComposedScene` — which had been binding
`marker_recs` into the image while its own dispatcher read a private `ring_st`, independently
reproducing the shell's bug — now allocates the same padded block. Pinned by
`test_composed_frame::test_marker_decay_writes_reach_the_dispatcher_grid` (direct: the decay's walked
marker must land in the grid the dispatcher reads; mutation-verified against any other arena) plus a
directed armed-decay drive, since no free drive kicks an object.

**That immediately exposed a divergence, asserted as an exact count.** With the arenas correctly aliased
the composed frame still differs from recreate on **2 of 27** sampled frames of the decay drive (263
bytes each, both early cadence samples before the first course advance). Not a regression from the
binding fix — it is what the fix made visible: bound separately the same drive diverged on **25 of 27**,
i.e. the old harness was noise, not signal. The decay's grid write itself is verified correct (the
walked `0xff` reaches the right band, high byte, through the pointer the dispatcher is given), so the
difference is downstream of it.

**Suspect REFUTED, and the effect localised (2026-07-25).** The proposed cause — `_ComposedScene.draw`
re-serializing the grid every frame where the shell only does so on a course advance — is not it:
gating the store on the wrap flag leaves the divergence at exactly 2 of 27. What a `marker_off` sweep
shows instead (frame 0, leg 0, whole-framebuffer diff vs `g_draw_frame`):

| `marker_off` | grid offset | diff | rows |
|---|---|---|---|
| none armed | — | **0** | — |
| `0x00` | the LOW PAD, below row 0 | 109 | 118–136 |
| `0x08` | row 0 byte 0 | 0 | — |
| `0x10` | row 0 byte 8 | 263 | 143–167 |
| `0x14` | row 0 byte 0xc | 528 | 143–167 |
| `0x20` | row 0 byte 0x18 | 0 | — |
| `0x2c` | row 1 byte 4 | 0 | — |

Two things follow. **The `0x00` row is residual #2, confirmed empirically**: that offset is the low pad,
which is `RoadPose.seg_data[12]` in the original — the reference zeroes a far road-slope byte and the
port writes into inert pad, and the road geometry visibly moves (rows 118–136 is the horizon band).
**The rest is still unexplained**: for `0x10` the decay writes stay entirely inside the grid, and the
candidate's and the reference's grids are BYTE-IDENTICAL after both prefixes have run (verified), yet
263 framebuffer bytes differ. So the cause is downstream of the flag bytes the dispatcher reads, and it
is offset-dependent — the next step is to bisect the draw stages on a diverging offset rather than
theorise. The test seeds `0x10`, i.e. one of the diverging cases, deliberately.

It is asserted as `stats["composed_diffs"] == DECAY_KNOWN_DIFFS`, **not** marked `xfail`: a binary xfail
cannot distinguish "still failing for the documented reason" from "failing because someone unbound the
arenas" — under the bias mutation that drive goes to 27 of 27 and an xfail would stay green (verified).

**Harness gap #2 closed (2026-07-24) — the on-target build is a test gate.** `make test` compiled the
game shell for nobody: `render/atari/game_main.c` is in neither the host `.so` nor `bench.elf`, and four
`src/` files (`frame`/`flow`/`intermission`/`results`) are host-compiled but never cross-compiled. A
commit landing `game_main.c` without its header half therefore left the m68k build broken **on origin**
with the suite green — twice in one session. `make test` now depends on a full cross-compile + link +
`.PRG` wrap in BOTH variants (stock ST and `GAME_STE=1`, which selects different sources), ~4 s on top of
a ~21 s suite; the m68k toolchain was already a hard prerequisite via `bench.elf`. Both go through
`build_game.sh` so the cross flags are never restated. `make golden` promotes the Hatari end-to-end
(5 legs, ~20 s) to a named target for pre-promotion runs. Mutation-verified: a typo'd constant in
`game_main.c` now fails `make test` at the build step. It catches "does not compile / does not link" —
NOT the binding class above, which stays the job of hoisting bindings into shared code.

**Binding hoist (the L3 job gap #2 does NOT cover).** `rm_bind_gobj_prefix_assets` (`src/gameplay.c`)
now owns every alias in the prefix bundle — decay arena → the dispatcher's grid, animated colour → the
HUD fuel mask, the two `buf_a` mirrors — and BOTH the shell and `equiv._ComposedScene` call it, so the
harness executes the shell's own binding code rather than a re-implementation of it. Mutation-verified:
dropping the bias inside the binder fails four tests. The remaining bundles (`HudAssets` especially)
carry their offsets in the generated `game_fixture.h`, so hoisting them needs that generator split into
defines vs arrays first — see `PORTING.md`, "Binding hoists".

**Residuals on #1, recorded rather than fixed blind** (both found by the pre-commit review, neither a
regression — before the fix the decay wrote nowhere at all):

- **The clears do not persist past the animation.** `ring_st` is a *derived* mirror: `ring_views_refresh`
  re-runs `rm_ring_store_st` from the authoritative `CourseRing` on every course advance, and the decay
  never touches the ring. During the animation this is invisible (the prefix re-applies the full clear
  every frame, after the re-serialize and before the object passes), but once the decay retires, the
  next advance restores the type codes the original had erased for good — the kicked scenery column
  pops back. Fixing it properly means giving the decay a home in the ring, which needs its own
  differential.
- **The low pad is not inert in the original.** `A_marker_decay_base`'s first word is
  `RoadPose.seg_data[12]` (`game.h`: `seg_data[11]/[12]` *are* `marker_slope_src` / `marker_decay_base`),
  which the port models natively. A decay armed on a `horizon_row == 0` frame therefore zeroes a far
  slope byte in the original and only pad here. Documented at the declaration in `game_main.c`.

Also noted, not folded in (out of scope): `render/atari/bench_main.c` still derives `objlist.bonus_timer`
/ `p24_flag` once at setup, so the perf bench no longer mirrors the shell's per-frame refresh and
measures the never-clamping path. Changing it moves the PERF30 baselines, so it belongs with the perf
work, not here.

Alias sweep over `recreate/include/addrs.h` (the root cause of #4 generalised): four addresses carry
two names — `0x18c58` (`obj_scan_off`/`ground_view_off`, fanned by `rm_apply_player`), `0x18d5a`
(`sprite_list_base`/`road_width_src`, documented at `game.h:142`), `0x18c7e` (a duplicate `#define`,
harmless) and `0x18d12`. Three were already handled; only `0x18d12` was broken. `names.txt` now records
the dual role at that address.

The name-entry ALPHABET is now drawn and compared (`test_flow::test_results_screen_draws_the_name_entry_alphabet`).
The results screen was already byte-compared against recreate across modes and legs — it missed the black
box purely on DATA: the default table's names are `"..."`, so `'`'` never reached the glyph blitter. Two
windows of the table's initials fields now tile `'A'..'`'`, the top one ending ON the delete sentinel.
Mutation-verified: restoring `FONT_BYTES = 0x600` reddens exactly the window that draws it (23 bytes),
leaving the other green — i.e. this test would have caught the shipped bug directly.

Suite: **727 passed** (was 708), ~21 s under `-n auto`.

### Game-mechanics coverage audit (2026-07-23)

Every in-race gameplay mechanism and its current differential reach (the playtest asked "check the game
mechanisms are all working"). "Drive" = a free-running leg drive compares it organically; "directed" =
a staged case reaches a branch the drives cannot.

| Mechanism | Reach |
|-----------|-------|
| **Flags — order match / score / consumption** | `test_flag_capture` (directed capture drive + the boundary branches: bonus/wrap/forced-match/out-of-order) + `test_events` dispatch fuzz (idx 1-12) + leg drives (organic captures) |
| **Flag HUD bars (phase 4/5) fan-out** | `test_flag_capture::test_hud_flag_bars_are_fanned_in` (the fix) + `test_hud` (the draw itself) + `test_composed_frame` (the fan wired into the whole-frame composition, on a real flag-capture drive) |
| **Football / bonus-number display (idx 41/42/63/64)** | `test_events::test_dispatch_matches_recreate` (all idx × gates × curve sign) + `test_dispatch_reaches_every_handler_kind` (non-vacuous: the record's own state change) |
| **Finish-line display (idx 61/62)** | dispatch fuzz + `test_events::test_fx_run_fills` (the 0x3d fill dispatches `disp_finish`) |
| **Marker-decay roadside pickup + score (idx 30/60)** | dispatch fuzz + `test_fx_block_slot_mapping` (dispatched from the right slot) + `test_gobj_prefix` (the decay retire) |
| **Checkpoint gate + time extension (§I)** | `test_events::test_section_i_directed` (checkpoint, leg-end at score '5', leg-0 dash rebuild, banner scroll) — the free drives reach 0 checkpoints, so this is directed-only |
| **Checkpoint counters (idx 22-24)** | dispatch fuzz (all three gates) + `test_dispatch_reaches_every_handler_kind` |
| **Score message (idx 13-21)** | dispatch fuzz (three delta groups × three gates) |
| **Time-gate suppression / bonus-clock time-out** | `test_leg_drive::test_leg_ends_on_timeout` + `_via_bonus_tally`; `test_crash_fx` (the drain order + abort arm) |
| **Crash varieties (common / rpm-band / curve-freeze / rpm-penalty collides, idx 25/27/34/35-40/43-59)** | dispatch fuzz (collision_lock gate) + leg drives ARM their own crashes (`test_crash_script_plays_out_and_returns_control`) |
| **Spin (idx 32/33 + §10 arming)** | `test_leg_drive::test_spin_arming_matches_recreate` + `_reaches_both_outcomes` (directed — the drives can't coincide an armed override with a held lock) |
| **Jumps / ramps (crash-script anim frame)** | `test_sprite` (fg frame) + `test_leg_drive::test_fanout_tracks_recreate_and_reaches_nonzero` (the anim/spin/lower-body fan-out) + `test_composed_frame` (the fan wired into the whole-frame composition, on real crash frames) |
| **Off-road push + edge clamp (§10)** | leg drives (`stats["offroad"]`/`["clamp"]` > 0) + `test_player::test_offroad_push_is_reached` |
| **Tunnel palette (mode 6) / screen-offset (mode 2) / race palette (mode 4)** | `test_leg_drive::test_course_mode_event_matches_recreate` (mode 4/6 organic, mode 2 directed) + `test_mode2_scroll_prebuild` — all three pinned |
| **Score multiplier (flag 5-in-a-row bonus window)** | `test_flag_capture` (the bonus arm) + `test_gobj_prefix` (the `flag_seq_off` advance at `bonus_timer==0x28`) |
| **Dashboard collision-probe marker walk (mini-map)** | `test_events::test_course_probe` + `_marker_walk` + `_reaches_both_outcomes` |

Honestly unpinned: `marker_unpack`'s "both shoulders" fixup (0 of 5120 records reach it — below) and the
§G 0x3e run-fill endpoint words (not differentially observable — below).

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

**Mode-2/4/6 event reachability (all three modes ARE reachable — none left unpinned).** Decoding each
leg's whole packed course stream (1024 record slots) and running `marker_unpack` on every record's
marker gives, per mode (`(unpacked_marker >> 8) & 6`):

| mode | effect                              | leg 0 | leg 1 | leg 2 | leg 3 | leg 4 |
|------|-------------------------------------|-------|-------|-------|-------|-------|
| 2    | scroll_frame → screen_offset        | 0     | 0     | 1     | 3     | 4     |
| 4    | palette stage + obj_shade           | 5     | 10    | 15    | 13    | 11    |
| 6    | tunnel per-register poke            | 5     | 14    | 6     | 6     | 9     |

The free-running leg drives (legs 0/1/4) reach modes 4 and 6 organically (read_pos advances a few
hundred bytes over 600 frames, past their earliest records at rp ≈ 0x150–0x238), and pin them frame-
for-frame. Mode 2's earliest record is deep in every leg's stream (leg 3 rp 0x550, leg 4 rp 0x420), so
the free drives never reach it; the directed `test_course_mode_event_matches_recreate` cases poke
`course_read_pos` so the first wrap pulls the chosen mode's earliest record, and pin all three there.
Mode 2 is absent from legs 0/1's data entirely — those legs simply never fire it (transcribed, and
correct by the other legs' pins), not an unpinned branch.

## Perf

`tools/bench.py` measures the game's WHOLE frame per stage on the cycle-accurate Musashi 68000 —
remaster (native structs, via the `bench_*` wrappers, staged exactly as game_main.c's frame) vs
recreate's recon (flat image) where an image-arg-only recon entry has the same scope — on the same
staged leg-0 boot frame. Build first: `bash render/atari/bench_build.sh`. `tools/profile.py <bench_sym>`
breaks any stage down to cycles-per-function (and per-PC with `--lines`) via the oracle's
cycle histogram.

Current (8 MHz ST, 160000-cycle 50 Hz frame budget) — the game frame is **148.8 ms ≈ 6.7 fps** on the
staged frame (203 ms before PERF30 A1 landed on `rm_blit_objshift`; 163.8 ms before A3 dropped the
fixed-pass engine to hand-asm; 157.6 ms after A3 phase 1, then A3 phase 2 dropped pass 1 to hand-asm
too). Caveat before reading the object rows: the staged frame is the game's BOOT frame — a
leg start, with the start gate spanning the road — which is close to the object tree's worst case
(see the frame-cost distribution below the table):

| stage | remaster ms | recon ms | rm/rec | notes |
|-------|-------------|----------|--------|-------|
| player_update + course + views + prefix | 1.64 | — | | scalar state, noise; −0.37 from the -O3 sweep |
| build_road_geometry | 3.90 | 3.91 | 1.00× | |
| render_road | 50.64 | 55.47 | 0.91× | 67% in the per-scanline core, 33% in bands B/D |
| blit_road_scroll | 12.06 | 33.55 | 0.36× | pre-rotated copies + unrolled fill |
| draw_ground | 0.88 | — | | −0.28 from -O3 |
| draw_fg_sprite | 2.06 | 2.39 | 0.86× | −0.34 from -O3 (objsprite family) |
| **objlist pass 1 (sprites)** | **19.91** | — | | ~70% inside `rm_blit_objshift`; C-level landed A1 + P1/P2 + P4a + review-fix fold + GCC-level sweep (…the per-function IRA attribute took the C function to 181,836 cyc, bench_objlist_pass1 253,564 → 231,480 = 28.93 ms; P3/L2/E2/E3 dropped; C3 pointer cursors on objsprite → 229,948 = 28.74 ms). **PERF30 A3 phase 2 (LANDED): the engine is now hand-written m68k, `src/asm/objshift.S` (ported from the ORIGINAL's `blit_objshift @0x14680`, template 110,572 cyc), selected via -DRM_ASM_BLIT → the per-core RM_ASM_OBJSHIFT (include/game.h RM_BLIT_OBJSHIFT; C stays the byte-exact reference in blit.c). `rm_blit_objshift` C 181,836 → `rm_blit_objshift_asm` 111,192 cyc (0.61×, −70,644); bench_objlist_pass1 229,948 → 159,304 (28.74 → 19.91 ms). Gap to the original is +620 across the recon's 6-call frame (movem 888 − register src-rewind claw-back ~760 `suba.l %a3,%a1` vs the original's memory-indirect `suba.w (a3),a1` + C-ABI marshalling/color_pairs indexing ~500 ≈ 628; scopes differ — the original's 110,572 is an 8-call frame incl. 2 off-edge returns ≈ +280, so on matched scope ≈ +900 ≈ the movem term). Pinned by test/test_asm_blit.py (1560-case Musashi C-vs-asm differential incl. the color_pairs table, bracketed compare + positive control, mutation-checked) + run_golden.py 5-leg MATCH** — PERF30 "A3 phase 2" |
| draw_object | 0.90 | — | | |
| objlist pass 2 | 0.05 | — | | empty on this frame |
| **objlist fixed pass** | **34.52** | — | | 96% inside the fixed-pass engine; A1 does NOT apply (value-passing REGRESSED it +1.98 ms, PERF30 A1); C-level exhausted at C1 (314,216 cyc / 39.28 ms). **PERF30 A3 phase 1 (LANDED): the engine is now hand-written m68k, `src/asm/objshift2.S` (ported from the ORIGINAL's `blit_objshift2 @0x13ed6`, template 262,940 cyc), selected on the m68k builds via -DRM_ASM_BLIT → the per-core RM_ASM_OBJSHIFT2 (include/game.h RM_BLIT_OBJSHIFT2; C stays the byte-exact reference in blit.c). `rm_blit_objshift2` C 314,216 → `rm_blit_objshift2_asm` 264,930 cyc (39.28 → 33.12 ms, 0.843×, −49,286, post-F3); bench_objlist_fixed 325,424 → 276,138 (40.68 → 34.52 ms). Gap to the original is +1,990 after F3's register-held rewinds (NOT "exactly the movem" — the earlier +6,178 decomposes as movem ~890 + a per-row suba.w regression ~2,900 that F3 fixed + marshalling/dispatch ~2,400). Pinned by test/test_asm_blit.py (1740-case Musashi C-vs-asm differential, bracketed compare + positive control, mutation-checked) + run_golden.py 5-leg MATCH** — PERF30 "A3 phase 1" |
| draw_buggy | 4.56 | 5.22 | 0.87× | −0.60 from -O3 (objsprite family) |
| draw_hud | 17.64 | 17.20 | 1.03× | 10.6 in the phases (dashboard masked blit), 6.0 in glyph_run; +0.17 under -O3 (within noise, outweighed by the objsprite wins) |
| **TOTAL (frame)** | **148.8** | | | was 203.2 before A1, 194.6 after A1, 188.0 after P1/P2, 185.6 after P4, 179.6 after the review-fix fold, 172.1 after L1, 167.8 after the GCC-level sweep, 163.8 after C1+C3, 157.6 after A3 phase 1 (objshift2 hand-asm); **A3 phase 2 (objshift hand-asm) took it to 148.8** (funcs-sum basis; 1,260,780 → 1,190,300 cyc, −70,480 = −8.81 ms); recon (recreate-parity) is ~240 ms on this frame; the ORIGINAL asm is **110 ms (9.1 fps)** — remaster is still slower than the original here, NOT faster (the ~240 ms is the recon, not the original — see PERF30.md Part 0) |

Whole-tree check: `object_tree` (prefix→buggy, recreate's `g_draw_game_objects` scope) is 62.9 ms
(was 117.2 before A1, 108.6 after A1, 102.0 after P1/P2, 99.6 after P4, 93.6 after the review-fix fold,
86.1 after L1, 82.0 after the GCC sweep, 77.9 after C1+C3, 72.3 after A3 phase 1, 71.7 after the A3
phase-1 review fixes, 62.9 after A3 phase 2 dropped pass 1 to hand-asm)
vs the recon's 130.3 ms (**0.55×**). `render_road` also beats the byte-exact **machine model**
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
  `rm_blit_objshift2` are the bulk of the gate frame's tree (~84%/97% of their passes). **PERF30 A1
  landed 2026-07-23 on `rm_blit_objshift` (pass 1 only):** its cell helpers mutated `col0/col1/sp`
  through pointers, so GCC kept the loop state in memory (~16 k cyc/pass of pure `movel %sp@(x),%sp@(y)`
  spill shuffling). Restructured to a value-in/value-out `ObjshCursor {col0,col1,sp}` struct passed by
  value through the inlined helpers → cursors register-pinned, the mem-to-mem moves GONE, **51.50 →
  42.83 ms (0.83×, −8.67 ms)**, byte-exact (`test/test_blit_engines.py` + `run_golden.py` 5-leg MATCH).
  `rm_blit_objshift2` was left by-pointer: it has no such mem-to-mem spill (its cell body walks the
  cursors in address registers) and is arithmetic/RMW-bound, so value-passing REGRESSED it +1.98 ms —
  see PERF30.md A1.
- **Do not collapse the wrap-frame's double `rm_build_road_geometry`.** On a view-wrap the game
  builds twice: once before `rm_course_events` (so `horizon_row` is fresh for the event tail), then
  again inside `draw_frame` (off the ring bands the tail pokes). Both are faithful — the original's
  own `g_draw_frame` (recreate gameplay.c:268) likewise rebuilds after the event pokes — so a future
  perf pass must not "dedupe" it: dropping either build renders stale-horizon / pre-poke geometry.
- **Where the fps can land (8 MHz ST, median frame ~180 ms recreate-parity):** dropping the memset
  puts the remaster game at ~155 ms ≈ 6.5 fps median. The full plan (blitters, road display list,
  HUD static/dynamic split, scroll fill tracking — PORTING.md "Perf plan") projects a median around
  **60–75 ms ≈ 13–17 fps**, with gate/tunnel frames at ~8–10 fps. **The ORIGINAL binary sets the
  Tier-A ceiling (measured, PERF30.md Part 0): ~12 fps median / ~9 fps gate / ~19 fps object-free** —
  so hand-asm matching the original *is* ~12 fps median (a proven ~2× over today's compiled C), and
  13–17 fps median needs the Tier-B algorithmic wins (pre-shifted sprites, road display list) that the
  original doesn't do. 30 fps is out of reach on a stock ST while staying pixel-faithful — the
  original's own 9-fps gate is 2.5–3.3× short of it.
- **The VBL sound pump (slice 3) adds a small per-frame tax.** The C `rm_refresh` runs ≈2.2–2.6× the
  cost of the original asm REFRESH per VBL, ≈2.3 ms/frame in-race and ≈4.8 ms while a tune plays — about
  1.6–3.3% of the 148.8 ms gate frame. It is admissible: a "skip refresh when the state is unchanged"
  shortcut is NOT (the original dumps ALL registers every VBL, so the chip output must too — skipping
  would diverge the psg_write trace and change what plays). `rm_refresh` is a future hand-asm candidate
  (like the objshift cores) if the tax ever matters; for now it is well under the render-stage costs.

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
