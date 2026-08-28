# Audio engine — YM2149 music + STE DMA samples

A self-contained audio module for the STE game, built and proven headless in Hatari. Nothing here
knows anything about the game: two modules with pointer-taking APIs, two Python tools that author
their data, one test .PRG, one verifier.

```
ym_music.c/.h   ym_psg.S/.h     3-voice YM2149 replayer, one tick per VBL, software envelopes
dma_sfx.c/.h                    STE DMA one-shot sample voice, 8-bit signed mono @ 12.5 kHz
mk_song.py                      song description -> binary blob + song_data.c + ym_notes.h + sfx_ids.h
mk_samples.py                   WAVs (or synthesized placeholders) -> sample blob + sfx_bank.c
songs/blackice.py               THE GAME'S SCORE — five songs + ten YM macros (songs/README.md)
songs/blackice_sfx.py           THE GAME'S CUES  — ten DMA samples, synthesized
audiotest.c  audio_os.s         the harness: installs the tick, plays, measures, restores
verify.py                       runs it in Hatari, analyses the recorded audio + the register trace
profile_tick.py                 Hatari's CPU profiler, per symbol and per instruction
Makefile  tos.ld  mkprg.py      the m68k-elf build (tos.ld/mkprg.py copied from projects/wonderboy)
```

`make` builds two .PRGs out of one `audiotest.c`, selected by `-DBLACKICE_MODE`:

| .PRG | bytes | material | check |
|---|--:|---|---|
| `disk/AUDIOTEST.PRG` | 43,244 | the demo tune and six placeholder samples | `make verify` |
| `disk/BICETEST.PRG` | 69,891 | the BLACK ICE score and its ten cues | `make verify-blackice` |

Both pass every check they run — 19 for the demo, 20 for BLACK ICE (it adds the tempo check). The
demo's table is below and BLACK ICE's is in `songs/README.md` §7. Every
generated source AND every `out/*_meta.json` the verifier reads is a Make target, so
`make clean && make verify` from a fresh tree is this directory's acceptance test.

---

## 1. What was built

### The music driver

Three YM2149 voices stepped once per 50 Hz vblank. **Software envelopes only** — every amplitude
comes from a per-frame volume table written into PSG registers 8-10, and the hardware envelope
generator (registers 11-13) is never armed. Confirmed by the trace: only registers 0-10 are ever
written, 32,483 times over the run.

Per channel, per frame: volume table step (looping or one-shot), arpeggio table step, vibrato (a
16-entry sine on the period), linear pitch slide, and the tone/noise mixer bits. The three channels
share one noise generator; the last channel to ask for noise sets its period.

**Channel steal.** `ym_music_sfx_play(id)` takes channel C for a short instrument+note macro carrying
a priority. An equal or higher priority restarts the macro; a strictly lower one is refused while a
macro is sounding. The channel returns to the music when the macro's one-shot volume table runs out —
that is also what "the note ended" means for every instrument, so nothing extra had to be invented.
An SFX macro may therefore not use a LOOPING envelope: it would hold the channel for ever. All three
layers refuse one — `mk_song.py` will not emit it, `ym_music_init` will not accept a blob containing
it, `ym_music_sfx_play` will not play it.

The call itself is a REQUEST: it stores one aligned word and the tick performs it, so the whole
channel update belongs to the vblank and a caller cannot be interrupted half way through one. That
is what makes it safe to fire an SFX from the main loop, and it costs no interrupt mask — which
would be a privileged instruction in a routine that has to be callable from user mode. The sound
starts on the next tick, within 20 ms; the return value is still decided at the call, because it is
what a caller routes on.

### The DMA sample voice

One voice, no CPU mixing: set the frame start/end, set mode `$ffff8921` = mono + rate code 01
(12,517 Hz), set the play bit in `$ffff8901`. A play costs 8 register stores. The play bit clears
itself at the end of a one-shot, which is what `dma_sfx_busy()` reads for the priority decision.

**Machine detection** is the `_MCH` cookie via `$5a0`, and no bus-error probe. The cookie jar arrived
with TOS 1.06, which is the oldest ROM any STE shipped with (and EmuTOS always builds one), so "no
jar" cannot be an STE — which means no exception vector has to be installed and taken back. On a
plain ST every entry point refuses and **not one `$ffff89xx` byte is written**; the caller routes to
the YM macro instead.

