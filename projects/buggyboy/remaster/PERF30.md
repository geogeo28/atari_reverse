# PERF30.md — the 30 fps plan (measured gaps + audacious per-stage proposals)

**Status: PROPOSAL. Nothing here is implemented.** This is the analysis and the ranked plan; the
implemented, verified perf work is in STATUS.md "Perf" and PORTING.md "Perf plan" (which now points
here). Every proposal below stays **byte-identical to the verified `recreate/` cores** and is pinned by
the existing differential + composed-frame harness — anything that trades pixels is called out
explicitly as **Tier C** with the fidelity cost stated.

Measurements taken 2026-07-23 on the cycle-accurate Musashi 68000 at 8 MHz, on CURRENT code
(`bench_build.sh` + `tools/bench.py` / `tools/frame_dist.py` / `tools/profile.py`). They reproduce the
STATUS "Perf" table exactly (no regression since the frame.c hoist).

> **REVISION 2026-07-23 — the baseline below was the wrong reference.** The "gap" figures in Part 1
> and the "5–6 fps original" framing were taken from the *recon / remaster GCC-compiled C*, never from
> the original game's own hand-written 68k. Measuring the **original binary** (three ways — see Part 0)
> shows it runs the same frames at **~9 fps gate / ~12 fps median / ~19 fps on an object-free stretch** —
> roughly **2× faster than the recon** the plan costed against. This does *not* raise the faithful
> ceiling to 30 (the original itself never reaches even 20 fps in the race), but it corrects the
> baseline, re-grounds every ratio, and turns the Tier-A hand-asm proposals from an estimate into a
> **measured, existence-proven ~2× lever**. Part 0 is the correction; Part 1's original table is
> superseded by Part 0's gap table.

---

## Part 0 — REVISION: the ORIGINAL binary's measured cost (the true baseline)

The whole of Part 1 costs the **recon** (`frame_dist.py` runs recon `g_draw_frame`; `bench.py`'s
per-stage rows are remaster-vs-recon) and never the original's own asm. The original *is* the faithful
implementation of these exact algorithms, so its measured cost is the real baseline and the real Tier-A
ceiling. It was measured three independent ways.

### Measurement 1 — the original binary on the cycle-accurate oracle (authoritative)

`emu.run()` executes the ORIGINAL image's own 68k. Its whole-frame wrapper is `draw_frame @0x12e22`
(build_road_geometry → render_road → blit_road_scroll → draw_game_objects → draw_hud — the exact
analog of recon `g_draw_frame`). Run on the **same staged frames** the remaster bench uses
(`gen_game_fixture.staged_image(0)` for the gate; `bench_frame.mid_race_state` legs 0/1/4 × warmups
0..600 for the distribution):

- **Gate frame** (staged leg-0 start gate, the frame `bench.py` costs): original `draw_frame`
  **880,376 cyc = 110.0 ms = 9.1 fps** (+game_update 22 k cyc → 8.9 fps).
- **Mid-race distribution** (63 frames): draw_frame **min 66.9 ms (14.9 fps) · median 82.8 ms
  (12.1 fps) · p90 101 ms (9.9 fps) · max 130 ms (7.7 fps)**.
- **Object-independent floor** (geometry+road+scroll+hud, the part that does *not* depend on object
  count): ~**53 ms ≈ 19 fps** across every sampled frame. `draw_game_objects` adds **13.6–76.7 ms**
  (median 30 ms) on top. So the frame rate is variable: ~19 fps on a clear stretch, ~12 fps median,
  ~9 fps at the gate/tunnel.

### Measurement 2 — the real game live in cycle-exact Hatari

