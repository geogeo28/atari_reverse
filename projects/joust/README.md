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
(the TITLE PICTURE — 0x7d00 bytes = one whole low-res framebuffer — not music, despite the
extension; and the loader is patched out in this release, see recreate/README.md), GEMDOS file I/O + XBIOS video + BIOS keyboard. No DRI symbols (unlike BuggyBoy).

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
**All 75 confirmed — none is still `# ctx`**, and one function Ghidra had missed (`fill_pattern_n`,
unreferenced) was added. Of the 56 names that carried `# ctx`, **37 were renamed** (35
substantively, 2 cosmetically) and 19 stood up as written. One previously-*untagged*
function was wrong too (`xbios_setcolor` → `flash_hiscore_color`), along with six untagged
variables. (The old header claimed 61 `# ctx` of 74; the file actually held 56 of 74.)

`_start` is twenty-one `jsr`s and a `bra.s`, nothing else. The first four —
`init_system`/`init_game`/`title_screen`/`init_video` — run once, and the branch at `0x1007e` goes
back to the **fifth**, so calls 5..21 are the per-frame loop, in this order:
`raise_floor` → `animate_ground_shrink` → `count_objects_and_pad` → `update_eggs` →
`read_joysticks` → `update_objects` (rider physics/AI) → `update_pterodactyl` → `render_objects` →
`collision_check` → `draw_platforms` → `draw_messages` → `lava_troll` → `dissolve_platforms` →
`wave_manager` → `snd_poll_done` → `poll_quit_key` → `check_highscore`.
(An earlier revision of this paragraph listed thirteen of the seventeen and started them in the
wrong place; the order above is asserted against the binary by
`recreate/test/test_init.py::test_start_is_twenty_one_calls_and_a_branch`.)

**The biggest correction is that Joust's sound driver was named as graphics/input code.**
The XBIOS opcode tables in `tools/prg_dis.py` and `tools/ghidra_scripts/AtariOsTrapAnnotate.java`
**were** wrong (`0x20` is **Dosound**, not Supexec; `0x1c` Giaccess and `0x19` Ikbdws were missing
entirely), so every trap in the sound layer was mislabelled. **Both tables are fixed now** — see the
trap-table warning in [`docs/tos-os-calls.md`](../../docs/tos-os-calls.md); re-running `prg_dis.py`
resolves all 71 trap sites with no `XBIOS ?` left. Reading the raw traps gave:
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

The last two `# ctx` names were held open for the same reason — the mechanism was read but the
*picture* was not — and both have since been discharged by reconstructing the routine and
rendering its sprite data. One name held, one did not:
- 0x13628 was `draw_spawn_sparkle`; rendering `0x1194c` showed a solid tapering trapezoid painted
  in a flat cycled colour, landing on the colour-4 pad already baked into every platform bitmap.
  It is not a sparkle — **renamed `flash_spawn_pad`**.
- `animate_ground_shrink` (0x175de) — rendering `0x18636`/`0x187e6` settled it: two lava-flame
  sprites that burn the ground in from both ends. The name stood.

`names.txt` also grew from 26 to **95 `var`s and 76 `cmt`s**, including the 0x4e-byte object
layout, the platform/edge/spawn-point/pterodactyl table formats, the message record, the
sprite-draw scratch globals and the sound/RNG state. Apply with `bash reapply.sh`.

> Gotcha: the Ghidra project is stamped with its creator's username in
> `ghidra_proj/Joust.rep/project.prp`; a different local user gets
> `NotOwnerException` from `reapply.sh` until `OWNER` is updated.

## README images

`gen_readme_assets.py` renders the workspace README's `assets/joust-*.png` — the title screen,
three frames of the game playing itself, the high-score name entry and a sprite sheet — by driving
the verified cores host-side through ctypes and de-interleaving the framebuffer they paint. It
needs `bin/JOUST.PRG` and a built `recreate/build/libjoust.so`; no Hatari and no TOS ROM. Every
picture is a function of the binary alone (the high-score record staged is the blank one the `.PRG`
carries, not `bin/HIGH.SCO`), so every run is byte-identical.

```bash
cd recreate && make venv && make && ./.venv/bin/python ../gen_readme_assets.py
```

**Its address and offset constants mirror `recreate/include/*.h` with nothing pinning them equal.**
`make test` never imports the script, so a header address corrected later would leave it
reading the old one and silently re-render a wrong picture. Closing that means a pin test in
`recreate/test/` (the mechanism `test_constants.py` already provides) — deliberately not taken
here, since it would change the differential suite.