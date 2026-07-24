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

### Instruction-level original-vs-remaster comparison 2026-07-23 — where the 2× actually is

Per-PC cycle profiles of BOTH sides on the same gate frame (original `draw_game_objects` run under
the profiling `run_bench` via an A6-staging trampoline — scratch tooling, reproduces Part 0's
458,728 cyc; remaster via `tools/profile.py`'s machinery with a full annotated listing). The
object-tree gap is NOT uniform and NOT mysterious:

| engine | ORIGINAL | remaster (post-A1) | ratio | gap |
|--------|---------:|-------------------:|------:|----:|
| blit_objshift2 (fixed pass) | 262,940 cyc = 32.9 ms | 435,940 = 54.5 ms | **1.66×** | 21.6 ms |
| blit_objshift (pass 1) | 110,572 = 13.8 ms | 288,256 = 36.0 ms | **2.61×** | 22.2 ms |
| buggy (objsprite family) | 45,014 = 5.6 ms | ~41,300 = 5.2 ms | **0.92× — rm WINS** | — |
| dispatcher + objsprite rest | ~25,900 | ~66,500 | ~2.6× | ~5 ms |

The buckets reconcile against the measured gaps almost exactly (objshift2: +163 cyc/cell × 648
cells + +282 cyc/row × 242 rows = 173.9k vs 173.0k measured; objshift: both sides run the same
190 rows — orig 582 cyc/row vs rm 1,517). Five concrete mechanisms, ranked:

1. **Stack traffic (the "extra memory instructions").** rm_blit_objshift spends **~72k cyc = 9 ms
   (25% of the function)** in `sp@`-relative loads/stores/RMW: colour-fill halves re-read from the
   stack per plane, the pix word spilled to `sp@(44)` and re-read, row bounds/rewinds and loop
   counters kept as stack slots (`addql #1,sp@(52)`). rm_blit_objshift2: ~50k cyc = 6.3 ms (12%).
   The original has ZERO stack traffic in its inner loops — every live value is a register.
2. **Split `dst + Offset` addressing.** The remaster carries cursors as 32-bit byte offsets and GCC
   addresses every framebuffer word as `a2@(0,a1:l)` (base+index, +6 cyc/access) and rebuilds
   pointers with `lea` per row. The original walks REAL pointers with `(a0)+`/`(a2)+` post-increment
   (free bump, cheapest addressing mode).
3. **Load-modify-store vs memory-destination RMW.** C's `wr16(p, (be16(p) & mask) | pix)` compiles
   to load(14)+and(4)+or(4)+store(14) = 36 cyc. The original issues `and.w d1,(a0)` then
   `or.w d0,(a0)+` = 24 cyc — two single-instruction RMWs, legal because the intermediate
   framebuffer state is invisible. Expressible in C as two statements (`wr16(p, be16(p)&mask);
   wr16(p, be16(p)|pix);`) — GCC then emits the memory-destination forms (it already does for
   objshift2's `andl d0,a2@`), and the final bytes are identical.
4. **Per-call constants in registers + full unrolling.** The original loads the colour fills into
   d3/d5 ONCE per call and `swap`-toggles them per plane; unrolls all 4 planes (objshift) and all
   3 straddle cells (objshift2) with zero loop control; bakes the per-family rewind as an immediate
   (`suba.w #$a8,a0`) in family-specialised entry paths. The remaster's plane loop is rolled, with a
   per-plane compare ladder GCC made of `objsh_fill_half` + the last-plane special case.
5. **Row bookkeeping.** Original row step = 3 `suba` + `dbra` ≈ 34–46 cyc. Remaster ≈ 150–316
   cyc/row (cursor/bound reload from stack). This alone is ~68k cyc of the objshift2 gap.

**What is NOT the problem:** the variable shifts cost both sides the same (~28–40 cyc each, same
count — the original pays them too); and the objsprite family shows the remaster's C at parity, so
the engine *shape* is fine — pass 1 and the fixed pass lose on register discipline, not algorithm.

**Consequence for the plan:** most of the ~44 ms gap is reachable in plain C, no hand asm (revised
A3): (P1) hoist the four fill half-words into locals once per call, killing the per-plane ladder
and reloads; (P2) manually unroll the 4-plane loop (last plane inline); (P3) two-statement
plane_write → memory-destination and/or; (P4) walk real `uint8_t*` cursors inside the row, not
`dst+Offset`. P1–P3 REDUCE register pressure (unlike the failed A1-on-objshift2 attempt, which
pinned more live values), so they compose with the by-pointer objshift2 shape. Byte-identical by
construction; pinned by the existing `test_blit_engines` fuzz + goldens. Hand asm (A3 proper)
remains only for whatever residue is left after C parity ~— the measured ceiling is the original's
57.3 ms tree.

> **LANDED 2026-07-23 (P1+P2 on objshift; P3 measured no-op, reverted; a follow-up code-review pass
> added a row-rewind hoist; +6.61 ms of the gate frame).**
> `rm_blit_objshift` (pass 1): **288,256 → 235,456 cyc = 36.03 → 29.43 ms (0.82×, −6.61 ms)** on the
> gate frame; **`bench_objlist_pass1` 342,668 → 289,868 cyc**. Split by change (each measured in
> isolation): **P1** (hoist the four per-plane fill words into an `ObjshFill {plane[4]}` struct built
> once per call, replacing the per-plane `objsh_fill_half` ladder) **−29,112 cyc**; **P2** (fully
> unroll the 4-plane loop in the straddle + edge cells via an `always_inline` per-plane helper, plane 3
> transparency inline) a further **−21,032 cyc** (P1+P2 = 238,112 cyc); the post-landing code-review
> pass then hoisted the loop-invariant per-row source rewind out of the row loop for a further
> **−2,656 cyc**, to the final 235,456. From the disassembly: the per-plane `pix` spill
> (`movew/movel %d0,%sp@(44)`), the `objsh_fill_half` compare ladder (`swap`/`clrw`/reg-select), and the
> per-plane loop counter (`clrl`/`addql #1,%sp@(52)`) are GONE; unrolling also collapsed the framebuffer
> writes from base+index `%a2@(0,%a1:l)` to cheap displacement `%a2@(2/4/6)` (no `%aN:l` access remains).
> The residual `sp@` traffic is now purely the **per-row** cursor rewind arithmetic (P4 territory, not
> attempted) plus the irreducible variable shifts.
>
> **P3 (two-statement `plane_write`) is a measured no-op here — reverted.** Unlike objshift2, whose AND
> and OR hit *distinct* addresses (so GCC emits the memory-destination `andl d0,a2@` form), objshift's
> mask-AND and pix-OR target the **same** word; GCC dead-store-eliminates the split back into one
> load/and/or/store either way (238,112 cyc identical with split vs. combined). Kept the objshift cells
> on the shared `plane_write` — no separate helper. objsprite family untouched.
>
> **`rm_blit_objshift2` (fixed pass) is UNCHANGED — 435,940 cyc exactly** (spec's post-A1 value), the
> proof objshift2 was not perturbed. The `bench_objlist_fixed` *total* moved 448,046 → 447,982 (−64 cyc)
> only because that pass also draws a few objshift-family objects (792 cyc within it), which P1+P2 sped
> up. Byte-exact: `make test` 558 passed; `run_golden.py` MATCH on all 5 legs. Gate-frame object tree
> **108.58 → 101.98 ms**; TOTAL (frame, funcs-sum basis) **1,556,552 → 1,503,688 cyc = 194.57 →
> 187.96 ms**. (The `draw_frame` composite row is a *different* basis — 1,487,660 cyc = 185.96 ms
> after; its pre-P1+P2 value at that basis was not captured, so no before is quoted. An earlier draft
> mis-compared the composite after-value against the funcs-sum before-value.)

> **LANDED 2026-07-23 (P4 — real-pointer cursors on BOTH fine-x engines; +2.34 ms of the gate frame).**
> Mechanism #2 above (split `dst + Offset` addressing): the `ObjshCursor` fields and the objshift2 cell
> pointees became real `uint8_t *`/`const uint8_t *` instead of 32-bit byte offsets, so the cell body
> reads/writes through them and the row rewind subtracts from them — no per-access `dst + offset` rebuild
> and no per-row base add. Both engines kept their existing calling shape (objshift value-in/value-out
> cursor struct; objshift2 by-pointer pointees — the A1 shapes), so P4 is purely the offset→pointer
> axis. Byte-identical by construction: the offset arithmetic is the same mod 2^32 on the 32-bit m68k
> target, and the running offsets stay positive (non-wrapping) on the 64-bit host — the invariant the
> offset form already relied on. ("Both fine-x engines" = the two hot ones; the *third* fine-x family,
> `rm_objsprite`, was left on offset cursors deliberately — it is cold on the gate frame, so the
> conversion is unmeasured and not worth the bring-up.)
>
> **P4a — `rm_blit_objshift` (pass 1): 235,456 → 221,328 cyc = 29.43 → 27.67 ms (0.94×, −1.77 ms);
> `bench_objlist_pass1` 289,868 → 275,740 cyc.** The per-row `moveal %sp@(x),%aN` + `addal %a3,%aN`
> pointer rebuilds (3 cursors × ~1,140 cyc/row region each — the dst-base re-add) are GONE from the row
> head; the src pointer is loaded once and rewound directly. *Fidelity fix during bring-up:* the fuzz
> drives `stride = -8`, so the source rewind `sp_rewind = sx16(stride) + sx16(src_extra)` is negative;
> stored as `uint32_t` and subtracted from a 64-bit host pointer it is a ~4 GB unsigned walk → segfault
> (the offset form wrapped it back mod 2^32; a pointer cannot). Kept `sp_rewind` **signed** (`int32_t`)
> so the negative delta moves the pointer the right way on both engines. The blit fuzz caught this
> immediately — pinned.
>
> **P4b — `rm_blit_objshift2` (fixed pass): 435,940 → 431,380 cyc = 54.49 → 53.92 ms (0.99×, −0.57 ms);
> `bench_objlist_fixed` 447,950 → 443,390 cyc — BELOW the 435,900 / 447,982 measure-or-revert bars, so
> kept.** The objshift2 baseline already carried col0/col1/sp as offsets in *registers* (d3/d6/d7), so
> the only per-row waste was the base+index `lea %a5@(0,%d3:l)` column-pointer rebuild (2 per row, 2,904
> cyc/line region) — those vanish, replaced by cheap displacement `lea %a0@(8),%a1`. This is why P4b's
> win is small next to P4a's: objshift2 never had the per-access `dst+offset` in its hot writes (already
> post-inc `%a2@`), only the per-row rebuild. Not a regression (unlike the A1 value-struct attempt),
> because the calling shape is unchanged — register pressure is the same, one addressing mode cheaper.
>
> Byte-exact: `make test` **558 passed** (blit fuzz incl. LEFT/RIGHT clip families and negative stride);
> `run_golden.py` **MATCH on all 5 legs**. Gate-frame object tree **101.98 → 99.64 ms**; TOTAL (frame,
> funcs-sum basis) **1,503,688 → 1,484,968 cyc = 187.96 → 185.62 ms**. Off-gate `frame_dist` (63 frames)
> median **179.8 ms**, p90 **221.4 ms** (the win concentrates on object-heavy frames; the median frame's
> object tree is ~46 ms, so its share is small). **Residual:** both engines still keep part of the cursor
> triple in stack slots at row boundaries under register pressure (fills + shl occupy the data regs), and
> the inner cell is now RMW-instruction-selection-bound — mechanism #3 (memory-destination `and.w/or.w`
> vs load/and/or/store). A forced RMW experiment (volatile) is explicitly OUT of scope here; noted only.
>
> **Review-fix pass 2026-07-23 (constant-row-step fold, on top of P4 — both engines improved further).**
> The pre-commit review found the per-row rewind bookkeeping was a constant step in disguise: every
> family advances both columns AND the source by a per-cell-count amount per row, then rewinds a matching
> per-cell-count constant, so the `total_cells`/`cells` terms cancel. Net per-row step is constant — both
> columns move one scanline up (`−SCREEN_ROW_BYTES`) and the source steps `OBJSH_CELL_BYTES − stride`
> (objshift) / `−OBJSH2_SRC_ROW_BYTES` (objshift2, 0x50). The row loops now save the row-start cursor,
> run the row's writes, then set the next row from row-start + the constant delta (col1 always col0 +
> `OBJSH_CELL_BYTES`); the `objsh_row`/`objsh2_row` internal cursor mutation is discarded. This deleted
> the per-row `rewind`/`src_extra`/`sp_rewind` computes, the objshift2 cells-switch, and the orphaned
> `OBJSH_ROW_REWIND`/`OBJSH2_REWIND*` constants. The signed-step lesson is kept: objshift's `sp_step`
> stays `int32_t` (stride > 8 → negative source walk). **`rm_blit_objshift` 221,328 → 199,152 cyc
> (−22,176, 27.67 → 24.89 ms); `rm_blit_objshift2` 431,380 → 405,540 cyc (−25,840, 53.92 → 50.69 ms)** —
> both below the P4 measure-or-revert bars, neither reverted. `bench_objlist_pass1` 275,740 → 253,564,
> `bench_objlist_fixed` 443,390 → 417,546. Gate-frame object tree **99.64 → 93.63 ms** (0.72×); TOTAL
> (frame, funcs-sum) **1,484,968 → 1,436,948 cyc = 185.62 → 179.62 ms**. Byte-exact: `make test` **558
> passed** (fuzz gained stride 0xa8, the real caller's backward-walking source stride); `run_golden.py`
> **MATCH on all 5 legs**. A host-only `RM_HOST_ASSERT` now enforces the non-wrap invariant at each
> col0 formation (compiled out on `__m68k__`, zero target cycles).

> **Mechanism #3 verdict — DEAD post-P4 (measured, do not re-chase).** The instruction-selection lever
> (memory-destination `and.w/or.w`, single RMW at 24 cyc, vs load/and/or/store at 36) was real only
> under the OLD base+index addressing the pre-P4 code used. After P4 walks the cursors as real pointers
> with `(An)`/`d16(An)`, **both** forms cost 24 cyc per plane word: the split form is load(8)+and(4)+
> or(4)+store(8) = 24 through a pointer, and the memory-destination form is `and.w d,(An)` (12) +
> `or.w d,(An)` (12) = 24 — identical. The 36→24 win existed only when every access paid the +6 cyc
> base+index penalty that P4 eliminated. So mechanism #3 buys nothing now and is closed. (The separate
> P3 note above — GCC dead-store-merges a same-address AND/OR split back into one load/and/or/store on
> objshift — still stands and is a different point: P3 is about objshift's same-word target, #3 was
> about objshift2's distinct-word targets.)

> **LANDED 2026-07-23 (L1 — objshift2 straddle-cell pixel-loop unroll; +7.53 ms of the gate frame).**
> The 2-iteration straddle pixel loop in `objsh2_straddle_cell` compiled ROLLED with indexed addressing
> (`movew %a2@(0,%d1:l)`, 14 cyc; `orw %d2,%a0@(0,%d1:l)`, 18 cyc RMW; ×2 iterations plus ~31 cyc/cell of
> loop control — counter, `cmpl`, `bne`) — ~262 cyc/cell vs the original asm's 160 for the same work.
> Unrolling the `for (i = 0; i < 2; i++)` into straight-line code (two locals `c0`/`c1`/`s`, +0/+2
> displacements, single write-back of the cursor triple at the end) lets GCC emit displacement
> addressing (`%a0@`/`%a0@(2)`, 12/16 cyc) with **zero loop control** — the same shape P2 used on
> objshift's planes. Source read order and the col1-then-col0 write order per iteration are preserved,
> and the two iterations write disjoint 2-byte cells, so it is byte-exact by construction.
> **`rm_blit_objshift2`: 405,540 → 345,264 cyc = 50.69 → 43.16 ms (0.85×, −7.53 ms)** — well below the
> ~355-365k estimate; `bench_objlist_fixed` 417,546 → 357,270. From the disassembly the inner pixel
> writes are now `orw %d1,%a0@` / `orw %d1,%a0@(2)` (displacement) with the indexed `%aN@(0,%d1:l)`
> reads/RMWs and the `addql #2,%d1`/`moveq #4,%d2`/`cmpl`/`bnes` loop control GONE. Also folded the edge
> cells' redundant high-source re-read (`lo = (uint16)both | be16(*sp)` → reuse `(uint16_t)(both >> 16)`,
> the same bytes be32 already loaded) — byte-equivalent, 0 cyc change (edge cells are cold on the gate
> frame) but one fewer memory access. The mask-split `andil #65535` (14 cyc) was left alone: it was
> present in the landed baseline (unchanged by L1) and is register-allocation-driven micro-noise the
> task flagged as not worth chasing. Gate-frame object tree **93.63 → 86.10 ms** (0.66×); TOTAL (frame,
> funcs-sum) **1,436,948 → 1,376,672 cyc = 179.62 → 172.08 ms**. Byte-exact: `make test` **558 passed**;
> `run_golden.py` **MATCH on all 5 legs**.

