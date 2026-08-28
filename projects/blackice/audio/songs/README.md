# BLACK ICE — the score and the cues

The game's own music and sound effects, authored as two Python files and compiled by the audio
engine's tools into the blobs the driver reads. Nothing here is a new format or a new player: the
score is `mk_song.py`'s format and the cues are `mk_samples.py`'s bank, so `ym_music.c` and
`dma_sfx.c` are untouched apart from **one new entry point** (§6).

```
blackice.py       five songs + the ten YM fallback macros -> blackice_song.c/.h, blackice_sfx_ids.h
blackice_sfx.py   the ten DMA samples, synthesized        -> blackice_sfx_bank.c/.h
```

Both are built by the parent `Makefile`; `make verify-blackice` runs `BICETEST.PRG` in Hatari and
proves them. `make` builds both harnesses, `make clean && make verify` is the demo's acceptance
test and `make clean && make verify-blackice` is this one's.

---

## 1. The musical design

**Key: A Phrygian** — A, B♭, C, D, E, F, G. One interval in that scale does the whole job: the
**lowered second**, B♭ against A. It will not resolve, it is a semitone from the root, and putting
it in a bass line is the sound of something being wrong with the floor. That is the ICE.

The design's colour split is the score's harmonic split:

| DESIGN.md | the music |
|---|---|
| cyan infrastructure | the `arp` instrument — a clean **minor triad** `[0, 3, 7]`, one note per frame |
| magenta ICE | the `ice` instrument — **root, ♭2, fifth** `[0, 1, 7]`, the same machinery gone wrong |
| the trace meter | the **tempo**, and nothing else (§2) |

**Motif.** The bass is a mechanical root pulse — the root on four of every eight rows with its
octave answering on the last — and the melody is a Phrygian tetrachord walked down: A – G – F – E,
answered by C – B♭ – A. `ice_a` and `ice_b` are the same shapes with B♭ under them instead of A.
Nothing modulates and nothing resolves; the loop returns to where it started, which is what a
sector you are still inside sounds like.

**Why it fits.** 1987-as-imagined-in-1987 means a square-wave bass on the beat, an arpeggiated
chord standing in for a third voice, and drums made of the noise generator — the three things a
YM2149 can do at once. The three channels are used exactly as DESIGN.md §16 assigns them: **A =
bass line, B = arpeggio/lead, C = percussion**, which is also the channel an SFX steals, so a cue
silences the drums and never the tune.

**The percussion grid is unbroken.** Every row of every score pattern carries a hit — kick, snare,
or the hat that fills the rest. That is a musical choice (a relentless 8th-note machine pulse) and
a measurement one: it puts a spectral line in the recording's amplitude envelope at exactly the row
rate, which is how the verifier reads the tempo back off the audio (§7).

---

## 2. Tempo per trace band

DESIGN.md §16: *"the tempo **is** the trace meter"* and *"tempo change is a driver counter, not a
new module."* So the four bands are **one song blob played at four speeds**, not four blobs.

| Band | Trace | Speed (frames/row) | BPM | DESIGN.md asks | Loop length |
|---|---|--:|--:|--:|--:|
| 0 | 0–25% | 11 | **136.4** | 140 | 84.5 s |
| 1 | 25–50% | 10 | **150.0** | 152 | 76.8 s |
| 2 | 50–75% | 9 | **166.7** | 168 | 69.1 s |
| 3 | 75–100% | 8 | **187.5** | 184 | 61.4 s |
| — | 100% exfil | 7 | **214.3** | 200 | (own song) |

**Why not the round numbers.** A row lasts a whole number of 50 Hz frames, so at two rows to the
beat only `BPM = 1500 / speed` exists. There is nothing between 136.4 and 150. The worst deviation
is band 0's **2.6%**; every other is under 2%, and the step-to-step escalation (+10%, +11%, +12.5%)
is steeper than the design's own (+8.6%, +10.5%, +9.5%), which is the property the meter is for.

