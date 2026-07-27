# PORTING.md — how to continue the remaster port

For anyone (human or agent) picking up `remaster/`. Read [`README.md`](README.md) first for the
*contract* (pixel-identical to `recreate/` per frame) and [`STATUS.md`](STATUS.md) for *what's done*.
This doc is the *how*: the recipe, the conventions, and the traps.

`draw_hud` (all 8 phases) is ported and verified on host + on a real 68000. The render pipeline is now
complete: `render_road`, `blit_road_scroll`, `build_road_geometry`, and the whole `draw_game_objects`
tree (`draw_ground`, the buggy/foreground sprites, `draw_object`, the fine-x blit engines, the
`draw_object_list` dispatcher, and the prefix/orchestrator) are all byte-exact vs `recreate/`.

Phase B has started: the **player physics** (`src/player.c`, `game_update` §3,4,5,6,7,8,9,10) is
ported and verified frame-for-frame against `g_game_update`, and `render/atari/BUGGYBOY.PRG` is a playable
buggy on the 68000. That now includes the crash / auto-steer script (§6), which replays a canned crash
out of `crash_anim_tbl` and hands the controls back, and section 12's object / marker ring — the
course window that scrolls the scenery and the road's per-band flags toward you. What remains in
`game_update` is the system that *decides* to crash you: section 12's collision probe, the fx block
rebuilt from `obj_flags`, and the horizon-event dispatch (which also carries the checkpoint and finish
events, so a leg still cannot be finished) — see STATUS.

A note on porting a *gameplay* function rather than a render one: there is no framebuffer to diff, so
the equivalence surface is the scalar state. `test/equiv.py`'s `compare_player_drive` is the pattern —
drive a scripted input, re-seed the candidate from the reference image each frame, and compare every
scalar the port owns. Two things made it honest: staging artefacts have to be cleared or the drive
degenerates (a mid-race image leaves `hud_crash_timer` armed, which pins the throttle off and the
buggy never moves), and frames where an *unported* system engages must be excluded and rolled back
explicitly, with a count reported, rather than silently tolerated.

`compare_leg_drive` is the stronger successor, and worth reaching for once a subsystem is meant to run
by itself: the candidate is seeded **once** from the leg-start image and then drives itself, so drift
accumulates instead of being erased every frame. Per-frame re-seeding hides exactly the bugs a
self-driving game has. Three traps it cost real time to find:

- **A "render output" can be a physics input across frames.** `adapter.scroll_state` zeroes
  `hscroll_step2` because it is an output of `blit_road_scroll` — but §9 adds it into the curve next
  frame, so a re-seed that dropped it to 0 put a permanent offset into `road_curve`.
- **Size an asset window from the whole region, not from the records you happened to trace.** The
  crash table's *display* records (finish/bonus) sit past `0x400`, well beyond the last crash record;
  an undersized window reads zeros, and a zero record is neither terminal nor a step, so the script
  walks forever. Bound it by the next known global instead.
- **Detect a handover on the 0 → nonzero edge, not on "the candidate looks idle".** Armings are
  incremental (a spin override can be armed on top of one already held), and an idle test also
  swallows the real bug you want to see — a script that walks wrong or quits early.

## State of play — read this first if you are picking the work up

**The between-legs LEG / GAME FLOW is now composed host-side** (flow slice B, `src/flow.c` + `FlowState`
in `include/flow.h`): the attract loop's phase-counter arithmetic (`rm_int_stepA`/`_phaseB_leg`/
`_stepD_counter`), the abort poll (`rm_check_abort`), the high-score insert (`rm_update_highscore`,
verified to recreate's prefix checkpoint — the ranking / row-shift / insert; the IKBD name-entry tail
is ported in slice F, below), and the leg-select nav (`rm_init_playfield_nav`/`_fire`). Each is differential vs
recreate's g_*, and two composed checks pin the wiring: an attract CYCLE (phases **A/B/D lockstep
against the oracle slices**; **Phase C is a boundary-count only** — a pure-Python mirror of the
0x96-frame count that cannot itself fail, guarded by the pinned `INT_C_FRAMES` constant, with the demo
pipeline pinned separately by the leg drives) and an end-to-end GAME-FLOW drive (a leg times out →
`update_highscore` → `game_over_flag`++ → intermission entry, matching main's loop-break path). The flow's LOGIC is host-side — `FlowState` is the composition's
owner, exactly as `_Candidate` owns the leg-drive structs — and the Vsync/palette/flip/sound are
off-image seams. See `test/test_flow_machine.py` and STATUS's slice-B row.

**The shell is the GAME (BUGGYBOY.PRG).** `render/atari/game_main.c` composes the original's whole
outer loop (decomp.c main @0x10100) out of the ported pieces — `run_leg_select` (init_playfield) →
`start_leg` (rm_init_leg) → the race loop → on the leg end (`abort_flag < 0`) `rm_update_highscore` →
`rm_flow_game_over_enter` → `run_intermission` (the attract A→B→C→D cycle) → `rm_flow_game_over_exit` →
back to the leg select. A `Shell` struct is the composition's on-target owner (pointers to every race
owner struct + its render views + the const asset bundles + `FlowState` + the flow's draw-asset
bundles); one handle so `game_update_step` / `start_leg` / the flow phases take one argument. The old
per-frame leg-restart stand-in is GONE — a finished leg now runs the real between-legs flow. The
leg-select fire can start ANY leg (`bind_leg` recomputes the per-leg stream / collision-mask pointers
and the scroll pre-build at runtime; the fixture's per-leg `ARENA_COURSE_*_OFF` stay only for
`bench_main.c`).