> **L2 (objshift fill-pair swap-packing) — MEASURED REGRESSION, REVERTED.** The four `ObjshFill` colour
> words exceed the free data registers, so `rm_blit_objshift`'s straddle row loop spills two to the stack
> (`movew %d5,%sp@(48)` / `%d6,%sp@(46)`) and reloads them per plane (`movew %sp@(50)/(46)/(48)`, 12 cyc
> each). L2 tried the original's trick — carry the fill as TWO `uint32_t` pairs (`{lo, hi}`) so both stay
> resident in two registers and each plane's 16-bit half is a 4-cyc `swap`-toggle. It **regressed
> `rm_blit_objshift` 199,152 → 213,504 cyc (+14,352)** — above the measure-or-revert bar, reverted to the
> P1 `plane[4]` shape (the current landed state). The swap toggles did appear, but the pair carriage does
> not relieve the fundamental pressure: the straddle row loop already needs col0/col1/sp pointers
> (a0–a3), the rotated mask (d0), shl (d2), pix temps and the row counter, leaving no room for two
> resident pair registers — GCC spilled the pairs anyway AND added a per-row `movel %d6,%sp@(44)` /
> reload shuffle, so the toggle cost stacked on top of undiminished spilling. Same wall as the
> A1-on-objshift2 attempt: objshift's row loop is register-pressure-bound, and forcing more values
> resident spills something else. objshift's spill residue is a hand-asm (A3) target, not a C-shape one.

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