### The VBL hook: `_vblqueue` ($456), not vector $70

TOS's own level-4 handler reloads the shifter's screen base from `_v_bas_ad`, runs the cursor and
mouse timers, honours `_vblsem` and counts `_frclock`. Taking $70 means either reproducing that or
breaking it, and a chained handler has to get its register save, its interrupt-priority state and the
hand-off order right — three chances to introduce a fault that only shows on one TOS. The queue is
the hook TOS publishes for exactly this: one longword to write and one to put back, our routine runs
*after* the housekeeping, in supervisor mode (which the PSG and the DMA registers need), and it does
not run while `_vblsem` says the OS is inside a critical section. The install scans for a free slot
and refuses loudly if there is none; the run took slot 1 and gave it back.

---

## 2. The song format

Big-endian, byte-addressed, word-aligned. `mk_song.py`'s docstring is the normative spec; this is
the shape.

```
header, 20 bytes
   0  'YMS1'                         12  u16 offset of the order (one pattern index per byte)
   4  u16 frames per row (tempo)     14  u16 offset of the pattern offset table
   6  u8  rows per pattern           16  u16 offset of the instrument offset table
   7  u8  order length               18  u16 offset of the SFX macro table
   8  u8  pattern count
   9  u8  instrument count       pattern:  rows x 3 x (note byte, instrument byte), channels A,B,C
  10  u8  sfx count                       note 0 = nothing, 1 = note off, n>=2 = semitone n-2
  11  u8  reserved                        instrument 0 = keep the channel's last, n>=1 = the nth

instrument, 10-byte head then two tables       sfx macro, 4 bytes
   0  u8  flags: 1 tone, 2 noise, 4 vol loops     0  u8 instrument (1-based)
   1  u8  volume table length  (= the envelope)   1  u8 semitone index
   2  u8  volume loop point                       2  u8 priority (>= 1)
   3  u8  arpeggio length (0 = none; it loops)    3  u8 reserved
   4  u8  noise period 0..31
   5  u8  vibrato depth (period units)
   6  u8  vibrato speed (0 = off)
   8  s16 pitch slide, period units per frame (+ = pitch falls)
  10      u8 volume[len] (0..15), then s8 arpeggio[len] (semitone offsets)
```

A **non-looping volume table is also the note's length**: when it runs out the driver releases the
channel. That one rule is how percussion ends itself and how a stolen SFX channel is handed back.

**The demo tune**: 1,892 bytes (budget 4,096) — 8 patterns of 32 rows, a 16-entry sequence, 12
instruments, 6 SFX macros. 3,072 frames = **61.4 s** at 50 Hz, 6 frames/row. D minor, dark: a
root-and-octave bass pulse, a vibrato lead that becomes an arpeggiated triad in the tense section,
and noise percussion on channel C — the channel an SFX steals, so a hit silences the drums and
nothing else.

**The sample bank**: 36,110 bytes (budget 102,400) — 6 procedurally synthesized placeholders,
2.88 s total at 12,517 Hz: gunshot 0.32 s, door 0.90 s, pickup 0.30 s, enemy_hit 0.16 s,
player_hurt 0.45 s, enemy_death 0.75 s. `mk_samples.py --wav-dir DIR` builds the same blob from
recorded WAVs (any rate, 8- or 16-bit, mono or stereo) when they exist.

---

## 3. The measured tick cost

**2,962 CPU cycles per frame** on the demo tune and **2,922** on the BLACK ICE score at its fastest
trace band, against the 3,000 budget. That is 370 µs, or **1.9% of a 160,000-cycle frame**.

Measured by the .PRG itself: two loops timed against the 200 Hz counter at `$4ba`, one empty and one
calling `ym_music_tick`, each about half a second long so TOS's own vblank and timer handlers inflate
both by the same share of elapsed time and subtract out. The host does the arithmetic
(`verify.py:tick_cycles`); the .PRG only counts, so it needs no 32-bit divide. Corroborated by
Hatari's CPU profiler over the same run (`profile_tick.py`): `ym_music_tick` called from the vblank
costs 2,841 inclusive cycles on the demo and 2,779 on the score, and the whole per-frame
`audio_vbl_entry` — register save, tick, SFX scheduling — costs 3,058.

