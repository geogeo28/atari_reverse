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