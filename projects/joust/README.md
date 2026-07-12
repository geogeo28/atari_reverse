# Joust (Atari ST, Gamex release) — validation target

Used to **validate the framework on a second, different game**. Verdict: the framework
generalizes to clean GEMDOS binaries of any extension, and the boundary is **packing** —
exactly the predicted gap. This project drove the new
[`docs/packed-executables.md`](../../docs/packed-executables.md) capability.

## Files (`bin/`)
- `GXUT20.PRG` — Gamex save-state utility. **Clean, unpacked** (textbook `Mshrink`
  prologue, 148 relocations, entropy 6.24). The normal pipeline works on it as-is.
- `START.TOS` — Gamex loader: self-relocating **LZ depacker + DRI relocator** (same shape
  as BuggyBoy's `START.PRG`); references a chained `JOUL1.TOS` (not shipped in `bin/`).
- `JOUSTS.CTE` — **the game, PACKED** (entropy 6.95, entry disassembles to garbage,
  0 relocations). Not directly analyzable.
- `JOUST.PCH` — patch/data · `HIGH.SCO` — high score · `README.TXT` — Gamex notes (by "PP").

## What generalized ✓
- Extension-agnostic: `.PRG`/`.TOS`/`.CTE` are all GEMDOS `601a`; `prg_dis`/`PrgLoader`/
  trap-annotate key off the magic, not the name.
- `GXUT20.PRG` is a ready target for the full naming loop.
- `START.TOS` matched the documented "custom loader/depacker" pattern; `prg_dis` read it cleanly.

## Where it hit the wall ✗ → then closed it ✓
`JOUSTS.CTE` is crunched (Gamex/"PP" LZSS). **Statically depacked** with
`tools/depack_gamex.py` (algorithm reverse-engineered from `START.TOS`, validated by
self-depacking `START.TOS` → a valid PRG):

`JOUSTS.CTE` (37 KB, entropy 6.95) → **`bin/JOUST.PRG`** (114 KB, entropy 4.01,
text=0x13aae, data=0x7d00, **1227 relocations**) — a standard GEMDOS PRG. First-pass
confirms the real game: clean init-dispatcher entry, strings `PREPARE TO JOUST` /
`EGG WAVE` / `PTERODACTYL WAVE` / `COPYRIGHT 1985 … RUGBY CIRCLE`, loads `JOUST.MUR`
music, GEMDOS file I/O + XBIOS video + BIOS keyboard. No DRI symbols (unlike BuggyBoy).

## Analyze (normal pipeline — no dump needed)
`JOUST.PRG` is a plain PRG, so it goes straight through `PrgLoader`:
```bash
bash run.sh          # import JOUST.PRG -> analyze -> annotate -> decomp.c
# read decomp.c, grow names.txt, then:
bash reapply.sh
```
`names.txt` currently seeds `_start` + the init-dispatcher comment. Full naming is a
project-sized effort like BuggyBoy — the framework is proven to reach it here.

## Naming progress (40/74 functions)
The whole architecture is mapped. `_start` = `init_system` / `init_game` / `title_screen`
/ `init_video`, then a per-frame main loop of: `update_objects` (buzzard physics/AI),
`animate_objects` (egg-hatch/spawn + anim), `render_objects` (flap-frame draw),
`collision_check`, `spawn_wave`, `wave_manager`, `lava_troll` (wave 4+ pit hand),
`draw_messages`, `check_highscore`, plus `scroll`/`vsync`/input. Graphics layer named:
`blit_copy`/`or`/`andnot`, `blit_sprite`(+mask), `draw_string`, `fill_screen`, palette
cycling. ~34 leaf helpers remain `FUN_*` (next passes). Confidence-tagged (`# ctx`) where
inferred. Apply + re-read: `bash reapply.sh`.