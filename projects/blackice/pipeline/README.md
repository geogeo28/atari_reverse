# stepix — asset pipeline for an STE raycaster

Host-side Python that turns procedural or PNG art into the exact bytes the 68000 engine
reads. **This file is the contract**: every table below is byte-exact, big-endian, and pinned
by a test. The C engine is written against this document; `stepix/` is its reference
implementation and `depack.c` is the one piece that ships to the target.

```
stepix/                       tests/                     out/            (generated)
  palette.py   colourspace.py   test_palette.py            *.bin  native blobs
  quantize.py  planar.py        test_quantize.py           *.png  2x previews
  texture.py   sprite.py        test_planar.py             *.pi1  DEGAS screen
  font.py      pack.py          test_texture.py            demo.pak
  demo_assets.py                test_sprite.py             demo_assets.h
depack.c depack.h              test_pack.py
depack_main.c (test harness)   test_font.py test_demo_assets.py
```

Build the demo set and previews:

```sh
python3 -m stepix.demo_assets out      # writes out/
python3 -m pytest tests/ -q            # the whole suite
```

All multi-byte fields are **big-endian**. All offsets are **from the start of the blob**.
Names are ASCII, NUL-padded to 8 bytes, and **upper-cased by the writer**: a name longer than
8 bytes is an error rather than a silent truncation, and two names that differ only in case
(`font` and `FONT`) are rejected as a collision rather than written twice.

---

## 1. Palette word — `$ffff8240 + 2n`

Each channel is a 4-bit intensity 0..15. The nibble **stored in the register is a rotation of
the intensity**: the STE's extra bit was bolted on at bit 3 as the new *least* significant
bit, so ST software writing bits 2..0 still means the same brightness.

```
encode:  nibble    = (intensity >> 1) | ((intensity & 1) << 3)
decode:  intensity = ((nibble & 7) << 1) | (nibble >> 3)

word: bits 15..12 = 0 | 11..8 = red nibble | 7..4 = green nibble | 3..0 = blue nibble
```

| RGB (0..15)  | word     | note                                                     |
|--------------|----------|----------------------------------------------------------|
| 15, 15, 15   | `$0FFF`  | STE white                                                 |
| 14, 14, 14   | `$0777`  | "ST white" — even intensities are ST-compatible           |
| 8, 8, 8      | `$0444`  | **not** `$0888`; the rotation drops the LSB out           |
| 1, 0, 0      | `$0800`  | intensity 1 sets only the STE-only bit 3                  |
| 7, 0, 0      | `$0B00`  |                                                           |
| 2, 4, 6      | `$0123`  |                                                           |
| 0, 0, 0      | `$0000`  |                                                           |

**Source**: `docs/graphics.md` in this workspace, which matches the Hatari shifter model.
*Verified against documentation, not against real hardware — see REPORT.md.*

A channel whose intensity is **even** has bit 3 clear, so its word is identical to the ST
word for `intensity/2`. `is_st_compatible(word)` reports this; `to_st_word(word)` truncates.

**On-disk palette** (`PALETTE`, 32 bytes): 16 big-endian words, index 0 first. Copy straight
to `$ffff8240`. **Index 0 is the background and the hardware border colour** —
`StePalette.build(background, entries)` is the only constructor that can place it.

---

## 2. Screen bitmap — 4 bitplanes, word-interleaved

320x200, 16 colours, **160 bytes per row, 32,000 bytes per screen**.

```
per 16 pixels:  word plane0 | word plane1 | word plane2 | word plane3
plane 0 = bit 0 (LSB) of the colour index
bit 15 of a word = the LEFTMOST of those 16 pixels
```

Pinned examples: index 1 at the leftmost pixel = `80 00 00 00 00 00 00 00`;
index 8 at the rightmost = `00 00 00 00 00 00 00 01`; sixteen pixels of index 5 =
`FF FF 00 00 FF FF 00 00`.

### `.PI1` (DEGAS Elite, uncompressed) — 32,034 bytes

| Offset | Size   | Field                                    |
|--------|--------|------------------------------------------|
| 0      | 2      | resolution word, `$0000` = low res       |
| 2      | 32     | 16 palette words                         |
| 34     | 32000  | the interleaved screen                   |

The palette written is the **STE** word (what the hardware register takes), and `read_pi1`
decodes STE words. An ST-only viewer wants each channel's STE low bit dropped; that is a
palette transform (`palette.to_st_word`), applied by the caller before writing, not a flag on
the file format.

---

