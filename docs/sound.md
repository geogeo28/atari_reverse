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

## Z80/AY heritage in an ST conversion — two gotchas that read as bugs

Many ST games are conversions of a Spectrum, Amstrad or MSX original, and the sound data usually
crosses over with the code that read it rather than being re-authored. Both machines drove the same
General Instrument AY-3-8910 the ST's YM2149 is a clone of, so the data is *nearly* portable — and
the two places it is not both look like a reconstruction bug rather than a heritage artefact.

**Word tables in the data are LITTLE-endian.** The Z80 is little-endian and the 68000 is not, so a
table of 16-bit offsets carried over unchanged has to be read back byte-swapped. Zynaps'
`sound_lookup_tune` (0x16b32) does exactly that, and the code makes it obvious once you expect it:

```
move.b 1(a1),d1     ; HIGH byte from the SECOND byte of the entry
lsl.w  #8,d1
move.b (a1),d1      ; ...and the low byte from the first
```

A 68000 routine that wanted a big-endian word would have written `move.w (a1),d1`. If you see a
byte-swapped assembly like this — or, reading a table by hand, if the offsets look like garbage one
way round and ascend the other — the data is imported, not corrupt. Zynaps' table reads
0x019a, 0x023d, 0x02da, … little-endian and 0x9a01, 0x3d02, 0xda02, … big-endian; only one of those
is a table.

**Note periods are doubled.** The AY in a Spectrum runs at ~1.77 MHz and in an Amstrad/MSX at
1 MHz, while the ST clocks its YM2149 at 2 MHz. Period = clock / (16 × frequency), so the same
musical note needs roughly **twice** the period value on the ST. A conversion either re-tabulated
its note table or left the old one and doubled at play time (`add.w d0,d0` / `lsl.w #1` on the
period just before the `$ff8800` write). Finding a shift you cannot otherwise explain on the way to
the period registers is a strong hint the note table is the original machine's; conversely, a port
that reproduces such a table but drops the doubling plays an octave high, which no image diff can
see — the periods only exist on the chip. That is a case for the direct-PSG ledger
(`TRAP_MODEL.md`, Phase 6), which compares the register write stream rather than memory.

## Naming approach

Anchor on the VBL-installed refresh routine and any exported symbols, then name outward:
`snd_voice_a/b/c` (per-channel updaters), `snd_cmd_handler` (stream dispatch),
`play_tune`/`play_sfx` (the event hooks), `stop_music`. Treat the PSG register writes as
the definition of what each routine does.

## Hearing it (BuggyBoy)

Once the driver is located you can *listen* without reimplementing it: run the original
`REFRESH` in the Musashi oracle and render the register writes it makes. For BuggyBoy this
lives in `projects/buggyboy/recreate/sound/`:

- `tools/recreate_kit/oracle/shim.c` taps writes to `$ff8800`/`$ff8802` into an ordered `(reg,val)` log
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

## Dumping a whole sound set (Zynaps)

`projects/zynaps/tools/extract_audio.py` does the same job one game over — original replayer under
the oracle, register stream out, YM6 + WAV in `out/audio/` — and its 45-number sweep surfaced three
things that are properties of *this kind of driver* rather than of Zynaps, and that a first attempt
will read as bugs.

**One counter free-runs, and it is what stops an exact loop being found.** A "the whole mutable
state repeated" detector is the strongest loop proof there is, and it fails on most tunes for a
reason that has nothing to do with the music: some counter is stepped **unconditionally, every
tick**, at a period of its own. Wonder Boy's is the song-speed accumulator; Zynaps' is the noise
sweep's counter pair at `sound_noise_block`, which `sound_noise_modulate` advances whether or not
any voice wants noise. Against the record the binary ships its cursor is 0, so both limit bytes are
read out of the zeroed vector page: the first counter fires only when it wraps (256 ticks) and the
second only when *it* wraps, 65,536 ticks — well past any cap worth running, and monotone until
then. The exact state cannot recur before that, so the detector finds nothing.

Note what does *not* follow: the sweep is not driving the loop, it is only witnessing time. The
same driver rewinds that pair whenever a note-on consumes a pending `0xe4`, which is precisely why
Zynaps' `0xe4`-using tunes reach a genuine exact loop and the rest cannot. So the rule is: run the
exact detector to the cap first, and only then re-hash the state with that one field cut out. The
ordering is what keeps the weaker rule from pre-empting a real loop. Be honest about what the
weaker one then proves, though — if the field you cut is not an input to the output (Zynaps' is
not: the register shadow the frames come from is still inside the hash), a "how much of the second
period replays the first" figure is 100% by construction and is a check on your frame/state
alignment, not evidence about the music. Wonder Boy's cut field *was* the row clock, and there the
same figure measures something real.

**A third of the index is fragments, and a fragment started cold is silent.** A stream table is a
table of *streams*, not of sounds: entries reached only by another stream's jump or spawn command sit in it
beside the real ones. Zynaps' numbers 0–9 are melody continuations — they carry no `0xfa` channel
header and, decisively, no `0xe8` volume-table command, so the voice's volume envelope is whatever
the parent stream already selected. Play one from a freshly loaded image and the volume byte steps
up from zero against an unset record: perfectly valid frames, valid periods, and not a sound. That
is data about the format, so dump it and say so (with the stream's own opening bytes on the page)
rather than "fixing" the capture until it makes a noise.

**A volume byte can carry bit 4 by accident, and bit 4 is not part of the level.** These drivers
build a volume by adding a biased delta to a running byte and writing it straight at the chip
without masking, so the register genuinely reaches values above `0x0f` — and bit 4 of registers
8–10 selects the *envelope generator* rather than the fixed level. Whether that is audible depends
on a register the driver may never touch: Zynaps' tick pushes 10..0 and stops (writing 13 would
retrigger the envelope every frame), so the last write to 13 is the reset's, the envelope has long
since finished, and every such channel-frame is **silence** on real hardware. A renderer that
masked the level to four bits instead would play a note there, and no image diff or ledger would
see it — the difference exists only on the chip.

→ Naming everything else: [`methodology.md`](methodology.md).