The loop is **60–90 s at every tempo the meter can ask for**: 84.5 s at band 0 down to 61.4 s at
band 3.

---

## 3. The songs

| Symbol | Bytes | Length | Speed | Patterns / sequence |
|---|--:|--:|--:|---|
| `blackice_title` | 662 | 30.7 s | 12 | 3 / 4 |
| `blackice_score` | 2,154 | 84.5 s @ band 0 | 11 (switched) | 8 / 12 |
| `blackice_death` | 264 | 2.9 s | 6 | 1 / 1 |
| `blackice_clear` | 312 | 3.8 s | 6 | 1 / 1 |
| `blackice_exfil` | 586 | 2.2 s | 7 | 1 / 1 |
| **total** | **3,978** | | | budget 8,192 |

- **`blackice_title`** — colder and sparser: a sustained drone, one slow line over it with a shallow
  vibrato, and a tick every four rows instead of a kit. Notes are held four rows (0.96 s), so it is
  also the window the verifier measures pitch in.
- **`blackice_score`** — `boot → boot2 → riff_a → riff_b → ice_a → riff_a → riff_b → ice_b → drop →
  riff_a → hammer → riff_b`, then loops. `boot` is the machine coming up (bass and grid only);
  `drop` takes the melody away but **not** the grid — the clock is still running; `hammer` is the
  peak, bass on every row under the ICE chord.
- **`blackice_death`** — the bass falls a tritone (A → D♯ → B♭) into a noise crash.
- **`blackice_clear`** — the one major chord in the whole score `[0, 4, 7]`, and the only place the
  ♭2 is absent.
- **`blackice_exfil`** — DESIGN.md §16 at 100%: *"one 200 BPM pulse, no melody."* There is no
  melody channel at all. This is the trace meter with the music taken away from it. Note the
  channel assignment is deliberately **not** the score's: the clock sits on **B** and **C is left
  empty**, because C is the channel an SFX steals and the cues firing at 100% are the trace alarm
  and the 1.2 s exfil siren. Everywhere else the stolen channel is the drums; here the drums are
  the whole track, and leaving them on C would have the siren silence the thing it is announcing.

**The two stings loop**, because every song in this format does. The game is expected to call
`ym_music_stop()` (or bind the next song) after the sting's length has elapsed — 2.9 s and 3.8 s.

**`blackice_title`, `blackice_death` and `blackice_clear` carry no SFX macro table.** On the YM-only
path `ym_music_sfx_play` therefore refuses every cue while one of those three is bound — no sound
effects on the title screen or under a sting. That is intended (no design cue fires in those
states), but it is a silent refusal, so a cue added to any of them needs the macros added too.

---

## 4. The ten cues

DESIGN.md §16's table verbatim — the lengths and the priorities are the design's, not choices made
here. `blackice_sfx.py` synthesizes the DMA sample and `blackice.py` carries the YM stand-in for
the same id, so **index N is the same event on both paths**.

