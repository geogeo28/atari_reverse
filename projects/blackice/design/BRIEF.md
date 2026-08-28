# BRIEF — an original Wolfenstein-3D-style game for the STOCK Atari STE

Read fully before doing anything. This is the single source of truth for constraints.

## Target machine (non-negotiable)
- Atari STE, **stock**: 68000 @ 8 MHz, 1 MB RAM (design to fit in 1 MB with margin; 512 KB is NOT a target),
  blitter, DMA sound ($ffff8900+), 4096-colour palette (4 bits/channel, STE colour word format $0RGB with
  the STE bit swizzle: each nibble's low bit is the MSB — write helpers, don't hand-encode),
  hardware scroll registers, enhanced joystick ports ($ffff9200). PAL 50 Hz VBL.
- Screen: 320x200, 4 bitplanes interleaved (16 px = 4 words), 160 bytes/line, 32,000 bytes/screen, 16 colours on screen.
- Budget: **160,000 CPU cycles per 50 Hz frame**. The blitter is on the same 8 MHz bus — it is not a GPU.
- No chunky pixel mode: a raycaster renders into a chunky (byte/nibble) buffer and converts with a table-driven
  chunky-to-planar (c2p) pass. Direct per-column planar writes are ~80 cycles/pixel and are forbidden in hot paths.
- Render window: **160x100 logical pixels, pixel-doubled to 320x200** (or a smaller window inside a HUD frame).
  Column count 160 (2-px wide) baseline; 80 columns (4-px wide) is the low-detail fallback.
- Frame-rate target: >= 14 fps at 160 columns, >= 20 fps at 80 columns, measured in Hatari (`--machine ste`) and later on real iron.
- Music on the YM2149 (VBL tick driver); SFX = 8-bit samples via STE DMA sound (one-shot, no CPU mixing) with a YM fallback.
- Input: joystick port 1 (IKBD) + keyboard; mouse turning optional later.
- Distribution: a single GEMDOS .PRG in an AUTO/ folder on a 720 KB DS floppy, own packed resource files loaded with Fread.
  No copy protection, no custom boot sector. Must not hard-code TOS internals (Line-A vars etc.).

## Hardware gotchas already paid for on real hardware (bake into the platform seam)
- TOS traps clobber d2/a2 that GCC assumes callee-saved: wrap every trap in asm that saves them.
- PSG / palette / shifter / DMA-sound writes need supervisor mode; do them from the VBL or under Supexec.
- IKBD: send $12 (mouse off) and $14 (joystick event reporting) at boot, or fire lands in the mouse packet.
- Floppy: deselect the drive (PSG port A) after loading, or the idle fuse fires mid-sector.
- Hardware READS (e.g. $ffff820a 50/60 Hz) are invisible to the Musashi oracle: they need a Hatari or iron surface.
- .bss must abut text+data (see tos.ld SUBALIGN(2) note) — copy tos.ld and mkprg.py from
  projects/wonderboy/recreate/atari/ rather than re-deriving them.

## Toolchain available on this Mac
- `m68k-elf-gcc` 16.1 (`-m68000 -O2 -fomit-frame-pointer -ffunction-sections -fdata-sections`, link `--gc-sections`
  with a copied tos.ld, wrap with a copied mkprg.py -> .PRG). GNU as syntax for asm (`.s`), NOT vasm/Devpac.
- `hatari` 2.6.1. Headless recipe (from projects/wonderboy/recreate/atari/smoke.py):
  `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy hatari --machine ste --tos <rom> --sound off --fast-forward on --confirm-quit off
   --statusbar off --drive-led off --frameskips 0 --memsize 1 --monitor rgb --run-vbls N --harddrive <dir> --auto <PRG>`
  TOS ROMs: tools/hatari/TOS102US.img, TOS104US.img (ST ROMs). For `--machine ste` prefer Hatari's bundled EmuTOS
  (omit --tos, or find the bundled etos*.img under the Hatari app/share dir) — TOS 1.0x has no STE support.
  Screenshots/memory dumps via a debugger script: `--parse script.txt` with `screenshot out.png` / `savebin` /
  `memdump`; the frame counter can be read from RAM by the shim writing a ledger the script dumps.
- Musashi oracle: tools/recreate_kit/oracle (emu.py) — cycle-exact 68000, for per-function cycle counts.
- Python 3 (conda env atari_reverse) with Pillow 12 and numpy 2. No Aseprite: pixel art is authored as
  reproducible Python scripts (PIL) that emit PNG + native planar/nibble assets.

## Engineering conventions (from the workspace CLAUDE.md — enforced at review)
- Portable C sim core with NO hardware access (`src/`), a host build that renders frames to PNG and runs
  deterministic replay tests (`test/`), and a thin platform seam (`atari/`) with the asm hot loops.
- Fixed timestep, seeded RNG, input recording -> replay golden hashes are the test suite.
- No magic numbers: name every address, offset, size, mask. No raw register names in C identifiers.
- Line length <= 160. Small single-purpose functions. Comment the why. No speculative features.
- Subagents NEVER run `git commit`. The orchestrator commits.
- Every deliverable ends with a short REPORT: what was built, what was measured (numbers), what is unverified.
