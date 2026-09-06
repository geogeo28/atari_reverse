# Bubble Ghost — asset survey

Bubble Ghost, ERE Informatique / Accolade, 1988, Atari ST. This covers the game's **data files** —
`GHOST.PRE`, `GHOST.DAT`, `GHOST.VOI`, `GHOST.DEM` — which were decoded without the code. The one
exception is the sample player: `GHOST.VOI`'s rate and length turned out to be unknowable from the
audio alone, and the numbers below come from `bin/GHOST.LOA`, read by the loader agent. `GHOST.PRG`,
the rest of `GHOST.LOA` and `DESKTOP.INF` belong to `notes/loader.md`, not here.

Everything is marked **CONFIRMED** (decoded and read back — a picture that reads, a waveform that
has structure, a field that stays in range over all 1,000 records) or **HYPOTHESIS** (consistent
with the bytes, not yet proved). The tools are
`projects/bubbleghost/tools/extract_gfx.py` and `.../extract_audio.py`; both write to
`projects/bubbleghost/out/assets/` (gitignored).

---

## The one graphics format: 32×32 tiles, palette last

**CONFIRMED.** `GHOST.PRE` and `GHOST.DAT` are the *same* format — a run of 32×32-pixel tiles
followed by a 32-byte `$0RGB` palette, with no header, no index table and no gap:

| file | bytes | = tiles × 512 | + palette |
|---|---:|---|---|
| `GHOST.PRE` | 30,752 | 60 × 512 = 30,720 | 32 |
| `GHOST.DAT` | 184,352 | 360 × 512 = 184,320 | 32 |

A tile is 512 bytes: **32 rows of 16 bytes**, each row being two word-interleaved groups — four
big-endian plane words for pixels 0–15, four more for pixels 16–31. That is the plain low-res ST
model of `tools/st_pixels.py` (`decode_planar(..., width=32, unit_bits=16, masked=False)`), just
applied to a 32-pixel-wide bitmap instead of a 320-pixel screen. Plane 0 is the index's LSB, and
the palette confirms it: entry 15 is `$0777` (white) in both files and the ghost comes out white.

### How the layout was found, and what was ruled out

Every "obvious" reading renders as striped noise, and each was rendered and looked at:

* 320×192 word-interleaved at a 160-byte row stride — noise
* 320×192 as four contiguous 7,680-byte planes — noise
* 320×192 byte-planar (`unit_bits=8`) — noise
* the palette read as a *header* (data at +32) — noise
* line-planar rows (40 bytes of plane 0, then plane 1, …) — noise
* widths 160 / 256 / 512 / 640, and 1-bit-per-pixel monochrome at several widths — noise

Both files are nonetheless *raw*: `GHOST.PRE` has byte entropy 5.27 and still zlib-compresses to
51%, `GHOST.DAT` 3.11 and 14%. Compressed data would not.

What located the tile was a **stride sweep**: extract the first plane word of every 16-byte group
and score, for each candidate stride, the mean Hamming distance between bytes that far apart. For
`GHOST.DAT` this picked out **64 bytes in plane-0 space = 512 bytes raw** against its neighbours
(0.83 vs 1.13/1.14 at ±2). 512 bytes with a 16-byte row is 32 rows: a 32×32 tile.

Then a **seam test** fixed the tile height: decode the whole file as one 32-pixel-wide column,
cut it into strips of every divisor height *h*, and score how often the last pixel column of one
strip equals the first column of the next. `h = 32` scored 0.515 against an *interior* horizontal
match of 0.520 — i.e. the seam at 32 rows is as continuous as the middle of the picture — while
the next best (h = 30) scored 0.401 and h = 192 only 0.185.

### `GHOST.PRE` — the title screen

**CONFIRMED.** The 60 tiles are the title picture in **row-major order, 10 across × 6 down =
320×192**, and it reads: the icicle **BUBBLE GHOST** logo, *by C.Andreani*, the ghost, the bubble,
the gargoyle head, and `Copyright 1988, ACCOLADE INC. TM` across the bottom. See
`out/assets/title.png`.

192 rows, not the ST's 200 — the picture is 8 scan lines short of a full low-res screen.

Palette (`out/assets/palette_title.txt`), in file order:
`0000 0121 0223 0334 0445 0556 0667 0770 0644 0704 0575 0465 0353 0242 0131 0777` — a black-to-white
ramp with a blue/purple cast, plus greens.

### `GHOST.DAT` — the game's tile bank

**CONFIRMED:** 360 tiles in the format above, and they render as coherent artwork
(`out/assets/dat_tiles.png`, in the file's own palette — the format is confirmed, so the
grey-ramp and title-palette sheets that found it are gone).

Palette (`out/assets/palette_dat.txt`):
`0000 0700 0256 0040 0050 0060 0237 0245 0000 0757 0771 0333 0444 0555 0666 0777` — red, sky blue,
three greens, pinks, yellow, a four-step grey ramp and white. One master palette covers ivy, sky,
brickwork and the HUD, so the whole bank shares it.

