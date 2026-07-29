# remaster/ — a free, optimized re-implementation of BuggyBoy

`recreate/` proves *what the original does*, byte-for-byte. `remaster/` is where we build a
**clean, human-readable, optimized** BuggyBoy that is free to look nothing like the original 68000
asm — subject to one rule that keeps it honest.

## The contract

> For any given input, the remaster must produce a **pixel-identical framebuffer** to the verified
> `recreate/` cores, every frame.

That is the whole guardrail. Inside it we may:

- use **native C structs** for game state (no flat image, no Ghidra-address offsets, no `image`
  pointer threaded through every call);
- use **native types and endianness**, direct arrays, idiomatic control flow;
- pick **faster algorithms** — LUT/precomputed rotates, bulk copies, a precomputed road display
  list — the wins the perf analysis flagged (see `recreate/`'s `buggyboy-perf-fast-track` note).

What we may **not** do is change the visible output. An optimization that alters a single pixel
fails the equivalence harness. That is by design: it lets us rewrite aggressively without fear,
because `recreate/` (verified against the Musashi oracle) is the reference oracle for `remaster/`.

## Why the framebuffer is the comparison surface

`recreate/` and `remaster/` deliberately use *different* memory layouts, so we cannot byte-diff
their internal state. The one surface they share is the thing the player actually sees: the ST
low-res framebuffer.

```
   deterministic input (leg + per-frame joystick script + fixed seed)
                     │
        ┌────────────┴─────────────┐
        ▼                          ▼
  REFERENCE (recreate/.so)     CANDIDATE (remaster)
  verified cores, flat image   native structs
        │                          │
        ▼                          ▼
   32000-byte framebuffer      32000-byte framebuffer
        └──────────► diff ◄────────┘   green = pixel-identical
```

**Framebuffer format** (mirrors `recreate/render/render_screen.py`): 320×200, 4 bitplanes
interleaved word-by-word, 160-byte row stride, 32000 bytes total. Constants live in
`include/screen.h`.

## Two-phase migration — both phases complete

Each phase was gated by a green equivalence harness before the next began. Both are green: the game
is playable end-to-end and the 5-leg goldens MATCH on ST and STE. The design is kept here because it
explains why the code is split the way it is.

1. **Phase A — render equivalence from captured state.**
   Capture real mid-race state snapshots from `recreate/` (reusing `recreate/tools/bench_frame.py`'s
   staging), translate each into remaster structs via a test-only **adapter**, run the remaster
   render pipeline, and diff its framebuffer against `recreate/`'s render of the same snapshot. This
   isolates *rendering* (the perf target) from gameplay.

2. **Phase B — gameplay equivalence.**
   Port `game_update` to native structs; drive both sides from the same per-frame input script; the
   framebuffer diff then covers the whole loop and the remaster is self-driving. The per-stage diffs
   verify each renderer in isolation with inputs staged from the reference; the **composed-frame
   differential** (`test/test_composed_frame.py`) closes the gap BETWEEN them — on sampled drive frames
   the candidate runs the shell's OWN whole-frame composition (the `apply_player`/`gobj_hud_view`
   fan-outs → `rm_draw_frame`, from its live owned state) and byte-compares it to recreate's
   `g_draw_frame`, so a missing wire between two individually-verified stages fails a drive.

The **adapter** (native structs ↔ flat `recreate` image) is test-only scaffolding — the bridge that
makes differential validation possible across the two layouts. It never ships in the game build.

## Layout

