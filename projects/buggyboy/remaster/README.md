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

## Two-phase migration

Each phase is gated by a green equivalence harness before the next begins.

1. **Phase A — render equivalence from captured state** *(current focus).*
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
include/   screen.h (framebuffer format)   game.h (native state structs — grows per subsystem)
           blit_const.h (fine-x blit constants shared by src/blit.c and the asm cores)
src/       main.c + one file per subsystem (road.c, objects.c, hud.c, score.c, game_update.c, …)
src/asm/   hand-written m68k cores for the hottest render leaves (objshift2.S, objshift.S); the C in src/*.c stays
           the byte-exact reference, and a per-core flag (game.h RM_ASM_* + the RM_BLIT_* dispatch macro)
           picks asm on the m68k builds / C on the host — see render/atari/README.md and PERF30.md A3
test/      capture_ref.py (golden framebuffers from recreate)  equiv.py (candidate vs reference)
           adapter.*  (flat image → remaster structs)   inputs/ (deterministic per-frame scripts)
render/atari/  on-target build: BUGGYBOY.PRG (the playable game — leg select, race, flow, sound)
           + the frame-0 golden harness (run_golden.py) — see render/atari/README.md
tools/     bench.py (cycles vs original + vs recreate, extends recreate/tools/bench_frame.py)
Makefile   build the host lib + run equivalence tests + bench
STATUS.md  per-subsystem progress vs recreate
PORTING.md how to continue the port — recipe, conventions, gotchas (read this to pick up the work)
```

## Measured performance & memory (2026-07-26; STE re-measured at C5 slice 1, ST/original at 6ac3066)

The canonical current-state tables — one build (`BUGGYBOY.PRG`, byte-identical on both machines),
one instrument (the 200 Hz sub-vblank render clock around `draw_frame`), one protocol (leg 0;
gate = 200 idle frames at the leg-start gate, the object-dense worst case; drive = 250 autodrive
frames; Hatari + EmuTOS 1024k). Measured by `render/atari/run_cadence.py`; raw runs in
`PERF30.md`'s C4 slice-10 / C5 slice-1 notes and `BLIT_STE_SPEC.md` §15-§16.

### Frame time (render clock = compute; locked cadence = player-visible latency)

| machine | scene | render ms/frame | render fps | locked present cadence | live engines |
|---|---|---:|---:|---|---|
| ST | gate (worst case) | **130.30** | 7.68 | 8 vbl → 160 ms → **6.25 fps** ¹ | 68000 hand-asm |
| ST | driving | **99.40** | 10.06 | mostly 6/8 vbl, mean ≈7.6 → **≈6.5 fps** | 68000 hand-asm |
| STE | gate (worst case) | **99.25** | 10.08 | 8 vbl → 160 ms → **6.25 fps** | blitter (objshift2 + colour skew table + road scroll) |
| STE | driving | **90.72** | 11.02 | mostly 6/8 vbl, mean ≈7.1 → **≈7.0 fps** | blitter, 90 % colour-table hits |

STE vs ST: **gate −23.8 %, driving −8.7 %** — same pixels, byte-identical framebuffers on both
machines (goldens ×5 each + whole-frame A/B pin it). RAM size has **zero** effect on speed: the
1 MB cells return bit-identical tick totals and route counters to the 4 MB cells.

*Moved at C5 slice 1 (`BLIT_STE_SPEC.md` §16): the road fine-scroll now runs on the blitter, taking the
STE cells from 105.47 / 97.34 to 99.25 / 90.72 ms. The ST cells moved 130.45 → 130.30 and 99.88 → 99.40
in the same change — the C reference's `copy_run` was rewritten as a post-increment pointer walk, worth
1,254 cyc/frame. (Both ST cells re-measured here; the 130.50 / 99.42 published at 6ac3066 were 130.45 /
99.88 when re-run in this session's Hatari — within the model's run-to-run spread, which is why the
before/after pairs above are same-session.)*

### vs the ORIGINAL binary (same instrument: Musashi cycle counts, staged gate frame, 8 MHz)

Both sides re-measured at HEAD on the identical staged leg-0 gate frame — the original via its own
68000 code under the oracle, the remaster via the cross-compiled bench build. The original never
touches the blitter (verified: zero `$FFFF8Axx` references in the binary), so its number is the
baseline on ST **and** STE.

| stage (gate frame) | original | remaster | ratio |
|---|---:|---:|---:|
| build_road_geometry | 2.42 ms | 3.90 ms | 1.61× |
| render_road | 26.19 ms | 28.85 ms | 1.10× |
| blit_road_scroll | 11.80 ms | 11.91 ms | 1.01× ⁴ |
| object tree | 57.34 ms | 62.93 ms | 1.10× |
| draw_hud | 12.29 ms | 16.27 ms | 1.32× ² |
| **TOTAL draw_frame** | **110.05 ms** (9.09 fps) | **123.83 ms** (8.08 fps) | **1.125×** |
| mid-race median | 82.8 ms (12.1 fps) | — (never measured on this instrument) | |
| **remaster on STE (estimate ³)** | 110.05 ms | **≈94.3 ms** (≈10.6 fps) | **≈0.86×** |

On a plain ST the hand-written original keeps an **11–13 %** edge on the worst frame; on an STE the
remaster's blitter path makes it — by the labeled estimate — **~14 % faster than the original runs
anywhere**: the first configuration where the port beats the original, at byte-identical pixels.

² draw_hud includes the dashboard memcpy revert (the live mini-map is transparent; the bulk copy
was overwriting the sky — pixel correctness beat the 3 ms, see PERF30's dash_pristine note).
³ Estimate: the Musashi ST figure scaled by the same-build Hatari render-clock ratio
(99.25 / 130.30 = 0.762) — the ratio is same-instrument, the absolute STE ms is not a measurement.
⁴ On an STE the same stage runs on the blitter instead, at ≈5.8 ms — this row is the CPU path both
machines' 68000 reference shares (and the only path a plain ST has).

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
| **remaster, ST (any RAM)** | **709,060** | 693 KB | basepage 256 + text 123,392 + BSS 585,412; blitter tables never placed |
| **remaster, STE** | **879,492** | 859 KB | + 170,432 B of blitter tables placed into free TPA at boot (alignment pad 0) |
| 1 MB usable TPA (EmuTOS) | 905,440 | 884 KB | so: 1 MB ST fits with **196,380 B** spare |
| 1 MB STE margin after tables + 16 KB stack margin | **9,564** | 9.3 KB | **watch item** — text/BSS growth beyond this silently drops a 1 MB STE's OBJECT routes to the (pixel-identical, slower) CPU engines; the road-scroll route has no table and stays on the chip. The cadence `free TPA bytes` counter is the gauge. C5 slice 1 spent 1,056 B of it (10,620 → 9,564) |

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
