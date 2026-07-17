# 00 — Overview & Workflow

## The end-to-end pipeline

```
.PRG binary
  │  parse header/symbols/relocs               → docs/binary-formats.md
  ▼
raw import into Ghidra (68000:BE:32)
  │  PrgLoader: rebuild TEXT at base, apply     → docs/ghidra-pipeline.md
  │  relocations, import symbols, set entry
  ▼
auto-analysis + trap annotation                → docs/tos-os-calls.md
  │  ExportDecompC → decomp.c
  ▼
NAMING LOOP  (the bulk of the work)             → docs/methodology.md
  read decomp.c → anchor on traps/hardware/     → docs/hardware-map.md
  strings/symbols → name fn/var → reapply → repeat
  ▼
assets on the side: graphics, sound             → docs/graphics.md, docs/sound.md
  ▼
(optional) RECONSTRUCT + PROVE                   → docs/agent-playbook.md §3–5
  turn the named asm into clean C and verify it
  byte-for-byte against an emulator oracle
```

For the operating practices that make all of this fast — anchoring, verifying by execution,
attack order, and the tight edit→verify loop — read **[`agent-playbook.md`](agent-playbook.md)**.

Concretely, per project:

```bash
bash tools/new_project.sh mygame path/to/MYGAME.PRG
bash projects/mygame/run.sh          # bootstrap: analyzed DB + decomp.c
# … read decomp.c, add lines to names.txt …
bash projects/mygame/reapply.sh      # apply + re-export; repeat
```

## "What is this file?" decision tree

- Bytes start with **`60 1A`** → a **GEMDOS executable** (`.PRG`/`.TOS`/`.TTP`,
  or a data file that embeds one). Parse the 28-byte header. → `binary-formats.md`
- Starts with **`60 1A`** but is tiny and references another filename / does
  `Fopen`/`Fread`/`Pexec` → a **loader/launcher**; the real game is the file it loads.
  (BuggyBoy's `START.PRG` is exactly this.)
- Starts with **`60 1A`** but the first-pass disassembly at the entry is garbage and the
  **text entropy is > ~6.7** (`prg_dis.py` prints it) → a **packed/crunched executable**;
  depack it before analyzing. (Joust's `JOUSTS.CTE`.) → `packed-executables.md`
- No `60 1A`, highly structured, lots of `0x0000`/`0xffff` runs → **compressed or
  bitmap data** (course/graphics data). → `graphics.md`
- ST palette words (`0x0RGB`, nibbles small), 16 in a row → a **palette table**. → `graphics.md`

## Two truths that shape everything

1. **The relocation table is gold.** Honor it on load and every absolute pointer
   (`lea $xxxx.l`, jump tables) resolves to a real, navigable address — this is what
   makes Ghidra's auto-analysis discover functions. Never load a `.PRG` as a flat blob.
2. **Games bypass the OS.** Expect file I/O via GEMDOS and *everything else* via
   direct hardware / Line-A / XBIOS. GUI (GEM AES/VDI) usually appears only in init.

## Effort model

Small helper (fill/blit/wrapper): name in seconds from its body. The two big wins are
(a) `main` + the frame loop (gives the whole architecture) and (b) the OS-trap +
hardware anchors (give ground truth to propagate from). Budget most time on the
naming loop, not the mechanics.