```
include/   14 headers: screen.h (framebuffer format)  game.h (native state structs — the whole owned state)
           blitter.h (the STE hardware-blitter seam)  sound.h  flow.h  text.h  assets.h  st.h, plus the
           per-subsystem constant tables (blit_const.h, road_const.h, scroll_const.h, dash_const.h, …)
src/       30 .c files, one per subsystem — render (road.c, ground.c, object.c, object_list.c, sprite.c,
           scroll.c, geometry.c, blit.c, hud.c, text.c), gameplay (player.c, gameplay.c, events.c, course.c,
           frame.c, flow.c, intermission.c, results.c), assets.c and sound.c/sound_trig.c. There is no
           main.c — the on-target shell lives in render/atari/game_main.c. Nine blitter*.c are the STE
           target-only route + its measurement builds (never in the host .so; see BLIT_STE_SPEC.md)
src/asm/   hand-written m68k cores for the hottest render leaves (objshift2.S, objshift.S, road_band.S); the C
           in src/*.c stays the byte-exact reference, and a per-core flag (game.h RM_ASM_* + the RM_BLIT_*
           dispatch macro) picks asm on the m68k builds / C on the host — see render/atari/README.md and PERF30.md A3
test/      the differential harness: capture_ref.py (golden state/framebuffers from recreate)  equiv.py
           (candidate vs reference)  adapter.py (flat recreate image ↔ remaster structs)  assets_load.py,
           plus 32 test_*.py — one per subsystem, each driving recreate and remaster from the same inputs
render/atari/  on-target build: BUGGYBOY.PRG (the playable game — leg select, race, flow, sound)
           + the frame-0 golden harness (run_golden.py) and the Hatari measurement runners
           (run_cadence.py, run_ste_*.py) — see render/atari/README.md
tools/     bench.py (cycles vs original + vs recreate, extends recreate/tools/bench_frame.py)
Makefile   build the host lib + run equivalence tests + bench
STATUS.md  per-subsystem progress vs recreate
PORTING.md how to continue the port — recipe, conventions, gotchas (read this to pick up the work)
```

## Measured performance & memory (2026-07-26, HEAD = C5 slice 2)

The canonical current-state tables — one build (`BUGGYBOY.PRG`, byte-identical on both machines),
one instrument per table (labeled), one protocol (leg 0; gate = 200 idle frames at the leg-start
gate, the object-dense worst case; drive = 250 autodrive frames; Hatari + EmuTOS 1024k). Cadence
measured by `render/atari/run_cadence.py`; raw runs in `PERF30.md`'s C4 slice-10 / C5 slice-1/2
notes and `BLIT_STE_SPEC.md` §15-§17.

### The final picture — ORIGINAL → remaster ST → remaster STE

One row per question people actually ask. Two instruments, never mixed within a column pair:
Musashi = cycle-exact 68000 counts on the identical staged frame (the only instrument the original
can run under); render clock = the 200 Hz sub-vblank clock around `draw_frame` under Hatari.

| | ORIGINAL (ST or STE) | remaster on ST | remaster on STE |
|---|---:|---:|---:|
| worst-case frame (gate), Musashi | **110.05 ms** (9.1 fps) | **123.83 ms** (8.1 fps) = **1.13×** | **≈92.9 ms** (≈10.8 fps) = **≈0.84× ³** |
| worst-case frame (gate), render clock | — (no instrument in the binary) | 130.30 ms | **97.75 ms** |
| driving, render clock | — ⁶ | 99.78 ms | **89.80 ms** |
| memory: resident bytes | **437,248** (427 KB) | **709,076** (693 KB) | **879,508** (859 KB, tables placed) |
| minimum machine | 512 KB (recovered design target) | **1 MB** | **1 MB** (blitter routes live) |

Bottom line: on a plain ST the hand-written original keeps an **11–13 %** edge on the worst frame;
on an STE the remaster is — by the labeled estimate — **~16 % faster than the original runs
anywhere**, at byte-identical pixels. The original never touches the blitter (verified: zero
`$FFFF8Axx` references in the binary), so its number is the baseline on ST **and** STE.

⁶ The original's mid-race median is **82.8 ms** under Musashi; the remaster's driving cells were
never measured on that instrument (and 99.78/89.80 are render-clock numbers), so the driving row
has no honest original-vs-remaster pair — flagged rather than guessed.

### Frame time (render clock = compute; present cadence = player-visible latency)

Presentation is **free-running** by default, exactly as the original does it (`flip_screen` @0x121f8:
poke the video base, one Vsync). The C1 even-vblank lock is opt-in (`-DGAME_PRESENT_LOCK`) — the
cadence column below is the LOCKED one it was measured under; free-running is the same render with the
round-up removed, so it is never slower and usually a vblank quicker.

