# Joust (Atari ST, Gamex release)

The **second game** through this workspace's pipeline, and the reason it was started: Buggy Boy had
proved the method on one binary, and Joust was picked to find out whether the method or the binary
was doing the work. It is a different publisher, a different decade of tooling, and a compiler
rather than a human writing the assembly — and the point of it is how little had to move.

It went well past that validation. **75/75 functions verified · 4368 differential tests**, and a
playable `JOUST.PRG` cross-compiled back to m68k and pinned against the shipped binary frame by
frame. It stops at the proving stage — there is **no Joust remaster**.

The one thing that did not generalize on contact was **packing** — exactly the predicted gap. The
framework reaches clean GEMDOS binaries of any extension unchanged; the game ships crunched, and
closing that drove the new [`docs/packed-executables.md`](../../docs/packed-executables.md)
capability.

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
`tools/depack_gamex.py` — the algorithm reverse-engineered out of the release's own
`START.TOS`, and validated by self-depacking that loader into a valid PRG:

`JOUSTS.CTE` (37 KB, entropy 6.95) → **`bin/JOUST.PRG`** (114 KB, entropy 4.01,
text=0x13aae, data=0x7d00, **1227 relocations**) — a standard GEMDOS PRG, and from there the
normal naming loop. First-pass confirms the real game: clean init-dispatcher entry, strings
`PREPARE TO JOUST` / `EGG WAVE` / `PTERODACTYL WAVE` / `COPYRIGHT 1985 … RUGBY CIRCLE`, loads
`JOUST.MUR` (the TITLE PICTURE — 0x7d00 bytes = one whole low-res framebuffer — not music, despite
the extension; and the loader is patched out in this release, see recreate/README.md), GEMDOS file
I/O + XBIOS video + BIOS keyboard. No DRI symbols (unlike BuggyBoy).

## Analyze, reconstruct, run
`JOUST.PRG` is a plain PRG, so it goes straight through `PrgLoader` — no dump needed:
```bash
bash run.sh          # import JOUST.PRG -> analyze -> annotate -> decomp.c
# read decomp.c, grow names.txt, then:
bash reapply.sh
```