| id | Event | Length | Pri | DMA sample | YM macro (plain ST) |
|--:|---|--:|--:|---|---|
| 0 | `SFX_BUSTER_SHOT` | 0.10 s | 1 | ring-modulated zap 2400→520 Hz + click | 5-frame noise burst, falling |
| 1 | `SFX_SPIKE_SHOT` | 0.35 s | 2 | ring mod 1500→300 Hz × 430 Hz, metallic | `[0,7,12]` arpeggio + noise, falling |
| 2 | `SFX_WATCHDOG_SNARL` | 0.30 s | 1 | two detuned glides beating, 28 Hz growl | descending square sweep + vibrato |
| 3 | `SFX_SENTRY_CHARGE` | 0.45 s | 2 | 190→1500 Hz whine, swelling, then a snap | rising pitch under a ramp envelope |
| 4 | `SFX_GATE_OPEN` | 0.55 s | 2 | servo groan + scrape swell + a clunk | rising sweep + noise |
| 5 | `SFX_TOKEN_GRAB` | 0.25 s | 2 | three rising blips G5–D6–G6 with a fifth | `[0,7,12,19]` shimmer |
| 6 | `SFX_TRACE_ALARM` | 0.90 s | 3 | two-tone 880/660 alarm, sagging, over a hum | `[0,0,0,5,5,5]` pulsed envelope |
| 7 | `SFX_PLAYER_HIT` | 0.30 s | 3 | crack + a 220→65 Hz body thud + ring bite | noise hit, falling fast |
| 8 | `SFX_ENEMY_DISSOLVE` | 0.40 s | 2 | ring mod 950→110 Hz crossfading into static | falling `[0,-5,-12]` + noise |
| 9 | `SFX_EXFIL_SIREN` | 1.20 s | 3 | a real siren: 520↔1150 Hz, 2.5 wails, wind | deep vibrato wail, pulsed |
| | **total** | **4.80 s** | | **60,176 B** (budget 102,400; design books 87,808) | |

The lengths and priorities in that table live in exactly one place — `blackice.py`'s
`SFX_CATALOGUE`. `blackice_sfx.py` imports it to size and order the samples, and
`blackice_sfx_ids.h` is generated from it, so "index N is the same event on both paths" is a
property of the build rather than a promise in two docstrings.

All ten are ramped to zero over their last 4 ms. The DMA stops dead at the end of a frame, so a
sample ending mid-waveform is a step to silence — an audible click, worst on the loudest cues
(before the fade, `sentry_charge` ended at 30% of full scale).

**The priority rule** is `dma_sfx.c`'s and `ym_music.c`'s, unchanged: a request of **higher or
equal** priority preempts the playing one; a strictly lower one is **dropped, never queued**. Which
is why the Buster is priority 1 and 0.10 s long — at its 0.20 s rate of fire the channel is idle
half the time, and a kill (2) or a token (2) preempts an in-flight shot outright.

Three cues in DESIGN.md's thirteen — gate close, door refusal tone, throttle change — are **not
here**: the brief asked for ten. They fit in the remaining budget (0.65 s, ~8 KB) whenever they are
wanted.

---

## 5. How the game calls it