## 3. Wall textures — `.TEX`, magic `STXT`

64x64 texels, **one byte per texel, COLUMN-MAJOR**: texel `(x, y)` is at `x * 64 + y`, so a
texture column is 64 contiguous bytes and a column draw is `move.b (a0)+,d0` with the
caller's fractional step. Planar is deliberately *not* used here.

| Offset | Size | Field                                                   |
|--------|------|---------------------------------------------------------|
| 0      | 4    | magic `"STXT"`                                          |
| 4      | 2    | version = 1                                             |
| 6      | 2    | texture count                                           |
| 8      | 2    | dimension = 64                                          |
| 10     | 2    | flags — bit 0 (`TEX_FLAG_DARK`) = dark variants present  |
| 12     | 12·n | entry table                                             |

Entry (12 bytes):

| Offset | Size | Field                                       |
|--------|------|---------------------------------------------|
| 0      | 8    | name, NUL-padded                            |
| 8      | 4    | offset of the **lit** texels                |

When `TEX_FLAG_DARK` is set the **dark variant sits immediately after the lit one**, at
`offset + 4096` — there is no second offset table. Texel data starts at `12 + 12 * count`.

### Shade table — the N-S vs E-W lighting cue

16 bytes, `index -> darker index`, applied at build time so the shaded side costs a different
base pointer and nothing per pixel. Built by darkening each entry in **linear light** and
matching in CIE Lab, constrained to entries that are **strictly darker** — an unconstrained
Lab search was measured mapping a colour to a *lighter* one on a coarse ramp, which inverts
the cue. Demo table:

```
00 05 01 02 02 00 05 06 07 05 09 0a 05 02 0d 0f
```

---

## 4. Billboard sprites — `.SPR`, magic `STSP`

Same 64x64 column-major texels as textures, so walls and billboards share one column loop,
plus a per-column span table. **Transparent index = 15.** Index 0 is the border colour and
the darkest ink the wall ramps need, so it cannot be the key; index 15 is set to a garish
magenta (`$0F0F`) that must never appear in wall or HUD art, making a leak visible at once.

| Offset | Size | Field                                     |
|--------|------|-------------------------------------------|
| 0      | 4    | magic `"STSP"`                            |
| 4      | 2    | version = 1                               |
| 6      | 2    | sprite count                              |
| 8      | 2    | dimension = 64                            |
| 10     | 2    | transparent index = 15                    |
| 12     | 12·n | entry table: name8 + u32 record offset    |

Record (4,224 bytes), at the entry's offset:

| Offset | Size | Field                                                           |
|--------|------|------------------------------------------------------------------|
| 0      | 128  | span table: 64 x { first_opaque_row u8, last_opaque_row u8 }      |
| 128    | 4096 | column-major texels, `(x, y)` at `x * 64 + y`                     |

**A fully transparent column is encoded `first = $FF, last = $00`**, so the engine's single
skip test is `if (first > last) continue;` — no separate empty flag.

---

## 5. HUD-layer art — planar data + 1-plane AND mask

For art drawn at **fixed screen positions on 16-pixel boundaries** (weapon overlay, status
icons). No pre-shifted rotations are generated: the HUD does not move, and pre-shifting would
multiply the art by 16 for nothing.

- `<name>_data` — standard interleaved planar (§2), width a multiple of 16, with every
  transparent pixel forced to **index 0** so the OR cannot leak.
- `<name>_mask` — **one** plane, one word per 16 pixels, `mask_row_bytes = width/16*2`.
  A set bit means **transparent**.

Draw, per 16-pixel chunk, reusing the same mask word for all four planes:

```
and.w  mask,(dst)     ; keep the background where the mask bit is set
or.w   data,(dst)     ; drop in the sprite pixels
```

Demo icon: 32x32, `data_row_bytes = 16`, `mask_row_bytes = 4`, 512 + 128 bytes.

---

## 6. Font — `FONT`, 768 bytes

8x8, **1 bitplane**, one byte per row, **bit 7 = leftmost pixel**. 96 glyphs, ASCII 32..127;
glyph for character `c` starts at `(c - 32) * 8`. Glyphs are drawn 5x7 inside the 8x8 cell,
leaving a 1px right/bottom gap so text does not touch. Lowercase maps to the uppercase
glyphs (the HUD vocabulary is uppercase and 5x7 has no room for descenders); unmapped
codepoints render a hollow box.

---

## 7. Archive — `.PAK`, magic `STPK`

