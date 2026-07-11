# Sound

ST audio is the **YM2149 PSG** (Programmable Sound Generator) at `$ffff8800/8802`, plus
(on STE) DMA sample sound at `$ffff8900+`. Most games run a small music/SFX driver from
the **VBL interrupt** (50 Hz), stepping a note/command stream each frame.

## YM2149 access

Two registers: write the register number to `$ffff8800`, then the value to `$ffff8802`
(some code reads `$8800` back for the joystick/keyboard port). 16 PSG registers:

| Reg | Role |
|----:|------|
| 0–5 | tone period (fine/coarse) for channels A/B/C |
| 6 | noise period |
| 7 | mixer (tone/noise enable per channel) + port I/O direction |
| 8–10 | channel A/B/C volume (bit 4 = use envelope) |
| 11–12 | envelope period |
| 13 | envelope shape |
| 14–15 | I/O ports A/B (14 = joysticks/drive select, keyboard) |

Port A/B on reg 14/15 is also how the machine reads joystick fire / drive select, so the
sound chip and input can share code.

## Finding & reading the driver

- The driver is usually **installed as a VBL handler** (see `hardware-map.md`: `_vblqueue`
  at `0x456`). Find who writes `0x456` — the pointer it installs is the per-frame sound
  update (BuggyBoy: `REFRESH`).
- Exported symbols, if present, name it for you. BuggyBoy shipped DRI symbols
  `INITTUNE`, `INITFX`, `TURNOFF`, `EGOFF`, `EGVOL`, `EGFREQ`, `EGFLAG`, `FXFLAG`,
  `MZFLAG`, `VOLUME`, `REFRESH` — a classic tune + envelope-generator (EG) + effects driver.
- Per-voice update routines read a **command stream**: bytes below a threshold are notes;
  bytes ≥ `0x80`/`0xB0` are commands dispatched through a small jump table (BuggyBoy's is
  at `snd_cmd_table`). Struct fields per voice hold current note, envelope counter,
  glide/portamento state.
- "Play jingle N" entry points take a track id in `d0`, gate on a priority flag
  (don't interrupt a higher-priority tune), set state, and call the tune-init routine —
  these are the hooks the game triggers on events (start, crash, checkpoint, game-over).

## Naming approach

Anchor on the VBL-installed refresh routine and any exported symbols, then name outward:
`snd_voice_a/b/c` (per-channel updaters), `snd_cmd_handler` (stream dispatch),
`play_tune`/`play_sfx` (the event hooks), `stop_music`. Treat the PSG register writes as
the definition of what each routine does.

→ Naming everything else: [`methodology.md`](methodology.md).