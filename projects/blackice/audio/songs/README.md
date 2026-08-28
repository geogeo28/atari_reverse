# BLACK ICE — the score, the cues and the drum lane

The game's own music and sound effects, authored as two Python files and compiled by the audio
engine's tools into the blobs the driver reads.

```
blackice.py       five songs, ten YM macros, the drum lanes -> blackice_song.c/.h, blackice_sfx_ids.h
blackice_sfx.py   ten DMA cues + four drum-lane samples      -> blackice_sfx_bank.c/.h
```

`make` builds both harnesses, `make verify-blackice` proves this material in Hatari, and
**`make listen-blackice` records it to `out/audio-blackice.wav`** so you can hear it on the host.

---

## 1. What plays, and on what

**Four tracks on an STE, three on a plain ST.**

| track | what carries it | on a plain ST |
|---|---|---|
| A — bass | YM channel A | plays |
| B — chords / lead | YM channel B | plays |
| C — percussion | YM channel C (also the SFX steal channel) | plays |
| **D — drum lane** | **the STE's DMA sample voice** | **silently absent** |

The drum lane is new (§4). It costs no chip channel, so it is a fourth voice that is genuinely
additive — and because the YM still carries a full kit on channel C, the arrangement stands up
complete on a machine that has no DMA sound at all.

---

## 2. The musical design

**Key: A Phrygian** — A, B♭, C, D, E, F, G. One interval does the whole job: the **lowered
second**, B♭ against A. It will not resolve, it is a semitone from the root, and putting it in a
bass line is the sound of something being wrong with the floor. That is the ICE.

| DESIGN.md | the music |
|---|---|
| cyan infrastructure | `chord` — a **four-note minor chord** `[0, 3, 7, 12]`, one note per frame |
| magenta ICE | `chord_ice` — **root, ♭2, 5th, ♭6** `[0, 1, 7, 8]`: the same machinery gone wrong |
| the build's refusal to land | `chord_sus` — `[0, 5, 7, 12]`, hanging on the fourth |
| the trace meter | the **tempo**, and nothing else (§3) |

**One voice, four notes.** The YM has three channels; two are spoken for by the bass and the kit.
The third gets the entire harmony by playing it one note per frame — four notes at 50 Hz is a
12.5 Hz cycle, fast enough to hear as a chord rather than a run. Every chord in the score is one
`arpeggio` table on one voice, and every chord duration is a whole multiple of the 4-frame cycle,
so no chord change ever lands mid-arpeggio.

**The chord voice is planed; the bass is not.** A fixed shape moved onto every root emits notes A
Phrygian does not hold — `chord_ice` on G gives G♯ and D♯ — and that is the point: the ICE is a
machine running one pattern over whatever it is pointed at, and it does not care what key the
sector is in. The bass is the voice that does care, so intervals its shape *derives* are snapped
back into the scale (ties go downward, which is how the fifth above the E bar becomes B♭ instead of
the B natural that would turn the whole thing into A Aeolian). A root the pattern *writes* is never
snapped — the build climbs F, F♯, G deliberately.

**The bass is an octave line.** A shape per bar, one entry per row, as semitone offsets from that
bar's root — `BASS_DRIVE = (0, 0, 12, 0, 0, 12, 0, 7)` for the verse, `BASS_OCTAVE` for the chorus,
`BASS_ROLL` for the drop, `BASS_HOLD` for the intro and break. The bar's last eighth takes
`bass_drop`, a one-shot voice whose pitch **slides away underneath it**; it is the only slide in
the arrangement and it is what makes a bar end rather than stop.

**The kit is three voices on one channel.** A kick is a low tone with a fast pitch drop under a
7-frame decay; a snare is the noise generator with a short decay; a hat is three frames of the same
generator at its shortest period. Channel C carries a hit on **every row** — a relentless
eighth-note machine pulse, and also the spectral line at the row rate that `verify.py` reads the
trace band back off the recording with.

### The arrangement — 10 patterns, 28 in the sequence

| section | patterns | what changes |
|---|---|---|
| **intro** | `intro_a`, `intro_b` | bass + grid only, then the chord voice arrives |
| **A** | `verse_a`, `verse_b` | the main statement and its answer, walking the Phrygian tetrachord |
| **B** | `chorus_a`, `chorus_b` | B♭ takes the bass, the ICE chord, the kick doubles |
| **break** | `break` | everything thins to two strikes a bar and one held note |
| **build** | `build` | the bass climbs a semitone a bar into B♭, snare roll on the last bar |
| **drop** | `drop` | bass on every row, ICE chord every half-bar, kick on every other eighth |
| **turn** | `turn` | four bars that walk it back to the top |