**Boot order.** The shipping BUGGYBOY.PRG boots into the LEG SELECT first, exactly as the original game
does — there is NO boot fast path in the shipping build. The frame-0 golden harness (`run_golden.py`)
needs a deterministic first painted frame, so it builds a SEPARATE variant with `-DGOLDEN_BOOT_LEG=N`:
that variant skips the leg select on the boot pass and starts leg N directly, drawing + dumping the
leg-start frame (byte-identical to `golden_leg<N>.bin`). The `game_main.c` `#ifdef BOOT_FAST_LEG` block carries
that fast path and is compiled ONLY when `GOLDEN_BOOT_LEG` (the golden harness) or `GAME_AUTODRIVE` (the
headless race trace, which can't drive the menu with a dead keyboard) is defined. Coverage seam worth
naming: the shipping cold-boot leg-select branch (the `#else` of that `#ifdef BOOT_FAST_LEG`) is
exercised ONLY by the manual `GAME_FLOW_AUTO` flow-trace recipe — `make test` builds no `.PRG` at all,
and `run_golden.py` compiles the `BOOT_FAST_LEG` branch (the golden variant skips the leg select). So
the leg-select-first boot path is on-target-only, proven by that trace. Proven on the 68000
(see the flow-trace section below): booting into the leg select, its fire starting a leg, a timed-out
leg reaching the intermission, a full attract cycle (A→B→C→D→restart), and the return to the leg select
— the whole game loop closes unattended. **All five legs 0–4 now have an on-target golden.**
`run_golden.py` loops the legs (or takes a single-leg argument for quick iteration): for each leg N it
builds `GOLDEN.PRG` with `-DGOLDEN_BOOT_LEG=N` and its reference with `GOLDEN_LEG=N`, both derived from
the ONE loop variable, and byte-compares the boot frame against `golden_leg<N>.bin`. The leg is a
parameter, not five divergent fixture bakes: the fixture arrays are leg-independent for the byte-compare
(the palette is an off-image seam that `rm_init_leg` re-stages per leg at boot; `bind_leg` recomputes the
per-leg stream/mask at runtime), so only the golden render and the informational `GAME_LEG_INDEX` vary
with the leg — the shipping BUGGYBOY.PRG still boots every leg from ONE binary. The per-leg goldens
genuinely differ (1624–5002 bytes vs leg 0), so five MATCHes are a real per-leg proof, not five identical
frames. Runtime ~16 s for the set (~3 s/leg, sequential — the cores don't vary with the leg, but each
needs a fresh golden render + cross-compile + Hatari run; restructuring the build to share the cores
across the five is the deferred two-variant refactor, not attempted here). `NUM_LEGS` (the loop bound) is
pinned == the shell's `IP_LEG_COUNT` by `test_game_fixture.py::test_golden_leg_count_matches_the_shell`.

**Slice D is done: the composition DRIVER is hoisted and given host coverage.** Slice C left the
sequencing driver (`intermission_cycle` / `run_leg_select` / `main`'s game-over tail) in `game_main.c`,
which `make test` never compiled — an integration smoke test (the flow trace + the golden), not a
differential, so four correctness bugs shipped green through it. Slice D moves that driver into
`src/flow.c` (`rm_flow_intermission_cycle` / `rm_flow_intermission` / `rm_flow_leg_select` /
`rm_flow_game_over`, structured to mirror `g_intermission` / `g_init_playfield`) behind a small `FlowOps`
callback table + a `FlowTuning` (the attract-timing knobs — the old `GAME_FLOW_FAST` #ifdefs promoted to
data). The driver orders only the platform effects it actually issues — `poll_input` / `quit_requested` /
`fkey_leg`, `draw_fade` / `draw_intermission` / `draw_results`, `set_palette` / `show`, `rebuild_dash` /
`start_demo_leg` / `run_demo_frame`, and the `event` trace hook — and `game_main.c` keeps only the 68000
implementations (`op_*` over the `Shell`; the input source is repointed per call, replacing the old
`input_of` / `fkey_leg` function-pointer args). With the leg-select-first boot order, the
`GAME_FLOW_AUTO` phase log now LEADS with the leg select (`SELECT_ENTER` → `SELECT_FIRE` → `LEG_START`),
where it used to lead with a boot fast-path `LEG_START` — see the flow-trace section for the current
sequence. One cosmetic detail in the trace only: the driver emits the flow's own `leg_index` in the
trace's leg column at the six intermission event sites, where the old shell passed its race leg — the
two differ on 2nd+ attract cycles, on a Phase-D abort, and on the select-idle path (the drawn frames
and every counter are identical; only the diagnostic leg column moved).

Host-side, `test/test_flow_machine.py`'s `test_flow_driver_*` run the hoisted driver with recording
callbacks and give **two distinct guarantees**: every flow COUNTER at each callback routes through the
verified in-image oracle slices (`g_int_stepA` / `g_int_phaseB_leg` / `g_int_stepD_counter` /
`g_check_abort` / `g_init_playfield_*`), and the SEQUENCING (draws / flips / palettes / phase events, the
loop structure) is pinned against a **hand-written Python structural mirror** (`_mirror_int_cycle` /
`_mirror_leg_select`) — the A→B→C→D→leg-select sequence, the abort/quit unwind in every polling phase,
and the game-over bracket, with 0 divergences. This is a structural mirror, NOT a lockstep against
`g_intermission`: it catches a one-sided mutation but would pass an ordering error authored identically
into both the C driver and the mirror. So of the four escaped bugs, only two (the idle hang past the leg
end, Esc/Q unreachable from menus) live in this now-covered driver; the other two — the leg-start marker
reseed (in `start_leg`, a host stub here) and the menu-race palette (set in `main()` after
`rm_flow_leg_select` returns) — are NOT in the driver and stay guarded only by the on-target flow trace
and the frame-0 golden. See `equiv.py`'s `compare_flow_*` + `_DriverRecorder` / `_MirrorRecorder`.

The between-legs **sub-draws are now ported and wired**: `rm_draw_divider` / `rm_draw_panel5`
(`src/results.c`, byte-exact vs `g_draw_divider` / `g_draw_panel5` — `test/test_flow.py`) draw the
5-entry leg-name menu over the leg-select and "get ready" screens, and `rm_draw_leg_labels`
(`src/events.c`, the existing folded-probe body exposed publicly) draws each leg's place-name labels
onto the dashboard graphic in Phase B and the fire-start (matching `g_draw_leg_labels`; its folded
`probe_collision` only WALKS the dashboard marker — it does not arm a crash — so it is safe in these
fresh-state contexts exactly as the original runs it). The fire-start now runs the real `ip_start_leg`
"get ready" sequence — redraw the results + menu twice, add the labels, then the **121-frame
`leg_start_palette` flash** (a per-frame palette animation from the obj-low flash tables + a vblank
wait; `op_flash_frame` in game_main.c). The driver (`src/flow.c`) owns the flash COUNT (a `FlowTuning`
knob, pinned + mutation-verified in `test/test_flow_machine.py`); the palette animation itself is an
off-image seam (Setpalette is palette-agnostic to the byte-compare, so the flash never touches the
framebuffer). It adds frames but no new trace tags, so the `GAME_FLOW_AUTO` phase log is unchanged.

The seams the shell stands in for, each documented at its call site in game_main.c: the exact Vsync
cadence, and the per-phase palette Setpalettes (off-image — the byte-compare is palette-agnostic,
including the leg-start flash's own animated palette). **Sound is NO LONGER a seam** (slice 3): a 50 Hz
VBL pump plays the REFRESH driver's YM2149 stream and the leg-start countdown / engine idle go through
real XBIOS Dosound — see the "Sound (slice 3)" section below. **The attract DEMO's input is
NOT a seam** (scouted 2026-07-23): the original does not replay a recorded ghost — it runs the demo with
`game_over_flag != 0`, in which `game_update` forces the player input to a constant throttle (`if
(game_over_flag != 0) uVar11 = 1`), and Phase C feeds the identical constant (`ATTRACT_DEMO_INPUT =
RM_IN_ACCEL`). See STATUS's `game_update` row + the ATTRACT_DEMO_INPUT note in game_main.c for the
mechanism and the one honest `p->game_over` nuance. The interactive high-score
NAME-ENTRY tail is now PORTED + wired (slice F): the made/missed dispatch is `rm_flow_score_tail`
(`src/flow.c`, not the shell, so `make test` pins the branch) — a leg-end score that made the table runs
the initials screen (`rm_flow_name_entry` — `rm_draw_results_screen` per frame + a `TIME nn` countdown
while the player dials three initials into row+8), one that missed runs the short game-over screen
(`rm_flow_game_over_tail`), then the intermission. The terminal tail's NON-sound steps are reproduced:
after the fade (redraw ×2) the finished table is HELD `FlowTuning.hold_frames` Vsyncs (default 121 ==
`HS_HOLD_FRAMES`, `op_hold_frame` = a plain `Vsync`), then the input-release wait polls until no bit is
held. The SOUND steps are host-verified as driver STATE (the name-entry jingle + TURNOFF) and, on target
(slice 3), actually AUDIBLE: `op_wait_music_off` is the real jingle-end spin (Vsync until `rm_sound_music_on`
goes false — the pump advances the tune to its end command — or a fresh key) + the Crawio key-drain, so the
jingle plays out before control returns to the intermission; the colour-3 flash (`op_name_flash`) is a `Setcolor` seam like the get-ready flash
(the driver owns the per-frame COUNT, the content `A_name_anim_tbl[(anim_counter & 0xe)]` is documented).
`init_scoretable`'s output is baked as a
program-data SEED (`fixture_highscore`) the shell copies into a mutable `highscore_ram` at boot, exactly
as `fixture_hud_text` seeds `hud_text_ram` — the tiny init routine is not run on-target (its output is
deterministic program data).

Last verified: 2026-07-23. `make test` = **540 passed**; `run_golden.py` = **MATCH on all five legs 0–4** (each leg's frame-0 golden). Section 12's **object / marker
ring** is ported (`CourseRing` in `include/game.h`, `rm_road_course_advance` in `src/course.c`) and
its four aliased consumers are unified onto it (see below). **Slice 2 is done**: the course-event
engine is wired into `rm_player_update`'s §6 event path and the frame loop (leg drive + game), the
leg-drive crash handover is removed, and the game's autodrive trace arms `collision_lock` on the
68000 at the same frame the host reference does.

**The course-event engine landed** (`src/events.c`): the event jump-table dispatch (`rm_event_dispatch`),
section 12's tail (`rm_course_events` — the fx block, the two horizon-keyed dispatches, and the
checkpoint / collision / score markers), and the collision-probe head (`rm_course_probe`), plus the
leg-0 dashboard rebuild and the checkpoint-banner scroll. Every piece is differential-tested against
recreate's `g_gu_dispatch_event` / `g_game_update_fx_and_events` / `g_probe_collision` on staged
frames (`test/test_events.py`). Slice 1 was the native core + its tests; **slice 2 wired it in**:
`rm_player_update` grew an `RmEventCtx *` (and a non-const `ctrl`), and its §6 event path now
dispatches a pending event through `rm_event_dispatch` — a bonus-display record even rebuilds the
control table mid-dispatch via `rm_build_road_geometry`, which §10's edge clamp reads back. The frame
loop (both `equiv._Candidate` and `game_main.c`) runs the wrap-frame course tail in the original's
order — `rm_course_probe` → `rm_road_course_advance` → `rm_build_road_geometry` (so `horizon_row` is
fresh) → `rm_course_events` — after clearing `event_pending` (recreate `game_update.c:504`). The
leg-drive crash handover is gone: the candidate arms its own crashes and every field (all 14 ring
bands, EventState, the GobjPrefixState counters, the HUD-text score) is compared strictly.

The leg/game-flow CORE landed (slice 1, host-side): `g_game_update` §1's marker gate + §2's input
capture are at the head of `rm_player_update`, and the crash / end-of-race tally (HUD phase 8's
`hud_crash_timer` decay + `draw_crash_fx`'s STATE side) is `rm_crash_fx_update` in `src/events.c`.
`hud.c`'s `hud_crash_fx` keeps DRAWING the tally off a throwaway HUD-text copy (pixel-verified by
`test_hud`); the new UPDATE owns the persistent mutations — `crash_frame`, the bonus drain into the
score, and `abort_flag` (new `EventState` field) — so a self-running leg advances and, when the bonus
clock times out, **ends** (`abort_flag` goes negative, which the frame loop reads as the leg end).
Pinned by `test/test_crash_fx.py` (every branch, mutation-verified) and organically by
`test/test_leg_drive.py`'s idle-to-time-out drives.

**The tally is wired on-target.** `game_main.c`'s `game_update_step` calls `rm_crash_fx_update` every
frame at the per-frame tail (before `apply_player`, so the drawn HUD sees this frame's tally — the same
order `equiv._Candidate.step` established). When `abort_flag` goes negative — the leg end — the shell
now runs the REAL between-legs flow (slice C, above): `rm_update_highscore` → `rm_flow_game_over_enter`
→ the intermission → `rm_flow_game_over_exit` → the leg select → the next leg. (The old leg-restart
stand-in — restart the current leg from its `R`-key boot state on `abort_flag < 0` — is gone.) The
idle leg-end path is still proven on the 68000 by the autodrive trace (`hud_crash_timer` arms 0x5b at
the time-out, decays negative, `abort_flag` arms 0xffff), and the flow-trace run then shows that leg
end flowing through highscore → intermission → leg select → a new leg start.

**The leg START is now native** (`rm_init_leg` in `src/gameplay.c`, homed with the gobj prefix as in
recreate's own gameplay.c). It reproduces `g_init_leg`'s eleven phases across the native owner structs
(Player/Course/Pose/Scroll/Ring/Event/GobjPrefix/Sprite) plus the two output scalars (`obj_shade`,
`screen_offset`) and the shared HUD-text region — the 0x6d-word clear becomes a per-struct reset (a
handful of fields below/above the clear bounds are PRESERVED: game-over, timeout-gate, anim-counter,
flag-seq cursor, the dash marker), the phase-2 defaults, the ring seeded from the leg's packed marker
records, the HUD bonus-time / score strings, and the scaled-object shade + scroll offset. Pinned by
`test/test_init_leg.py` (differential vs `g_init_leg` over all legs 0-4, FRESH + RE-INIT/warmed,
mutation-verified) and organically by a `test_leg_drive.py` drive whose candidate start state comes
from `rm_init_leg` (native init is drive-equivalent). One phase is a documented exception (not a compared
surface): phase 3's checkpoint-banner draw (gfx-only, regenerated by `rm_course_events`; the golden
renders from the fresh arena). Phase 11 is fully ported — it stages the object-display / palette record
(the same 0x17fac.. record the mode-4 event re-stages) into a native `race_pal` buffer AND derives
`obj_shade`; the four staged palette pieces are a compared surface (`test_init_leg`). **The game boots AND restarts
through `rm_init_leg`** (`game_main.c` `start_leg`: reset the owner structs, then derive the views via
`apply_player` + `ring_views_refresh` before the frame-0 draw), so the fixture no longer bakes any
per-leg leg-start scalar (see the fixture-shrink note below). Verified on the 68000: `run_golden.py`
MATCH (frame 0 reproduced natively), and the idle leg-end autodrive restarts through `start_leg`
cleanly (timer → negative → `abort_flag` 0xffff → reset to 0, no re-arm/hang). One honest correction
the port turned up: the oracle's `init_leg` (0x104b8) does NOT seed the dashboard marker — it stays 0
at a leg start; the per-leg arena reseed is the intermission's `init_leg_dash` (already ported in
`events.c`), which fires on a checkpoint. The baked `EV_DASH_*_INIT` were therefore 0 and are simply
dropped.

Sound is now fully ported and wired end-to-end (slices 1–3): the REFRESH driver + triggers are verified
host-side and slice 3 makes them audible on target (the VBL pump + real Dosound + the countdown; `rev_reload`
aliases `lean_frame` and is invisible to every compared surface — verified, not assumed). (The attract demo
input is NO LONGER listed as unported: it was never a replay — the original holds a constant throttle via
`game_over_flag != 0`, which Phase C reproduces with `ATTRACT_DEMO_INPUT`; scouted 2026-07-23, see above.)
The interactive high-score name-entry tail
is now ported + wired (slice F, above). The intermission / results / highscore flow AROUND `init_leg`
is ported (slice B) AND now composed on-target in place of the leg-restart stand-in (slice C, above).

**The record-driven mode-2/4/6 palette / screen-offset events (`game_update_course_advance`'s tail) are
now ported + wired** (`rm_course_mode_event`, `src/events.c`). When `rm_road_course_advance` pulls a
record (it returns that as a bool), the shell fires the mode event between the geometry rebuild and
`rm_course_events`, exactly where the original runs it. The mode is ring row 0's marker high byte `& 6`:
mode 2 advances `scroll_frame` and re-picks `screen_offset`, and the shell re-runs `rm_scroll_prebuild`
from the new offset (its PIXELS are verified, not just the scalar — see the pinning note below); mode 4
advances `palette_cursor`, stages the palette record
(shared with phase 11's `rm_stage_palette_record`) and derives `obj_shade`; mode 6 flips `palette_toggle`
and pokes one tunnel colour register. The three scalars are new `EventState` fields (cleared by
`rm_init_leg`'s phase-1 reset). The palette WRITE is an off-image seam the shell owns: mode 4 →
`Setpalette(race_pal)`, mode 6 → `Setcolor` (the original pokes `0xffff824c + reg_sel`, a byte address
the shell folds to a register index — `reg_sel` is 4 in the shipped data → register 8). The byte-compare
and golden are palette-agnostic, so the seam's COLOURS are unverifiable, but the compared state
(`scroll_frame`/`palette_cursor`/`palette_toggle`/`obj_shade`/`screen_offset`) and the staged palette
BYTES are pinned frame-for-frame vs `g_game_update` (leg drives + directed
`test_course_mode_event_matches_recreate`; reachability + mutation table in STATUS.md). Mode 2's
re-prebuilt scroll PIXELS — the bytes the new `screen_offset` selects, not just the scalar — are pinned
byte-exact too: `test_mode2_scroll_prebuild_matches_recreate` drives to a mode-2 event, re-runs
`rm_scroll_prebuild` from the moved offset and blits, and compares the whole framebuffer vs recreate's
`g_blit_road_scroll` (mutation: prebuild from the pre-event offset → 419-byte diff, caught).

### What the ring port did and did not fix

The previous revision claimed one missing subsystem explained three symptoms. That was **one for
three** — worth recording, because the reasoning error is repeatable:

| Symptom | Status |
|---|---|
| `compare_leg_drive` hands the road control table over every frame | **fixed** — the table is now a compared result, and the ring is compared band by band |
| `run_golden.py` reports `DIFF 1110/32000` | **fixed — it was the leg-0 start gate, dropped by two game-fixture bugs** (see below); `run_golden.py` prints `MATCH` again |
| The start pole stays put as you drive | **fixed by the consumer unification below** — a frame-300 autodrive shows the course scenery arriving (tunnel approach), not the leg-start objects |

The lesson: a symptom that appears on **frame 0** cannot be explained by state that only diverges
once something has advanced. Check the frame index before attributing a symptom to a scroll.

### The ring's consumers are unified — every view now derives from the live `CourseRing`

The game used to hold the ring twice: `rm_build_road_geometry` read the live ring while four other
consumers read the *frozen* copy baked into `fixture_obj_low`, so the road's flags animated while
the scenery stayed at fixture-generation values. All four now derive from the live ring
(`src/course.c` helpers, wired in `game_main.c`, refreshed after every course advance):

- the object-list dispatcher's two flag streams walk `rm_ring_store_st`'s serialized ST-byte mirror
  (row 1 for the sprite passes, row 12 for the fixed pass) — the dispatcher keeps its flat-bytes
  contract, the mirror is just the ring in the original's own row-grid layout;
- `rm_ring_sprite_count` replaces the game's flat-image marker walk;
- `rm_ring_ground_markers` refreshes `GroundState.markers` (band *i*'s byte is **slot 7's low
  byte**, row byte `0xf` — an earlier revision of this section said slot 6, which is off by one:
  the original reads descriptor+3 from `0x18d48` = row base + `0xc` + 3);
- `rm_ring_buggy_gate`/`rm_ring_fg_gate` feed the sprite gates from band 11's marker bytes
  (`0x18eba`/`0x18ebb`), so the `(buggy_gate|fg_gate) & 0x80` suppression frames (24 on leg 0, 174
  on leg 3 over 600 reference frames) now reach the draws instead of a once-seeded fixture value.

The mapping is pinned by `test/test_ring_consumers.py`: over 5 legs × 3 warmup depths, each helper
is compared against the raw image bytes at the aliased addresses — including the full serialized
mirror byte-for-byte — plus directed cases for the sprite-count walk (the captured cases only
sample counts 0 and 11) and a reachability check that at least one sampled case carries the gate's
bit-7 suppress flag. The ring's *values* over time were already pinned by the leg drives; these
tests pin the *address arithmetic*. Most of the game *wiring* still has no host test (`make test`
never runs `game_main.c`) — it is verified on-target by the golden frame-0 compare and autodrive
runs. The one wiring seam that IS now host-tested is the per-frame **draw-struct fan-out**
(`apply_player`): its pure struct-to-struct body is hoisted into `rm_apply_player` (`src/gameplay.c`),
which `make test` compiles, and `game_main.c`'s `apply_player` is a thin wrapper over it. The leg
drives run the fan-out each frame and pin the four crash/spin SpriteState fields (`anim_frame`,
`spin_state`, `spin_reset`, `collision_lock`) it derives against recreate's image bytes — the seam
that used to be MISSED, so the dirt/wheel sprite stayed on the road through a jump (see STATUS
"Recently fixed").

A SECOND fan-out of the same class was found + fixed (2026-07-23): the **HUD flag-sequence view**.
`draw_hud` reads `flag_seq_count` (phase-4 bars) and `flag_seq_off` / `dsp_color_scroll` (phase-5
colour cursor) as globals; those live in `GobjPrefixState`, and `rm_apply_player` (which has no `gobj`
param) never fanned them into `HudState`, so the flag-sequence bars never drew — capturing a flag was
invisible (only the bars are its feedback; the score ticks every wrap frame anyway). The flag STATE
path (dispatch → order-match → score → `obj_active` consumption) was correct and already tracked by the
leg drives; ONLY the HUD view was unwired. Fixed by `rm_gobj_hud_view` (`src/gameplay.c`), which
`draw_frame` runs **after `rm_gobj_prefix`, before `rm_draw_hud`** (the original's `g_draw_game_objects`
-then-`g_draw_hud` order — it reads the *post*-prefix values, so it can't fold into `rm_apply_player`,
which runs before the prefix). Pinned host-side by `test/test_flag_capture.py` (the HUD-bars fan render,
a directed capture drive, and the flag_gate boundary branches the dispatch fuzz never reaches), all
mutation-verified. See STATUS "flag-sequence HUD fan-out gap" + the game-mechanics coverage audit.

**The COMPOSED-FRAME differential closes the coverage HOLE both fan-out bugs slipped through
(2026-07-23).** Both shipped green because the model verifies every state transition and every draw
STAGE in isolation, with the draw inputs staged FROM the reference image — it never ran the shell's
per-frame COMPOSITION (state → the fan-outs → the `draw_frame` stage sequence) end-to-end, so a gap
BETWEEN two verified pieces was invisible. Closed by hoisting the render composition into
**`rm_draw_frame` (`src/frame.c`)** — `game_main.c`'s `draw_frame` is now a thin wrapper that builds an
`RmScene` (a bundle of the owner structs + const assets + scratch buffers, `include/game.h`) and calls
it, so the shell calls ONE composition (`bench_main.c` deliberately mirrors it with staged HUD scalars) (the shell keeps only buffer selection +
`Setscreen`; `GAME_DUMP_STAGE`'s staged cuts move into `rm_draw_frame` under the same macro, still an
on-target debug knob). On top of it, `test/test_composed_frame.py` drives each leg and, on sampled
frames, runs the candidate's OWN composition (`rm_apply_player` → `rm_draw_frame` from its live owned
state, via `equiv._ComposedScene`) into an isolated framebuffer and **byte-compares it strict — no
persistent-diff allowlist — to recreate's `g_draw_frame`** on the image. Sampling = every EVENT frame
(view-wrap / crash arm / leg-end — where wiring bugs bite) + every 15th; drives = a free flat-out per
leg 0–4 (crashes on every leg) + directed slalom + a flag capture + a time-out leg-end. Mutation-
verified: dropping the `anim_frame` fan, dropping `rm_gobj_hud_view`, dropping a stage, and swapping
two ordered stages each fail a composed drive. It found **no** existing divergence (the composition,
incl. the once-seeded `objlist.bonus_timer`/`p24_flag`, is faithful on this game's data), cost ~0 suite
time (each drive is an xdist unit), and left `run_golden.py` MATCH + the `GAME_FLOW_AUTO` trace (19
records) unchanged. This is the general backstop for future fan/composition wiring bugs. See STATUS
"COMPOSED-FRAME differential".

**Closed (slice 2):** ring bands 12/13's slot words — which the fixed-object pass and
`GroundState.markers[12]` consume — used to be exempt from the leg-drive ring comparison, because the
then-unported horizon-event dispatch cleared bytes that land there. The dispatch now runs on the
candidate too (via `rm_course_events`), so `equiv._ring_mismatches` compares **all 14 bands whole**
and the exemption (`RING_EVENT_OWNED_BANDS`) is deleted.

### Recently fixed (kept here until the next STATUS pass)

**`build_road_geometry`'s write past the end of `ctrl`** is fixed by allocation, not clamping: the
stamp loop's spill (2 bytes on view bank 0, 6 on banks 2/4/6) is faithful to the original, so every
ctrl buffer is now sized `RM_CTRL_ALLOC_BYTES` (= `RM_CTRL_BYTES + RM_CTRL_STAMP_SPILL`). Two pins
keep it honest, because no ctrl comparison can see an under-sized pad (they all stop at
`RM_CTRL_BYTES`): `test_course_ring.test_python_constants_match_the_c` pins the game.h/adapter.py
copies equal, and `test_geometry.test_stamp_spill_stays_within_alloc` poison-pins the pad to the
stamp's measured write extent per view bank.

**Controls are now identical to the original arcade port** (2026-07-23). The earlier shell scheme had
invented bindings — `Esc`/`Q` quit the program, `R` restarted the leg — none of which the original has.
The original's actual scheme, read from the decomp:
- **Race** (`main @0x10100:273-311`): each frame after the flip does a non-blocking `Crawio(0xff)`
  console read. **ESC** (ASCII `0x1b`, `0x286 cmpi.b #$1b,d0 / beq $1e6`) breaks the race loop straight
  into `update_highscore` → `game_over++` → `intermission` — i.e. it aborts the leg back to the
  intermission attract cycle (which returns to the leg select); the current score is ranked, no bonus
  tally. `abort_flag < 0` (a natural time-out / finish) breaks to the SAME place. The read also stores
  the scancode into `last_key` (the keyboard driving fallback `read_input @0x120b0` reads), toggles
  **`dsp_toggle`** on scancode `0x22` = **G** (`0x296 not.w`), and runs a sound-reset debug on `0x62` =
  Help (`0x2a2`). Now that the remaster ships WITH sound (the VBL pump, slice 3) that Help key is PORTED
  as the in-race pause: `rm_pause_silence` (TURNOFF + EGOFF + fxflag clear, pump left running) + the
  shell's release-then-fresh-key wait, matching the original's silence-and-freeze loop (`0x2a2`; a
  resume-Q still quits — the drain preserves the Q latch). There is **no** quit key and **no** restart key: `main` is an
  infinite `do…while(true)` — a coin-op that never terminates.
- **Leg select** (`init_playfield @0x12af6`): joystick nav (up/left prev, down/right next) + button
  starts; the function-key menu reads the console for **F1..F5** (`0x3b..0x3f`, direct select+start),
  F6 (results preview), F10+RETURN (reload) — no ESC, exits only by a leg start or the idle-timeout →
  intermission.

The shipping `BUGGYBOY.PRG` now matches this: **ESC aborts a race back to the intermission** (sets the
race loop's `ended` flag, joining the already-verified natural-leg-end path — `update_highscore` →
`rm_flow_game_over` → intermission → leg select), **G toggles `dsp_toggle`**, **F1..F5** select a leg,
and the invented **R-restart and Esc-quit are gone**. The **single deliberate deviation** is **Q =
quit to the desktop** — a GEMDOS `.PRG` needs a way back to the desktop that a coin-op does not, so Q (a
key the original never reads) is it; `quit_requested()` is now Q-only. A stray ESC pressed in the leg
select is discarded at race entry (`take_key_hit(SCAN_ESC)`), mirroring the original menu's per-frame
Crawio drain, so it never aborts the race on frame 0. Verification: the `GAME_FLOW_AUTO` flow trace is
**unchanged at 19 records** (the documented sequence) — the auto build's keyboard is dead, so ESC/G/Q
never fire and the leg ends via the `GAME_TIME_LEFT` time-out, not ESC — and `run_golden.py` still
**MATCH**es (the golden's `BOOT_FAST_LEG` dumps frame 0 before the keyboard is even taken). The ESC-abort
itself is pinned by the decomp quote above + the fact that it merges into the natural-leg-end path the
trace already exercises; the race loop lives in `game_main.c`, which `make test` never compiles, so it
carries no host differential (the leg-select/intermission logic it feeds is pinned in `src/flow.c`). The
leg-select **arrow-key navigation** the shell keeps is the one non-conflicting convenience the arcade's
`init_playfield` reads only from the stick — it collides with nothing and keeps keyboard-only play usable.

**Esc returning to a frozen picture** is fixed: the game captures `Physbase()` and the 16 palette
registers (`Setcolor(reg, -1)`) before taking the screen, and restores both on exit — base only
would hand back a desktop drawn in the racing palette. (This restore now runs on the **Q** quit; the old
`Esc`-quit that motivated it is gone, per the controls note above.)

**The frame-0 `DIFF 1110/32000` was the leg-0 start gate, silently dropped by two game bugs.**
Neither was in a core (every stage matched the host byte-exactly under the on-target
`GAME_DUMP_STAGE` bisect until pass 1, which painted *nothing*):

- `buf_a_ram` was sized 0x3400 by what the old mid-race build happened to reach, but the
  dispatcher's per-type record table runs to `OBJ_TYPE_BASE + 0x40 * OBJ_TYPE_STRIDE = 0x3ca0` —
  the gate's type codes (0x3a/0x3b) indexed past the copy, read BSS zeros, and dispatched to the
  noop. `test_game_fixture.py` now pins the window to the dispatcher's constants.
- `ObjListCtx.obj_scan_off` was seeded 0, but the list-cursor offset and the ground's view column
  are ONE original global (0x18c58, = 442 at a leg start): frame 0's passes read their display
  records 442 bytes early, because the first draw runs before `apply_player` ever copies
  `ground_view_off` in.

Two diagnosis lessons, paid for in a day of byte archaeology: **bisect with `GAME_DUMP_STAGE`
against host-built partial frames first** — it took four probes to notice pass 1 painted nothing at
all (`stage3 == stage2`), which no amount of comparing wrong pixels against wrong models would have
shown; and **verify on-target data with word-granularity C reads before trusting byte-copy probe
dumps** — a chain of byte-level probes manufactured a phantom "+1 shift" that word reads of the
same memory refuted.

### Two dead ends — do not repeat them

- **The IKBD is not the problem.** A raw byte log of everything the ACIA delivered showed only
  well-formed make/break pairs — no stray mouse/joystick packet bytes reaching `key_down[]`. The
  "packet noise corrupts key state" theory is refuted by evidence. (This held because both mouse and
  joystick reporting were OFF then. Joystick support later turned joystick reporting back ON, so 0xFD
  reports DO arrive now — `kbd_isr` grew a packet state machine that routes them to `joy_state` and
  keeps them out of `key_down[]`; see the joystick note below.)
- **Seeding the game's `ctrl` from the leg's control table does nothing.** `draw_frame` rebuilds
  `ctrl` before anything reads the seed; the diff was byte-identical with and without. Reverted.

### Coverage traps this subsystem taught (they generalise)

Porting the ring cost two rounds of the same mistake, both caught by mutation-testing rather than by
reading:

- **Never infer branch coverage from the output.** A counter that looked for the animation run's
  successor codes in the resulting band reported the expansion firing — but 525 of the 554 animation
  codes across the five legs re-select those slots and overwrite them with exactly the bytes the
  expansion would have written. Deleting the whole expansion left the suite green. The same trap bit
  the slot-1 → slot-13 echo counter a second time. Derive coverage from the **record consumed**, not
  from the band produced.
- **A differential can be pinned on the wrong DATA.** `draw_results_screen` was byte-compared against
  recreate across every mode, rank and leg — and still missed the black-box glyph, because the default
  hi-score table's names are `"..."`, so the name-entry alphabet never reached the glyph blitter from
  there. The draw was covered; the *character set* was not. When a surface renders data, ask which
  values the fixture actually contains, not just which code paths run (`test_flow`'s alphabet windows).
- **Mutation testing lies if the edit preserves file size.** Python validates a cached `.pyc` on
  (mtime, size), so a same-length constant edit — `0x60` → `0x5f` — applied and reverted inside one
  filesystem second can leave the MUTATED bytecode in `__pycache__`. A mutation "caught" or "survived"
  under those conditions proves nothing. `find test -name __pycache__ -delete` between mutation runs,
  and be suspicious of a mutation result that contradicts a source read. (It also bit the generated
  fixture: a gate build running under the mutated `adapter.py` baked a truncated `fixture_font`, which
  the shipped-fixture assertion then caught — the reason that assertion is worth having.)
- **The data may not reach a branch at all.** Of the four `marker_unpack` outcomes, "right shoulder"
  appears in 25 records — all in leg 3 — and "both shoulders" in **none** of the 5120. Pin what the
  data can reach by *seeding `read_pos` onto a real record* (`test_ring_hard_to_reach_branches`);
  say so in `STATUS.md` for what it cannot, and never fabricate a record to manufacture a green tick.

### The shell-binding trap: what the tests bind is not what the game binds (2026-07-24)

A play-test turned up four bugs at once, and **not one of them was in `src/`** — every ported core was
byte-exact. They were all in the layer the harness cannot see: `render/atari/game_main.c` decides which
arena each asset pointer aims at and how big each fixture window is, while `test/adapter.py` +
`test/equiv.py` build *their own* bindings for the same structs. Where the two disagree, the suite is
green and the game is wrong. Concretely:

- **A live global captured once.** `objlist.bonus_timer` / `p24_flag` were derived in `start_leg` and
  never refreshed; in the original the dispatcher reloads both every frame. The 5-flag bonus window
  therefore never clamped an object type, and the p24 gate never re-read the score digit §I bumps at a
  checkpoint. Worse, `equiv._ComposedScene` *reproduced the staleness on purpose* "so the composed
  differential would surface it" — but reproducing a bug on both sides is exactly what stops a
  differential from surfacing it. **Both are now refreshed in `rm_draw_frame`**, where the original
  reads them, and the test seeds neither.
- **An arena pointed at dead scratch.** `GobjPrefixAssets.marker_recs` was bound to a private BSS block
  while the object dispatcher read `ring_st`. In the original both are the one grid at `A_obj_markers`
  (the decay base is 8 bytes below it), so the marker-decay animation — a kicked roadside object flying
  away, drawn by walking a `0xff` through the grid one band nearer per frame — wrote to nowhere. The
  object still vanished and still scored, so it looked *almost* right. `ring_st` is now a padded block
  and the prefix gets the biased base.
- **A fixture window sized by its first caller.** `FONT_BYTES` was `0x600` — "all the gauge string
  uses" — but the high-score initials cycle up to `'`'` (0x60), one glyph past the end. On target the
  blitter read the next fixture as glyph pixels, and an all-zero `(mask, ink)` row *replaces* the cell
  with colour 0: a black box. Host tests never saw it because they hand the C code a slice of the live
  68k image, where the bytes past the window are the real font.
- **An alias the port split.** See the bullet below.

The generalisable rules:

- **Every fixture window needs a bound derived from the widest caller, asserted in a test** — not a
  comment naming the caller it was measured against. `test_game_fixture.py` is where those bounds live.
- **A global two subsystems share must be refreshed where the original reads it**, not where the port
  finds it convenient to derive.
- **Never teach a test to imitate the shell's binding.** If the test needs its own copy of a binding,
  that binding is the untested thing. The structural fix is to hoist the binding into shared code both
  the shell and the harness call — the same move that hoisted `rm_draw_frame` out of `game_main.c`.
- **Aliased addresses are load-bearing.** `recreate/include/addrs.h` has four addresses under two names
  (`0x18c58`, `0x18d5a`, `0x18d12`, and one duplicate); three are handled, and `0x18d12`
  (`rev_reload` == `lean_frame`) was not: the port skipped the `rev_reload` poke on the reasoning that
  "no compared surface reads lean_frame", which is false — `draw_buggy_hi` reads it every frame. Sweep
  `addrs.h` for duplicate addresses when porting, and justify each one in code.

Coverage note, honestly: of the four, the composed-frame differential now pins the two `objlist`
globals, `test_text` + `test_game_fixture` pin the font, and a directed
`test_rev_reload_poke_restarts_the_lean_overlay` pins the alias at both its poke sites (nothing else
could — the composed differential re-seeds the sprite's draw-internal cursors from the reference by
design).

#### Harness gap #1 — closed (2026-07-24)

The `marker_recs` binding lives in `game_main.c`, which `make test` does not compile, so at first it
was pinned only by reading. The fix was **not** to compile the shell host-side but to remove the
opportunity to disagree:

- The aliasing geometry moved OUT of the shell into `include/game.h` — `RM_RING_DECAY_BIAS`,
  `RM_RING_ST_BLOCK_BYTES`, `rm_ring_decay_base()`. One definition; the shell and the harness both
  allocate the padded block and take the biased base from it.
- `equiv._ComposedScene` had been binding `marker_recs` into the image while its dispatcher read a
  private `ring_st` — i.e. **the harness independently reproduced the shell's bug**, which is why the
  composed differential was blind to it. It now allocates the same padded block.
- A directed drive seeds an armed decay (no free drive kicks an object), plus a direct assertion that
  the decay's walked marker lands in the grid the dispatcher reads
  (`test_marker_decay_writes_reach_the_dispatcher_grid`). Mutation-verified: any other arena fails it.

The generalised rule this adds to the list above: **when two subsystems must see the same bytes, the
geometry of that aliasing belongs in shared code, not in each caller.** A constant the shell and the
harness each define is a constant they can each get wrong.

What it immediately caught: with the arenas correctly aliased the composed frame still diverges from
recreate on 2 of 27 sampled frames of the decay drive (263 bytes, both early cadence samples before the
first course advance). Binding them separately hid it entirely — the same drive diverged on 25 of 27,
i.e. the old harness was noise, not signal. That divergence is real, unresolved, and now recorded as a
strict `xfail` rather than a comment; see `STATUS.md`.

### Harness gap #2 — the on-target build is now a test gate (2026-07-24)

`make test` used to compile the game shell for **nobody**. `render/atari/game_main.c` (1721 lines — every
asset binding, the frame loop, every TOS seam) is in neither the host `.so` (`SRC` is `src/*.c` only) nor
`bench.elf` (`bench_build.sh` links `bench_main.c` and a 17-file subset of `src/`), and four `src/` files
— `frame.c`, `flow.c`, `intermission.c`, `results.c` — are host-compiled but never cross-compiled. The
only thing that built the shell was `build_game.sh`, which nothing in the gate invoked.

Consequence, twice in one session: a commit landed `game_main.c` using symbols whose header half was
still uncommitted, so the m68k build was broken **on `origin`** and every test stayed green.

Closed by making the real build part of the gate:

- `make test` now depends on `GATE.PRG` **and** `GATESTE.PRG` — full cross-compile + link + `.PRG` wrap,
  the shipping build and the measurement build (`GAME_STE_SELFTEST/SWEEP/CENSUS=1`, which adds sources
  and CFLAGS, so without the second build those sources compile nowhere). ~2 s each; the m68k toolchain
  was ALREADY a hard prerequisite via `bench.elf`, so this adds no dependency, only ~4 s.
- Both go through `build_game.sh` rather than restating its flags. A third copy of the cross flags is
  exactly the drift this gate exists to catch. They build under gate-only names so the shipping
  `BUGGYBOY.PRG` is never clobbered.
- `make golden` promotes the existing Hatari end-to-end (5 legs, byte-compared against recreate's ported
  pipeline) to a named target. Not in `make test` — it needs Hatari and ~20 s — but it is the only check
  that runs the shipped shell on a 68000.

Mutation-verified: a typo'd constant in `game_main.c` now fails `make test` at the build step, before
pytest runs.

**The trap adding it exposed: a generated header that is rewritten unconditionally poisons every
downstream target's incrementality.** `build_game.sh` and `bench_build.sh` both re-run
`gen_sound_fixture.py` on every invocation, so `build/sound_data.h`'s mtime bumped every build — and
every target depending on it (`libremaster.so`, `bench.elf`, now the gate `.PRG`s) was out of date the
moment it finished, rebuilding forever. `bench.elf` had been doing exactly that, unnoticed, because
nobody times a 2 s step. The fix is at the root, not in the dependency lists: `fixture_lib.write_if_changed()`
skips the write when the content is identical, so all three generators are content-stable and `make test`
on an unchanged tree now rebuilds nothing. Reaching for order-only prerequisites instead (the first
attempt) "works" only by dropping the rebuild coverage that made the dependency worth declaring — the
review caught it.

Dependency lists for a target built by a *script* are easy to under-declare, and an under-declared gate
is worth nothing: it certifies a binary it did not rebuild. `GATE_DEPS` therefore lists the generators
and the harness modules the fixture is baked from (`test/adapter.py` bakes the asset windows — an
adapter change is precisely what shipped the truncated font fixture), plus `render/atari/*.h`, which
neither the `include/` nor the `shim_include/` wildcard covers.

**What this does and does not buy.** It catches "the shell does not compile / does not link" — a real
failure mode that reached `origin` twice. It would NOT have caught any of the four play-test bugs above:
those were all semantically valid C. Executing the shell's bindings host-side is a different job — the
next section.

### Binding hoists: making the harness execute the SHELL's bindings

The bug class the play-test found is not "does it compile" but "does the shell wire the arenas the way
the original did". `make test` cannot answer that by compiling `game_main.c` for the host (it is full of
TOS seams); the answer is to move each binding DECISION into shared code that the shell and the harness
both call, so a wrong decision is wrong on both sides and the composed-frame differential sees it.

Three hoists so far, in increasing order of what they retire:

1. **`rm_draw_frame`** (`src/frame.c`) — the per-frame composition. The shell keeps only buffer
   selection and `Setscreen`.
2. **The ring/decay geometry** (`include/game.h`: `RM_RING_DECAY_BIAS`, `RM_RING_ST_BLOCK_BYTES`,
   `rm_ring_decay_base()`) — the shape of the aliasing, so both sides allocate one padded block.
3. **`rm_bind_gobj_prefix_assets`** (`src/gameplay.c`) — the whole bundle. The caller still resolves the
   three const table pointers (only it knows its own base: the shell walks its obj-low blob, the harness
   points into the 68k image — they agree because `OBJ_LOW_BASE + OBJ_LOW_X == A_X`), but every ALIAS and
   OFFSET is applied in one place: decay arena → the dispatcher's grid, animated colour → the HUD's
   fuel mask, the two `buf_a` anim-word mirrors. `_ComposedScene` no longer builds this bundle at all.
   Mutation-verified: dropping the bias inside the binder now fails four tests, because the harness runs
   the shell's own binding code.

What is left, and the reason it is bigger than it looks: the other bundles (`HudAssets` most of all)
carry their offsets in the GENERATED `game_fixture.h` — `OBJ_LOW_*`, `ARENA_*_OFF`, `CIDX_ZERO_OFF` —
which `src/` would have to include to bind them, pulling every baked array into the host `.so` as well.
Hoisting those cleanly needs `gen_game_fixture.py` split into a defines header and an arrays header.
Until then, bind bundle-by-bundle, starting with whichever one holds an alias.

### Joystick support (port 1) — and the supervisor-mode gotcha

The arcade reads a joystick in port 1 every frame: `read_joystick @0x12110` busy-waits the IKBD ACIA
transmit register empty and pokes command `0x16` (interrogate joystick) into the data register; a TOS
`joyvec` handler (`@0x12156`, installed via `Kbdvbase`) then snapshots `input_state` and copies the
two joystick payload bytes into it. The game's input word bits (`RM_IN_ACCEL 0x01` … `FIRE 0x80`) are
byte-identical to the Atari joystick packet byte, and `read_input @0x120b0` already gives the joystick
priority (keyboard is the fallback only when `(input_state & 0x8f) == 0`).

The shell keeps its **own** ACIA vector (it does not use TOS's `joyvec` route), so two pieces landed:

- **`kbd_isr` grew a packet state machine** (`os.s`). It stops disabling joystick reporting (keeps
  mouse-off), so 0xFD joystick reports now arrive interleaved with scancodes. A byte `< 0xF6` is a
  keyboard make/break (break codes top out at `0xF2`); `0xF6..0xFF` is a report header whose payload
  length comes from a small table, and a joystick report (`0xFD`/`0xFE`/`0xFF`) routes its payload into
  `joy_state` (any other report's payload is swallowed, so mouse noise can never reach `key_down[]`).
  Reports arrive byte-contiguous, so `pkt_left` tracks one across interrupts without a scancode slipping
  in mid-payload. `read_input` then merges joystick-priority: `if (joy & 0x8f) return joy;` else the
  arrow/Space fallback — mirroring recreate `input.c:32`.

- **The interrogate goes through `Ikbdws`, not a raw ACIA poke.** The arcade ran in **supervisor**
  mode, so its direct `move.b (a1),d2` on `0xfffffc00` is legal. This shell is a **user-mode** GEMDOS
  program, where the IKBD ACIA (`0xffff8000`+) is supervisor-only: a raw read **bus-errors**
  (`Bus Error reading at address $fffffc00, PC=$1b150` — caught by the `GAME_FLOW_AUTO` trace, whose
  race loop drives through `read_input`). The fix is to send `0x16` via `Ikbdws` (XBIOS 25), the same
  BIOS path `kbd_install` already uses for mouse-off. The reply still returns through our own ACIA
  vector into `kbd_isr` (whose raw ACIA reads are fine — interrupts always run supervisor).

**A one-byte BSS trap paid for once.** `os.s`'s three new BSS bytes (`joy_state`/`pkt_left`/`pkt_join`)
made that section's `.bss` **odd**-sized; `tos.ld` packs the next object's `.bss` immediately after it
(`SUBALIGN(1)`, no gap), so every word-aligned global downstream shifted to an **odd** address and a
`move.w` at boot address-errored ($a970b) — before any dump, so it read as a build/boot failure that
`run_golden.py` caught. `key_down`+`key_hit` were 256 (even) on their own. The fix is a trailing `.even`
directive closing that `.bss` (not a hand-counted pad byte): the assembler now rounds the section up to
even automatically, so any future `os.s` `.bss` addition stays even-sized without anyone re-counting.

**Verification is honest about its limits.** The parser + interrogate are on an on-target path
`make test` cannot reach, and the headless gates pin LESS of it than they might seem to. What they cover:
`run_golden.py` MATCH (unaffected — the interrogate is never called before the frame-0 dump), and the
`GAME_FLOW_AUTO` trace **unchanged at 19 records** (the documented sequence) — its race loop now runs
`read_input` every frame, so the `Ikbdws` interrogate and the `kbd_isr` packet parse execute, which
proves only that they **don't hang, don't bus-error, and don't corrupt the keyboard/flow**. It does NOT
pin the joystick STORE/decode: headless Hatari has no stick attached, so the interrogate reply is
all-zeros, `joy_state` stays 0 and the keyboard fallback is intact — and the flow trace is byte-identical
whether the decode is correct or completely broken (an all-zero reply exercises neither the store guard
nor the bit mapping). This is exactly the repo's "beware output-inferred coverage" rule: a green trace
here is not evidence the decode works. **The joystick STORE path is pinned ONLY by the manual
stick-in-hand run** — headless Hatari cannot receive key/joystick events:

```bash
bash render/atari/build_game.sh
hatari --memsize 4 --tos-res low --joy1 keys --harddrive render/atari/disk --auto 'C:\BUGGYBOY.PRG'
```

Then drive with the arrow keys (Hatari's `--joy1 keys` maps them to joystick port 1) — the buggy steers
and accelerates through the joystick path, and the leg select / fire respond to the stick, while
scancode-only keys (F1..F5, G, ESC, Q) stay clean. (The pre-joystick build, with reporting off, would
mis-read a `0xFD` report as scancodes; that this drives cleanly is the parser working.)

## Debugging on-target

Three build flags, all off in normal builds, set via `GAME_EXTRA_CFLAGS`:

```bash
# bisect a divergence to one render stage (0 road, 1 ground, 2 foreground, 3 pass 1)
GAME_EXTRA_CFLAGS="-DGAME_DUMP_STAGE=0" bash render/atari/build_game.sh

# drive a fixed script headlessly and log per-frame course state to SCREEN.BIN (9 BE words/frame:
# frame, read_pos, row_ctr, speed, rpm, collision_lock, hud_crash_timer, view_wrapped, abort_flag).
# Under GAME_AUTODRIVE the trace is dumped on race-loop EXIT — whichever comes first, the leg end
# (abort_flag < 0) or the GAME_TRACE frame budget — then the run quits rather than entering the
# between-legs flow (which would poll a dead keyboard under headless Hatari and hang).
GAME_EXTRA_CFLAGS="-DGAME_AUTODRIVE=600 -DGAME_TRACE=600 -DAUTODRIVE_STEER_AFTER=100000" \
  bash render/atari/build_game.sh

# drive the IDLE leg-end path (no throttle, shortened bonus clock) to prove the tally ends the leg on
# the 68000: hud_crash_timer arms 0x5b, decays negative, abort_flag arms — SCREEN.BIN then holds the
# leg-end frames (the last record has abort_flag = 0xffff, ~frame 129), because the dump fires on the
# leg end, not only at the frame budget. AUTODRIVE_BASE_INPUT=0 idles; GAME_TIME_LEFT shortens the clock.
GAME_EXTRA_CFLAGS="-DGAME_AUTODRIVE=160 -DGAME_TRACE=160 -DAUTODRIVE_BASE_INPUT=0 \
  -DAUTODRIVE_STEER_AFTER=100000 -DGAME_TIME_LEFT=6" bash render/atari/build_game.sh

# drive the WHOLE game shell headlessly and log the flow's phase transitions to SCREEN.BIN, in the
# shipping boot order: leg select -> fire starts leg 0 -> the leg times out (GAME_TIME_LEFT) ->
# update_highscore -> intermission (A->B->C->D->restart, the phases shortened by GAME_FLOW_FAST so a
# cycle fits a bounded run) -> auto-abort -> back to the leg select -> a fresh fire starts a leg -> the
# loop closes. GAME_FLOW_AUTO scripts the inputs; GAME_FLOW_TRACE writes the (tag, leg, aux) phase log.
# Decode with a run_flow helper (see the flow-trace section).
GAME_EXTRA_CFLAGS="-DGAME_FLOW_AUTO -DGAME_FLOW_FAST -DGAME_FLOW_TRACE -DGAME_TIME_LEFT=6" \
  bash render/atari/build_game.sh
```

(The old `-DGAME_KEYLOG` raw-IKBD-byte log is gone: the slice-C rewrite of game_main.c dropped it, and
the IKBD-noise investigation it served is a closed dead end — "The IKBD is not the problem", below.)

`run_hatari.RUN_VBLS` defaults to 4000, which is **not enough for a long trace** — a frame costs
~200 ms (≈10 vbls; measured by the 2026-07-22 full-frame bench, see STATUS "Perf"), so a 600-frame
run needs ~60000 and a raised `timeout=`. Set both when driving headlessly, or the run dies with
"did not produce SCREEN.BIN" and looks like a build failure.

A trace run necessarily reports `DIFF` from `run_golden.py`: `golden.bin` is frame 0 and the dump is
frame N (or telemetry). That is the run working, not failing — a `MATCH` there would mean nothing moved.

### The flow phase trace

`GAME_FLOW_TRACE` writes the between-legs flow's PHASE-transition log to SCREEN.BIN (padded to a full
framebuffer so the standard runner picks it up): word 0 = the record count, then `(tag, leg, aux)`
triples. The tags are the flow boundaries — `LEG_START` / `LEG_END` / `HISCORE`, the intermission's
`INT_PROLOGUE` / `PHASEA_BREAK` / `PHASEB` / `PHASEC_DONE` / `PHASED_ADVANCE` / `PHASED_RESTART` /
`INT_ABORT`, and the leg select's `SELECT_ENTER` / `SELECT_FIRE` / `SELECT_IDLE`. A headless run of the
`GAME_FLOW_AUTO` build reads these back to confirm the loop closes.

With the shipping leg-select-first boot order, the trace LEADS with the leg select. The observed log
(RUN_VBLS 150000, GAME_FLOW_FAST + GAME_TIME_LEFT=6) is:

```
SELECT_ENTER 0 → SELECT_FIRE 0 → LEG_START 0 → LEG_END 0 (abort_flag 0xffff) → HISCORE 0 →
INT_PROLOGUE → PHASEA_BREAK → PHASEB 1 → PHASEC_DONE (6 frames) → PHASED_ADVANCE 1,2,3,4 →
PHASED_RESTART 0 → INT_PROLOGUE → INT_ABORT → SELECT_ENTER 0 → SELECT_FIRE 0 → LEG_START 0
```

That exercises, in the shipping order: booting into the **leg select**, its **fire** starting a leg, a
timed-out leg (`LEG_END`, `abort_flag 0xffff`) reaching **highscore + intermission**, a full attract
cycle **A→B→C→D→restart**, and the **return to the leg select** — where a fresh fire starts a leg again,
so the **whole loop closes**. Slice F's name-entry branch leaves this log **unchanged** (still 19 records,
verified 2026-07-23): the timed-out leg's score misses the default table (`HISCORE 0`, `hiscore_pos` 0),
so the short game-over tail (two redraws, no new trace tags) runs between `HISCORE` and `INT_PROLOGUE`
rather than the interactive initials screen — which the auto build's no-fire input never confirms and is
instead exercised by the host tests (`test_name_entry.py`). The attract Phase C also RACES the picked leg (leg 1 here) through the real
pipeline for 6 frames without hanging — on-target evidence that a non-zero leg's race runs. Decode with a
runner that sets `RUN_VBLS` high and parses the log words (a `run_flow.py` scratch helper; the trace is
the on-target guard, as `make test` never runs game_main.c). This is a deliberate re-pin from the old
boot-into-leg-0 sequence, which used to lead with `LEG_START 0`.

Slice 3's leg-start countdown (below) leaves this log **unchanged at 19 records** too — it adds Vsyncs (4
beeps × the pacing wait) at each `LEG_START` but emits no trace tags. Under `GAME_FLOW_FAST` the beep
pacing is shrunk to 2 Vsyncs/beep so the trace stays snappy; the beeps still fire (a PSG trace sees them).

## Sound (slice 3): making the wired triggers audible + proving it

Slices 1–2 left a fully-driven `SoundDriver` whose YM2149 stream `rm_refresh` returns but never plays.
Slice 3 (`render/atari/game_main.c`) plays it:

- **The VBL pump** — `vbl_sound` is spliced into `_vblqueue[0]` (a brief `Supexec`, since the queue +
  conterm are supervisor-only low memory and the shell runs USER mode) PRESERVING the displaced TOS
  entries — that is what keeps TOS's per-VBL Dosound stepper running (dropping them silences the
  countdown). Each vblank it writes `rm_refresh`'s (reg,val) stream to `0xffff8800/02` when the driver is
  RUNNING. PARKED = silent, exactly as the original's parked VBL vector.
- **Real Dosound** — under `-DRM_SOUND_TARGET` the shell's `rm_dosound` is `Dosound(SND_DOSOUND + off)`
  over the baked blob (`build/sound_dosound.h`, split out of `sound_data.h`), replacing `sound_trig.c`'s
  host ledger. The countdown / engine idle / crash effects play through it.
- **The countdown** — `race_start_countdown` fires `stop_music(BEEP)` ×3 + `stop_music(GO)` (`main`
  @0x10226), each paced by a Vsync wait; each `stop_music` parks the pump and hands the beep to Dosound.
- **VBL reentrancy** — the pump refreshes the SAME `SoundState` the main-loop triggers mutate.
  `RM_SOUND_LOCK`/`UNLOCK` (sound.h) bracket each `sound_trig.c` leaf's mutation; on target they are a
  nesting counter `snd_lock_depth` the pump skips a frame on (a VBL is atomic vs the main line, so this is
  full mutual exclusion; the window is µs, so a skip is rare + inaudible). They are no-ops on the host /
  bench builds, so the differential `.so` is byte-unchanged. An SR-mask would defer rather than skip but
  needs supervisor, which the user-mode shell hasn't got; the counter is correct in user mode.

**Proof (Hatari PSG trace).** Build the flow-auto variant, run it under a headless Hatari with
`--trace psg_write --msg-repeat`, and read the `ff8800`/`ff8802` writes back:

```bash
GAME_PRG=FLOWSND.PRG GAME_EXTRA_CFLAGS="-DGAME_FLOW_AUTO -DGAME_FLOW_FAST -DGAME_FLOW_TRACE -DGAME_TIME_LEFT=6" \
  bash render/atari/build_game.sh
hatari --sound off --fast-forward on --tos-res low --run-vbls 60000 --trace psg_write --msg-repeat \
  --trace-file /tmp/psg.txt --harddrive <dir-with-FLOWSND.PRG+data> --auto 'C:\FLOWSND.PRG'
```

A register write is a `ff8800=0xNN` (select reg NN) then `ff8802=0xVV` (value); `pc=e1xxxx` is TOS ROM
(the Dosound stepper), a lower `pc` is our REFRESH pump. The documented signatures, verified 2026-07-24:
the **countdown** = `reg 13 = 0x00` ×4 from Dosound (once per leg start), the **engine idle** = `reg 13 =
0x0e` repeating from Dosound, and **music** = regs 0–0xc from the REFRESH pump. `run_golden.py` still
MATCHes all 5 legs (sound is off-image) and the flow trace still closes at 19 records. Audio QUALITY (does
it sound right) is only verifiable by ear on real hardware / a sound-enabled Hatari — the trace proves the
right registers get the right values, not the timbre.

## Commands

```bash
cd ../recreate && make build/libbuggyboy.so   # once: the reference .so the harness drives
cd ../remaster
make test                                       # the gate: build the .so + BOTH on-target .PRGs + run the suite
make gate                                       # just the on-target builds (ST + STE), ~4 s
make golden                                     # END-TO-END: run the shipped shell in Hatari, 5 legs, ~20 s
make ref                                        # sanity: recreate's render pipeline is deterministic
```

`make test` now cross-compiles AND LINKS the game shell both ways before running the suite — see
"Harness gap #2" below for why. `make golden` is deliberately NOT part of it (needs Hatari, ~20 s); run
it before promoting to `main`.

Tests use `../recreate/.venv/bin/python` (numpy/pytest pinned there). `make test` runs `pytest -n auto`.

## Perf plan (2026-07-22 full-frame bench + drive distribution — numbers in STATUS "Perf")

**The 30 fps plan (audacious, per-stage, with the honest verdict on what a stock ST can reach) is in
[`PERF30.md`](PERF30.md)** — the measured gap table, tiered proposals (A = faster code, B = different
algorithm, C = fidelity trades), the ranked sequence with cumulative ms, and the arithmetic showing 30
fps pixel-faithful is not reachable on a stock ST (faithful ceiling ~16–18 fps median; 30 fps needs an
STE-blitter build). The ranked short list below is the near-term, already-scoped subset.

Baselines: recreate-parity median frame **180 ms (5.6 fps)** over real drives (min 138 / max 315);
the game today adds a redundant 96 ms clear on top. **These are the RECON/remaster compiled-C figures,
not the original.** The ORIGINAL binary runs the same frames at **~110 ms gate (9.1 fps) / ~82 ms
median (12.1 fps) / ~53 ms object-free (19 fps)** — measured three ways (PERF30.md Part 0). That is the
real Tier-A ceiling: hand-asm matching the original *is* ~12 fps median, a proven ~2× over the compiled
C, and the object tree / render_road each carry a measured ~2× of hand-asm headroom. The ranked
proposals, each byte-identical by construction and pinned by the existing differential tests:

1. **Drop the per-frame 32 KB `memset`** (game_main.c `draw_frame`) — recreate's own pipeline
   repaints every framebuffer byte, so clear each screen buffer once at boot and never again.
   −96 ms, trivial. Verify: `run_golden.py` MATCH plus a later-frame autodrive dump (a stale-byte bug
   would surface after the buffers have alternated, not on frame 0).
   **DONE 2026-07-22** — frame TOTAL 299 → 203 ms. `run_golden.py` MATCH, and the autodrive frame-2 /
   frame-61 dumps are byte-identical to a per-frame-clear build (both buffer parities).
2. **De-pointer the fine-x blitter loops** (`src/blit.c`) — the cell helpers take
   `Offset *col0/*col1/*sp`, so the loop state is address-taken and GCC keeps it in memory (the
   profile shows the spill shuffling directly). Restructure to value-in/value-out or inline the row
   loop. The engines are 99 ms on the gate frame, ~35 ms on a median frame; expect 25–40% off them.
   Pinned by `test/test_blit_engines.py` byte-exact fuzz.
3. **render_road display list** (50.7 ms every frame) — 67% is the per-scanline interpret-and-
   dispatch core; a per-frame plan (or per-band specialised writers) cuts the dispatch. Expect
   15–25 ms off. Pinned by `test/test_road.py` whole-framebuffer compares.
4. **draw_hud static/dynamic split** (17.4 ms) — the dashboard masked blit repaints unchanged pixels
   every frame; draw the static dashboard once per buffer, then per-frame only the dynamic cells
   (digits, gauges, blink, crash fx), restoring their background from the pristine dashboard first.
   Expect ~10 ms off. Needs per-buffer bookkeeping (two alternating buffers). Pinned by
   `test/test_hud.py`.
5. **blit_road_scroll top-fill dirty tracking** (part of 12.0 ms) — the constant fill above the band
   only changes when the horizon moves relative to that buffer's previous frame; skip it otherwise.
   Small and stateful; do last.

Projected landing zone (8 MHz ST): median **~60–75 ms ≈ 13–17 fps**, gate/tunnel frames ~8–10 fps.
Tier-A hand-asm alone lands at the original's measured **~12 fps median / ~9 fps gate** (PERF30.md
Part 0); the reach to 13–17 fps median comes from the algorithmic items (blitter de-pointer + display
list) doing less per-frame work than the original. 20 fps median is not reached by the original itself
(best object-light ~15 fps) — it needs everything landing plus light scenes; 30 fps needs a 16 MHz+
/ STE target or giving up pixel-faithfulness. Profile any candidate first:
`tools/profile.py bench_<stage> [--lines]`; re-check the distribution with `tools/frame_dist.py`.

## The recipe (porting one function)

1. **Read the target twice.** `recreate/src/<area>.c` for the idiomatic form, and the real disasm
   (`prg_dis.py` / `../decomp.c`) for anything subtle. Note every global it reads and every buffer it
   writes — and whether each write lands in the **framebuffer** or is **off-frame** state.
2. **Probe before you port.** Stage a realistic image, run the recreate `g_<fn>` on it, and diff the
   framebuffer to see its *footprint*. Then perturb each candidate input and re-diff to learn which
   inputs actually affect pixels (see the phase-8 probes in this session's history). This tells you
   what the candidate must reproduce and what it can skip.
3. **Model the inputs natively.** Dynamic scalars → fields in `HudState`/the relevant state struct
   (`include/game.h`). Static/asset bytes (tables, sprites, palettes) → `const uint8_t *` pointers in
   the assets struct, extracted by `test/adapter.py`. Keep it idiomatic — named fields, native types.
4. **Write the core** in `src/<area>.c` using the existing primitives (below). No `image + offset`.
5. **Extend the adapter** (`test/adapter.py`) to fill the new struct fields from the flat recreate
   image, and mirror the ctypes struct layout **exactly** (a mismatch shows up as wrong pixels).
6. **Write the differential test** (`test/test_<area>.py`) — see "Test shape" below — and iterate
   until it's **100 % of the footprint, 0 wrong pixels** (or whole-framebuffer exact for a leaf).
7. **Wire the on-target game** if it grew the structs: `render/atari/gen_game_fixture.py` (emit the new
   arrays/defines — the HUD's share of them lives in `gen_hud_fixture.py`) + `game_main.c` (fill the new
   fields), then re-run `run_golden.py` for a MATCH on every leg.
8. **Commit** green, with the test in the same commit; update STATUS.

## Conventions

**Types** (semantic, not just width): `Offset` = a byte offset/cursor into a buffer; `Plane4` = a
4-plane 16-px longword (two plane words); `Framebuffer *` = the draw target (compiler rejects passing
an asset buffer). Both `Offset`/`Plane4` are `uint32_t` aliases in `st.h`. Gate flags are C `bool`.
Asset buffers are `const uint8_t *`. Single plane words stay `uint16_t`. Don't invent a generic `Ptr`
or a `Byte` alias — they lose info or (for a pointer typedef) break `const`.

**Hardware bytes vs game state.** The framebuffer and asset tables are ST format (big-endian,
plane-interleaved) — read/write them through `be16/be32/wr16/wr32` in `st.h` (native `move` on the
m68k target, byte-assembled on the little-endian host, so the compared bytes match either way).
*Native game state* uses native C types and never goes through these.

**Blit primitives** — reuse, don't re-roll:
- `plane.h`: `cell_fill` / `cell_and` / `cell_overlay` — the three write patterns for one 4-plane cell.
- `text.h`: `rm_glyph_run` (paired-glyph text/gauge/bar body) and `rm_num_run` (digit/label sprites
  from `buf_c`). Both are validated against recreate's own `g_draw_*` entry points.
- `fill.h`: `rm_fill_span` / `rm_fill_words` / `rm_fill_screen` / `rm_fill_rect` — solid-colour fills
  from a `color_pairs` cell (recreate's `fill_span` family). Added for the between-legs flow's
  backdrops; reuse these rather than re-rolling a colour fill.

**The flip-derived draw buffer.** Most render leaves draw into `physbase_tbl[flip_idx]` (adda.w on the
word `flip_idx`), which is NOT always `SCREEN_BASE` — the between-legs surfaces are staged at both flip
parities. When a differential test's reference draws through `draw_dst`, extract the buffer at
`adapter.draw_buffer_addr(image)` (physbase_tbl[flip_idx]), not a fixed `SCREEN_BASE`; the remaster
`Framebuffer` abstracts the flip away (its `px[0]` IS the draw buffer), so the core never sees it.

**Adapter windowing patterns** (test-only bridge; the shipped game shares none of it):
- Extract just the bytes the function indexes, as a ctypes array kept alive via the returned tuple.
- **Rebase** a runtime offset into a compact window when the source offset is dynamic (see the phase-3
  `dsp_table`/`dsp_src`: each record's `src_off` is rewritten relative to the extracted window).
- **Cursor-zero pointer** for a signed-offset index: point at the middle of a padded window (see
  `color_bar_cidx`).
- **One shared mutable buffer** when several logical buffers alias one region in the original — copy
  it once, let the phases mutate it in order (see `hud_text`, which unifies the gauge string, the
  crash num/bar strings, the rollover records and the score).

**Test shape.** Prefer validating a leaf against recreate's *own* exported `g_<fn>` for a
whole-framebuffer exact match (that's how `rm_glyph_run`/`rm_num_run` are checked). Where recreate
only exposes a composite (e.g. `g_draw_hud`), use `test/equiv.py`'s **footprint coverage** +
**no-wrong-pixel** invariant, staging the composite's inputs to exercise each branch. Fuzz tests
parametrize by `chunk` for xdist.

## Gotchas (each of these cost real time)

- **Recreate's dst conventions differ per function.** `g_draw_num` takes a *buffer-relative* `dst_off`
  (`draw_dst` adds the draw buffer); `g_draw_hud_bar` takes an *absolute* dst. Check `draw_dst` usage
  in the recreate source before wiring a test, or the reference draws in the wrong place.
- **Asset windows must cover the full indexed range.** A table indexed by a byte *value* (e.g.
  `num_glyph_tbl[char*2]`) needs coverage up to the largest value used — digits `'0'`–`'9'` fit in a
  small window but letters/symbols index far past it. Sprite offsets from such a table can be large;
  size the window to `max_offset + sprite_height`. An undersized window reads zeros → wrong pixels.
- **Overlapping buffers.** HUD text buffers alias each other in the original (phases 1/2 write the
  speed/time digits that phase 7/8 then *draw*). Model the whole aliased region as one mutable copy.
- **Off-framebuffer state is skippable — but verify.** Sound, counters, and score arithmetic that
  isn't drawn can be omitted; but confirm by probing (the score *string* IS drawn via an overlapping
  bar buffer even though the score *BCD* isn't). When in doubt, perturb it and diff.
- **The differential test catches scaffolding bugs too.** Several "failures" this session were the
  adapter (window size, dst convention, ctypes layout), not the C. Suspect both.
- **Palette is off-image.** `Setpalette` is invisible to the byte-compare (which is palette-agnostic).
  The in-race palette is `A_race_palette` (0x17fa2); runtime fades aren't captured by the image model.

## Where things live

`include/assets.h` + `src/assets.c` load the game's own `COURSES.DAT` / `GRAPHICS.GRA` into one arena
(`rm_assets_unpack`, pinned byte-exact over the whole arena by `test/test_assets.py`). Asset *file*
bytes come from there; the original program's own data-segment tables (fonts, colour pairs, road
perspective/edge tables, the object jump table) are not file content and still come from the
adapter/fixture. `rm_assets_unpack` does no I/O — the caller supplies the two files' bytes, so the
core stays platform-free (GEMDOS `Fread` in `game_main.c`, a buffer poke in `test/assets_load.py`,
and a direct write into emulated memory in `tools/bench.py`, which has no filesystem).

**When you port a function that reads an asset**, point it at an arena region rather than growing the
fixture. `gen_game_fixture.py` emits only the *offsets* (`ARENA_*`) for arena-resident assets now; a
new baked array there is a smell unless it is genuinely program data-segment content.

**Fixture shrink (init_leg):** the game used to bake a `*_INIT` snapshot of the oracle's `init_leg`
output for every per-leg leg-start scalar (`PL_*`, `EV_*`, `PFX_*`, `SP_*`, `HUD_*`, `ROAD_*_INIT`,
`SCROLL_*_INIT`, `COURSE_*_INIT`, `COURSE_RING_INIT`, `OBJ_SHADE_INIT`, …). Those are all gone —
`rm_init_leg` produces the leg-start state natively at boot and on every restart. `gen_game_fixture.py`
now bakes only genuine program-data (the geometry const sources, the render_road static tables, the
obj-low table blob, the HUD asset arrays, the new `fixture_legtime` bonus-time strings) and the
arena-resident asset *offsets*. The one leg-start scalar that could still be considered baked — the
dashboard marker — is not: `init_leg` leaves it 0 (see the init_leg note above).

`include/` types + primitives · `src/` cores · `test/adapter.py` flat-image→struct bridge ·
`test/equiv.py` differential driver · `test/test_*.py` per-subsystem tests · `render/atari/` on-target
game. Workspace-wide conventions (name map, commit hygiene, the differential-vs-oracle bar) are in the
repo-root `CLAUDE.md`.
