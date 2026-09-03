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

## The STE's mixer, and the one value that lets the YM through

On an STE both the DMA sample voice and the YM leave the machine through a **National LMC1992**
volume/tone/mixer chip, driven over the **MicroWire** bus: write the latch mask to `$ffff8924`, the
word to `$ffff8922`, then spin until the mask register reads back as itself (the chip rotates it as
it shifts out the frame) — bounded, because a machine whose MicroWire never completes must not hang
the boot. The word is 11 bits under a `$07ff` mask: **2 device-address bits** (`%10` for the
LMC1992), **3 command bits**, **6 data bits**. Commands are `0` mixer, `1` bass, `2` treble, `3`
master, `4` right, `5` left; bass and treble run 0–12 with **6** flat, master 0–**40**, each side
0–**20**.

**The mixer field is where this bites.** The widely repeated reading — that the two bits mean
`00 = −12 dB, 01 = PSG only, 10 = DMA only, 11 = PSG + DMA` — does not survive measurement, and
getting the field wrong is silent in every register-level way: the writes look right, the trace is
clean, the samples play, and **the music is simply gone**. BLACK ICE built its driver four times
and recorded each run (`projects/blackice/audio/REPORT.md`, "The defect this found, which no register check could have"):

| mixer value | all-silent audio frames, of 700 |
|---|---|
| 0 | 597 |
| **1** | **294** |
| 2 | 597 |
| 3 | 597 |

Only **1** lets the YM through, and EmuTOS's own boot writes 1 here — a second, independently written
piece of software reading the field the same way. Both readings are still emulation-side, so what
this establishes is that the folklore encoding is wrong, **not** what the silicon does. **TOS leaves
the LMC1992 wherever the last program left it**, so a game that does not route it can ship silent on
a machine that works. And note which surface caught it: the *audio recording*, not the register
trace — this is the class of bug that needs sound as its surface.

*(Hatari 2.6.1 + EmuTOS; `projects/blackice/audio/REPORT.md`'s "What is unverified" names the command
encoding, the mixer value and the completion poll as unmeasured on real silicon.)*

**The DMA voice itself** — its control, start, end and mode registers, and the odd-address rule they
are laid out under — is [`hardware-map.md`](hardware-map.md)'s, under "The STE sound block". Two
things about *driving* it belong here: the mode register's low two bits are the rate (`00` 6258 Hz,
`01` 12517, `10` 25033, `11` 50066), and the frame registers are set with the voice **stopped**.