| Offset | Size | Field                     |
|--------|------|---------------------------|
| 0      | 4    | magic `"STPK"`            |
| 4      | 2    | version = 1               |
| 6      | 2    | entry count               |
| 8      | 24·n | directory                 |

Directory entry (24 bytes):

| Offset | Size | Field                                          |
|--------|------|------------------------------------------------|
| 0      | 8    | name, NUL-padded                               |
| 8      | 4    | offset of the payload, from the file start     |
| 12     | 4    | packed length                                  |
| 16     | 4    | raw length                                     |
| 20     | 2    | method: 0 = stored, 1 = LZSS                   |
| 22     | 2    | reserved, zero                                 |

**Every payload offset is even** — the 68000 reads these blobs with word and long moves. A
member is stored raw whenever compression would not shrink it.

### LZSS stream (method 1)

```
control byte, bits consumed MSB first, 8 tokens per control byte
  bit = 1 -> one literal byte follows
  bit = 0 -> 2-byte big-endian match token:  ((len - 3) << 12) | (offset - 1)
             offset 1..4096 counts BACK from the current output position
             len    3..18
```

There is **no end marker**: the depacker stops at `raw_len`, which the directory entry
already carries. Matches are copied **one byte at a time** and may overlap their own output
(offset 1, len 18 = an 18-byte run fill) — `memcpy` would be wrong here.

`depack.c` is the engine-side implementation:

```c
int stepix_depack(const unsigned char *src, unsigned long packed_len,
                  unsigned char *dst, unsigned long raw_len);   /* 0 = OK, 1 = BAD_STREAM */
```

`packed_len` is the directory entry's packed length. The depacker checks, once per token and
never per byte, that the stream is not truncated and that a match offset does not reach before
`dst`; either fails with `STEPIX_DEPACK_BAD_STREAM`. A match whose length would run past
`dst + raw_len` is **clamped** to the room left, not rejected. `stepix/pack.py:lz_unpack` is
the Python twin and pairs the same policies (clamp on overshoot, `ValueError` on a bad offset
or a truncated stream), and `tests/test_pack.py` compiles the C and asserts Python-pack →
C-depack is identity on synthetic corpora, fuzzed data, and the real generated textures and
screen — plus that both twins agree on three malformed streams.

`depack.h` also restates the PAK directory constants for the engine (`PAK_HEADER_BYTES`,
`PAK_ENTRY_BYTES`, `PAK_ALIGNMENT`, the method codes); `tests/test_readme_contract.py` parses
them out of the header and pins them to `stepix.pack`.

---

## 8. Demo palette (generated)

Index 0 background, four ramps, index 15 the key. Ramp shades are spaced by perceived
lightness (CIE L*), not linearly, because even linear spacing turns to mud at 16 levels.

| Idx | Word    | RGB4        | Role                    | Idx | Word    | RGB4         | Role               |
|-----|---------|-------------|-------------------------|-----|---------|--------------|--------------------|
| 0   | `$0008` | 0, 0, 1     | background / border     | 8   | `$0E7F` | 13, 14, 15   | steel white (HUD)  |
| 1   | `$0288` | 4, 1, 1     | brick darkest           | 9   | `$0AA2` | 5, 5, 4      | stone dark         |
| 2   | `$0421` | 8, 4, 2     | brick                   | 10  | `$0C4B` | 9, 8, 7      | stone mid          |
| 3   | `$0F32` | 15, 6, 4    | brick                   | 11  | `$0EED` | 13, 13, 11   | stone light        |
| 4   | `$0FBA` | 15, 7, 5    | brick lit               | 12  | `$0A28` | 5, 4, 1      | wood dark          |
| 5   | `$0111` | 2, 2, 2     | steel dark              | 13  | `$0DB1` | 11, 7, 2     | wood mid           |
| 6   | `$0AA3` | 5, 5, 6     | steel                   | 14  | `$0F59` | 15, 10, 3    | wood light         |
| 7   | `$0CC5` | 9, 9, 10    | steel light             | 15  | `$0F0F` | 15, 0, 15    | **transparency key** |

## 9. Quantiser notes

`quantize.quantize_image` matches in **CIE Lab**, not RGB: on a 16-colour gamut a nearest-RGB
search picks hue-shifted neighbours that are numerically close and visibly wrong. Ordered
(Bayer 2x2 / 4x4) dither only — error diffusion does not tile, so it seams at every texture
repeat. `quantize.check_palettized` audits art that is supposed to be palettised already and
**reports rather than fixes**: silently "correcting" a stray colour hides the authoring bug.