Getting there took four changes, all measured with `profile_tick.py --addresses`:

| change | cycles |
|---|---|
| first working build | ~3,880 |
| dropped the register-image clear (GCC turned an 11-byte clear into a byte loop) | −308 |
| the per-frame decision left `YmChannel` for a local struct (5 stores + 5 reloads per channel) | −~250 |
| the pitch-slide field read as an aligned word instead of two bytes | −~150 |
| the eleven hardware writes moved to `ym_psg.S` | −~130 |
| the SFX request became a pending word the tick performs (review item 6) | +20 |
| **final** | **2,962** |

`ym_psg.S` is the only assembly in the driver and it exists for one measured reason. In C, GCC folds
the chip address into every store — `move.b d16(a0),d1` / `move.b #n,$ffff8800.w` /
`move.b d1,$ffff8802.w` = 40 cycles a register. Holding the chip in an address register and walking
the image with a post-increment — `move.b #n,(a0)` / `move.b (a1)+,2(a0)` = 28 — is not expressible
in C, because the pointer is a compile-time constant and the compiler always prefers the absolute
form. The unroll is a `.rept` over `PSG_REG_COUNT` from `ym_psg.h`, which the C includes too, so the
count that sizes the image and the count that writes it are one definition.

The publish holds IPL 7 for its eleven writes (~310 cycles, 39 µs). A PSG access is a select store
then a data store, and TOS's floppy and keyboard code drive port A through the same two addresses
from a level-6 handler, which is live inside a level-4 vblank.

---

## 4. Verification in Hatari

`make verify` — `--machine ste`, Hatari's bundled EmuTOS (`--country uk`, which is what makes it come
up in 50 Hz PAL), `--memsize 1`, GEMDOS drive, `--auto C:\AUDIOTEST.PRG`. Audio recorded with
`--sound 44100 --disable-video on --avirecord`; both chips traced with `--trace psg_write,dmasound`.
Then a second run of the *same* .PRG on `--machine st` with TOS 1.04.

```
check                               result  detail
machine is an STE                   PASS    _MCH cookie says STE-class
songs accepted                      PASS    1 song(s), 1892 bytes: demo_song 61.4 s
sample bank accepted                PASS    6 samples, 36110 bytes
vblank tick installed               PASS    _vblqueue slot 1
frames run                          PASS    950 of 950
vblank rate is PAL                  PASS    50.09 Hz measured over 3793 200 Hz ticks
tick within budget                  PASS    2962 cycles/frame against a 3000 budget (370 us, 1.9% of a 160k frame)
every SFX request answered          PASS    15 requests (12 in the rotation, 3 in the priority probe), 14 on the DMA, 0 on the YM, 1 refused
SFX took the DMA path               PASS    14 DMA starts on an STE
priority refuses the quieter claim  PASS    the claim started=1, then a LOWER priority started=0, then an equal/higher one started=1
audio recorded                      PASS    1800 chunks, 35.9 s at 44100 Hz -> out/audio.wav
run is not silent                   PASS    RMS 5604 of 32767 over the 950-frame window
music is continuous                 PASS    0.0% of 20 ms blocks silent (budget 2%)
YM notes are on pitch               PASS    21/21 sounding notes peak within 4% of the song's own frequency
DMA samples identified              PASS    12/12 match the packed bytes at the frame they were fired
PSG traffic is ours and bounded     PASS    registers [0..10] written 32483 times; envelope regs 11-13 never touched
DMA control writes in order         PASS    30 control writes, 14 of them a start
LMC1992 routed and turned up        PASS    mixing=1, master=40, left=20, right=20, treble=6, bass=6
plain-ST fallback                   PASS    no _MCH STE, bank refused, 14 SFX on the YM, 0 on the DMA, 950 frames
```

### The WAV numbers

Hatari's recording is extracted from the AVI's PCM chunks and written as `out/audio.wav` (35.9 s,
44,100 Hz stereo). Over the 950-frame demo window: **RMS 5,604 of 32,767**, and **0.0%** of 20 ms
blocks silent — the tune plays without a gap from the first note to the teardown.