```c
#include "blackice_song.h"        /* blackice_title/score/death/clear/exfil, BLACKICE_BAND_SPEED */
#include "blackice_sfx_bank.h"    /* blackice_sfx_bank                                           */
#include "blackice_sfx_ids.h"     /* SFX_*, blackice_sfx_priority[]                              */

/* once, in supervisor */
dma_sfx_init(blackice_sfx_bank, BLACKICE_SFX_BANK_BYTES);   /* 0 on a plain ST, and stays 0 */

/* on a state change */
ym_music_init(blackice_title, BLACKICE_TITLE_BYTES); ym_music_start();  /* attract screen   */
ym_music_init(blackice_score, BLACKICE_SCORE_BYTES); ym_music_start();  /* entering a sector */

/* on a trace threshold — the loop does NOT restart */
ym_music_set_speed(BLACKICE_BAND_SPEED[band]);    /* band = 0..3                           */

/* once per VBL, from the _vblqueue slot */
ym_music_tick();

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
iris/charge → 3. A gate or door opens → 4. Token picked up → 5. The trace crosses 25/50/75/100% →
6 (fire it on the same frame the palette and the tempo change). Player takes damage → 7. An enemy
dissolves → 8. Exfil begins, and once per wave after → 9.

**Route on the hardware, never on the answer.** `dma_sfx_available()` is a question about the
machine; `dma_sfx_play` returning 0 on an STE means a higher-priority sample is still playing, and
falling back to the YM there would steal a music channel to play the sound the priority just said
to drop.

---

## 6. The one API that was missing

The format has a tempo field but no way to change it while a song plays — `ym_music_init` read it
once into `song_speed` and nothing else touched it. Four bands would therefore have meant four
copies of the same 1.5 KB of patterns to express one 16-bit field, which is exactly what DESIGN.md
§16 says not to do. So `ym_music.c` gained **one function**, and nothing else changed:

```c
/* Change the tempo of the song that is already playing, WITHOUT restarting it. A 0 is ignored. */
void ym_music_set_speed(uint16_t frames_per_row);
```

It costs nothing per frame (it is not on the tick's path), writes no hardware, and the row in
progress finishes at the old rate. The four-band escalation is four calls to it.

---

## 7. What is measured

`make verify-blackice` — `BICETEST.PRG` on an STE under Hatari's EmuTOS, 2,600 frames (52 s): the
title theme alone, the score walked through all four band tempi, all ten cues fired, the priority
probe, then the death, clear and exfil songs. Then the same .PRG on a plain ST with TOS 1.04.

**20 checks, all PASS** — the demo harness's 19, plus the one this material made possible:

- **trace bands change the tempo** — 4/4. The recording's own amplitude envelope is scored against
  all four candidate row rates and has to pick its own — and the winner also has to BE that band's
  rate, not merely the closest of the four. Measured 4.543 / 5.009 / 5.530 / 6.229 rows/s against
  4.552 / 5.007 / 5.563 / 6.258 expected (errors 0.19 / 0.05 / 0.60 / 0.47%), winning by
  2.09× / 3.37× / 3.27× / 4.64× over the runner-up. **This is the only surface that can catch a tempo switch that did not
  happen**: `ym_music_set_speed` returns nothing, and the driver publishes all eleven PSG registers
  every frame at every tempo, so neither the ledger nor the register trace changes at all.
- **YM notes are on pitch** — 18/18 title-theme notes within 4% (largest error **0.68%**), across
  the drone and the lead.
- **DMA samples identified** — 10/10 cross-correlated against the bytes `blackice_sfx.py` packed,
  correlations **0.479–0.910**, peaks **9.2×–56.6×** the background correlation of the same sample
  against the surrounding music, all within 12 ms of the frame they were fired on.
- **plain-ST fallback** — the same .PRG, no `_MCH` STE, bank refused, **12 SFX out of the YM**, no
  `$ffff89xx` byte written, 2,600 frames, the priority refusal held.
- **tick within budget** — **2,882 cycles/frame** (360 µs, 1.8% of a 160,000-cycle frame) against
  the 3,000 budget, measured with the *score* bound at band 3's speed: three sounding channels, an
  arpeggio, a vibrato and the most row steps, which is the worst case the game ever pays. (The
  demo tune measures 2,942 on the same driver.)

The demo harness is untouched and still **19/19** with byte-identical numbers (`AUDIOTEST.PRG` is
still 42,206 bytes, and its tick still measures 2,942 cycles).

---

## 8. What is not proven

- **Real hardware.** Nothing here has run on an STE — see `../REPORT.md` §5, which applies
  unchanged (the LMC1992 encoding, the MicroWire poll, the DMA play bit).
- **A 60 Hz machine.** The tempo table above assumes a 50 Hz vblank. On the ST fallback run the
  whole score plays 20% fast, which makes band 0 sound like band 2. If the game must sound the same
  on both, `BAND_SPEEDS` needs a rate divisor — a game decision, not a driver one.
- **Nobody has listened to it.** `out/audio-blackice.wav` is 69 s of the real thing and every claim
  above is a measurement, not a hearing.
- **The samples are synthesized.** `python3 songs/blackice_sfx.py --wav-dir DIR` is the door
  recorded versions walk in through, and it lands the same bytes in the same slots; it has only
  been run against files this repo does not have.
- **The score has not been playtested against the trace meter.** Whether band 0 → band 3 *feels*
  like escalation over a three-minute sector is a playtest question, and the only thing measured
  here is that the tempo really changes.
