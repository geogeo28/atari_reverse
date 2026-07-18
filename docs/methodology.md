# Methodology — naming functions & variables

This is where the real work is. The mechanics (load, decompile, apply names) are cheap;
turning `FUN_0001110e` into `game_update` with named state is the craft. The tools are in
`ghidra-pipeline.md`; this doc is *how to think*.

## Golden rule: anchors → outward

You never read a 48 KB binary top-to-bottom. You anchor on **ground truth** and propagate
along the call graph. Sources of ground truth, strongest first:

1. **OS traps** (annotated already) — "this function `Fopen`s a file / sets the palette."
2. **Hardware register access** — `$ffff8240` = palette, `$ffff8800` = sound,
   `$ffff8200` = video base, `$fffffc00` = keyboard. Unambiguous. → `hardware-map.md`.
3. **Imported symbols** — any DRI symbols name whole subsystems for free.
4. **Strings** — filenames loaded, menu text, author credit, score labels. They pin down
   loaders, menus, HUD, and high-score code.
5. **Interrupt installs** — whoever writes `0x456` (VBL) / MFP vectors owns the tick.
6. **Call graph** — name leaf utilities first (a `dbf` copy loop = `memcpy`; a masked
   blit = `draw_sprite`), then the callers that compose them.

## Verify before you name (this bit me repeatedly)

Position and size are hints, **not** evidence. In BuggyBoy: a function I assumed was
`read_input` was actually `flip_screen` (it wrote the video base); one I called
`show_message` was actually `add_score` (BCD score with carries). **Read the decompiled
body and confirm what it touches** before committing a name. Wrong sticky names are worse
than `FUN_`.

## Naming variables

Name a global by how it's *used*, across functions:
- incremented every VBL → `frame_ctr`; counts down to 0 then triggers → `timer`.
- ANDed with joystick bits / compared to key scancodes → `input_state`.
- written to `$ffff8240` region → a palette buffer; toggled 0/N and used to pick a screen
  base → `flip_idx`.
- BCD digits `0x30..0x39` assembled for display → a score/time string.

## Jump tables → many names at once

Decode an offset table to reveal a whole family of handlers (and, for course/level
scripts, the *data format* that indexes it):

```python
import struct
d = open("bin/GAME.PRG","rb").read(); HDR = 28
base_img = 0x<table_image_off>            # Ghidra addr - load_base
for i in range(N):
    off = struct.unpack(">h", d[HDR+base_img+2*i : HDR+base_img+2*i+2])[0]
    print(i, hex(0x10000 + base_img + off))   # handler address (Ghidra)
```
Then read each target and name it (`evt_collision`, `evt_flag_gate`, …). Where handlers
are jump-only stubs (never `call`ed), `ApplyNames` disassembles + creates them.

## The loop, and honesty

Read `decomp.c` → name what you can confirm → `reapply.sh` → re-read (now more of the
program is legible, unlocking the next layer). Repeat until coverage is high. When you
name a leaf helper from **call-context** rather than a full read, tag it with a trailing
`# ctx` in `names.txt` (category-true names like `draw_hud_*`/`snd_*` are fine, but mark
them refinable rather than presenting a guess as fact). Untagged = verified from the body.
If you explore/rename in the GUI, fold those edits back with `dump_names.sh` so `names.txt`
stays the source of truth.

## What "done" looks like

`main` and the frame loop read as pseudocode; every function has a meaningful name; the
key globals (state, buffers, tables) are labelled; jump tables and asset formats are
documented. See `projects/buggyboy/README.md` for a finished example (91/91 functions).

## "Verified" ≠ "complete": the checkpoint trap (this bit us on sound)

A green differential test proves *our code ≡ the original, up to where the oracle can run it*.
It says **nothing** about behaviour past that point. Interactive functions that never return under
the oracle (they wait on the IKBD / a `mzflag` spin / Vsync) are verified only to a **checkpoint**
PC — the deterministic prefix runs, the tail is read-verified. That is fine, *as long as you track
what the checkpoint hides*.

We didn't, once. `update_highscore` was checkpoint-verified at `0x12450`/`0x123e6` — one instruction
*before* its `play_event_tune` calls. The prefix stub returned there and `game_main.c` called it and
moved on, so the game-over jingle and the name-entry jingle were never reconstructed and never
reachable in the playable build. Three tune triggers sat on the far side of a "91/91 verified" line.
The suite stayed 100% green the whole time the game was silent; it took running on hardware and a
human ear to notice (see [`on-target-execution.md`](on-target-execution.md) — same blind spot, applied
to a *missing feature* rather than perf).

Lessons, now guardrails:

- **A checkpoint is a suspicious boundary — ask what's on the other side.** If the deferred tail
  contains sound / palette / trap / I/O pokes, the harness cannot see them *and* they may be silently
  absent from the PRG. Note it explicitly in `STATUS.md`, don't let "read-only tail" read as "done".
- **Audit call-graph coverage, not just per-function correctness.** Grep the disassembly for every
  `play_event_tune` / `INITTUNE` / `INITFX` (and each trap / palette poke) call site and confirm each
  is both reconstructed *and* reachable in the playable build — or logged as intentionally omitted.
  That one grep would have caught the silent tunes immediately.
- **Don't let the headline count flatten the distinction.** "N/N verified" should still say which are
  checkpoint/piecewise-verified; a deferred tail is a *known gap*, not a finished function.
- **The playable build is its own verification surface.** A cheap on-target smoke check ("does every
  subsystem produce output — sound triggers, palette, input?"), e.g. a PSG-write / border-colour probe,
  catches this class of gap that the differential suite is structurally blind to.