**Pitch.** Each sustained tone note in the music-only window (frames 1-299, before any SFX) is
FFT'd over 180 ms and the peak near its expected frequency is interpolated across its neighbours.
21 of 21 land within 4%; in fact the largest error is **0.62%** and the median is **0.21%**:

```
frame  ch  instrument   expected     peak    err%   peak/median
    0   0  bass            73.4     73.3   0.15         362
   24   0  bass           146.9    147.0   0.10         431
  240   1  lead           293.4    292.3   0.38         121
  264   1  lead           349.2    347.3   0.52         149
  288   1  lead           329.8    327.8   0.62         146
```

Notes whose fundamental gets fewer than 12 periods inside the window (the 58 Hz bass) are not
checked: at 180 ms the FFT bin is 9% of that note, so the measurement could not tell 4% either way.

**Samples.** Each fired SFX is **cross-correlated against the very bytes `mk_samples.py` packed**,
not merely looked at for energy — energy appears whenever anything is loud, whereas a correlation
spike at one offset says *that* sound and no other came out of the DMA at that frame. The gate is
the ratio of the peak to the background correlation of the same sample against the surrounding
music, because a 0.16 s burst of filtered noise under a full arrangement correlates at 0.3 however
perfectly it played while a tonal sample reaches 0.8.

```
frame  id  name          correlation  peak/background  offset ms
  300   0  gunshot             0.618        18.4           0.0
  350   1  door                0.548         7.8           1.0
  400   2  pickup              0.738        36.0           1.6
  450   3  enemy_hit           0.432        10.5           2.4
  500   4  player_hurt         0.626        21.9           3.1
  550   5  enemy_death         0.590        18.2           4.0
  600   0  gunshot             0.295        15.1           4.7
  650   1  door                0.422         4.6           2.5
  700   2  pickup              0.765        51.2           6.5
  750   3  enemy_hit           0.556        28.8           7.3
  800   4  player_hurt         0.733        15.3           7.9
  850   5  enemy_death         0.626        34.7           8.7
```

The offsets are the residual between Hatari's audio clock and its vblank clock: 8.7 ms of drift over
11 s, 0.08%. The first sample's offset anchors the timeline and every later one is held to it within
40 ms.

### The trace

