# render/atari — run the reconstructed screen on a real 68000 (Hatari)

This takes the reconstruction one step past the host PNG render (`../render_screen.py`): it
**cross-compiles the very same C cores to 68000** and runs them as a GEMDOS `.PRG` under Hatari
with a real TOS ROM. A headless run then proves the on-target framebuffer is **byte-identical**
to the host render — so the reconstructed C is correct not just against the Musashi oracle, but
compiled and executed on an independent 68000.

Four screens are wired up (selected at build time): `leg` → `g_draw_leg_results`, `results` →
`g_draw_results_screen`, `highscore` → `g_update_highscore` (populate the table) then
`g_draw_results_screen`, and `intermission` → `g_init_scoretable` + `g_draw_intermission` (the
scrolling between-legs credits/table/times screen).

**The whole game** is wired up too (`game_*` files): `game_main.c` mirrors the original `main()`
— it builds the image, loads + unpacks the graphics, installs the VBL sound driver and IKBD
joystick handler, and runs the attract → leg-select → race → results loop, all from the verified
cores. See "Playable game" below.

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
| `main.c`        | Atari shim: build the image in BSS, load `STATIC.BIN` + `COURSES.DAT` + `GRAPHICS.GRA`, set the buffer pointers, call `g_unpack_graphics` then the selected screen (leg / `-DDEMO_RESULTS` / `-DDEMO_HIGHSCORE`, the last loading the `HISCORE.BIN` player record and calling `g_init_scoretable` + `g_update_highscore` first), dump the framebuffer to `C:\SCREEN.BIN`, blit to `Physbase()`, wait for a key. Also the freestanding `memcpy/memmove/memset`. |
| `os.s`          | `_start` + GEMDOS/XBIOS trap wrappers (Fopen/Fread/Fclose/Fcreate/Fwrite, Cconin, Physbase, Setpalette). |
| `tos.ld`        | link at base 0 as one tight text+data blob; the 1 MiB image is `.bss` (TOS zeroes it). |
| `mkprg.py`      | wrap the linked ELF into a GEMDOS `.PRG` — header + flat binary + a relocation table built from the ELF's `R_68K_32` fixups (`ld --emit-relocs`). |
| `gen_static.py` | dump the relocated PRG static-data region (`[0x10000,0x1c000)`: fonts, label strings, fill patterns) via the harness loader, so the on-target data matches the host exactly. |
| `gen_hiscore.py`| write `HISCORE.BIN` (the 12-byte `highscore` player record) from `../hiscore_demo.py` — the same bytes the host render pokes, so the two agree byte-for-byte. |
| `shim_include/` | a minimal freestanding `<string.h>` (this bare-metal GCC ships no libc). |
| `build.sh`      | compile + link + wrap + stage the drive (`disk/`). |
| `run_hatari.py` | headless: auto-run the PRG, read back `C:\SCREEN.BIN`, de-interleave to PNG, diff against the host render. |
| `run.sh`        | interactive: launch Hatari (GUI) so you can watch it. |
| `game_main.c`   | the whole game: image build, load+unpack, VBL sound, IKBD input, attract/leg-select/race/results loop (mirrors the original `main()`). |
| `game_os.s`     | GEMDOS/XBIOS trap wrappers + the IKBD joystick-packet interrupt handler for the game build. |
| `game_build.sh` | build `BUGGY.PRG` (add `smoke` for the headless `-DSMOKE` render test). |
| `game_run.sh`   | play `BUGGY.PRG` in the Hatari GUI. |
| `game_smoke.py` | headless: boot the smoke build, verify the on-target framebuffer is a real rendered scene. |

## Use

```bash
brew install m68k-elf-gcc                # one-time: the cross toolchain (+ binutils)
bash render/atari/build.sh highscore     # -> build/HIGHSCORE.PRG + disk/  (or: leg / results)
python render/atari/run_hatari.py highscore   # headless verify: prints MATCH + writes *_hatari.png
bash render/atari/run.sh highscore       # watch it in the Hatari GUI (press a key to exit)
```

Hatari needs a 4 MiB machine here (`--memsize 4`) because the 1 MiB game image lives in the
program's BSS. `build/` and `disk/` are gitignored build artifacts.

## Playable game