The runnable original (`projects/buggyboy/bin/` — Atari's BUGGYBOY.PRG) booted headless (`hatari
--machine st --cpu-exact on --fast-forward on --run-vbls N`, SDL dummy video). `flip_screen @0x121f8`
writes the video-base register `$ffff8201` once per rendered frame; a value-change breakpoint
(`:trace :lock`, stamping `VBL=`) counts flips and their inter-flip vblank gaps. Over 6000 vblanks the
game's own rendering is **bimodal**:

- **Heavy render** (the animated buggy-sprite parade — same masked fine-x blit engine as the race's
  `draw_game_objects`): median **5 vblanks/frame = 10 fps**, range 3.6–12.5 fps.
- **Light game screens** (title / hi-score, drawn once then flipped): **1–2 vblanks = 25–50 fps**.
- **Whole-attract average: ~19 fps.**

The input-free attract loops the sprite-parade + title/hi-score and does **not** enter the road-driving
demo (that needs a start input headless Hatari can't inject), so the road-race fps rests on Measurement
1 — but Hatari independently confirms the original's hand-asm masked blitter runs a screen-full of
sprites at **~10 fps live**, matching the oracle's race numbers, and that light screens run 25–50 fps.

### Measurement 3 — per-stage spot-check on the gate frame (original vs remaster)

Same gate frame, per stage, original asm (`emu.run`) vs remaster C (`bench.py`):

| stage (gate frame) | **ORIGINAL asm** | remaster C | recon C | **orig/rm** (rm slower by) |
|--------------------|-----------------:|-----------:|--------:|---------------------------:|
| **object tree** (`draw_game_objects`) | **57.34 ms** (458,728 cyc) | 117.24 ms | 130.25 ms | **0.49× (rm 2.04× slower)** |
| **render_road** | **25.90 ms** (207,232) | 50.68 ms | 55.47 ms | **0.51× (1.96×)** |
| draw_hud | **12.29 ms** (98,346) | 17.47 ms | 17.20 ms | 0.70× (1.42×) |
| blit_road_scroll | **11.80 ms** (94,416) | 11.98 ms | 33.55 ms | **0.99× (parity)** |
| build_road_geometry | **2.42 ms** (19,378) | 3.87 ms | 3.91 ms | 0.63× (1.60×) |
| **whole draw_frame** | **110.05 ms** (880,376) | **201.22 ms** | **240.40 ms** | **0.55× (rm 1.83× slower)** |
| **→ fps** | **9.1** | **5.0** | **4.2** | |

**Reading it:** on *the fight* — the object tree — the original's hand asm is **2.04× faster** than the
remaster's compiled C, and 1.96× on render_road. `blit_road_scroll` is the one stage already at
**parity** with the original (1.01×) — the remaster's pre-rotation recovered original-level speed on
that *plain-copy* stage, which is exactly why it can't be repeated on the *masked* object blitters. The
"~240 ms original" that STATUS.md's Perf table cites is the **recon**, not the original; the original is
110 ms.

### What this corrects

- **Baseline:** the original is **~2× faster** than the recon figures Part 1 costed against — not 3.5×,
  and *not* 20 fps. The recon-parity model overstated the original's per-frame cost by **1.8× (gate) to
  2.2× (mid-race)**.
- **The "~20 fps" the game feels like** is real but is *not* the race frame: it is the object-free floor
  (~19 fps on open stretches), the attract's light screens (25–50 fps), and the mix average (~19 fps).
  The *driving* frame is ~12 fps median, dipping to ~9 at the gate/tunnel — the original's own hand-asm
  proves that is what these algorithms cost.
- **The faithful ceiling is now measured, not estimated.** Tier A (hand-asm, *same* algorithm) can at
  best **match the original** — so the pixel-faithful Tier-A ceiling is the original's own speed:
  **~12 fps median / ~9 fps gate**. Part 1's projected "16–18 fps median (Tier A+B)" sits *above* the
  original and is therefore reachable **only** via the Tier-B algorithmic wins the original does *not*
  do (pre-shifted sprites A2, road display list B2 — both do less per-frame work than the original).
- **Which proposals move:**
  - **A1 / A3 (value-pass + hand-asm blitter cores) GAIN the most** — the original is the *existence
    proof* that hand asm does the object tree at 0.49× the compiled C. This is now a measured ~2× lever,
    the biggest and safest win, not a hopeful estimate.
  - **A4 (per-band road writers) gains similarly** — render_road has a measured 1.96× of hand-asm
    headroom to recover before B2 (display list) is even needed to go *beyond* the original.
  - **blit_road_scroll is done** (already at original parity); B5 top-fill tracking is the only
    further, beyond-original nibble — low priority, as Part 1 already ranks it.
  - **Tier B (A2, B2, B4) is reframed:** it is the *only* path above the original's ~12 fps median,
    since it does work the original didn't. Valuable, but speculative relative to the now-proven Tier A.
  - **Tier C / STE unchanged:** 25 fps still needs C1 (+C2/C3 for the gate); 30 fps still needs C4 (STE
    blitter). The original's own 9-fps gate *reinforces* this — the hand-asm faithful game is 2.5–3.3×
    short of 30, so no amount of matching it reaches 30 faithfully on stock hardware.

**Corrected one-line verdict:** *the original hand-asm game runs these exact algorithms at ~9 fps gate /
~12 fps median / ~19 fps object-free — so the pixel-faithful Tier-A ceiling is ~12 fps median (matching
the original, a measured ~2× over today's compiled C), and 16–18 fps median needs the Tier-B
algorithmic wins on top. 20 fps faithful race is above the original itself; 25 fps needs Tier C; 30 fps
needs an STE. The original never ran at 20 fps in the race — that impression is the object-free floor and
the attract's light screens.* Reproduce: `../recreate/.venv/bin/python tools/bench_frame.py 0 60`
(original vs recon per stage) and Part 0's oracle/Hatari recipes.

---

## The target, in cycles

| target | ms/frame | cycles @ 8 MHz | how it maps to a 50 Hz ST |
|--------|---------:|---------------:|---------------------------|
| 50 fps | 20.0 | 160,000 | one vblank — the hardware frame |
| **30 fps** | **33.3** | **266,667** | 1.66 vblanks — *not* vsync-aligned on a 50 Hz machine |
| 25 fps | 40.0 | 320,000 | every 2nd vblank — the honest vsync-locked ST target (Tier C) |
| today (gate) | 203.2 | 1,625,796 | the staged leg-0 boot frame (start gate in view) |
| today (median) | ~155–160 | ~1.24 M | real drives, remaster ≈ 0.90× the recon median (180 ms) |
| **original (gate)** | **110.0** | **880,376** | the ORIGINAL asm on the same frame — **9.1 fps**, the Tier-A ceiling (Part 0) |
| **original (median)** | **82.8** | **662,470** | original mid-race — **12.1 fps**; object-free floor ~53 ms ≈ 19 fps |

30 fps on a 50 Hz display is itself a Tier-C choice: it cannot be vsync-locked (1.66 frames), so it
means either tearing or a 60 Hz/VGA modeset. The vsync-honest ST cadences are 50 / 25 / 16.7 fps. This
document keeps "30 fps" as the headline the task set, but the arithmetic below repeatedly shows **25 fps
(320,000 cyc) is the real ceiling to aim at**, and even that needs Tier C.

---

## Part 1 — the measured gap table

> **Reference note (see Part 0):** the `recon ms` column and the "recon-parity" framing below are
> the *compiled C*, not the original. The original asm runs this same gate frame at **110 ms (9.1 fps)**
> — Part 0's gap table is the corrected reference; the `rm/rec` ratios here still hold as *C-vs-C*, but
> the real headroom target for each stage is the **ORIGINAL** column in Part 0, ~2× under the remaster.

### Headline: where the frame goes (gate frame, `tools/bench.py`, current code)

| stage | remaster ms | cyc | % frame | recon ms | rm/rec | what the cycles are actually ON (profile) |
|-------|------------:|----:|--------:|---------:|-------:|-------------------------------------------|
| **objlist fixed pass** (`rm_blit_objshift2`) | **55.99** | 447,946 | **27.6%** | — | — | 97% in the blitter; **77,760 cyc (18%) is variable shifts** (`lsll`/`roll d5`), the rest word/long **RMW** `and`/`or` to the framebuffer |
| **objlist pass 1** (`rm_blit_objshift`) | **51.50** | 412,012 | **25.3%** | — | — | 87% in the blitter; shifts + **pointer-spill shuffling** (`movel sp@(x),sp@(y)` ~5.3 k cyc each), word RMW |
| **render_road** | **50.68** | 405,412 | **24.9%** | 55.47 | 0.91× | 67% in the per-scanline interpret-and-dispatch core; **33% in bands B/D** (near+far copies); dominated by pixel stores + per-row branches |
| **draw_hud** | 17.47 | 139,782 | 8.6% | 17.20 | 1.02× | 61% dashboard masked blit (`rm_draw_hud`), 34% `rm_glyph_run`, 5% memcpy |
| blit_road_scroll | 11.98 | 95,870 | 5.9% | 33.55 | **0.36×** | already optimised (pre-rotated copies + unrolled fill); top-fill is the remainder |
| draw_buggy | 5.16 | 41,298 | 2.5% | 5.22 | 0.99× | fine-x sprite (same engine family) |
| build_road_geometry | 3.87 | 30,970 | 1.9% | 3.91 | 0.99× | stamp loop; **runs twice on wrap frames — faithful, do not dedupe** |
| draw_fg_sprite | 2.40 | 19,196 | 1.2% | 2.39 | 1.00× | |
| ring_views + course + player + prefix | ~1.9 | ~15,000 | 0.9% | — | | scalar state, wrap-frame only |
| draw_ground | 1.16 | 9,290 | 0.6% | — | | |
| draw_object (scaled) | 0.89 | 7,146 | 0.4% | — | | empty-ish on this frame |
| objlist pass 2 | 0.09 | 688 | 0.0% | — | | empty on this frame |
| **TOTAL (frame)** | **203.2** | 1,625,796 | 100% | | | 30 fps needs this ÷ 6.1; median needs ÷ 4.7 |

**The three heavy stages are 78% of the frame** (158.2 ms of 203.2). No plan reaches 30 (or 25) fps
without collapsing all three. Everything else combined is 45 ms — already below a 25 fps budget on its
own, so the small stages are not where the fight is.

### Per-stage 30 fps budget (proportional share of 266,667 cyc)

If every stage shrank by the same factor to hit 30 fps, each must reach **0.164×** its current cost:

| stage | now (ms) | 30 fps share (ms) | must be | 25 fps share (ms) |
|-------|---------:|------------------:|--------:|------------------:|
| objlist fixed | 55.99 | 9.2 | 0.16× | 11.0 |
| objlist pass 1 | 51.50 | 8.4 | 0.16× | 10.1 |
| render_road | 50.68 | 8.3 | 0.16× | 10.0 |
| draw_hud | 17.47 | 2.9 | 0.16× | 3.4 |
| blit_road_scroll | 11.98 | 2.0 | 0.16× | 2.4 |
| everything else | 15.6 | 2.6 | 0.16× | 3.1 |
| **total** | **203.2** | **33.3** | | **40.0** |

The blitter and road budgets (8–9 ms) are the hard ones: `blit_road_scroll` already shows the best case
for this class of ST code — a **0.36×** cut from pre-rotation + unrolled fill on a *plain copy*. The
object blitters are *masked* (transparency RMW), so they cannot copy with `movem`; their realistic floor
is worse than 0.36×. See the honesty section.

### Frame-cost distribution (`tools/frame_dist.py`, recon `g_draw_frame`, legs 0/1/4 × warmups 0..600)

```
frames: 63   min 138.3 ms   median 179.8 ms   p90 221.4 ms   max 314.9 ms
fps:    best 7.2            median 5.6         worst 3.2
```

Remaster runs ≈ 0.90× the object tree and 0.36× the scroll blit, so the remaster distribution is
roughly **median ~155–160 ms, p90 ~195 ms, worst ~280 ms**. **The tail is the object tree**: a median
frame's tree is ~46 ms, the gate frame's is 117 ms (2.5×). What drives the tail:

- **the start gate** (the staged bench frame) — the gate sprite spans the road, filling both fine-x
  passes with wide straddle cells; near the worst case.
- **tunnels** — the mode-6 palette-poke scenes pack the object band.
- **object-heavy frames** generally — many roadside objects → many `blit_objshift` calls.

**Plan against the median (155 ms) but check every proposal on the gate frame (203 ms)**, because a
median-frame win that collapses on the gate is a stutter, not a speedup. The gate/tunnel frames are the
ones that will still miss any budget after a median-frame win.

---

## Part 2 — the proposals (per stage, tiered, no implementation)

Tiers: **A** = same pixels, faster code · **B** = same pixels, different algorithm · **C** = a fidelity
trade the user must sign off. Savings are estimates grounded in the profile; each names how the harness
pins it.

### Stage 1 — the two fine-x object blitters (107.5 ms, 53% of frame) — THE fight

These share a shape (straddle / left-edge / right-edge cells over a col0/col1 cursor pair, one scanline
up per row) and dominate the tail. Ranked:

**A1. Value-passing restructure of the cell loop.** *(Tier A, ~15–25 ms)* The cell helpers take
`Offset *col0/*col1/*sp`; GCC address-takes the loop state and keeps it in memory — the profile shows
`movel sp@(x),sp@(y)` spill shuffling at ~5.3 k cyc each in pass 1. Restructure to value-in / value-out
(return the advanced cursors, or inline the row loop so the cursors stay in registers). *Grounded:* the
spill lines are ~16 k cyc/pass of pure memory-to-memory moves that vanish when the cursors are
register-pinned. *Risk:* low — pure code shape, no arithmetic change. *Pinned:* `test/test_blit_engines.py`
byte-exact fuzz across every fine-x / dispatch case; `test_composed_frame` on crash frames.

> **LANDED 2026-07-23 (partial — objshift only; +8.65 ms of the gate frame).** The winning shape is a
> value-in/value-out cursor struct `ObjshCursor {col0, col1, sp}` passed by value through the (inlined)
> cell/row helpers, so GCC keeps the three cursors register-pinned. **`rm_blit_objshift` (pass 1):
> 412,012 → 342,668 cyc = 51.50 → 42.83 ms (0.83×, −8.67 ms)** on the gate frame. The three
> `movel sp@(x),sp@(y)` mem-to-mem moves are GONE from the disassembly (0 in the function; profile's
> spill lines eliminated, not relocated), and all `objsh_*` helpers inline (`objsh_edge_cell` needed
> `always_inline` — two call sites tripped GCC's size heuristic, which would re-spill the cursor across
> the call on edge sprites). Gate-frame TOTAL **1,625,796 → 1,556,552 cyc = 203.22 → 194.57 ms**
> (4.92 → 5.14 fps); object tree **117.24 → 108.58 ms (0.90× → 0.83×)**. Byte-exact: `make test` 558
> passed; `run_golden.py` MATCH on all 5 legs; `GAME_FLOW_AUTO` trace unchanged (19 records).
>
> **`rm_blit_objshift2` (fixed pass) does NOT take this change — reverted.** A1's spill premise is
> specific to pass 1: objshift2's baseline has **0** `movel sp@,sp@` mem-to-mem moves (its cell body
> walks col0/col1 in address registers via `wr32(dst + *col0)`, spilling the cursors to the stack only
> at row boundaries), and its cost is arithmetic/RMW-bound (`lsll`/`roll`/`orw`/`andl`/`orl`). Applying
> the value-struct shape there **regressed it +15,844 cyc (55.99 → 57.97 ms, +1.98 ms)**: forcing the
> cursors register-resident steals the address registers the RMW cell needs and spills the loop counter
> (`addql #1,sp@(44)`) instead. The other candidate shape (inlined cell bodies as plain locals) gives
> GCC the same IR freedom its already-inlined baseline has post-SRA, so it converges to baseline, not
> below — objshift2's by-pointer baseline is already optimal for its register pressure. Kept as-is with
> the rationale in a code comment. **Net A1 landed: the objshift half only.**

**A2. Pre-shifted compiled sprites (build-time, from the sprite data).** *(Tier A/B boundary, ~40–55 ms
— the single biggest lever after A1)* The 68000 variable shift is 8+2n cyc; the fixed pass spends 77,760
cyc (18%) in `lsll`/`roll` alone, and the mask is rebuilt from the source words every cell every row.
But **mask and pixel words depend only on (sprite, fine_x), never on the destination** — so for each of
the 16 fine-x phases precompute the shifted `pix` and `mask` word arrays once, at asset-load time, into
an arena (exactly as `rm_scroll_prebuild` pre-rotates the 16 playfield copies). The per-frame blit then
becomes: read pre-`mask`, read pre-`pix`, `dst = (dst & mask) | pix` — no shift, no mask build, and the
straddled 32-bit form can go long-at-a-time. *Grounded:* removes the 18% shift cost outright and the
per-cell mask-build (`~(a|b|c)&d`, several ops/cell); the scroll blit's analogous pre-rotation delivered
0.36× on a *plain* copy, so a masked RMW version plausibly lands 0.45–0.55×. *Cost:* arena memory for 16
pre-shifted copies of every roadside sprite (bounded — the same sprite set the scroll prebuild already
tables); build time at leg load (once, invisible to the frame). *Risk:* medium — the arena build must
reproduce the mask/pixel words bit-exactly, but it is verified against the *same* `test_blit_engines`
fuzz (the pre-shift table is just a memoised prefix of the current shift). *Pinned:* `test_blit_engines`
+ a new "prebuild == on-the-fly shift" equivalence test (like `test_mode2_scroll_prebuild`).

> **MEASURED SIZING 2026-07-23 (decision #1 — the memory budget, not yet landed).** Instrumented the
> three fine-x engines (guarded `BLIT_TRACE_SRC` touch-bitmap in `blit.c`, reverted) and ran a free
> flat-out drive per leg 0–4 (600 frames, composing the candidate's own object tree every frame) to
> record the **distinct** `buf_c` source bytes each engine actually reads. The min/max *span* wildly
> overcounts (it is mostly inter-sprite gaps); the distinct footprint is what the table must cover:
>
> | engine (stage) | distinct src (union 5 legs) | per-leg | calls/leg | leg-invariant? |
> |----------------|----------------------------:|--------:|----------:|----------------|
> | **objshift2** (fixed pass, 56.0 ms) | **3.0 KB** | 3.0 KB | 3 240 | **yes** — identical `gfx[32000..45604]` region every leg |
> | **objshift** (pass 1, 42.8 ms) | **8.8 KB** | ~8–9 KB | 25 k–72 k | mostly (shared sprites) |
> | objsprite (*not* an A2 target — the small stages) | 66.8 KB | 38–46 KB | 35 k–91 k | no |
>
> **A2 target (objshift + objshift2) = 11.8 KB distinct source.** The key finding: **objshift2 — the
> bigger 56 ms prize — reads only 3.0 KB of leg-invariant sprite data, and re-shifts it 3 240×/leg**;
> that is the ideal pre-shift target (build once at *boot*, not even per-leg). objshift's 8.8 KB is
> mostly shared across legs, so a per-leg build saves little over a whole-game build.
>
> **The expansion is the catch.** A masked straddle group is 8 source bytes but its pre-shifted form is
> 32-bit-per-word (it straddles two columns), so — unlike `rm_scroll_prebuild`, whose scrolled word
> stays 16-bit — the table cannot be a same-size offset-preserving window. Per 8-byte group per phase:
> full (pix + mask) ≈ 16–20 B, masks-only ≈ 4–8 B. Two layouts trade size vs addressing:
> *offset-preserving* over the **span** (simple `table[phase]+src_off`, blit unchanged) vs *compacted*
> over the **distinct** groups (needs a `src_off→idx` map). Resulting table sizes:
>
> | variant | objshift2 | objshift | both |
> |---------|----------:|---------:|-----:|
> | full, compacted (distinct) | ~98 KB | ~360 KB | **~458 KB** |
> | full, offset-preserving (span) | ~440 KB | ~1.4 MB | prohibitive |
> | masks-only, compacted | ~49 KB | ~72 KB | ~121 KB |
>
> **RAM verdict** (arena `RM_ARENA_BYTES` = 389 KB, plus two screen buffers ≈ 108 KB + overdraw tails,
> code, stack): on a **1 MB** ST there is room for **objshift2 full-compacted (~98 KB)** — the recommended
> first landing, capturing the 56 ms prize — but **not** both engines full (~458 KB blows the budget).
> objshift needs **masks-only (~72 KB)** or deferral to A3 (hand-asm; A1 already removed pass 1's spill).
> On a **512 KB** ST no full table fits — only masks-only objshift2 (~49 KB) is plausible; a pre-shifted
> build effectively **requires a 1 MB machine.** Before committing to full-vs-masks-only, measure the
> *split* of the 18% (`lsll` pix-shift, one op, vs `roll`+mask-build, multi-op): masks-only keeps the
> one-op pix `lsll` live and only fits captures the multi-op half. *Correctness note for the port:*
> objshift gates pix by a per-**call** colour fill (`color_pairs[color]`) applied after the shift, so
> the table stores the **pre-colour** shifted pix and mask (both colour-independent); the blit keeps the
> per-plane `& fill` and the RMW — i.e. even full A2 leaves the irreducible masked-blit RMW, consistent
> with the 0.45–0.55× estimate. The clip/edge/base/width dispatch stays as control flow (destination-
> dependent); only the per-cell compute becomes a table read. *Status: measured + designed; the
> bit-exact prebuild + rewired cells + equivalence test are the implementation, not yet built.*

**A3. Hand-asm cores with a jump-table entry per fine-x.** *(Tier A, ~10–20 ms on top of A1/A2)* Once
A1/A2 remove the spill and shift, the residual is word/long RMW to the framebuffer and per-cell
branching. A hand-written `.s` core (register-pinned cursors, unrolled straddle cells, `movem` where the
mask permits a run of opaque cells, a jump-table entry per fine-x so the shifted immediate is baked)
squeezes the RMW loop below what GCC emits. The C stays as the verified reference; the asm is pinned
byte-exact by the same fuzz. *Risk:* medium — asm is harder to keep faithful; gated behind A1/A2 landing
first so its target is stable. *Pinned:* `test_blit_engines` byte-exact fuzz (the asm core is a drop-in
replacement behind the same signature).

**B1. Frame-coherent object culling under dirty tracking.** *(Tier B, situational — 0 on the gate frame)*
Objects that did not move relative to the buffer need not redraw — but the road repaints the whole band
per scanline every frame *under* them, so an object is only skippable if nothing beneath it changed.
Feasible only jointly with a road dirty-rect (B-road below), and the road scrolls every frame, so on a
moving frame this saves nothing. Worth it only for **paused / menu / get-ready** frames where the scene
is static. *Verdict:* low priority; note it, do not build it first.

### Stage 2 — render_road (50.68 ms, 25% of frame)

**A4. Per-band specialised scanline writers.** *(Tier A, ~10–15 ms)* 67% is the interpret-and-dispatch
core that pulls a control long per scanline and branches on flag bits; bands B/D are 16.7%/16.3% each.
The flag combination is *stable within a band* for long runs — hoist the dispatch out of the per-scanline
loop into per-flag-combo specialised writers (one tight loop per variant), so the inner loop is a
straight column copy/fill with no per-row branch. *Grounded:* the per-row `cmpi`/`bne` chain and the
band B/D stores are the top PCs; removing the dispatch from the inner loop cuts the branch overhead.
*Risk:* low-medium — must enumerate the flag combos the data actually uses. *Pinned:* `test/test_road.py`
whole-framebuffer byte-exact across legs 0–4.

**B2. Road display list (precompute per-(curve,view) scanline programs).** *(Tier B, ~15–25 ms)* The
road geometry is a function of (curve, view-bank, near-slope); the per-scanline control stream is
recomputed every frame but only *changes* when those change. Precompute, per (curve,view) bucket, a
compact "scanline program" (the sequence of column-copy / fill / edge-mask ops) and replay it, so the
per-frame cost is a replay of straight writes, not an interpret. *Grounded:* the 67% core is
interpret-and-dispatch; a display list turns it into pure writes. *Risk:* medium — the bucket space
(curve × view × slope) must be bounded and the cache built/invalidated correctly; the double-build on
wrap frames (STATUS: **faithful, do not dedupe**) means the list is rebuilt, not shared, across the two
builds. *Pinned:* `test_road.py` + `test_geometry.py` (control table byte-exact under arbitrary steering)
+ `test_composed_frame`.

**B3. Half-horizontal-resolution road where the pattern allows.** *(Tier B — VERIFY FIRST, likely
rejected)* If the original's road texture is 2-pixel-doubled on some bands, those bands could be written
16-at-a-time from a doubled source. **This must be checked against the actual texture data before
claiming any saving** — the road is masked and edge-shaded per row, so most bands are *not* pattern-
doubled. *Verdict:* probably not pixel-faithful; if the data disproves it, drop it. Do not assume.

### Stage 3 — draw_hud (17.47 ms, 9%)

**B4. Static/dynamic dashboard split (already in the old plan).** *(Tier B, ~8–10 ms)* 61% is the
dashboard masked blit repainting unchanged pixels every frame. Draw the static dashboard once per
screen buffer at leg start; per frame restore only the dynamic cells (digits, gauges, blink, crash fx)
from the pristine dashboard, then redraw them. *Grounded:* the masked blit is 10.6 ms of static pixels.
*Risk:* medium — needs per-buffer bookkeeping across the two alternating screen buffers (a cell is dirty
on *this* buffer if it changed since *this* buffer's last frame, two frames ago). *Pinned:* `test_hud.py`
100%-footprint / 0-wrong-pixel, + `test_composed_frame` (which alternates buffers).

**A5. `movem`-based glyph/gauge fills.** *(Tier A, ~2–3 ms)* `rm_glyph_run` is 34%; where a run writes a
solid or aligned pattern, `movem` a register bank instead of word stores. *Pinned:* `test_text.py`
byte-exact.

### Stage 4 — blit_road_scroll (11.98 ms, 6%) — already 0.36×

**B5. Top-fill dirty tracking.** *(Tier B, ~3–5 ms, do last)* The constant fill above the band only
changes when the horizon moves relative to *this* buffer's previous frame; skip it otherwise. Small,
stateful, per-buffer. *Pinned:* `test_scroll.py` whole-framebuffer + a later-frame autodrive dump (a
stale-fill bug surfaces after the buffers alternate, not on frame 0).

### Stage 5 — small stages (buggy/fg/ground/object, ~9.6 ms combined)

`draw_buggy` and `draw_fg_sprite` are the **same fine-x engine family** as Stage 1 — A1/A2/A3 carry
straight over (the buggy is one more `objsprite` caller). No separate proposal; they ride the blitter
work. Ground/object are already small.

---

### Tier C — departures that need sign-off (each flagged with the fidelity trade)

**C1. 25 fps vsync-locked instead of 30.** *(the honest ST target)* Render every 2nd 50 Hz vblank → a
**40.0 ms / 320,000 cyc** budget (20% more than 30 fps) that is *tearing-free* on a stock 50 Hz display,
which 30 fps is not. **Fidelity trade: none in pixels — only the frame rate label changes** (25 vs 30).
*Harness:* no change; it is the same pixel-faithful frame, just presented at a locked cadence. This is
the single most valuable Tier-C item because it *raises the budget* while keeping full fidelity, and it
makes the presentation vsync-honest.

**C2. Reduced road band height / letterbox.** *(Tier C, ~10–20 ms off render_road + blitters)* Shrink
the drawn road band (letterbox top/bottom). **Fidelity trade: fewer scanlines of road/scenery drawn —
visibly different framing.** *Harness:* a separate non-pixel-faithful build profile with its **own**
goldens (the byte-compare against `recreate/` no longer holds — this is a different picture). A knob
(`ROAD_BAND_ROWS`) whose default is the faithful value; the reduced value ships as a distinct build with
its own per-leg goldens.

**C3. Interlaced far-scenery update (odd/even frames).** *(Tier C, ~15–25 ms off the object tree)* Update
distant/small objects every *other* frame (near objects every frame). **Fidelity trade: far scenery
updates at 12.5 fps while near updates at 25 — visible on fast pans/tunnels.** *Harness:* not pixel-
faithful frame-to-frame; needs its own goldens sampled on the matching parity, and the composed-frame
differential can only pin the *near* half strictly.

**C4. STE-only build (blitter chip + hardware scroll).** *(Tier C, the only credible 30 fps path)* On an
STE the hardware blitter does masked block moves far faster than the 68000 RMW loop, and hardware
fine-scroll offloads `blit_road_scroll` entirely. **Fidelity trade: none in pixels — but it is a
separate binary that will not run on a stock ST.** *Harness:* a separate build target; the *pixels* are
still pinnable against `recreate/` (the blitter produces the same bytes), so the existing byte-compare
holds on STE hardware/emulation. This is the honest way to say "30 fps" out loud.

**C5. Palette tricks to fake work.** *(Tier C, situational)* Colour-cycling / palette animation to
simulate motion the CPU didn't draw (e.g. a scrolling texture faked in the palette). **Fidelity trade:
the framebuffer bytes differ from `recreate/`** — off-image already (Setpalette is a documented seam),
so it is invisible to the byte-compare but also *unverified* by it. Narrow applicability; note, don't
lead with it.

---

## The sequence (which items first, cumulative ms, when a budget becomes reachable)

Costs are the gate frame (203 ms) so the sequence is judged at the worst case; the median (~155 ms)
tracks it at roughly 0.75×. Savings are the *mid* of each estimate.

| # | item | tier | stage now | after | gate total | gate fps | median fps |
|---|------|------|----------:|------:|-----------:|---------:|-----------:|
| 0 | *baseline (memset already dropped)* | — | | | 203 | 4.9 | ~6.5 |
| 1 | **A1** value-pass blitter loops | A | 107.5 | ~87 | ~183 | 5.5 | ~7.5 |
| 2 | **A2** pre-shifted compiled sprites | A/B | 87 | ~45 | ~141 | 7.1 | ~10 |
| 3 | **A4** road per-band writers | A | 50.7 | ~38 | ~128 | 7.8 | ~11 |
| 4 | **B2** road display list | B | 38 | ~26 | ~116 | 8.6 | ~12.5 |
| 5 | **B4** HUD static/dynamic split | B | 17.5 | ~8 | ~107 | 9.3 | ~14 |
| 6 | **A3** hand-asm blitter cores | A | ~45 | ~32 | ~94 | 10.6 | ~16 |
| 7 | **B5** scroll top-fill tracking | B | 12 | ~8 | ~90 | 11.1 | ~17 |

**Landing zone with all of Tier A+B (pixel-faithful): gate ~90 ms (~11 fps), median ~55–60 ms
(~16–18 fps).** That matches and slightly extends the existing plan's 13–17 fps median / 8–10 fps gate.

**When each budget becomes reachable:**

- **30 fps (266,667 cyc / 33 ms):** not reachable on a stock ST with any combination of Tier A+B. The
  arithmetic below shows why. Reachable only via **C4 (STE blitter build)**, or **C1+C2+C3 stacked**
  (25 fps cadence + letterbox + interlaced scenery), which is no longer the faithful picture.
- **25 fps (320,000 cyc / 40 ms):** reachable *on median/good frames* after items 1–6, but **the gate
  and tunnel frames still miss it** (~90 ms). Making 25 fps hold on the gate frame needs one Tier-C
  item — **C1 (the 40 ms budget itself)** plus **C3 (interlaced far scenery)** or **C2 (letterbox)** to
  pull the gate frame under 40 ms. So: **25 fps median is Tier A+B; 25 fps floor (gate included) is
  A+B+C1+one of C2/C3.**
- **~16–18 fps median:** reachable pixel-faithful with the full Tier A+B sequence. This is the honest
  "how fast can the faithful remaster go on a stock ST" answer.

> **Part 0 cross-check on this landing zone:** Tier A *alone* (hand-asm matching the original) lands at
> the original's measured **~12 fps median / ~9 fps gate** — that half of the "16–18 fps" is now
> *proven*, not projected. The remaining lift to 16–18 comes entirely from the **Tier-B** items (A2
> pre-shifted sprites, B2 road display list) that do *less* per-frame work than the original — so
> 16–18 fps median is credible only if those land; without them the faithful ceiling is the original's
> ~12 fps. Either way the **gate frame stays ~9–11 fps**, the binding constraint below.

---

## Honesty section — what this plan does NOT believe is reachable

**30 fps pixel-faithful on a stock 8 MHz ST is not credible — the ORIGINAL hand-asm game itself proves
it (Part 0): it runs these exact algorithms at ~9 fps gate / ~12 fps median, 2.5–3.3× short of 30.**

The three heavy stages are 158 ms and must fall to **~26 ms combined** (0.164×) to hit 30 fps. Consider
the physical floor for the object blitters:

- They are **masked** blits (transparency): every cell is a read-mask-OR-write to the framebuffer. Even
  with A2 (pre-shifted, no shift, no mask build) the irreducible per-cell work is `dst = (dst & mask) |
  pix` — that is a framebuffer **read + and + or + write** per plane-word, and it cannot become a
  `movem` copy the way the *plain* scroll blit did (the scroll blit hit 0.36× precisely because it
  copies, not masks).
- The gate frame issues enough straddle cells that even at an optimistic **0.45×** the two passes are
  107.5 → ~48 ms. Add render_road at an optimistic 0.55× (28 ms) and the rest at 0.7× (~30 ms): the gate
  frame floors around **90–105 ms ≈ 10 fps**. That is 3× short of 30 fps and ~2× short of 25 fps.
- To claw another 3× out you must **stop drawing pixels** — dirty-rect the road (but it scrolls every
  frame, so the dirty region *is* the whole band on a moving frame), interlace the scenery (C3, not
  faithful), or letterbox (C2, not faithful). There is no faithful algorithm left once the road repaints
  per scanline every frame, which it must, because the original does.

**The credible faithful ceiling is ~16–18 fps median / ~10–11 fps gate** (full Tier A+B). This is
consistent with, and slightly better than, the existing plan's 13–17 fps. **Part 0 anchors the lower
half of that as measured fact:** Tier A alone (matching the original hand-asm) *is* ~12 fps median /
~9 fps gate — the original's own speed — and the reach to 16–18 depends on Tier B doing work the
original didn't.

**The Tier-C combination that actually reaches 30 fps:** **C4 (STE hardware-blitter build)** — the
STE blitter does the masked block moves in a fraction of the 68000 RMW cost and hardware fine-scroll
removes the scroll blit, so 30 fps becomes plausible *while keeping the pixels byte-identical to
`recreate/`* (the blitter emits the same bytes). It is a **separate binary** that will not boot on a
stock ST — that is the honest cost. On stock hardware, the honest target is **25 fps vsync-locked
(C1)** with the full Tier A+B stack, and even then the **gate/tunnel frames need C2 or C3** (a
fidelity trade) to hold the floor.

**One-line verdict** *(revised — see Part 0):* *the ORIGINAL hand-asm game runs these algorithms at
~9 fps gate / ~12 fps median / ~19 fps object-free, so the pixel-faithful Tier-A ceiling is ~12 fps
median (matching the original — a measured ~2× over today's compiled C, the biggest proven lever), and
16–18 fps median needs the Tier-B algorithmic wins on top. 30 fps pixel-faithful is out of reach — the
original is 2.5–3.3× short of it. 30 fps is an STE-blitter build (C4, still byte-faithful) or a
stock-ST build that gives up pixel fidelity (C1+C2+C3). 25 fps median is reachable faithfully only with
Tier B; 25 fps with the gate frame included needs one Tier-C item. The original never ran at 20 fps in
the race — that impression is the object-free floor (~19 fps) and the attract's light screens (25–50
fps), not the driving frame.*

---

## Reproduce the measurements

```bash
cd projects/buggyboy/remaster
bash render/atari/bench_build.sh                       # build bench.elf
../recreate/.venv/bin/python tools/bench.py            # per-stage gate-frame table
../recreate/.venv/bin/python tools/frame_dist.py       # median / p90 / gate distribution
../recreate/.venv/bin/python tools/profile.py --lines 10 bench_objlist_fixed   # hot PCs
../recreate/.venv/bin/python tools/profile.py --lines 10 bench_render_road
```

Every proposal is verified byte-exact by the existing harness before it lands: the per-stage
differential tests (`test_blit_engines` / `test_road` / `test_hud` / `test_scroll`), the composed-frame
differential (`test_composed_frame`), and the on-target per-leg goldens (`run_golden.py` MATCH on legs
0–4). A Tier-C item that trades pixels ships as a **separate build profile with its own goldens**, never
under the `recreate/` byte-compare.

### A2 implementation attempt 2026-07-23 — BLOCKED, expectations corrected

Measured before implementing (scratchpad/analyze_groups.py; 648 distinct 4-byte straddle groups
in 125 runs, 129 right-edge, dense span [32000,45596]):
- **The A2 win was over-estimated ~5×**: only 17.4% of objshift2's cycles are shifts (77,760 cyc);
  the masked RMW majority (dst read + and + or + write per plane-word) is irreducible by a table.
  Honest full-table payoff **~8–11 ms** (objshift2 55.99 → ~45–48 ms), masks-only ~6 ms.
- **RAM blocker**: the shipping game.elf is **927 KB** (arena 389 KB + screen_pool 326 KB —
  SCREEN_OVERDRAW 0x20000 per screen, ~4× the apparent max object reach — + shifted 106 KB + text).
  The full table (dense arithmetic addressing, 638 KB; compacted, ~128 KB) does not fit a literal
  1 MB ST; the compacted idxmap is UNSOUND besides (the group set is object-record-driven, not
  boot-enumerable — a missed group = visual corruption). The 4 MB Hatari harness would not catch
  the overflow.
- **Path if A2 is still wanted**: right-size SCREEN_OVERDRAW first (measure the true max write
  reach; 0x20000 → ~0x8000 frees ~192 KB), then the DENSE table fits 1 MB with margin.
- **Rerank consequence**: A3 (hand-asm cores) now dominates — the original's asm is the measured
  proof of ~2× on the whole object tree (~50 ms available) vs A2's corrected ~8–11 ms.