```
intro_a intro_b | verse_a verse_b verse_a verse_b | chorus_a chorus_b | verse_a verse_b
break build drop drop | verse_a verse_b | chorus_a chorus_b chorus_a chorus_b
break build drop drop | verse_a verse_b turn turn
```

The drop arrives twice, from two different directions. At band 0 the sequence runs **197 s**; at
band 3, **143 s**.

---

## 3. Tempo per trace band

DESIGN.md §16: *"the tempo **is** the trace meter"*, *"tempo change is a driver counter, not a new
module."* The four bands are **one song blob played at four speeds**.

| Band | Trace | Speed (frames/row) | BPM | DESIGN.md asks | Sequence length |
|---|---|--:|--:|--:|--:|
| 0 | 0–25% | 11 | **136.4** | 140 | 197 s |
| 1 | 25–50% | 10 | **150.0** | 152 | 179 s |
| 2 | 50–75% | 9 | **166.7** | 168 | 161 s |
| 3 | 75–100% | 8 | **187.5** | 184 | 143 s |
| — | 100% exfil | 7 | **214.3** | 200 | (own song) |

A row lasts a whole number of 50 Hz frames, so at two rows to the beat only `BPM = 1500 / speed`
exists. Worst deviation is band 0's **2.6%**; the step-to-step escalation (+10%, +11%, +12.5%) is
steeper than the design's own (+8.6%, +10.5%, +9.5%), which is the property the meter is for.

---

## 4. The drum lane — the format change

**One byte per row, beside the three YM channels, naming a sample in the DMA bank.**

```
song header, 24 bytes ('YMS2')
   ...
   11  u8  drum sample limit — one past the highest bank index the lane names; 0 = no lane
   20  u16 offset of the drum lane offset table (one u16 per pattern); 0 = no lane
drum lane   one byte per row, in the pattern's own row order
            0 = no hit, n >= 1 = DMA bank sample index n - 1
```

`mk_song.py` takes it as two optional description keys — `drum_bank` (`{name: bank index}`) and
`drums` (`{pattern name: a token string of `rows` tokens}`). A pattern left out of `drums` still
gets a lane of silence, so the driver can index the lane table by pattern with no second test.

**The tick publishes; the platform plays.** `ym_music.c` knows nothing about `$ffff89xx`. On the
row step it stores the lane byte into one aligned word — the same trick as the pending SFX request,
and for the same reason — and the platform takes it:

```c
ym_music_tick();
hit = ym_music_take_drum_hit();
if (hit != YM_DRUM_NONE) { dma_sfx_play((uint8_t)hit, YM_DRUM_PRIORITY); }
```

That split is what makes the lane free on a plain ST: `dma_sfx_play` refuses, writes no register,
and the YM percussion channel plays on untouched. **It is on by default wherever
`dma_sfx_available()` is true** — there is no enable, because there is nothing to enable: the song
data is identical on both machines and the hardware decides.

**`YM_DRUM_PRIORITY` is 0 and every game cue is 1–3.** A cue always preempts a drum; a drum never
preempts a cue; a drum preempts a drum (equal priority restarts, so the lane can hit every row).
Measured over the whole verification run: **30 of 289 lane hits were refused** while a cue held the
voice, and every one of the 110 hits inside the cue-free drum window started.

### The four samples

| bank id | sample | length | bytes | what it is |
|--:|---|--:|--:|---|
| 10 | `kick` | 0.11 s | 1,378 | 400 → 52 Hz chirp, saturated, with a click |
| 11 | `snare` | 0.12 s | 1,502 | high-passed noise over a 190/285 Hz body |
| 12 | `hat` | 0.055 s | 688 | the top of a noise burst, corner near 3 kHz |
| 13 | `clap` | 0.13 s | 1,628 | three bursts 9 ms apart, then a tail |
| | **total** | 0.42 s | **5,196** | budget 20,480 |

**The kit is balanced against itself, which a bank of cues is not.** `mk_samples.to_signed_bytes`
peak-normalises every sample — right for one-off cues, which are never heard at once, and wrong for
four sounds that play together every row. `DRUM_GAINS` ducks the quieter voices after that
normalise (kick 1.0, snare 0.95, clap 0.9, hat 0.75). The hat is ducked less than a mixing desk
would: the YM percussion channel is playing its own hat underneath on the same row, and the
verifier has to be able to tell this one from a kick at the same instant.

