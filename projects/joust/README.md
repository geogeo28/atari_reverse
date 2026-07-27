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

## Naming progress (75/75 functions — verified)
Every name has now been checked against the function body (Ghidra decompile **plus** the
68000 disassembly, because Ghidra renders the register-argument routines as bare `return;`).
**73 confirmed, 2 still `# ctx`**, and one function Ghidra had missed (`fill_pattern_n`,
unreferenced) was added. Of the 56 names that carried `# ctx`, **37 were renamed** (35
substantively, 2 cosmetically) and 19 stood up as written. One previously-*untagged*
function was wrong too (`xbios_setcolor` → `flash_hiscore_color`), along with six untagged
variables. (The old header claimed 61 `# ctx` of 74; the file actually held 56 of 74.)

`_start` = `init_system`/`init_game`/`title_screen`/`init_video`, then a per-frame loop:
`update_objects` (rider physics/AI) → `update_eggs` → `read_joysticks` → `update_pterodactyl`
→ `render_objects` → `collision_check` → `draw_platforms` → `lava_troll` →
`dissolve_platforms` → `wave_manager` → `snd_poll_done` → `poll_quit_key` → `check_highscore`.

**The biggest correction is that Joust's sound driver was named as graphics/input code.**
The XBIOS opcode tables in `tools/prg_dis.py` and `tools/ghidra_scripts/AtariOsTrapAnnotate.java`
are wrong (`0x20` is **Dosound**, not Supexec; `0x1c` Giaccess and `0x19` Ikbdws are missing
entirely), so every trap in the sound layer was mislabelled. Reading the raw traps gave:
`set_color_lvl` → **`play_sound`** (Dosound off `sound_table`, 21 call sites),
`read_key_flag` → **`snd_poll_done`** (Giaccess reads the YM2149 mixer to release the
priority), `init_gfx` → **`snd_tone_sweep`** (a PSG pitch/volume sweep), and
`wait_vsync` → **`read_joysticks`** (Ikbdws `0x16` interrogate → `control_player` per stick).
Other significant renames: `spawn_wave` → `update_pterodactyl` (the bird, not the wave),
`animate_objects` → `update_eggs`, `alloc_object` → `erase_egg_sprite` (it allocates
nothing — it AND-NOT-masks the egg out), `respawn_player` → `start_death_anim`,
`bonus_life` → `draw_lives`, `add_score*` → `score_update*` (they carry-propagate digits
the caller already bumped), `check_messages` → `find_free_message`,
`draw_explosions` → `dissolve_platforms`, `scroll_screen_up` → `raise_floor`,
`stub_ret`/`stub_ret2` → `make_fill_pattern`/`select_sprite_base` (not stubs at all).
`p1_x`/`p2_x` pointed at object+4, which is **y**; `cursor_pos` is the sprite **shift**
(`x mod 16`) that every blitter uses, reused as the name-entry cursor only during the
high-score screen.

Still `# ctx`, both for the same reason — the mechanism is read but the *picture* is not:
- `draw_spawn_sparkle` (0x13628) — proven to draw a 3-longword pattern from `0x1194c` at a
  `spawn_points` entry during the respawn branch; rendering `0x1194c` would name the shape.
- `animate_ground_shrink` (0x175de) — proven to narrow `ground_x0`/`ground_x1` (platform 0)
  on wave 3 while blitting two sprites; rendering `0x18636`/`0x187e6` with
  `tools/extract_graphics.py` would settle what is actually on screen.

`names.txt` also grew from 26 to **95 `var`s and 76 `cmt`s**, including the 0x4e-byte object
layout, the platform/edge/spawn-point/pterodactyl table formats, the message record, the
sprite-draw scratch globals and the sound/RNG state. Apply with `bash reapply.sh`.

> Gotcha: the Ghidra project is stamped with its creator's username in
> `ghidra_proj/Joust.rep/project.prp`; a different local user gets
> `NotOwnerException` from `reapply.sh` until `OWNER` is updated.