# render/atari — run the reconstructed screen on a real 68000 (Hatari)

This takes the reconstruction one step past the host PNG render (`../render_screen.py`): it
**cross-compiles the very same C cores to 68000** and runs them as a GEMDOS `.PRG` under Hatari
with a real TOS ROM. A headless run then proves the on-target framebuffer is **byte-identical**
to the host render — so the reconstructed C is correct not just against the Musashi oracle, but
compiled and executed on an independent 68000.

Three screens are wired up (selected at build time): `leg` → `g_draw_leg_results`, `results` →
`g_draw_results_screen`, and `highscore` → `g_update_highscore` (populate the table) then
`g_draw_results_screen` (the race-end high-score table with entries).

## Why this works with unmodified cores

The cores take the flat game image as a pointer argument and only ever compute `image + offset`
— they never dereference an absolute address baked into the binary (the one stored pointers they
read, `buf_*`/`physbase_tbl`, the shim sets itself, as plain offsets). So the code is
position-independent in the way that matters, and where TOS loads the program is irrelevant. The
GEMDOS relocation table (`mkprg.py`) only fixes up the handful of absolute references the
compiler/`libgcc` emit for their *own* code and data.

## Pieces

| file | role |
|------|------|
| `main.c`        | Atari shim: build the image in BSS, load `STATIC.BIN` + `COURSES.DAT` + `GRAPHICS.GRA`, set the buffer pointers, call `g_unpack_graphics` then the selected screen (leg / `-DDEMO_RESULTS` / `-DDEMO_HIGHSCORE`, the last loading `HISCORE.BIN` and calling `g_update_highscore` first), dump the framebuffer to `C:\SCREEN.BIN`, blit to `Physbase()`, wait for a key. Also the freestanding `memcpy/memmove/memset`. |
| `os.s`          | `_start` + GEMDOS/XBIOS trap wrappers (Fopen/Fread/Fclose/Fcreate/Fwrite, Cconin, Physbase, Setpalette). |
| `tos.ld`        | link at base 0 as one tight text+data blob; the 1 MiB image is `.bss` (TOS zeroes it). |
| `mkprg.py`      | wrap the linked ELF into a GEMDOS `.PRG` — header + flat binary + a relocation table built from the ELF's `R_68K_32` fixups (`ld --emit-relocs`). |
| `gen_static.py` | dump the relocated PRG static-data region (`[0x10000,0x1c000)`: fonts, label strings, fill patterns) via the harness loader, so the on-target data matches the host exactly. |
| `gen_hiscore.py`| build `HISCORE.BIN` (the `highscore` demo table + player record) from `../hiscore_demo.py` — the same data the host render pokes, so the two agree byte-for-byte. |
| `shim_include/` | a minimal freestanding `<string.h>` (this bare-metal GCC ships no libc). |
| `build.sh`      | compile + link + wrap + stage the drive (`disk/`). |
| `run_hatari.py` | headless: auto-run the PRG, read back `C:\SCREEN.BIN`, de-interleave to PNG, diff against the host render. |
| `run.sh`        | interactive: launch Hatari (GUI) so you can watch it. |

## Use

```bash
brew install m68k-elf-gcc                # one-time: the cross toolchain (+ binutils)
bash render/atari/build.sh highscore     # -> build/HIGHSCORE.PRG + disk/  (or: leg / results)
python render/atari/run_hatari.py highscore   # headless verify: prints MATCH + writes *_hatari.png
bash render/atari/run.sh highscore       # watch it in the Hatari GUI (press a key to exit)
```

Hatari needs a 4 MiB machine here (`--memsize 4`) because the 1 MiB game image lives in the
program's BSS. `build/` and `disk/` are gitignored build artifacts.

## Fidelity

Colours and text are the game's own: `main.c` points `Setpalette` at the results-screen palette
in `STATIC.BIN` (`0x17fc2`), and stages `COURSES.DAT` at `mem_base` so the per-leg labels/digits
(`buf_a = mem_base + 0x1900`) are the real course names. The results screen's SCORE/NAME rows come
from the runtime `highscore_table` (`0x18266`, ships all-zero): `results` shows them blank, while
`highscore` loads a demo table (`HISCORE.BIN`) and runs the verified `g_update_highscore` to rank a
player record into it first (the table is demo data; the ranking/insert is real). Everything else
is from static data or the data files.
