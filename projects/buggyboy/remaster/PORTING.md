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
stays deferred), and the leg-select nav (`rm_init_playfield_nav`/`_fire`). Each is differential vs
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
leg-start frame (byte-identical to `golden.bin`). The `game_main.c` `#ifdef BOOT_FAST_LEG` block carries
that fast path and is compiled ONLY when `GOLDEN_BOOT_LEG` (the golden harness) or `GAME_AUTODRIVE` (the
headless race trace, which can't drive the menu with a dead keyboard) is defined. Coverage seam worth
naming: the shipping cold-boot leg-select branch (the `#else` of that `#ifdef BOOT_FAST_LEG`) is
exercised ONLY by the manual `GAME_FLOW_AUTO` flow-trace recipe — `make test` builds no `.PRG` at all,
and `run_golden.py` compiles the `BOOT_FAST_LEG` branch (the golden variant skips the leg select). So
the leg-select-first boot path is on-target-only, proven by that trace. Proven on the 68000
(see the flow-trace section below): booting into the leg select, its fire starting a leg, a timed-out
leg reaching the intermission, a full attract cycle (A→B→C→D→restart), and the return to the leg select
— the whole game loop closes unattended. **Legs 1–4 are playable, but only leg 0 has a golden**
(`GOLDEN_BOOT_LEG=0`); a per-leg golden is deferred, not attempted here.

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

The seams the shell stands in for, each documented at its call site in game_main.c: sound (never
played), the exact Vsync cadence, the per-phase palette Setpalettes (off-image — the byte-compare is
palette-agnostic, including the leg-start flash's own animated palette), the interactive high-score
NAME-ENTRY tail (update_highscore ranks + inserts the score so the results screen fills in, but the
IKBD initials screen is not run — recreate defers it too), and the attract DEMO's input-replay (Phase C
holds throttle instead of replaying a recorded ghost). `init_scoretable`'s output is baked as a
program-data SEED (`fixture_highscore`) the shell copies into a mutable `highscore_ram` at boot, exactly
as `fixture_hud_text` seeds `hud_text_ram` — the tiny init routine is not run on-target (its output is
deterministic program data).

Last verified: 2026-07-22. `make test` = **499 passed**; `run_golden.py` = **MATCH** (leg-0 frame-0 golden). Section 12's **object / marker
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
from `rm_init_leg` (native init is drive-equivalent). Two phases are documented exceptions, neither a
compared surface: phase 3's checkpoint-banner draw (gfx-only, regenerated by `rm_course_events`; the
golden renders from the fresh arena) and phase 11's palette-staging record (feeds the unported
mode-2/4/6 palette event — only its `obj_shade` output is consumed). **The game boots AND restarts
through `rm_init_leg`** (`game_main.c` `start_leg`: reset the owner structs, then derive the views via
`apply_player` + `ring_views_refresh` before the frame-0 draw), so the fixture no longer bakes any
per-leg leg-start scalar (see the fixture-shrink note below). Verified on the 68000: `run_golden.py`
MATCH (frame 0 reproduced natively), and the idle leg-end autodrive restarts through `start_leg`
cleanly (timer → negative → `abort_flag` 0xffff → reset to 0, no re-arm/hang). One honest correction
the port turned up: the oracle's `init_leg` (0x104b8) does NOT seed the dashboard marker — it stays 0
at a leg start; the per-leg arena reseed is the intermission's `init_leg_dash` (already ported in
`events.c`), which fires on a checkpoint. The baked `EV_DASH_*_INIT` were therefore 0 and are simply
dropped.

Still unported (documented at each call site, per convention): off-frame sound (INITTUNE/INITFX/
TURNOFF, the VBL vector; `rev_reload` aliases `lean_frame` and is invisible to every compared
surface — verified, not assumed); the record-driven mode-2/4/6 palette / screen-offset events in
`game_update_course_advance`'s tail; and the interactive high-score name-entry tail + the attract
input-replay (both off-image seams the game shell documents). The intermission / results / highscore
flow AROUND `init_leg` is ported (slice B) AND now composed on-target in place of the leg-restart
stand-in (slice C, above).

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

**Esc returning to a frozen picture** is fixed: the game captures `Physbase()` and the 16 palette
registers (`Setcolor(reg, -1)`) before taking the screen, and restores both on exit — base only
would hand back a desktop drawn in the racing palette.

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
  "packet noise corrupts key state" theory is refuted by evidence.
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
- **The data may not reach a branch at all.** Of the four `marker_unpack` outcomes, "right shoulder"
  appears in 25 records — all in leg 3 — and "both shoulders" in **none** of the 5120. Pin what the
  data can reach by *seeding `read_pos` onto a real record* (`test_ring_hard_to_reach_branches`);
  say so in `STATUS.md` for what it cannot, and never fabricate a record to manufacture a green tick.

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
so the **whole loop closes**. The attract Phase C also RACES the picked leg (leg 1 here) through the real
pipeline for 6 frames without hanging — on-target evidence that a non-zero leg's race runs. Decode with a
runner that sets `RUN_VBLS` high and parses the log words (a `run_flow.py` scratch helper; the trace is
the on-target guard, as `make test` never runs game_main.c). This is a deliberate re-pin from the old
boot-into-leg-0 sequence, which used to lead with `LEG_START 0`.

## Commands

```bash
cd ../recreate && make build/libbuggyboy.so   # once: the reference .so the harness drives
cd ../remaster
make test                                       # build the candidate .so + run the equivalence suite
make ref                                        # sanity: recreate's render pipeline is deterministic
bash render/atari/build.sh && python render/atari/run_hatari.py   # on-target: prints MATCH
```

Tests use `../recreate/.venv/bin/python` (numpy/pytest pinned there). `make test` runs `pytest -n auto`.

## Perf plan (2026-07-22 full-frame bench + drive distribution — numbers in STATUS "Perf")

Baselines: recreate-parity median frame **180 ms (5.6 fps)** over real drives (min 138 / max 315);
the game today adds a redundant 96 ms clear on top. The ranked proposals, each byte-identical by
construction and pinned by the existing differential tests:

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
20 fps median is the stretch ceiling if everything lands (hand-asm blitter cores after item 2);
30 fps needs a 16 MHz+ target or giving up pixel-faithfulness. Profile any candidate first:
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
7. **Wire the on-target game** if it grew the structs: `render/atari/gen_hud_fixture.py` (emit the new
   arrays/defines) + `main.c` (fill the new fields), then re-run `run_hatari.py` for a MATCH.
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