That loop is finished here — see [Naming progress](#naming-progress-7575-functions--verified). To
rebuild the reconstruction and everything downstream of it (needs your own `bin/JOUST.PRG`):
```bash
cd recreate
make venv && make test                       # the shared kit's oracle + the C cores, the
                                             # differential suite
./.venv/bin/python ../gen_readme_assets.py   # re-render this README's images, host-side
bash atari/build.sh && bash atari/run.sh     # ...or play it on a 68000, under Hatari
```

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

## Recreate — prove it

The harness is **shared**. [`tools/recreate_kit/`](../../tools/recreate_kit/README.md) owns the PRG
loader, the Musashi oracle and the TOS trap model; a game binds to it with a small `project.toml`
naming its binary, load base and image size, and everything else in `recreate/` is game-specific.
Joust needed none of the kit's optional capabilities.

**Status: 75/75 functions verified · 4368 differential tests · no `# ctx` names left.** Being
compiled C rather than hand-written assembly cost one thing Buggy Boy never needed: most of Joust's
routines take their arguments on the **caller's stack**, and the differential deliberately stops
comparing at the stack. `recreate/test/abi.py` fixes that by poking a two-instruction 68000 stub
into free image space and entering the oracle there, so every argument block lands in ordinary,
fully diffed memory. Per-function notes, and every limit that is disclosed rather than closed, are
in [`recreate/STATUS.md`](recreate/STATUS.md).

## On target, three surfaces are compared rather than one

[`recreate/atari/`](recreate/atari/README.md) cross-compiles the same verified cores to m68k and
runs the result under Hatari **beside the shipped binary, on one emulator**. At six sampled frames
of real play — each chosen because its neighbour differs, so a one-frame mis-anchor is detectable —
the **32000 framebuffer bytes** are identical, and so are the **sixteen hardware palette pens read
back off the shifter**. Once more, at a frame from the static band, so is the **rendered picture**:
the emulator's own video output, the one artefact there that is not a memory dump, and the only one
that sees what the player sees. On EmuTOS and on TOS 1.04. The palette and the picture each get
their own injected-fault control, because the frame anchors structurally cannot exercise either —
that README is careful about what each check can and cannot see, and it also records the three bugs
that appear only on real hardware and the one fidelity gap (a register hand-off no C `_start` can
make) that is disclosed rather than papered over.

## Gallery

Rendered **host-side by the reconstruction**, with no emulator and no TOS ROM in the loop:
`gen_readme_assets.py` loads your own `bin/JOUST.PRG` through the kit, drives the verified cores
over ctypes exactly as the tests do, and de-interleaves the framebuffer they paint with the game's
own palette words. It needs `bin/JOUST.PRG` and a built `recreate/build/libjoust.so` — see
[Analyze, reconstruct, run](#analyze-reconstruct-run) for the commands. Every picture is a function
of the binary alone — the high-score record staged is the blank one the `.PRG` itself carries, not
`bin/HIGH.SCO` — so the whole set is byte-identical every run.

| Title screen | Wave 1 begins | A joust, and a loose egg |
|:---:|:---:|:---:|
| ![](../../assets/joust/title.png) | ![](../../assets/joust/wave1.png) | ![](../../assets/joust/eggs.png) |

`init_system` takes the machine over and loads `HIGH.SCO`; `title_screen` then paints the picture
the `.PRG` itself carries, draws its three lines through `draw_string` — the middle one is the
`HIGH SCORE:` line the loaded record is spliced into, blank here because nobody has set one — and
runs one attract pass, which is what `cycle_palette` and the six-pen ring rotate the shown palette
by.

The two frames beside it are the game **playing itself**. `_start`'s init chain runs
(`init_game`, `init_video`), then laps of its frame loop, each lap driven through the two verified
rotated entries either side of the IKBD wait no run can cross — with the joysticks fed from a
seeded generator, because random input is what makes riders fight and eggs exist. Everything drawn
is the loop's own seventeen calls: `draw_platforms`, `render_objects`, `update_eggs`,
`draw_messages`, `collision_check`, `wave_manager` and the rest.

| The pterodactyl arrives | A new record, being typed | The cast |
|:---:|:---:|:---:|
| ![](../../assets/joust/pterodactyl.png) | ![](../../assets/joust/hiscore.png) | ![](../../assets/joust/sprites.png) |

On lap 1850 of that same self-played game `update_pterodactyl` has the bird over the middle of the
playfield, drawn by `blit_mask_wide` and `blit_sprite_planes`. The middle picture ends the same
kind of run: the score it really earned beats the blank record, which is what `check_highscore`
reports when it puts the entry screen up, and `hiscore_key_input` then types the name one console
key per call. The one thing staged there is the last-life flag itself — bounded self-play cannot
reach a real game over, because the frame loop's own glue refuses a lap once the game is finished
and the record taken.

The last is a sheet of the game's own bitmaps, at their own addresses, drawn by the five routines
that draw them in play — only the destination is ours, plus one row count: the lava flames take
theirs from a ground-burn block that only a later wave ever arms, so a cold image has nothing to
read and the sheet supplies the height instead. `draw_object_data` lays out the five rider
sets in three poses plus the three unseated ones, `draw_egg_sprite` the three egg poses,
`blit_sprite_planes` the pterodactyl's four wing beats out of `ptero_frame_table`,
`troll_draw_hand` the lava troll's hand frames out of `troll_sprite_table`, and `blit_sprite` the
four lava flames. No two of them describe a sprite the same way — the rider and egg blitters take
an absolute destination and read `draw_shift`/`draw_rows` as **bytes**, the bird and the hand take
an offset from `screen_base` and read the same two addresses as **words** — which is a width clash
in the original, reproduced rather than tidied.

**The script's address and offset constants mirror `recreate/include/*.h` with nothing pinning them
equal.** `make test` never imports the script, so a header address corrected later would leave it
reading the old one and silently re-render a wrong picture. Closing that means a pin test in
`recreate/test/` (the mechanism `test_constants.py` already provides) — deliberately not taken
here, since it would change the differential suite.
