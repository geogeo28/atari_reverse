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