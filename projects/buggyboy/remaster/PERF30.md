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

**B2. Road display list (precompute per-(curve,view) scanline programs).** *(Tier B, ~15–25 ms)*
**→ DECIDED NO-GO 2026-07-24 — the premise is measured false; see the "B2 measurement" campaign note
at the end of this file.** The
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

**B4. Static/dynamic dashboard split (already in the old plan).** *(Tier B, ~8–10 ms)*
**→ DECIDED NO-GO AS SCOPED 2026-07-24 — the premise is measured false; a 1.37 ms opaque fast path
landed instead; see the "B4/B5 measurement" campaign note at the end of this file.** 61% is the
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

**B5. Top-fill dirty tracking.** *(Tier B, ~3–5 ms, do last)*
**→ DECIDED NO-GO 2026-07-24 — the fill is a fixed-region constant, not horizon-relative, and it IS
the deterministic background the masked composites rely on; see the "B4/B5 measurement" note.** The constant fill above the band only
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

> **C4 slice 1 — infrastructure + driver + recipe PROVEN (landed, not committed).** The STE build target
> exists: `GAME_STE=1 bash render/atari/build_game.sh` → `BUGGYBST.PRG` (`-DGAME_STE`, links
> `src/blitter.c`); the stock `BUGGYBOY.PRG` is **byte-identical** with the flag off (hash-pinned). The
> driver (`include/blitter.h` + `src/blitter.c`) is the named `0xFFFF8A00` register block, a `BlitPass`
> struct + `blit_run()` (HOG mode — justified: per-object blits are µs, well under the 20 ms VBL, so the
> bus-hold never starves the sound pump; the non-HOG restart loop is documented for a future screen-sized
> blit), and a boot presence check (`_BLT` cookie first, else `_MCH` id ∈ {1,3} — so the TT030, which has
> no blitter, also bails) that prints a clean `Cconws` message instead of bus-erroring. **Recipe:** objshift2's `dst = (dst & ~(w0|w1)) | pix` self-mask is a
> two-pass blitter cookie-cut (AND `mask`, OR per-plane `data`, `HOP=SRC`); the mask is materialised in
> memory (the sprite source is static — A2 phase tables, ~49 KB masks). The **aligned (fine_x=0)** case is
> proven **byte-for-byte against the real `rm_blit_objshift2`** on `--machine ste --blitter` (0/32000,
> `run_ste_selftest.py`). Pins all green: stock goldens ×5 (`--machine st`), STE goldens ×5 (`--machine
> ste`), whole-frame A/B stock-vs-STE = 0-mismatch (`run_ste_ab.py`), `make test` 708. Cadence baseline on
> `--machine ste` == stock (objshift2 still CPU this slice). **Full spec + slice-2 plan: `BLIT_STE_SPEC.md`.**
> Slice 2: pin the fine_x **skew** (skew=fine_x + FXSR/NFSR/endmask, self-test sweep 1..15), build the A2
> phase tables, route `RM_BLIT_OBJSHIFT2` through the blitter under supervisor (hybrid CPU fallback for any
> un-pinnable clip case), and measure the cadence delta (objlist fixed pass = 27.6% of the gate frame).

> **C4 slice 2 — objshift2 blitter path byte-exact + ROUTED; cadence flat, the collapse is a DATA change
> (landed, not committed).** The fixed-pass fine-x blit now runs on the blitter for the BASE family
> (`src/blitter_objshift2.c`), the CPU asm engine for CLIP (a pinned hybrid; the dispatcher picks the
> family in user mode, so a clip case never pays the excursion). **Recipe decision: pre-shift in the
> materialiser + skew=0, NOT the hardware SKEW register** — slice 1 proved skew=0 byte-exact, so the
> fine-x straddle is done in software into `straddle+1`-wide interleaved bitmaps and the blit is 2 passes
> (AND all planes / OR all planes, contiguous); this keeps the pin on the proven aligned recipe and avoids
> the FXSR/NFSR edge-calibration byte-exactness risk (hardware skew deferred as a RAM optimisation).
> **Pinned:** `run_ste_sweep.py` sweeps 1728 cases (width_idx × fine_x 0..15 × 12 columns × rows) — 720
> BASE blitter-drawn, **0 mismatch** vs the CPU engine (a shift-by-fine_x+1 mutation fails 601, so it is
> not vacuous); STE goldens MATCH ×5 with objshift2 live on the blitter; whole-frame A/B stock-ST-vs-STE =
> 0-mismatch over 10 drive frames (now load-bearing); `make test` 718; stock .PRG byte-neutral to the
> `object_list.c`/`game_main.c` edits (both `#ifdef GAME_STE`). **Cadence (free-run, leg 0):** stock 6.61
> vs STE 6.65 vbl/present — **flat**. The per-blit materialiser redoes the fine-x shift + a scratch
> round-trip, so it only offloads the framebuffer RMW (~15 %/BASE-blit, swamped at leg 0). The real
> collapse needs the **boot pre-shift tables** (remove the per-frame materialise → 2 blits over static
> tables): that is slice 3, along with blitter-side clip and then the colour-indexed pass 1 (25.3 %).