| machine | scene | render ms/frame | render fps | C1-LOCKED present cadence | live engines |
|---|---|---:|---:|---|---|
| ST | gate (worst case) | **130.30** | 7.68 | 8 vbl → 160 ms → **6.25 fps** ¹ | 68000 hand-asm |
| ST | driving | **99.78** | 10.02 | mostly 6/8 vbl, mean ≈7.6 → **≈6.5 fps** | 68000 hand-asm |
| STE | gate (worst case) | **97.75** | 10.23 | 8 vbl → 160 ms → **6.25 fps** | blitter (objshift2 + colour skew table + road scroll + HUD dashboard) |
| STE | driving | **89.80** | 11.14 | mostly 6/8 vbl, mean ≈7.1 → **≈7.0 fps** | blitter, 90 % colour-table hits |

Free-running vs locked, measured on the same scene (`run_cadence.py ste 200` with and without `--lock`,
STE driving): median **7 vs 8** vblanks/present, mean **6.94 vs 7.36** — the lock was rounding 83 of 199
presents that finished in 7 vblanks up to 8. The gap widens on a faster machine, because a shorter render
lands lower on the grid and the round-up costs proportionally more.

STE vs ST: **gate −25.0 %, driving −10.0 %** — same pixels, byte-identical framebuffers on both
machines (goldens ×5 each + whole-frame A/B pin it). RAM size has **zero** effect on speed: the
1 MB cells return bit-identical tick totals and route counters to the 4 MB cells.

*Cells are same-session before/after pairs (the Hatari model is deterministic within a session,
drifts across sessions): C4 close 105.47/97.34 → slice 1 (road scroll) 99.25/90.72 → slice 2 (HUD
dashboard) 97.75/89.80. Instrument caveat: the render clock counts whole 5 ms ticks per frame, so a
sub-tick change re-phases frames across tick boundaries and sums to ±N ticks over a run — treat
sub-0.5 ms moves in the driving cells as instrument phase, not cost (the +0.38 ms ST-driving wobble
at slice 2 is exactly this: the Musashi bench shows `draw_frame` unchanged to the cycle).*

### Latency per stage (Musashi cycle counts, staged gate frame, 8 MHz)

Original and remaster measured at HEAD on the identical staged leg-0 gate frame — the original via
its own 68000 code under the oracle, the remaster via the cross-compiled bench build. The
`original` and `remaster (68000)` columns are the same instrument and directly comparable; the
68000 column is also what a plain ST ships. The STE columns say which engine the boot bind selects
there and what that route measurably removed from the whole frame when it landed (same-session
render-clock deltas at the gate — per-stage Musashi numbers do not exist for the blitter, so these
are attributions, not a third same-instrument column).

| stage (gate frame) | original | remaster (68000) | ratio | on the STE: engine | measured Δ gate |
|---|---:|---:|---:|---|---:|
| build_road_geometry | 2.42 ms | 3.90 ms | 1.61× | 68000 (same C) | — |
| render_road | 26.19 ms | 28.85 ms | 1.10× | 68000 (same hand-asm) | — |
| blit_road_scroll | 11.80 ms | 11.91 ms | 1.01× | **blitter** (C5 slice 1) | **−6.2 ms** |
| object tree | 57.34 ms | 62.93 ms | 1.10× | **blitter** (objshift2 + colour skew table, C4) | **−24.8 ms** |
| draw_hud | 12.29 ms ⁵ | 16.27 ms ⁵ | 1.32× ² | **blitter** dashboard composite (C5 slice 2), rest 68000 | **−1.5 ms** |
| **TOTAL draw_frame** | **110.05 ms** (9.09 fps) | **123.83 ms** (8.08 fps) | **1.125×** | render clock 130.30 → **97.75 ms** | **−32.5 ms** |
| mid-race median | 82.8 ms (12.1 fps) | — (never measured on this instrument) | | | |
| **remaster on STE (estimate ³)** | 110.05 ms | **≈92.9 ms** (≈10.8 fps) | **≈0.84×** | | |