`--trace psg_write,dmasound`, split by pc so EmuTOS's own writes (428 of them) are not counted as
ours. 30 DMA control writes: a stop before each of the 14 frame re-points, the 14 starts, the init
stop and the teardown stop — the frame registers are always set with the voice stopped. The MicroWire
route is confirmed by Hatari's own decode of the shifted words: `mixing=1, master volume=40, left=20,
right=20, treble=6, bass=6`.

### The defect this found, which no register check could have

`dma_sfx_init` originally wrote **3** to the LMC1992 mixer field, on the widely repeated reading that
the two bits mean `00 = -12 dB, 01 = PSG only, 10 = DMA only, 11 = PSG + DMA`. Every register write
looked right, the trace was clean, the samples played — **and the music was gone**. Building the file
four times and recording each says the field does not mean that:

| mixer value | all-silent audio frames, of 700 |
|---|---|
| 0 | 597 |
| **1** | **294** |
| 2 | 597 |
| 3 | 597 |

Only 1 lets the YM through, and EmuTOS's own boot writes 1 here for the same reason. Getting this
wrong is silent in every other way: the game would simply ship with no music. It is the one class of
bug that needs the *audio*, not the registers, as the surface.

---

## 5. The game's own material

`songs/` is BLACK ICE's score and cues, authored against the format above and proven by the second
harness. **`songs/README.md` is that work's report**; the two things it added to the engine are:

- **`ym_music_set_speed(frames_per_row)`** — the one API the format was missing. It changes the
  tempo of the song that is already playing without restarting it, which is how DESIGN.md §16's
  four trace bands are one 2,154-byte blob at four speeds (11/10/9/8 frames per row = 136.4 /
  150.0 / 166.7 / 187.5 BPM) instead of four copies of the same patterns. It is not on the tick's
  path and costs nothing per frame.
- **A tempo check that reads the audio.** `ym_music_set_speed` returns nothing, writes no hardware,
  and the driver publishes all eleven PSG registers on every frame at every tempo — so neither the
  ledger nor the register trace changes at all when a band switch happens or fails to. What changes
  is *when the rows land*. `verify.py:check_band_tempo` scores the recording's own amplitude
  envelope against all four candidate row rates and requires each band window to pick its own; it
  does, 4/4, by 2.09x to 4.64x over the runner-up. This is the same class of defect as the LMC1992
  mixer bug in §4: correct everywhere except in the sound.

---

## 6. What is unverified

- **Real hardware.** Nothing here has run on an STE. Specifically: the LMC1992 command encoding and
  the mixer value above are Hatari's model plus EmuTOS's corroboration, not a measurement on the
  chip; the MicroWire completion poll (mask register read back to `$07ff`, bounded at 1,000 spins) is
  Hatari's rotation model; and the DMA play bit clearing itself at the end of a one-shot — which the
  priority logic reads — is Hatari's behaviour. All three are the kind of thing this workspace has
  already been bitten by (`docs`: hardware reads are invisible to the differential).
- **The `_MCH`-only detection** on a machine with no cookie jar. The argument (no jar ⇒ not an STE)
  is sound but is only exercised here on TOS 1.04, where `$5a0` happened to be readable. A TOS that
  left junk at `$5a0` would be dereferenced. If real iron ever disagrees, the fix is the bus-error
  probe the brief allows, not a wider cookie search.
- **A 60 Hz machine.** The driver is vblank-rate agnostic — it is the *tempo* that assumes 50 Hz. On
  the ST fallback run (TOS 1.04 US, 60 Hz) the tune simply plays 20% fast. If the game must sound the
  same on both, the tempo needs a rate divisor; that is a game decision, not a driver one.
- **The samples are placeholders.** They are synthesized, not recorded. `--wav-dir` is the door the
  real ones walk in through and it lands the same bytes in the same slots, but it has only been run
  against files this repo does not have. That path now **anti-aliases before it decimates** — a
  127-tap windowed sinc at 0.45 of the output rate, applied at the source rate, and only when the
  source is faster than 12,517 Hz. Without it everything above 6.25 kHz folded back down into the
  sample as a phantom tone, which is the failure mode that sounds like a bad recording rather than
  like a broken tool. It is measured only against a synthetic 9 kHz probe tone (which folds to
  3,515 Hz: magnitude 840 unfiltered, 0.2 filtered — about 72 dB down); **on real recordings the WAV
  path is still unexercised**, and the placeholders cannot exercise it because they are generated at
  the target rate and have nothing up there to fold.
- **Sustained SFX on a stolen channel.** When a YM macro releases channel C, the music resumes there
  at the next row that carries a note, so a long held note that was interrupted does not come back.
  That is the classic behaviour and it is deliberate; it has not been evaluated musically.
- **`out/audio.wav` has not been listened to by a human.** Every claim above is a measurement.

---

## 7. How the game calls it

```c
ym_music_init(demo_song, DEMO_SONG_BYTES);   /* once, in supervisor: validates the whole blob      */
dma_sfx_init(sfx_bank, SFX_BANK_BYTES);      /* once: 0 on a plain ST, and then it stays 0         */
ym_music_start();                            /* rewind and play                                    */
/* once per VBL, from the _vblqueue slot */ ym_music_tick();
/* on an event, from anywhere */ if (dma_sfx_available()) dma_sfx_play(SFX_GUNSHOT, sfx_priority[SFX_GUNSHOT]); else ym_music_sfx_play(SFX_GUNSHOT);
```

The last line is the whole platform story and `audiotest.c:sfx_fire` is its named form. **Route on the
hardware, never on the answer**: falling back to the YM whenever `dma_sfx_play` returns 0 looks like
robustness and is the opposite — on an STE a 0 means a higher-priority sample is still playing, and
the "fallback" would then steal a music channel to play the very sound the priority just said to
drop. `dma_sfx_available()` answers a question about the *machine*, which is why it is the one that
decides.

Both `*_init` calls take the blob's length beside it, and the generators emit that length as a macro
next to the array, so there is no number to keep in step by hand. The length is not decoration: it
is what the drivers walk the whole structure against once, which is what earns the per-frame tick and
the DMA play path the right to do no checking at all.

Teardown is `ym_music_stop(); dma_sfx_stop();` plus putting the vblank slot back — which leaves the
PSG with all three generators off and all three volumes 0, and the DMA stopped, which is a state TOS
is happy to inherit.
