# BuggyBoy (Atari ST) — reference project

The worked example for this workspace: Elite's **Buggy Boy** (pseudo-3D racer),
**coded by Martin W. Ward** (string at `0x7e20`; the `"MARTIN"` in the score display is
his name). Fully reverse-engineered: loader, road data, graphics (decompressed + coloured),
and **91/91 functions named**. Use it as a template for how a solved project looks.

## Files

```
bin/        START.PRG (loader) · BUGGYBOY.PRG (game) · COURSES.DAT · GRAPHICS.GRA · BUGBFALC.S (Falcon launcher src)
names.txt   the full name map (fn/var/cmt) — source of truth
decomp.c    decompiled C for all 91 functions (regenerate: reapply.sh)
ghidra_proj Ghidra DB (open: ghidraRun → open this dir)
out/        gfx/ (colour sprite screens) · courses_bitmap.png · dis.txt (first-pass 68k)
run.sh      bootstrap (re-import — wipes names) ; reapply.sh  apply names.txt + re-export
docs/       function_graph.html — interactive d3 call-graph explorer (regenerate: gen_graph.py)
            docs/assets/ — the 8 decoded GRAPHICS.GRA sprite sheets, per-object roadside sprites
            (one per objsprite_* handler, sliced by driving the real blitter), rendered
            screens/course/palette PNGs, buggy-pose GIF animations, and tune/fx WAVs — all produced
            by the C reconstruction (regenerate: gen_assets.py); manifest.json links each to its functions
```

## How it was solved (maps to the docs)

- **START.PRG** — a custom loader (not the game): sets low-res, LZ-unpacks a title
  bitmap, prints a machine/TOS/RAM banner, then `Fopen`/`Fread`s `BUGGYBOY.PRG`, applies
  its DRI relocations by hand, fabricates a basepage, and `jmp`s in. → `tos-os-calls.md`.
- **BUGGYBOY.PRG** — load base `0x10000`. `main` (never returns): GEM `appl_init →
  graf_handle → v_opnvwk`, Malloc buffers, install sound `REFRESH` on the VBL, then
  attract/gameplay loops. Frame = `game_update → draw_frame[build_road_geometry →
  render_road → blit_road_scroll → draw_game_objects → draw_hud]`. → `methodology.md`.
- **Controls**: joystick (IKBD interrogate `$fffffc00`) then keyboard fallback (arrows +
  space) → `input_state`. Physics: input → `engine_rpm` → `speed`; steering → `road_curve`.
- **COURSES.DAT** — *not* a script: road-slice **bitmap** data, streamed 8 bytes at a time
  through a `0x2000` circular buffer and shifted to draw the curving road. → `graphics.md`.
- **GRAPHICS.GRA** — a 0xd00-byte sprite table + RLE-compressed (`0x1234`/`0x5678` runs) →
  8× 320×200 4-plane sprite atlases (logo, buggies, scenery, HUD, font). Extracted to
  `out/gfx/` with palette `0x7f9e` (skip `0xd00` to clear the leading table). →
  `graphics.md`.
- **Course-event engine** — an offset **jump table at `0x11aa2`** (129 entries) dispatches
  course-script opcodes → `evt_flag_gate` / `evt_collision` / `evt_score_msg` → `add_score`
  (BCD) + `play_event_tune`. A second table at `0x13144` dispatches roadside-object sprites.
- **Sound** — driver at `0x1b2xx` (`snd_voice_a/b`, `snd_cmd_handler`), the DRI-symbol
  `INITTUNE`/`EG*`/`REFRESH` family, run from the VBL. → `sound.md`.

## Play it

`remaster/` is a free, playable re-implementation of the game (pixel-identical to the original's
renderer, verified per frame). It runs on a real ST/STE and in Hatari.

```bash
cd remaster
bash render/atari/build_game.sh          # -> render/atari/disk/{BUGGYBOY.PRG, COURSES.DAT, GRAPHICS.GRA}
bash render/atari/game_run.sh            # play the remaster in Hatari
bash render/atari/game_run.sh original   # play the ORIGINAL binary, same emulator setup, for comparison
```

On real hardware, copy the whole `render/atari/disk/` folder to a floppy or hard-disk partition and run
`BUGGYBOY.PRG` — it loads `COURSES.DAT` and `GRAPHICS.GRA` from the directory it was started in. The
game needs **low resolution** (320x200, 16 colours) and about 1 MB of RAM; it binds the STE blitter
automatically when it finds one.

### How the game goes

**Leg select** → pick one of five legs → **get ready** (the countdown) → **drive the leg** → the leg
ends on the timer or a crash tally → if you made the leg's high-score table, **enter your initials** →
the **attract/demo** cycle plays → back to the leg select. That whole outer loop is the original's.

You are driving a buggy over a course of five legs; steer between the gates and flags, avoid the
scenery, and reach the checkpoints before the clock runs out.

### Controls

A **joystick in port 1** works everywhere the keys do and takes **priority**: whenever the stick reports
any direction or its button, the keyboard is ignored for that frame. Keyboard is the fallback whenever
the stick is centred. (This mirrors the original's own input order.)

| Key | During a race | On the leg select | On the name-entry screen |
|---|---|---|---|
| **Up** | accelerate | previous leg | step the initial back (past `A` → `` ` ``) |
| **Down** | brake | next leg | step the initial forward |
| **Left** | steer left | previous leg | step the initial back |
| **Right** | steer right | next leg | step the initial forward |
| **Space** (or joystick fire) | change gear — swaps the engine's rev cap and throttle step | start the selected leg | confirm this initial |
| **F1**–**F5** | — | select **and** start that leg directly | — |
| **F6** | — | preview the race-results screen | — |
| **F10** then **Return** | — | reload `GRAPHICS.GRA` + the score table | — |
| **G** | toggle the dashboard-variant display | — | — |
| **Help** | pause: silence the sound and freeze until any key | — | — |
| **Esc** | abort the leg back to the attract cycle | — | — |
| **Q** | quit to the desktop | quit to the desktop | — |

A few notes:

- **Esc** does what the original does — it ends the leg immediately, ranks the score you have, and drops
  into the attract cycle. It is not a quit key and there is no bonus tally.
- **Q** is the **one deliberate deviation** from the original. The arcade port is a coin-op whose `main`
  never terminates; a GEMDOS `.PRG` needs a way back to the desktop, so Q — a key the original never
  reads — quits. The original has no quit and no restart key.
- On the name-entry screen, dialling **below `A`** gives you `` ` ``; confirming that character **backs
  up** to re-enter the previous initial. A 30-second `TIME` countdown ends entry if it expires.

Implementation notes for these controls — scancodes, the IKBD handler, why the joystick has priority —
are in [`remaster/render/atari/README.md`](remaster/render/atari/README.md).

## Regenerate

```bash
bash reapply.sh    # names.txt -> ghidra_proj + decomp.c (fast)
bash run.sh        # full re-import + analysis (only if starting over; wipes names)
python3 ../../tools/extract_graphics.py bin/GRAPHICS.GRA out/gfx \
        --pal-file bin/BUGGYBOY.PRG --pal-off 0x7f9e --skip 0xd00   # colour sprites
```

## Open threads (optional)

- Per-leg palettes (`0x7f7e–0x8044`) for pixel-exact scenery colour, or capture live in Hatari.
- A `COURSES.DAT` walker that renders each leg's road as a track map.
- Finer names for the ~12 leaf draw/HUD helpers (named from call-context, refinable).