**HYPOTHESIS — what the index ranges hold.** The 20-column sheet layout is this tool's; the bands
below are read off the picture, and only the first three are backed by anything measurable.

| tiles | bytes | content |
|---|---|---|
| 0–46 | 0–24,063 | the ghost's animation frames — **objectively delimited**: these 47 tiles are the only ones that use *just* colours 0 and 15 |
| 47–49 | 24,064–25,599 | a three-frame sparkle burst (a bubble popping) |
| 50 | 25,600–26,111 | entirely colour 0 — an empty tile |
| 51–59 | 26,112–30,719 | nine bubble frames, the highlight rotating around the rim |
| ~60–~199 | ~30,720–~102,399 | room furniture: brick walls, framed pictures, candles, fans, pipes, valves, blue signs, arrows/spikes, plus the menu buttons (`Play Pinball Wizard`, `Play MEAN 18`, `Hard ball`, `Pinky`, `compu ON` / `compu OFF`) around tiles ~80–95 |
| ~200–~349 | ~102,400–~178,687 | more rooms, stone busts, the ivy maze, the outdoor ending scene (sky, cloud, grass, flowers), the `ERE` logo, and the message plates `HALF WAY` and `WELL DONE! THE BUBBLE THANKS YOU` |
| 350–359 | 178,688–184,319 | the status panel: exactly **ten** tiles = 320×32, carrying the BUBBLE GHOST logo, `ERE`, `SCORE:`, `HI-SCORE:`, `HALL:`, `BUBBLE:` and a red `BONUS` bar |

That last row supports a tidy reading of the whole screen — **HYPOTHESIS**: the game runs a 320×192
display of 10×6 tiles, the top 10×5 being the room and the bottom row being the HUD. It would
explain why the title picture is 192 rows too.

Nothing in either file marks transparency: there is no mask field (a masked group is five words
wide, which would not give a 512-byte tile). The ghost and bubble sit on colour 0, so the drawing
code presumably treats index 0 as transparent or builds a mask at run time — **HYPOTHESIS**.

---

## `GHOST.VOI` — the digitised "Welcome to Bubble Ghost" speech

**CONFIRMED — the container.** 30,100 bytes of raw **unsigned 8-bit PCM** centred on 128, with no
header, no offset table and no trailing palette. All 256 byte values occur; quiet passages sit on
127/128. WAV's own 8-bit format is unsigned with 128 as zero, so `extract_audio.py` copies the bytes
through untouched.

**CONFIRMED — it is ONE sample, played at 14,985 Hz.** The player is not in `GHOST.PRG` at all: it
is **`bin/GHOST.LOA`** (2,703 B, no reloc table, ABSFLAG set), a self-contained MFP Timer A routine.
Its header at text+2 is three longs — the sample address, the length `0x00007594` = **30,100 = the
whole of GHOST.VOI**, and a rate index — and it plays `[addr, addr+len)` as a single sample,
synchronously (Super, save the MFP registers, install `$134` as the Timer A vector, spin on a done
flag, restore, `rts`).

The rate comes out of the routine at text+0x15e:

```
andi.w #7,d0 ; lea table(pc),a0 ; lsl.w #1,d0 ; move.w (a0,d0.w),d0
move.b d0,$fffa19        ; Timer A control = low byte
lsr.w  #8,d0
move.b d0,$fffa1f        ; Timer A data   = high byte
```

with an 8-word table at text+0xa62: `0506 0505 0405 2901 1f01 0802 0106 0106`. The header's rate
index **3** selects `0x2901` → control 1 = prescaler ÷4, data `0x29` = 41. Against the MFP's
2.4576 MHz clock that is **2,457,600 / (4 × 41) = 14,985.37 Hz**, and the whole file is **2.009 s**.
The WAV header holds an integer, so the export is written at 14,985 Hz — 0.0024% low, inaudible.

**CONFIRMED that index 3 is what plays.** The LOA header carries it as shipped on disk, and
`GHOST.PRG`'s loader pokes only the sample-ADDRESS field at `+0x1e` before calling the routine — the
rate word is never patched (`notes/loader.md`).

**CONFIRMED — why the bytes are copied through unchanged.** There is no DAC and no DMA voice in
this: the Timer A handler reads one byte, biases it by `0x80`, and uses it to index a 256-entry
table at text+0x262 of (register, value) pairs written to **PSG registers 8/9/10** — the three
channel volumes. One sample byte becomes one volume triple, and across that table byte `0x00` is
about the loudest, `0xff` about the quietest and `0x7f`/`0x80` about the midpoint. Only the *trend*
is smooth — the PSG's volume steps are logarithmic, so the summed amplitude has small local
reversals (about ten in the first 70 byte values under a 3 dB-per-2-steps model) — but the trend is
what settles the reading: unsigned, centred on 128. The polarity is **not** normalised in the
export, since the table runs loud-to-quiet and inversion is inaudible; leaving it alone keeps the
WAV a byte-for-byte copy of the file.