> **C4 slice 3 — objshift2 collapses on the gate frame: −12 % via a memoisation cache (landed, not
> committed).** Slice 2's cadence was flat, so slice 3 profiled the objshift2-DENSE gate frame (idle the
> autodrive on the leg-start gate). Decomposition (`GAME_STE_PROF_NOMAT/NOBLIT` timing builds, free-run
> mean vbl/present): stock 8.28; STE-bare (dispatch+Supexec, no work) 6.27; STE-**nomat** (blit, skip the
> materialise) 7.27; STE-noblit (materialise, skip blit) 9.28; STE-full 9.28. **The per-frame MATERIALISE
> is ~3 vbl — the entire cost; the blitter passes are ~free.** Fix: a memoisation cache — the materialised
> bitmap is a pure function of (src, src_off, fine_x, width_idx, rows_m1) over the STATIC `arena.gfx`, so a
> direct-mapped cache of the interleaved (mask,data) bitmaps never invalidates; the gate/tunnel sprites hit
> after warm-up → the `nomat` win, byte-exact. **Result (free-run):** leg-0 gate 8.22→**7.22** (−12 %),
> leg-4 gate 8.23→**7.23** (−12 %, not a leg-0 artifact), leg-0 driving 7.06→7.04 (~flat). Cache RAM ≈
> **356 KB** BSS (128 slots; fits a 1 MB STE, tunable to 64 slots / 178 KB for 512 KB). Pins all green:
> sweep 1728 cases 0-XOR *with the cache live*, STE goldens ×5, A/B 0-mismatch ×10, `make test` 718, stock
> byte-neutral (the one stock-path edit — `mkprg.py`'s `abs_fixups` now filters relocs to `.rela.text/.data`,
> excluding debug-section relocs that the bigger STE binary emitted — hashes identically). **Slice 4:
> blitter-side clip (now unblocked by the cache) + the colour-indexed pass 1 (25.3 %, same recipe) as the
> headline; one-excursion Supexec DEFERRED (per-blit trap didn't block the win).**

> **C4 slice 4 — colour-indexed pass 1: recipe byte-exact, but the on-demand cache hits a DRIVING wall
> (landed, not committed).** The colour-indexed `rm_blit_objshift` (~25 % of the gate) ports to the SAME
> cache-keyed pre-shift + 2-pass cookie-cut (`src/blitter_objshift.c`): 4-plane source, `~(A|B|C)&D` mask,
> per-plane colour fill composited into the OR-data (no third pass), plane-3 `~mask` special. The
> per-column values are the exact algebraic reduction of the CPU's sequential AND-then-OR straddle
> (`net_mask=m_col1[j-1]&m_col0[j]`, `net_data=(pix_lo[j-1]&m_col0[j])|pix_hi[j]`). **Proven byte-exact:**
> `run_ste_sweep.py` now sweeps BOTH engines — 3264 cases (1728 objshift2 + 1536 objshift), **0 mismatch**,
> 704 colour BASE cases blitter-drawn; a plane-3 mutation fails 297. **But it is NOT routed:** hit-rate
> counters show the colour cache is 100 % on the static gate yet only **9 % while DRIVING** (roadside
> objects change fine-x/scale/colour every frame → the key never repeats), so the 4-word materialise runs
> on ~91 % of driving blits and **regresses the race ~15 %** (7.06→8.13 vbl). objshift2 escaped only
> because it issues ~0.24 blits/frame while driving. So the colour engine ships byte-exact on the CPU path
> (`-DRM_STE_OBJSH_ROUTE` opts it in — knob DELETED in slice 9, which routes the colour engine through
> the hardware-skew table instead); default STE routes objshift2 only — **gate −12 %, driving flat**
> (7.06→7.03, no regression). Pins: sweep 3264 0-XOR, STE goldens ×5, A/B 0-mismatch ×15, `make test` 723,
> stock byte-neutral (`mkprg.py` only). Combined cache RAM ~553 KB (fits a 1 MB STE). **The colour driving
> win needs boot pre-shift tables (remove the per-frame materialise) — slice 5's gating item; the recipe +
> sweep are the proven foundation.**

> **C4 slice 5 — boot-table census: MEASURED NO-GO for colour, UNNEEDED for objshift2 (landed, not
> committed).** Boot tables only pay off if the reachable materialise-key set is bounded + fits RAM, so
> slice 5 measured it (`src/blitter_census.c`, `-DGAME_STE_CENSUS`: instrument every call over a real
> drive, count DISTINCT base-family tuples). **objshift2: BOUNDED at 6 distinct tuples** (flat as the drive
> grows — a fixed-sprite pass; the cache already covers it 100 %, tables UNNEEDED). **colour: effectively
> UNBOUNDED** — distinct grows ~5/frame *accelerating* (30f→100, 40f→149, 60f→349; ~70 % of blits a
> never-seen tuple) because the roadside pass draws many objects across a continuum of scale × sub-pixel-x.
> Over a full leg → tens of thousands of entries × ~2 KB = **tens of MB, does not fit a 1 MB (or 4 MB)
> STE** → NO-GO for full tables. The **hybrid also fails** (70 % unique = no recurring set to cache).
> **Verdict (evidence over a forced landing):** the colour engine stays on the CPU (byte-exact recipe
> preserved); the STE build's honest object win is objshift2 (gate −12 %). The colour pass's per-frame
> materialise is irreducible under pre-shift+cache/tables — a real colour win would need hardware skew from
> unshifted data (no materialise; the FXSR/NFSR calibration slice 2 deferred), a research item not a
> landing. Gates: stock byte-neutral, default STE goldens ×5, `make test` 723 (census wiring inert off).
> Full analysis: `BLIT_STE_SPEC.md` §10.

> **C4 slice 6 — ONE unified ST/STE binary (landed, not committed).** The census (slice 5) made this cheap:
> objshift2's reachable set is a bounded 6 tuples, so its cache shrinks to a census-justified **16 slots
> (44 KB, down from 356 KB)** and lives unconditionally in BSS. The shipping `BUGGYBOY.PRG` now carries the
> blitter path always (`-DRM_BLITTER`), **bound once at boot**: `blitter_available()` (the `_BLT`/`_MCH`
> probe — never bails, binds the CPU path on a plain ST/TT) sets `rm_blit_objshift2_fn` to the blitter
> dispatch on an STE or the 68000 asm engine otherwise. **Measured stock-ST overhead of the indirection:
> ZERO** — the unified PRG on `--machine st` is cadence-identical to the old committed stock (gate
> 8.932=8.932, drive 8.167=8.167 vbl/present). Same-PRG matrix: goldens **MATCH ×5 on `--machine st`** AND
> **×5 on `--machine ste`**; whole-frame A/B st(CPU) vs ste(blitter) **0-mismatch ×15**; STE gate **−11 %**
> (7.949); `--machine tt` **boots + renders on the CPU path, no bail**; sweep **3264/0**; `make test` 723.
> The base game's **1 MB requirement does not move**. The separate `BUGGYBST.PRG` / "byte-identical stock"
> pin is retired (there is no separate stock — the cadence identity on `--machine st` replaces it). Colour
> engine stays CPU on every machine. Full analysis: `BLIT_STE_SPEC.md` §11.

> **C4 slice 7 — RE-KEY census: the colour engine's set is BOUNDED under hardware skew — the slice-5
> NO-GO flips (landed, not committed).** Slice 5 measured the **full pre-shift key** (src_off × fine_x ×
> colour × stride × rows × cells) as unbounded — correct for pre-shifted tables. A **hardware-SKEW**
> engine (blit from UNSHIFTED bitmaps, chip shifts at blit time) removes fine_x from the materialised
> content, colour (a per-plane binary fill select), and rows (max-rows materialise, blit fewer via
> y_count) — so the census now counts four keys at once. **Measured: the `sprite` key
> (src_off, stride, base_cells) is BOUNDED at 78 entries on leg 0 (98 worst leg), flat from ~80 frames
> through a 300-frame drive — the last +700 base calls added 0 new keys (100 % table hit)**, while the
> full-key control reproduces slice 5 exactly (100/149/349) and keeps growing. Table RAM: 41–82 KB
> worst-leg (structural ceiling ~293 KB); retiring the redundant 219 KB on-demand colour cache makes the
> net delta ≈ −40 KB…+75 KB. Bonus findings: §10's "~60 clean frames" ceiling was a
> `GOLDEN_BOOT_LEG`-vs-census SCREEN.BIN dump race (now `#error`-guarded; autodrive censuses ≥300 frames
> clean), and the measured shipping footprint is **1.18 MB** — the "1 MB STE" claim was wrong; honest
> minimum 2 MB — superseded by the slice-10 diet: minimum is 1 MB. **Open risk unchanged:** the FXSR/NFSR/endmask
> byte-exactness calibration for skew — the data side is now proven affordable; the recipe is the next
> slice. Full analysis + tables: `BLIT_STE_SPEC.md` §12.

> **C4 slice 8 — the hardware-skew colour recipe PROVEN byte-exact; the calibration risk dissolves
> (landed, not committed).** `src/blitter_skew.c` blits the colour BASE family from **unshifted,
> colour-independent** bitmaps (`M = ~(A|B|C)&D`, planes A/B/C, `D&~M`) with `skew = fine_x` and — the
> headline — **no FXSR, no NFSR**: the one polluted source read per line lands exactly in the bits
> `endmask1 = 0xFFFF>>k` / `endmask3 = ~(0xFFFF>>k)` already block, and the colour fill rides in the
> OR-pass endmasks (`dst |= src & e`), so a zero plane skips its pass outright (game blits average
> **6 passes**, fills verified binary over all legs). Pinned: the sweep now runs THREE grids — **4800
> cases, 0 mismatch** (objshift2 720 + pre-shift 704 + skew 704 handled), non-vacuity gated by
> C-emitted expected counts (a forced-decline build fails loudly), `--mutate all` catches all 5
> mutations (704/704/643/660/297) with the other grids skipped, `make test` 730, shipping PRG
> sha-identical. **Cost (isolated pass timing — the old subtract-two-totals "passes are ~free" was an
> artifact):** materialise 13,520 cyc, passes 12,920 (game fill), CPU asm 33,960 → **0.78× with
> per-call materialise, 0.38× from a table.** Seam pre-built for slice 2 (`ObjshSkewBitmaps`,
> materialise-into-entry / blit-from-entry). Slice 2 = §12's sprite-key static table + routing +
> poke batching + the DRIVING cadence go/no-go. Full recipe + register table: `BLIT_STE_SPEC.md` §13.

> **C4 slice 9 — the colour engine ROUTED through the skew table: GO, driving improves (landed, not
> committed).** The shipping STE build routes `rm_blit_objshift`'s BASE family via a 128-entry
> no-eviction first-sight table (sprite key + `src`; grow-on-demand rows; 123 KB BSS) behind a
> boot-bound `rm_blit_objshift_fn`; `-DRM_STE_OBJSH_ROUTE` is DELETED and the pre-shift path + its
> 219 KB cache left the shipping link (sweep-only). **The census key-union measurement forced a per-leg
> flush**: converged per-leg key sets are 78/75/79/98/79 but their cross-leg UNION is exactly 128 = the
> table capacity, zero headroom — so `start_leg()` flushes (live set ≤ 98, ~30 spare) and a saturation
> latch guards overflow by retiring the route (pixel-identical CPU hybrid) instead of scanning forever.
> Poke batching: 42 register writes per 6-pass blit vs blit_run's 102 (`src_addr` must re-poke — the
> chip walks it; X_COUNT latch-reloads, sweep-verified). **Cadence (sub-vblank render clock, leg 0):
> STE gate 111.05 → 105.58 ms (−19.2 % vs stock ST), STE drive 99.22 → 97.18 ms (−2.5 % vs stock,
> NO regression — §8's 9 %-hit failure inverted to 90 % hits); ST tick-identical.** Table blit 9,400
> cyc vs CPU asm 33,920 (0.28×). Pins: sweep **4936/0** incl. a new 134-case table section
> (grow/clip/hit/full/latch/flush), 6/6 mutations (NOGROW caught only by the table section), goldens
> ×5 + ×5, A/B 0-mismatch, make test 730, TT clean. Footprint 1.08 MB (−97 KB). Quantified + deferred:
> per-blit Supexec ≈ 0.3–0.55 ms/frame. Full design: `BLIT_STE_SPEC.md` §14.

> **C4 slice 10 — the 1 MB DIET (landed, not committed): the remaster fits a 1 MB ST *and* a 1 MB STE,
> like the original.** Two measurement-first moves. (1) The 2×128 KB `SCREEN_OVERDRAW` tails were sized
> to the "~102 KB past the screen" folklore — the reach census (5,240 composed + 4,000 forced-branch +
> 305 staged frames, in-repo `tools/reach_census.py`) measured the TRUE max at **8 bytes** (render_road;
> every object engine stays below 32,000; the off-screen cull idea is moot — nothing draws below the
> screen). Tail → 0x1000 (512× margin), −253,952 B, with standing guards so the number can never rot
> again: the host suite canaries the tail every compared frame (mutation-checked), trace builds scan the
> whole tail per present on target, and a new 32-case below-screen sweep section pins the chip path
> against the tail too. (2) `skew_table` + `objsh2_cache` (170,432 B) leave BSS — placed into free TPA
> above `_end` at boot only when the blitter binds (os.s captures basepage + SP; ceiling
> min(p_hitpa, SP) − 16 KB; unplaced state is TOTALLY safe: latched routes, null-safe flushes, sweep
> reports a clean decline). **Footprint 1,132,000 → 707,840 B. Measured TPA at 1 MB: EmuTOS 905,448 —
> a 1 MB ST fits +197 KB; a 1 MB STE fits WITH the tables placed (blitter route live, 14 KB spare —
> the thin-margin watch item).** New standing pin: goldens ×5 + ×5 at `--memsize 1` on both machines
> (plus 730 host tests, sweep 4,968/0, A/B 0-mismatch, cadence in noise). `BLIT_STE_SPEC.md` §15.

> **Consolidated measurement at HEAD 6ac3066 (2026-07-26)** — one build, one instrument, all four
> cells fresh: ST gate **130.50 ms** / drive **99.42**; STE gate **105.38** (−19.2 %) / drive
> **97.36** (−2.1 %); 1 MB cells bit-identical to 4 MB (RAM size costs zero speed). Resident memory
> without TOS: **ST 708,004 B**, **STE 878,436 B** (incl. the 170,432 B placed tables; pad 0,
> pinned empirically — placement declines at exactly +4 B over need). 1 MB STE shipping margin
> corrected to **10,620 B** (the §15 "14,092" was the trace build's). The canonical tables live in
> **`README.md` "Measured performance & memory"**.

### C5 — the ROAD FINE-SCROLL on the blitter (a new campaign, distinct from the Tier-C "C5" below)

C4 closed with the two object engines routed and the 1 MB diet landed, leaving `blit_road_scroll` as the
largest stage still on the 68000 when the blitter is bound (12.06 ms of the 130.5 ms gate frame). The C4
proposal above already named it ("hardware fine-scroll offloads `blit_road_scroll` entirely"); this
campaign does it with the blitter rather than the shifter's hardware scroll, so the pixels stay
byte-identical. **NAME CLASH, noted once:** the Tier-C proposal list below also has a "C5" (palette
tricks); the two are unrelated — this is the campaign tag, that is a proposal id.

> **C5 slice 1 — `blit_road_scroll` ROUTED through the blitter: GO (landed, not committed).** The third
> route, and the first with **no lookup table**: it blits straight out of the `shifted` pre-rotated
> playfield the CPU reference already reads, so nothing is placed and nothing can be vetoed by a tight
> TPA — it is therefore bound on the blitter probe ALONE, before `rm_blit_bind_all`'s table placement can
> retire the object routes. **Recipe (3-4 passes + a CPU seam):** `ROAD_TOP_FILL` is `0xffff0000`, which
> in the interleaved framebuffer is "every EVEN plane-word ones, every ODD one zero" — so the 13,440-byte
> constant fill is TWO **source-less** passes over one 84x40 pair grid (`HOP=ONE`, `LOP=ONE`/`ZERO`,
> all-ones endmasks: write-only bus cycles, no source or destination read); both band pitches are
> constant across the 20 rows, so the main copy is ONE blit (+ one more for the wrapped tail when
> `edge >= 1`, SKIPPED at `edge == 0` — `x_count` 0 means 65,536 to the chip). The 4-word masked seam
> stays on the CPU and must run AFTER the main blit (it reads what that blit wrote); the wrap blit is
> disjoint from it. All passes share ONE Supexec. **Bus policy: the shared-bus restart loop SHIPS.** §2's
> documented snippet was incomplete — no start, so its own first `bset` reads the pre-start `BUSY=0` and
> falls through after one burst (measured: 640/640 sweep cases failed, ~63 of 3,360 words written). With
> the explicit `move.b #BUSY` start it is byte-exact. HOG measured at **98.22/90.20 ms vs the restart
> loop's 99.25/90.72** (gate/drive) with an identical vblank distribution and 0 canary trips — **1.0 %,
> declined**: not worth a ~3 ms whole-CPU freeze per frame that no pin can see (sound pump + IKBD
> latency), knob kept as `GAME_SCROLL_HOG=1`. **Cadence (leg 0): STE gate 105.47 -> 99.25 ms (-5.9 %),
> STE drive 97.34 -> 90.72 (-6.8 %); vs stock ST that is -23.8 % / -8.7 %** (was -19.2 % / -2.1 %).
> **The ST path got FASTER too (gate 130.45 -> 130.30, drive 99.88 -> 99.40) — and that was not free:**
> splitting `rm_blit_road_scroll` into a shared scalar head + `rm_scroll_draw` first cost **+13,690
> cyc/frame** because GCC stopped strength-reducing `copy_run` across the new function boundary
> (double-indexed `move.l (aN,dI.l),(aM,dI.l)` instead of `move.l (aN)+,(aM)+`, ~17 cyc x 800 longs);
> rewriting `copy_run` as an explicit post-increment pointer walk recovered it and 1,254 cyc more —
> bench `blit_road_scroll` **96,514 -> 95,260 cyc (12.06 -> 11.91 ms)**. Pins: sweep **5,608/0** incl. a
> new **640-case EXHAUSTIVE** road-scroll section (every reachable `hscroll_pos`, both delta signs, whole
> `ScrollState` compared), `--mutate 7..10` **4/4 caught** (640/640/304/300 — the last two exactly the
> `edge>=1` and `edge>=0 & shift!=0` case counts) with 1-6 unregressed, goldens x5 st + x5 ste at default
> AND `--memsize 1`, A/B 0-mismatch, `make test` 730, route counters `routed=201/251 declined=0`.
> **Footprint +1,056 B (708,804), so the 1 MB STE margin drops 10,620 -> 9,564 B** — verified live at
> `--memsize 1 --machine ste` (tables placed, all three routes bound). Full design: `BLIT_STE_SPEC.md`
> §16.

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

### A3 phase 1 — hand-asm objshift2 core LANDED (2026-07-23; the fixed-pass engine dropped to asm)

The pure-C levers on `rm_blit_objshift2` were exhausted (C1 landed the straddle switch; C2 mask-immediate
reshaping REGRESSED twice). The residue is the C-ABI/register-allocation overhead GCC cannot shed — so
phase 1 replaces the fixed-pass engine with a hand-written m68k core, `src/asm/objshift2.S`, ported from
the ORIGINAL game's own `blit_objshift2 @0x13ed6` (the measured template, 262,940 cyc). **The C stays the
byte-exact reference** (`src/blit.c` `rm_blit_objshift2`, still fuzz-pinned by `test/test_blit_engines.py`);
the asm is a drop-in with the same signature.

**Selection mechanism (C is reference, asm is the shipped hot path).** `include/game.h` defines a dispatch
macro `RM_BLIT_OBJSHIFT2` → asm (m68k builds) / C (host); `src/object_list.c`'s call sites call the macro.
Per-core flags (F10): the m68k build scripts (`bench_build.sh`, `build_game.sh`) pass one umbrella flag
`-DRM_ASM_BLIT`, which turns on the individual core flag `RM_ASM_OBJSHIFT2` (the macro keys off *that*);
phase 2's `rm_blit_objshift` core will get its own `RM_ASM_OBJSHIFT`, so each core is independently
bisectable. The scripts link `objshift2.S` (a `.S`, so cpp runs first — it `#include`s the shared blit
constants; see F11). The host test build defines no flag, so the 558-test host suite keeps pinning the C
reference unchanged.

**What the asm does differently from the C (the original's tricks, ported):**
- `moveq #-1` mask seed — the 0xFFFF high word that rotates into col0's straddle half is free, vs the C's
  `oril #-65536` (16 cyc) the compiler wouldn't drop (C2).
- mask split into the two column masks by `move`/`swap` shuffles (4-cyc ops) instead of `andi.w` immediates.
- both destination columns walked with `(a0)+`/`(a2)+` post-increment; source with `(a1)+` — the cheapest
  addressing mode, no `dst+offset` rebuild.
- the three BASE families (`width_idx` 0/1/2 → 3/2/1 straddle cells) are each a fully-unrolled row loop —
  zero per-cell loop control; the per-row rewind is held in `d3`/`d5` (F3) so the row bookkeeping is 3
  `suba.w %dN,%aN` (8 cyc) + `dbra`, matching the original, not the `suba.w #imm` (12 cyc) it first used
  nor the C's cursor-triple stack reload. The (cold) LEFT/RIGHT clip ladders + edge cells are transcribed
  for correctness. A `bmi` at entry (F1) skips a bit-15-set `rows_m1` — the C draws `(int16)rows_m1+1 <= 0`
  = zero rows there, and a plain 16-bit `dbra` would otherwise loop up to 65536 times.
- the one structural change from the original is the ABI: the original is register-in
  (`x@D0 rows_m1@D4 dst@A0 src@A1`); this implements the remaster C signature, reading its 7 stack args
  and doing a GCC-style `movem.l %d2-%d7/%a2-%a3` save/restore — the only overhead over the original's
  zero-prologue core.

**Measured on the gate frame (`tools/bench.py` / `tools/profile.py bench_objlist_fixed`), post-F3:**
- **`rm_blit_objshift2` (the fixed-pass engine): C 314,216 cyc (39.28 ms) → asm `rm_blit_objshift2_asm`
  264,930 cyc (33.12 ms) = 0.843×, −49,286 cyc (−6.16 ms).**
- **`bench_objlist_fixed` (the whole fixed pass): 325,424 → 276,138 cyc (40.68 → 34.52 ms).**
- Isolated head-to-head microbench (`bench_objshift2_c` vs `bench_objshift2_asm`, one base-straddle-3
  blit × 0x2a rows): **56,658 → 47,266 cyc = 0.834×** (data-independent, same-build A/B).
- Whole object tree **573,948 cyc = 71.74 ms**; TOTAL (frame, funcs-sum) **1,260,780 cyc = 157.60 ms**.

**Gap to the original (F2 — the earlier "exactly the movem" claim was wrong).** Before F3 the asm profiled
269,118 cyc, +6,178 over the original's 262,940. That gap decomposes (per the review) as: the C-ABI
`movem` save/restore ≈ 890 cyc (≈148/call × ~6 calls); a per-row `suba.w #imm` (12 cyc) regression the
first cut carried where the original holds the rewind in a register ≈ 2,900; and C-ABI argument
marshalling + the runtime width-family dispatch ≈ 2,400 — NOT a single `movem` term. F3 switches the three
hot base loops to register-held rewinds (`suba.w %dN,%aN`, 8 cyc), measured **−4,188 cyc** on the profile
(more than the ~2,900 the review estimated for that term), taking the asm to 264,930 — **+1,990 over the
original**, the residue being the `movem` prologue + the C-ABI marshalling/dispatch the register-in
original skips.

**Verification.** A Musashi-executed differential, `test/test_asm_blit.py`, runs every objshift2 fuzz case
(3 width families × 16 fine-x × 12 clip/edge/base columns × 3 row counts = 1728, PLUS a 12-case bit-15-set
`rows_m1` list, F1 = **1740 cases**, sharded into 8 chunks) through BOTH the C entry and the asm entry on
`bench.elf` under the cycle-accurate 68000 (via a `bench_main.c` param-block wrapper). The compare is
bracketed (F5): the whole dst window plus GUARD bytes either side of it plus the src buffer must be
byte-identical between the C and asm runs — a guard/src divergence flags a wild asm store past the window.
A positive control (F4) asserts the known base-drawing cases changed dst from the pre-blit noise, so a dead
harness (broken param block / renamed wrapper) fails loudly instead of false-greening C==asm. The harness
is driven by an engine descriptor (F12) so phase 2 adds a descriptor + case table, not a parallel class;
`_x_for` and the flat-image loader are imported from `test_blit_engines` / `tools/bench.py`, not copied
(F7). Wired into `make test` (bench.elf is a Makefile prerequisite — now also rebuilt when the build glue
changes, F6; a missing elf FAILS with a build hint, never silently skips). **Mutation check**: flipping the
cell's `not.w %d1` → `not.l %d1` corrupts the high mask word and the suite fails; restored, green again.
`make test` **566 passed** (558 host + 8 asm-differential chunks); `run_golden.py` **MATCH on all 5 legs**
(the flagged GAME binary runs the asm path in Hatari — the end-to-end pin).

**One source of truth (F11).** The engine constants the asm shares with the C were duplicated (`.equ` in
the asm, `#define` in `blit.c`): hoisted into `include/blit_const.h` (a `#define`-only, asm-safe header
`blit.c` and `objshift2.S` both `#include`), and `SCREEN_ROW_BYTES` now comes from `screen.h` (its C-only
parts guarded behind `__ASSEMBLER__`) — which is *why* the asm is a `.S`. The refactor is verified pure:
the `rm_blit_objshift2_asm` section objdumps byte-identical before/after.

**What the differential pins, honestly (F13a).** `test_asm_blit.py` is an EQUIVALENCE pin (asm == C), and
the C reference itself is directly oracle-fuzzed only at `width_idx 0` (only `g_blit_objshift2` has a
public recreate entry). For `width_idx 1/2` the asm-vs-C differential still proves the two agree, but the
C's own correctness there rests on the composed-frame differential (`test/equiv.py`) and the 5-leg goldens,
which drive the dispatcher through all three families — not on a direct leaf-level oracle fuzz.

**Deferred to phase 2:** `rm_blit_objshift` (pass 1) — its spill residue is the other hand-asm target
(PERF30 L2/E-sweep noted the register-pressure wall no C shape relieves). Not started here. F8/F9 already
de-duplicated the bench harness (`bench.py` folds the A/B rows into one staged image; `bench_main.c` shares
one arg-marshalling macro) so the phase-2 core slots in with minimal new scaffolding.

### A3 phase 2 — hand-asm objshift core LANDED (2026-07-23; the colour-indexed pass-1 engine dropped to asm)

The second (and last hot) fine-x engine, `rm_blit_objshift @0x14680`, is now a hand-written m68k core
(`src/asm/objshift.S`) behind the same `-DRM_ASM_BLIT` umbrella (its own per-core flag `RM_ASM_OBJSHIFT`,
dispatch macro `RM_BLIT_OBJSHIFT` at `object_list.c`'s three call sites). **The C stays the byte-exact
REFERENCE** (`rm_blit_objshift`, still compiled + fuzz-pinned); the asm mirrors the ORIGINAL game's own
`blit_objshift` (the measured template, **110,572 cyc**).

**Result — it lands essentially at the original.** On the gate frame (`profile.py bench_objlist_pass1`):
**`rm_blit_objshift_asm` = 111,192 cyc = 13.90 ms**, vs the C's **181,836** (with the per-function IRA
attribute) — **−70,644 cyc (0.61×)**, and only **+620 cyc (+0.6%) over the original's 110,572**. That is
below the 115–135k target zone (the target budgeted more C-ABI overhead than the register-held source
rewind actually costs). `bench_objlist_pass1` **229,948 → 159,304 cyc** (the whole pass-1 scope, asm path;
229,948 is the C3-landed baseline = 28.74 ms, and 229,948 − 159,304 = 70,644 = exactly the engine delta).
Same-build A/B microbench (`bench.py`, one base-straddle-1 blit × 0x2a rows): **objshift C 40,616 → asm
24,762 cyc = 0.610×** (data-independent). Whole object tree **503,468 cyc = 62.93 ms**; TOTAL (frame,
funcs-sum) **1,190,300 cyc = 148.79 ms** (objshift2 phase-1 basis was 157.60 ms → −8.8 ms from this core).

**Gap to the original, decomposed honestly (F2).** Headline: **+620 cyc** — the recon's asm over the gate
frame's **6 objshift calls** (111,192) vs the original's **110,572** template. The scopes differ (caveat
below), so read +620 as indicative, not a clean per-call delta. The terms, over the recon's 6-call frame:
- **movem save/restore, +888.** The C-ABI entry adds `movem.l %d2-%d7/%a2-%a3`: 72 cyc/call save
  (`MOVEM.L` 8 regs reg→mem = 8+8·8) + 76 restore (mem→reg = 12+8·8) = 148/call × 6 (the entry-`movem`
  PC profiled exactly 432 = 6 × 72, confirming the call count).
- **register src-rewind claw-back, −760.** The asm rewinds the source with a register op `suba.l %a3,%a1`
  (8 cyc) where the original does a memory-indirect `suba.w (a3),a1` (12 cyc; its register ABI passed
  `stride` BY POINTER in a3) — 4 cyc/row × ~190 rows across the frame.
- **C-ABI marshalling + in-function `color_pairs` indexing, ≈ +500.** A REAL net add: the original receives
  its args in registers and bakes `color_pairs[color]` as an immediate; the recon reads the 10 stack slots
  (`movea.l`/`adda.l`/`move.w`) and indexes `color_pairs` at runtime. The original's caller-side register
  setup is OUTSIDE the 110,572 baseline, so it cannot cancel this.

These terms sum to 888 − 760 + 500 = **+628 ≈ the measured +620**. NOT a single "movem" term. **Scope
caveat:** the original's 110,572 is an **8-call** frame — 2 of those are off-edge early returns (≈ +280)
the recon's frame does not make; on matched scope (drop the 2 off-edge returns) the gap widens to ≈ **+900
≈ the movem term** alone. Either framing lands the engine within ~0.6–0.8% of the original.

**What the asm does differently from the C (why it wins).** The engine is COLOUR-INDEXED: each of the 4
planes ORs the shifted source word gated by that plane's `color_pairs[color]` fill. The asm (a) loads the
four fill words ONCE per call into `d3`/`d5` as two 32-bit pairs and `swap`-toggles them per plane (2
registers hold 4 halves — no per-plane `color_pairs` reload, no `objsh_fill_half` ladder), (b) builds the
`~(a|b|c)&d` SHOW mask with a `moveq #-1` seed so the load-bearing `0xFFFF` high word is free, (c) fully
unrolls all 4 planes with `(a1)+` source walking and interleaved `and.w`/`or.w` memory RMW (plane 3 folds
the transparency `~mask` inline), (d) bakes the per-family dst rewind as an immediate and holds the runtime
src rewind (`stride + 8·(cells−1)`) in `a3`. The families (BASE / LEFT ladder with skips / RIGHT ladder off
the 0x98 bound) and both `base_cells` 1/2 width families dispatch to straight-line unrolled row loops (no
per-cell branch). The signed `stride` (8 → net source step 0 = re-read the row; 0xa8 → −160; −8 → +16) is
handled by `suba.l %a3,%a1` where `a3` is sign-extended from the stack slot — the fuzz drives all four.

**Bring-up bug the fuzz caught.** The base-vs-right ceiling test first used `d3` as a scratch (`move.w
%d0,%d3` …) — but `d3` holds colour fill pair 0. That clobbered `fill.plane[1]` (its low word) while
leaving `fill.plane[0]` (high word) intact, so plane 0 was correct and plane 1 diverged by a few bytes.
Reworked the test to use only `d0`/`d2`. The differential flagged it on the first run (small per-plane
diff on every BASE case); pinned.

**Verification.** `test/test_asm_blit.py` gains an `OBJSHIFT` engine descriptor (F12 — a second descriptor
+ case table, not a parallel harness class; the one engine-agnostic `_Harness` gained an optional read-only
`color_pairs` buffer it stages with a distinct-byte table so the colour gate bits vary). Both engines' chunk
tests now call ONE descriptor-driven runner `_run_engine_chunk` (the objshift2/objshift bodies had drifted
into a ~25-line copy-paste), with two thin per-engine pytest entry points so xdist sharding and the
per-engine labels stay intact. Cases mirror `test_blit_engines.py`'s objshift fuzz and widen it: both
`base_cells` families × 16 fine-x × 12 clip/base/off-edge columns × the same four `(color, rows_m1, stride)`
tuples (strides **8 / 0x10 / −8 / 0xa8**), PLUS a bit-15-set `rows_m1` list (F1: the C draws 0 rows; the
asm's `bmi` guards the 16-bit `dbra`) = **1,560 cases**, sharded into 8 chunks. The compare is bracketed
(F5: dst window + GUARD + src + the color_pairs table) with the F4 positive control. **Mutation check (both
engines, re-run through the reshaped runner):** flipping objshift's `OSH_PLANE_LAST` `not.w %d2` → `not.w
%d1` (wrong register for the col1 transparency fill) fails all 8 objshift chunks; flipping objshift2's cell
`not.w %d1` → `not.l %d1` (corrupts the load-bearing 0xFFFF high mask word) fails all 8 objshift2 chunks;
each restored, green again. `make test` **574 passed** (558 host + 8 objshift2 + 8 objshift asm chunks);
`run_golden.py` **MATCH on all 5 legs** (the GAME binary now runs BOTH asm cores in Hatari — the end-to-end
pin). The shared constants `OBJSH_NIBBLE`/`OBJSH_SUBPX_BITS`/`COL_ALIGN`/`OBJSH_RIGHT_BOUND` were hoisted
from `blit.c` into `include/blit_const.h` (F11), joining `OBJSH_CELL_BYTES` there (consumed by `blit.c` +
`objshift.S`; `objshift2.S` bakes its own immediates and takes only `OBJSH_CELL_BYTES` / `OBJSH2_*`).

**Coverage honesty.** Two branches are unexercised by BOTH the host fuzz (`test_blit_engines.py`) and the
Musashi differential, mirroring each other, because no game data reaches them: `base_cells` ∉ {1,2} (the
asm's BASE path falls to the 2-cell family — see the objshift.S CONTRACT note; every `object_list.c` caller
passes 1 or 2) and `color` ≥ 16 (the fill index `(color & 0xf) << 3` only ever sees nibbles 0..15). Per
CLAUDE.md these stay honestly unpinned — a branch the game's own data never drives, not a missing test.

**A3 follow-ups (deferred).** `src/object.c` carries a historical duplicate `#define COL_ALIGN 0xfff8` of
the value now hoisted into `blit_const.h`; fold it onto the shared constant (out of scope here — object.c
was untouched, so `blit.c`'s "single source" note points at the duplicate rather than claiming to erase it).

**Both hot fine-x engines are now hand-asm.** `objsprite` (the third, cold family) stays C. A3 is done.

### A4 — render_road pointer cursors + B/D localization LANDED (2026-07-24; 50.64 → 43.79 ms)

The C-shape levers from the blitter campaign (P4 real-pointer cursors, cursor localization) carry to
the road; the plan's per-flag-combo specialization does **not** (measured reasoning below). Landed, all
byte-exact every step (`make test` 700 passed; `run_golden.py` MATCH ×5 on-target):

- **P4 real-pointer cursors (all bands).** The blit primitives took `(Framebuffer*, Offset *dst)` and
  recomputed `fb->px + *dst` per write; the copies in bands B/D compiled to base+index
  `%fp@(4,%d6:l)` accesses (+6 cyc each). Converting the primitives to walk a native `uint8_t*`
  (formed once per row/tail per st.h's offset-first rule) makes every store displacement/post-increment.
  **405,148 → 378,890 cyc (−26,258; 50.64 → 47.36 ms).**
- **B/D cursor localization.** `rr_band_B`/`rr_band_D` mutated `r->param/width/edge/dst` through the
  `rr_regs*` per scanline; GCC must assume every framebuffer store aliases `r->*` and re-wrote the
  struct fields every row (`movel %aN,%a2@(12/16/20)`). Pulling the cursors into locals (write back
  once at return) keeps them register-resident. **378,890 → 355,998 cyc (−22,892; → 44.50 ms).**
- **Review-gate hardening (net −5,688 on top).** The gate's verify pass confirmed the pointer
  conversion formed out-of-object pointers before their guards at three sites (band A shoulder walk,
  B-far/C-far tails — strict-C UB the old uint32 Offset math was immune to; harmless at -O2 today).
  The B-far/C-far hoists are free; band A's shoulder fill was reshaped into two phases — the skip
  prefix (cells past the row end, the actual UB) walks in Offset space forming no pointer, then the
  in-bounds write loop runs the fast predecrement pointer walk with the skip test dropped entirely.
  The naive all-Offset rewrite was measured **+8,012** and rejected; the two-phase shape is faster
  than the pre-fix code: **355,998 → 350,310 cyc (→ 43.79 ms, 0.79× recon)**. Also: `rr_fill_full_row`
  folded into `rr_fill_row` (post-refactor duplicate), `_Static_assert(RR_ROW_LONG_PAIRS * 8 ==
  RR_ROW_STRIDE_D2)` pins the fill/stride coupling the old cursor-advancing fill enforced by
  construction.
- **Gate frame TOTAL 1,190,068 → 1,135,230 cyc = 148.76 → 141.90 ms.** Original binary reference for
  the stage: 207,232 cyc / 25.9 ms — remaining gap is ~1.69×.

**Dead ends (measured — don't retry):**
- **Localizing bands A/C: +7,526.** A/C inline into `rm_render_road`; three resident cursor-sets
  spill (same register-pressure wall as L2/E2). The asymmetry is fenced by a why-not comment at
  `rr_band_B`'s localization note.
- **IRA `region=one`+`priority` attribute: +5,648 on B/D, +8,622 on `rm_render_road`.** The road is
  store/loop-control-bound, not spill-bound like objshift — the allocator lever regresses here.
- **All-Offset band-A shoulder walk: +8,012** (see above; the two-phase reshape is the right form).

**A4-proper (per-combo specialised writers) not pursued.** The flag census (77 staged frames, legs
0–4 × warmups; temporary `RR_CENSUS` instrumentation, removed) shows the dispatch fans wide —
14–38 distinct `(flags, col_sign)` combos per band, skewed ~45% to `flags=0` everywhere (D-far's
largest bucket is `col<0`, road off the left edge, 1819/6930 rows) — but the after-profile puts
`rm_render_road` (A+C inlined) at 248,526 cyc dominated by irreducible fill/copy stores
(`movel %d2,%a0@(4)`) and band A's variable-count shoulder-fill loop control; `rr_band_B`/`rr_band_D`
at ~54k each with the base+index gone. Dispatch is a small fraction — specialising it can't pay.
Below this the road needs hand-asm (A3-style) or the **B2 display list** (do less work per frame),
which is the next front.

**Deferred (noted by the review, needs its own re-measure):** band B open-codes
`rr_draw_edge_cell`'s body at three sites and bands C open-code `rr_fill_shoulder`'s fill at two —
verified byte-equivalent, but both helpers are static non-inline and new call sites could shift
inlining in the hot loops; collapse only with a bench before/after.

### B2 measurement — DECIDED: NO-GO (road display list does not pay). 2026-07-24

B2's premise — "the per-scanline control stream only changes when (curve, view-bank, near-slope)
change" — is **false, measured**. The control table is a moving perspective surface: its per-scanline
road widths change on plain **forward motion, every frame**, before any steering. Census tool:
`tools/road_dl_census.py` (legs 0–4 × 300 real frames, the `frame_dist` drive; forced advance/frame,
input=0). Structural fact (road.c / geometry.c / fixtures): the display list (op sequence + source
offsets + fill counts) is a pure function of `width_tbl` content + the view-selected edge window;
`param`/`edge`/`edge_const`/`tex` are static, never branched on — so "DL changed ⟺ `width_tbl` (or
the edge bank) changed."

- **Q1 streams:** `width_tbl` changes **90.6%** of frames (mean 68 B of 512); `param` **0.0%**
  (static fixture); `tex_base`/`hscroll` 0%. (`edge` shows 100% only because forcing an advance every
  frame toggles `view_bank`/`road_edge_sel` — a harness artifact.)
- **Q2 steering (the central question):** curve enters the control-long **low words per-row as a
  RAMP** (`spread_curvature` accumulates curve/106 down the rows), not a per-frame scalar. Δcurve=±1
  changes 54/106 low words and the shape DL; ±8 → 100/106; +64 → per-row deltas `[1,10,19,…,64]`.
  A steering-continuous stream — any steered frame is a cache miss. (`test_geometry`'s "byte-exact
  under arbitrary steering" is a correctness pin, not an invariance claim.)
- **Q3 cache hit rates (1500 frames pooled):** FULL DL (op seq + operands — what a replay must
  reproduce) changes **100%** frame-to-frame; content-addressed hit 20.5%; per-(curve, view, bank,
  seg, markers) tuple hit **17.5%** (1237/1500 tuples unique; tuple space unbounded — curve is
  ~continuous 16-bit, 13×16-bit slopes, 14×16-bit markers). SHAPE-only (ignores operands — the most
  optimistic possible cache) still changes 79.9%; best-case content hit 30.7%.
- **Q5 wraps:** the build is a pure function of (pose, ring); the wrap double-build differs by
  exactly the per-advance delta (~68–79 B on ~90% of advances) — a cache must rebuild around every
  course advance.
- **Q6 store floor** (`bench_render_road` 350,310 cyc, per-PC classified): pixel stores/RMW 78,044
  (22.3%) + copy/table loads 32,580 (9.3%) = **110,624 cyc irreducible (31.6%)** a replay still pays;
  branches/dbf 29.0% + per-row setup 39.4% are only partly removable and must be re-spent building
  the DL on every miss.
- **Economics:** a miss (≥80% of frames unsteered, ~100% steered) costs *build + replay* > a plain
  render; a hit costs the replay (~110k + flat-op overhead), which does not beat the original's
  207,232 cyc; weighted at ~17% hit, B2 is break-even-to-worse than today's 350k. RAM seals it:
  ~2.3–4.6 KB per cached DL (384 band-rows × 6–12 B) × the hundreds of live buckets needed, against
  a ~927 KB build with ~97 KB headroom on a 1 MB ST.

**Honesty caveats:** the drive forces a course-advance every frame (over-states advance frequency;
the physical driver — perspective widths move on forward motion — holds regardless) and has no
steering input (recon input glue is a no-op host-side; Q2's poke experiment covers steering, and it
only worsens the miss rate). The SHAPE fingerprint's constant texture can only *under*-count shape
changes, so the true best-case hit is ≤30.7%. Neither caveat is close to flipping a verdict that
fails on both the hit-rate and store-floor axes.

**Verdict: NO-GO. Fallback = hand-asm the current seven bands (A3-style), targeting the original
binary's 207,232 cyc / 25.90 ms** — the store-bound faithful floor (remaster: 350,310 = 1.69×). The
original is itself a per-row interpreter with no display list, so it is the correct ceiling; the gap
is register discipline on the stores/loads/loop control, exactly the lever that landed objshift and
objshift2 within ~0.6% of the original.

### Road-asm slice 1 — hand-asm band D LANDED (byte-exact), but a lone asm band nets ~break-even. 2026-07-24

Following the B2 NO-GO fallback ("hand-asm the current seven bands, A3-style"), slice 1 ports render_road's
band D (near + far copy) to a hand-written m68k core, `src/asm/road_band.S` (`rr_band_D_asm`), behind
`-DRM_ASM_ROAD` (per-core flag `RM_ASM_RR_BAND_D`; dispatch `RR_BAND_D_FN` in road.c). The C `rr_band_D_c`
stays the byte-exact reference. **The core is correct and 27% faster in isolation, but composing a single
asm band into the otherwise-inlined C road de-inlines its neighbours, so the gate-frame road is break-even
— a measured cost that only a SECOND ported band amortises.**

**Which band + why.** Band D is one of the two ~54k standalone band functions (B/D) the A4 note flagged; D
was picked over B because its near/far tails share the most structure (both end in a reset-to-row-start
forward fill + `rr_fill_full_row`), so the transcription cribs cleanly from the original's machine model
(`recreate/src/machine/road.c` rr_band_D @0x987c/@0x9950). The asm mirrors that register map (a2=row-start
dst, a0/a1=working dst/src, a3=tex, a4/a5/a6=param/width/edge, d3=mask, d5/d6=fill, d2=stride, d7=col-mask,
d4=dbra), adapting only the addressing to the remaster ABI (RoadInput native pointers + an Offset dst
rebased onto fb->px; write-back of param/width/edge/dst at return) exactly as objshift2.S adapted the blitter.

**Isolated: the asm wins (profile.py bench_render_road, per-PC).** `rr_band_D_asm` = **38,722 cyc** vs the
C `rr_band_D` **53,240** = **0.73×, −14,518** on the gate frame — squarely in A3 territory, the register-held
cursors + (aN)+ stores beating GCC's struct-localized C.

**Composed: it does NOT pay (the neighbour-inlining tax).** render_road with band D asm = **352,968 cyc**
vs the pre-slice C road **350,310** = **+2,658 (+0.76%)**. Cause, measured every way: the moment
rm_render_road contains an opaque external asm call, GCC drops band A from a resident inline into a cold
`.constprop` clone (**+17k cyc**) — the "A/C inline into rm_render_road" wall from A4, now tripped by the
asm call rather than by localization. `always_inline` on bands A + C_near + C_far pins them resident and
recovers the clone penalty to a worse-regalloc residue, but the residue (~+17k) still slightly exceeds
band D's 14.5k saving. `noinline`/`noipa` wrappers, an `optimize()` growth-param attribute, and guarding
the unused C body out were all tried and did not move it (all leave A de-inlined or spilling). Host suite
+ 5-leg goldens stay byte-exact throughout.

**Why this is groundwork, not a dead end.** The +17k de-inline is a ONE-TIME cost of having *any* asm band
inside the C road — it does not grow with the number of asm bands (band A is already de-inlined). So slice 2
(band B, the sibling ~54k standalone function) adds ~another −14k with ~no further de-inline tax, flipping
the composite to a clear net win (~339k, below the 350,310 C floor). The lone-band break-even is the price
of admission; the campaign pays off from the second band on.

**Shipping decision (this commit): the game holds on the C band D.** `build_game.sh` does NOT pass
`-DRM_ASM_ROAD`, so `RR_BAND_D_FN` defaults to `rr_band_D_c` and the game runs no regression; the flag flips
ON when slice 2 makes the composite net-positive (re-golden then). The core, the differential and the bench
A/B stay landed and verified via `bench_build.sh` (which DOES pass `-DRM_ASM_ROAD` + `-DRM_ROAD_DIFF`).
road_band.S assembles unconditionally and `rr_band_D_c` compiles unconditionally (as blit.c/objshift2.S do),
so only the dispatch macro keys off the flag — undefining it A/Bs the band on every build.

**Verification.**
- **Differential** `test/test_asm_road.py` (Musashi, sharded by LEG — 5 shards + a staging-pin test): each
  leg's mid-race road is simulated ONCE and checkpointed at warmups 60/90/120 (prefixes), then
  `adapter.road_input` extracts the five road buffers (as test_road.py does) and pokes them + a
  GUARD-bracketed background into the bench's `rr_diff_*` staging. `test_staging_matches_adapter` pins those
  buffer sizes against the bench ELF's own symbol spacing (nm), so a C-side resize can't false-green. Each
  frame runs the WHOLE road three ways — band D = C (`bench_road_run_c`) vs asm (`bench_road_run_asm`) vs the
  SHIPPING `rm_render_road` (`bench_road_run_shipping`) — and byte-compares the framebuffer + GUARD + the
  read-only inputs: C-vs-asm isolates band D, and shipping-vs-asm pins the duplicated `render_road_bandD`
  pipeline against `rm_render_road`. Positive control: a no-op-band-D run must draw a different frame (per
  leg). **Mutation check**: flipping the near shoulder-fill `%d5`→`%d6` fails the differential; restored, green.
- `make test` **706 passed** (700 host + the road-asm shards; test_asm_blit unchanged).
- `run_golden.py` **MATCH ×5** — the GAME build (now on the C band D) is byte-identical to recreate's
  pipeline on all 5 legs. The asm's own on-target pixels are pinned by test_asm_road.py; re-golden with the
  flag on at slice 2.

**Next slice (2): port band B** (`rr_band_B`, ~54k, the other standalone A4 band) to `road_band.S` behind its
own per-core flag `RM_ASM_RR_BAND_B`, reusing this differential harness (add a `bench_road_run_*` pair / a
`bench_road_bB_*` micro A/B). ABI/contract note: band B's write-back is identical (param/width/edge/dst at
return) and it shares the src-dispatch shape, but its near/far tails differ from D — near does `+8` to both
cursors before the asr, and its far tail (0x9514) has TWO fill shapes (a `moveq #$13` dbf-counted fill AND
the shoulder fill) plus a distinct full-fill; crib the machine model rr_band_B @0x93c2/@0x948c. Expect band
B asm to add ~−14k with no further de-inline tax → the composite drops below the C floor.

### Road-asm slice 2 — hand-asm band B LANDED; composite drops BELOW the C floor (the amortization pays off). 2026-07-24

Slice 1 predicted the lone-band break-even would flip positive once a SECOND band ported (the +17k
band-A de-inline is a one-time cost, not per band). Slice 2 ports band B (`rr_band_B`, the other ~54k
standalone A4 band) to a second core in `src/asm/road_band.S` (`rr_band_B_asm`), behind its own per-core
flag `RM_ASM_RR_BAND_B` under the `RM_ASM_ROAD` umbrella. **Prediction confirmed: render_road now runs
below the pre-asm C floor, and the shipping game build turns both asm bands ON.**

**Result — the composite beats the C floor.**
- **`rr_band_B_asm` = 38,552 cyc** vs the C `rr_band_B` **54,084** = **0.71×, −15,532** (profile.py, per-PC) —
  same A3 register discipline (row-start/working cursor pair, (aN)+ stores, register-held rewinds).
- **render_road (bands B+D asm) = 337,984 cyc / 42.25 ms** vs the pre-asm C floor **350,310** = **−12,326
  (0.965×)**, and vs slice 1's band-D-only **352,968** = **−14,984** (band B's contribution, ≈ its isolated
  saving — the de-inline tax did NOT grow). 0.75× the machine-model reference, 0.76× the idiomatic recon.
- **Gate TOTAL 1,122,904 cyc / 140.36 ms** (bands B+D asm, both blit cores asm). render_road vs the ORIGINAL
  binary's 207,232: **1.63×** (was 1.69× pre-asm-road).

**Structure (reused slice 1's, per the review's reuse bar).** Band B is a second `.globl` core in the same
`.S`; the movem prologue + the param/width/edge/dst write-back epilogue (the shared A4 localization ABI) are
now `RR_BAND_PROLOGUE` / `RR_BAND_EPILOGUE` macros used by BOTH cores — band D's bytes are unchanged
(differential + goldens confirm). The CONTRACT block is extended, not restated (the slice-1 hazard): it now
covers the d7 invariant for both — band B's C reads `r->d7` (its `col_mask` local) and its asm reads `r->d7`,
so they agree unconditionally; band D's C hardcodes `RR_D7_WORD_MASK` while its asm reads the field, agreeing
via the post-group-step invariant. road.c: `rr_band_B` → `rr_band_B_c` (`__attribute__((unused))`, compiled
unconditionally), `RR_BAND_B_FN` dispatch mirrors band D. The differential's `render_road_pipeline` now takes
BOTH band pointers so either can be swapped C-vs-asm while the other stays its shipping core; the bench
measures ONE all-asm baseline and compares each band's C-isolation against it (no per-band asm re-run of the
identical config), and the fill-count immediates (`moveq`) are all derived from `RR_ROW_LONG_PAIRS`.

*Deferred to slice 3:* the per-row header decode (14 instructions) and the const-strip select are
instruction-identical between the two cores, but their macro extraction is deferred — it would trade
read-against-the-machine-model clarity and force re-verification of both cores, and only earns its keep at
THREE copies (when band C ports). Revisit it with band C.

**Verification.**
- **Differential** `test/test_asm_road.py`: the leg-sharded harness now carries a `BANDS` descriptor
  ((c/asm/noop) wrapper names per band), so ONE harness covers B and D — both run on the same per-leg
  simulation, byte-compared over framebuffer + GUARD + read-only inputs, with the shipping-pipeline-drift
  pin (each band's both-asm run == `rm_render_road`) and per-band no-op positive control. **Mutation checks
  BOTH cores**: flipping band B's near shoulder-fill `%d5`→`%d6` fails the differential; likewise band D's;
  restored, green.
- `make test` **706 passed** (band B folded into the existing 5 leg shards + the staging-pin test — no new
  shards, per the reuse bar).
- `run_golden.py` **MATCH ×5** — the GAME build (now `-DRM_ASM_ROAD` ON: bands B+D asm) is byte-identical to
  recreate's pipeline on all 5 legs in Hatari.

**Next (slice 3): the inlined bands A and C, or a stop-point call.** What remains between 337,984 and the
original's 207,232 (1.63×) is dominated by bands A (~146k, 46% — inlined) and C (~91k+4k, 26% — inlined);
B/D are now ~38.5k each, essentially at the original's efficiency. The catch: A/C are `always_inline` INTO
`rm_render_road` (three resident cursor-sets; A4 measured localizing them at +7,526), so they are NOT
standalone functions to swap. BUT the +17k de-inline tax the asm bands pay is EXACTLY the cost of band A
being inlined — if A (and C) themselves become asm cores, there is nothing left to de-inline, so that tax
disappears too. Porting A/C is the path to the original's floor; it is more work (band A alone is 96 rows
with the shoulder-fill/interior sub-shapes) and needs its own ABI (A runs before the first group step, so
d7==0 there — the CONTRACT's d7 invariant does NOT hold for A; its col uses d7 as scratch). Alternatively,
1.63× may be an acceptable stop for the road: the two hot standalone bands are done, and the remaining gap
is the inlined-band register-pressure wall A4 already charted. Recommend profiling band A's C vs a hand-asm
estimate before committing slice 3.

### Road-asm slice 3 — bands C + A LANDED; the whole road is asm, at 1.11x the original. CAMPAIGN CLOSED. 2026-07-24

Slice 3 finishes the road: it ports the remaining bands to hand-m68k cores in `src/asm/road_band.S` in two
sub-phases. **Phase 1 = band C** (`rr_band_C_near_asm` + `rr_band_C_far_asm`, one umbrella flag
`RM_ASM_RR_BAND_C`), **phase 2 = band A** (`rr_band_A_asm`, `RM_ASM_RR_BAND_A`). With all seven writers asm,
`rm_render_road` is pure C glue calling seven cores + the group steps — **no band is inlined, so the +17k
GCC de-inline tax that slices 1-2 carried is gone**, and the `always_inline` mitigation on bands A/C was
removed with the port.

**Result — render_road lands at the original's register-discipline floor.**
- **render_road (all seven bands asm) = 230,766 cyc / 28.85 ms** vs the ORIGINAL binary's **207,232 =
  1.114x** (0.52x the idiomatic recon; 0.51x recon's machine-model transcription). The 23.5k residual is
  the per-band C-ABI overhead — 7 `movem` prologue/epilogues + the rr_regs struct load/store per call + the
  glue — the same "C-ABI residue over the register-in original" the A3 blitters showed, scaled to 7 calls
  (~3.4k/call).
- **Gate TOTAL 1,015,686 cyc / 126.96 ms.**
- Per-band asm saving vs its C reference (gate frame, C-isolation minus the all-asm baseline):

  | band | asm saving | x C | note |
  |------|-----------:|----:|------|
  | A       | 62,864 | 0.786 | biggest — the 96-row two-pass renderer; GCC's C was far off the tight original |
  | C-far   | 35,944 | 0.865 | the bidirectional reverse-fill merge tail |
  | B       | 17,928 | 0.928 | |
  | D       | 14,514 | 0.941 | |
  | C-near  |  1,318 | 0.994 | small/cheap band; barely moves |

**Campaign arc (gate render_road, all measured):** pre-asm C floor **350,310** -> slice 1 (D) 352,968
(+2,658, the one-time de-inline tax) -> slice 2 (B+D) 337,984 -> slice 3 ph.1 (B+C+D) 302,594 -> ph.2
(A+B+C+D) **230,766**. **Net campaign win: 350,310 -> 230,766 = -119,544 (0.66x), and vs the pre-A3 road
(50.68 ms recon-era) the whole stack is now 28.85 ms.** The tax elimination is confirmed: slice 2's
always_inline-era all-C-bands road was ~+17k inflated; with band A asm that inflation is structurally gone
(nothing left to de-inline), which is why band A's composite drop (71,828 ph.1->ph.2) exceeds its isolated
62,864 saving.

**Macro extraction (the slice-2 deferral, done at 5 copies + tightened in the slice-3 review).** Two clean,
self-contained shared blocks are extracted, both byte-neutral (differential 0-mismatch before/after;
composite unchanged at 230,766) and mutation-checkable: **`RR_ROW_HEAD`** (8 instructions: reset cursors,
ctrl+param -> half_width, fine-x src offset — all five cores; a flip fails all five shards) and
**`RR_SRCSEL(merge)`** (the plane-hi / SRC_CONST src-strip select — bands A/C-near/C-far, differing only in
the merge-target label, passed as the one macro arg; its plane-hi arm's mutation is caught, though its
const sub-arm is a frame-coverage hole like the others below). The prologue/epilogue were already shared
(RR_BAND_PROLOGUE/EPILOGUE). What is deliberately NOT extracted, pinned with lockstep cross-reference
comments instead: (a) the mask read + `edge_seed` load + fill defaults (order/conditionality genuinely
differ per band — a macro would need per-band params); (b) C-far's row front end through the SPLIT_C
dispatch, instruction-identical to C-near's but the branch TARGETS differ — extracting the flag-dispatch
ladder would obscure each core's flag identity, so C-far's banner states the lockstep and "any edit to one
MUST be mirrored" (the differential pins it). Judgment call per the review's escape hatch.

**Structure.** Band A uses the shared prologue/epilogue too: its `r->d7` (== 0 pre-group-step) seeds the d7
scratch it wants, `d2` (stride) is reused as a saved col and restored before the row tail, `d4` is overridden
to 96 (band A takes no rows arg), and a3/d2 are unchanged at exit so the epilogue's param/width/edge/dst
write-back is exactly right. The differential's `render_road_pipeline` now takes all five band pointers (A,
B, C-near, C-far, D); band C-near/C-far and band A are each isolated separately against the single all-asm
baseline. CONTRACT extended (not restated) for band A's d7-is-scratch / masks-with-the-constant rule.

**Verification.**
- **Differential** `test/test_asm_road.py` (5 leg shards + the staging pin): the `BANDS` descriptor now
  carries A/B/C-near/C-far/D; each is byte-compared (C-isolation vs the all-asm baseline) over framebuffer +
  GUARD + read-only inputs, with the shipping-pipeline-drift pin and per-band no-op positive controls. All
  five bands draw and match on every staged frame. **Mutation checks on both new cores + the extracted
  macro**: band C-near (fast-split shoulder) and C-far (fast-split fill) each fail when flipped; band A
  (width-cursor post-increment) fails; a flip inside `RR_ROW_HEAD` fails all shards; all restored green.
- `make test` **706 passed**; `run_golden.py` **MATCH x5** — the GAME build (all seven asm bands on) is
  byte-identical to recreate's pipeline on all 5 legs in Hatari.

**Mutation-coverage caveats (honest).** Two band paths the staged frames do not exercise, so their flips are
not caught by the differential: band C-far's "road spans the whole row" reverse-fill (the census's rare
bucket) and band A's backward shoulder-fill *value* (on these frames the shoulder pattern has d5==d6, so a
d5<->d6 flip is invisible; the fill IS exercised, only value-insensitive). Both are pinned only structurally
(byte-exact on every exercised frame + the 5-leg goldens). Also band A's col-input mutations (fine-x, the
+param delta) are masked because those inputs are 0 on the staged frames — the col itself (from the road
half-width) is non-zero and fully exercised. Seeding a frame that spans the row / varies fine-x would close
these; deferred as low-value (the original's own data rarely hits them).

**Road campaign closing verdict.** The road is DONE: 1.11x the original's hand-asm, the two hot bands (A,
C-far) at ~0.8x their C, and the residual is purely the per-band C-ABI glue. Closing that last 23.5k would
mean collapsing the seven calls into ONE monolithic asm render_road (like the original's register-resident
loop), which trades away the per-band C-vs-asm differential + the C references as the readable spec — NOT
worth it for 23.5k (0.3 ms). The gate frame TOTAL is now 126.96 ms (was 141.90 post-A4); the remaining
frame cost is the object tree + HUD, not the road. Next campaign front (if any) is `blit_road_scroll` (0.36x
already) or the object tree, not render_road.

### B4/B5 measurement — premises measured false; opaque-dashboard fast path landed (−1.37 ms). 2026-07-24

Both remaining Tier-B items were investigated measure-first (scratch probes over real staged frames)
and their premises do not hold in the real pipeline:

- **B4's "draw static pixels once per buffer, skip repaints" is impossible.** The dashboard rows
  (4–43) sit inside `[0, 0x3480)` — the region `blit_road_scroll`'s top-fill rewrites with the
  constant fill **every frame**, after which `draw_game_objects` writes ~3.4 KB into the same region
  (~1.1 KB inside the dashboard rows). The static pixels are destroyed before `draw_hud` runs; a
  per-buffer skip would never fire. Also corrected: the composed-frame differential composes into ONE
  persistent framebuffer (`test/equiv.py _ComposedScene`), so no existing pin alternates buffers —
  the "test_composed_frame alternates buffers" claim in the B4 proposal was inaccurate.
- **B5's "top-fill only changes when the horizon moves" is false.** The top-fill is a fixed-region
  constant fill of `[0, 0x3480)` with no horizon dependence, and it is the mechanism that makes
  `game_main.c`'s invariant hold ("repainting over two-frames-old content is byte-identical to over
  zeros") — it IS the deterministic background the masked object/HUD composites over that region rely
  on. Skipping it ghosts last-frame object pixels into the sky and corrupts the masked composites.
  The only conservative variant is B1-class per-byte object-footprint tracking, which saves ~0 on
  moving frames (B1's own verdict).

**What IS true and landed: the dashboard graphic is 100% opaque** (mask==0 for all 320 groups,
verified on all 5 legs' `mid_race_state`, the leg-drive fixtures, and on-target in Hatari). For an
opaque group `(bg & 0) | ink == ink` — background-independent — so `cell_dashboard` (include/plane.h,
shared by the HUD phase-7 blit and the results dashboard) gained a per-group `mask == 0` fast path
that skips the framebuffer read+AND and stores the ink directly; the RMW branch remains for any
transparent group. Provably byte-exact regardless of what scroll/objects wrote underneath.
**draw_hud 141,116 → 130,120 cyc (17.64 → 16.27 ms, −1.37 ms); gate TOTAL 1,015,686 → 1,004,690
(126.96 → 125.59 ms).** `make test` 706; goldens MATCH ×5; mutation check (perturb the opaque store)
fails 44 tests, restored green.

**Open option, not built (needs sign-off):** precompute the opaque dashboard into a pristine buffer
once per leg and long-`memcpy` it per frame — ceiling ~4 ms total off draw_hud (≈2.5 ms beyond the
landed fast path; the residual is unavoidable stores), at the cost of a `rm_hud_dashboard_prebuild`
API + per-leg invalidation signal (`buf_c + DASH_SRC_OFF` is the same pointer every leg with
different content). Judged borderline; recorded here so the trade is explicit.

**Plan-of-record impact:** with B2 NO-GO (road), B4-as-scoped and B5 NO-GO (this note), every
remaining Tier-B algorithmic item is measured dead. The pixel-faithful stock-ST frame now stands at
**gate 125.59 ms (~8.0 fps) / median proportionally better**, and the remaining levers are Tier-A
residue (A5 glyph movem fills ~2–3 ms, object-tree dispatcher/objsprite ABI, the ~4 ms HUD memcpy
option) and Tier-C departures (C1 25 fps vsync cadence, C4 STE blitter build).

### B4 follow-on LANDED — dashboard precompute+memcpy (−3.07 ms); A5 measured NO-GO in C. 2026-07-24

> **REVERTED 2026-07-25 (correctness).** The precompute+memcpy below rests on a FALSE premise: the
> dashboard is 100% opaque *only* for the leg-independent baked atlas the goldens/`make test`/autodrive
> stage. The LIVE per-leg mini-map `init_leg_dash` builds is TRANSPARENT (mask `0xffff` keeps the
> background), so the bulk-copy composited it over its background-less buffer and opaquely overwrote the
> road's sky — the in-race mini-map black-background bug (STATUS.md Known issues). Phase 7 is back to the
> on-the-fly masked blit (the original's behaviour); `dash_pristine` / `RM_HUD_DASH_PRISTINE_BYTES` /
> `dash_pristine_dirty` and the two tests cited below (`test_hud_dashboard_is_opaque`,
> `test_hud_dashboard_fallback_matches`) are removed, replaced by
> `test_hud_dashboard_transparent_composites_over_frame` (drives the real `init_leg_dash`). The ~3 ms is
> given back; the dashboard blit is a tiny fraction of the frame. The rest of this section is historical.

**Dashboard precompute+memcpy.** The phase-7 dashboard is 100% opaque (all 5 legs, pinned by the new
`test_hud_dashboard_is_opaque`), so its masked blit's output is background-independent: prebuild it
once per leg into a 6.25 KB `dash_pristine` (`RM_HUD_DASH_PRISTINE_BYTES` = 40 rows × 160 B, one
copy serves both screen buffers) by running the SAME verified `cell_dashboard` blit, then bulk-copy
64 B/row per frame. **draw_hud 130,120 → 105,556 cyc = 16.27 → 13.19 ms (0.77× recon); gate TOTAL
1,004,690 → 980,126 cyc = 125.59 → 122.52 ms.** The art carries a wrap-only progress marker
(`probe_collision` via the checkpoint rebuild), so the shell re-prebuilds on leg init + wrap via
`dash_pristine_dirty`; the composed differential mirrors the rule and **reddens (8 drives) if the
wrap rebuild is suppressed** — the invalidation is load-bearing and pinned. NULL pristine falls back
to the on-the-fly masked blit (kept + newly covered by `test_hud_dashboard_fallback_matches`).
`make test` 708; goldens MATCH ×5 (the on-target build runs the real prebuild + dirty path).

**A5 (glyph bulk-store) is a measured NO-GO in C.** `rm_glyph_run` = 52,986 cyc / 6.62 ms (40.7% of
draw_hud), but **0% of glyph/num rows are opaque** (per-row tally, all HUD phases, legs 0–2) — every
cell is a transparent masked overlay, so the solid/aligned `movem` premise never fires. The cost is
masked-RMW base+index addressing (~12k) + pack shuffles (~7k) under register pressure (45 stack refs).
Two C reshapes measured as washes (real-pointer displacement walk → 8 row-pointer spills;
`no-unroll-loops` → identical) — the objshift story again. **The ~2.5–3 ms is reachable only via a
hand-asm `rm_glyph_run` core** (ideal ~168 cyc/row vs 331 today; road_band.S pattern: frozen C ref +
per-core flag + Musashi differential + mutation).

### A5 hand-asm rm_glyph_run — MEASURED 0.86× (−0.95 ms), below the 1.5 ms bar; NOT landed. 2026-07-24

A whole-run m68k core (register-pinned fills d6/d7, displacement-addressed RMW, outer scan + inner
8-row blit in one call behind the movem prologue) was built and proven byte-exact to the C:
750 Musashi cases (random fonts/strings driving the terminator + LAST_HALF_GLYPH paths, every HUD
dst alignment, all fill combos, si offsets, budgets, end_dst NULL/non-NULL) + GUARD canary +
positive control + mutation (lsr #8→#7 fails 8 shards). Measured: glyph runs 52,986 → 45,394 cyc;
draw_hud 105,556 → 97,964 (13.19 → 12.25 ms); gate TOTAL 973,488 / 121.69 ms.

**Why only 0.86×: the "~168 cyc/row ideal" estimate ignored the 68000's shift-by-8.** The two-glyph
pack interleaves bytes (mask16 = [g1.hi:g2.hi], ink16 = [g1.lo:g2.lo]) and the 68000 has no
byte-permute — each repositioning is a 22-cyc lsr/lsl #8, 44 cyc/row irreducible, on top of the
~112-cyc masked 2-long RMW and a 24-cyc dup16. The asm removes the C's real waste (45 stack spills +
base+index, ~73 cyc/row) but the floor is ~258 cyc/row vs the C's 331. Every shift-avoidance route
(byte-read repositioning, long-deinterleave, rol, dup-then-pack) costs an equivalent shift-class op.
**A 2× glyph win is not reachable on this engine; the honest ceiling is ~0.9 ms.**

Per the pre-declared bar (<1.5 ms → report, don't force), the core was NOT landed — 0.95 ms does not
justify a standing .S core + differential suite + a 5-file dispatch refactor. The verified sources
are preserved in the session scratchpad (a5_glyph_asm_backup/) and this note records the register
design and the floor analysis for any future revisit.

**Perf campaign close-out (2026-07-24).** With this verdict every measured lever on the faithful
stock-ST build is resolved: object tree (A1/A2-reframed/A3/C-levers), render_road (A4 + full
hand-asm), HUD (opaque fast path + precompute/memcpy), scroll (pre-rotation, earlier), and the
measured NO-GOs (B2, B4-as-scoped, B5, A5-asm-below-bar, plus every dead end logged in the campaign
notes). **The faithful frame stands at gate 122.52 ms (~8.2 fps) — from 203 ms (4.9 fps) at the
campaign's start — with the original binary's own gate at 110 ms.** What remains is Tier-C
territory requiring sign-off: C1 (25 fps vsync-locked cadence — pixel-faithful, the honest
presentation), C4 (STE blitter build — byte-faithful, separate binary), C2/C3 (fidelity trades).

### C1 LANDED — vsync-locked presentation cadence (pixel-faithful). 2026-07-24

A free-running 50 Hz `vbl_count` (bumped at the top of the VBL sound pump, before its early-outs)
drives an even-vblank flip lock in `show_surface`: each present quantizes onto a fixed
`PRESENT_QUANTUM_VBLS = 2` grid, so consecutive frames land 2/4/6… vblanks apart (25/12.5/8.3 fps
steps) instead of free-running. Measured over a 249-present headless autodrive (Hatari,
emulated-time-exact): baseline jitters 5/6/7/8 vblanks per present (98/249 odd-span, 39%); locked
collapses to 6/8 (153×6 + 93×8; 2/249 odd = an instrument artifact — `present_target` is even by
construction). Mean 6.59 → 6.99 vblanks: the ~0.4-vblank cost of rounding heavy frames up to the
next even boundary (the lock only ever waits).

**Honesty notes:** at the 122.5 ms gate the real cadence is 6/8 vblanks — the deliverable is the
LOCK (regular pacing), not 25 fps compute; 2-vblank presents need <40 ms frames, which no faithful
stock-ST frame reaches. And tearing was NEVER present — Setscreen's base poke latches at the next
vblank on the shifter, before and after; C1's fix is pacing jitter, not tearing.
*(2026-07-26 consolidated measurement: the lock leaks ~2 % ODD spans while driving, always in
adjacent pairs — a `present_wait_boundary` race when a frame finishes exactly on the grid; the
grid re-phases on the next present, no pixel effect. "Always even" is not literally true. Also:
the trace build's tail canary costs ~7 ms/present, so locked-cadence numbers measured under
`GAME_CADENCE_TRACE` are taxed — a `-DGAME_NO_TAIL_CANARY` opt-out is the noted follow-up.)*

**Design:** the wait is the shell's plain `Vsync()` (services the VBL pump + IKBD while idling; no
busy-poll/halt needed — nothing to overlap). `vbl_count` is single-writer (VBL hook) /
single-reader (main line), one indivisible 68000 op each side — no lock. Liveness is fenced by
ordering (install_sound before the first show_surface; the exit path flips raw after uninstall) and
commented at the declaration. No game-logic skew: every game clock is a per-frame counter (bonus
time, TIME entry, crash timer) — nothing reads a vblank/wall clock, so presentation timing cannot
change what is computed. `GAME_PRESENT_FREERUN` compiles the lock out (the baseline-measurement
build); `GAME_CADENCE_TRACE=N` is the scratch cadence instrument (SCREEN.BIN dump, runner in the
session scratchpad). Shell-local: game_main.c only. Pixels: goldens MATCH ×5, `make test` 708,
flow trace unchanged at 19 records, psg_write signature confirms sound alive under the lock.
