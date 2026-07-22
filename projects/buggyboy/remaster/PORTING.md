# PORTING.md — how to continue the remaster port

For anyone (human or agent) picking up `remaster/`. Read [`README.md`](README.md) first for the
*contract* (pixel-identical to `recreate/` per frame) and [`STATUS.md`](STATUS.md) for *what's done*.
This doc is the *how*: the recipe, the conventions, and the traps.

`draw_hud` (all 8 phases) is ported and verified on host + on a real 68000. The render pipeline is now
complete: `render_road`, `blit_road_scroll`, `build_road_geometry`, and the whole `draw_game_objects`
tree (`draw_ground`, the buggy/foreground sprites, `draw_object`, the fine-x blit engines, the
`draw_object_list` dispatcher, and the prefix/orchestrator) are all byte-exact vs `recreate/`.

Phase B has started: the **player physics** (`src/player.c`, `game_update` §3,4,5,6,7,8,9,10) is
ported and verified frame-for-frame against `g_game_update`, and `render/atari/DEMO.PRG` is a playable
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

Last verified: 2026-07-22. `make test` = **361 passed, 1 skipped**. Section 12's **object / marker
ring** is ported (`CourseRing` in `include/game.h`, `rm_road_course_advance` in `src/course.c`) and
its four aliased consumers are unified onto it (see below). The next chunk is section 12's tail:
the collision probe, the fx block, and the horizon-event dispatch — the system that decides to
crash you and ends a leg.

### What the ring port did and did not fix

The previous revision claimed one missing subsystem explained three symptoms. That was **one for
three** — worth recording, because the reasoning error is repeatable:

| Symptom | Status |
|---|---|
| `compare_leg_drive` hands the road control table over every frame | **fixed** — the table is now a compared result, and the ring is compared band by band |
| `run_demo.py` reports `DIFF 1110/32000` | **not fixed, and the ring was never a candidate** — the diff is present at frame 0, before any course advance runs, so a static-vs-scrolling ring could not have caused it |
| The start pole stays put as you drive | **fixed by the consumer unification below** — a frame-300 autodrive shows the course scenery arriving (tunnel approach), not the leg-start objects |

The lesson: a symptom that appears on **frame 0** cannot be explained by state that only diverges
once something has advanced. Check the frame index before attributing a symptom to a scroll.

### The ring's consumers are unified — every view now derives from the live `CourseRing`

The demo used to hold the ring twice: `rm_build_road_geometry` read the live ring while four other
consumers read the *frozen* copy baked into `fixture_obj_low`, so the road's flags animated while
the scenery stayed at fixture-generation values. All four now derive from the live ring
(`src/course.c` helpers, wired in `demo_main.c`, refreshed after every course advance):

- the object-list dispatcher's two flag streams walk `rm_ring_store_st`'s serialized ST-byte mirror
  (row 1 for the sprite passes, row 12 for the fixed pass) — the dispatcher keeps its flat-bytes
  contract, the mirror is just the ring in the original's own row-grid layout;
- `rm_ring_sprite_count` replaces the demo's flat-image marker walk;
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
tests pin the *address arithmetic*. The demo *wiring* itself has no host test (`make test` never
runs `demo_main.c`) — it is verified on-target by the golden frame-0 compare and autodrive runs.

**Known limitation, inherent until the event dispatch is ported:** the fixed-object pass and
`GroundState.markers[12]` consume ring bands 12/13's slot words, which the leg drives verify only
by marker — the unported horizon-event dispatch clears bytes there in the original, so those
bands' values are faithful to the ring but not yet to the dispatch.

### Recently fixed (kept here until the next STATUS pass)

**`build_road_geometry`'s write past the end of `ctrl`** is fixed by allocation, not clamping: the
stamp loop's spill (2 bytes on view bank 0, 6 on banks 2/4/6) is faithful to the original, so every
ctrl buffer is now sized `RM_CTRL_ALLOC_BYTES` (= `RM_CTRL_BYTES + RM_CTRL_STAMP_SPILL`). Two pins
keep it honest, because no ctrl comparison can see an under-sized pad (they all stop at
`RM_CTRL_BYTES`): `test_course_ring.test_python_constants_match_the_c` pins the game.h/adapter.py
copies equal, and `test_geometry.test_stamp_spill_stays_within_alloc` poison-pins the pad to the
stamp's measured write extent per view bank.