`game_main.c` + `game_os.s` build the entire reconstruction into a runnable game (not just a static
screen). The cores are the whole game — `game_main` only supplies the hardware boundary the
differential harness stubbed out: real `Setpalette`, a video-base page-flip in `g_flip_screen`, the
IKBD joystick command sequence + packet handler for input, and the 50 Hz VBL sound driver installed
in the TOS `_vblqueue`. It loads the data files in user mode (GEMDOS handle allocation misbehaves
from supervisor — see [`docs/binary-formats.md`](../../../../docs/binary-formats.md)), then
`Super()`s for the hardware phase.

**Leg-select** is driven by the original's function-key menu (`ip_menu`, ported from `0x2b24`):
press **F1–F5** to pick and start a leg (F1 = leg 1 … F5 = leg 5), **F6** to preview the results
screen, **F10** then **RETURN** to reload the graphics. This menu polls the GEMDOS console, which the
differential harness models as always-empty (so it stays a no-op under test); the real trap lives in
`game_main.c`'s `g_console_scancode`/`g_console_wait_char` overrides. Once a leg starts, arrows steer,
space fires/shifts, and ESC quits the leg.

```bash
bash render/atari/game_build.sh          # -> build/BUGGY.PRG + disk/
bash render/atari/game_run.sh            # play it in the Hatari GUI (arrows steer, space fires, ESC quits a leg)

bash render/atari/game_build.sh smoke    # -DSMOKE=120: skip leg-select, render 120 race frames, dump C:\SCREEN.BIN
python render/atari/game_smoke.py        # headless: boot, run, verify the on-target framebuffer is a real rendered scene

bash render/atari/game_build.sh legdump  # -DSMOKE_LEG: draw g_draw_leg_results, dump it, terminate
python render/atari/game_smoke.py legdump # headless: prove the on-target buffer is BYTE-IDENTICAL to the host render
```

The `smoke` build is the headless proof: it forces leg 0, runs the full per-frame pipeline
(`game_update → render_road → blit_road_scroll → draw_game_objects → draw_hud → flip`) on the real
68000, dumps the framebuffer and checks it is a non-blank scene (`out/render/game_smoke.png`). The
`legdump` build goes further — it renders the deterministic leg-select screen and byte-compares the
on-target buffer against the host `g_draw_leg_results` (prints `MATCH`), so the on-target draw is
proven identical to the oracle-verified reconstruction, not just "looks right". The `BEACON(n)`
marker files (SMOKE-only) drop `B<n>` files on `C:` at each init step so a hang can be pinpointed by
the highest marker present.

## Performance

The reconstruction runs at close to the original's speed on a stock 8 MHz ST. The one change that
mattered: the big-endian image accessors in `include/machine.h` (`be16`/`be32`/`wr16`/`wr32`) are
compiled *natively* on the 68000. They exist to preserve the 68000's byte order on a little-endian
*host* (the differential-test `.so`), where they must assemble each word byte-by-byte — but the
m68k target IS big-endian, so there they are just aligned `move.w`/`move.l`. The accessors are now
`#if __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__`-guarded to emit the native load/store on-target; the
host path is untouched, so all differential tests stay byte-identical. This is the hot path — every
field read in every draw/blit routine — so before the fix GCC emitted an `lsl #8` shuffle on *every*
access and the whole game (menu included, no `render_road` involved) ran ~4x too slow; after it the
byte-shuffle code is gone and the PRG is ~40% smaller too. The PRG is also built `-O2` (not `-Os`)
with a long-word `memcpy`/`memset`; none of this touches the verified cores. If you still want it
faster than a real ST, `hatari --cpuclock 16` (or `32`) overclocks the emulated CPU.

## Fidelity

Colours and text are the game's own: `main.c` points `Setpalette` at the results-screen palette
in `STATIC.BIN` (`0x17fc2`), and stages `COURSES.DAT` at `mem_base` so the per-leg labels/digits
(`buf_a = mem_base + 0x1900`) are the real course names. The results screen's SCORE/NAME rows come
from the runtime `highscore_table` (`0x18266`, ships all-zero): `results` shows them blank, while
`highscore` builds the game's default table on-target with the verified `g_init_scoretable` and
ranks a demo player record (`HISCORE.BIN`, 12 bytes) into it with `g_update_highscore` first (only
the player record is demo data). Everything else is from static data or the data files.