**Every one is shorter than the shortest row it will ever play on** — band 3's row is 160 ms and
the exfil pulse's is 140 ms. The DMA is one voice: a drum that outlived its row would be cut by the
next hit, which stutters, smears the grid the tempo check reads, and leaves its own tail sitting
under the next drum. (Measured at 0.16 s: 50 of 110 hits landed in the wrong bin.)

**The kick's sweep starts at 400 Hz** for the same class of reason. The bass line lives at
87–220 Hz and strikes on every row; a kick that lingered in that register is a decaying tone in the
same band as a freshly struck bass note, and nothing downstream can tell them apart.

---

## 5. The songs

| Symbol | Bytes | Length | Speed | Patterns / sequence | Drum lane |
|---|--:|--:|--:|---|--:|
| `blackice_title` | 790 | 30.7 s | 12 | 3 / 4 | 32 hits |
| `blackice_score` | 2,946 | 197.1 s @ band 0 | 11 (switched) | 10 / 28 | 726 hits |
| `blackice_death` | 306 | 2.9 s | 6 | 1 / 1 | — |
| `blackice_clear` | 354 | 3.8 s | 6 | 1 / 1 | — |
| `blackice_exfil` | 608 | 2.2 s | 7 | 1 / 1 | 16 hits |
| **total** | **5,004** | | | | budget 12,288 |

- **`blackice_title`** — colder and sparser, but no longer thin: a drone with its octave answering,
  a chord voice that arrives only in the last section, and a tick on every row. Its lane has **no
  kick**: a 400 → 52 Hz chirp struck on a drone's own onset row puts foreign energy in the exact
  band `verify.py` reads that note's pitch out of (measured at 4.5% error on the F-2, against a 4%
  tolerance). Musically a cold attract screen does not want a kick either.
- **`blackice_death`** — the bass falls a tritone (A → D♯ → B♭) into a noise crash.
- **`blackice_clear`** — the one major chord in the whole score, and the only place the ♭2 is absent.
- **`blackice_exfil`** — DESIGN.md §16 at 100%: *"one 200 BPM pulse, no melody."* No melody channel
  at all, a hard four-on-the-floor in the lane, and the clock deliberately on **channel B** with
  **C left empty** — C is the channel an SFX steals, and the cues firing at 100% are the trace alarm
  and the 1.2 s exfil siren.

**The two stings loop**, because every song in this format does; the game calls `ym_music_stop()`
after 2.9 s and 3.8 s. **The title and the two stings carry no SFX macro table**, so on the YM-only
path `ym_music_sfx_play` refuses every cue while one of them is bound — intended, but silent.

---

## 6. The ten cues

DESIGN.md §16's table verbatim. `blackice.py`'s `SFX_CATALOGUE` is the only place the lengths and
priorities are written down; `blackice_sfx.py` imports it, so index N is the same event on both
paths by construction.

| id | Event | Length | Pri | DMA sample | YM macro (plain ST) |
|--:|---|--:|--:|---|---|
| 0 | `SFX_BUSTER_SHOT` | 0.10 s | 1 | ring-modulated zap 2400→520 Hz + click | 5-frame noise burst, falling |
| 1 | `SFX_SPIKE_SHOT` | 0.35 s | 2 | ring mod 1500→300 Hz × 430 Hz, metallic | `[0,7,12]` arpeggio + noise |
| 2 | `SFX_WATCHDOG_SNARL` | 0.30 s | 1 | two detuned glides beating, 28 Hz growl | descending square sweep |
| 3 | `SFX_SENTRY_CHARGE` | 0.45 s | 2 | 190→1500 Hz whine, swelling, then a snap | rising pitch under a ramp |
| 4 | `SFX_GATE_OPEN` | 0.55 s | 2 | servo groan + scrape swell + a clunk | rising sweep + noise |
| 5 | `SFX_TOKEN_GRAB` | 0.25 s | 2 | three rising blips G5–D6–G6 | `[0,7,12,19]` shimmer |
| 6 | `SFX_TRACE_ALARM` | 0.90 s | 3 | two-tone 880/660 alarm over a hum | `[0,0,0,5,5,5]` pulsed |
| 7 | `SFX_PLAYER_HIT` | 0.30 s | 3 | crack + a 220→65 Hz thud + ring bite | noise hit, falling fast |
| 8 | `SFX_ENEMY_DISSOLVE` | 0.40 s | 2 | ring mod 950→110 Hz into static | falling `[0,-5,-12]` + noise |
| 9 | `SFX_EXFIL_SIREN` | 1.20 s | 3 | a real siren: 520↔1150 Hz, 2.5 wails | deep vibrato wail, pulsed |
| | **cues** | **4.80 s** | | 60,088 B | |
| | **+ drum lane** | 0.42 s | 0 | 5,196 B | (none — the YM kit covers it) |
| | **bank** | 5.22 s | | **65,404 B** | budget 102,400 |

