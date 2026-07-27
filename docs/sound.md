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

### BuggyBoy's stream encoding (worked example)

A recovered command set, for the shape to expect. Bytes `< 0x80` are notes (a note reloads the
duration timer and ends the frame's stream read); `0x80..0x8C` index the 13-entry jump table at
`snd_cmd_table` (`0x1b394`); `≥ 0xB0` set a field in place and read on — `0xB0..0xBF` waveform,
`0xC0..0xDF` pitch, `0xE0..0xFF` note duration. "(n op)" = n operand bytes follow the command.

| Byte | Name | Handler does |
|-----:|------|--------------|
| `0x80` | `REST` | envelope → inactive, then finalise: a rest of one note duration |
| `0x81` | `FLAGS_CLEAR` | clear every voice mode bit (glide / portamento / vibrato off) |
| `0x82` | `PORTAMENTO` | (2 op) step, then delay; arms the portamento bit |
| `0x83` | `GLIDE_DOWN` | arm glide-down, then fall into `GLIDE_UP` |
| `0x84` | `GLIDE_UP` | arm glide: the sounding note walks ±1 per frame |
| `0x85` | `LOOP` | jump to the next loop-table entry (a 0 entry restarts the loop) |
| `0x86` | `VIBRATO` | (2 op) step, then depth; arms the vibrato bit |
| `0x87` | `SET_BIT1` | arms voice flag bit 1 (musical role not recovered) |
| `0x88` | `END_TUNE` | stop music, and abort the rest of the driver's frame |
| `0x89` | `SET_F13` | (1 op) → the voice byte that biases the period-table index |
| `0x8A` | `SET_BIT12` | arms voice flag bits 1+2 (roles not recovered) |
| `0x8B` | `SET_R6_SRC` | (1 op) → the value the per-frame DSP feeds to PSG reg 6; also bits 1+2 |
| `0x8C` | `ENV_HOLD` | set note bit 7 so the next note keeps the running envelope |

Names are *claims* recovered from what each handler does; the two `SET_BIT*` entries keep the
offset+role convention because their musical intent was never grounded. The port's `SND_OP_*`
constants (`projects/buggyboy/remaster/include/sound.h`) are this table.
- "Play jingle N" entry points take a track id in `d0`, gate on a priority flag
  (don't interrupt a higher-priority tune), set state, and call the tune-init routine —
  these are the hooks the game triggers on events (start, crash, checkpoint, game-over).

## Naming approach

Anchor on the VBL-installed refresh routine and any exported symbols, then name outward:
`snd_voice_a/b/c` (per-channel updaters), `snd_cmd_handler` (stream dispatch),
`play_tune`/`play_sfx` (the event hooks), `stop_music`. Treat the PSG register writes as
the definition of what each routine does.

## Hearing it (BuggyBoy)

Once the driver is located you can *listen* without reimplementing it: run the original
`REFRESH` in the Musashi oracle and render the register writes it makes. For BuggyBoy this
lives in `projects/buggyboy/recreate/sound/`:

- `oracle/shim.c` taps writes to `$ff8800`/`$ff8802` into an ordered `(reg,val)` log
  (`osh_psg_*`), read back per frame via `emu.psg_writes()`.
- `sound_player.py` seeds a track with `INITTUNE` (music) or `INITFX` (effects), then calls
  `REFRESH` once per 50 Hz VBL — feeding the image forward so driver state persists — and
  captures the per-frame register stream.
- `ym2149.py` renders that stream (3 tones + noise + envelope, mixer, ~3 dB/step volume DAC)
  to a WAV in `out/sound/`. Run `python sound/sound_player.py` (needs numpy).

Timing is authentic (real driver, real 2 MHz clock, exact 50 Hz frames); only the YM DAC
curve and envelope edge-cases are approximated. Cross-check against Hatari's audio if in doubt.

**Playing it on a C64 SID.** The same captured register stream can be *transcoded* to the
Commodore 64's SID (`sound/sid.py`, via reSID-fp / `pyresidfp`): run
`python sound/sound_player.py --synth sid` to write `out/sound/*_sid.wav` beside the YM refs.
The chips differ, so it's a mapping, not a copy — YM square → SID 50% pulse, YM noise → SID
noise (driven by the YM *noise* rate, since SID clocks its LFSR from the voice frequency),
and per-channel YM volume/envelope → per-voice software amplitude scaling (SID has no
per-voice volume, and this also stands in for YM's hardware-envelope "buzz", which SID lacks).
The output is AC-coupled (DC-block) and faded in to mimic the real C64 and drop reSID's reset
transient. It keeps BuggyBoy's exact arrangement and 50 Hz timing, rendered in SID timbre; it
is *not* a re-scored native C64 tune (no filter/PWM/ring-mod craft).

**Exact durations.** Each frame is 1/50 s, and the driver defines a sound's end: it clears
`mzflag` (music) or `fxflag` (effects), or its state freezes. `sound_player.py` steps until
then, so every WAV is the sound's natural length; a driver-RAM state *revisit* (period > 1)
would flag a true loop. What this surfaces for BuggyBoy:

- **Music: ids 0–6 are real, self-terminating tracks** (2.8 s–47 s). `tune 3` is a ~102 s
  through-composed piece — *not* a loop (no state ever recurs; it ends by freezing to silence).
  Tunes 7–9 are short stubs past the real set.
- **Effects: the table is 9 records at `0x1bc56` (`0x12` each), ending at the text end
  `0x1bcf8`.** So ids 0–8 are real; **id ≥ 9 reads zeroed BSS past the table** → an empty
  effect (tone period 0, an envelope that is never triggered) → silent. That is why `fx 9`
  produces nothing. An envelope-mode channel whose reg 13 is never written must read as a
  *completed* (silent) envelope, not a fresh one — the synth models this.

→ Naming everything else: [`methodology.md`](methodology.md).