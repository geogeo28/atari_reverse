# Docs — routed by expertise domain

Start with **[`00-overview.md`](00-overview.md)** for the end-to-end workflow. Then
jump to the domain you need. Each doc is standalone and grounded in the BuggyBoy
reference project, but written as general procedure for any Atari ST binary.

| Doc | Read it when you need to… | Expertise |
|-----|---------------------------|-----------|
| [00-overview](00-overview.md) | see the whole pipeline + "what is this file?" decision tree | lead / generalist |
| [binary-formats](binary-formats.md) | parse a `.PRG`/`.TOS`/`.TTP`, its header, symbols, relocations | binary formats |
| [packed-executables](packed-executables.md) | the entry is garbage / high-entropy — depack via Hatari before analyzing | packing / dynamic |
| [m68k-disassembly](m68k-disassembly.md) | read 68000 asm, run `prg_dis.py`, avoid sweep desync, spot jump tables | assembly |
| [ghidra-pipeline](ghidra-pipeline.md) | load into Ghidra correctly, run the headless pipeline, drive the naming loop | tooling |
| [ghidra-gui](ghidra-gui.md) | explore interactively in the GUI: decompiler, xrefs, spot-renaming, syncing to names.txt | tooling |
| [tos-os-calls](tos-os-calls.md) | identify GEMDOS/BIOS/XBIOS/GEM calls, basepage, loaders | OS internals |
| [hardware-map](hardware-map.md) | decode direct hardware access (video/sound/MFP/IKBD), interrupts, Line-A | hardware |
| [graphics](graphics.md) | decode bitmaps: planar format, palettes, RLE, extract sprites to PNG | graphics |
| [sound](sound.md) | find & read the YM2149 sound/music driver | audio |
| [methodology](methodology.md) | actually name functions/variables: anchors→outward, verify, iterate | RE methodology |

Cross-domain rule of thumb: **formats → disassembly/ghidra → OS+hardware (to anchor) →
graphics/sound (assets) → methodology (naming loop) all the way through.**