All fourteen are ramped to zero over their last 4 ms: the DMA stops dead at the end of a frame, so
a sample ending mid-waveform is a step to silence.

---

## 7. How the game calls it

```c
#include "blackice_song.h"        /* the five blobs, their _BYTES, BLACKICE_BAND_SPEED  */
#include "blackice_sfx_bank.h"    /* blackice_sfx_bank, BLACKICE_SFX_BANK_BYTES         */
#include "blackice_sfx_ids.h"     /* SFX_*, blackice_sfx_priority[], SFX_DRUM_*         */

/* once, in supervisor */
dma_sfx_init(blackice_sfx_bank, BLACKICE_SFX_BANK_BYTES);   /* 0 on a plain ST, and stays 0 */

/* on a state change */
ym_music_init(blackice_score, BLACKICE_SCORE_BYTES);  ym_music_start();

/* on a trace threshold — the loop does NOT restart */
ym_music_set_speed(BLACKICE_BAND_SPEED[band]);              /* band = 0..3 */

/* once per VBL, from the _vblqueue slot — THESE THREE LINES, IN THIS ORDER */
ym_music_tick();
hit = ym_music_take_drum_hit();
if (hit != YM_DRUM_NONE) { dma_sfx_play((uint8_t)hit, YM_DRUM_PRIORITY); }

/* on an event, from anywhere */
if (dma_sfx_available()) { dma_sfx_play(SFX_TOKEN_GRAB, blackice_sfx_priority[SFX_TOKEN_GRAB]); }
else                     { ym_music_sfx_play(SFX_TOKEN_GRAB); }
```

**Song per game state:**

| State | Song | Then |
|---|---|---|
| title / attract | `blackice_title` | loops |
| in a sector, trace 0–100% | `blackice_score` | `ym_music_set_speed(BLACKICE_BAND_SPEED[band])` at each threshold |
| trace hits 100% (exfil) | `blackice_exfil` | loops until the gate or the death path |
| player death | `blackice_death` | `ym_music_stop()` after 2.9 s |
| sector cleared | `blackice_clear` | `ym_music_stop()` after 3.8 s |

**SFX per event:** Buster fired → 0. Spike fired → 1. Watchdog enters ALERT → 2. Sentry begins its
charge → 3. A gate or door opens → 4. Token picked up → 5. The trace crosses 25/50/75/100% → 6.
Player takes damage → 7. An enemy dissolves → 8. Exfil begins → 9.

**Route on the hardware, never on the answer.** `dma_sfx_available()` is a question about the
machine; `dma_sfx_play` returning 0 on an STE means a higher-priority sample is still playing, and
falling back to the YM there would steal a music channel to play the sound the priority just
dropped.

---

## 8. What the platform layer must adopt

Three things, all in the per-frame audio path and the once-per-state-change path:

1. **The three-line VBL body above.** `ym_music_take_drum_hit()` must be called from the same
   vblank as `ym_music_tick()`, immediately after it: the take is a read then a clear, and a tick
   landing between the two would throw the hit away. Not calling it at all is safe — the lane
   simply never sounds — but then the STE gets three tracks, not four.
2. **`YM_DRUM_PRIORITY` (0) is reserved.** No game cue may be played at priority 0, or it will lose
   every argument with a hi-hat.
3. **The song format is now `'YMS2'`** — a 24-byte header, two new fields. `ym_music_init` refuses
   a `'YMS1'` blob outright. Every blob in this tree is a build product, so this costs a rebuild
   and nothing else; anything holding a pre-built blob must regenerate it.

---

## 9. What is measured