The Δ column sums to the whole measured ST-vs-STE render-clock gap at the gate (130.30 − 97.75 =
32.5 ms), because each route landed alone with a same-session before/after pair: the object routes
measured −25.0 at C4 close (130.50 → 105.47, shown as the −24.8 residual after the ST baseline
itself gained 0.2 ms from slice 1's `copy_run` rewrite), road scroll −6.2 (C5 slice 1), dashboard
−1.5 (C5 slice 2). Driving deltas are smaller (object ≈−2.1, scroll −6.6, dashboard −0.9 — the gate
is the object-dense worst case).

² draw_hud includes the dashboard memcpy revert (the live mini-map is transparent; the bulk copy
was overwriting the sky — pixel correctness beat the 3 ms, see PERF30's dash_pristine note).
⁵ **Both draw_hud cells are measured on the BAKED atlas, not on live art.** The staged bench frame
carries the leg-independent dashboard atlas, which is 100 % opaque, so `cell_dashboard`'s `mask == 0`
fast path takes every group. Driving a real leg, `init_leg_dash` replaces it with a TRANSPARENT per-leg
mini-map: the same blit then costs 67,978 cyc / 8.50 ms instead of 5.70, and real in-race `draw_hud` is
**19.06 ms**, not 16.27 (the fast path fires on 1–9 of 320 groups). The remaster's 16.27 and the
original's 12.29 are same-instrument on the same staged frame, so the 1.32× ratio stands; what is NOT
determinable from the binary is whether 12.29 would move the same way on live art — the original runs
the identical masked-blit algorithm with no fast path, so it plausibly moves less. Flagged rather than
guessed.
³ Estimate: the Musashi ST figure scaled by the same-build Hatari render-clock ratio
(97.75 / 130.30 = 0.750) — the ratio is same-instrument, the absolute STE ms is not a measurement.

¹ The locked-cadence instrument (`GAME_CADENCE_TRACE`) pays a ~7 ms/present tail-canary tax the
shipping PRG does not; the taxed ST gate frame quantises to 10 vbl in the trace build, but the
slice-9 no-canary measurement at the same render clock showed 8 vbl — 8 is the shipping figure.
The C1 even-vblank lock also leaks ~2 % odd spans in adjacent pairs (a boundary race, no pixel
effect). All timing is the Hatari model, not cycle-exact hardware; comparisons are same-instrument
and fully deterministic (repeat runs are bit-identical).

### Memory (total resident, TOS excluded)

| configuration | bytes | ≈ | notes |
|---|---:|---|---|
| **ORIGINAL** (reference) | **437,248** TPA held | 427 KB | 48,632 program (text carries all globals + the stack; data=0 bss=0) + one 388,616 B Malloc — read from the binary's own `main`; **469,248 B incl. the TOS-owned second screen** |
| **remaster, ST (any RAM)** | **709,076** | 693 KB | basepage 256 + text 123,392 + BSS 585,428; blitter tables never placed |
| **remaster, STE** | **879,508** | 859 KB | + 170,432 B of blitter tables placed into free TPA at boot (alignment pad 0) |
| 1 MB usable TPA (EmuTOS) | 905,440 | 884 KB | so: 1 MB ST fits with **196,364 B** spare |
| 1 MB STE margin after tables + 16 KB stack margin | **9,548** | 9.3 KB | **watch item** — text/BSS growth beyond this silently drops a 1 MB STE's OBJECT routes to the (pixel-identical, slower) CPU engines; the two TABLE-LESS routes (road scroll, HUD dashboard) stay on the chip. The cadence `free TPA bytes` counter is the gauge. C5 slice 1 spent 1,056 B of it (10,620 → 9,564) and slice 2 a further 16 B (→ 9,548) |

Static BSS breakdown: arena 388,616 (exactly the original's Malloc size — it models the same work
block) · scroll prebuild 106,496 · screen pool 72,448 (2 × 32,000 screens + 2 × 4,096
measured-overdraw tails + alignment) · buf_a 15,520 · the rest ≈ 2.3 KB.

**Minimum machine: the remaster needs 1 MB (ST and STE alike). The ORIGINAL's recovered design
target was a 512 KB ST** — its 427 KB TPA hold fits one tightly, and `START.PRG` hard-codes a
scratch address (`0x77000`) that is exactly the highest safe spot on a 512 KB machine
(medium-high confidence; nothing in either binary gates on RAM size). The remaster's extra
~270 KB buys the perf structures the original didn't have: the pre-rotated scroll copies
(104 KB), the compiled C text (123 vs 48 KB), the double-buffered screens with measured tails,
and the mutable course copy.

## Relationship to `recreate/`

`remaster/` **depends on** `recreate/` at test time only: it drives `recreate/build/libbuggyboy.so`
(via the same `oracle/`/`harness.py` machinery) to generate the golden framebuffers. Build
`recreate/` first (`cd ../recreate && make`) so the reference `.so` exists. The shipped remaster
game shares none of `recreate/`'s code.