> **LANDED 2026-07-23 — GCC-level sweep (E1 kept; E2/E3 measured and dropped; +4.25 ms of the gate
> frame). This is the GCC-tools attack on the register-pressure wall the L2 note identified.** L2 proved
> that no *C shape* relieves `rm_blit_objshift`'s cursor-triple spill and that *forcing* residency by
> hand makes it worse; this sweep went one level down to the compiler's own allocator knobs. **Final
> config: global `-O3` (was `-O2`) in BOTH build scripts, plus a per-function
> `__attribute__((optimize("-fira-region=one","-fira-algorithm=priority")))` on `rm_blit_objshift`
> only.** Measured on the gate frame (`bench_build.sh` + `tools/bench.py`), one flag added at a time:
>
> | flag (global, on -O2 base) | objlist_pass1 | objlist_fixed | TOTAL | verdict |
> |----------------------------|--------------:|--------------:|------:|---------|
> | *baseline* | 253,564 | 357,270 | 1,376,672 | — |
> | **-O3** | 248,796 | 356,436 | **1,359,926** | **KEPT** — both engines + objsprite family (buggy −4,812, fg_sprite −2,716, ground −2,224) improve; only draw_hud +1,334 (+0.17 ms, within noise) |
> | -fira-algorithm=priority | 240,766 | 363,076 | 1,364,940 | pass1 −12,798 but fixed +5,806 AND draw_hud +7,712 (+0.96 ms) — global reject; the pass1 lever is real, scoped below |
> | -fira-region=one | 243,966 | 357,294 | 1,370,416 | pass1 −9,598 but draw_hud +2,108 (+0.26 ms) — global reject; scoped below |
> | -fira-region=all | 253,564 | 357,270 | 1,376,672 | no-op at -O2 |
> | -flive-range-shrinkage | 253,564 | 357,270 | 1,376,672 | no-op |
> | -fweb | 253,564 | 357,202 | 1,376,604 | noise |
> | -frename-registers | 255,350 | 358,324 | 1,382,480 | REGRESSION everywhere — drop |
> | -fno-caller-saves | 253,338 | 357,066 | 1,376,270 | noise |
> | -fno-crossjumping | 253,564 | 357,270 | 1,379,038 | +2,366 elsewhere, blitters flat — drop |
> | -fipa-ra | 253,564 | 357,270 | 1,376,672 | no-op |
> | -fschedule-insns -fsched-pressure | 253,564 | 357,270 | 1,375,850 | −822 elsewhere, blitters flat (m68k has a weak scheduler); not worth the risk — drop |
> | -funroll-loops | 341,876 | 357,982 | 1,493,064 | pass1 +88,312 — severe REGRESSION, drop |
>
> **The register-pressure lever is `-fira-region=one` + `-fira-algorithm=priority`, but only on
> `rm_blit_objshift`.** Applied *globally* both regress draw_hud past the ±0.2 ms bar; applied
> *per-file* to blit.c they help pass1 but the same two flags **REGRESS `rm_blit_objshift2` +4,440**
> (objshift2 is arithmetic/RMW-bound, not spill-bound — priority steals the address registers its RMW
> cell needs, the identical wall the A1 value-struct hit). The **per-function `optimize()` attribute**
> is the only tool that scopes the allocator lever to the one function that benefits. Composition
> matrix (on global -O3):
>
> | scope of region=one+priority | objlist_pass1 | objlist_fixed | TOTAL |
> |------------------------------|--------------:|--------------:|------:|
> | -O3 only (no allocator flag) | 248,796 | 356,436 | 1,359,926 |
> | blit.c per-file (hits BOTH engines) | 231,824 | 360,880 (+4,440 ✗) | 1,347,398 |
> | **attribute on objshift ONLY** | **231,480** | **356,436** | **1,342,610** ← kept |
> | attribute region=one only | 239,676 | 356,436 | 1,350,806 |
> | attribute priority only | 239,152 | 356,436 | 1,350,282 |
>
> The two flags **compose** (231,480 is far below either alone), and the attribute leaves objshift2 at
> -O3's clean 356,436. No attribute helps objshift2 (region=one/live-range/fweb all neutral; the pair
> regresses it) — its win is -O3's −834 only.
>
> **E2 (local register variables) — MEASURED REGRESSION, DROPPED.** Pinned the cursor triple to
> a2/a3/a4 with guarded `register … __asm__("aN")` vars in the row loop (the task's exact recipe). It
> **regressed**: on -O3 + the attribute, `rm_blit_objshift` 231,480 → 246,688 (+15,208); standalone
> (no attribute) 253,564 → 278,844 (-O3) / 285,932 (-O2). Same wall as L2 — forcing the cursors
> resident collides with the fills/mask/shift live set and spills worse. The allocator FINDING the
> assignment (E1's attribute) beats us FORCING it; the attribute is E2's lever done right.
>
> **E3 (-flto / cross-TU dispatcher inlining) — DROPPED, incompatible with the harness.** LTO's
> whole-program DCE internalizes every symbol reached only from *outside* the link — the `bench_*`
> entry points (0 `T bench_` symbols survive) and the staging symbols `tools/bench.py` resolves by name
> (`arena_block`, the prep functions), so the bench cannot even run; `-Wl,-u` force-retention hits the
> next missing symbol. It also reflows a RWX LOAD segment the tight `tos.ld` + entry-at-0 + mkprg reloc
> contract does not expect. The dispatcher glue (~31 k cyc) is real headroom but LTO is the wrong tool
> for it through this name-based harness; unmeasurable and unshippable here.
>
> **Result:** `rm_blit_objshift` (the function) 199,152 → **181,836** (−17,316 from the attribute);
> the whole pass `bench_objlist_pass1` 253,564 → **231,480** (−22,084 = 31.70 → 28.93 ms; the extra
> −4,768 is -O3 on the dispatcher glue). `rm_blit_objshift2` 357,270 → **356,436** (−834, -O3 only,
> `bench_objlist_fixed`); both engine rows improve, no other
> row regresses past ±0.2 ms (draw_hud +0.17, outweighed by objsprite-family −1.2 ms). Gate-frame TOTAL
> **1,376,672 → 1,342,610 cyc = 172.08 → 167.83 ms** (−34,062, −4.25 ms); object tree 86.10 → 81.97 ms.
> Byte-exact: `make test` **558 passed** (host; clang ignores the m68k `optimize` attribute, so the
> differential C is unchanged); `run_golden.py` **MATCH on all 5 legs** (the real gate — the flagged
> GAME binary runs in Hatari). Both `bench_build.sh` and `build_game.sh` carry `-O3` identically; the
> attribute lives in blit.c so both builds get it. The GCC-level lever on the blitters is now
> **exhausted** — what remains on objshift is the hand-asm (A3) spill residue, not a compiler knob.

### C1/C2/C3 — the last three C-level object-tree levers (2026-07-23; C1 + C3 landed, C2 dropped; +4.07 ms of the gate frame)

The three remaining pure-C levers on the object tree, after the GCC-level sweep exhausted the
allocator knobs. Baselines re-measured on -O3 + the objshift IRA attribute (the switch moved
function-level numbers): `rm_blit_objshift2` 345,264 cyc (43.16 ms); `rm_objsprite` 18,204 (2.28 ms);
`bench_objlist_fixed` 356,436; `bench_objlist_pass1` 231,480; TOTAL 1,342,610 (167.83 ms). Fuzz
(`test/test_blit_engines.py`) covers all three engines' clip/edge/base/wide families × 16 fine-x ×
multi-row; no extension needed (C1 is byte-identical calls, C3 is offset→pointer under the existing
cases).

> **LANDED — C1 (objshift2 straddle-cell run specialized as a fall-through switch; +3.88 ms).** The
> row's `for (i = 0; i < straddle; i++) objsh2_straddle_cell(...)` paid per-cell loop control that the
> annotated profile put at `addql #1,%d3` (5,184 cyc) + `cmpl %d6,%d3` (3,888) + `bnes` (5,996) ≈ 15 k
> cyc, and blocked cross-cell scheduling. `straddle` is 0..3 and constant per call, so the loop became
> a fall-through `switch (straddle) { case 3: cell; case 2: cell; case 1: cell; default: break; }`
> (case labels `OBJSH2_BASE_STRADDLE`/−1/−2, no magic numbers). The switch compiles to a compare chain
> under `-fno-jump-tables`, run once per row, not per cell. **First attempt REGRESSED +176 k** — three
> `case` labels tripped GCC's called-more-than-once heuristic into emitting a *real* call to
> `objsh2_straddle_cell`, which spilled the by-pointer `uint8_t **` cursor args to memory (the A1 wall);
> **`always_inline` on the cell** pins the three straight-line inlined copies and is the whole point.
> Result: **`rm_blit_objshift2` 345,264 → 314,216 cyc = 43.16 → 39.28 ms (0.91×, −31,048 = −3.88 ms)** —
> well past the ~2–2.5 ms estimate (eliminating loop control also freed cross-cell scheduling and
> register reuse); `bench_objlist_fixed` 356,436 → 325,424. From the disassembly the three cells are now
> unrolled straight-line (mask build `oril`/`roll`/`andil` appears 3× with no per-cell `addql/cmpl/bne`;
> the only back-edge is the row loop). Byte-exact: `make test` **558 passed**; `run_golden.py` **MATCH
> on all 5 legs**.

> **C2 (objshift2 mask-build/split reshaping) — TWO honest shapes, BOTH REGRESSED, reverted.** The
> per-cell mask code emits `oril #-65536` (16 cyc) + `andil #65535` (14 cyc ×2) where the original asm
> uses a `moveq #-1` seed and 4-cyc `move`/`swap` shuffles. Analysis showed the chained
> `(x & 0xffff0000)|…` idiom actually computes just `mask_col0 = dup16(hi16(mask32))`,
> `mask_col1 = dup16(lo16(mask32))`. **Attempt #1** (express that directly with `dup16` of each half,
> `OBJSH_MASK_HI | base` seed): `rm_blit_objshift2` 314,216 → **318,104 (+3,888)** — GCC still emitted
> the `oril`/`andil` and added a worse split. **Attempt #2** (`~(w0|w1)` computed as `int`, whose sign
> extension yields `0xffff_<base>` for a `not.l` instead of the `oril`): **325,182 (+10,966)** — the
> `not.l` lengthened the dependency chain. Per the measure-or-revert rule (this is the class GCC refused
> at P3/L2), both reverted to the landed chained idiom. The immediate ops are register-allocation
> micro-noise GCC will not give up here.

