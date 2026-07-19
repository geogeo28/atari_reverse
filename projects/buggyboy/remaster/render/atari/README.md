# render/atari — run the remaster HUD on a real 68000 (Hatari)

remaster renders only the HUD so far, so this cross-compiles `rm_draw_hud` to 68000 and runs it as
a GEMDOS `.PRG` under Hatari — proving the remaster C is correct not just on the host, but compiled
and executed on an independent 68000.

Because the HUD reads asset tables (font, colour-fill table, mask/cursor tables, the gauge string,
the dashboard graphic from `buf_c`) that normally come from the recreate loaders, we **capture them
once on the host** (`gen_hud_fixture.py`, via the same `adapter.py` the equivalence tests use), bake
them + a realistic mid-race **background** + the `HudState` into `build/hud_fixture.h`, and draw the
HUD over that background on-target.

## The proof

`gen_hud_fixture.py` also writes `build/golden.bin` — recreate's `g_draw_hud` output for the exact
same inputs. The demo dumps its painted framebuffer to `C:\SCREEN.BIN`; `run_hatari.py` byte-compares
that against `golden.bin`. A **MATCH** proves remaster's HUD, cross-compiled and run on a real 68000,
is pixel-identical to the verified recreate cores. (recreate's HUD is itself verified byte-for-byte
against the Musashi oracle, so this closes the loop end to end.)

## Pieces

| file | role |
|------|------|
| `gen_hud_fixture.py` | capture background + assets + `HudState` + golden + palette from the host harness |
| `main.c`             | TOS shim: build the structs from the fixture, `rm_draw_hud`, dump `SCREEN.BIN`, set palette, blit, wait for a key |
| `os.s` / `tos.ld` / `mkprg.py` | GEMDOS entry + trap wrappers, link script, `.PRG` wrapper (copied from recreate's harness) |
| `shim_include/string.h` | minimal freestanding `<string.h>` (bare-metal GCC ships no libc) |
| `build.sh`           | generate fixture → cross-compile `hud.c`+`text.c`+shim → `.PRG` → stage `disk/` |
| `run_hatari.py`      | headless: run the `.PRG`, byte-compare `SCREEN.BIN` vs `golden.bin`, write a PNG |
| `run.sh`             | interactive: watch it in the Hatari GUI |

## Use

```bash
cd projects/buggyboy/recreate && make build/libbuggyboy.so   # once: the fixture generator drives it
cd ../remaster
bash render/atari/build.sh                 # -> build/HUD.PRG + disk/HUD.PRG
python render/atari/run_hatari.py          # headless: prints MATCH, writes out/render/remaster_hud_hatari.png
bash render/atari/run.sh                   # watch it in Hatari (press a key in the ST to exit)
```

Hatari needs a 4 MiB machine (`--memsize 4`); `build/` and `disk/` are gitignored build artifacts.

## Scope

The background road/buggy/scenery is a **captured** recreate frame; only the HUD strip is remaster's
own rendering. Phase 3 (the dashboard-variant sprite) and phase 8 (crash fx) are gated off, so their
regions show the background on both sides. As more of the pipeline is ported (road, objects), this
harness extends to render whole frames.