**The gaps in it are pauses between words, not sound boundaries.** An amplitude envelope splits the
file into five bursts separated by gaps of 0.8–1.2 KB, with 1.4 KB of silence at the end — and an
earlier pass of this survey read those as five separate effects and exported them as five WAVs.
That was wrong: the LOA header's length field is the whole file. `out/assets/voi_envelope.png` plots
the waveform under its envelope, and the five bursts are the phrase's words.

| | offset | bytes | seconds | DC | peak dev | RMS |
|---|---:|---:|---:|---:|---:|---:|
| the whole phrase | 0 | 30,100 | 2.009 | −1.0 | 128 | 39.8 |

**The in-game sound effects are not here.** `GHOST.VOI` holds this one speech sample and nothing
else; the effects come from a PSG synth engine inside `GHOST.PRG` (ADSR-style voice records of
`0x8c` bytes, runtime `0x1459a` in the depacked image) that the loader agent will name.


---

## `GHOST.DEM` — the attract-mode playback

**CONFIRMED.** 6,000 bytes = **1,000 records of 6 bytes**. At 50 Hz that is 20 s of attract mode.
The six fields, over all 1,000 records:

| field | range | mean \|Δ\| per record | reading |
|---|---|---:|---|
| 0 | 0–92 | 0.72 | x of one object |
| 1 | 0–62 | 0.85 | y of that object |
| 2 | **0–44** | 1.81 | that object's sprite |
| 3 | 6–81 | 0.38 | x of a second object |
| 4 | 3–56 | 0.29 | y of that object |
| 5 | **0–12** | 1.59 | that object's sprite |

**HYPOTHESIS: the record is `(ghost x, ghost y, ghost tile, bubble x, bubble y, bubble frame)` —
recorded object state, not input.** It is not the input-script reading the opening bytes suggest
(`1b 1c 01 35 20 04` looks like IKBD scancodes until the fields are separated). Three things back
it, and they cross-check against `GHOST.DAT`:

* **Field 2 stays inside the ghost's tile bank.** It takes every value 0–44 and never more — and
  tiles 0–46 are exactly the mono-white ghost frames found independently above. It also moves in
  4-step cycles within a base (…5,6,7,8,5… then …25,26,27,28,25…), which is a per-direction
  animation reading its tile index straight out of the bank.
* **Field 5 tracks the bubble's life, and 47 + field 5 lands on the right tiles.** It normally
  cycles 4→12 (nine values = the nine bubble frames, tiles 51–59). Three times in the demo it
  instead runs 0, 1, 2, 3 and then **holds at 3** for 36–40 records: 47+0/1/2 are the three sparkle
  frames and 47+3 = tile 50, the empty one. That is a pop followed by ~0.75 s with no bubble.
* **Fields 3–4 freeze for exactly those stretches** — the bubble's position stops updating at
  (68,28), (27,56) and (64,37) while field 5 sits at 3, and resumes when it returns to 4–12.

**OPEN: the coordinate unit and origin.** Neither pair maps cleanly onto 320×192. Four pixels per
unit would put the ghost's x at 368 and its y at 248, both off the picture; the ranges also differ
between the two objects (0–92 / 0–62 against 6–81 / 3–56), which the demo simply not visiting the
extremes would explain, but so would two different origins. The code settles it.

---

## What the code must answer

1. **`GHOST.DAT`'s room maps.** The 35 rooms are presumably lists of tile indices; find the table
   and the drawing loop. `extract_gfx.py` is structured so a `render_room()` beside `tile_grid()`,
   fed those indices, is the whole addition.
2. **Transparency.** Does the blitter treat index 0 as transparent, or is a mask built at run time
   for the ghost and bubble tiles?
3. **Palettes.** Is the palette at the end of `GHOST.DAT` the only one, or does the PRG hold
   per-room palettes (the title's is already a second, different one)? Look for `Setpalette`
   (`Trap #14`, opcode 6) and the pointer it is handed.
4. **`GHOST.DEM`'s coordinate unit and origin**, and whether the file is played at one record per
   VBL.
5. **Where the music and the sound effects are.** Neither is on the disk as data: Bubble Ghost's
   YM2149 title tune and its effects both come out of `GHOST.PRG`. The effects have already been
   located — a PSG synth engine with ADSR-style voice records of `0x8c` bytes at runtime `0x1459a`
   in the depacked image — and the tune should be a VBL-installed refresh routine (`_vblqueue` at
   `0x456`, see `docs/sound.md`). Once both are named, capture them the way
   `projects/zynaps/tools/extract_audio.py` captures Zynaps': run the original code under the kit's
   Musashi oracle, log the `$ff8800`/`$ff8802` writes per 50 Hz frame, and render them through
   `projects/buggyboy/recreate/sound/ym2149.py`.
