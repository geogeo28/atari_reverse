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
   framebuffer diff then covers the whole loop and the remaster is self-driving.

The **adapter** (native structs ↔ flat `recreate` image) is test-only scaffolding — the bridge that
makes differential validation possible across the two layouts. It never ships in the game build.

## Layout

```
include/   screen.h (framebuffer format)   game.h (native state structs — grows per subsystem)
src/       main.c + one file per subsystem (road.c, objects.c, hud.c, score.c, game_update.c, …)
test/      capture_ref.py (golden framebuffers from recreate)  equiv.py (candidate vs reference)
           adapter.*  (flat image → remaster structs)   inputs/ (deterministic per-frame scripts)
tools/     bench.py (cycles vs original + vs recreate, extends recreate/tools/bench_frame.py)
Makefile   build the host lib + run equivalence tests + bench
STATUS.md  per-subsystem progress vs recreate
```

## Relationship to `recreate/`

`remaster/` **depends on** `recreate/` at test time only: it drives `recreate/build/libbuggyboy.so`
(via the same `oracle/`/`harness.py` machinery) to generate the golden framebuffers. Build
`recreate/` first (`cd ../recreate && make`) so the reference `.so` exists. The shipped remaster
game shares none of `recreate/`'s code.
