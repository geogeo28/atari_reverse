# Graphics

ST bitmaps are **planar**. Understanding the plane layout, palette, and any compression
lets you extract a game's art to PNG. Reference tool: `tools/extract_graphics.py`.

## Low-res planar format (320×200, 16 colours)

- 4 **bitplanes**. A pixel's 4-bit colour index = one bit taken from each plane.
- **Screen (interleaved)**: memory goes word0=plane0, word1=plane1, word2=plane2,
  word3=plane3, then the next 16 pixels, … (32000 bytes total).
- **Storage (contiguous/planar)**: assets are often stored as 4 separate planes back to
  back (plane0 = 8000 bytes, then plane1, …). Games convert contiguous→interleaved when
  drawing (look for copies with strides of `+8000/+16000/+24000` bytes — that's the tell).
- Plane 0 is the **LSB** of the colour index (standard). Getting plane order wrong
  scrambles colours but not shapes, so a greyscale-by-index render still looks "right"
  structurally — verify colour separately.

`extract_graphics.py` decodes a full-screen block as 4 contiguous planes → 320×200 indices
→ PNG. Feed it a palette (below) or it renders greyscale.

### The shared pixel model — `tools/st_pixels.py`

The layouts above vary along exactly two axes, and `tools/st_pixels.py` is the one place this
workspace spells either of them out — import it from a project's extractor rather than re-deriving
them (Zynaps' `projects/zynaps/tools/dat2png.py` and Wonder Boy's
`projects/wonderboy/tools/extract_gfx.py` both do).

- **Granularity.** A group of interleaved planes is either **word** granular (`unit_bits=16`: four
  big-endian plane words, 16 pixels — screens, tiles, most bitmaps) or **byte** granular
  (`unit_bits=8`: four consecutive plane bytes, 8 pixels — fonts, digit glyphs, other 8-px-wide
  cells). Within a group the **leftmost pixel is the most significant bit**.
- **Masked or not.** A sprite puts one extra **mask** field *ahead* of the four plane fields of
  every group, so a group is five fields wide, and a **set** mask bit means transparent (the drawing
  code ANDs the mask, then ORs the data — "Masked sprites" below). `decode_planar` returns
  `TRANSPARENT` for those pixels, which is `-1` **on purpose and never a palette subscript**: a
  masked pixel has no colour index at all, and `to_rgb_image` refuses a decode containing one rather
  than let `palette[-1]` quietly paint the last entry.

Two of its refusals are worth knowing about, because both failures are otherwise invisible in the
PNG: a slice too short for the requested `width × rows` raises instead of decoding the missing bytes
as zeros (a blank, entirely plausible-looking bitmap), and `split_rows` refuses a tall decode that
does not divide into equal frames. Colour lives in the same module — `st_word_to_rgb` is the
`value * 255 // 7` scaling below, and `is_st_colour_word` is the in-range test a palette scan is
built on.

## Palettes

- **ST**: 16 words, each `0x0RGB`, **3 bits/channel** (0–7). `r = (w>>8)&7` etc.,
  scale ×255/7.
- **STE**: 4 bits/channel but bit-rotated — the LSB sits in bit 3 of each nibble:
  intensity = `((v&7)<<1) | ((v>>3)&1)`. If ST decoding looks too dark/off, try STE. Going the other
  way — authoring a palette for a real machine — the encode is `((i>>1)&7) | ((i&1)<<3)`, and the
  useful predicate beside it is "does this word use bit 3 in any channel?", i.e. whether the colour
  is reproducible on a plain ST at all (`projects/blackice/pipeline/stepix/palette.py`).
- Find palettes in the **code** (`.PRG`), not the graphics file: scan for 16 consecutive
  words with the top nibble zero and channel nibbles in range. Confirm by finding the
  `Setpalette` call and reading the pointer it passes (`a0`). Games keep a **table** of
  per-scene/leg palettes; the atlas often shares one master palette.

```bash
python3 tools/extract_graphics.py bin/GRAPHICS.GRA out/gfx \
  --pal-file bin/GAME.PRG --pal-off 0x<palette-file-offset> [--skip 0x<header-bytes>]
```

`--skip` drops a raw header/sprite table that some files carry *before* the RLE stream —
read the unpacker to find it (see below). Decoding without the skip prepends that table as
literals and shifts every screen; the tell-tale is a decompressed size that isn't a clean
multiple of the screen size.

## Compression (RLE is common)

ST assets are frequently run-length encoded with sentinel words. Find the unpacker in the
code (it reads a stream, writes runs) and mirror its rules. BuggyBoy's `GRAPHICS.GRA`:

- `0x1234 N` → `N+1` words of `0x0000`; `0x1234 0` → literal `0x1234`
- `0x5678 N` → `N+1` words of `0xFFFF`; `0x5678 0` → literal `0x5678`
- `0x1234 0x1234 0x1234` → end of stream; anything else → literal word

That decompressed 182 KB → **8× 320×200 screens** (logo, sprites, scenery, HUD, font).
The file opens with a **0xd00-byte (3328) raw sprite table** before the RLE stream — the
unpacker (`unpack_graphics` @ `0x10620`) pre-copies it (416 records × 8 B) into a work
buffer, then decompresses the stream that follows. Pass `--skip 0xd00` to line up on it.
These 8 screens are **sprite/tile atlases** (dense source art the game composites and
scales at runtime), not finished framebuffers — expect e.g. the intro "LEG"/digit text at
several zoom sizes packed into one atlas. Tables of small `0x1234`-delimited records =
individual sprites/tiles.

## Masked sprites

Objects that overlay a background use a **mask + data** pair (often adjacent longwords):
`AND` the mask, `OR` the data. Edge masks (e.g. two small lookup tables) anti-alias the
scaled object's left/right boundary. Scaling for pseudo-3D is done by choosing how many
screen rows each source row covers, from a perspective table.

→ Sound assets: [`sound.md`](sound.md). Naming the drawing code: [`methodology.md`](methodology.md).