`make verify-blackice` — `BICETEST.PRG` on an STE under Hatari's EmuTOS: 3,700 frames (74 s) of the
title theme, the score walked through all four band tempi, a 20 s drum window at one tempo, all ten
cues, the priority probe, and the death, clear and exfil songs. Then the same .PRG on a plain ST
with TOS 1.04.

**24 checks, all PASS.** The ones this material added or changed:

- **drum lane identified** — of the 110 lane hits inside the 20 s window, **106 (96.4%)** are the
  sample the lane asked for: 36/36 kicks, 11/11 snares, 5/5 claps, 54/58 hats. The floor applies
  **per sample as well as overall**, because 58 of the 110 are hats and an aggregate floor says
  nothing about a rare one — relabelling all five claps would still score 95%.

  Each hit is scored against *every* lane sample and the strongest has to be the one the ledger
  says fired, so this is a classification, not a threshold. Two corrections make it a measurement
  of the lane rather than of the arrangement: the timeline is fitted first, as a straight line
  through the window's kicks (Hatari's audio and vblank clocks drift 0.08% apart, 16 ms across the
  window), and each reference is scored against **its own background** — what it reads on the rows
  the ledger says it did not play. Without that second correction the kick reference, a chirp
  through the bass's own register, reads ~0.45 on rows it never played and wins most of them.

  The negative control matters more than the number. Run the same .PRG on a plain ST — where
  `dma_sfx_play` refuses every hit and not one `$ffff89xx` byte is written, while the YM
  arrangement, the ledger and all 110 recorded hits are otherwise identical — and the same check
  scores **23.6%** (kick 14/36, hat 9/58, snare 3/11, clap **0/5**). That is the control that
  matters, because unlike shuffling the labels it leaves the correlation between a label and its
  musical position completely intact and removes only the drums.

- **the drum lane is on the row grid** — the fitted lag is **+6.2 ms** at the window's first hit
  and **+9.8 ms** at its last, against a 45 ms budget and a 160 ms row; every recorded hit is
  inside the window and a whole number of rows from the one before it. This check exists because
  the identification deliberately cannot answer *where*: the clock fit has an offset, and an offset
  absorbs any constant error. Measured before it existed, moving every hit **one whole row late
  scored 110/110**.
- **every drum hit reached the DMA** — 110 of 110 in the window. No cue fires there, so a refusal
  would be a defect.
- **a cue outranks the drum lane** — 30 of 289 lane hits over the whole run were refused while a
  cue held the voice. A lane that never lost an argument would mean `YM_DRUM_PRIORITY` was wrong.
- **DMA control writes in order** — the hardware trace's start count equals the cues plus the drum
  starts the .PRG counted, which is what says no start happened that neither path asked for.
- **plain-ST fallback** — the same .PRG, no `_MCH` STE, bank refused, 12 cues out of the YM,
  **289 lane hits published and 0 played**, no `$ffff89xx` byte written.
- **tick within budget** — **2,902 cycles/frame** (363 µs, 1.8% of a 160,000-cycle frame) against
  3,000, measured with the score bound at band 3's speed — the worst case the game ever pays, and
  80 cycles under the demo tune's 2,982 on the same driver. The lane costs the tick a byte load
  and a word store once per row; firing the hit is the platform's eight register stores, outside
  the measured tick and inside the same vblank.
- **YM notes are on pitch** — 22/22 title-theme notes within 4%. Arpeggiated instruments are
  excluded by the checker, because an arpeggio steps the pitch every frame and its written root is
  in the window for only its share of the chord.
- **trace bands change the tempo** — 4/4, unchanged.

The demo harness is untouched and still **19/19** (`AUDIOTEST.PRG` unchanged in behaviour; its blob
is now `'YMS2'` with an empty lane).

---

## 10. What is not proven

- **Real hardware.** Nothing here has run on an STE — `../REPORT.md` §6 applies unchanged.
- **A 60 Hz machine.** The tempo table assumes a 50 Hz vblank; on the ST fallback the whole score
  plays 20% fast, which makes band 0 sound like band 2.
- **The drum lane under load.** It is measured in a window where no cue fires. The priority rule is
  measured over the whole run, but "does it still groove while a firefight is going on" is a
  playtest question.
- **Nobody has listened to it.** `make listen-blackice` writes `out/audio-blackice.wav`; every
  claim above is a measurement.
- **The samples are synthesized.** `python3 songs/blackice_sfx.py --wav-dir DIR` is the door
  recorded versions walk in through.