**One tempo caveat that is not about the chip.** A driver stepped from the vertical blank is
rate-agnostic, but its *tempo* is not: a score written against 50 Hz plays **20% fast** on a 60 Hz
machine. If the game must sound the same on both, the tempo needs a rate divisor — a game decision,
not a driver one (`projects/blackice/audio/REPORT.md`, "What is unverified" → "A 60 Hz machine").

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
- `ym2149.py` renders that stream (3 tones + noise + envelope, mixer, ~3 dB/step volume DAC,
  band-limited by 8x oversampling and AC-coupled like the machine's output) to a WAV in
  `out/sound/`. Run `python sound/sound_player.py` (needs numpy). `render(normalise=False)` gives
  the chip's own scale instead of each track's peak, which is what makes two renders comparable.

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

## Checking a dump against the real machine (Hatari as the second opinion)

A capture-and-render pipeline cannot judge itself: it runs the original replayer under *our* oracle
and renders the register stream with *our* synth, so a fault in either half comes out as a plausible
`.wav`. Hatari is an independent implementation of both halves, and it will hand you both of them
off one headless boot. `projects/zynaps/tools/ref_capture.py` is the worked example.

**The audio.** There is no `--wav-record` option: the destination is a *config* value and the
recorder is a *runtime shortcut*, so you need both.

```ini
[Sound]
szYMCaptureFileName = /abs/path/ref.wav
```

```
hatari -c that.cfg --sound 44100 ...        # NOT --sound off
hatari-shortcut recsound                    # ...over --cmd-fifo: a TOGGLE, so pair the two sends
```

It works under `SDL_AUDIODRIVER=dummy`: the dummy device is still a device, Hatari mixes into it and
the recorder taps the same buffer. The file is 16-bit **stereo** at the `--sound` rate, both channels
carrying the same mono PSG signal — read it as mono and you read it at half speed. A second span in
one run *replaces* the first, since the config names one path, so copy the finished WAV aside before
starting another. Hatari drops samples rather than stalling if its mixer buffer overruns (it says so
in the log); the honest gate is the recorded LENGTH, because dropped samples make the file short.

**The register stream.** `--trace psg_write --trace-file <path>` prints two lines per write — the
raw `$ff8802` store and the decoded register — of which only `ym write data reg=0x.. val=0x..`
carries both numbers. To cut per-frame register files out of it, look for the driver's own flush as
a **run of writes in the order it makes them** (Zynaps: registers 10..0 descending). That needs no
load address, where a `pc=` filter would have to know where GEMDOS put the program, and it steps
over TOS's own register-14 traffic for the floppy and the keyboard. Watch for a *wider* flush with
the same tail — Zynaps' `sound_reset_psg` pushes 13..0 — and skip it whole, or you file the silenced
chip as a frame of music.

*Read the trace incrementally* if you read it while the run is going. A boot plus a game is tens of
megabytes, re-parsing it costs seconds, and those seconds are **skew** between the register frame
counter and the recorder: measured at ~220 frames (4.4 s) parsing the whole file at the mark.

**Comparing them.** The register surface is the strong one — an exact per-frame comparison, so it is
a yes/no about the bytes, and it settles "did the capture record the right stream?" outright (Zynaps:
1000/1000 frames of the real title screen replay the dump register for register). Two cautions:
compare only the registers the tick actually flushes, since a `.ym` carries `0xff` in register 13 for
"not written this frame" where the chip carries its own value; and mask register 7's top two bits,
which are the I/O-port *direction* bits a driver may OR in and which the YM5/YM6 format reuses as
special-effect codes.

The audio surface is the weak one, and the weakness is **alignment**. A recording does not start on
a driver frame, and a dominant-pitch track is far too unstable to correlate on three simultaneous
square waves — measured against the recording's own registers, the loudest partial is the sounding
fundamental in only 41% of frames, which is the ceiling of any "pitch agrees within a semitone"
figure on this material. Prefer an **alignment-free** measure: the cosine of the two average power
spectra over a span. It cannot see a timing fault at all (that is the register surface's job) but it
sees every difference of timbre, gain stage and filtering, which is what a renderer gets wrong.

## Three things a YM renderer gets wrong, and how the recording shows them

All three were found this way on `ym2149.py`, and all three are properties of the chip rather than
of any one game.

**A tone period of 0 is not silence and is not slow — it is 125 kHz.** The chip reloads the same
counter for 0 as for 1, so both run the tone divider at `CLOCK/16`. Drivers reach it constantly
(Zynaps: 2,268 channel-frames of one tune, and two effects that are period 0 for *every* frame they
have). On the machine that is an inaudible ultrasonic the analog stage averages away. Point-sampled
at 44100 Hz it folds back into the audio band **at full amplitude** and becomes the loudest thing in
the file. The fix is to band-limit: evaluate the channels oversampled (8× puts 125 kHz below the
oversampled Nyquist) and make each output sample the *mean* of its interval, which is the same
integration the analog stage does. It takes the square waves' own aliased harmonics with it.

**The output is AC-coupled, and subtracting the track's mean is not the same thing.** Each channel is
a *unipolar* square, so it carries a DC of amplitude × duty — and that DC **moves with the volume
register**. A tremolo therefore leaves a full-depth sub-audio staircase that one mean for the whole
track cannot touch: measured at 20% of a tune's entire energy below 50 Hz, against 8% in a recording
of the real machine. A moving-mean high-pass with a corner near 20 Hz is the coupling capacitor, and
it moved that tune's alignment-free spectrum agreement from 0.906 to 0.978.

**Per-file peak normalisation is a gain stage inventing a fact.** It makes a one-voice effect as loud
as a three-voice tune and pulls a nearly-silent track up to full scale. Render on the *chip's* scale
instead — 0 dBFS = every channel at volume 15 — which cannot clip by construction and leaves the
files comparable with each other. Zynaps' set then spans −1.6 dBFS (the title music) to −34.7 (a
one-voice jingle), which is how far apart they really are.

**And one it gets right, once you check.** An envelope-mode volume (bit 4 of registers 8–10) is
silence *only if* the envelope has finished, which depends on a register the driver may never touch.
Do not reason about it — read it. Zynaps' shipped register shadow carries shape `0x00`, a one-shot,
and the Hatari trace shows registers 11, 12 and 13 written by nothing but the driver's own 14-register
reset, always as 0. Both halves are checkable, so check both: the value in the image, and the fact
that nothing else on a real boot writes it.

→ Naming everything else: [`methodology.md`](methodology.md).