> **LANDED — C3 (objsprite family gets the P4 pointer treatment; +0.19 ms + dead-code drop).** The
> third fine-x engine `objsp_core` (behind `rm_objsprite`/`rm_objsprite_alt`, the roadside dispatcher's
> t1/t2/t4/w88/t53 handlers) was the one still on offset cursors. Correcting the plan's premise first:
> `objsp_core` is used **only** by object_list.c's pass-1 objsprite objects — `rm_draw_buggy`/
> `rm_draw_fg_sprite`/`rm_draw_ground` are *separate* engines (sprite.c/ground.c), not this family — so
> C3's reach is `rm_objsprite` (18,204 cyc of `bench_objlist_pass1`), not the multi-row set the estimate
> assumed.
> - **(a) P4b pointer conversion** — the cell pointees `Offset *col0/*col1`, `uint32_t *sp` became real
>   `uint8_t **`/`const uint8_t **` (by-pointer shape kept, per the A1 lesson — NOT the value-struct),
>   the cells drop the `dst`/`src` params and write through the pointers. **`rm_objsprite` 18,204 →
>   16,672 cyc (−1,532 = 2.28 → 2.08 ms)**; `bench_objlist_pass1` 231,480 → 229,948. This made the two
>   offset wrappers (`plane_write`, `objsh_build_mask`) — which existed ONLY for objsprite — dead;
>   removed, with their "kept for the objsprite family" comments and the banner's "kept on offset
>   cursors deliberately" rationale.
> - **(b) P2 plane unroll** — already done by `-O3`: the profile shows the objsprite plane loop compiled
>   to displacement addressing (`%a1@(2)/(4)/(6)`) with the plane-3 clamp inline, not the indexed rolled
>   loop. No explicit unroll needed; the P4 local-pointer copies are what let -O3 do it.
> - **(c) constant row-step fold** — byte-exact (proved: every family's per-row advance `8*cells` equals
>   `(0xc0 − 8*rung) − SCREEN_ROW_BYTES`, so the net step is `−SCREEN_ROW_BYTES` for col0/col1/**and**
>   the screen-format source), but measured a **no-op** (+32 cyc, noise). Per the "affected rows improve
>   net" acceptance bar, **reverted** — the faithful `rewind` form is kept.
> - **dispatcher glue** (`rm_draw_object_list`/`obj_dispatch`/`objsprite_hi_wrapper`, ~30 k cyc): the
>   line-level profile shows its cost is inherent long-parameter-list ABI marshalling (`movel
>   %sp@(x),%sp@(y)` at 168 cyc each) and the record-walk loop bound — no surgical spill/re-derived
>   pointer to take without restructuring the dispatcher, which is out of scope. Left as-is.
>
> Byte-exact: `make test` **558 passed**; `run_golden.py` **MATCH on all 5 legs**.

> **Net C1+C3:** `bench_objlist_fixed` 356,436 → 325,424; `bench_objlist_pass1` 231,480 → 229,948;
> object tree **81.97 → 77.90 ms** (0.60× the recon); TOTAL (frame, funcs-sum) **1,342,610 → 1,310,066
> cyc = 167.83 → 163.76 ms (−32,544, −4.07 ms)**. The pure-C object-tree levers are now exhausted:
> objshift's residue is hand-asm (A3), objshift2's mask immediates resist GCC (C2), and objsprite is
> cold. What remains on the tree is A3 (hand-asm) or the Tier-B algorithmic wins (A2 pre-shift, culling).
