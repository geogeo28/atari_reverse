# PORTING.md — how to continue the remaster port

For anyone (human or agent) picking up `remaster/`. Read [`README.md`](README.md) first for the
*contract* (pixel-identical to `recreate/` per frame) and [`STATUS.md`](STATUS.md) for *what's done*.
This doc is the *how*: the recipe, the conventions, and the traps.

`draw_hud` (all 8 phases) is ported and verified on host + on a real 68000. The render pipeline is now
complete: `render_road`, `blit_road_scroll`, `build_road_geometry`, and the whole `draw_game_objects`
tree (`draw_ground`, the buggy/foreground sprites, `draw_object`, the fine-x blit engines, the
`draw_object_list` dispatcher, and the prefix/orchestrator) are all byte-exact vs `recreate/`.

Phase B has started: the **player physics** (`src/player.c`, `game_update` §3,4,5,7,8,9,10) is ported
and verified frame-for-frame against `g_game_update`, and `render/atari/DEMO.PRG` is a playable buggy
on the 68000. What remains in `game_update` is the crash / auto-steer script (§6), object collision,
the horizon-event dispatch, and section 12's object ring — see STATUS.

A note on porting a *gameplay* function rather than a render one: there is no framebuffer to diff, so
the equivalence surface is the scalar state. `test/equiv.py`'s `compare_player_drive` is the pattern —
drive a scripted input, re-seed the candidate from the reference image each frame, and compare every
scalar the port owns. Two things made it honest: staging artefacts have to be cleared or the drive
degenerates (a mid-race image leaves `hud_crash_timer` armed, which pins the throttle off and the
buggy never moves), and frames where an *unported* system engages must be excluded and rolled back
explicitly, with a count reported, rather than silently tolerated.

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

`include/` types + primitives · `src/` cores · `test/adapter.py` flat-image→struct bridge ·
`test/equiv.py` differential driver · `test/test_*.py` per-subsystem tests · `render/atari/` on-target
demo. Workspace-wide conventions (name map, commit hygiene, the differential-vs-oracle bar) are in the
repo-root `CLAUDE.md`.