**Esc returning to a frozen picture** is fixed: the demo captures `Physbase()` and the 16 palette
registers (`Setcolor(reg, -1)`) before taking the screen, and restores both on exit — base only
would hand back a desktop drawn in the racing palette.

### Two dead ends — do not repeat them

- **The IKBD is not the problem.** A raw byte log of everything the ACIA delivered showed only
  well-formed make/break pairs — no stray mouse/joystick packet bytes reaching `key_down[]`. The
  "packet noise corrupts key state" theory is refuted by evidence.
- **Seeding the demo's `ctrl` from the leg's control table does nothing.** `draw_frame` rebuilds
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

Three build flags, all off in normal builds, set via `DEMO_EXTRA_CFLAGS`:

```bash
# bisect a divergence to one render stage (0 road, 1 ground, 2 foreground, 3 pass 1)
DEMO_EXTRA_CFLAGS="-DDEMO_DUMP_STAGE=0" bash render/atari/build_demo.sh

# drive a fixed script headlessly and log per-frame course state to SCREEN.BIN (8 BE words/frame:
# frame, read_pos, row_ctr, speed, rpm, collision_lock, hud_crash_timer, view_wrapped)
DEMO_EXTRA_CFLAGS="-DDEMO_AUTODRIVE=600 -DDEMO_TRACE=600 -DAUTODRIVE_STEER_AFTER=100000" \
  bash render/atari/build_demo.sh

# interactive session: log every raw IKBD byte + the per-frame trace to KEYLOG.BIN on quit
DEMO_EXTRA_CFLAGS="-DDEMO_KEYLOG -DDEMO_TRACE=2000 -Wa,--defsym,KBD_RAWLOG=1" \
  bash render/atari/build_demo.sh
```

`run_hatari.RUN_VBLS` defaults to 4000, which is **not enough for a long trace** — a frame costs ~84 ms
(≈4 vbls), so a 600-frame run needs ~60000 and a raised `timeout=`. Set both when driving headlessly,
or the run dies with "did not produce SCREEN.BIN" and looks like a build failure.

A trace run necessarily reports `DIFF` from `run_demo.py`: `golden.bin` is frame 0 and the dump is
frame N (or telemetry). That is the run working, not failing — a `MATCH` there would mean nothing moved.

## Commands

```bash
cd ../recreate && make build/libbuggyboy.so   # once: the reference .so the harness drives
cd ../remaster
make test                                       # build the candidate .so + run the equivalence suite
make ref                                        # sanity: recreate's render pipeline is deterministic
bash render/atari/build.sh && python render/atari/run_hatari.py   # on-target: prints MATCH
```

Tests use `../recreate/.venv/bin/python` (numpy/pytest pinned there). `make test` runs `pytest -n auto`.

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
7. **Wire the on-target demo** if it grew the structs: `render/atari/gen_hud_fixture.py` (emit the new
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
core stays platform-free (GEMDOS `Fread` in `demo_main.c`, a buffer poke in `test/assets_load.py`,
and a direct write into emulated memory in `tools/bench.py`, which has no filesystem).

**When you port a function that reads an asset**, point it at an arena region rather than growing the
fixture. `gen_demo_fixture.py` emits only the *offsets* (`ARENA_*`) for arena-resident assets now; a
new baked array there is a smell unless it is genuinely program data-segment content.

`include/` types + primitives · `src/` cores · `test/adapter.py` flat-image→struct bridge ·
`test/equiv.py` differential driver · `test/test_*.py` per-subsystem tests · `render/atari/` on-target
demo. Workspace-wide conventions (name map, commit hygiene, the differential-vs-oracle bar) are in the
repo-root `CLAUDE.md`.
