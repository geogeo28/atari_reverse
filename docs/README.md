# Docs — routed by expertise domain

Start with **[`00-overview.md`](00-overview.md)** for the end-to-end workflow, then read
**[`agent-playbook.md`](agent-playbook.md)** for how to work fast and prove it. After that,
jump to the domain you need. Each doc is standalone and grounded in this workspace's worked
projects — BuggyBoy is the reference reconstruction, Joust, Wonder Boy and Zynaps followed it, and
BLACK ICE contributes STE hardware knowledge as an *original* program rather than a reconstruction —
but every doc is written as general procedure for any Atari ST binary.

| Doc | Read it when you need to… | Expertise |
|-----|---------------------------|-----------|
| [agent-playbook](agent-playbook.md) | **go fast and prove it** — the meta-practices + the differential reconstruction/verification loop that ties the rest together, plus how a gate fails quietly, **the setup contract a multi-agent wave needs before it launches**, and how to run and merge one | lead / methodology |
| [00-overview](00-overview.md) | see the whole pipeline + "what is this file?" decision tree | lead / generalist |
| [binary-formats](binary-formats.md) | parse a `.PRG`/`.TOS`/`.TTP`, its header, symbols, relocations; read a disk image (`st_extract.py`, `stx_extract.py`); decode a game's own resource container (`depack_rad.py`); **write one back** — a `.PRG` from the reconstruction, and a bootable FAT12 `.ST` a real machine mounts (`st_build.py`) | binary formats |
| [packed-executables](packed-executables.md) | the entry is garbage / high-entropy — depack via Hatari, or statically with `depack_gamex.py` / `depack_lsd.py` | packing / dynamic |
| [m68k-disassembly](m68k-disassembly.md) | read 68000 asm, run `prg_dis.py`, avoid sweep desync, spot jump tables | assembly |
| [ghidra-pipeline](ghidra-pipeline.md) | load into Ghidra correctly, run the headless pipeline, drive the naming loop | tooling |
| [ghidra-gui](ghidra-gui.md) | explore interactively in the GUI: decompiler, xrefs, spot-renaming, syncing to names.txt | tooling |
| [tos-os-calls](tos-os-calls.md) | identify GEMDOS/BIOS/XBIOS/GEM calls **and Line-A `$aXXX`**, basepage, loaders; **ask which machine you are on** (the cookie jar) and what `Setscreen` does besides what you called it for | OS internals |
| [hardware-map](hardware-map.md) | decode direct hardware access (video/sound/MFP/IKBD, the STE sound block), interrupts and the VBL queue | hardware |
| [graphics](graphics.md) | decode bitmaps: planar format (the shared pixel model in `st_pixels.py` — word/byte granularity, masked sprites), palettes, RLE, extract sprites to PNG | graphics |
| [sound](sound.md) | find & read the YM2149 sound/music driver; route the STE's LMC1992 mixer so the music is audible at all | audio |
| [on-target-execution](on-target-execution.md) | **run the verified reconstruction on real hardware** — the seam pattern, the thirteen-class bug taxonomy the harness cannot see, the six observable surfaces and the diagnostic toolkit, closing a speed gap, and changing the program on purpose without losing the verification. Long; it opens with its own contents list | on-target / perf |
| [methodology](methodology.md) | actually name functions/variables: anchors→outward, verify, iterate — and, once it's named, the **dead-code hunt** | RE methodology |

Cross-domain rule of thumb: **formats → disassembly/ghidra → OS+hardware (to anchor) →
graphics/sound (assets) → methodology (naming loop) all the way through.**

One body of transferable knowledge lives outside this directory because it is the shared harness's
own contract: [`../tools/recreate_kit/TRAP_MODEL.md`](../tools/recreate_kit/TRAP_MODEL.md) — what the
oracle models of TOS and the hardware and what it deliberately refuses, the seeded read models, the
scheduled-write and hardware-write ledgers, and the callback door an asm twin calls a verified core
through. `agent-playbook` and `on-target-execution` both send you there.